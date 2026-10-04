from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from cfd_sdf.fd08_calibration import (
    FORMAL_DIRECTION_IDS,
    aggregate_formal_verdict,
    audit_float32_centered_pair,
    clipped_time_mean_from_rows,
    derive_response_floor,
    evaluate_formal_direction_response,
    select_formal_epsilon_ladder,
    validate_calibration_ladder,
    validate_formal_epsilon_ladder,
    verify_output_manifest,
    verify_registered_dataset,
)
from verify_fd08_formal import verify_source_inputs


def _calibration_rows(epsilons: tuple[float, ...], slope: float) -> list[dict]:
    return [{"epsilon_m": eps, "centered_response_n": slope * eps,
             "centered_slope_n_per_m": slope, "sign": 1}
            for eps in epsilons]


def test_exact_endpoint_clipping_recomputes_linear_force_mean():
    rows = [{"t_u_l": t, "drag_solver": 2 * t, "downforce_solver": -3 * t,
             "step": t, "fx_solver": 2 * t, "fy_solver": 0, "fz_solver": 3 * t,
             "pressure_fx_solver": t, "pressure_fy_solver": 0, "pressure_fz_solver": 0,
             "viscous_fx_solver": t, "viscous_fy_solver": 0, "viscous_fz_solver": 3 * t}
            for t in (79.0, 91.0, 113.0, 121.0)]
    assert clipped_time_mean_from_rows(rows, "drag_solver") == pytest.approx(200.0)
    assert clipped_time_mean_from_rows(rows, "downforce_solver") == pytest.approx(-300.0)


def test_response_floor_uses_exactly_five_repeats_and_positive_guard():
    exact = derive_response_floor([0.3] * 5)
    assert exact["repeat_count"] == 5
    assert exact["span_n"] == 0.0
    assert exact["response_floor_n"] == pytest.approx(1e-8)
    varied = derive_response_floor([0.3, 0.3001, 0.3, 0.2999, 0.3])
    assert varied["response_floor_n"] == pytest.approx(0.0002)
    with pytest.raises(ValueError, match="exactly 5"):
        derive_response_floor([0.3] * 4)


def test_calibration_epsilon_ladder_requires_broad_unique_positive_range():
    ladder = (1e-4, 3e-4, 1e-3, 3e-3, 1e-2, 3e-2, 1e-1)
    assert validate_calibration_ladder(ladder) == ladder
    with pytest.raises(ValueError, match="span at least"):
        validate_calibration_ladder((1e-3, 2e-3, 3e-3, 4e-3, 5e-3, 6e-3, 1e-2))
    with pytest.raises(ValueError, match="strictly increasing"):
        validate_calibration_ladder((1e-4, 3e-4, 1e-3, 3e-3, 1e-2, 3e-2, 3e-2))


def test_formal_epsilon_ladder_is_exactly_five_selected_points():
    ladder = (1e-4, 3e-4, 1e-3, 3e-3, 1e-2)
    assert validate_formal_epsilon_ladder(ladder) == ladder
    with pytest.raises(ValueError, match="exactly 5"):
        validate_formal_epsilon_ladder((*ladder, 3e-2))
    with pytest.raises(ValueError, match="strictly increasing"):
        validate_formal_epsilon_ladder((1e-4, 1e-3, 3e-4, 3e-3, 1e-2))


def test_runner_output_manifest_checks_full_inventory_and_file_bytes(tmp_path: Path):
    root = tmp_path / "output"
    root.mkdir()
    terminal = root / "result.json"
    terminal.write_text('{"status":"complete"}\n')
    digest = hashlib.sha256(terminal.read_bytes()).hexdigest()
    (root / "sha256.json").write_text(json.dumps({"result.json": digest}))
    (root / "DONE").write_text("complete\n")
    verified = verify_output_manifest(root, terminal)
    assert verified["verified_file_count"] == 1
    terminal.write_text("tampered\n")
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        verify_output_manifest(root, terminal)


def test_registered_dataset_verifies_exact_staged_payload(tmp_path: Path):
    root = tmp_path / "dataset"
    root.mkdir()
    payload = root / "baseline.raw"
    payload.write_bytes(b"phi")
    criteria_bytes = b'{"immutable":true}\n'
    criteria_sha = hashlib.sha256(criteria_bytes).hexdigest()
    (root / "xfidc_criteria.json").write_bytes(criteria_bytes)
    (root / "xfidc_criteria.json.sha256").write_text(criteria_sha + "\n")
    (root / "dataset-metadata.json").write_text("{}\n")
    criteria = {"dataset_files": {"baseline.raw": hashlib.sha256(b"phi").hexdigest()}}
    assert verify_registered_dataset(criteria, criteria_sha, root)["verified_file_count"] == 1
    payload.write_bytes(b"changed")
    with pytest.raises(ValueError, match="file SHA-256 mismatch"):
        verify_registered_dataset(criteria, criteria_sha, root)


def test_float32_direction_audit_reports_realized_pair_and_rejects_rounding_error():
    base = np.array([0.25, -0.5, 1.0], dtype=np.float32)
    direction = np.array([1.0, 0.0, -1.0])
    eps = 1e-2
    plus = np.asarray(base.astype(np.float64) + eps * direction, dtype=np.float32)
    minus = np.asarray(base.astype(np.float64) - eps * direction, dtype=np.float32)
    result = audit_float32_centered_pair(base, direction, epsilon_m=eps,
                                         phi_plus=plus, phi_minus=minus)
    assert result["changed_node_count_plus"] == 2
    assert result["changed_node_count_minus"] == 2
    assert result["direction_gate_passed"] is True
    with pytest.raises(ValueError, match="Float32"):
        audit_float32_centered_pair(base, direction, epsilon_m=1e-8,
                                    phi_plus=base.copy(), phi_minus=base.copy())


def test_calibration_selection_is_common_smallest_contiguous_five_for_all_six():
    eps = (1e-4, 3e-4, 1e-3, 3e-3, 1e-2, 3e-2, 1e-1)
    pairs = {direction: {response: _calibration_rows(eps, 0.01)
                         for response in ("drag", "downforce")}
             for direction in ("D0", "D1", "D2")}
    result = select_formal_epsilon_ladder(
        epsilons_m=eps, pairs=pairs, response_floors_n={"drag": 1e-8, "downforce": 1e-8})
    assert result["status"] == "COMMON_PLATEAU_FOUND"
    assert result["selected_formal_epsilon_ladder_m"] == list(eps[:5])
    pairs["D2"]["drag"] = _calibration_rows(eps, 0.01)
    pairs["D2"]["drag"][0]["centered_slope_n_per_m"] = 0.012
    pairs["D2"]["drag"][0]["centered_response_n"] = 0.012 * eps[0]
    result = select_formal_epsilon_ladder(
        epsilons_m=eps, pairs=pairs, response_floors_n={"drag": 1e-8, "downforce": 1e-8})
    assert result["status"] == "COMMON_PLATEAU_FOUND"
    assert result["selected_formal_epsilon_ladder_m"] == list(eps[1:6])


def test_formal_verdict_gives_resolved_failure_precedence_over_subfloor_rows():
    rows = [{"epsilon_m": eps, "response_plus_n": 0.01 * eps, "response_minus_n": -0.01 * eps}
            for eps in (1e-4, 3e-4, 1e-3, 3e-3, 1e-2)]
    rows[0] = {"epsilon_m": 1e-4, "response_plus_n": 1e-12, "response_minus_n": -1e-12}
    rows[3] = {"epsilon_m": 3e-3, "response_plus_n": 0.014 * 3e-3,
               "response_minus_n": -0.014 * 3e-3}
    result = evaluate_formal_direction_response(rows, response_floor_n=1e-8)
    assert result["verdict"] == "FAIL"
    assert "resolved_plateau_failure" in result["failure_gates"]
    rows = [{"epsilon_m": eps, "response_plus_n": 0.01 * eps, "response_minus_n": -0.01 * eps}
            for eps in (1e-4, 3e-4, 1e-3, 3e-3, 1e-2)]
    rows[0] = {"epsilon_m": 1e-4, "response_plus_n": 1e-12, "response_minus_n": -1e-12}
    assert evaluate_formal_direction_response(rows, response_floor_n=1e-8)["verdict"] == "UNRESOLVED"


def test_formal_aggregate_requires_six_cells_and_fails_before_unresolved():
    values = {f"{d}/{r}": {"verdict": "PASS"}
              for d in FORMAL_DIRECTION_IDS for r in ("drag", "downforce")}
    values[f"{FORMAL_DIRECTION_IDS[1]}/drag"] = {"verdict": "UNRESOLVED"}
    values[f"{FORMAL_DIRECTION_IDS[2]}/downforce"] = {"verdict": "FAIL"}
    result = aggregate_formal_verdict(values)
    assert result["verdict"] == "FAIL"
    assert result["qualification_flags"]["fd_oracle"] is False
    with pytest.raises(ValueError, match="six registered"):
        aggregate_formal_verdict({f"{FORMAL_DIRECTION_IDS[0]}/drag": {"verdict": "PASS"}})


def test_fd08_t4_runner_reuses_registered_xfid_runner_byte_for_byte():
    repo = Path(__file__).resolve().parents[1]
    assert (repo / "infra/kaggle/kernel_fd08_calibration/runner_base.py").read_bytes() == (
        repo / "infra/kaggle/kernel_xfid_candidate_c/runner.py").read_bytes()
    assert (repo / "infra/kaggle/kernel_fd08_formal/runner_base.py").read_bytes() == (
        repo / "infra/kaggle/kernel_xfid_candidate_c/runner.py").read_bytes()


def test_formal_verifier_checks_criteria_bound_source_hashes(tmp_path: Path):
    source = tmp_path / "scripts" / "verifier.py"
    source.parent.mkdir()
    source.write_text("verified source\n")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    inputs = {
        "formal_verifier": {
            "path": "scripts/verifier.py", "sha256": digest, "location": "source_repo",
        },
    }
    assert verify_source_inputs(inputs, root=tmp_path) == {"formal_verifier": digest}
    source.write_text("changed source\n")
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        verify_source_inputs(inputs, root=tmp_path)
