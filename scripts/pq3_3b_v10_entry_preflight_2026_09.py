"""PQ3.3b v10 entry preflight: margin mask + b=128 step at the trimmed rho.

Verifies the v10 registration and qualifies one cap-corrected b=128 inequality
step at the trimmed terminal rho, with transform-only checks of the margin
mask extent and the registered discreteness bound at the start state.
Append-only artifact; the campaign is refused until it passes.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from cfd_sdf import campaign_assertions as ca  # noqa: E402
from cfd_sdf.fixed_grid_contract import _read_cell_vti  # noqa: E402
from cfd_sdf.fixed_grid_primal import load_fixed_grid_density_state  # noqa: E402
from cfd_sdf.path_b_bracket import BracketSpec  # noqa: E402
from cfd_sdf.phase2_inequality_policy import evaluate_phase2_inequality  # noqa: E402
from cfd_sdf.problem_spec import load_problem_spec  # noqa: E402
from cfd_sdf.problem_spec_compiler import VolumeBudget, compile_problem  # noqa: E402
from scripts.pq3_3b_campaign_v6_2026_09 import _oracle, _transform  # noqa: E402
from scripts.pq3_3b_preflight_v6_2026_09 import run_evidence, sha256_array  # noqa: E402

MANIFEST = ROOT / "docs/evidence/pq3_3b_campaign_manifest_v10_2026_09.json"
OUTPUT = ROOT / "work/pq3_3b_v10_entry_preflight"
ARTIFACT = ROOT / "docs/evidence/pq3_3b_v10_entry_preflight_2026_09.json"
SHAPE = (60, 32, 24)


def verify() -> tuple[dict, np.ndarray]:
    sidecar = MANIFEST.with_suffix(".json.sha256").read_text(encoding="utf-8").strip()
    if ca.sha256_file(MANIFEST) != sidecar:
        raise SystemExit("v10 manifest sidecar mismatch")
    manifest = ca.load_json(MANIFEST)
    if manifest["status"] != "registered_preflight_pending":
        raise SystemExit("v10 manifest is not awaiting its entry preflight")
    if ca.sha256_file(__file__) != manifest["entry_preflight"]["script_sha256"]:
        raise SystemExit("v10 entry preflight script hash mismatch")
    for key, ref in manifest.get("pinned_evidence", {}).items():
        if ca.sha256_file(ROOT / ref["path"]) != ref["sha256"]:
            raise SystemExit(f"pinned evidence mismatch: {key}")
    if ca.sha256_file(ROOT / manifest["margin_mask"]["state"]) != manifest["margin_mask"]["state_sha256"]:
        raise SystemExit("margin mask state hash mismatch")
    if ca.sha256_file(ROOT / manifest["margin_mask"]["density_vti"]) != manifest["margin_mask"]["density_vti_sha256"]:
        raise SystemExit("margin mask density hash mismatch")
    if ca.python_source_tree_sha256(ROOT / "src/cfd_sdf") != manifest["source_tree_python_sha256"]:
        raise SystemExit("source tree differs from the v10 registration")
    rho_ref = manifest["input_stop_state"]
    rho_path = ROOT / rho_ref["rho_path"]
    if ca.sha256_file(rho_path) != rho_ref["rho_file_sha256"]:
        raise SystemExit("bootstrap rho file hash mismatch")
    rho = np.load(rho_path, allow_pickle=False)
    if sha256_array(rho) != rho_ref["rho_sha256"]:
        raise SystemExit("bootstrap rho array hash mismatch")
    if OUTPUT.exists() or ARTIFACT.exists():
        raise SystemExit("v10 entry preflight artifacts already exist")
    return manifest, np.asarray(rho, dtype=np.float64)


def run() -> dict:
    manifest, rho = verify()
    OUTPUT.mkdir(parents=True)
    shutil.copytree(ROOT / manifest["registered_inputs"]["template_trial"]["path"], OUTPUT / "template_trial")
    grid = load_fixed_grid_density_state(ROOT / manifest["registered_inputs"]["canonical_grid"]["path"])
    arrays = grid.arrays
    active = (
        (np.asarray(arrays["active_design_mask"]) > 0)
        & (np.asarray(arrays["allowed_mask"]) > 0)
        & ~(np.asarray(arrays["forbidden_mask"]) > 0)
        & ~(np.asarray(arrays["fixed_solid_mask"]) > 0)
    )
    spec = load_problem_spec(ROOT / manifest["registered_inputs"]["problem_spec"]["path"])
    compiled = compile_problem(spec, volume_budget=VolumeBudget("volume_fraction_max", manifest["v_max_projected"]))
    level = manifest["levels"][0]
    transform = _transform(manifest, active, level)
    projected = np.asarray(transform.forward(rho).rho_projected, dtype=np.float64)
    values = projected[active]
    mean_nd = float(np.mean(4.0 * values * (1.0 - values)))
    _, grid_arrays = _read_cell_vti(
        ROOT / manifest["margin_mask"]["density_vti"], expected_kind="fixed_grid_density"
    )
    from cfd_sdf.fixed_grid_contract import CartesianCellGrid

    grid_meta = json.loads((ROOT / manifest["registered_inputs"]["canonical_grid"]["path"]).read_text())["grid"]
    y_origin = float(grid_meta["origin"][1])
    y_spacing = float(grid_meta["spacing"][1])
    y_shape = int(grid_meta["cell_shape"][1])
    y_centres = y_origin + y_spacing * (np.arange(y_shape) + 0.5)
    del grid_arrays, CartesianCellGrid
    y_mask = np.broadcast_to(np.abs(y_centres).reshape(1, -1, 1) <= 0.475, SHAPE)
    active_3d = active.reshape(SHAPE, order="F")
    mask_violations = int(np.count_nonzero(active_3d & ~y_mask))
    transform_checks = {
        "active_cells": int(active.sum()),
        "mean_nd_start": mean_nd,
        "mean_nd_bound": 0.01,
        "mean_nd_within_bound": bool(mean_nd <= 0.01),
        "projected_volume_start": float(values.mean()),
        "margin_mask_violations": mask_violations,
        "margin_mask_ok": bool(mask_violations == 0),
    }
    if not transform_checks["mean_nd_within_bound"] or not transform_checks["margin_mask_ok"]:
        return _finalize(manifest, transform_checks, None, False)

    oracle = _oracle(manifest, transform, compiled, OUTPUT, OUTPUT / "runs")
    parent = oracle.evaluate_parent(rho)
    parent_run = run_evidence(parent)

    def trial(candidate):
        result = oracle.evaluate_values(candidate)
        return result, run_evidence(result)

    payload, accepted = evaluate_phase2_inequality(
        transform=transform,
        parent_result=parent,
        rho_parent=rho,
        parent_downforce=float(parent_run["downforce_coefficient"]),
        move_limit=float(level["move_limit"]),
        ladder=tuple(manifest["phase2_policy"]["alpha_ladder"]),
        v_max=manifest["v_max_projected"],
        objective_noise_threshold=manifest["noise_thresholds"]["objective"],
        downforce_noise_threshold=manifest["noise_thresholds"]["downforce"],
        bracket_spec=BracketSpec(epsilon=manifest["path_b"]["epsilon"], noise_floor_abs=manifest["path_b"]["noise_floor_abs"]),
        evaluate_values=oracle.evaluate_values,
        evaluate_trial=trial,
        return_rho=True,
        volume_cap_correction=True,
        min_update_inf_norm=manifest["phase2_policy"]["min_corrected_update_inf_norm"],
        extractability_fraction=manifest["phase2_policy"]["extractability_fraction"],
    )
    stage = {
        "level": level["name"],
        "parent_run": parent_run,
        "phase2": payload,
        "accepted_rho_sha256": payload["corrected_rho_sha256"] if accepted is not None else None,
        "pass": bool(payload["successful"]),
    }
    return _finalize(manifest, transform_checks, stage, bool(stage["pass"]))


def _finalize(manifest: dict, transform_checks: dict, stage: dict | None, stage_pass: bool) -> dict:
    passed = bool(transform_checks["mean_nd_within_bound"] and transform_checks["margin_mask_ok"] and stage_pass and stage is not None)
    artifact = {
        "kind": "pq3_3b_v10_entry_preflight",
        "schema_version": 1,
        "manifest": {"path": str(MANIFEST.relative_to(ROOT)), "sha256": ca.sha256_file(MANIFEST)},
        "transform_checks": transform_checks,
        "stage": stage,
        "summary": {"entry_preflight_pass": passed, "long_campaign_started": False},
        "claims_supported": [
            "the margin mask and the b=128 start state meet the registered discreteness bound",
            "one cap-corrected b=128 step was qualified with fresh real primals",
        ],
        "claims_not_supported": [
            "the long v10 campaign is not started by this artifact",
        ],
    }
    if ARTIFACT.exists():
        raise SystemExit("v10 preflight artifact already exists")
    ARTIFACT.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(artifact["summary"], indent=2))
    return artifact


def main() -> None:
    parser = argparse.ArgumentParser(description="PQ3.3b v10 entry preflight")
    parser.add_argument("--verify-preconditions", action="store_true")
    parser.add_argument("--run", action="store_true")
    args = parser.parse_args()
    if args.verify_preconditions:
        manifest, _rho = verify()
        print(json.dumps({"status": "preconditions_ok", "output": str(OUTPUT)}))
    elif args.run:
        run()
    else:
        parser.error("specify --verify-preconditions or --run")


if __name__ == "__main__":
    main()
