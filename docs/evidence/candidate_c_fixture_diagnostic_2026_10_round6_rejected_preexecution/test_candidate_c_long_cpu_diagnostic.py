import copy
import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
RUNNER_PATH = ROOT / "scripts/verify_candidate_c_grid_sdf_long_cpu_diagnostic.py"
PLAN_PATH = ROOT / "docs/evidence/candidate_c_fixture_diagnostic_2026_10_round6/plan.json"
SPEC = importlib.util.spec_from_file_location("candidate_c_long_cpu", RUNNER_PATH)
RUNNER = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(RUNNER)


def _plan():
    return json.loads(PLAN_PATH.read_text(encoding="utf-8"))


def _row(fixture, mode, time_value):
    row = {
        "fixture": fixture,
        "mode": mode,
        "step": str(round(time_value * 4)),
        "t_u_over_l": str(time_value),
        "phi_sha256": "a" * 64,
        "phi_margin_m": "0.15",
        "candidate_closure_n": "0",
        "ground_closure_n": "0",
        "combined_closure_n": "0",
        "flux_x_minus_kg_s": "-1",
        "flux_x_plus_kg_s": "1",
        "flux_y_minus_kg_s": "0",
        "flux_y_plus_kg_s": "0",
        "flux_z_minus_kg_s": "0",
        "flux_z_plus_kg_s": "0",
        "net_outward_kg_s": "0",
        "integrated_divergence_kg_s": "100",
        "divergence_boundary_difference_kg_s": "100",
        "ground_velocity_matches_freestream": "true",
        "ground_body_has_no_normal_velocity": "true",
        "ground_velocity_x_solver": "1",
        "ground_velocity_y_solver": "0",
        "ground_velocity_z_solver": "0",
        "ground_wall_normal_error_max_solver": "0.2",
        "ground_wall_tangent_error_max_solver": "0.4",
        "ground_wall_face_samples": "100",
        "finite_u": "true",
        "finite_p": "true",
    }
    for group in RUNNER.GROUPS:
        for axis, scale in zip(RUNNER.AXES, (1.0, 2.0, 3.0)):
            pressure = time_value * scale
            viscous = -0.25 * scale
            for kind, value in (
                ("pressure", pressure),
                ("viscous", viscous),
                ("total", pressure + viscous),
            ):
                row[f"{group}_{kind}_f{axis}_n"] = str(value)
    return row


def _write_rows(path, rows):
    import csv

    keys = list(rows[0])
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=keys)
        writer.writeheader()
        writer.writerows(rows)


def _synthetic_rows():
    return [
        _row(fixture, mode, time_value)
        for fixture in RUNNER.FIXTURES
        for mode in RUNNER.MODES
        for time_value in (4.0, 6.0, 8.0, 10.0, 11.0)
    ]


def test_registered_contract_pins_matrix_outer_operator_and_unresolved_physics():
    plan = _plan()
    RUNNER._expected_configuration(plan)
    assert plan["fixtures"][1]["half_extents_m"][1] == 0.025
    assert plan["fixtures"][2]["half_extents_m"][1] == 0.05
    assert plan["operator"]["normal_floor"] == 0.25
    assert "outer simulation.body" in plan["operator"]["solver_body_composition"]
    assert "UNRESOLVED" in plan["unresolved_physical_contracts"]["mass_acceptance"]
    assert all(value is False for value in plan["flags"].values())


def test_exact_window_means_and_integrity_do_not_turn_diagnostics_into_qualification(tmp_path):
    rows = _synthetic_rows()
    path = tmp_path / "raw.csv"
    _write_rows(path, rows)
    result = RUNNER.verify_raw_history(path, _plan())
    arm = result["arms"]["plate_1cell/candidate_c"]
    assert arm["forces_n"]["whole"]["candidate"]["total"][0] == pytest.approx(7.25)
    assert arm["relative_half_window_drifts_report_only"]["candidate_total_fx"] > 0.0
    assert arm["mean_net_outward_kg_s"]["divergence_boundary_difference_kg_s"] == pytest.approx(100.0)
    assert result["status"] == "diagnostic_data_integrity_ok"
    assert "mass-conservation qualification" in result["scope"]
    assert all(value is False for value in result["qualification_flags"].values())


def test_wrong_fixture_matrix_missing_exact_window_or_force_closure_fails_closed(tmp_path):
    plan = _plan()
    wrong_matrix = copy.deepcopy(plan)
    wrong_matrix["fixtures"].pop()
    with pytest.raises(ValueError, match="fixture matrix"):
        RUNNER._expected_configuration(wrong_matrix)

    rows = _synthetic_rows()
    rows = [row for row in rows if not (row["fixture"] == "sphere" and row["mode"] == "native" and row["t_u_over_l"] in ("4.0", "6.0"))]
    missing_bracket = tmp_path / "missing.csv"
    _write_rows(missing_bracket, rows)
    with pytest.raises(ValueError, match="strictly increasing|bracket"):
        RUNNER.verify_raw_history(missing_bracket, plan)

    rows = _synthetic_rows()
    rows[0]["candidate_total_fx_n"] = "999"
    bad_closure = tmp_path / "closure.csv"
    _write_rows(bad_closure, rows)
    with pytest.raises(ValueError, match="closure"):
        RUNNER.verify_raw_history(bad_closure, plan)


def test_input_flux_roundoff_and_nonfinite_values_are_detected(tmp_path):
    rows = _synthetic_rows()
    rows[0]["net_outward_kg_s"] = "1"
    bad_flux = tmp_path / "flux.csv"
    _write_rows(bad_flux, rows)
    with pytest.raises(ValueError, match="flux sum mismatch"):
        RUNNER.verify_raw_history(bad_flux, _plan())

    rows = _synthetic_rows()
    rows[0]["integrated_divergence_kg_s"] = "nan"
    bad_divergence = tmp_path / "divergence.csv"
    _write_rows(bad_divergence, rows)
    with pytest.raises(ValueError, match="non-finite"):
        RUNNER.verify_raw_history(bad_divergence, _plan())
