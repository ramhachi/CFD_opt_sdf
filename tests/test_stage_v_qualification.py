"""Tests for the Stage V qualification gates (docs/problem_resolution_plan_2026_09.md, C7).

These exercise the fail-closed rule the plan requires: a body-fitted run that merely produces
a force file must not be treated as a qualified reference. Real historical logs from
work/stage_sv_laminar/case_a_coarse (predating the residualControl fix) are used as one of the
fixtures precisely because they are known to hit the 500-iteration cap without ever printing a
declared-convergence message.
"""

from __future__ import annotations

from pathlib import Path

from cfd_sdf import cfd

REAL_CASE = Path(__file__).resolve().parent.parent / "work" / "stage_sv_laminar" / "case_a_coarse"

_CHECK_MESH_HEADER = """Check mesh...
Time = 0

Mesh stats
    points:           100
    faces:            300
    internal faces:   250
    cells:            1000
    faces per cell:   6

Checking topology...
    Boundary definition OK.
"""


def _check_mesh_log(*, failed_lines: list[str], failed_count: int) -> str:
    body = "\n".join(f"    ***{line}" for line in failed_lines)
    return (
        _CHECK_MESH_HEADER
        + body
        + f"\n\nFailed {failed_count} mesh checks.\n\nEnd\n"
        if failed_lines
        else _CHECK_MESH_HEADER + "\nMesh OK.\n\nEnd\n"
    )


def _coefficient_dat(cd_values: list[float], downforce_values: list[float]) -> str:
    lines = ["# Time\tCd\tCl"]
    for index, (cd, downforce) in enumerate(zip(cd_values, downforce_values), start=1):
        lines.append(f"{index}\t{cd:.10g}\t{-downforce:.10g}")
    return "\n".join(lines) + "\n"


def _write_case(
    case_dir: Path,
    *,
    check_mesh_log: str,
    solver_log: str,
    cd_values: list[float],
    downforce_values: list[float],
) -> None:
    (case_dir / "postProcessing" / "forceCoeffs" / "0").mkdir(parents=True)
    (case_dir / "log.checkMesh").write_text(check_mesh_log, encoding="utf-8")
    (case_dir / "log.simpleFoam").write_text(solver_log, encoding="utf-8")
    (case_dir / "postProcessing" / "forceCoeffs" / "0" / "coefficient.dat").write_text(
        _coefficient_dat(cd_values, downforce_values), encoding="utf-8"
    )


def _converged_solver_log(n_iterations: int) -> str:
    lines = ["SIMPLE: residualControl active."]
    for i in range(1, n_iterations + 1):
        residual = 1.0 / i
        lines += [
            f"Time = {i}",
            f"smoothSolver:  Solving for Ux, Initial residual = {residual}, Final residual = {residual/10}, No Iterations 2",
            f"GAMG:  Solving for p, Initial residual = {residual}, Final residual = {residual/10}, No Iterations 4",
            f"time step continuity errors : sum local = {residual}, global = {residual/2}, cumulative = {residual/2}",
        ]
    lines += [f"SIMPLE solution converged in {n_iterations} iterations", "End"]
    return "\n".join(lines) + "\n"


def test_real_historical_run_without_residual_control_is_not_called_converged() -> None:
    """A run that completes the 500-step endTime with no declared convergence criterion (the
    situation for every existing Stage V case) must not qualify as solver_converged."""

    text = (REAL_CASE / "log.simpleFoam").read_text(encoding="utf-8")
    result = cfd.evaluate_solver_convergence(text)
    assert result["termination_reason"] == "iteration_cap"
    assert result["solver_converged"] is False
    assert result["qualified"] is False
    assert "iteration_cap_without_residual_control_convergence" in result["reasons"]


def test_solver_log_with_declared_convergence_message_qualifies() -> None:
    text = _converged_solver_log(30)
    result = cfd.evaluate_solver_convergence(text)
    assert result["termination_reason"] == "residual_control_met"
    assert result["solver_converged"] is True
    assert result["qualified"] is True
    assert result["iteration_count"] == 30


def test_check_mesh_failing_an_unwaived_check_fails_qualification() -> None:
    text = _check_mesh_log(
        failed_lines=["Wrong-oriented face found, number of faces: 12"], failed_count=1
    )
    result = cfd.evaluate_check_mesh(text)
    assert result["qualified"] is False
    assert any("unwaived_failed_check" in reason for reason in result["reasons"])


def test_check_mesh_waived_concave_cells_within_bound_passes() -> None:
    # 1000 total cells (from the shared header); 50 concave cells is 5%, under the
    # pre-registered 8% cap.
    text = _check_mesh_log(
        failed_lines=["Concave cells (using face planes) found, number of cells: 50"],
        failed_count=1,
    )
    result = cfd.evaluate_check_mesh(text)
    assert result["qualified"] is True


def test_check_mesh_waived_marker_over_fraction_bound_still_fails() -> None:
    # 950/1000 = 95% concave cells: far past the 8% cap, so the waiver does not apply.
    text = _check_mesh_log(
        failed_lines=["Concave cells (using face planes) found, number of cells: 950"],
        failed_count=1,
    )
    result = cfd.evaluate_check_mesh(text)
    assert result["qualified"] is False
    assert any("concave_cell_fraction" in reason for reason in result["reasons"])


def test_drifting_force_history_fails_stationarity(tmp_path: Path) -> None:
    case_dir = tmp_path / "case"
    # Cd steadily increasing right through the recorded window -- never plateaus.
    cd_values = [0.5 + 0.01 * i for i in range(100)]
    downforce_values = [0.02] * 100
    _write_case(
        case_dir,
        check_mesh_log=_check_mesh_log(failed_lines=[], failed_count=0),
        solver_log=_converged_solver_log(100),
        cd_values=cd_values,
        downforce_values=downforce_values,
    )
    qualification = cfd.qualify_stage_v_case(case_dir)
    assert qualification.force_stationarity["qualified"] is False
    assert qualification.qualified is False
    assert "force_not_stationary" in qualification.reasons


def test_flat_force_history_is_stationary_and_case_fully_qualifies(tmp_path: Path) -> None:
    case_dir = tmp_path / "case"
    cd_values = [0.9] * 100
    downforce_values = [0.02] * 100
    _write_case(
        case_dir,
        check_mesh_log=_check_mesh_log(failed_lines=[], failed_count=0),
        solver_log=_converged_solver_log(100),
        cd_values=cd_values,
        downforce_values=downforce_values,
    )
    qualification = cfd.qualify_stage_v_case(case_dir)
    assert qualification.check_mesh["qualified"] is True
    assert qualification.solver["qualified"] is True
    assert qualification.force_stationarity["qualified"] is True
    assert qualification.qualified is True
    assert qualification.reasons == []


def test_write_stage_v_qualification_saves_full_evidence_artifact(tmp_path: Path) -> None:
    case_dir = tmp_path / "case"
    _write_case(
        case_dir,
        check_mesh_log=_check_mesh_log(failed_lines=[], failed_count=0),
        solver_log=_converged_solver_log(40),
        cd_values=[0.9] * 40,
        downforce_values=[0.02] * 40,
    )
    path = cfd.write_stage_v_qualification(case_dir)
    assert path == case_dir / "stage_v_qualification.json"
    import json

    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["qualified"] is True
    # A later reader must be able to re-judge without re-parsing raw solver logs.
    assert saved["solver"]["residual_history"]
    assert saved["force_stationarity"]["history"]["drag_coefficient_history"]
    assert saved["check_mesh"]["total_cells"] == 1000


def test_grid_convergence_uses_absolute_tolerance_for_downforce() -> None:
    values = {"V0": 0.013, "V1": 0.014, "V2": 0.0145}
    result = cfd.evaluate_stage_v_grid_convergence(values, ["V0", "V1", "V2"], "downforce")
    assert result["transitions"]["V0->V1"]["bound_kind"] == "absolute"
    assert result["converged"] is True


def test_grid_convergence_fails_when_still_moving_past_tolerance() -> None:
    values = {"V0": 0.013, "V1": 0.036, "V2": 0.045}
    result = cfd.evaluate_stage_v_grid_convergence(values, ["V0", "V1", "V2"], "downforce")
    assert result["converged"] is False
    assert result["transitions"]["V1->V2"]["status"] == "fail"


def test_grid_convergence_uses_relative_tolerance_for_drag_regardless_of_magnitude() -> None:
    # Cd values are always well above the old (now-removed) magnitude-based near-zero cutoff,
    # but the point is that the bound kind is fixed by response identity, not inferred.
    values = {"V0": 0.86, "V1": 0.93, "V2": 0.958}
    result = cfd.evaluate_stage_v_grid_convergence(values, ["V0", "V1", "V2"], "Cd")
    assert result["transitions"]["V1->V2"]["bound_kind"] == "relative"
    assert result["converged"] is False  # V0->V1 relative change (~8%) exceeds the 2% cap
