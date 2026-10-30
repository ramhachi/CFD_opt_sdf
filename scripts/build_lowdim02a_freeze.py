#!/usr/bin/env python3
"""Write the immutable LOWDIM-02A (#49) pre-registration freeze."""
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
import analyze_lowdim02a as analyzer  # noqa: E402
import build_lowdim02a_kernel as kernel  # noqa: E402
from cfd_sdf import lowdim02a_contract as contract  # noqa: E402

E = ROOT / "docs/evidence/lowdim02a_flow32_cross_grid_2026_10_09"
FILES = {
    "job": "scripts/waterlily_lowdim02_flow32_job.jl",
    "step01_states_module": "scripts/step01_states.py",
    "runner_template": "scripts/lowdim02a_runner_template.py",
    "kernel_builder": "scripts/build_lowdim02a_kernel.py",
    "inputs_builder": "scripts/build_lowdim02a_inputs.py",
    "analyzer": "scripts/analyze_lowdim02a.py",
    "contract": "src/cfd_sdf/lowdim02a_contract.py",
    "force_io": "scripts/fd08_v2_campaign_io.py",
    "runner": "infra/kaggle/kernel_lowdim02a_a/runner.py",
    "kernel_metadata": "infra/kaggle/kernel_lowdim02a_a/kernel-metadata.json",
    "inventory": "docs/evidence/lowdim02a_flow32_cross_grid_2026_10_09/inventory.json",
    "prerun_note": "docs/evidence/lowdim02a_flow32_cross_grid_2026_10_09/prerun_note.md",
    "identity_free_check": "docs/evidence/lowdim02a_flow32_cross_grid_2026_10_09/identity_free_check.json",
    "proposal_raw": "docs/evidence/lowdim01_four_direction_capability_2026_10_09/inputs/proposal_downforce.dir_f4_fortran.raw",
    "t4_project": "julia/CFDSDFWaterLilyT4/Project.toml",
    "t4_manifest": "julia/CFDSDFWaterLilyT4/Manifest.toml",
    "formal_criteria": "docs/evidence/fd08_v2_formal_2026_10_07_amend3/formal_criteria.json",
    "lowdim01_analysis": "docs/evidence/lowdim01_four_direction_capability_2026_10_09/lowdim01_analysis.json",
    "w4_flow32_baseline_csv": "docs/evidence/kaggle_w4_v17_candidate_c_round2_retained/flow_32.forces.csv",
}


def sha(path):
    return hashlib.sha256((ROOT / path).read_bytes()).hexdigest()


def build(source_commit: str, parent: str) -> dict:
    inv = json.loads((E / "inventory.json").read_text())
    hashes = {name: sha(path) for name, path in FILES.items()}
    hashes["inventory_canonical_json"] = hashlib.sha256((json.dumps(inv, sort_keys=True, indent=2) + "\n").encode()).hexdigest()
    assert hashes["inventory_canonical_json"] == hashes["inventory"]
    assert inv["flow32_baseline_reference"]["forces_csv_sha256"] == hashes["w4_flow32_baseline_csv"]
    formal = json.loads((ROOT / FILES["formal_criteria"]).read_text())
    return {
        "kind": "lowdim02a_flow32_cross_grid_prerun_freeze", "parent_integration_commit": parent, "source_commit": source_commit, "file_hashes": hashes, "pins": kernel.pins(),
        "flow32_baseline": {"forces_csv_sha256": inv["flow32_baseline_reference"]["forces_csv_sha256"], "host_recomputed_n": inv["flow32_baseline_reference"]["host_recomputed_n"]},
        "runtime": formal["runtime"],
        "design": {"states": [r["name"] for r in inv["states"]], "case": "flow_32", "accepted_step": "LOWDIM-01 +1.25 mm along the proposal direction (flow_24: +4.05e-4 N)", "control": "-1.25 mm (reverse proposal)",
                   "descriptive_only_state": "lowdim02a__prop__s2.5mm", "kernel_id": kernel.metadata()["id"], "kernel_timeout_s": kernel.TIMEOUT_S, "reinitialization": "none"},
        "rules": {"min_resolved_n": contract.MIN_RESOLVED_N, "noise_factor": contract.NOISE_FACTOR, "nominal_sigma0_n": contract.NOMINAL_SIGMA0_N, "summary_rel": analyzer.SUMMARY_REL,
                  "baseline_rel": analyzer.BASELINE_REL, "min_t_end": analyzer.MIN_T_END, "flow32_case": contract.FLOW32_CASE,
                  "authority": "actual primal responses (host-recomputed with the flow_32 force scale); the geometry gates are those of the same LOWDIM-01 states"},
        "verdicts": list(contract.VERDICTS),
        "known_before_the_run": {"flow24_downforce_change_n": inv["flow24_reference_lowdim01"]["downforce_change_n"],
                                 "expectation": ("no prediction is registered for flow_32: the grid sensitivity of the force is large (flow_24 -> flow_32 baseline downforce +8.9%) and the accepted flow_24 gain is only +0.12%, "
                                                 "so STAGE_A_SIGN_FLIP and STAGE_A_UNRESOLVED are both plausible outcomes")},
        "prohibitions": {"gradient_claim": True, "grid01_completion_claim": True, "opt01_claim": True, "flag_change": True, "selected_delta": True, "grad03_verdict": True, "fd08_verdict_change": True,
                         "reinitialization": True, "post_hoc_states_or_thresholds": True, "stage_b_before_stage_a_result": True, "ad_or_tangent": True},
        "declarations": {"selected_delta": None, "grad03_verdict": None, "reverse": "untouched", "not_grid01": True, "not_opt01": True, "stage_b_requires_separate_preregistration": True},
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
