"""Tests for independent required-pair verification (DF5)."""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from cfd_sdf.cli import app
from cfd_sdf.independent_verification import (
    CandidateMeasurement,
    IndependentVerificationError,
    RequiredPair,
    verify_required_pairs,
)

runner = CliRunner()


def _measurement(
    candidate_id: str,
    role: str,
    downforce: float,
    *,
    numerical: float = 0.01,
    extraction: float = 0.0,
    gates: dict[str, bool] | None = None,
    used_in_optimization: bool = False,
    drag: float = 1.0,
) -> CandidateMeasurement:
    return CandidateMeasurement(
        candidate_id=candidate_id,
        role=role,
        responses={"downforce": downforce, "drag": drag},
        improvement_direction={"downforce": "decrease", "drag": "decrease"},
        numerical_uncertainty={"downforce": numerical, "drag": numerical},
        extraction_uncertainty={"downforce": extraction, "drag": extraction},
        gates=gates
        or {"mesh": True, "residual": True, "stationarity": True},
        grid_levels=("V1", "V2", "V3"),
        extraction_status="measured",
        used_in_optimization=used_in_optimization,
    )


def test_improvement_beyond_combined_uncertainty_passes():
    baseline = _measurement("baseline", "baseline", -0.50, numerical=0.005, extraction=0.005)
    stage_t = _measurement("stage_t", "stage_t", -0.60)
    verdict = verify_required_pairs(
        [baseline, stage_t],
        [RequiredPair("baseline", "stage_t", "baseline->T")],
        responses=["downforce"],
    )
    assert verdict["passed"] is True
    assert verdict["pairs"][0]["verdict"] == "improved"
    # the pair uses the larger of the two candidate-specific combined uncertainties
    assert verdict["pairs"][0]["combined_uncertainty"] == pytest.approx(0.01)


def test_improvement_below_uncertainty_is_unresolved():
    baseline = _measurement("baseline", "baseline", -0.50, numerical=0.05)
    stage_t = _measurement("stage_t", "stage_t", -0.52)
    verdict = verify_required_pairs(
        [baseline, stage_t],
        [RequiredPair("baseline", "stage_t", "baseline->T")],
    )
    assert verdict["passed"] is False
    assert verdict["pairs"][0]["verdict"] == "unresolved"


def test_wrong_direction_beyond_uncertainty_is_regressed():
    baseline = _measurement("baseline", "baseline", -0.50)
    stage_t = _measurement("stage_t", "stage_t", -0.40)
    verdict = verify_required_pairs(
        [baseline, stage_t],
        [RequiredPair("baseline", "stage_t", "baseline->T")],
    )
    assert verdict["pairs"][0]["verdict"] == "regressed"
    assert verdict["passed"] is False


def test_missing_gate_suppresses_conclusion_without_dropping_rows():
    baseline = _measurement("baseline", "baseline", -0.50, gates={"mesh": True, "residual": False, "stationarity": True})
    stage_t = _measurement("stage_t", "stage_t", -0.70)
    verdict = verify_required_pairs(
        [baseline, stage_t],
        [RequiredPair("baseline", "stage_t", "baseline->T")],
    )
    assert verdict["pairs"][0]["verdict"] == "gate_failed"
    assert verdict["pairs"][0]["gate_failures"] == {"baseline": ["residual"]}
    assert verdict["pairs"][0]["from_candidate"] == "baseline"


def test_reference_used_in_optimization_is_rejected():
    baseline = _measurement("baseline", "baseline", -0.50, used_in_optimization=True)
    stage_t = _measurement("stage_t", "stage_t", -0.60)
    with pytest.raises(IndependentVerificationError, match="tuning signal"):
        verify_required_pairs(
            [baseline, stage_t],
            [RequiredPair("baseline", "stage_t", "baseline->T")],
        )


def test_not_measured_extraction_forces_unresolved():
    baseline = _measurement("baseline", "baseline", -0.50)
    stage_t = _measurement("stage_t", "stage_t", -0.70)
    stage_t = dataclasses.replace(stage_t, extraction_status="not_measured")
    verdict = verify_required_pairs(
        [baseline, stage_t],
        [RequiredPair("baseline", "stage_t", "baseline->T")],
        responses=["downforce"],
    )
    assert verdict["passed"] is False
    assert verdict["pairs"][0]["verdict"] == "unresolved_extraction_not_measured"


def test_unknown_role_and_duplicate_roles_are_rejected():
    baseline = _measurement("baseline", "baseline", -0.50)
    stage_t = _measurement("stage_t", "stage_t", -0.60)
    with pytest.raises(IndependentVerificationError, match="missing roles"):
        verify_required_pairs(
            [baseline],
            [RequiredPair("baseline", "stage_s", "baseline->S")],
        )
    with pytest.raises(IndependentVerificationError, match="duplicate candidate role"):
        verify_required_pairs(
            [baseline, _measurement("baseline_two", "baseline", -0.4), stage_t],
            [RequiredPair("baseline", "stage_t", "baseline->T")],
        )


def test_cli_writes_verdict_and_exits_nonzero_on_unresolved(tmp_path: Path):
    document = {
        "measurements": [
            {
                "candidate_id": "baseline",
                "role": "baseline",
                "responses": {"downforce": -0.5},
                "improvement_direction": {"downforce": "decrease"},
                "numerical_uncertainty": {"downforce": 0.05},
                "extraction_uncertainty": {"downforce": 0.0},
                "gates": {"mesh": True, "residual": True, "stationarity": True},
                "grid_levels": ["V1", "V2", "V3"],
                "extraction_status": "measured",
            },
            {
                "candidate_id": "stage_t",
                "role": "stage_t",
                "responses": {"downforce": -0.51},
                "improvement_direction": {"downforce": "decrease"},
                "numerical_uncertainty": {"downforce": 0.005},
                "extraction_uncertainty": {"downforce": 0.005},
                "gates": {"mesh": True, "residual": True, "stationarity": True},
                "grid_levels": ["V1", "V2", "V3"],
                "extraction_status": "measured",
            },
        ],
        "required_pairs": [{"from_role": "baseline", "to_role": "stage_t", "label": "baseline->T"}],
        "responses": ["downforce"],
    }
    input_path = tmp_path / "verification_input.json"
    input_path.write_text(json.dumps(document), encoding="utf-8")
    output_path = tmp_path / "verdict.json"
    result = runner.invoke(
        app,
        ["verify-required-pairs", str(input_path), "--output", str(output_path)],
    )
    assert result.exit_code == 1
    verdict = json.loads(output_path.read_text(encoding="utf-8"))
    assert verdict["pairs"][0]["verdict"] == "unresolved"
    assert verdict["combined_uncertainty_rule"].startswith("root_sum_square")


def test_missing_grid_levels_and_response_uncertainty_are_rejected():
    baseline = _measurement("baseline", "baseline", -0.50)
    stage_t = _measurement("stage_t", "stage_t", -0.60)
    two_levels = dataclasses.replace(baseline, grid_levels=("V1", "V2"))
    with pytest.raises(IndependentVerificationError, match="grid level"):
        verify_required_pairs(
            [two_levels, stage_t],
            [RequiredPair("baseline", "stage_t", "baseline->T")],
            responses=["downforce"],
        )

    missing_band = dataclasses.replace(
        baseline,
        numerical_uncertainty={"drag": 0.01},
        extraction_uncertainty={"drag": 0.0},
    )
    with pytest.raises(IndependentVerificationError, match="missing numerical uncertainty"):
        verify_required_pairs(
            [missing_band, stage_t],
            [RequiredPair("baseline", "stage_t", "baseline->T")],
            responses=["downforce"],
        )

    with pytest.raises(IndependentVerificationError, match="extraction_status"):
        bad_status = dataclasses.replace(baseline, extraction_status="unknown")
        verify_required_pairs(
            [bad_status, stage_t],
            [RequiredPair("baseline", "stage_t", "baseline->T")],
            responses=["downforce"],
        )
