"""PQ3.3b v8 entry preflight: cap-stationarity exit and b=16 transition.

Stage A qualifies the pre-registered cap-stationarity exit at the v7 final
checkpoint: an all-machine-scale attempt, the last accepted delta within the
window bound, the cumulative accepted floor, and an independent fresh primal
reproducing the parent response. Stage B qualifies the b=16 transition with
one cap-corrected step. The long campaign is refused until both pass.
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
from cfd_sdf.fixed_grid_primal import load_fixed_grid_density_state  # noqa: E402
from cfd_sdf.path_b_bracket import BracketSpec  # noqa: E402
from cfd_sdf.phase2_inequality_policy import evaluate_phase2_inequality  # noqa: E402
from cfd_sdf.problem_spec import load_problem_spec  # noqa: E402
from cfd_sdf.problem_spec_compiler import VolumeBudget, compile_problem  # noqa: E402
from scripts.pq3_3b_campaign_v6_2026_09 import (  # noqa: E402
    _oracle,
    _transform,
    cap_stationarity_exit_allowed,
)
from scripts.pq3_3b_preflight_v6_2026_09 import run_evidence, run_restoration, sha256_array  # noqa: E402

MANIFEST = ROOT / "docs/evidence/pq3_3b_campaign_manifest_v8_2026_09.json"
OUTPUT = ROOT / "work/pq3_3b_v8_entry_preflight"
ARTIFACT = ROOT / "docs/evidence/pq3_3b_v8_entry_preflight_2026_09.json"
V7_OUTCOME = ROOT / "docs/evidence/pq3_3b_campaign_v7_outcome_2026_09.json"


def verify() -> tuple[dict, np.ndarray]:
    sidecar = MANIFEST.with_suffix(".json.sha256").read_text(encoding="utf-8").strip()
    if ca.sha256_file(MANIFEST) != sidecar:
        raise SystemExit("v8 manifest sidecar mismatch")
    manifest = ca.load_json(MANIFEST)
    if manifest["status"] != "registered_preflight_pending":
        raise SystemExit("v8 manifest is not awaiting its entry preflight")
    if ca.sha256_file(__file__) != manifest["entry_preflight"]["script_sha256"]:
        raise SystemExit("v8 entry preflight script hash mismatch")
    for key, ref in manifest.get("pinned_evidence", {}).items():
        if ca.sha256_file(ROOT / ref["path"]) != ref["sha256"]:
            raise SystemExit(f"pinned evidence mismatch: {key}")
    if ca.python_source_tree_sha256(ROOT / "src/cfd_sdf") != manifest["source_tree_python_sha256"]:
        raise SystemExit("source tree differs from the v8 registration")
    rho_ref = manifest["input_stop_state"]
    rho_path = ROOT / rho_ref["rho_path"]
    if ca.sha256_file(rho_path) != rho_ref["rho_file_sha256"]:
        raise SystemExit("resume rho file hash mismatch")
    rho = np.load(rho_path, allow_pickle=False)
    if sha256_array(rho) != rho_ref["rho_sha256"]:
        raise SystemExit("resume rho array hash mismatch")
    if OUTPUT.exists() or ARTIFACT.exists():
        raise SystemExit("v8 entry preflight artifacts already exist")
    return manifest, np.asarray(rho, dtype=np.float64)


def _masks(manifest: dict) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    grid = load_fixed_grid_density_state(ROOT / manifest["registered_inputs"]["canonical_grid"]["path"])
    arrays = grid.arrays
    active = (
        (np.asarray(arrays["active_design_mask"]) > 0)
        & (np.asarray(arrays["allowed_mask"]) > 0)
        & ~(np.asarray(arrays["forbidden_mask"]) > 0)
        & ~(np.asarray(arrays["fixed_solid_mask"]) > 0)
    )
    return active, np.asarray(arrays["forbidden_mask"]) > 0, np.asarray(arrays["fixed_solid_mask"]) > 0


def run() -> dict:
    manifest, rho = verify()
    OUTPUT.mkdir(parents=True)
    shutil.copytree(ROOT / manifest["registered_inputs"]["template_trial"]["path"], OUTPUT / "template_trial")
    active, forbidden, fixed = _masks(manifest)
    spec = load_problem_spec(ROOT / manifest["registered_inputs"]["problem_spec"]["path"])
    compiled = compile_problem(spec, volume_budget=VolumeBudget("volume_fraction_max", manifest["v_max_projected"]))
    bracket = BracketSpec(epsilon=manifest["path_b"]["epsilon"], noise_floor_abs=manifest["path_b"]["noise_floor_abs"])
    levels = {level["name"]: level for level in manifest["levels"]}
    level = levels[manifest["input_stop_state"]["level"]]

    # ---------------- Stage A: cap-stationarity exit qualification at b=8
    transform = _transform(manifest, active, level)
    oracle = _oracle(manifest, transform, compiled, OUTPUT, OUTPUT / "stage_a/runs")
    parent = oracle.evaluate_parent(rho)
    parent_run = run_evidence(parent)

    def trial(candidate):
        result = oracle.evaluate_values(candidate)
        return result, run_evidence(result)

    payload, _accepted_stage_a = evaluate_phase2_inequality(
        transform=transform,
        parent_result=parent,
        rho_parent=rho,
        parent_downforce=float(parent_run["downforce_coefficient"]),
        move_limit=float(level["move_limit"]),
        ladder=tuple(manifest["phase2_policy"]["alpha_ladder"]),
        v_max=manifest["v_max_projected"],
        objective_noise_threshold=manifest["noise_thresholds"]["objective"],
        downforce_noise_threshold=manifest["noise_thresholds"]["downforce"],
        bracket_spec=bracket,
        evaluate_values=oracle.evaluate_values,
        evaluate_trial=trial,
        return_rho=True,
        volume_cap_correction=True,
        min_update_inf_norm=manifest["phase2_policy"]["min_corrected_update_inf_norm"],
        extractability_fraction=manifest["phase2_policy"]["extractability_fraction"],
    )
    repeat_oracle = _oracle(manifest, transform, compiled, OUTPUT, OUTPUT / "stage_a/repeat_runs")
    repeat = repeat_oracle.evaluate_values(rho)
    repeat_run = run_evidence(repeat)
    tolerance = float(manifest["cap_stationarity_exit"]["reproducibility_tolerance"])
    reproducible = bool(
        repeat.primal_converged
        and abs(float(repeat.objective) - float(parent.objective)) <= tolerance
        and abs(float(repeat_run["downforce_coefficient"]) - float(parent_run["downforce_coefficient"])) <= tolerance
    )
    v7_outcome = ca.load_json(V7_OUTCOME)
    v7_record = list(v7_outcome["level_records"].values())[0]
    last_metric = v7_record["last_metrics"][-1]
    exit_rule = manifest["cap_stationarity_exit"]
    reasons = {candidate["reason"] for candidate in payload["candidates"]}
    exit_allowed = cap_stationarity_exit_allowed(
        enabled=bool(exit_rule["enabled"]),
        reasons=reasons,
        all_rejected_as=set(exit_rule["all_candidates_rejected_as"]),
        last_metric=last_metric,
        last_metric_limit=float(exit_rule["last_accepted_objective_delta_max"]),
        accepted_count=int(manifest["accepted_count_carryover"][level["name"]]),
        min_accepted=int(level["min_accepted_iterations"]),
    )
    stage_a = {
        "level": level["name"],
        "parent_run": parent_run,
        "attempt_reasons": sorted(reasons),
        "attempt_candidates": [
            {"alpha": candidate["alpha"], "reason": candidate["reason"], "inf_norm": candidate["corrected_update_inf_norm"]}
            for candidate in payload["candidates"]
        ],
        "repeat_run": repeat_run,
        "reproducible": reproducible,
        "last_accepted_objective_delta_abs": last_metric["objective_delta_abs"],
        "cumulative_accepted": int(manifest["accepted_count_carryover"][level["name"]]),
        "exit_allowed": exit_allowed,
        "pass": bool(reproducible and exit_allowed),
    }
    if not stage_a["pass"]:
        return _finalize(manifest, stage_a, None, False)

    # ---------------- Stage B: b=16 transition + one cap-corrected step
    level_b = levels["level_2_b16_q100"]
    transform_b = _transform(manifest, active, level_b)
    oracle_b = _oracle(manifest, transform_b, compiled, OUTPUT, OUTPUT / "stage_b/runs")
    from scripts.pq3_3b_preflight_v6_2026_09 import phi_of

    phi_before = phi_of(transform_b, rho, active)
    restored = rho
    restoration = None
    if phi_before < manifest["registered_target"] - manifest["volume_tolerance"]:
        restoration, restored = run_restoration(
            transform_b, oracle_b, active, forbidden, fixed, rho,
            float(level_b["move_limit"]), level_b["name"],
        )
        if not restoration["reached_target"]:
            stage_b = {"level": level_b["name"], "phi_before_restoration": float(phi_before), "restoration": restoration, "pass": False}
            return _finalize(manifest, stage_a, stage_b, False)
    parent_b = oracle_b.evaluate_parent(restored)
    parent_b_run = run_evidence(parent_b)

    def trial_b(candidate):
        result = oracle_b.evaluate_values(candidate)
        return result, run_evidence(result)

    payload_b, accepted_b = evaluate_phase2_inequality(
        transform=transform_b,
        parent_result=parent_b,
        rho_parent=restored,
        parent_downforce=float(parent_b_run["downforce_coefficient"]),
        move_limit=float(level_b["move_limit"]),
        ladder=tuple(manifest["phase2_policy"]["alpha_ladder"]),
        v_max=manifest["v_max_projected"],
        objective_noise_threshold=manifest["noise_thresholds"]["objective"],
        downforce_noise_threshold=manifest["noise_thresholds"]["downforce"],
        bracket_spec=bracket,
        evaluate_values=oracle_b.evaluate_values,
        evaluate_trial=trial_b,
        return_rho=True,
        volume_cap_correction=True,
        min_update_inf_norm=manifest["phase2_policy"]["min_corrected_update_inf_norm"],
        extractability_fraction=manifest["phase2_policy"]["extractability_fraction"],
    )
    stage_b = {
        "level": level_b["name"],
        "phi_before_restoration": float(phi_before),
        "restoration": restoration,
        "parent_run": parent_b_run,
        "phase2": payload_b,
        "accepted_rho_sha256": payload_b["corrected_rho_sha256"] if accepted_b is not None else None,
        "pass": bool(payload_b["successful"]),
    }
    return _finalize(manifest, stage_a, stage_b, bool(stage_b["pass"]))


def _finalize(manifest: dict, stage_a: dict, stage_b: dict | None, stage_b_pass: bool) -> dict:
    passed = bool(stage_a["pass"] and stage_b_pass and stage_b is not None)
    artifact = {
        "kind": "pq3_3b_v8_entry_preflight",
        "schema_version": 1,
        "manifest": {"path": str(MANIFEST.relative_to(ROOT)), "sha256": ca.sha256_file(MANIFEST)},
        "stage_a_cap_stationarity": stage_a,
        "stage_b_b16_transition": stage_b,
        "summary": {
            "stage_a_pass": bool(stage_a["pass"]),
            "stage_b_pass": bool(stage_b_pass),
            "entry_preflight_pass": passed,
            "long_campaign_started": False,
        },
        "claims_supported": [
            "the pre-registered cap-stationarity exit was qualified with an independent repeat at the v7 final checkpoint",
            "the b=16 transition and one cap-corrected step were qualified",
        ],
        "claims_not_supported": [
            "the exit is a registered stopping rule, not a convergence certificate",
            "the long v8 campaign is not started by this artifact",
        ],
    }
    if ARTIFACT.exists():
        raise SystemExit("v8 preflight artifact already exists")
    ARTIFACT.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(artifact["summary"], indent=2))
    return artifact


def main() -> None:
    parser = argparse.ArgumentParser(description="PQ3.3b v8 entry preflight")
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
