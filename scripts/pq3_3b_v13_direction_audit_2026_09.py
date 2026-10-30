"""Solver-free v13 direction audit from the blocked v12 checkpoint.

The exact cached v12 parent adjoint is reconstructed, but no OpenFOAM command
is launched.  The artifact compares the registered alpha ladder only in the
transform space and selects the first candidate satisfying the unchanged
discreteness, projected-volume, occupancy, mask, and move-box gates.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from cfd_sdf import campaign_assertions as ca  # noqa: E402
from cfd_sdf.fixed_grid_primal import load_fixed_grid_density_state  # noqa: E402
from cfd_sdf.phase2_discreteness_direction import (  # noqa: E402
    backtrack_transform_candidates,
    projected_raw_gradient_direction,
)
from cfd_sdf.problem_spec import load_problem_spec  # noqa: E402
from cfd_sdf.problem_spec_compiler import VolumeBudget, compile_problem  # noqa: E402
from scripts.pq3_3b_campaign_v6_2026_09 import _oracle, _path, _transform  # noqa: E402
from scripts.pq3_3b_preflight_v6_2026_09 import run_evidence, sha256_array  # noqa: E402

V12_MANIFEST = ROOT / "docs/evidence/pq3_3b_campaign_manifest_v12_2026_09.json"
V12_STATE = ROOT / "work/pq3_3b_campaign_v12/checkpoints/state_0001.json"
V12_RHO = ROOT / "work/pq3_3b_campaign_v12/checkpoints/rho_0001.npy"
V12_EVENTS = ROOT / "work/pq3_3b_campaign_v12/events.jsonl"
V12_META = ROOT / "work/pq3_3b_campaign_v12/campaign_meta.json"
V12_PARENT = ROOT / "work/pq3_3b_campaign_v12/runs/parent_3603a5b04721/case"
ARTIFACT = ROOT / "docs/evidence/pq3_3b_v13_direction_audit_2026_09.json"


def _ref(path: Path) -> dict:
    return {"path": str(path.relative_to(ROOT)), "sha256": ca.sha256_file(path)}


def _active_mask(manifest: dict) -> np.ndarray:
    grid = load_fixed_grid_density_state(_path(manifest["registered_inputs"]["canonical_grid"]))
    arrays = grid.arrays
    return (
        (np.asarray(arrays["active_design_mask"]) > 0)
        & (np.asarray(arrays["allowed_mask"]) > 0)
        & ~(np.asarray(arrays["forbidden_mask"]) > 0)
        & ~(np.asarray(arrays["fixed_solid_mask"]) > 0)
    )


def _cached_parent(manifest: dict, transform, rho: np.ndarray):
    if not (V12_PARENT / "fixed_grid_primal_summary.json").is_file():
        raise ValueError("cached v12 parent summary is missing")
    spec = load_problem_spec(_path(manifest["registered_inputs"]["problem_spec"]))
    compiled = compile_problem(
        spec,
        volume_budget=VolumeBudget("volume_fraction_max", manifest["v_max_projected"]),
    )
    output = ROOT / manifest["output_directory"]
    oracle = _oracle(manifest, transform, compiled, output, output / "runs")
    parent = oracle.evaluate_parent(rho)
    adapter_artifact = (parent.primal_artifact or {}).get("artifact", {})
    if adapter_artifact.get("reused") is not True:
        raise ValueError("v13 direction audit must reuse the cached v12 parent")
    if Path(adapter_artifact.get("case_dir", "")).resolve() != V12_PARENT.resolve():
        raise ValueError("cached parent case does not match the registered v12 parent")
    return parent


def verify_inputs() -> tuple[dict, dict, np.ndarray]:
    sidecar = V12_MANIFEST.with_suffix(".json.sha256").read_text(encoding="utf-8").strip()
    if ca.sha256_file(V12_MANIFEST) != sidecar:
        raise ValueError("v12 manifest sidecar mismatch")
    manifest = ca.load_json(V12_MANIFEST)
    checkpoint = ca.load_json(V12_STATE)
    rho = np.load(V12_RHO, allow_pickle=False)
    if checkpoint.get("checkpoint_index") != 1 or checkpoint.get("accepted_count") != 6:
        raise ValueError("v12 checkpoint 1 lineage mismatch")
    if checkpoint.get("rho_file_sha256") != ca.sha256_file(V12_RHO):
        raise ValueError("v12 checkpoint rho file hash mismatch")
    if checkpoint.get("rho_sha256") != sha256_array(rho):
        raise ValueError("v12 checkpoint rho array hash mismatch")
    meta = ca.load_json(V12_META)
    if meta.get("status") != "blocked" or meta.get("reason") != "objective_rejected":
        raise ValueError("v12 did not stop at the registered objective rejection")
    if ARTIFACT.exists():
        raise ValueError("v13 direction audit artifact already exists")
    return manifest, checkpoint, np.asarray(rho, dtype=np.float64)


def build() -> dict:
    manifest, checkpoint, rho = verify_inputs()
    active = _active_mask(manifest)
    level = next(
        level
        for level in manifest["levels"]
        if level["name"] == checkpoint.get("level", manifest["input_stop_state"]["level"])
    )
    transform = _transform(manifest, active, level)
    parent = _cached_parent(manifest, transform, rho)
    direction = projected_raw_gradient_direction(
        transform=transform,
        rho=rho,
        objective_gradient=np.asarray(parent.objective_gradient, dtype=np.float64),
    )
    ladder = tuple(float(value) for value in manifest["phase2_policy"]["alpha_ladder"])
    ledger, selected = backtrack_transform_candidates(
        transform=transform,
        rho=rho,
        direction=direction.values,
        ladder=ladder,
        move_limit=float(level["move_limit"]),
        discreteness_mean_nd_max=float(
            manifest["phase2_policy"]["discreteness_mean_nd_max"]
        ),
        v_max=float(manifest["v_max_projected"]),
        freeze_box_faces=bool(manifest["phase2_policy"]["freeze_exact_box_faces"]),
        min_update_inf_norm=float(
            manifest["phase2_policy"]["min_corrected_update_inf_norm"]
        ),
        extractability_fraction=float(
            manifest["phase2_policy"]["extractability_fraction"]
        ),
    )

    derivative_checks = []
    projected = np.asarray(transform.forward(rho).rho_projected, dtype=np.float64)

    def mean_nd(candidate: np.ndarray) -> float:
        field = np.asarray(transform.forward(candidate).rho_projected, dtype=np.float64)
        values = field[active]
        return float(np.mean(4.0 * values * (1.0 - values)))

    for epsilon in (1e-6, 1e-7):
        finite_difference = (
            mean_nd(rho + epsilon * direction.values)
            - mean_nd(rho - epsilon * direction.values)
        ) / (2.0 * epsilon)
        analytic = float(direction.diagnostics["g_discreteness_dot_direction"])
        derivative_checks.append(
            {
                "epsilon": epsilon,
                "analytic": analytic,
                "centered_finite_difference": finite_difference,
                "absolute_difference": abs(finite_difference - analytic),
            }
        )

    entries = []
    for candidate in ledger:
        record = candidate.to_jsonable()
        delta = candidate.rho - rho
        record["adjoint_predicted_objective_delta"] = float(
            np.dot(np.asarray(parent.objective_gradient, dtype=np.float64), delta)
        )
        record["linearized_discreteness_delta"] = float(
            np.dot(direction.discreteness_gradient, delta)
        )
        entries.append(record)

    return {
        "kind": "pq3_3b_v13_solver_free_direction_audit",
        "schema_version": 1,
        "source_tree_python_sha256": ca.python_source_tree_sha256(ROOT / "src/cfd_sdf"),
        "v12_inputs": {
            "manifest": _ref(V12_MANIFEST),
            "checkpoint_state": _ref(V12_STATE),
            "checkpoint_rho": {
                **_ref(V12_RHO),
                "array_sha256": sha256_array(rho),
            },
            "events": _ref(V12_EVENTS),
            "campaign_meta": _ref(V12_META),
            "cached_parent_summary": _ref(V12_PARENT / "fixed_grid_primal_summary.json"),
        },
        "parent": {
            "objective": float(parent.objective),
            "downforce_coefficient": float(run_evidence(parent)["downforce_coefficient"]),
            "rho_sha256": sha256_array(rho),
            "rho_projection_mean_nd": float(
                np.mean(4.0 * projected[active] * (1.0 - projected[active]))
            ),
            "projected_volume": float(np.mean(projected[active])),
            "cached_parent_reused": True,
        },
        "direction": direction.diagnostics,
        "derivative_checks": derivative_checks,
        "alpha_ladder": list(ladder),
        "transform_candidates_through_first_feasible": entries,
        "selected": None
        if selected is None
        else {
            "alpha": float(selected.alpha),
            "rho_sha256": sha256_array(selected.rho),
            "adjoint_predicted_objective_delta": float(
                np.dot(
                    np.asarray(parent.objective_gradient, dtype=np.float64),
                    selected.rho - rho,
                )
            ),
        },
        "summary": {
            "solver_invocations": 0,
            "transform_feasible_candidate_found": selected is not None,
            "long_campaign_started": False,
        },
        "claims_not_supported": [
            "transform feasibility does not establish Path B sign agreement or real-primal improvement",
            "this audit does not establish convergence, Stage S readiness, grid independence, or target physics",
        ],
    }


def main() -> None:
    artifact = build()
    ARTIFACT.write_text(
        json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(artifact["summary"], indent=2))


if __name__ == "__main__":
    main()
