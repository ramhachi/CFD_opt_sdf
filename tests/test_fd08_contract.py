from __future__ import annotations

from pathlib import Path
import sys

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cfd_sdf.fd08_contract import (
    audit_float32_perturbation,
    evaluate_fd08_response,
    validate_fd08_binding,
    validate_fd08_design,
    validate_fd08_run_partition,
)


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


def _design() -> list[dict]:
    rows = [{"run_id": f"fresh-baseline-{index}", "role": "baseline"} for index in range(3)]
    rows.extend(
        {
            "run_id": f"fresh-d{direction}-e{epsilon}-s{sign}",
            "role": "perturbation",
            "direction_id": f"D{direction}",
            "epsilon_m": epsilon * 1e-3,
            "sign": sign,
        }
        for direction in range(3)
        for epsilon in (0.1, 0.2, 0.4, 0.8, 1.6)
        for sign in (-1, 1)
    )
    return rows


def test_fd08_design_checks_supplied_rectangular_33_run_inventory_without_registering():
    result = validate_fd08_design(["cal-01", "cal-02"], _design())
    assert result["qualification_run_count"] == 33
    assert result["criteria_registered"] is False
    rows = _design()
    rows[-1] = {**rows[-1], "run_id": "cal-01"}
    with pytest.raises(ValueError, match="reused"):
        validate_fd08_design(["cal-01"], rows)
    rows = _design()
    rows.pop()
    with pytest.raises(ValueError, match="exactly 33"):
        validate_fd08_design(["cal-01"], rows)
    with pytest.raises(ValueError, match="must be a mapping"):
        validate_fd08_design(["cal-01"], [None])


def test_fd08_binding_fails_closed_without_the_frozen_candidate_c_identity(tmp_path: Path):
    with pytest.raises(ValueError, match="frozen Candidate C identity"):
        validate_fd08_binding(
            tmp_path,
            calibration_backend="Kaggle-T4",
            qualification_backend="Kaggle-T4",
            flow_id="flow_24",
            window_tu_l=(80, 120),
            canonical_state_sha256="02f48f6488be4f5d772c3ec515d4860b00e0e4a84d38aa56b187c82c1a615dcb",
            canonical_phi_fortran_f32_sha256="e3966d87c0ddb0d3ff9a6ee096c94221d0d4cccff77221ba84987ef5faa04431",
        )
    with pytest.raises(ValueError, match="Kaggle-T4"):
        validate_fd08_binding(
            tmp_path,
            calibration_backend="CPU",
            qualification_backend="CPU",
            flow_id="flow_24",
            window_tu_l=(80, 120),
            canonical_state_sha256="02f48f6488be4f5d772c3ec515d4860b00e0e4a84d38aa56b187c82c1a615dcb",
            canonical_phi_fortran_f32_sha256="e3966d87c0ddb0d3ff9a6ee096c94221d0d4cccff77221ba84987ef5faa04431",
        )


@pytest.mark.parametrize("floor", [0.0, True, float("nan")])
def test_fd08_resolution_floor_must_be_positive_finite_nonboolean(floor):
    with pytest.raises(ValueError, match="positive finite"):
        evaluate_fd08_response(_rows(), resolution_floor_n=floor)


def test_fd08_float32_perturbation_records_actual_change_and_rejects_rounding_or_mismatch():
    base = np.array([0.0, 1.0], dtype=np.float32)
    direction = np.array([1.0, 0.0])
    actual = np.array([1e-4, 1.0], dtype=np.float32)
    result = audit_float32_perturbation(
        base, direction, epsilon_m=1e-4, sign=1, actual_phi=actual
    )
    assert result["changed_node_count"] == 1
    assert result["actual_phi_dtype"] == "float32"
    with pytest.raises(ValueError, match="rounded away"):
        audit_float32_perturbation(
            base, np.zeros_like(base), epsilon_m=1e-4, sign=1, actual_phi=base
        )
    with pytest.raises(ValueError, match="does not match"):
        audit_float32_perturbation(
            base, direction, epsilon_m=1e-4, sign=1, actual_phi=base
        )
    with pytest.raises(ValueError, match="stored as Float32"):
        audit_float32_perturbation(
            base, direction, epsilon_m=1e-4, sign=1, actual_phi=actual.astype(np.float64)
        )
