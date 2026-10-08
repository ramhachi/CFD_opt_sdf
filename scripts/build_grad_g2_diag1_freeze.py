#!/usr/bin/env python3
"""Write the immutable G2-DIAG1 pre-registration freeze (hashes of everything the T4 run and its analysis depend on)."""
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
from scripts import analyze_grad_g2_diag1 as analyzer  # noqa: E402

E = ROOT / "docs/evidence/grad03_g2_diag1_d0_nonfinite_2026_10_08"
G2E = ROOT / "docs/evidence/grad03_g2_full_window_forward_bridge_2026_10_08"
G2_FREEZE = G2E / "prerun_freeze.json"
FILES = {
    "script": "scripts/waterlily_grad_g2_diag1_d0_nonfinite_2026_10_08.jl",
    "stages": "scripts/waterlily_grad_g2_diag1_stages.jl",
    "runner": "infra/kaggle/kernel_grad_g2_diag1/runner.py",
    "kernel_metadata": "infra/kaggle/kernel_grad_g2_diag1/kernel-metadata.json",
    "analyzer": "scripts/analyze_grad_g2_diag1.py",
    "prerun_note": "docs/evidence/grad03_g2_diag1_d0_nonfinite_2026_10_08/prerun_note.md",
    "identity_free_check": "docs/evidence/grad03_g2_diag1_d0_nonfinite_2026_10_08/identity_free_check.json",
    "t4_project": "julia/CFDSDFWaterLilyT4/Project.toml",
    "t4_manifest": "julia/CFDSDFWaterLilyT4/Manifest.toml",
    "candidate_c_body": "julia/CFDSDFWaterLily/src/CandidateCWaterLilyBody.jl",
    "normal_floor_body": "julia/CFDSDFWaterLily/src/WaterLilyNormalFloorBody.jl",
    "grid_sdf_body": "julia/CFDSDFWaterLily/src/GridSDFBody.jl",
    "device_grid_sdf": "julia/CFDSDFWaterLily/src/DeviceGridSDF.jl",
    "g2_parent_script": "scripts/waterlily_grad_g2_full_window_bridge_2026_10_08.jl",
    "g2_parent_runner": "infra/kaggle/kernel_grad_g2_bridge/runner.py",
}
G2_EVIDENCE = ("prerun_freeze.json", "prerun_note.md", "note.md", "independent_reviews.md", "terminal_verification_attempt1.json", "identity_free_check.json",
               "kernel_attempt1/ERROR.txt", "kernel_attempt1/g2_run_index.json", "kernel_attempt1/plain.history.csv", "kernel_attempt1/plain.summary.json",
               "kernel_attempt1/run_identity.json", "kernel_attempt1/output_manifest.json", "SHA256SUMS")
STAGE_ORDER = ["measure", "pre_scale", "predict_conv_diff", "predict_accelerate", "predict_bdim", "predict_bc", "predict_exitbc",
               "project1_rhs", "project1_solve", "project1_gradient", "project1_bc",
               "correct_conv_diff", "correct_accelerate", "correct_bdim", "correct_scale", "correct_bc",
               "project2_rhs", "project2_solve", "project2_gradient", "project2_bc", "cfl", "cfl_dt",
               "force_candidate_pressure", "force_candidate_viscous", "force_candidate_total",
               "force_ground_pressure", "force_ground_viscous", "force_ground_total"]
HYPOTHESES = {
    "H1": "Float32 tangent dynamic-range overflow",
    "H2": "finite but unstable tangent dynamics during the start-up transient",
    "H3": "Candidate C / near-degenerate immersed-boundary coefficient derivative amplification",
    "H4": "finite-iteration Poisson derivative amplification",
    "H5": "force post-processing only is non-finite while state tangents are finite",
    "H6": "instrumentation-independent reproducibility failure / non-determinism",
}
DECISION_TABLE = {
    "A": "primal finite, tangent grows gradually toward overflow -> Float64 Dual precision discriminator strongly justified",
    "B": "tangent jumps from finite to huge in one step -> local diagnostic of the offending stage/operation first",
    "C": "Poisson tangent diverges first -> new pre-registered tolerance/iteration sensitivity diagnostic candidate",
    "D": "geometry coefficient tangent extreme/non-finite from setup -> investigate Candidate C derivative semantics first",
    "E": "state tangents finite, only the force computation is non-finite -> diagnose/repair the force derivative path locally",
    "F": "the primal went non-finite first -> investigate the offending stage's primal arithmetic locally",
    "unclassified": "no mechanical proposal; report to the user"}


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
    return {"waterlily_flow_jl_sha256": hashlib.sha256((src / "Flow.jl").read_bytes()).hexdigest(),
            "waterlily_multilevelpoisson_jl_sha256": hashlib.sha256((src / "MultiLevelPoisson.jl").read_bytes()).hexdigest(),
            "waterlily_git_tree_sha1": "8e1d973f428df4bae450e1a45f19d0dba3ac6857"}


def build(source_commit: str, parent: str) -> dict:
    g2 = json.loads(G2_FREEZE.read_text())
    meta = json.loads((ROOT / FILES["kernel_metadata"]).read_text())
    hashes = {name: sha(path) for name, path in FILES.items()}
    runner_pins = {FILES["t4_project"]: hashes["t4_project"], FILES["t4_manifest"]: hashes["t4_manifest"], FILES["script"]: hashes["script"], FILES["stages"]: hashes["stages"]}
    return {
        "kind": "grad03_g2_diag1_d0_nonfinite_prerun_freeze",
        "parent_integration_commit": parent,
        "source_commit": source_commit,
        "file_hashes": hashes,
        "pins": runner_pins,
        "runtime_pins": g2["runtime_pins"],
        "runtime_source_hashes": runtime_source_hashes(),
        "g2_attempt1_evidence_sha256": {rel: hashlib.sha256((G2E / rel).read_bytes()).hexdigest() for rel in G2_EVIDENCE},
        "g2_attempt1": {"source_commit": g2["source_commit"], "script_sha256": g2["file_hashes"]["script"], "runner_sha256": g2["file_hashes"]["runner"],
                        "failure": {"step": analyzer.G2_FAIL_STEP, "t_u_l_repr": analyzer.G2_FAIL_TIME_REPR}, "verdict": "G2-BLOCKED"},
        "candidate_c_identity": g2["candidate_c_identity"],
        "canonical_state": g2["canonical_state"],
        "directions": {"fortran_raw_sha256_d0_only": {"D0_interface_offset": g2["directions"]["fortran_raw_sha256"]["D0_interface_offset"]},
                       "baseline_phi": g2["directions"]["baseline_phi"], "inputs_manifest_sha256": g2["directions"]["inputs_manifest_sha256"]},
        "scientific_state": {"float": "Float32", "device": "CuArray (T4)", "dual_width": 1, "alpha_unit": "metre", "remeasure": True,
                             "poisson_tol": 1e-4, "poisson_itmx": analyzer.ITMX, "sample_every_steps_reference": 8, "case_id": "flow_24",
                             "force_semantics": "candidate only, -(pressure+viscous); drag=Fx, downforce=-Fz"},
        "run": {"order": ["A_reference_plain_sim_step", "B_instrumented_stage_copies"], "directions": ["D0_interface_offset"],
                "horizon": {"min_steps": 1400, "min_t_u_l": 20.0, "rule": "first step with both", "max_steps": 2000, "fail_fast": "stop after the step in which B first sees a non-finite value"},
                "snapshot_steps": [0, 2, 100, 500, 900, 1000, 1050, 1100, 1150, 1175, 1190, 1195, 1198, 1199], "snapshot_late": {"from": 1000, "every": 25},
                "ring_steps": 12, "sha256_every_steps": 25, "flush": "every step", "stage_order": STAGE_ORDER,
                "first_bad_rule": "first stage checkpoint, in execution order, whose field has a non-finite primal or tangent element; component = primal|tangent|both"},
        "analysis_constants": {k: getattr(analyzer, k) for k in ("G2_FAIL_STEP", "G2_FAIL_TIME_REPR", "ITMX", "PRE_FAILURE_STEPS", "SUDDEN_JUMP_DECADES", "EXP_MIN_SLOPE",
                                                                  "EXP_MIN_R2", "MONOTONE_FRACTION", "FLOAT32_NEAR_LIMIT_LOG10", "FLOAT32_FAR_LOG10", "H2_SUPPORT_DECADES",
                                                                  "H2_WEAK_DECADES")},
        "hypotheses": HYPOTHESES,
        "decision_table": DECISION_TABLE,
        "case_priority": ["E", "D", "F", "A", "C", "B", "unclassified"],
        "kernel_identity": {"id": meta["id"], "title": meta["title"], "type": meta["kernel_type"], "machine_shape": meta["machine_shape"]},
        "prohibitions": {"float64_dual": True, "d1_d2_p1": True, "bridge_analyzer": True, "selected_delta": True, "grad03_verdict": True, "reverse": True,
                         "poisson_tolerance_change": True, "candidate_c_change": True, "precision_change": True, "tangent_clipping_or_reset": True},
        "declarations": {"selected_delta": None, "grad03_verdict": None, "reverse": "untouched", "bridge_value": None, "float64_run": False, "d1_d2_p1_run": False},
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
