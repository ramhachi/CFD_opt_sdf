#!/usr/bin/env python3
"""Write the immutable G2-DIAG4 pre-registration freeze (hashes of everything the T4 run and its analysis depend on)."""
from __future__ import annotations

import argparse
import datetime
import glob
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import analyze_grad_g2_diag4 as analyzer  # noqa: E402

E = ROOT / "docs/evidence/grad03_g2_diag4_forced32_horizon_2026_10_09"
D1E = ROOT / "docs/evidence/grad03_g2_diag1_d0_nonfinite_2026_10_08"
D2E = ROOT / "docs/evidence/grad03_g2_diag2_d0_tangent_counterfactual_2026_10_08"
D3E = ROOT / "docs/evidence/grad03_g2_diag3_tangent_poisson_2026_10_08"
FILES = {
    "script": "scripts/waterlily_grad_g2_diag4_forced32_horizon_2026_10_09.jl",
    "stages_diag3": "scripts/waterlily_grad_g2_diag3_stages.jl",
    "stages_diag1": "scripts/waterlily_grad_g2_diag1_stages.jl",
    "runner": "infra/kaggle/kernel_grad_g2_diag4/runner.py",
    "kernel_metadata": "infra/kaggle/kernel_grad_g2_diag4/kernel-metadata.json",
    "analyzer": "scripts/analyze_grad_g2_diag4.py",
    "prerun_note": "docs/evidence/grad03_g2_diag4_forced32_horizon_2026_10_09/prerun_note.md",
    "identity_free_check": "docs/evidence/grad03_g2_diag4_forced32_horizon_2026_10_09/identity_free_check.json",
    "t4_project": "julia/CFDSDFWaterLilyT4/Project.toml",
    "t4_manifest": "julia/CFDSDFWaterLilyT4/Manifest.toml",
    "candidate_c_body": "julia/CFDSDFWaterLily/src/CandidateCWaterLilyBody.jl",
    "normal_floor_body": "julia/CFDSDFWaterLily/src/WaterLilyNormalFloorBody.jl",
    "grid_sdf_body": "julia/CFDSDFWaterLily/src/GridSDFBody.jl",
    "device_grid_sdf": "julia/CFDSDFWaterLily/src/DeviceGridSDF.jl",
    "g2_parent_script": "scripts/waterlily_grad_g2_full_window_bridge_2026_10_08.jl",
    "diag2_job": "scripts/waterlily_grad_g2_diag2_d0_tangent_counterfactual_2026_10_08.jl",
    "diag2_stages": "scripts/waterlily_grad_g2_diag2_stages.jl",
    "diag3_job": "scripts/waterlily_grad_g2_diag3_poisson_tangent_2026_10_08.jl",
    "ref_straight": "docs/evidence/grad03_g2_diag3_tangent_poisson_2026_10_08/kernel_output/straight_checksums.csv",
    "ref_f32": "docs/evidence/grad03_g2_diag3_tangent_poisson_2026_10_08/kernel_output/arm_F32_forced_dual_32.steps.csv",
}
DIAG1_EVIDENCE = ("prerun_freeze.json", "diag1_analysis.json", "posthoc_addendum.json")
DIAG2_EVIDENCE = ("prerun_freeze.json", "diag2_analysis.json", "kernel_output/variant_V1c_poisson_n32.steps.csv")
DIAG3_EVIDENCE = ("prerun_freeze.json", "diag3_analysis.json", "kernel_output/output_manifest.json", "kernel_output/diag_index.json")


def sha(path):
    return hashlib.sha256((ROOT / path).read_bytes()).hexdigest()


def runtime_source_hashes() -> dict:
    flows = sorted(glob.glob(str(Path.home() / ".julia/packages/WaterLily/*/src/Flow.jl")))
    assert flows, "WaterLily 1.8.0 source is required to freeze the runtime source hashes"
    for rel in ("julia/CFDSDFWaterLilyT4/Manifest.toml", "julia/CFDSDFWaterLily/Manifest.toml"):
        text = (ROOT / rel).read_text()
        block = text[text.index("[[deps.WaterLily]]"):][:600]
        assert 'git-tree-sha1 = "8e1d973f428df4bae450e1a45f19d0dba3ac6857"' in block and 'version = "1.8.0"' in block, rel
    src = Path(flows[-1]).parent
    return {f"waterlily_{n}_sha256": hashlib.sha256((src / f"{f}.jl").read_bytes()).hexdigest()
            for n, f in (("flow_jl", "Flow"), ("multilevelpoisson_jl", "MultiLevelPoisson"), ("poisson_jl", "Poisson"))} | {"waterlily_git_tree_sha1": "8e1d973f428df4bae450e1a45f19d0dba3ac6857"}


def build(source_commit: str, parent: str) -> dict:
    d1 = json.loads((D1E / "prerun_freeze.json").read_text())
    meta = json.loads((ROOT / FILES["kernel_metadata"]).read_text())
    hashes = {name: sha(path) for name, path in FILES.items()}
    pins = {FILES[k]: hashes[k] for k in ("t4_project", "t4_manifest", "script", "stages_diag1", "stages_diag3", "ref_straight", "ref_f32")}
    return {
        "kind": "grad03_g2_diag4_forced32_horizon_prerun_freeze",
        "parent_integration_commit": parent,
        "source_commit": source_commit,
        "file_hashes": hashes,
        "pins": pins,
        "runtime_pins": d1["runtime_pins"],
        "runtime_source_hashes": runtime_source_hashes(),
        "diag1_evidence_sha256": {rel: hashlib.sha256((D1E / rel).read_bytes()).hexdigest() for rel in DIAG1_EVIDENCE},
        "diag2_evidence_sha256": {rel: hashlib.sha256((D2E / rel).read_bytes()).hexdigest() for rel in DIAG2_EVIDENCE},
        "diag3_evidence_sha256": {rel: hashlib.sha256((D3E / rel).read_bytes()).hexdigest() for rel in DIAG3_EVIDENCE},
        "prior_results": {"diag2": "DIAG2_LOCALIZED", "diag3": "TANGENT_ONLY_NO_SUPPORT", "forced32_vs_diag2_v1c_bitwise_equal_steps": 200, "baseline_slope": 0.1009, "forced32_slope_880_980": -0.0003},
        "candidate_c_identity": d1["candidate_c_identity"],
        "canonical_state": d1["canonical_state"],
        "directions": {"fortran_raw_sha256_d0_only": d1["directions"]["fortran_raw_sha256_d0_only"], "baseline_phi": d1["directions"]["baseline_phi"],
                       "inputs_manifest_sha256": d1["directions"]["inputs_manifest_sha256"]},
        "scientific_state": d1["scientific_state"],
        "run": {"arms": {"B0": "original semantics (plain sim_step!), step 0 -> 1500", "B32fork": "exact clone of B0 at step 780, forced solver!(b; tol=0.0, itmx=32) for steps 781 -> 1500 (PRIMARY)",
                         "B32fresh": "forced 32 from step 0 -> 1500, independent (SECONDARY: history dependence only, never used for the primary verdict)"},
                "fork_step": analyzer.FORK_STEP, "end_step": analyzer.END_STEP, "reference_last_step": analyzer.REF_LAST_STEP,
                "regression_gates": ["B0 steps 1..980 == DIAG3 straight (full bits)", "B32fork steps 781..980 == DIAG3 F32 arm (= DIAG2 V1c) (full bits)", "clone bit-identical at the fork step"],
                "intervals": [list(i) for i in analyzer.INTERVALS], "rolling_windows": [list(w) for w in analyzer.ROLLING], "snapshot_steps": [1000, 1250, 1500],
                "box_1based": dict(zip("ijk", [list(b) for b in analyzer.BOX]))},
        "analysis_constants": {k: getattr(analyzer, k) for k in ("FORK_STEP", "END_STEP", "REF_LAST_STEP", "GROWTH_SLOPE", "GROWTH_R2", "MIN_POINTS", "BOX_MAX_GATE", "GLOBAL_MAX_GATE",
                                                                  "DOMINANCE_FACTOR", "MODE_WINDOW", "BOX_ENERGY_FRACTION", "MODE_OUTSIDE_FRACTION")},
        "classification": ["FORCED32_NO_ONSET_OBSERVED_TO_1500", "FORCED32_DELAYED_ONSET", "FORCED32_DIFFERENT_MODE", "FORCED32_GROWTH_UNLOCALIZED", "DIAG4_INCOMPLETE"],
        "kernel_identity": {"id": meta["id"], "title": meta["title"], "type": meta["kernel_type"], "machine_shape": meta["machine_shape"]},
        "prohibitions": {"float64_dual": True, "d1_d2_p1": True, "bridge_analyzer": True, "fd08_comparison": True, "selected_delta": True, "grad03_verdict": True, "reverse": True,
                         "flag_change": True, "diag5_internal_decomposition": True, "adaptive_extra_arm": True, "automatic_full_window_run": True, "forced32_as_ad_fix": True},
        "declarations": {"selected_delta": None, "grad03_verdict": None, "reverse": "untouched", "bridge_value": None, "float64_run": False, "d1_d2_p1_run": False,
                         "forced32_is_a_different_solver_candidate": True},
        "qualification_flags": {k: False for k in ("fd_oracle", "field_gradient", "reverse", "optimizer", "topology", "shape_update_allowed")},
        "frozen_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source-commit", required=True)
    p.add_argument("--parent", required=True)
    args = p.parse_args()
    out = E / "prerun_freeze.json"
    if out.exists():
        sys.exit("refusing to overwrite the freeze")
    data = (json.dumps(build(args.source_commit, args.parent), sort_keys=True, indent=2) + "\n").encode()
    out.write_bytes(data)
    out.with_name(out.name + ".sha256").write_text(hashlib.sha256(data).hexdigest() + "\n")
    print(hashlib.sha256(data).hexdigest())


if __name__ == "__main__":
    main()
