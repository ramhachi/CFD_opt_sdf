#!/usr/bin/env python3
"""Write the immutable G2-DIAG3 pre-registration freeze (hashes of everything the T4 run and its analysis depend on)."""
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
from scripts import analyze_grad_g2_diag3 as analyzer  # noqa: E402

E = ROOT / "docs/evidence/grad03_g2_diag3_tangent_poisson_2026_10_08"
D1E = ROOT / "docs/evidence/grad03_g2_diag1_d0_nonfinite_2026_10_08"
D2E = ROOT / "docs/evidence/grad03_g2_diag2_d0_tangent_counterfactual_2026_10_08"
FILES = {
    "script": "scripts/waterlily_grad_g2_diag3_poisson_tangent_2026_10_08.jl",
    "stages_diag3": "scripts/waterlily_grad_g2_diag3_stages.jl",
    "stages_diag1": "scripts/waterlily_grad_g2_diag1_stages.jl",
    "fixture": "scripts/waterlily_grad_g2_diag3_fixture.jl",
    "fixture_test": "scripts/test_grad_g2_diag3_poisson_fixture.jl",
    "runner": "infra/kaggle/kernel_grad_g2_diag3/runner.py",
    "kernel_metadata": "infra/kaggle/kernel_grad_g2_diag3/kernel-metadata.json",
    "analyzer": "scripts/analyze_grad_g2_diag3.py",
    "host_window": "scripts/grad_g2_window.py",
    "prerun_note": "docs/evidence/grad03_g2_diag3_tangent_poisson_2026_10_08/prerun_note.md",
    "fixture_results": "docs/evidence/grad03_g2_diag3_tangent_poisson_2026_10_08/fixture_results.json",
    "identity_free_check": "docs/evidence/grad03_g2_diag3_tangent_poisson_2026_10_08/identity_free_check.json",
    "t4_project": "julia/CFDSDFWaterLilyT4/Project.toml",
    "t4_manifest": "julia/CFDSDFWaterLilyT4/Manifest.toml",
    "candidate_c_body": "julia/CFDSDFWaterLily/src/CandidateCWaterLilyBody.jl",
    "normal_floor_body": "julia/CFDSDFWaterLily/src/WaterLilyNormalFloorBody.jl",
    "grid_sdf_body": "julia/CFDSDFWaterLily/src/GridSDFBody.jl",
    "device_grid_sdf": "julia/CFDSDFWaterLily/src/DeviceGridSDF.jl",
    "g2_parent_script": "scripts/waterlily_grad_g2_full_window_bridge_2026_10_08.jl",
    "diag2_job": "scripts/waterlily_grad_g2_diag2_d0_tangent_counterfactual_2026_10_08.jl",
}
DIAG1_EVIDENCE = ("prerun_freeze.json", "diag1_analysis.json", "posthoc_addendum.md", "posthoc_addendum.json", "note.md")
DIAG2_EVIDENCE = ("prerun_freeze.json", "diag2_analysis.json", "note.md", "kernel_output/diag_index.json", "kernel_output/output_manifest.json")
G2_PLAIN_HISTORY = "docs/evidence/grad03_g2_full_window_forward_bridge_2026_10_08/kernel_attempt1/plain.history.csv"
HYPOTHESES = {
    "H11": "tangent Poisson solve left unconverged because the stop test is primal-only (DIAG2 supports; the variable of DIAG3)",
    "H14": "the tangent mean of the Poisson residual is not removed by `residual!` when the primal mean is tiny (Dual path), making the tangent system incompatible (post-hoc, from the DIAG3 fixture)",
}


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
    pins = {FILES[k]: hashes[k] for k in ("t4_project", "t4_manifest", "script", "stages_diag1", "stages_diag3", "fixture")}
    return {
        "kind": "grad03_g2_diag3_tangent_poisson_prerun_freeze",
        "parent_integration_commit": parent,
        "source_commit": source_commit,
        "file_hashes": hashes,
        "pins": pins,
        "runtime_pins": d1["runtime_pins"],
        "runtime_source_hashes": runtime_source_hashes(),
        "diag1_evidence_sha256": {rel: hashlib.sha256((D1E / rel).read_bytes()).hexdigest() for rel in DIAG1_EVIDENCE},
        "diag2_evidence_sha256": {rel: hashlib.sha256((D2E / rel).read_bytes()).hexdigest() for rel in DIAG2_EVIDENCE},
        "g2_plain_history_sha256": sha(G2_PLAIN_HISTORY),
        "diag2": {"verdict": "DIAG2_LOCALIZED", "baseline_slope": 0.1009, "forced32_slope": -0.0003, "forced16_slope": 0.0394, "forced4_slope": 0.1713},
        "candidate_c_identity": d1["candidate_c_identity"],
        "canonical_state": d1["canonical_state"],
        "directions": {"fortran_raw_sha256_d0_only": d1["directions"]["fortran_raw_sha256_d0_only"], "baseline_phi": d1["directions"]["baseline_phi"],
                       "inputs_manifest_sha256": d1["directions"]["inputs_manifest_sha256"]},
        "scientific_state": d1["scientific_state"],
        "poisson_semantics": {
            "system": "A(L) x = z (Neumann), L = mu0; under ForwardDiff r = z - A x with partials dr = dz - dA x - A dx (dA = A'(L) dL is nonzero in the body band)",
            "primal_stop": "r2 = L2(p) < 1e-4 on values only (WaterLily MultiLevelPoisson.solver!, itmx 32); unchanged in every A arm",
            "tangent_only_continuation": "primal solve unchanged; then A e = (dr - active-set mean) solved by the value-only multigrid on the same operator; dx <- dx + e; primal bytes never written",
            "gauge": "residual! skips the mean correction when |primal mean| <= 2 eps, also for the tangent; the refinement removes the active-set mean of dr and records it"},
        "run": {"fork_step": analyzer.FORK_STEP, "end_step": analyzer.END_STEP, "slope_window": [analyzer.SLOPE_FROM, analyzer.END_STEP],
                "arms": analyzer.ARM_NAMES, "taus": list(analyzer.TAUS), "counts": list(analyzer.COUNTS), "max_tangent_cycles": analyzer.MAX_TANGENT_CYCLES,
                "primal_identity": "value-only checksums of u, p and the dt value bits equal to the plain replay at every step (A0 also full bits)",
                "floor": "global max |tangent u| of the plain replay at the fork step (step 780)",
                "stage_b": {"horizon": "fresh D0 from step 0 until sim_time >= 120 tU/L, G2 sampling every 8 steps", "box_max": analyzer.LONG_BOX_MAX, "global_max": analyzer.LONG_GLOBAL_MAX,
                            "primal_gate": analyzer.PRIMAL_GATE, "summary_agreement": analyzer.SUMMARY_AGREEMENT}},
        "analysis_constants": {k: getattr(analyzer, k) for k in ("FORK_STEP", "END_STEP", "SLOPE_FROM", "BASELINE_MIN_SLOPE", "SUPPRESS_SLOPE", "FLOOR_FACTOR", "REDUCE_FACTOR",
                                                                  "MAX_TANGENT_CYCLES", "PLATEAU_RUN", "LONG_BOX_MAX", "LONG_GLOBAL_MAX", "MIN_POINTS", "PRIMAL_GATE", "SUMMARY_AGREEMENT")},
        "selection_rule": "threshold-family arm that suppresses with primal identity, belongs to a run of >= 3 consecutive suppressing settings and has a looser neighbour that also suppresses; fewest mean tangent cycles; ties -> tighter",
        "hypotheses": HYPOTHESES,
        "kernel_identity": {"id": meta["id"], "title": meta["title"], "type": meta["kernel_type"], "machine_shape": meta["machine_shape"]},
        "prohibitions": {"float64_dual": True, "d1_d2_p1": True, "bridge_analyzer": True, "fd08_comparison": True, "selected_delta": True, "grad03_verdict": True, "reverse": True,
                         "candidate_c_change": True, "production_backend_selection": True, "manual_candidate_replacement": True},
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
