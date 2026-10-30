"""Pre-registered G1 decision rule: pass, partial and fail branches on synthetic results."""
import copy

from scripts import evaluate_grad_dual_gpu_g1 as g1

GOOD = {"status": "COMPLETE", "float32": {
    "fields_finite_incl_partials": True, "primal_rel_diff_max": 2e-6,
    "combined_fx": {"ad_tangent": 23000.0}, "combined_fz": {"ad_tangent": -4600.0},
    "cand_drag": {"ad_tangent": -23000.0}, "cand_downforce": {"ad_tangent": 4000.0}}}


def test_good_result_passes():
    out = g1.decide(GOOD)
    assert out["verdict"] == "G1-PASS" and all(out["checks"].values())


def test_primal_mismatch_or_tangent_disagreement_is_partial_not_pass():
    bad_primal = copy.deepcopy(GOOD); bad_primal["float32"]["primal_rel_diff_max"] = 5e-3
    assert g1.decide(bad_primal)["verdict"] == "PARTIAL"
    off = copy.deepcopy(GOOD); off["float32"]["combined_fx"]["ad_tangent"] = 30000.0
    assert g1.decide(off)["verdict"] == "PARTIAL"


def test_incomplete_nonfinite_or_zero_tangent_fails():
    assert g1.decide({"status": "ERROR", "error": "MethodError"})["verdict"] == "G1-FAIL"
    nan = copy.deepcopy(GOOD); nan["float32"]["cand_drag"]["ad_tangent"] = float("nan")
    assert g1.decide(nan)["verdict"] == "G1-FAIL"
    zero = copy.deepcopy(GOOD); zero["float32"]["combined_fz"]["ad_tangent"] = 0.0
    assert g1.decide(zero)["verdict"] == "G1-FAIL"
    unfinite = copy.deepcopy(GOOD); unfinite["float32"]["fields_finite_incl_partials"] = False
    assert g1.decide(unfinite)["verdict"] == "G1-FAIL"


def test_float32_done_is_judged_but_error_is_not():
    partial_run = copy.deepcopy(GOOD); partial_run["status"] = "FLOAT32_DONE"
    assert g1.decide(partial_run)["verdict"] == "G1-PASS"
    errored = copy.deepcopy(GOOD); errored["status"] = "ERROR"
    assert g1.decide(errored)["verdict"] == "G1-FAIL"
