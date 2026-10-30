#!/usr/bin/env python3
"""Write the immutable LOWDIM-01 (#48) pre-registration freeze."""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src")); sys.path.insert(0, str(ROOT / "scripts"))
import analyze_lowdim01 as analyzer  # noqa: E402
import build_lowdim01_kernel as kernel  # noqa: E402
import lowdim01_states as L  # noqa: E402
from cfd_sdf import lowdim01_contract as contract  # noqa: E402

E = ROOT / "docs/evidence/lowdim01_four_direction_capability_2026_10_09"
FILES = {
    "job": "scripts/waterlily_xfid_candidate_c_job.jl",
    "states_module": "scripts/lowdim01_states.py",
    "step01_states_module": "scripts/step01_states.py",
    "runner_template": "scripts/lowdim01_runner_template.py",
    "kernel_builder": "scripts/build_lowdim01_kernel.py",
    "inputs_builder": "scripts/build_lowdim01_inputs.py",
    "exploration_script": "scripts/lowdim01_geometry_exploration.py",
    "analyzer": "scripts/analyze_lowdim01.py",
    "contract": "src/cfd_sdf/lowdim01_contract.py",
    "force_io": "scripts/fd08_v2_campaign_io.py",
    "runner": "infra/kaggle/kernel_lowdim01_a/runner.py",
    "kernel_metadata": "infra/kaggle/kernel_lowdim01_a/kernel-metadata.json",
    "inventory": "docs/evidence/lowdim01_four_direction_capability_2026_10_09/inventory.json",
    "geometry_exploration": "docs/evidence/lowdim01_four_direction_capability_2026_10_09/geometry_exploration_step01_states.json",
    "prerun_note": "docs/evidence/lowdim01_four_direction_capability_2026_10_09/prerun_note.md",
    "identity_free_check": "docs/evidence/lowdim01_four_direction_capability_2026_10_09/identity_free_check.json",
    "proposal_raw": "docs/evidence/lowdim01_four_direction_capability_2026_10_09/inputs/proposal_downforce.dir_f4_fortran.raw",
    "t4_project": "julia/CFDSDFWaterLilyT4/Project.toml",
    "t4_manifest": "julia/CFDSDFWaterLilyT4/Manifest.toml",
    "formal_criteria": "docs/evidence/fd08_v2_formal_2026_10_07_amend3/formal_criteria.json",
    "step01_analysis": "docs/evidence/step01_finite_step_secant_2026_10_09/step01_analysis.json",
    "step01_freeze": "docs/evidence/step01_finite_step_secant_2026_10_09/prerun_freeze.json",
}


def sha(path):
    return hashlib.sha256((ROOT / path).read_bytes()).hexdigest()


def build(source_commit: str, parent: str) -> dict:
    inv = json.loads((E / "inventory.json").read_text())
    hashes = {name: sha(path) for name, path in FILES.items()}
    hashes["inventory_canonical_json"] = hashlib.sha256((json.dumps(inv, sort_keys=True, indent=2) + "\n").encode()).hexdigest()
    hashes["step01_states_module"] = sha("scripts/step01_states.py")
    assert hashes["inventory_canonical_json"] == hashes["inventory"]
    assert inv["coefficient_gradient"]["step01_analysis_sha256"] == hashes["step01_analysis"], "the inventory is bound to a different STEP-01 analysis"
    formal = json.loads((ROOT / FILES["formal_criteria"]).read_text())
    return {
        "kind": "lowdim01_four_direction_capability_prerun_freeze", "parent_integration_commit": parent, "source_commit": source_commit, "file_hashes": hashes,
        "pins": kernel.pins(), "fd08_baseline": {"forces_csv_sha256": inv["fd08_baseline_reference"]["forces_csv_sha256"], "host_recomputed_n": inv["fd08_baseline_reference"]["host_recomputed_n"]},
        "step01_analysis_sha256": hashes["step01_analysis"], "runtime": formal["runtime"],
        "design": {"basis": list(L.BASIS), "objective": "maximise downforce", "coefficient_gradient": "STEP-01 centered +-2.5 mm downforce (hash-bound, proposal only)", "metric": "Euclidean in coefficient space",
                   "candidate_step_mm": list(L.CANDIDATE_STEP_MM), "control_step_mm": list(L.CONTROL_STEP_MM), "controls": "reverse proposal direction; never accepted or selected", "states": len(inv["states"]), "kernel_id": kernel.metadata()["id"], "kernel_timeout_s": kernel.TIMEOUT_S, "reinitialization": "none",
                   "selection": "accepted candidate with the largest actual downforce gain (ties: smaller step)"},
        "rules": {"min_downforce_gain_n": contract.MIN_DOWNFORCE_GAIN_N, "drag_allowance_n": contract.DRAG_ALLOWANCE_N, "nominal_sigma0_n": contract.NOMINAL_SIGMA0_N, "resolved_factor": contract.RESOLVED_FACTOR,
                  "geometry_gate_thresholds": inv["geometry_gate_thresholds"], "summary_rel": analyzer.SUMMARY_REL, "baseline_rel": analyzer.BASELINE_REL, "min_t_end": analyzer.MIN_T_END,
                  "authority": "actual primal responses and hard geometry gates; predictions are reference only"},
        "verdicts": ["LOWDIM_ACCEPT", "LOWDIM_NO_GO", "LOWDIM_INCOMPLETE"],
        "known_before_the_run": {"candidate_hard_gates_pass": {r["name"]: r["geometry_gates"]["all_hard_gates_pass"] for r in inv["states"] if r["kind"] == "candidate"},
                                 "expectation": ("an accepted trial at 1.25 / 2.5 mm is plausible (per-direction quadratic models from STEP-01 give about +5.0e-4 N and +4.2e-4 N; 5.0 / 7.5 mm negative), "
                                                 "but D0+P1 was non-additive in STEP-01 and an ACCEPT would be largely predictable from STEP-01's curvature; LOWDIM_NO_GO is also a valid result"),
                                 "quadratic_model_prediction_n": {"1.25": 4.986e-4, "2.5": 4.240e-4, "5.0": -1.445e-3, "7.5": -5.608e-3}},
        "prohibitions": {"gradient_claim": True, "opt01_claim": True, "flag_change": True, "selected_delta": True, "grad03_verdict": True, "fd08_verdict_change": True, "reinitialization": True,
                         "prediction_in_accept": True, "post_hoc_candidates_thresholds_or_basis": True, "ad_or_tangent": True},
        "declarations": {"selected_delta": None, "grad03_verdict": None, "reverse": "untouched", "not_opt01": True, "capability_statement_for_a_fixed_four_direction_basis_only": True,
                         "supersession_of_opt01_requires_a_separate_phase_plan_entry": True},
        "qualification_flags": {k: False for k in analyzer.FLAGS}, "frozen_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }


def check_git(source_commit: str) -> None:
    if subprocess.run(["git", "-C", str(ROOT), "status", "--porcelain", "--untracked-files=no"], capture_output=True, text=True).stdout.strip():
        sys.exit("tracked files have uncommitted changes: the freeze must hash committed bytes")
    if subprocess.run(["git", "-C", str(ROOT), "merge-base", "--is-ancestor", source_commit, "HEAD"], capture_output=True).returncode != 0:
        sys.exit("the source commit is not an ancestor of HEAD")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source-commit", required=True)
    p.add_argument("--parent", required=True)
    args = p.parse_args()
    check_git(args.source_commit)
    out = E / "prerun_freeze.json"
    if out.exists():
        sys.exit("refusing to overwrite the freeze")
    data = (json.dumps(build(args.source_commit, args.parent), sort_keys=True, indent=2) + "\n").encode()
    out.write_bytes(data)
    out.with_name(out.name + ".sha256").write_text(hashlib.sha256(data).hexdigest() + "\n")
    print(hashlib.sha256(data).hexdigest())


if __name__ == "__main__":
    main()
