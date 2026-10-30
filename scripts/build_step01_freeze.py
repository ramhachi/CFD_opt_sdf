#!/usr/bin/env python3
"""Write the immutable STEP-01 (#47) pre-registration freeze (hashes of everything the three T4 kernels and the analysis depend on)."""
from __future__ import annotations

import argparse
import datetime
import glob
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src")); sys.path.insert(0, str(ROOT / "scripts"))
import analyze_step01 as analyzer  # noqa: E402
import build_step01_kernels as kernels  # noqa: E402
import step01_states as S  # noqa: E402
from cfd_sdf import step01_contract as contract  # noqa: E402

E = ROOT / "docs/evidence/step01_finite_step_secant_2026_10_09"
FILES = {
    "job": "scripts/waterlily_xfid_candidate_c_job.jl",
    "states_module": "scripts/step01_states.py",
    "runner_template": "scripts/step01_runner_template.py",
    "kernel_builder": "scripts/build_step01_kernels.py",
    "inputs_builder": "scripts/build_step01_inputs.py",
    "analyzer": "scripts/analyze_step01.py",
    "contract": "src/cfd_sdf/step01_contract.py",
    "force_io": "scripts/fd08_v2_campaign_io.py",
    "runner_a": "infra/kaggle/kernel_step01_a/runner.py",
    "runner_b": "infra/kaggle/kernel_step01_b/runner.py",
    "runner_c": "infra/kaggle/kernel_step01_c/runner.py",
    "metadata_a": "infra/kaggle/kernel_step01_a/kernel-metadata.json",
    "metadata_b": "infra/kaggle/kernel_step01_b/kernel-metadata.json",
    "metadata_c": "infra/kaggle/kernel_step01_c/kernel-metadata.json",
    "inventory": "docs/evidence/step01_finite_step_secant_2026_10_09/inventory.json",
    "prerun_note": "docs/evidence/step01_finite_step_secant_2026_10_09/prerun_note.md",
    "identity_free_check": "docs/evidence/step01_finite_step_secant_2026_10_09/identity_free_check.json",
    "t4_project": "julia/CFDSDFWaterLilyT4/Project.toml",
    "t4_manifest": "julia/CFDSDFWaterLilyT4/Manifest.toml",
    "formal_criteria": "docs/evidence/fd08_v2_formal_2026_10_07_amend3/formal_criteria.json",
    "direction_manifest": "docs/evidence/grad03_gpu_dual_spike_2026_10_08/inputs/inputs_manifest.json",
}
DIAG5_EVIDENCE = ("prerun_freeze.json", "diag5_analysis.json")


def sha(path):
    return hashlib.sha256((ROOT / path).read_bytes()).hexdigest()


def build(source_commit: str, parent: str) -> dict:
    inv = json.loads((E / "inventory.json").read_text())
    formal = json.loads((ROOT / FILES["formal_criteria"]).read_text())
    fits = {k: {"g_n_per_m": v["g_n_per_m"], "se_g_n_per_m": v["se_g_n_per_m"]} for k, v in formal["calibration_binding"]["fits"].items()}
    hashes = {name: sha(path) for name, path in FILES.items()}
    hashes["inventory_canonical_json"] = hashlib.sha256((json.dumps(inv, sort_keys=True, indent=2) + "\n").encode()).hexdigest()
    assert hashes["inventory_canonical_json"] == hashes["inventory"], "inventory.json is not in the canonical serialisation"
    assert len(fits) == 8
    files, directions = kernels.pins()
    flow = sorted(glob.glob(str(Path.home() / ".julia/packages/WaterLily/*/src/Flow.jl")))
    return {
        "kind": "step01_finite_step_secant_prerun_freeze",
        "parent_integration_commit": parent,
        "source_commit": source_commit,
        "file_hashes": hashes,
        "pins": files,
        "direction_files": directions,
        "fd08_baseline": {"forces_csv_sha256": inv["fd08_baseline_reference"]["forces_csv_sha256"], "host_recomputed_n": inv["fd08_baseline_reference"]["host_recomputed_n"]},
        "runtime": formal["runtime"],
        "design": {"states": len(inv["states"]), "kernels": {k: len(v) for k, v in inv["kernels"].items()}, "step_mm": list(S.STEP_MM), "fractions_h": list(S.FRACTIONS_H), "signs": [-1, 1],
                   "single_directions": list(S.SINGLE_DIRECTIONS), "combos": [list(p) for p in S.COMBOS], "combo_step_mm": S.COMBO_STEP_MM,
                   "combo_component_step_mm": {k: v["component_step_mm"] for k, v in inv["combined_directions"].items()}, "baseline_per_kernel": True,
                   "primary_quantity": "g_sec(s) = [R(+s) - R(-s)] / (2 s)", "nonlinearity_index": "eta_even(s) = |R(+s)+R(-s)-2R(0)| / |R(+s)-R(-s)|",
                   "response": "[80,120] tU/L endpoint-clipped trapezoid mean, drag=+Fx, downforce=-Fz, N", "kernel_timeout_s": kernels.TIMEOUT_S, "kernel_ids": {k: kernels.metadata(k)["id"] for k in S.KERNELS}},
        "definitions": {"agreement_tolerances": list(contract.AGREEMENT_TOLERANCES), "agreement_radius_name": "30% / 50% agreement radius (descriptive; not a validity claim)",
                        "nominal_sigma0_n": contract.NOMINAL_SIGMA0_N, "resolved_factor": contract.RESOLVED_FACTOR, "summary_rel": analyzer.SUMMARY_REL, "baseline_rel": analyzer.BASELINE_REL,
                        "min_t_end": analyzer.MIN_T_END, "interpolations": ["pchip", "linear"]},
        "fd08_g_hat_fits": fits,
        "diag5_evidence_sha256": {rel: hashlib.sha256((ROOT / "docs/evidence/grad03_g2_diag5_one_step_gain_2026_10_09" / rel).read_bytes()).hexdigest() for rel in DIAG5_EVIDENCE},
        "waterlily_flow_jl_sha256_local": hashlib.sha256(Path(flow[-1]).read_bytes()).hexdigest() if flow else None,
        "verdicts": ["STEP01_RECORDED", "STEP01_INCOMPLETE"],
        "prohibitions": {"gradient_claim": True, "fd08_verdict_change": True, "flag_change": True, "selected_delta": True, "grad03_verdict": True, "reverse": True, "ad_or_tangent": True,
                         "reuse_of_fd08_run_records": True, "post_hoc_steps_thresholds_or_directions": True, "calling_agreement_radius_a_validity_claim": True, "diag6": True},
        "declarations": {"selected_delta": None, "grad03_verdict": None, "reverse": "untouched", "gradient_qualification": False, "fd08_verdict_unchanged": True,
                         "agreement_radius_is_descriptive": True, "g_hat_is_model_a_local_slope_not_the_epsilon_to_zero_derivative": True},
        "qualification_flags": {k: False for k in analyzer.FLAGS},
        "frozen_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }


def check_git(source_commit: str) -> None:
    import subprocess
    dirty = subprocess.run(["git", "-C", str(ROOT), "status", "--porcelain", "--untracked-files=no"], capture_output=True, text=True).stdout.strip()
    if dirty:
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
