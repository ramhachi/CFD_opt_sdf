"""PQ4.1: run the composite Stage S entry gate on the v9 terminal candidate.

No solver run. The v9 terminal rho (b=16 convergence window, independent
terminal repeat) is re-materialized into the four registered fields, handed
off to a ``rho_projection`` iso-0.5 surface (``beta_solver`` retained as the
solver audit field), and judged by the complete composite gate. The verdict
is recorded append-only; a failure is recorded as such, never overridden.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from cfd_sdf import campaign_assertions as ca  # noqa: E402
from cfd_sdf.design_transform import ConeFilter, DesignTransform, RampInterpolation, TanhProjection  # noqa: E402
from cfd_sdf.fixed_grid_contract import CartesianCellGrid, _read_cell_vti, _write_cell_vti  # noqa: E402
from cfd_sdf.fixed_grid_primal import load_fixed_grid_density_state  # noqa: E402
from cfd_sdf.handoff import build_density_to_sdf_handoff  # noqa: E402
from cfd_sdf.stage_s_entry import qualify_stage_s_entry  # noqa: E402

V9_OUTCOME = ROOT / "docs/evidence/pq3_3b_campaign_v9_outcome_2026_09.json"
CAMPAIGN = ROOT / "work/pq3_3b_campaign_v9"
CANONICAL = ROOT / "work/df2_fd_refresh/topology_state.json"
PROBLEM_SPEC = ROOT / "work/pq4_candidate/project.yaml"
OUT = ROOT / "work/pq4_1_terminal_candidate"
EVIDENCE = ROOT / "docs/evidence/pq4_1_terminal_stage_s_entry_v2_2026_09.json"
SHAPE = (60, 32, 24)
SPACING_M = 0.05
FILTER_RADIUS_M = 0.15
PROJECTION_B = 16.0
RAMP_Q = 100.0
BETA_MAX = 2500.0
ISO_VALUE = 0.5
V_MAX = 0.07632566813424899
VOLUME_TOLERANCE = 1e-4


def _array_sha256(values: np.ndarray) -> str:
    raw = np.ascontiguousarray(np.asarray(values, dtype=np.float64))
    return hashlib.sha256(raw.tobytes()).hexdigest()


def main() -> None:
    if OUT.exists() or EVIDENCE.exists():
        raise SystemExit("PQ4.1 artifacts already exist; the evidence is append-only")
    outcome = ca.load_json(V9_OUTCOME)
    terminal = outcome["terminal"]
    rho_sha = terminal["rho_sha256"]
    latest = ca.load_json(CAMPAIGN / "latest.json")
    state = ca.load_json(CAMPAIGN / latest["state_path"])
    if state["rho_sha256"] != rho_sha:
        raise SystemExit("latest checkpoint does not hold the terminal rho")
    rho_path = CAMPAIGN / state["rho_path"]
    if ca.sha256_file(rho_path) != state["rho_file_sha256"]:
        raise SystemExit("terminal rho file hash mismatch")
    rho = np.load(rho_path, allow_pickle=False)
    if _array_sha256(rho) != rho_sha:
        raise SystemExit("terminal rho array hash mismatch")

    reference_grid, reference_arrays = _read_cell_vti(
        CANONICAL.parent / "density.vti", expected_kind="fixed_grid_density"
    )
    active = (
        (np.asarray(reference_arrays["active_design_mask"]) > 0)
        & (np.asarray(reference_arrays["allowed_mask"]) > 0)
        & ~(np.asarray(reference_arrays["forbidden_mask"]) > 0)
        & ~(np.asarray(reference_arrays["fixed_solid_mask"]) > 0)
    )
    transform = DesignTransform(
        shape=SHAPE,
        spacing_m=SPACING_M,
        active_mask=active,
        filter=ConeFilter(SHAPE, SPACING_M, active, radius_m=FILTER_RADIUS_M),
        projection=TanhProjection(PROJECTION_B, 0.5),
        ramp=RampInterpolation(RAMP_Q),
    )
    derived = transform.forward(np.asarray(rho, dtype=np.float64))
    fields = {
        "rho_design": np.asarray(rho, dtype=np.float32),
        "rho_filtered": np.asarray(derived.rho_filtered, dtype=np.float32),
        "rho_projection": np.asarray(derived.rho_projected, dtype=np.float32),
        "beta_solver": np.asarray(derived.beta, dtype=np.float32),
    }
    ramp_of_projection = RampInterpolation(RAMP_Q).forward(fields["rho_projection"].astype(np.float64))
    beta_identity = float(np.max(np.abs(ramp_of_projection - fields["beta_solver"].astype(np.float64))))
    projected_volume = float(fields["rho_projection"].astype(np.float64)[active].mean())

    OUT.mkdir(parents=True)
    grid = CartesianCellGrid(
        origin=tuple(reference_grid.origin),
        spacing=tuple(reference_grid.spacing),
        cell_shape=tuple(reference_grid.cell_shape),
    )
    bundle_paths: dict[str, str] = {}
    for name, values in fields.items():
        path = OUT / f"{name}.vti"
        _write_cell_vti(grid, {name: values}, path, kind=f"stage_t_field_{name}")
        bundle_paths[name] = str(path.relative_to(ROOT))
    candidate = OUT / "candidate"
    candidate.mkdir()
    arrays = {
        "rho": fields["rho_design"],
        "rho_filtered": fields["rho_filtered"],
        "rho_projection": fields["rho_projection"],
        "alpha": (BETA_MAX * fields["beta_solver"].astype(np.float64)).astype(np.float32),
        "allowed_mask": reference_arrays["allowed_mask"],
        "forbidden_mask": reference_arrays["forbidden_mask"],
        "fixed_solid_mask": reference_arrays["fixed_solid_mask"],
        "root_mask": reference_arrays["root_mask"],
        "active_design_mask": reference_arrays["active_design_mask"],
    }
    _write_cell_vti(grid, arrays, candidate / "density.vti", kind="fixed_grid_density")
    topology_state = {
        "schema_version": 1,
        "kind": "fixed_grid_topology_state",
        "design_variable": "rho",
        "grid": grid.to_dict(),
        "density_vti": "density.vti",
        "density_array": "rho_projection",
        "source_solver": {"backend": "pq4_1_terminal_candidate"},
    }
    (candidate / "topology_state.json").write_text(json.dumps(topology_state, indent=2), encoding="utf-8")

    verdict_record: dict
    handoff_record: dict | None = None
    try:
        handoff = build_density_to_sdf_handoff(
            candidate / "topology_state.json",
            output_dir=OUT / "handoff",
            rho_variant="rho_projection",
            iso_value=ISO_VALUE,
        )
        handoff_record = {
            "ok": bool(handoff.ok),
            "manifest_json": str(handoff.manifest_json.relative_to(ROOT)),
            "manifest_sha256": ca.sha256_file(handoff.manifest_json),
            "surface_stl": str(handoff.surface_stl.relative_to(ROOT)),
            "revoxelized_density_vti": str(handoff.revoxelized_density_vti.relative_to(ROOT)),
            "fidelity_report": dict(handoff.fidelity_report),
        }
        verdict = qualify_stage_s_entry(
            handoff.manifest_json,
            mesh_path=handoff.surface_stl,
            problem_spec_yaml=PROBLEM_SPEC,
            volume_constraint={
                "projected_volume": projected_volume,
                "limit": V_MAX,
                "absolute_tolerance": VOLUME_TOLERANCE,
            },
        )
        verdict_record = verdict.to_dict()
    except Exception as exc:  # fail-closed: a handoff failure is the verdict
        verdict_record = {
            "ready_for_stage_s": False,
            "profile_id": "stage_s_entry_v1",
            "reasons": [f"handoff_failure:{type(exc).__name__}:{exc}"],
            "sub_verdicts": {},
        }

    evidence = {
        "kind": "pq4_1_terminal_stage_s_entry_v2",
        "correction": {
            "supersedes": {
                "path": "docs/evidence/pq4_1_terminal_stage_s_entry_2026_09.json",
                "sha256": "206434c51bcc90b54608f7419c5157078692e3e71e3a8d5c0bcf22618c17ed84",
                "note": "kept unmodified; its extraction-profile verdict used a buggy barycentric formula",
            },
            "detector_fix": (
                "extraction_qualification._edges_pierce_triangles computed the second "
                "barycentric coordinate as (d00*d20 - d01*d21)/denom instead of "
                "(d00*d21 - d01*d20)/denom, producing false self-intersection hits on "
                "near-parallel non-crossing triangle pairs; verified against an exact "
                "Moeller-Trumbore reference (property test)"
            ),
        },
        "schema_version": 1,
        "input": {
            "v9_outcome": {"path": str(V9_OUTCOME.relative_to(ROOT)), "sha256": ca.sha256_file(V9_OUTCOME)},
            "terminal_rho_sha256": rho_sha,
            "terminal_rho_file_sha256": state["rho_file_sha256"],
            "canonical_grid": {"path": str(CANONICAL.relative_to(ROOT)), "sha256": ca.sha256_file(CANONICAL)},
            "problem_spec": {"path": str(PROBLEM_SPEC.relative_to(ROOT)), "sha256": ca.sha256_file(PROBLEM_SPEC)},
        },
        "fields": {
            "bundle": bundle_paths,
            "beta_equals_ramp_of_projection_max_abs_difference": beta_identity,
            "rho_projection_sha256": _array_sha256(fields["rho_projection"]),
            "beta_solver_sha256": _array_sha256(fields["beta_solver"]),
            "beta_solver_retained_as": "solver audit field",
        },
        "geometry_basis": "rho_projection",
        "iso_value": ISO_VALUE,
        "projected_volume": projected_volume,
        "volume_constraint": {
            "limit": V_MAX,
            "absolute_tolerance": VOLUME_TOLERANCE,
            "within_limit": bool(projected_volume <= V_MAX + VOLUME_TOLERANCE),
        },
        "handoff": handoff_record,
        "stage_s_entry_verdict": verdict_record,
        "claims_supported": [
            "the v9 terminal candidate was extracted from rho_projection and judged by the complete composite Stage S entry gate",
        ],
        "claims_not_supported": [
            "a passing gate would qualify the Stage T numerical candidate only; it is not a grid-independent or target-physics claim",
        ],
    }
    EVIDENCE.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "ready_for_stage_s": verdict_record["ready_for_stage_s"],
                "reasons": verdict_record.get("reasons", [])[:6],
                "projected_volume": projected_volume,
            }
        )
    )


if __name__ == "__main__":
    main()
