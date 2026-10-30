#!/usr/bin/env python3
"""Write the immutable G2-DIAG2 pre-registration freeze (hashes of everything the T4 run and its analysis depend on)."""
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
from scripts import analyze_grad_g2_diag2 as analyzer  # noqa: E402

E = ROOT / "docs/evidence/grad03_g2_diag2_d0_tangent_counterfactual_2026_10_08"
D1E = ROOT / "docs/evidence/grad03_g2_diag1_d0_nonfinite_2026_10_08"
D1_FREEZE = D1E / "prerun_freeze.json"
FILES = {
    "script": "scripts/waterlily_grad_g2_diag2_d0_tangent_counterfactual_2026_10_08.jl",
    "stages_diag2": "scripts/waterlily_grad_g2_diag2_stages.jl",
    "stages_diag1": "scripts/waterlily_grad_g2_diag1_stages.jl",
    "runner": "infra/kaggle/kernel_grad_g2_diag2/runner.py",
    "kernel_metadata": "infra/kaggle/kernel_grad_g2_diag2/kernel-metadata.json",
    "analyzer": "scripts/analyze_grad_g2_diag2.py",
    "prerun_note": "docs/evidence/grad03_g2_diag2_d0_tangent_counterfactual_2026_10_08/prerun_note.md",
    "identity_free_check": "docs/evidence/grad03_g2_diag2_d0_tangent_counterfactual_2026_10_08/identity_free_check.json",
    "t4_project": "julia/CFDSDFWaterLilyT4/Project.toml",
    "t4_manifest": "julia/CFDSDFWaterLilyT4/Manifest.toml",
    "candidate_c_body": "julia/CFDSDFWaterLily/src/CandidateCWaterLilyBody.jl",
    "normal_floor_body": "julia/CFDSDFWaterLily/src/WaterLilyNormalFloorBody.jl",
    "grid_sdf_body": "julia/CFDSDFWaterLily/src/GridSDFBody.jl",
    "device_grid_sdf": "julia/CFDSDFWaterLily/src/DeviceGridSDF.jl",
    "g2_parent_script": "scripts/waterlily_grad_g2_full_window_bridge_2026_10_08.jl",
    "diag1_job": "scripts/waterlily_grad_g2_diag1_d0_nonfinite_2026_10_08.jl",
}
DIAG1_EVIDENCE = ("prerun_freeze.json", "prerun_note.md", "note.md", "diag1_analysis.json", "posthoc_addendum.md", "posthoc_addendum.json", "independent_reviews.md",
                  "kernel_output/output_manifest.json", "kernel_output/diag_index.json", "kernel_output/first_bad.json")
VARIANTS = {
    "V0_baseline": {"kill": None, "poisson": None, "freeze_dt": False},
    "V1a_poisson_n4": {"kill": None, "poisson": {"tol": 0.0, "itmx": 4}, "freeze_dt": False},
    "V1b_poisson_n16": {"kill": None, "poisson": {"tol": 0.0, "itmx": 16}, "freeze_dt": False},
    "V1c_poisson_n32": {"kill": None, "poisson": {"tol": 0.0, "itmx": 32}, "freeze_dt": False},
    "V2_dt_tangent_frozen": {"kill": None, "poisson": None, "freeze_dt": True},
    "V3_kill_corner_box": {"kill": "i1:12 j1:8 k49:56", "poisson": None, "freeze_dt": False},
    "V4a_kill_slab_xmin": {"kill": "i1:8", "poisson": None, "freeze_dt": False},
    "V4b_kill_slab_ymin": {"kill": "j1:8", "poisson": None, "freeze_dt": False},
    "V4c_kill_slab_zmax": {"kill": "k49:56", "poisson": None, "freeze_dt": False},
    "V4d_kill_slabs_all": {"kill": "i1:8 + j1:8 + k49:56", "poisson": None, "freeze_dt": False},
    "V5_kill_ghost_layers": {"kill": "outer 2 cells of every face", "poisson": None, "freeze_dt": False},
    "V6_kill_exit_slab": {"kill": "i145:152", "poisson": None, "freeze_dt": False},
}
HYPOTHESES = {
    "H11": "tangent Poisson solve unconverged because the stop test is primal-only (post-hoc, from DIAG1)",
    "H12": "dt tangent feedback through the CFL max selection",
    "H8": "boundary / corner tangent path",
    "H7": "exit-side tangent",
    "H13": "ghost-layer tangent boundary condition",
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
    return {"waterlily_flow_jl_sha256": hashlib.sha256((src / "Flow.jl").read_bytes()).hexdigest(),
            "waterlily_multilevelpoisson_jl_sha256": hashlib.sha256((src / "MultiLevelPoisson.jl").read_bytes()).hexdigest(),
            "waterlily_git_tree_sha1": "8e1d973f428df4bae450e1a45f19d0dba3ac6857"}


def build(source_commit: str, parent: str) -> dict:
    d1 = json.loads(D1_FREEZE.read_text())
    meta = json.loads((ROOT / FILES["kernel_metadata"]).read_text())
    hashes = {name: sha(path) for name, path in FILES.items()}
    pins = {FILES[k]: hashes[k] for k in ("t4_project", "t4_manifest", "script", "stages_diag1", "stages_diag2")}
    return {
        "kind": "grad03_g2_diag2_d0_tangent_counterfactual_prerun_freeze",
        "parent_integration_commit": parent,
        "source_commit": source_commit,
        "file_hashes": hashes,
        "pins": pins,
        "runtime_pins": d1["runtime_pins"],
        "runtime_source_hashes": runtime_source_hashes(),
        "diag1_evidence_sha256": {rel: hashlib.sha256((D1E / rel).read_bytes()).hexdigest() for rel in DIAG1_EVIDENCE},
        "diag1": {"source_commit": d1["source_commit"], "verdict": "DIAG_LOCALIZED", "first_bad": {"step": 1196, "stage": "correct_conv_diff", "field": "f", "component": "tangent"},
                  "post_hoc": {"corner_box_1based": "i1:12 j1:8 k49:56", "growth_decade_per_step": 0.0975, "extrapolated_onset_step": 800}},
        "candidate_c_identity": d1["candidate_c_identity"],
        "canonical_state": d1["canonical_state"],
        "directions": {"fortran_raw_sha256_d0_only": d1["directions"]["fortran_raw_sha256_d0_only"], "baseline_phi": d1["directions"]["baseline_phi"],
                       "inputs_manifest_sha256": d1["directions"]["inputs_manifest_sha256"]},
        "scientific_state": d1["scientific_state"],
        "run": {"fork_step": analyzer.FORK_STEP, "end_step": analyzer.END_STEP, "slope_window": [analyzer.SLOPE_FROM, analyzer.END_STEP], "variants": VARIANTS,
                "primary_metric": "log10 of the global max |tangent u| after project2_bc (before that stage's intervention)",
                "intervention_stages": ["predict_bc", "predict_exitbc", "project1_bc", "correct_bc", "project2_bc"],
                "v0_gate": "per-step checksums (u, p, dt bits) equal to the straight replay for steps FORK+1..END"},
        "analysis_constants": {k: getattr(analyzer, k) for k in ("FORK_STEP", "END_STEP", "SLOPE_FROM", "BASELINE_MIN_SLOPE", "SUPPRESS_SLOPE", "REDUCE_FACTOR", "MIN_POINTS", "GAIN_WINDOW")},
        "hypotheses": HYPOTHESES,
        "hypothesis_variants": {h: list(v) for h, v in analyzer.HYPOTHESES.items()},
        "kernel_identity": {"id": meta["id"], "title": meta["title"], "type": meta["kernel_type"], "machine_shape": meta["machine_shape"]},
        "prohibitions": {"float64_dual": True, "d1_d2_p1": True, "bridge_analyzer": True, "selected_delta": True, "grad03_verdict": True, "reverse": True,
                         "candidate_c_change": True, "production_fix": True, "conv_diff_internal_split": True},
        "declarations": {"selected_delta": None, "grad03_verdict": None, "reverse": "untouched", "bridge_value": None, "float64_run": False, "d1_d2_p1_run": False,
                         "interventions_are_counterfactual_not_fixes": True},
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
