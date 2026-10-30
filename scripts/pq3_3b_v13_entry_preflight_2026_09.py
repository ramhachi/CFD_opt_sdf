"""One-step v13 preflight for the discreteness-projected raw gradient.

The v12 parent/adjoint is reused exactly.  Rejected alpha values use only the
deterministic transform.  The first transform-feasible candidate alone may
consume a centered Path B pair and one fresh trial primal.  No campaign is
started by this script.
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
from cfd_sdf.path_b_bracket import BracketSpec, evaluate_path_b_bracket  # noqa: E402
from cfd_sdf.phase2_discreteness_direction import (  # noqa: E402
    backtrack_transform_candidates,
    projected_raw_gradient_direction,
)
from cfd_sdf.problem_spec import load_problem_spec  # noqa: E402
from cfd_sdf.problem_spec_compiler import VolumeBudget, compile_problem  # noqa: E402
from scripts.pq3_3b_campaign_v6_2026_09 import _oracle, _path, _transform  # noqa: E402
from scripts.pq3_3b_preflight_v6_2026_09 import run_evidence, sha256_array  # noqa: E402
from scripts.pq3_3b_v13_direction_audit_2026_09 import (  # noqa: E402
    V12_MANIFEST,
    V12_RHO,
    _active_mask,
    _cached_parent,
)

MANIFEST = ROOT / "docs/evidence/pq3_3b_v13_discriminant_manifest_2026_09.json"
AUDIT = ROOT / "docs/evidence/pq3_3b_v13_direction_audit_2026_09.json"
OUTPUT = ROOT / "work/pq3_3b_v13_entry_preflight"
ARTIFACT = ROOT / "docs/evidence/pq3_3b_v13_entry_preflight_2026_09.json"


def verify() -> tuple[dict, dict, np.ndarray]:
    sidecar = MANIFEST.with_suffix(".json.sha256").read_text(encoding="utf-8").strip()
    if ca.sha256_file(MANIFEST) != sidecar:
        raise SystemExit("v13 discriminant manifest sidecar mismatch")
    manifest = ca.load_json(MANIFEST)
    if manifest.get("kind") != "pq3_3b_v13_discriminant_manifest":
        raise SystemExit("v13 discriminant manifest kind mismatch")
    if manifest.get("status") != "registered_preflight_pending":
        raise SystemExit("v13 discriminant is not awaiting preflight")
    if ca.sha256_file(__file__) != manifest["entry_preflight"]["script_sha256"]:
        raise SystemExit("v13 entry preflight script hash mismatch")
    if ca.sha256_file(AUDIT) != manifest["direction_audit"]["sha256"]:
        raise SystemExit("v13 direction audit hash mismatch")
    if ca.python_source_tree_sha256(ROOT / "src/cfd_sdf") != manifest["source_tree_python_sha256"]:
        raise SystemExit("source tree differs from v13 registration")
    for key, ref in manifest["pinned_inputs"].items():
        path = ROOT / ref["path"]
        if ca.sha256_file(path) != ref["sha256"]:
            raise SystemExit(f"v13 pinned input mismatch: {key}")
    for key, ref in manifest["registered_inputs"].items():
        path = ROOT / ref["path"]
        actual = ca.tree_sha256(path) if path.is_dir() else ca.sha256_file(path)
        if actual != ref["sha256"]:
            raise SystemExit(f"v13 registered input mismatch: {key}")
    for key in ("state", "density_vti"):
        path = ROOT / manifest["margin_mask"][key]
        if ca.sha256_file(path) != manifest["margin_mask"][f"{key}_sha256"]:
            raise SystemExit(f"v13 margin-mask input mismatch: {key}")
    rho = np.load(V12_RHO, allow_pickle=False)
    if sha256_array(rho) != manifest["input_stop_state"]["rho_sha256"]:
        raise SystemExit("v13 input rho array hash mismatch")
    audit = ca.load_json(AUDIT)
    if audit["summary"].get("solver_invocations") != 0:
        raise SystemExit("v13 direction audit was not solver-free")
    if audit.get("source_tree_python_sha256") != manifest["source_tree_python_sha256"]:
        raise SystemExit("v13 direction audit source tree mismatch")
    if audit["summary"].get("transform_feasible_candidate_found") is not True:
        raise SystemExit("v13 direction audit found no transform-feasible candidate")
    if OUTPUT.exists() or ARTIFACT.exists():
        raise SystemExit("v13 preflight output already exists")
    return manifest, audit, np.asarray(rho, dtype=np.float64)


def run() -> dict:
    manifest, audit, rho = verify()
    v12_manifest = ca.load_json(V12_MANIFEST)
    OUTPUT.mkdir(parents=True)
    shutil.copytree(
        _path(manifest["registered_inputs"]["template_trial"]),
        OUTPUT / "template_trial",
    )
    active = _active_mask(v12_manifest)
    level = manifest["level"]
    transform = _transform(v12_manifest, active, level)
    parent = _cached_parent(v12_manifest, transform, rho)
    parent_run = run_evidence(parent)
    direction = projected_raw_gradient_direction(
        transform=transform,
        rho=rho,
        objective_gradient=np.asarray(parent.objective_gradient, dtype=np.float64),
    )
    if direction.diagnostics["direction_sha256"] != audit["direction"]["direction_sha256"]:
        raise RuntimeError("v13 direction does not reproduce the registered audit")

    ledger, selected = backtrack_transform_candidates(
        transform=transform,
        rho=rho,
        direction=direction.values,
        ladder=tuple(manifest["alpha_ladder"]),
        move_limit=float(level["move_limit"]),
        discreteness_mean_nd_max=float(manifest["gates"]["discreteness_mean_nd_max"]),
        v_max=float(manifest["gates"]["v_max_projected"]),
        freeze_box_faces=bool(manifest["direction_policy"]["freeze_exact_box_faces"]),
        min_update_inf_norm=float(manifest["gates"]["min_corrected_update_inf_norm"]),
        extractability_fraction=float(manifest["gates"]["extractability_fraction"]),
    )
    if selected is None:
        return _finalize(manifest, audit, direction, ledger, parent_run, None)
    if float(selected.alpha) != float(audit["selected"]["alpha"]):
        raise RuntimeError("v13 selected alpha does not reproduce the registered audit")
    if sha256_array(selected.rho) != audit["selected"]["rho_sha256"]:
        raise RuntimeError("v13 selected rho does not reproduce the registered audit")

    spec = load_problem_spec(_path(manifest["registered_inputs"]["problem_spec"]))
    compiled = compile_problem(
        spec,
        volume_budget=VolumeBudget(
            "volume_fraction_max", manifest["gates"]["v_max_projected"]
        ),
    )
    trial_oracle = _oracle(manifest, transform, compiled, OUTPUT, OUTPUT / "runs")
    calls = {"path_b_primal": 0, "candidate_primal": 0}

    def bracket_values(candidate):
        calls["path_b_primal"] += 1
        return trial_oracle.evaluate_values(candidate)

    bracket = evaluate_path_b_bracket(
        spec=BracketSpec(
            epsilon=manifest["path_b"]["epsilon"],
            noise_floor_abs=manifest["path_b"]["noise_floor_abs"],
        ),
        parent_rho=rho,
        parent_gradient=np.asarray(parent.objective_gradient, dtype=np.float64),
        proposal_delta=selected.rho - rho,
        active=active,
        evaluate_values=bracket_values,
    )
    trial_result = None
    trial_run = None
    if bracket.ok:
        calls["candidate_primal"] += 1
        trial_result = trial_oracle.evaluate_values(selected.rho)
        trial_run = run_evidence(trial_result)

    parent_downforce = float(parent_run["downforce_coefficient"])
    trial_downforce = (
        None if trial_run is None else float(trial_run["downforce_coefficient"])
    )
    response_gates = {
        "path_b_pass": bool(bracket.ok),
        "trial_primal_converged": bool(
            trial_result is not None and trial_result.primal_converged
        ),
        "canonical_objective_improved": bool(
            trial_result is not None
            and trial_result.objective
            < parent.objective - float(manifest["noise_thresholds"]["objective"])
        ),
        "raw_downforce_improved": bool(
            trial_downforce is not None
            and trial_downforce
            > parent_downforce + float(manifest["noise_thresholds"]["downforce"])
        ),
    }
    stage = {
        "transform_candidates": [candidate.to_jsonable() for candidate in ledger],
        "selected_alpha": float(selected.alpha),
        "selected_rho_sha256": sha256_array(selected.rho),
        "path_b": bracket.to_dict(),
        "parent_run": parent_run,
        "trial_run": trial_run,
        "trial_objective": None if trial_result is None else float(trial_result.objective),
        "trial_downforce": trial_downforce,
        "response_gates": response_gates,
        "pass": bool(selected.feasible and all(response_gates.values())),
        "solver_call_counts": {
            "cached_parent_reused": 1,
            "fresh_parent_or_adjoint": 0,
            **calls,
        },
    }
    return _finalize(manifest, audit, direction, ledger, parent_run, stage)


def _finalize(manifest, audit, direction, ledger, parent_run, stage):
    passed = bool(stage is not None and stage["pass"])
    artifact = {
        "kind": "pq3_3b_v13_entry_preflight",
        "schema_version": 1,
        "manifest": {
            "path": str(MANIFEST.relative_to(ROOT)),
            "sha256": ca.sha256_file(MANIFEST),
        },
        "direction_audit": {
            "path": str(AUDIT.relative_to(ROOT)),
            "sha256": ca.sha256_file(AUDIT),
        },
        "input_stop_state": manifest["input_stop_state"],
        "direction": direction.diagnostics,
        "parent_run": parent_run,
        "transform_candidates": [candidate.to_jsonable() for candidate in ledger],
        "stage": stage,
        "summary": {
            "entry_preflight_pass": passed,
            "cached_parent_reused": True,
            "long_campaign_registered": False,
            "long_campaign_started": False,
        },
        "claims_supported": [
            "the v12 parent and adjoint were reused for the exact checkpoint-1 design",
            "only the first transform-feasible direction may consume Path B and one candidate primal",
        ],
        "claims_not_supported": [
            "one preflight step does not establish convergence or Stage S readiness",
            "the v13 discriminant does not register or start a long campaign",
            "the result is not grid-independent or target-physics evidence",
        ],
    }
    ARTIFACT.write_text(
        json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(artifact["summary"], indent=2))
    return artifact


def main() -> None:
    parser = argparse.ArgumentParser(description="PQ3.3b v13 bounded entry preflight")
    parser.add_argument("--verify-preconditions", action="store_true")
    parser.add_argument("--run", action="store_true")
    args = parser.parse_args()
    if args.verify_preconditions:
        verify()
        print(json.dumps({"status": "preconditions_ok", "output": str(OUTPUT)}))
    elif args.run:
        run()
    else:
        parser.error("specify --verify-preconditions or --run")


if __name__ == "__main__":
    main()
