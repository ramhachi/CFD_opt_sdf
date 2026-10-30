"""PQ3.3a: re-materialize the PQ3.3 candidate with the correct geometry field.

The previous materialization contoured ``beta_solver`` (OpenFOAM beta, the RAMP
output) while the adopted state chain defines the geometry occupancy as
``rho_projection`` (the tanh projection output). With q=100 the two fields
differ by orders of magnitude at a given iso value, so the recorded
0.4/0.5/0.6 sweep was not the intended geometry sweep.

Steps:
1. freeze the hashes of the original evidence, manifest and candidate inputs;
2. derive the four named fields from the saved ``rho_design`` plus the
   registered transform, verifying ``beta == RAMP(projection)``;
3. write the bundle VTIs, then re-run the registered 0.4/0.5/0.6 sweep on
   ``rho_projection`` with the composite Stage S entry gate;
4. write a correction artifact referencing the original evidence SHA-256
   (append-only; the original file is never rewritten).
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cfd_sdf.design_transform import (  # noqa: E402
    ConeFilter,
    DesignTransform,
    RampInterpolation,
    TanhProjection,
)
from cfd_sdf.extraction_sweep import run_extraction_threshold_sweep  # noqa: E402
from cfd_sdf.fixed_grid_contract import (  # noqa: E402
    CartesianCellGrid,
    _read_cell_vti,
    _write_cell_vti,
)
from cfd_sdf.fixed_grid_primal import load_fixed_grid_density_state  # noqa: E402

ORIGINAL_EVIDENCE = ROOT / "docs/evidence/pq3_3_volume_target_2026_09.json"
MANIFEST_V3 = ROOT / "docs/evidence/pq3_3_volume_target_manifest_2026_09.json"
BASE = ROOT / "work/p0_closed_loop"
OUT = ROOT / "work/pq3_3a_rematerialize"
EVIDENCE = ROOT / "docs/evidence/pq3_3a_semantic_rematerialize_2026_09.json"
RAMP_Q = 100.0
PROJECTION_B = 16.0
FILTER_RADIUS_M = 0.15
BETA_MAX = 2500.0
SHAPE = (60, 32, 24)
THRESHOLDS = (0.4, 0.5, 0.6)
VOLUME_LIMIT = 0.07632566813424899
VOLUME_TOLERANCE = 1e-4


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    if OUT.exists() or EVIDENCE.exists():
        raise SystemExit("PQ3.3a artifacts already exist; the correction is append-only")

    original = json.loads(ORIGINAL_EVIDENCE.read_text(encoding="utf-8"))
    final_design_rho = np.asarray(original["final_design_rho"], dtype=np.float64)

    frozen_hashes = {
        "original_evidence": _sha256_file(ORIGINAL_EVIDENCE),
        "manifest": _sha256_file(MANIFEST_V3),
        "canonical_density": _sha256_file(BASE / "density.vti"),
        "canonical_topology_state": _sha256_file(BASE / "topology_state.json"),
    }

    reference_grid, reference_arrays = _read_cell_vti(
        BASE / "density.vti", expected_kind="fixed_grid_density"
    )
    active = (
        (np.asarray(reference_arrays["active_design_mask"]) > 0)
        & (np.asarray(reference_arrays["allowed_mask"]) > 0)
        & ~(np.asarray(reference_arrays["forbidden_mask"]) > 0)
        & ~(np.asarray(reference_arrays["fixed_solid_mask"]) > 0)
    )
    transform = DesignTransform(
        shape=SHAPE,
        spacing_m=0.05,
        active_mask=active,
        filter=ConeFilter(
            shape=SHAPE, spacing_m=0.05, active_mask=active, radius_m=FILTER_RADIUS_M
        ),
        projection=TanhProjection(PROJECTION_B, 0.5),
        ramp=RampInterpolation(RAMP_Q),
    )
    derived = transform.forward(final_design_rho)
    fields = {
        "rho_design": np.asarray(final_design_rho, dtype=np.float32),
        "rho_filtered": np.asarray(derived.rho_filtered, dtype=np.float32),
        "rho_projection": np.asarray(derived.rho_projected, dtype=np.float32),
        "beta_solver": np.asarray(derived.beta, dtype=np.float32),
    }

    ramp_of_projection = RampInterpolation(RAMP_Q).forward(
        fields["rho_projection"].astype(np.float64)
    )
    beta_difference = float(
        np.max(np.abs(ramp_of_projection - fields["beta_solver"].astype(np.float64)))
    )
    contract_checks = {
        "beta_equals_ramp_of_projection_max_abs_difference": beta_difference,
        "beta_solver_sha256": hashlib.sha256(
            np.ascontiguousarray(fields["beta_solver"]).tobytes()
        ).hexdigest(),
        "rho_projection_sha256": hashlib.sha256(
            np.ascontiguousarray(fields["rho_projection"]).tobytes()
        ).hexdigest(),
        "note": (
            "alpha = beta_max * beta_solver is enforced by the solver-injection "
            "contract, not re-derived here; the recorded identity check for the "
            "alpha array uses the contract's own alpha against the contract's "
            "rho_projected (beta), which is consistent by construction"
        ),
    }

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

    sweep_source = OUT / "candidate"
    sweep_source.mkdir(parents=True, exist_ok=True)
    arrays = {
        "rho": fields["rho_design"],
        "rho_filtered": fields["rho_filtered"],
        "rho_projection": fields["rho_projection"],  # geometry occupancy basis
        "alpha": (BETA_MAX * fields["beta_solver"].astype(np.float64)).astype(np.float32),
        "allowed_mask": reference_arrays["allowed_mask"],
        "forbidden_mask": reference_arrays["forbidden_mask"],
        "fixed_solid_mask": reference_arrays["fixed_solid_mask"],
        "root_mask": reference_arrays["root_mask"],
        "active_design_mask": reference_arrays["active_design_mask"],
    }
    _write_cell_vti(grid, arrays, sweep_source / "density.vti", kind="fixed_grid_density")
    topology_state = {
        "schema_version": 1,
        "kind": "fixed_grid_topology_state",
        "design_variable": "rho",
        "grid": grid.to_dict(),
        "density_vti": "density.vti",
        "density_array": "rho_projection",
        "source_solver": {"backend": "pq3_3a_rematerialize"},
    }
    (sweep_source / "topology_state.json").write_text(
        json.dumps(topology_state, indent=2), encoding="utf-8"
    )
    active_mask = np.asarray(reference_arrays["active_design_mask"], dtype=bool)
    sweep = run_extraction_threshold_sweep(
        sweep_source / "topology_state.json",
        thresholds=list(THRESHOLDS),
        output_dir=OUT / "projection_sweep",
        selection_rule={
            "kind": "registered_range_first_that_passes",
            "range": [0.4, 0.6],
            "require_ready_for_stage_s": True,
        },
        stage_s_entry={
            "problem_spec_yaml": ROOT / "work/pq4_candidate/project.yaml",
            "volume_constraint": {
                "projected_volume": float(
                    fields["rho_projection"].astype(np.float64)[active_mask].mean()
                ),
                "limit": VOLUME_LIMIT,
                "absolute_tolerance": VOLUME_TOLERANCE,
            },
        },
    )
    for row in sweep["rows"]:
        entry = row.get("stage_s_entry") or {}
        print(
            json.dumps(
                {
                    "threshold": row["threshold"],
                    "status": row["status"],
                    "extraction_profile_pass": row.get("extraction_profile_pass"),
                    "global_ready": row["ready_for_stage_s"],
                    "reasons": entry.get("reasons", [])[:3],
                }
            ),
            flush=True,
        )
    evidence = {
        "artifact_id": "pq3_3a_semantic_rematerialize_2026_09",
        "evidence_class": "field_semantic_rejudgment",
        "issue": "PQ3.3a (bridge plan Work A)",
        "original_evidence": {
            "path": str(ORIGINAL_EVIDENCE.relative_to(ROOT)),
            "sha256": frozen_hashes["original_evidence"],
            "not_rewritten": True,
            "known_defects": [
                "artifact_id and issue said PQ3.2 while manifest paths said PQ3.3",
                "final_design_rho embedded in JSON (~46k lines)",
                "the recorded 0.4/0.5/0.6 sweep contoured beta_solver, not rho_projection",
            ],
        },
        "frozen_hashes": frozen_hashes,
        "bundle": bundle_paths,
        "contract_checks": contract_checks,
        "projection_sweep": sweep,
        "claims_supported": [
            "the four named fields are re-derived from the saved rho_design with one transform",
            "the registered 0.4/0.5/0.6 sweep is re-run on the geometry occupancy basis",
        ],
        "claims_not_supported": [
            "no Stage S readiness is claimed: b=16 recorded no accepted step, so even a "
            "passing extraction cannot promote this to a terminal candidate",
        ],
    }
    EVIDENCE.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print("wrote", EVIDENCE)


if __name__ == "__main__":
    main()
