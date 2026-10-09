"""G2-DIAG5 recorded result: the kept output is intact, the analysis is the registered one and reproducible from it, and the earlier records are untouched."""
import hashlib
import json
from pathlib import Path

from scripts import analyze_grad_g2_diag5 as A

ROOT = Path(__file__).resolve().parents[1]
E = ROOT / "docs/evidence/grad03_g2_diag5_one_step_gain_2026_10_09"
K = E / "run_output"
ANALYSIS = json.loads((E / "diag5_analysis.json").read_text())
FREEZE = json.loads((E / "prerun_freeze.json").read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def test_terminal_state_and_registered_identity():
    assert (K / "DONE").is_file() and not (K / "ERROR.txt").exists()
    drv = json.loads((K / "driver_index.json").read_text())
    assert drv["status"] == "COMPLETE" and drv["source_commit"] == FREEZE["source_commit"] and drv["pins"] == FREEZE["pins"] and len(drv["processes"]) == 21 and all(p["ok"] for p in drv["processes"])
    assert A.verify_integrity(K, FREEZE)["pass"] is True


def test_the_registered_classification_is_r4_for_both_states_and_contains_no_bridge_value():
    assert ANALYSIS["verdict"] == "R4_INCONCLUSIVE" and ANALYSIS["labels"] == {"S900": "R4_INCONCLUSIVE", "S1000": "R4_INCONCLUSIVE"} and ANALYSIS["gates"]["pass"] is True
    assert ANALYSIS["integrity"]["pass"] is True and ANALYSIS["selected_delta"] is None and ANALYSIS["grad03_verdict"] is None and ANALYSIS["no_bridge_value"] is True and set(ANALYSIS["qualification_flags"].values()) == {False}
    for s in A.STATES:
        st = ANALYSIS["states"][s]
        assert st["r2_testable"] is False and st["agrees_at_every_mid_eps"] is False and st["mismatch_grows_with_flips"] is False and st["baseline_disagrees_at_1e-3"] is True
        assert st["surrogate_one_step"]["agrees_with_fd"] is False and st["surrogate_one_step"]["mismatch_reduction"] > 0.85 and st["surrogate_one_step"]["gain_close_to_fd"] is True


def test_the_analysis_is_reproduced_from_the_kept_output():
    again = A.analyze(K)
    assert again["labels"] == ANALYSIS["labels"] and again["gates"]["pass"] is True
    for s in A.STATES:
        for key in ("flip_mismatch_rank_correlation", "agree_by_eps", "flip_rate_by_eps", "smooth_eps", "fd_growth_clearly_lower", "surrogate_reproduces_finite_growth"):
            assert json.loads(json.dumps(A.clean(again["states"][s][key]))) == ANALYSIS["states"][s][key], (s, key)


def test_post_hoc_observations_quoted_in_the_note_hold():
    import csv
    for s, (fd_lo, fd_hi, ad_lo) in {"S900": (0.52, 0.60, 1.3), "S1000": (0.52, 0.56, 1.4)}.items():
        rows = [r for r in csv.DictReader((K / f"{s}_E3" / "e3_rows.csv").open()) if r["region"] == "box" and r["lambda"] == "quick"]
        assert all(fd_lo <= float(r["gain_fd_box_max"]) <= fd_hi and float(r["gain_jvp_box_max"]) >= ad_lo for r in rows)
        fd = [float(r["l2_box"]) for r in csv.DictReader((K / f"{s}_E5FD_1e-3" / "e5fd_rows.csv").open()) if r["variant"] == "FD/A"]
        ad = [float(r["l2_box"]) for r in csv.DictReader((K / f"{s}_E5AD" / "e5ad_rows.csv").open()) if r["variant"] == "AD/quick"]
        assert fd[20] < fd[0] * 0.02 and ad[20] > ad[0] * 100                 # the finite response decays while the baseline AD tangent grows
        e6 = json.loads((K / f"{s}_E6" / "result.json").read_text())
        assert sorted(e6["pattern_changes"])[8] > 0.4 and sorted(e6["fd_changes"])[8] < 0.01


def test_earlier_records_are_untouched():
    for key, base in (("diag1_evidence_sha256", "grad03_g2_diag1_d0_nonfinite_2026_10_08"), ("diag2_evidence_sha256", "grad03_g2_diag2_d0_tangent_counterfactual_2026_10_08"),
                      ("diag3_evidence_sha256", "grad03_g2_diag3_tangent_poisson_2026_10_08"), ("diag4_evidence_sha256", "grad03_g2_diag4_forced32_horizon_2026_10_09")):
        for rel, digest in FREEZE[key].items():
            assert sha(ROOT / "docs/evidence" / base / rel) == digest, (key, rel)
