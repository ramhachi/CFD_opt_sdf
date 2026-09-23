"""PQ3.3b v7 entry preflight: one volume-cap-corrected step at the v6 checkpoint.

Verifies the v7 registration (which pins the v6 final checkpoint, the v6
outcome and the current source tree), then runs exactly one inequality step
with ``volume_cap_correction`` at the v6 final rho. The artifact is
append-only; the long campaign is refused until this passes.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from cfd_sdf import campaign_assertions as ca  # noqa: E402
from cfd_sdf.fixed_grid_primal import load_fixed_grid_density_state  # noqa: E402
from cfd_sdf.path_b_bracket import BracketSpec  # noqa: E402
from cfd_sdf.phase2_inequality_policy import evaluate_phase2_inequality  # noqa: E402
from cfd_sdf.problem_spec import load_problem_spec  # noqa: E402
from cfd_sdf.problem_spec_compiler import VolumeBudget, compile_problem  # noqa: E402
from scripts.pq3_3b_campaign_v6_2026_09 import _oracle, _transform  # noqa: E402
from scripts.pq3_3b_preflight_v6_2026_09 import run_evidence, sha256_array  # noqa: E402

MANIFEST = ROOT / "docs/evidence/pq3_3b_campaign_manifest_v7_2026_09.json"
OUTPUT = ROOT / "work/pq3_3b_v7_entry_preflight"
ARTIFACT = ROOT / "docs/evidence/pq3_3b_v7_entry_preflight_2026_09.json"
V6_OUTCOME = ROOT / "docs/evidence/pq3_3b_campaign_v6_outcome_2026_09.json"


def verify() -> tuple[dict, np.ndarray]:
    sidecar = MANIFEST.with_suffix(".json.sha256").read_text(encoding="utf-8").strip()
    if ca.sha256_file(MANIFEST) != sidecar:
        raise SystemExit("v7 manifest sidecar mismatch")
    manifest = ca.load_json(MANIFEST)
    if manifest["status"] != "registered_preflight_pending":
        raise SystemExit("v7 manifest is not awaiting its entry preflight")
    if ca.sha256_file(__file__) != manifest["entry_preflight"]["script_sha256"]:
        raise SystemExit("v7 entry preflight script hash mismatch")
    for key, ref in manifest.get("pinned_evidence", {}).items():
        path = ROOT / ref["path"]
        if ca.sha256_file(path) != ref["sha256"]:
            raise SystemExit(f"pinned evidence mismatch: {key}")
    if ca.python_source_tree_sha256(ROOT / "src/cfd_sdf") != manifest["source_tree_python_sha256"]:
        raise SystemExit("source tree differs from the v7 registration")
    rho_ref = manifest["input_stop_state"]
    rho_path = ROOT / rho_ref["rho_path"]
    if ca.sha256_file(rho_path) != rho_ref["rho_file_sha256"]:
        raise SystemExit("resume rho file hash mismatch")
    rho = np.load(rho_path, allow_pickle=False)
    if sha256_array(rho) != rho_ref["rho_sha256"]:
        raise SystemExit("resume rho array hash mismatch")
    if OUTPUT.exists() or ARTIFACT.exists():
        raise SystemExit("v7 entry preflight artifacts already exist")
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
    level = next(level for level in manifest["levels"] if level["name"] == manifest["input_stop_state"]["level"])
    transform = _transform(manifest, active, level)
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
    candidate = payload["candidates"][-1] if payload["candidates"] else None
    passed = bool(
        payload.get("successful")
        and candidate is not None
        and candidate["accepted"]
        and candidate["gates"].get("projected_volume_within_v_max") is True
        and bool(candidate["volume_cap_correction_applied"])
        and not payload.get("all_failed", True)
    )
    artifact = {
        "kind": "pq3_3b_v7_entry_preflight",
        "schema_version": 1,
        "manifest": {"path": str(MANIFEST.relative_to(ROOT)), "sha256": ca.sha256_file(MANIFEST)},
        "input_stop_state": manifest["input_stop_state"],
        "stage": {
            "level": level["name"],
            "parent_run": parent_run,
            "phase2": payload,
            "accepted_rho_sha256": payload["corrected_rho_sha256"] if accepted is not None else None,
            "pass": passed,
        },
        "summary": {
            "entry_preflight_pass": passed,
            "volume_cap_correction_applied": None if candidate is None else candidate["volume_cap_correction_applied"],
            "volume_cap_kappa": None if candidate is None else candidate["volume_cap_kappa"],
            "long_campaign_started": False,
        },
        "claims_supported": [
            "one cap-corrected inequality step was qualified at the v6 final checkpoint with fresh real primals",
        ],
        "claims_not_supported": [
            "the long v7 campaign is not started and no convergence conclusion is included",
        ],
    }
    if ARTIFACT.exists():
        raise SystemExit("v7 preflight artifact already exists")
    ARTIFACT.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(artifact["summary"], indent=2))
    return artifact


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="PQ3.3b v7 entry preflight")
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
