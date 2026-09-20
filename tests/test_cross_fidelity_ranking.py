"""Tests for the fail-closed cross-fidelity ranking qualification module."""

from __future__ import annotations

import json

import pytest

from cfd_sdf.cross_fidelity_ranking import (
    MIN_CANDIDATES,
    FidelityScores,
    RankingQualification,
    RankingReport,
    Uncertainty,
    qualify_cross_fidelity_ranking,
    kendall_tau,
    pair_is_resolvable,
    pair_sign,
    rank_values,
    spearman_tau,
)

UNCERTAINTY = Uncertainty(downforce_abs=0.0147, drag_coefficient_rel=0.034)


def _scores(fidelity_id: str, values: dict[str, float], **info) -> FidelityScores:
    return FidelityScores(fidelity_id=fidelity_id, values=values, info=info or {})


def test_module_exports_required_api():
    from cfd_sdf.cross_fidelity_ranking import (  # noqa: F401
        FidelityScores,
        RankingReport,
        Uncertainty,
        qualify_cross_fidelity_ranking,
    )


def test_identical_rankings_with_wide_margins_pass():
    reference = _scores("stage_v_v2", {"c1": 0.90, "c2": 1.00, "c3": 1.10, "c4": 1.20}, grid_level=2)
    surrogate = _scores("stage_t", {"c1": 0.85, "c2": 1.00, "c3": 1.15, "c4": 1.30}, grid_level=1)
    report = qualify_cross_fidelity_ranking(
        surrogate,
        reference,
        uncertainty=UNCERTAINTY,
        response_id="drag_coefficient",
    )
    assert report.verdict == "pass"
    assert report.n_sign_inversions == 0
    assert report.surrogate_order == report.reference_order


def test_rankings_agree_but_below_band_unresolved():
    reference = _scores("stage_v_v2", {"c1": 1.00, "c2": 1.01, "c3": 1.02, "c4": 1.03})
    surrogate = _scores("stage_t", {"c1": 1.00, "c2": 1.005, "c3": 1.02, "c4": 1.035})
    report = qualify_cross_fidelity_ranking(
        surrogate,
        reference,
        uncertainty=UNCERTAINTY,
        response_id="drag_coefficient",
    )
    assert report.surrogate_order == report.reference_order
    assert report.verdict == "unresolved"
    assert report.n_signed_pairs == 0


def test_one_big_resolvable_inversion_no_go():
    reference = _scores("stage_v_v2", {"c1": 1.00, "c2": 1.10, "c3": 1.20, "c4": 1.30})
    surrogate = _scores("stage_t", {"c1": 1.10, "c2": 1.00, "c3": 1.20, "c4": 1.30})
    report = qualify_cross_fidelity_ranking(
        surrogate,
        reference,
        uncertainty=UNCERTAINTY,
        response_id="drag_coefficient",
    )
    assert report.verdict == "no_go"
    assert report.n_sign_inversions == 1
    inverted = [p for p in report.pairs if p.verdict == "inverted"]
    assert [(p.candidate_a, p.candidate_b) for p in inverted] == [("c1", "c2")]


def test_candidate_set_mismatch_raises_value_error():
    surrogate = _scores("stage_t", {"a": 1.0, "b": 2.0})
    reference = _scores("stage_v_v2", {"a": 1.0, "c": 2.0})
    with pytest.raises(ValueError, match="candidate sets differ"):
        qualify_cross_fidelity_ranking(
            surrogate,
            reference,
            uncertainty=UNCERTAINTY,
            response_id="drag_coefficient",
        )


def test_require_benchmark_coverage_refuses_fewer_than_eight():
    values = {f"c{i}": 1.0 + 0.01 * i for i in range(7)}
    surrogate = _scores("stage_t", values)
    reference = _scores("stage_v_v2", dict(values))
    with pytest.raises(ValueError, match="require_benchmark_coverage"):
        qualify_cross_fidelity_ranking(
            surrogate,
            reference,
            uncertainty=UNCERTAINTY,
            response_id="drag_coefficient",
            require_benchmark_coverage=True,
        )


def test_require_benchmark_coverage_accepts_exactly_eight():
    values = {f"c{i}": 1.0 + 0.01 * i for i in range(MIN_CANDIDATES)}
    surrogate = _scores("stage_t", values)
    reference = _scores("stage_v_v2", dict(values))
    report = qualify_cross_fidelity_ranking(
        surrogate,
        reference,
        uncertainty=UNCERTAINTY,
        response_id="drag_coefficient",
        require_benchmark_coverage=True,
    )
    assert len(report.candidate_ids) == MIN_CANDIDATES
    assert report.n_pairs == 28


def test_spearman_and_kendall_on_known_examples():
    perfect = [1.0, 2.0, 3.0, 4.0]
    rho, rho_p = spearman_tau(perfect, list(perfect))
    tau, tau_p = kendall_tau(perfect, list(perfect))
    assert rho == pytest.approx(1.0)
    assert tau == pytest.approx(1.0)
    one_transposition_ref = [1.0, 2.0, 3.0, 4.0]
    one_transposition_surr = [2.0, 1.0, 3.0, 4.0]
    rho2, _ = spearman_tau(one_transposition_ref, one_transposition_surr)
    tau2, _ = kendall_tau(one_transposition_ref, one_transposition_surr)
    assert rho2 == pytest.approx(0.8)
    assert tau2 == pytest.approx(4.0 / 6.0)


def test_report_rank_correlations_match_known_example():
    reference = _scores("stage_v_v2", {"c1": 1.0, "c2": 2.0, "c3": 3.0, "c4": 4.0})
    surrogate = _scores("stage_t", {"c1": 2.0, "c2": 1.0, "c3": 3.0, "c4": 4.0})
    report = qualify_cross_fidelity_ranking(
        surrogate,
        reference,
        uncertainty=UNCERTAINTY,
        response_id="drag_coefficient",
        j_scale=10.0,
    )
    assert report.spearman_rho == pytest.approx(0.8)
    assert report.kendall_tau == pytest.approx(4.0 / 6.0)


def test_report_echoes_passed_uncertainty_verbatim():
    reference = _scores("stage_v_v2", {"c1": 0.90, "c2": 1.00, "c3": 1.10, "c4": 1.20})
    surrogate = _scores("stage_t", {"c1": 0.85, "c2": 1.00, "c3": 1.15, "c4": 1.30})
    report = qualify_cross_fidelity_ranking(
        surrogate,
        reference,
        uncertainty=UNCERTAINTY,
        response_id="drag_coefficient",
        j_scale=0.5,
        extraction_sensitivity={"c1": 0.02},
    )
    assert report.uncertainty == UNCERTAINTY
    assert report.response_uncertainty == UNCERTAINTY.drag_coefficient_rel
    assert report.j_scale == 0.5
    assert report.extraction_sensitivity == {"c1": 0.02}
    payload = report.to_dict()
    assert payload["uncertainty"] == {
        "downforce_abs": 0.0147,
        "drag_coefficient_rel": 0.034,
    }
    assert payload["response_uncertainty"] == 0.034


def test_non_finite_values_are_refused():
    with pytest.raises(ValueError, match="finite"):
        _scores("stage_t", {"c1": float("nan"), "c2": 1.0})
    with pytest.raises(ValueError, match="finite"):
        _scores("stage_t", {"c1": float("inf"), "c2": 1.0})
    with pytest.raises(ValueError, match="non-negative"):
        Uncertainty(downforce_abs=-1.0, drag_coefficient_rel=0.034)
    with pytest.raises(ValueError, match="finite"):
        Uncertainty(downforce_abs=float("nan"), drag_coefficient_rel=0.034)


def test_rank_values_sorts_and_refuses_bad_input():
    assert rank_values({"b": 1.0, "a": 1.0, "c": 0.5}) == ["c", "a", "b"]
    with pytest.raises(ValueError, match="finite"):
        rank_values({"a": float("nan")})
    with pytest.raises(ValueError, match="at least one candidate"):
        rank_values({})
    with pytest.raises(ValueError, match="real number"):
        rank_values({"a": "1.0"})


def test_pair_sign_and_resolvability():
    assert pair_sign(1.2, 1.0, 1.0) == pytest.approx(0.2 / 1.2)
    assert pair_sign(0.5, 1.5, 1.0) == pytest.approx(-1.0)
    with pytest.raises(ValueError):
        pair_sign(1.0, 0.0, 0.0)
    with pytest.raises(ValueError):
        pair_sign(float("inf"), 0.0, 1.0)
    assert pair_is_resolvable(0.1, 0.034, 0.034) is True
    assert pair_is_resolvable(0.05, 0.034, 0.034) is False
    assert pair_is_resolvable(0.1, 0.0, 0.0, 0.06, 0.0) is False
    assert pair_is_resolvable(0.13, 0.0, 0.0, 0.06, 0.0) is True


def test_required_pairs_gate_the_pass_verdict():
    reference = _scores("stage_v_v2", {"c1": 0.90, "c2": 1.00, "c3": 1.10, "c4": 1.20})
    surrogate = _scores("stage_t", {"c1": 0.85, "c2": 1.00, "c3": 1.15, "c4": 1.30})
    report = qualify_cross_fidelity_ranking(
        surrogate,
        reference,
        uncertainty=UNCERTAINTY,
        response_id="drag_coefficient",
        required_pairs=[("c1", "c2")],
    )
    assert report.verdict == "pass"
    assert report.failed_required_pairs == ()

    tight = _scores("stage_v_v2", {"c1": 1.00, "c2": 1.01, "c3": 1.10, "c4": 1.20})
    tight_surr = _scores("stage_t", {"c1": 1.00, "c2": 1.005, "c3": 1.15, "c4": 1.30})
    report = qualify_cross_fidelity_ranking(
        tight_surr,
        tight,
        uncertainty=UNCERTAINTY,
        response_id="drag_coefficient",
        required_pairs=[("c1", "c2")],
    )
    assert report.failed_required_pairs == (("c1", "c2"),)
    assert report.verdict == "unresolved"

    inverted_ref = _scores("stage_v_v2", {"c1": 1.00, "c2": 1.10, "c3": 1.20, "c4": 1.30})
    inverted_surr = _scores("stage_t", {"c1": 1.10, "c2": 1.00, "c3": 1.20, "c4": 1.30})
    report = qualify_cross_fidelity_ranking(
        inverted_surr,
        inverted_ref,
        uncertainty=UNCERTAINTY,
        response_id="drag_coefficient",
        required_pairs=[("c1", "c2")],
    )
    assert report.failed_required_pairs == (("c1", "c2"),)
    assert report.verdict == "no_go"


def test_required_pair_validation_is_fail_closed():
    reference = _scores("stage_v_v2", {"c1": 0.90, "c2": 1.00})
    surrogate = _scores("stage_t", {"c1": 0.85, "c2": 1.00})
    with pytest.raises(ValueError, match="outside the candidate set"):
        qualify_cross_fidelity_ranking(
            surrogate,
            reference,
            uncertainty=UNCERTAINTY,
            response_id="drag_coefficient",
            required_pairs=[("c1", "zz")],
        )
    with pytest.raises(ValueError, match="distinct"):
        qualify_cross_fidelity_ranking(
            surrogate,
            reference,
            uncertainty=UNCERTAINTY,
            response_id="drag_coefficient",
            required_pairs=[("c1", "c1")],
        )


def test_response_uncertainty_selection_and_unknown_response():
    reference = _scores("stage_v_v2", {"c1": 0.90, "c2": 1.00})
    surrogate = _scores("stage_t", {"c1": 0.85, "c2": 1.05})
    report = qualify_cross_fidelity_ranking(
        surrogate,
        reference,
        uncertainty=UNCERTAINTY,
        response_id="downforce_coefficient",
        j_scale=0.1,
    )
    assert report.response_uncertainty == UNCERTAINTY.downforce_abs
    with pytest.raises(ValueError, match="no declared per-response uncertainty"):
        qualify_cross_fidelity_ranking(
            surrogate,
            reference,
            uncertainty=UNCERTAINTY,
            response_id="sideforce",
        )


def test_enforces_two_candidate_minimum_and_refuses_empty():
    reference = _scores("stage_v_v2", {"c1": 1.0})
    surrogate = _scores("stage_t", {"c1": 1.0})
    with pytest.raises(ValueError, match="at least 2 candidates"):
        qualify_cross_fidelity_ranking(
            surrogate, reference, uncertainty=UNCERTAINTY, response_id="drag_coefficient"
        )
    with pytest.raises(ValueError, match="at least one candidate"):
        FidelityScores(fidelity_id="stage_t", values={})


def test_spearman_and_kendall_raise_runtime_error_without_scipy(monkeypatch):
    import cfd_sdf.cross_fidelity_ranking as module

    monkeypatch.setattr(module, "_scipy_stats", None)
    with pytest.raises(RuntimeError, match="scipy"):
        spearman_tau([1.0, 2.0], [1.0, 2.0])
    with pytest.raises(RuntimeError, match="scipy"):
        kendall_tau([1.0, 2.0], [1.0, 2.0])


def test_report_to_dict_is_json_serializable():
    reference = _scores("stage_v_v2", {"c1": 0.90, "c2": 1.00, "c3": 1.10, "c4": 1.20}, grid_level=2)
    surrogate = _scores("stage_t", {"c1": 0.85, "c2": 1.00, "c3": 1.15, "c4": 1.30}, grid_level=1)
    report = qualify_cross_fidelity_ranking(
        surrogate,
        reference,
        uncertainty=UNCERTAINTY,
        response_id="drag_coefficient",
    )
    payload = report.to_dict()
    assert isinstance(report, RankingReport)
    assert json.dumps(payload, allow_nan=False)
    assert payload["pairs"][0]["candidate_a"] == "c1"
    assert set(payload["pairs"][0]) == {
        "candidate_a",
        "candidate_b",
        "surrogate_improvement",
        "reference_improvement",
        "surrogate_sign",
        "reference_sign",
        "resolvable",
        "verdict",
    }


def test_ranking_qualification_assess_and_to_dict():
    reference = _scores("stage_v_v2", {"c1": 0.90, "c2": 1.00})
    surrogate = _scores("stage_t", {"c1": 0.85, "c2": 1.00})
    qualification = RankingQualification.assess(surrogate, reference, UNCERTAINTY)
    assert qualification.surrogate is surrogate
    assert qualification.reference is reference
    json.dumps(qualification.to_dict(), allow_nan=False)
    with pytest.raises(ValueError, match="candidate sets differ"):
        RankingQualification.assess(
            surrogate, _scores("stage_v_v2", {"c1": 0.90, "c3": 1.00}), UNCERTAINTY
        )
