"""Pre-registered iso-surface threshold sweep for the T-to-S handoff (DF4).

Choosing the extraction threshold by looking at the best downstream result is a
scope violation (architecture plan DF4). This module runs the bounded sweep over
a registered threshold range, records every row including failures, measures the
extraction sensitivity of each threshold (volume error, watertightness,
components, revoxelized geometry), and then applies a registered selection rule.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .fixed_grid_contract import _read_cell_vti
from .extraction_qualification import ExtractionQualification, qualify_extraction
from .handoff import build_density_to_sdf_handoff
from .stage_s_entry import StageSEntryVerdict, qualify_stage_s_entry
from .shape_feature_metrics import occupancy_metrics

SELECTION_RULES = (
    "registered_range_min_abs_volume_error",
    "registered_range_first_that_passes",
)


class ExtractionSweepError(ValueError):
    """Fail-closed extraction sweep contract violation."""


@dataclass(frozen=True)
class SweepRow:
    threshold: float
    output_dir: str
    status: str
    error: str | None
    ok: bool
    ready_for_stage_s: bool
    watertight: bool
    positive_volume: bool
    component_count: int | None
    volume_relative_difference: float | None
    revoxelized_relative_difference: float | None
    checks: dict[str, Any] = field(default_factory=dict)
    manifest_json: str | None = None
    manifest_sha256: str | None = None
    geometry_metrics: dict[str, Any] | None = None
    geometry_metrics_status: str = "not_requested"
    qualification: dict[str, Any] | None = None
    extraction_profile_pass: bool | None = None
    stage_s_entry: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _geometry_metrics(revoxelized_vti: Path) -> tuple[dict[str, Any] | None, str]:
    try:
        grid, arrays = _read_cell_vti(revoxelized_vti, expected_kind="stage_s_revoxelized_density")
    except Exception as exc:  # noqa: BLE001 - recorded, never hidden
        return None, f"unavailable: {exc}"
    if "rho_revoxelized" not in arrays:
        return None, "unavailable: rho_revoxelized array is missing"
    material = (arrays["rho_revoxelized"] > 0.5).reshape(
        tuple(grid.cell_shape), order="F"
    )
    if not material.any():
        return {"empty": True}, "empty"
    metrics = occupancy_metrics(material, float(grid.spacing[0]))
    return metrics, "measured"


def run_extraction_threshold_sweep(
    topology_state_json: str | Path,
    *,
    thresholds: list[float] | tuple[float, ...],
    output_dir: str | Path,
    selection_rule: dict[str, Any],
    rho_variant: str | None = None,
    qualification_profile: dict[str, Any] | None = None,
    stage_s_entry: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run the registered thresholds and apply the registered selection rule.

    ``stage_s_entry`` (a mapping with ``problem_spec_yaml``) enables the
    composite Stage S entry gate: the row's ``ready_for_stage_s`` is the
    conjunction of lineage, discreteness, extraction profile, volume fidelity,
    width/gap, component/root policy and clearance. The local extraction
    verdict is recorded separately as ``extraction_profile_pass`` and can never
    override a global failure.

    ``selection_rule`` must declare ``require_ready_for_stage_s: true``; the
    selection never picks a threshold that failed the composite gate.
    """

    rule_kind = selection_rule.get("kind")
    if rule_kind not in SELECTION_RULES:
        raise ExtractionSweepError(
            f"unknown selection rule {rule_kind!r}; registered rules are {SELECTION_RULES}"
        )
    registered_range = selection_rule.get("range")
    if (
        not isinstance(registered_range, (list, tuple))
        or len(registered_range) != 2
        or not 0.0 < float(registered_range[0]) < float(registered_range[1]) < 1.0
    ):
        raise ExtractionSweepError(
            "selection_rule.range must be an increasing pair inside (0, 1)"
        )
    if selection_rule.get("require_ready_for_stage_s") is not True:
        raise ExtractionSweepError(
            "the selection rule must declare require_ready_for_stage_s=true; "
            "selecting a threshold that failed the Stage S entry gate is refused"
        )
    if not thresholds:
        raise ExtractionSweepError("at least one threshold is required")
    ordered = sorted({float(value) for value in thresholds})
    if any(not 0.0 < value < 1.0 for value in ordered):
        raise ExtractionSweepError("thresholds must be inside (0, 1)")

    target_root = Path(output_dir)
    target_root.mkdir(parents=True, exist_ok=True)
    rows: list[SweepRow] = []
    for threshold in ordered:
        row_dir = target_root / f"threshold_{threshold:.6g}"
        try:
            artifacts = build_density_to_sdf_handoff(
                topology_state_json,
                output_dir=row_dir,
                rho_variant=rho_variant,
                iso_value=threshold,
            )
            report = artifacts.fidelity_report
            volume = report.get("volume", {})
            surface = report.get("surface", {})
            qualification: ExtractionQualification | None = None
            entry: StageSEntryVerdict | None = None
            if stage_s_entry is not None:
                # the composite gate owns the verdict; the extraction profile it
                # uses is forwarded so the local row field and the composite
                # sub-verdict always come from the same profile
                entry = qualify_stage_s_entry(
                    artifacts.manifest_json,
                    mesh_path=artifacts.surface_stl,
                    problem_spec_yaml=stage_s_entry["problem_spec_yaml"],
                    extraction_profile=stage_s_entry.get("extraction_profile"),
                    volume_profile=stage_s_entry.get("volume_profile"),
                    clearance_profile=stage_s_entry.get("clearance_profile"),
                    volume_constraint=stage_s_entry.get("volume_constraint"),
                )
            elif qualification_profile is not None:
                qualification = qualify_extraction(
                    artifacts.manifest_json,
                    mesh_path=artifacts.surface_stl,
                    profile=qualification_profile,
                )
            geometry_metrics, geometry_status = _geometry_metrics(
                artifacts.revoxelized_density_vti
            )
            rows.append(
                SweepRow(
                    threshold=threshold,
                    output_dir=str(artifacts.output_dir),
                    status="ok",
                    error=None,
                    ok=bool(report.get("ok")),
                    ready_for_stage_s=(
                        entry.ready_for_stage_s
                        if entry is not None
                        else False
                        if stage_s_entry is not None
                        else bool(report.get("ready_for_stage_s"))
                    ),
                    extraction_profile_pass=(
                        (
                            (entry.sub_verdicts.get("extraction_profile") or {}).get("pass")
                            if entry is not None
                            else None
                        )
                        if stage_s_entry is not None
                        else (
                            qualification.ready_for_stage_s
                            if qualification is not None
                            else None
                        )
                    ),
                    watertight=bool(surface.get("watertight")),
                    positive_volume=bool(surface.get("positive_volume")),
                    component_count=surface.get("component_count"),
                    volume_relative_difference=volume.get("relative_difference"),
                    revoxelized_relative_difference=volume.get(
                        "revoxelized_relative_difference"
                    ),
                    checks=dict(report.get("checks", {})),
                    manifest_json=str(artifacts.manifest_json),
                    manifest_sha256=_sha256_file(artifacts.manifest_json),
                    geometry_metrics=geometry_metrics,
                    geometry_metrics_status=geometry_status,
                    qualification=qualification.to_dict() if qualification else None,
                    stage_s_entry=entry.to_dict() if entry else None,
                )
            )
        except Exception as exc:  # noqa: BLE001 - a failed threshold stays in the table
            rows.append(
                SweepRow(
                    threshold=threshold,
                    output_dir=str(row_dir),
                    status="error",
                    error=str(exc),
                    ok=False,
                    ready_for_stage_s=False,
                    watertight=False,
                    positive_volume=False,
                    component_count=None,
                    volume_relative_difference=None,
                    revoxelized_relative_difference=None,
                )
            )

    low, high = float(registered_range[0]), float(registered_range[1])
    require_ready = bool(selection_rule.get("require_ready_for_stage_s", False))
    eligible = [
        row
        for row in rows
        if row.status == "ok"
        and row.ok
        and (row.ready_for_stage_s or not require_ready)
        and low <= row.threshold <= high
    ]
    selected: SweepRow | None = None
    reason = "no eligible threshold inside the registered range"
    if eligible:
        if rule_kind == "registered_range_min_abs_volume_error":
            eligible = [
                row for row in eligible if row.volume_relative_difference is not None
            ]
            selected = min(
                eligible,
                key=lambda row: (
                    abs(float(row.volume_relative_difference)),
                    row.threshold,
                ),
            ) if eligible else None
            reason = (
                "minimum |volume relative difference| among gate-passing thresholds "
                "inside the registered range"
            )
        else:
            selected = min(eligible, key=lambda row: row.threshold)
            reason = "first gate-passing threshold inside the registered range"

    summary = {
        "kind": "density_extraction_threshold_sweep",
        "schema_version": 1,
        "topology_state_json": str(Path(topology_state_json).resolve()),
        "output_dir": str(target_root.resolve()),
        "thresholds": ordered,
        "selection_rule": dict(selection_rule),
        "selected_threshold": selected.threshold if selected else None,
        "selected_manifest_json": selected.manifest_json if selected else None,
        "selection_reason": reason,
        "n_ready_for_stage_s": sum(1 for row in rows if row.ready_for_stage_s),
        "rows": [row.to_dict() for row in rows],
        "claims": {
            "extraction_sensitivity_measured": all(
                row.status == "ok" for row in rows
            ),
            "selection_is_registered_not_observed_best": True,
            "quantitative_qualification_evaluated": qualification_profile is not None,
            "stage_s_entry_gate_evaluated": stage_s_entry is not None,
        },
        "notes": (
            "every failed threshold remains an explicit row; the selection rule "
            "operates only inside the pre-registered range",
        ),
    }
    summary_path = target_root / "sweep_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


__all__ = [
    "ExtractionSweepError",
    "SELECTION_RULES",
    "SweepRow",
    "run_extraction_threshold_sweep",
]
