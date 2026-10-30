"""Composite Stage S entry gate (PQ4.0).

The local extraction-profile verdict (surface distance, feature survival,
manifoldness, root connectivity) is necessary but not sufficient: a grey Stage T
field can produce a clean STL while Stage T computed its forces on a
semi-permeable object. This module composes the complete entry gate

    ready_for_stage_s =
        source lineage
      & source discreteness
      & extraction profile
      & volume fidelity
      & width / gap policy
      & component / root policy
      & self-intersection / manifoldness
      & clearance

and records every sub-verdict separately, so a local pass can never overwrite a
global failure. A policy that the ProblemSpec does not declare is recorded as
``not_required`` explicitly, never as a silent pass.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
from scipy import ndimage

from .extraction_qualification import (
    EXTRACTION_QUALIFICATION_PROFILE_V2,
    ExtractionQualificationError,
    qualify_extraction,
)
from .fixed_grid_contract import _read_cell_vti
from .problem_spec import load_problem_spec
from .shape_feature_metrics import component_boundary_gap_m, occupancy_metrics
from .stage_v_domain_preflight import (
    STAGE_V_CLEARANCE_PROFILE_V1,
    evaluate_stage_v_domain_preflight,
)

VOLUME_FIDELITY_PROFILE_V1: dict[str, Any] = {
    "profile_id": "volume_fidelity_v1",
    "relative_max": 0.25,
    "revoxelized_relative_max": 0.20,
    "absolute_max_m3": 0.02,
    "calibration": "docs/evidence/pq4_volume_fidelity_calibration_2026_09.json",
    "calibration_correction": (
        "docs/evidence/pq4_volume_fidelity_calibration_correction_2026_09.json"
    ),
    "note": "tolernces sit above the analytic binary ground-truth floor "
    "(relative 0.093-0.181, revoxelized 0.023-0.161, absolute 0.0046-0.0109 m3)",
}


@dataclass(frozen=True)
class StageSEntryVerdict:
    ready_for_stage_s: bool
    profile_id: str
    reasons: list[str] = field(default_factory=list)
    sub_verdicts: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _fail(reasons: list[str], name: str, message: str) -> None:
    reasons.append(f"{name}:{message}")


def qualify_stage_s_entry(
    handoff_manifest_json: str | Path,
    *,
    mesh_path: str | Path,
    problem_spec_yaml: str | Path,
    extraction_profile: dict[str, Any] | None = None,
    volume_profile: dict[str, Any] | None = None,
    clearance_profile: dict[str, Any] | None = None,
    volume_constraint: dict[str, Any] | None = None,
) -> StageSEntryVerdict:
    """Compose the complete Stage S entry gate for one handoff.

    ``volume_constraint`` optionally registers the optimizer's projected-volume
    limit and its feasibility tolerance:
    ``{"projected_volume": v, "limit": vmax, "absolute_tolerance": 1e-4}``.
    """

    import hashlib

    import trimesh

    extraction_profile = dict(
        EXTRACTION_QUALIFICATION_PROFILE_V2 if extraction_profile is None else extraction_profile
    )
    volume_profile = dict(
        VOLUME_FIDELITY_PROFILE_V1 if volume_profile is None else volume_profile
    )
    clearance_profile = dict(
        STAGE_V_CLEARANCE_PROFILE_V1 if clearance_profile is None else clearance_profile
    )
    manifest_path = Path(handoff_manifest_json)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    base = manifest_path.parent
    artifacts = manifest.get("artifacts") or {}
    # the manifest's own surface path is authoritative; a caller-provided path
    # is only used when the manifest is silent, and must exist
    manifest_mesh = artifacts.get("surface_stl")
    if isinstance(manifest_mesh, dict):
        # absolute: the clearance preflight resolves relative STLs against the
        # spec directory, not the manifest directory
        mesh_path = (base / manifest_mesh["path"]).resolve()
    elif not Path(mesh_path).is_file():
        raise ExtractionQualificationError(
            f"mesh path is missing and the manifest has no surface_stl: {mesh_path}"
        )
    reasons: list[str] = []
    sub: dict[str, Any] = {}

    # --- lineage -------------------------------------------------------------
    lineage: dict[str, Any] = {"status": "pass", "artifacts": {}}
    for key in ("revoxelized_density_vti", "source_density_vti", "surface_stl"):
        record = artifacts.get(key)
        if not isinstance(record, dict):
            lineage = {"status": "fail", "reason": f"artifact {key} is missing"}
            _fail(reasons, "lineage", f"{key} is missing")
            break
        path = base / record["path"]
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        lineage["artifacts"][key] = {"sha256_match": actual == record["sha256"]}
        if actual != record["sha256"]:
            lineage["status"] = "fail"
            _fail(reasons, "lineage", f"{key} changed after the handoff")
    sub["lineage"] = lineage
    if lineage["status"] == "fail":
        return StageSEntryVerdict(False, "stage_s_entry_v1", reasons, sub)

    revoxelized_path = base / artifacts["revoxelized_density_vti"]["path"]
    source_density_path = base / artifacts["source_density_vti"]["path"]
    revoxelized_grid, revoxelized_arrays = _read_cell_vti(
        revoxelized_path, expected_kind="stage_s_revoxelized_density"
    )
    source_grid, source_arrays = _read_cell_vti(
        source_density_path, expected_kind="fixed_grid_density"
    )
    spacing = float(revoxelized_grid.spacing[0])
    shape = tuple(int(v) for v in revoxelized_grid.cell_shape)
    material = (revoxelized_arrays["rho_revoxelized"] > 0.5).reshape(shape, order="F")
    spec = load_problem_spec(problem_spec_yaml)
    report = json.loads(
        (base / artifacts.get("fidelity_report", {}).get("path", "fidelity_report.json")).read_text(
            encoding="utf-8"
        )
    )

    # --- discreteness (Stage T grey-field gate) ------------------------------
    discreteness = report.get("discreteness") or {}
    disc_ok = discreteness.get("status") == "pass"
    sub["discreteness"] = {
        "pass": bool(disc_ok),
        "status": discreteness.get("status"),
        "mean_nd": discreteness.get("mean_nd"),
        "mean_nd_max": discreteness.get("mean_nd_max", discreteness.get("max_mean_nd_allowed")),
        "max_rho_threshold": discreteness.get("max_rho_threshold"),
        "reasons": discreteness.get("reasons"),
    }
    if not disc_ok:
        _fail(reasons, "discreteness", "source density is not sufficiently discrete")

    # --- extraction profile (local quantitative checks) ----------------------
    try:
        extraction = qualify_extraction(
            manifest_path, mesh_path=mesh_path, profile=extraction_profile
        )
        sub["extraction_profile"] = {
            "pass": extraction.ready_for_stage_s,
            "reasons": extraction.reasons,
            "checks": extraction.checks,
        }
        for reason in extraction.reasons:
            _fail(reasons, "extraction_profile", reason)
    except ExtractionQualificationError as exc:
        sub["extraction_profile"] = {"pass": False, "reasons": [str(exc)]}
        _fail(reasons, "extraction_profile", str(exc))

    # --- volume fidelity -----------------------------------------------------
    volume = report.get("volume") or {}
    relative = volume.get("relative_difference")
    revoxelized_relative = volume.get("revoxelized_relative_difference")
    absolute = volume.get("absolute_difference_m3")
    volume_ok = (
        relative is not None
        and revoxelized_relative is not None
        and absolute is not None
        and relative <= float(volume_profile["relative_max"])
        and revoxelized_relative <= float(volume_profile["revoxelized_relative_max"])
        and absolute <= float(volume_profile["absolute_max_m3"])
    )
    sub["volume_fidelity"] = {
        "pass": bool(volume_ok),
        "relative": relative,
        "revoxelized_relative": revoxelized_relative,
        "absolute_m3": absolute,
        "profile": volume_profile["profile_id"],
    }
    if not volume_ok:
        _fail(reasons, "volume_fidelity", "volume difference exceeds the registered profile")

    # --- width / gap policy --------------------------------------------------
    policy = spec.topology_policy
    width: dict[str, Any] = {"pass": True, "measured": {}, "declared": {}, "status": "measured"}
    if not material.any():
        width = {"pass": False, "status": "empty_material"}
        _fail(reasons, "width_gap", "no material to measure")
    else:
        material_metrics = occupancy_metrics(material, spacing)
        width["measured"]["ridge_width_p5_m"] = material_metrics["thickness_ridge_m_p5"]
        width["measured"]["minimum_solid_width_m"] = material_metrics[
            "thickness_ridge_m_min"
        ]
        width["quantization_tolerance_m"] = spacing / 2
        width["note"] = (
            "minimum_solid_width_m is the minimum medial-axis (ridge) thickness "
            "of the supersampled occupancy, calibrated on analytic fixtures; "
            "ridge_width_p5_m is a separate quantile recorded for information "
            "and is never substituted for a declared minimum"
        )
        if policy.minimum_solid_width_m is not None:
            width["declared"]["minimum_solid_width_m"] = policy.minimum_solid_width_m
            if (
                material_metrics["thickness_ridge_m_min"]
                < policy.minimum_solid_width_m - spacing / 2
            ):
                width["pass"] = False
                _fail(reasons, "width_gap", "minimum solid width below the declared minimum")
        complement = ~material
        if complement.any():
            void_metrics = occupancy_metrics(complement, spacing)
            width["measured"]["void_ridge_width_p5_m"] = void_metrics[
                "thickness_ridge_m_p5"
            ]
            width["measured"]["minimum_void_width_m"] = void_metrics[
                "thickness_ridge_m_min"
            ]
            if policy.minimum_void_width_m is not None:
                width["declared"]["minimum_void_width_m"] = policy.minimum_void_width_m
                if (
                    void_metrics["thickness_ridge_m_min"]
                    < policy.minimum_void_width_m - spacing / 2
                ):
                    width["pass"] = False
                    _fail(reasons, "width_gap", "minimum void width below the declared policy")
        components, count = ndimage.label(material, structure=np.ones((3, 3, 3), dtype=bool))
        width["measured"]["component_count"] = int(count)
        if count > 1:
            # calibrated face-to-face gap: the old formula read a
            # center-to-center EDT and overestimated by one voxel
            measured_gap = component_boundary_gap_m(components, spacing)
            width["measured"]["component_boundary_gap_m"] = measured_gap
            if policy.minimum_gap_m is not None:
                width["declared"]["minimum_gap_m"] = policy.minimum_gap_m
                if measured_gap is None or measured_gap < policy.minimum_gap_m - spacing / 2:
                    width["pass"] = False
                    _fail(reasons, "width_gap", "minimum gap below the declared policy")
    sub["width_gap"] = width

    # --- component / root policy --------------------------------------------
    connectivity = policy.solid_connectivity
    root_mask = np.asarray(
        source_arrays.get("root_mask", np.zeros(source_grid.cell_count, dtype=np.uint8))
    ).reshape(shape, order="F") > 0
    components = {
        "mode": connectivity.mode,
        "max_components": connectivity.max_components,
        "component_count": int(sub.get("width_gap", {}).get("component_count", 0)),
        "root_required": connectivity.mode in {"root_connected", "required_root_groups"},
        "root_mask_cells": int(root_mask.sum()),
    }
    components_ok = True
    if connectivity.mode != "disabled":
        _, count = ndimage.label(material, structure=np.ones((3, 3, 3), dtype=bool))
        components["component_count"] = int(count)
        if connectivity.max_components is not None and count > int(connectivity.max_components):
            components_ok = False
            _fail(reasons, "components_root", "component count exceeds the declared maximum")
        if components["root_required"]:
            if not root_mask.any():
                components_ok = False
                _fail(
                    reasons,
                    "components_root",
                    "the policy requires root connectivity but the source root mask is empty",
                )
            else:
                labels, _ = ndimage.label(material, structure=np.ones((3, 3, 3), dtype=bool))
                attached = all(
                    bool(np.any(root_mask & (labels == label)))
                    for label in range(1, int(labels.max()) + 1)
                )
                components["all_attached"] = attached
                if not attached:
                    components_ok = False
                    _fail(reasons, "components_root", "an unattached material component exists")
    components["pass"] = bool(components_ok)
    sub["components_root"] = components

    # --- optimizer volume constraint ----------------------------------------
    if volume_constraint is not None:
        projected = float(volume_constraint["projected_volume"])
        limit = float(volume_constraint["limit"])
        tolerance = float(volume_constraint.get("absolute_tolerance", 0.0))
        violation = projected - limit
        volume_pass = violation <= tolerance
        sub["volume_constraint"] = {
            "pass": bool(volume_pass),
            "projected_volume": projected,
            "limit": limit,
            "violation": violation,
            "absolute_tolerance": tolerance,
        }
        if not volume_pass:
            _fail(reasons, "volume_constraint", "the projected volume exceeds the declared limit")

    # --- clearance -----------------------------------------------------------
    try:
        preflight = evaluate_stage_v_domain_preflight(
            spec, mesh_path, float(spec.grid.voxel_size_m), profile=clearance_profile
        )
        clearance = {
            "pass": bool(preflight.qualified),
            "reasons": list(preflight.reasons),
            "profile_id": clearance_profile.get("profile_id", "stage_v_clearance_v1"),
        }
        if not preflight.qualified:
            _fail(reasons, "clearance", "the extracted surface fails the clearance preflight")
    except Exception as exc:  # noqa: BLE001 - recorded, never hidden
        clearance = {"pass": False, "reasons": [str(exc)]}
        _fail(reasons, "clearance", str(exc))
    sub["clearance"] = clearance

    ready = not reasons
    return StageSEntryVerdict(
        ready_for_stage_s=ready,
        profile_id="stage_s_entry_v1",
        reasons=reasons,
        sub_verdicts=sub,
    )


__all__ = [
    "VOLUME_FIDELITY_PROFILE_V1",
    "StageSEntryVerdict",
    "qualify_stage_s_entry",
]
