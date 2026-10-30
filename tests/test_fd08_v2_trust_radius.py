"""Solver-free trust-radius analysis: formulas, exact reproduction of stored fits, determinism, no claims."""
import json
import math

import numpy as np
import pytest

from scripts import analyze_fd08_v2_trust_radius as tr


def test_radius_formulas_hit_the_requested_ratio():
    g, c, k = -1e-4, 3e-6, 2e-5
    for ratio in tr.RATIOS:
        eps_a = float(tr.radius_a(g, c, ratio))
        eps_b = float(tr.radius_b(g, k, ratio))
        assert math.isclose(abs(c) * eps_a**2 / abs(g), ratio, rel_tol=1e-12)
        assert math.isclose(abs(k) * eps_b / abs(g), ratio, rel_tol=1e-12)


def test_zero_higher_order_coefficient_is_unbounded():
    assert np.isinf(tr.radius_a(1e-4, 0.0, 0.1)) and np.isinf(tr.radius_b(1e-4, 0.0, 0.1))


@pytest.fixture(scope="module")
def result():
    return tr.analyze()


def test_all_eight_stored_fits_are_reproduced_by_the_frozen_evaluator(result):
    assert len(result["series"]) == 8
    assert all(row["stored_fit_reproduced_by_evaluate_series"] for row in result["series"])


def test_analysis_is_deterministic(result):
    assert json.dumps(tr.analyze(), sort_keys=True) == json.dumps(result, sort_keys=True)


def test_radius_ordering_and_units(result):
    assert result["method"]["calibrated_range_mm"] == [0.5, 5.0]
    for row in result["series"]:
        for block in (row["model_A_cubic"], row["model_B_quadratic"]):
            r = block["ratios"]
            for key in ("point_mm", "p05_mm", "p50_mm"):
                values = [r[x][key] for x in ("0.05", "0.10", "0.20")]
                if all(v is not None for v in values):
                    assert values == sorted(values)
            lower = r["0.10"]["p05_mm"]
            assert math.isclose(r["0.10"]["p05_in_h_sdf"], lower / 25.0)


def test_formal_comparison_counts_and_claim_limits(result):
    comparison = result["formal_model_A_vs_B"]
    assert comparison["closer_A"] + comparison["closer_B"] == 24 == len(comparison["comparisons"])
    assert "extrapolations" in result["claim_limit"] and "No flag or verdict changes" in result["claim_limit"]
    assert set(result["qualification_flags"].values()) == {False}
