from __future__ import annotations

import pytest

from cfd_sdf.fd08_contract import evaluate_fd08_response, validate_fd08_run_partition


def _qualification_ids() -> list[str]:
    return [f"fresh-{index:02d}" for index in range(33)]


def _rows(*, resolved: bool = True, deviation: float = 0.04, sign: int = 1) -> list[dict]:
    return [
        {
            "response_n": sign * (2e-5 if resolved else 5e-6),
            "plateau_relative_deviation": deviation,
            "resolved": resolved,
            "sign": sign,
        }
        for _ in range(3)
    ]


def test_fd08_partition_requires_33_unique_fresh_runs():
    validate_fd08_run_partition(["cal-1", "cal-2"], _qualification_ids())
    with pytest.raises(ValueError, match="reused"):
        validate_fd08_run_partition(["cal-1"], ["cal-1", *_qualification_ids()[1:]])
    with pytest.raises(ValueError, match="exactly 33"):
        validate_fd08_run_partition(["cal-1"], _qualification_ids()[:-1])
    with pytest.raises(ValueError, match="duplicate"):
        validate_fd08_run_partition(["cal-1", "cal-1"], _qualification_ids())


def test_fd08_verdict_keeps_resolution_plateau_and_sign_separate():
    assert evaluate_fd08_response(_rows(), resolution_floor_n=1e-5)["verdict"] == "PASS"
    assert evaluate_fd08_response(
        _rows(resolved=False), resolution_floor_n=1e-5
    )["verdict"] == "UNRESOLVED"
    assert evaluate_fd08_response(
        _rows(deviation=0.051), resolution_floor_n=1e-5
    )["verdict"] == "FAIL"
    assert evaluate_fd08_response(
        [*_rows()[:2], *_rows(sign=-1)[:1]], resolution_floor_n=1e-5
    )["verdict"] == "FAIL"


def test_fd08_cannot_call_a_subfloor_response_resolved():
    with pytest.raises(ValueError, match="cannot be resolved"):
        evaluate_fd08_response(_rows(resolved=True), resolution_floor_n=2e-5)


def test_fd08_zero_response_is_unresolved_and_cannot_form_a_plateau_alone():
    zero = [{"response_n": 0.0, "plateau_relative_deviation": 0.0, "resolved": False, "sign": 0}]
    with pytest.raises(ValueError, match="at least 3"):
        evaluate_fd08_response(zero, resolution_floor_n=1e-5)
    rows = zero * 3
    assert evaluate_fd08_response(rows, resolution_floor_n=1e-5)["verdict"] == "UNRESOLVED"


def test_fd08_rejects_boolean_sign_and_nonfinite_values():
    rows = _rows()
    rows[0]["sign"] = True
    with pytest.raises(ValueError, match="not boolean"):
        evaluate_fd08_response(rows, resolution_floor_n=1e-5)
    rows = _rows()
    rows[0]["response_n"] = float("nan")
    with pytest.raises(ValueError, match="finite"):
        evaluate_fd08_response(rows, resolution_floor_n=1e-5)
