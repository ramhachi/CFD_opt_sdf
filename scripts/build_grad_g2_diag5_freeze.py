#!/usr/bin/env python3
"""Write the immutable G2-DIAG5 pre-registration freeze (hashes of everything the CPU matrix and its analysis depend on)."""
from __future__ import annotations

import argparse
import datetime
import glob
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import analyze_grad_g2_diag5 as analyzer  # noqa: E402
from scripts import run_grad_g2_diag5_local as driver  # noqa: E402

E = ROOT / "docs/evidence/grad03_g2_diag5_one_step_gain_2026_10_09"
D1E = ROOT / "docs/evidence/grad03_g2_diag1_d0_nonfinite_2026_10_08"
D2E = ROOT / "docs/evidence/grad03_g2_diag2_d0_tangent_counterfactual_2026_10_08"
D3E = ROOT / "docs/evidence/grad03_g2_diag3_tangent_poisson_2026_10_08"
D4E = ROOT / "docs/evidence/grad03_g2_diag4_forced32_horizon_2026_10_09"
FILES = {
    "job": "scripts/waterlily_grad_g2_diag5_one_step_gain_2026_10_09.jl",
    "stages": "scripts/waterlily_grad_g2_diag5_stages.jl",
    "driver": "scripts/run_grad_g2_diag5_local.py",
    "analyzer": "scripts/analyze_grad_g2_diag5.py",
    "prerun_note": "docs/evidence/grad03_g2_diag5_one_step_gain_2026_10_09/prerun_note.md",
    "project": "julia/CFDSDFWaterLily/Project.toml",
    "manifest": "julia/CFDSDFWaterLily/Manifest.toml",
    "candidate_c_body": "julia/CFDSDFWaterLily/src/CandidateCWaterLilyBody.jl",
    "normal_floor_body": "julia/CFDSDFWaterLily/src/WaterLilyNormalFloorBody.jl",
    "grid_sdf_body": "julia/CFDSDFWaterLily/src/GridSDFBody.jl",
    "snapshot_index": "docs/evidence/grad03_g2_diag1_d0_nonfinite_2026_10_08/kernel_output/snapshot_index.json",
    "checksums": "docs/evidence/grad03_g2_diag1_d0_nonfinite_2026_10_08/kernel_output/instrumented_checksums.csv",
    "diag4_job": "scripts/waterlily_grad_g2_diag4_forced32_horizon_2026_10_09.jl",
    "diag1_stages": "scripts/waterlily_grad_g2_diag1_stages.jl",
}
STORED_STATES = ("step0900.u", "step0900.p", "step1000.u", "step1000.p", "ring_step1188.u", "ring_step1188.p", "ring_step1189.u", "ring_step1189.p")
DIAG1_EVIDENCE = ("prerun_freeze.json", "diag1_analysis.json", "posthoc_addendum.json")
DIAG2_EVIDENCE = ("prerun_freeze.json", "diag2_analysis.json")
DIAG3_EVIDENCE = ("prerun_freeze.json", "diag3_analysis.json")
DIAG4_EVIDENCE = ("prerun_freeze.json", "diag4_analysis.json", "kernel_output/diag_index.json")
THRESHOLDS = ("AGREE_REL", "AGREE_COS", "AGREE_RATIO", "SMOOTH_FLIP_RATE", "SMOOTH_MIN_EPS", "SMOOTH_MAX_EPS", "FLIP_RANK_CORRELATION", "RANK_EPS_MAX", "RANK_MIN_POINTS", "LINEAR_AMPLITUDE",
              "RATE_MIN_POINTS", "FD_LOWER_FACTOR", "FD_MATCH", "SURROGATE_RATE_TOL", "SURROGATE_RATE_FLOOR", "SURROGATE_MISMATCH_REDUCTION", "SURROGATE_GAIN_TOL", "ULP_SENSITIVE", "AD_RATE_MIN",
              "ENSEMBLE_N", "E0_DT_REL", "E0_PRIMAL_U_REL", "E0_PRIMAL_P_REL", "K_STEPS", "EPS_E3", "EPS_E5", "EPS_E5_VARIANT_B", "STATES")
PRE_FREEZE_DISCLOSURES = [
    "numpy branch audit (x-direction fluxes only, advecting velocity approximated by a face average) of the stored u at steps 500 and 900: in the corner box about 79% of the limiter calls select the "
    "unlimited QUICK candidate, 19% the central value and 2% a limited branch; the median spread of the candidate values is 4.5e-6 (the box velocity has a standard deviation of 2e-5)",
    "a CPU prototype of the one-step map from stored step 1188 (ring) against the stored step 1189: dt tangent reproduced to 8e-7 (relative), primal u rel L2 3.6e-6, the corner tangent gain 1.12 on CPU against 1.33 on the T4 "
    "(corner tangent pattern rel L2 difference 0.47); with +-1 ulp noise on every primal u the corner tangent pattern changed by 1.7e-5 (0.1% of cells), 0.046 (10%) and 0.24 (100%) and the gain by 0 to 2.5%",
    "CPU timing: plain step 1.8 s, Dual step 2.7 s (1 thread); the bit identity of the instrumented step and of the limiter variants against `sim_step!` over three steps from the initial state",
    "an independent review found that a plain Float32 simulation is a different rounding of the map than the Dual simulation (@fastmath on quick/div/mu-ddn: 44% of the limiter values and 1.2M of 1.9M u values "
    "differ after one step at step 100); the finite-difference runs therefore use Dual simulations with zero tangents, the branch audit replicates WaterLily's median operand selection, and Delta t = CFL(u) is gated against the stored value for every state",
    "dry runs of every group on the stored step-100 state (not a registered state) with K=3 / ensemble 2, and of E0 on the registered ring state (identical to the registered run): E2 on step 100 showed that 74% of the "
    "corner-box limiter calls already have a kink distance below 1e-5; the relative divergence of the stored tangent direction at step 100 is 2.3e-2 (primal 5e-6)",
]


def sha(path):
    return hashlib.sha256((ROOT / path).read_bytes()).hexdigest()


def runtime_source_hashes() -> dict:
    flows = sorted(glob.glob(str(Path.home() / ".julia/packages/WaterLily/*/src/Flow.jl")))
    assert flows, "WaterLily 1.8.0 source is required to freeze the runtime source hashes"
    for rel in ("julia/CFDSDFWaterLily/Manifest.toml",):
        text = (ROOT / rel).read_text()
        block = text[text.index("[[deps.WaterLily]]"):][:600]
        assert 'git-tree-sha1 = "8e1d973f428df4bae450e1a45f19d0dba3ac6857"' in block and 'version = "1.8.0"' in block, rel
    src = Path(flows[-1]).parent
    return {f"waterlily_{n}_sha256": hashlib.sha256((src / f"{f}.jl").read_bytes()).hexdigest()
            for n, f in (("flow_jl", "Flow"), ("multilevelpoisson_jl", "MultiLevelPoisson"), ("poisson_jl", "Poisson"))} | {"waterlily_git_tree_sha1": "8e1d973f428df4bae450e1a45f19d0dba3ac6857"}


def stored_state_hashes() -> dict:
    text = (ROOT / FILES["snapshot_index"]).read_text()
    out = {}
    for name in STORED_STATES:
        m = re.search(r'"' + re.escape(name) + r'\.dual_f32_interleaved_value_tangent\.raw":\s*\{[^}]*?"sha256":\s*"([0-9a-f]{64})"', text)
        assert m, name
        out[name] = m.group(1)
    return out


def build(source_commit: str, parent: str) -> dict:
    d1 = json.loads((D1E / "prerun_freeze.json").read_text())
    hashes = {name: sha(path) for name, path in FILES.items()}
    pins = {FILES[k]: hashes[k] for k in ("job", "stages", "project", "manifest", "snapshot_index", "checksums")} | {driver.SRC_TREE: driver.sha256(ROOT / driver.SRC_TREE)}
    return {
        "kind": "grad03_g2_diag5_one_step_gain_prerun_freeze",
        "parent_integration_commit": parent,
        "source_commit": source_commit,
        "file_hashes": hashes,
        "pins": pins,
        "runtime_pins": d1["runtime_pins"],
        "runtime_source_hashes": runtime_source_hashes(),
        "stored_state_sha256": stored_state_hashes(),
        "diag1_evidence_sha256": {rel: hashlib.sha256((D1E / rel).read_bytes()).hexdigest() for rel in DIAG1_EVIDENCE},
        "diag2_evidence_sha256": {rel: hashlib.sha256((D2E / rel).read_bytes()).hexdigest() for rel in DIAG2_EVIDENCE},
        "diag3_evidence_sha256": {rel: hashlib.sha256((D3E / rel).read_bytes()).hexdigest() for rel in DIAG3_EVIDENCE},
        "diag4_evidence_sha256": {rel: hashlib.sha256((D4E / rel).read_bytes()).hexdigest() for rel in DIAG4_EVIDENCE},
        "prior_results": {"diag1": "DIAG_LOCALIZED", "diag2": "DIAG2_LOCALIZED", "diag3": "TANGENT_ONLY_NO_SUPPORT", "diag4": "FORCED32_DELAYED_ONSET"},
        "candidate_c_identity": d1["candidate_c_identity"],
        "canonical_state": d1["canonical_state"],
        "directions": {"fortran_raw_sha256_d0_only": d1["directions"]["fortran_raw_sha256_d0_only"], "baseline_phi": d1["directions"]["baseline_phi"],
                       "inputs_manifest_sha256": d1["directions"]["inputs_manifest_sha256"]},
        "scientific_state": {**d1["scientific_state"], "device": "CPU (re-evaluation of stored T4 states)", "threads": 1},
        "run": {
            "groups": {"E0": "harness closure: CPU one step from stored 1188 vs stored 1189 (faithful geometry seed, exact power-of-two scaling)",
                       "E1": "stage and term gains of the one-step tangent (full / box-only / outside-only; conv_diff roles x (i,j) x region; BDIM terms)",
                       "E2": "limiter audit (branch counts, kink distances, flip-prone fractions)",
                       "E3": "one-step JVP vs central FD, eps scan, flips, mismatch localisation, derivative variants (E4)",
                       "E3C": "the same with the solenoidal velocity direction (control)",
                       "E5AD": "multi-step AD tangent growth (baseline and derivative variants; direction C)", "E5FD": "multi-step finite-amplitude growth (variants A, B, C)",
                       "E6": "+-1 ulp roundoff ensemble on the primal u"},
            "states": ["S900", "S1000"], "e0_state": "R1188", "k_steps": analyzer.K_STEPS, "eps_e3": list(analyzer.EPS_E3), "eps_e5": list(analyzer.EPS_E5),
            "eps_e5_variants_b_c": list(analyzer.EPS_E5_VARIANT_B), "ensemble_n": 16, "tie_taus": [1e-5, 1e-4], "box_1based": {"i": [1, 12], "j": [1, 8], "k": [49, 56]},
            "persistent_state": "(u incl. ghost cells, p); p is the Poisson initial guess and is perturbed with u; Delta t[end] = CFL(u) is recomputed; u0, f, sigma, mu0, mu1, V are rebuilt by the step",
            "direction": "t = (delta u, delta p) / max|delta u| (interior, all components): ||eps t||_inf = eps in u; effective direction after Float32 rounding is used for the JVP in E3",
            "variants": {"A": "primary: the stored (delta u, delta p)", "B": "control: p not perturbed", "C": "control: the velocity direction projected onto the discrete solenoidal subspace (the solver's div, L = mu0, face gradient)"},
            "e4": {"baseline": "the frozen-branch derivative of the implemented map (ForwardDiff selects the branch of the primal values): the control", "tie": "value unchanged (original quick), partials averaged over the candidates within tau",
                   "linear": "partials of the unlimited QUICK candidate"}},
        "thresholds": {k: getattr(analyzer, k) for k in THRESHOLDS},
        "classification": ["R1_SELECTOR_CONVENTION", "R2_LINEARISATION_DEFECT", "R3_FINITE_INSTABILITY", "R4_INCONCLUSIVE", "DIAG5_INCOMPLETE"],
        "classification_priority": ["R2", "R3", "R1", "R4"],
        "pre_freeze_disclosures": PRE_FREEZE_DISCLOSURES,
        "prohibitions": {"float64_simulation": True, "d1_d2_p1": True, "bridge_analyzer": True, "fd08_comparison": True, "selected_delta": True, "grad03_verdict": True, "reverse": True, "flag_change": True,
                         "tangent_clip_reset_sanitise": True, "post_hoc_thresholds_or_states": True, "automatic_full_window_run": True, "t4_run_unless_e0_fails": True},
        "declarations": {"selected_delta": None, "grad03_verdict": None, "reverse": "untouched", "bridge_value": None, "float64_run": False, "d1_d2_p1_run": False,
                         "e4_variants_are_surrogate_derivatives_not_the_derivative_of_the_implemented_map": True, "r4_is_a_bounded_no_go_of_the_current_programme_not_of_full_field_ad": True},
        "qualification_flags": {k: False for k in analyzer.FLAGS},
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
