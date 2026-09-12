from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from math import isfinite
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class CfdEvaluation:
    source: str
    latest: dict[str, float]
    drag_coefficient: float | None
    lift_coefficient: float | None
    downforce_coefficient: float | None
    efficiency: float | None
    efficiency_constraint: float | None

    @property
    def ok(self) -> bool:
        return self.drag_coefficient is not None and self.downforce_coefficient is not None

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        data["ok"] = self.ok
        return data


def evaluate_openfoam_case(case_dir: Path, efficiency_min: float) -> CfdEvaluation:
    force_file = _find_force_coeffs(case_dir)
    values = _read_latest_force_coeffs(force_file)
    cd = values.get("Cd")
    cl = values.get("Cl")
    downforce = -cl if cl is not None else None
    efficiency = None
    efficiency_constraint = None
    if cd is not None and downforce is not None and abs(cd) > 1.0e-12:
        efficiency = downforce / cd
        efficiency_constraint = efficiency_min * cd - downforce
    return CfdEvaluation(
        source=str(force_file),
        latest=values,
        drag_coefficient=cd,
        lift_coefficient=cl,
        downforce_coefficient=downforce,
        efficiency=efficiency,
        efficiency_constraint=efficiency_constraint,
    )


def write_cfd_summary(case_dir: Path, efficiency_min: float) -> Path:
    evaluation = evaluate_openfoam_case(case_dir, efficiency_min)
    path = case_dir / "cfd_summary.json"
    path.write_text(json.dumps(evaluation.to_dict(), indent=2), encoding="utf-8")
    return path


def _find_force_coeffs(case_dir: Path) -> Path:
    files = sorted(case_dir.glob("postProcessing/forceCoeffs*/**/forceCoeffs.dat"))
    files.extend(sorted(case_dir.glob("postProcessing/forceCoeffs*/**/coefficient.dat")))
    if not files:
        raise FileNotFoundError(f"No force coefficient file found under {case_dir / 'postProcessing'}")
    return sorted(files)[-1]


def _read_latest_force_coeffs(path: Path) -> dict[str, float]:
    header: list[str] = []
    latest: list[str] | None = None
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            header = stripped.lstrip("#").split()
            continue
        latest = stripped.split()
    if latest is None:
        raise ValueError(f"No data rows found in {path}")
    if not header:
        header = [f"col_{index}" for index in range(len(latest))]
    return {name: float(value) for name, value in zip(header, latest)}


# ---------------------------------------------------------------------------
# Stage V qualification (docs/problem_resolution_plan_2026_09.md, section C7).
#
# Body-fitted Stage V runs are currently accepted as a reference the moment they finish and
# write a force file. That is not enough: every existing run fails one checkMesh check and
# every run completes a fixed 500-iteration cap with no declared convergence criterion. The
# functions below turn "the case finished" into "the case is a qualified reference": a hard
# checkMesh gate, an explicit residualControl-based convergence gate, and a force-history
# stationarity gate, all against thresholds fixed here -- before any new run is looked at --
# so they cannot be tuned to make a particular result pass.
# ---------------------------------------------------------------------------

STAGE_V_QUALIFICATION_PROFILE_V1: dict[str, Any] = {
    "profile_id": "stage_v_qualification_v1",
    "check_mesh": {
        # Any failed checkMesh check is disqualifying UNLESS its name starts with one of these
        # markers, in which case it is judged by the numeric bounds below instead of an
        # automatic fail. Chosen because snappyHexMesh's "Concave cells (using face planes)"
        # check is known (from work/stage_sv_laminar and work/stage_sv_demo, all six existing
        # cases) to fire on a shrinking-with-refinement minority of near-surface polyhedral
        # cells, historically 1.3%-5.2% of total cells, while every other check (closed
        # boundaries, non-negative volumes, face orientation, aspect ratio, skewness, ...)
        # passed cleanly. This profile is fixed before generating or looking at any new run.
        "allowed_failed_check_markers": ["Concave cells"],
        "concave_cell_fraction_max": 0.08,
        "concave_face_max_angle_deg_max": 170.0,
    },
    "force_stationarity": {
        # Fraction (and floor) of the recorded force-history rows treated as the "final window"
        # a response must be flat over.
        "window_fraction": 0.25,
        "window_min_rows": 20,
        # Which bound each response is judged by is fixed per response identity, not inferred
        # from a single run's incidental magnitude: Cd is an O(1) well-scaled coefficient
        # (relative bound is meaningful); downforce is a near-zero side coefficient by physical
        # construction on these candidates (observed 0.013-0.045, the same order as its own
        # run-to-run variation), so a relative bound on it is meaningless and it always uses
        # the pre-registered absolute Q_scale instead, per plan section 6.3.
        "response_bound_kind": {"Cd": "relative", "downforce": "absolute"},
        "relative_drift_max": 0.01,
        "relative_std_max": 0.01,
        "absolute_drift_max": 1.0e-3,
        "absolute_std_max": 1.0e-3,
    },
    "grid_convergence": {
        # Same fixed per-response bound choice as force_stationarity, but looser: this judges a
        # genuine physical change between two mesh resolutions, not iteration-to-iteration noise
        # within one converged run.
        "response_bound_kind": {"Cd": "relative", "downforce": "absolute"},
        "relative_change_max": 0.02,
        "absolute_change_max": 5.0e-3,
    },
}

_CHECK_MESH_FAILED_LINE = re.compile(r"^\s*\*{2,}\s*(.+?)\s*$")
_CHECK_MESH_TOTAL_CELLS = re.compile(r"^\s*cells:\s+(\d+)\s*$", re.MULTILINE)
_CHECK_MESH_FAILED_SUMMARY = re.compile(r"Failed (\d+) mesh checks?\.")
_CHECK_MESH_CONCAVE_CELLS = re.compile(r"Concave cells.*?number of cells:\s*(\d+)")
_CHECK_MESH_CONCAVE_ANGLE = re.compile(r"Max concave angle\s*=\s*([\d.eE+-]+)\s*degrees")

_SOLVER_TIME_HEADER = re.compile(r"^Time\s*=\s*(\d+)\s*$")
_SOLVER_RESIDUAL_LINE = re.compile(
    r"Solving for (\w+),\s*Initial residual\s*=\s*([^,]+),\s*Final residual\s*=\s*([^,]+),\s*No Iterations\s*(\d+)"
)
_SOLVER_CONTINUITY_LINE = re.compile(
    r"time step continuity errors\s*:\s*sum local\s*=\s*([^,]+),\s*global\s*=\s*([^,]+),\s*cumulative\s*=\s*([^\s]+)"
)
_SOLVER_CONVERGED_LINE = re.compile(r"[Ss]olution converged in (\d+) iterations")
_SOLVER_FATAL_SUBSTRINGS = ("foam fatal", "segmentation fault", "mpi_abort")
# OpenFOAM prints this startup banner on every run (FOAM_SIGFPE trapping is always enabled); it
# must not be mistaken for an actual floating point exception crash later in the same log.
_FPE_STARTUP_BANNER = re.compile(
    r"^\s*trapFpe:\s+floating point exception trapping enabled\s+\(foam_sigfpe\)\.\s*$",
    re.IGNORECASE,
)
_FPE_FAILURE_PATTERN = re.compile(r"\b(?:floating point exception|foam_sigfpe|sigfpe)\b", re.IGNORECASE)


def _solver_fatal_patterns(text: str) -> list[str]:
    lower = text.lower()
    found = [pattern for pattern in _SOLVER_FATAL_SUBSTRINGS if pattern in lower]
    for line in text.splitlines():
        if _FPE_STARTUP_BANNER.match(line):
            continue
        if _FPE_FAILURE_PATTERN.search(line):
            found.append("floating point exception")
            break
    return found


def parse_check_mesh_log(text: str) -> dict[str, Any]:
    """Parse a ``checkMesh -allGeometry -allTopology`` log into a structured summary.

    Every ``***``-prefixed line is a failed check (checkMesh's own convention); everything else
    is informational. Concave-cell count/fraction and the reported max concave-face angle are
    pulled out explicitly because they are the one failure this profile may waive.
    """

    total_cells_match = _CHECK_MESH_TOTAL_CELLS.search(text)
    total_cells = int(total_cells_match.group(1)) if total_cells_match else None

    failed_lines = [
        match.group(1)
        for line in text.splitlines()
        if (match := _CHECK_MESH_FAILED_LINE.match(line)) is not None
    ]

    summary_match = _CHECK_MESH_FAILED_SUMMARY.search(text)
    reported_failed_count = int(summary_match.group(1)) if summary_match else 0
    mesh_ok = reported_failed_count == 0 and bool(re.search(r"Mesh OK\.", text))

    concave_match = _CHECK_MESH_CONCAVE_CELLS.search(text)
    concave_cell_count = int(concave_match.group(1)) if concave_match else None
    concave_cell_fraction = (
        concave_cell_count / total_cells if concave_cell_count is not None and total_cells else None
    )
    angle_match = _CHECK_MESH_CONCAVE_ANGLE.search(text)
    concave_face_max_angle_deg = float(angle_match.group(1)) if angle_match else None

    return {
        "total_cells": total_cells,
        "reported_failed_check_count": reported_failed_count,
        "failed_check_lines": failed_lines,
        "mesh_ok": mesh_ok,
        "concave_cell_count": concave_cell_count,
        "concave_cell_fraction": concave_cell_fraction,
        "concave_face_max_angle_deg": concave_face_max_angle_deg,
        "ran_to_completion": bool(re.search(r"^End\s*$", text, re.MULTILINE)),
    }


def evaluate_check_mesh(text: str, profile: Mapping[str, Any] = STAGE_V_QUALIFICATION_PROFILE_V1) -> dict[str, Any]:
    """Apply the checkMesh hard gate: fail closed unless every failure matches the waived marker
    and stays inside its pre-registered numeric bound."""

    rules = profile["check_mesh"]
    summary = parse_check_mesh_log(text)
    if not summary["ran_to_completion"]:
        return {**summary, "status": "fail", "qualified": False, "reasons": ["check_mesh_did_not_complete"]}

    reasons: list[str] = []
    markers = rules["allowed_failed_check_markers"]
    for line in summary["failed_check_lines"]:
        if not any(line.startswith(marker) for marker in markers):
            reasons.append(f"unwaived_failed_check:{line}")

    if summary["failed_check_lines"]:
        if summary["concave_cell_fraction"] is None:
            reasons.append("concave_cell_fraction_unavailable")
        elif summary["concave_cell_fraction"] > rules["concave_cell_fraction_max"]:
            reasons.append(
                f"concave_cell_fraction_{summary['concave_cell_fraction']:.4f}_exceeds_"
                f"{rules['concave_cell_fraction_max']}"
            )
        if summary["concave_face_max_angle_deg"] is not None and (
            summary["concave_face_max_angle_deg"] > rules["concave_face_max_angle_deg_max"]
        ):
            reasons.append(
                f"concave_face_max_angle_{summary['concave_face_max_angle_deg']:.1f}deg_exceeds_"
                f"{rules['concave_face_max_angle_deg_max']}"
            )

    return {**summary, "status": "fail" if reasons else "pass", "qualified": not reasons, "reasons": reasons}


def parse_simple_foam_log(text: str) -> dict[str, Any]:
    """Parse an OpenFOAM ``simpleFoam`` log into a per-iteration residual/continuity history.

    Records, per iteration: the initial residual of every solved field and the continuity
    error, plus whether the run ended via a declared ``residualControl`` convergence (OpenFOAM
    prints ``solution converged in N iterations`` and stops) or by exhausting ``endTime``.
    """

    history: list[dict[str, Any]] = []
    current_iteration: int | None = None
    current_residuals: dict[str, float] = {}
    current_continuity: dict[str, float] | None = None

    def flush() -> None:
        if current_iteration is not None and (current_residuals or current_continuity):
            history.append(
                {
                    "iteration": current_iteration,
                    "initial_residuals": dict(current_residuals),
                    "continuity": dict(current_continuity) if current_continuity else None,
                }
            )

    for line in text.splitlines():
        time_match = _SOLVER_TIME_HEADER.match(line.strip())
        if time_match:
            flush()
            current_iteration = int(time_match.group(1))
            current_residuals = {}
            current_continuity = None
            continue
        residual_match = _SOLVER_RESIDUAL_LINE.search(line)
        if residual_match and current_iteration is not None:
            field, initial, _final, _iters = residual_match.groups()
            current_residuals[field] = float(initial)
            continue
        continuity_match = _SOLVER_CONTINUITY_LINE.search(line)
        if continuity_match and current_iteration is not None:
            local, glob, cumulative = continuity_match.groups()
            current_continuity = {
                "sum_local": float(local),
                "global": float(glob),
                "cumulative": float(cumulative),
            }
    flush()

    converged_match = _SOLVER_CONVERGED_LINE.search(text)
    fatal = _solver_fatal_patterns(text)
    end_marker = bool(re.search(r"^End\s*$", text, re.MULTILINE))
    no_criteria = "no convergence criteria found" in text.lower()

    last = history[-1] if history else None
    return {
        "iteration_count": last["iteration"] if last else 0,
        "residual_history": history,
        "final_residuals": last["initial_residuals"] if last else {},
        "final_continuity": last["continuity"] if last else None,
        "residual_control_converged_at_iteration": (
            int(converged_match.group(1)) if converged_match else None
        ),
        "no_convergence_criteria_declared": no_criteria,
        "fatal_patterns": fatal,
        "end_marker": end_marker,
    }


def evaluate_solver_convergence(
    text: str, profile: Mapping[str, Any] = STAGE_V_QUALIFICATION_PROFILE_V1
) -> dict[str, Any]:
    """Apply the residualControl gate: completing ``endTime`` steps is never, by itself,
    ``solver_converged=True``. Only an explicit ``solution converged in N iterations`` message
    (which OpenFOAM only prints once every residualControl threshold is met) qualifies."""

    parsed = parse_simple_foam_log(text)
    reasons: list[str] = []
    if parsed["fatal_patterns"]:
        reasons.append(f"fatal_log_pattern:{parsed['fatal_patterns']}")
    if not parsed["end_marker"]:
        reasons.append("missing_solver_end_marker")
    if not parsed["residual_history"]:
        reasons.append("no_residual_history_parsed")

    solver_converged = parsed["residual_control_converged_at_iteration"] is not None
    termination_reason = (
        "residual_control_met" if solver_converged else "iteration_cap" if parsed["end_marker"] else "incomplete"
    )
    if not solver_converged and not reasons:
        reasons.append("iteration_cap_without_residual_control_convergence")

    return {
        **parsed,
        "solver_converged": solver_converged,
        "termination_reason": termination_reason,
        "status": "pass" if solver_converged and not reasons else "fail",
        "qualified": solver_converged and not reasons,
        "reasons": reasons,
    }


def read_force_coefficient_history(case_dir: Path) -> dict[str, Any]:
    """Read every row (not just the latest) of the case's forceCoeffs/coefficient output."""

    force_file = _find_force_coeffs(case_dir)
    header: list[str] = []
    rows: list[list[float]] = []
    for line in force_file.read_text(encoding="utf-8", errors="ignore").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            candidate = stripped.lstrip("#").split()
            if candidate and candidate[0].lower() == "time":
                header = candidate
            continue
        parts = stripped.split()
        if not header:
            header = [f"col_{index}" for index in range(len(parts))]
        rows.append([float(value) for value in parts])

    columns: dict[str, list[float]] = {name: [] for name in header}
    for row in rows:
        for name, value in zip(header, row):
            columns[name].append(value)

    downforce = [-value for value in columns["Cl"]] if "Cl" in columns else None
    return {
        "source": str(force_file),
        "row_count": len(rows),
        "columns": columns,
        "drag_coefficient_history": columns.get("Cd"),
        "downforce_coefficient_history": downforce,
    }


def _window_stats(values: Sequence[float], window_fraction: float, window_min_rows: int) -> dict[str, Any] | None:
    if len(values) < window_min_rows:
        return None
    window_size = max(window_min_rows, int(round(len(values) * window_fraction)))
    window_size = min(window_size, len(values))
    window = values[-window_size:]
    n = len(window)
    mean = sum(window) / n
    variance = sum((value - mean) ** 2 for value in window) / n
    std = variance**0.5
    x_mean = (n - 1) / 2.0
    numerator = sum((index - x_mean) * (value - mean) for index, value in enumerate(window))
    denominator = sum((index - x_mean) ** 2 for index in range(n))
    slope = numerator / denominator if denominator else 0.0
    return {
        "window_size": n,
        "mean": mean,
        "std": std,
        "slope_per_iteration": slope,
        "window_drift": slope * (n - 1),
    }


def evaluate_force_stationarity(
    history: Mapping[str, Any], profile: Mapping[str, Any] = STAGE_V_QUALIFICATION_PROFILE_V1
) -> dict[str, Any]:
    """Fail a run whose force coefficients are still drifting in their final window.

    Records mean/std/slope over the final window for each response and applies a relative
    bound to well-scaled responses (drag) and a pre-registered absolute bound to near-zero
    responses (downforce), per plan section 6.3.
    """

    rules = profile["force_stationarity"]
    responses = {"Cd": history.get("drag_coefficient_history"), "downforce": history.get("downforce_coefficient_history")}
    results: dict[str, Any] = {}
    for name, values in responses.items():
        if not values:
            results[name] = {"status": "fail", "reason": "missing_history"}
            continue
        stats = _window_stats(values, rules["window_fraction"], rules["window_min_rows"])
        if stats is None:
            results[name] = {"status": "fail", "reason": "insufficient_history", "available_rows": len(values)}
            continue
        bound_kind = rules["response_bound_kind"][name]
        if bound_kind == "absolute":
            drift_ok = abs(stats["window_drift"]) <= rules["absolute_drift_max"]
            std_ok = stats["std"] <= rules["absolute_std_max"]
        else:
            scale = max(abs(stats["mean"]), 1.0e-12)
            drift_ok = abs(stats["window_drift"]) / scale <= rules["relative_drift_max"]
            std_ok = stats["std"] / scale <= rules["relative_std_max"]
        results[name] = {
            **stats,
            "bound_kind": bound_kind,
            "status": "pass" if (drift_ok and std_ok) else "fail",
        }

    passed = bool(results) and all(result["status"] == "pass" for result in results.values())
    return {"status": "pass" if passed else "fail", "qualified": passed, "responses": results}


@dataclass(frozen=True)
class StageVQualification:
    case_dir: str
    profile_id: str
    check_mesh: dict[str, Any]
    solver: dict[str, Any]
    force_stationarity: dict[str, Any]
    qualified: bool
    reasons: list[str]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def qualify_stage_v_case(
    case_dir: Path, profile: Mapping[str, Any] = STAGE_V_QUALIFICATION_PROFILE_V1
) -> StageVQualification:
    """Run every Stage V hard gate (checkMesh, residualControl convergence, force stationarity)
    against one already-executed body-fitted case and record the result. This is the
    fail-closed replacement for treating "the run produced a force file" as reference-grade."""

    check_mesh_log = (case_dir / "log.checkMesh").read_text(encoding="utf-8")
    solver_log = (case_dir / "log.simpleFoam").read_text(encoding="utf-8")

    check_mesh = evaluate_check_mesh(check_mesh_log, profile)
    solver = evaluate_solver_convergence(solver_log, profile)
    history = read_force_coefficient_history(case_dir)
    force_stationarity = evaluate_force_stationarity(history, profile)
    force_stationarity["history"] = history

    reasons = []
    if not check_mesh["qualified"]:
        reasons.append("check_mesh_failed")
    if not solver["qualified"]:
        reasons.append("solver_not_converged")
    if not force_stationarity["qualified"]:
        reasons.append("force_not_stationary")

    return StageVQualification(
        case_dir=str(case_dir),
        profile_id=str(profile["profile_id"]),
        check_mesh=check_mesh,
        solver=solver,
        force_stationarity=force_stationarity,
        qualified=not reasons,
        reasons=reasons,
    )


def write_stage_v_qualification(
    case_dir: Path, profile: Mapping[str, Any] = STAGE_V_QUALIFICATION_PROFILE_V1
) -> Path:
    """Qualify a case and save the full checkMesh/residual/force evidence as a case artifact so
    a later reader can re-judge the run without re-parsing raw solver logs."""

    qualification = qualify_stage_v_case(case_dir, profile)
    path = case_dir / "stage_v_qualification.json"
    path.write_text(json.dumps(qualification.to_dict(), indent=2), encoding="utf-8")
    return path


def evaluate_stage_v_grid_convergence(
    values_by_grid: Mapping[str, float | None],
    grid_order: Sequence[str],
    response_id: str,
    profile: Mapping[str, Any] = STAGE_V_QUALIFICATION_PROFILE_V1,
) -> dict[str, Any]:
    """Compare a target response across successive grid levels (Gate 3: "V1->V2 within
    tolerance, else add V3"). ``response_id`` (e.g. "Cd" or "downforce") selects the bound kind
    fixed for that response in the profile; near-zero responses (downforce) use a pre-registered
    absolute change bound instead of a relative one, regardless of the values seen this run."""

    rules = profile["grid_convergence"]
    bound_kind = rules["response_bound_kind"][response_id]
    ordered = [grid for grid in grid_order if grid in values_by_grid and values_by_grid[grid] is not None]
    transitions: dict[str, Any] = {}
    for previous, current in zip(ordered, ordered[1:]):
        a = values_by_grid[previous]
        b = values_by_grid[current]
        assert a is not None and b is not None
        change = abs(b - a)
        if bound_kind == "absolute":
            ok = change <= rules["absolute_change_max"]
            observed = change
        else:
            scale = max(abs(a), abs(b), 1.0e-12)
            ok = (change / scale) <= rules["relative_change_max"]
            observed = change / scale
        transitions[f"{previous}->{current}"] = {
            "status": "pass" if ok else "fail",
            "bound_kind": bound_kind,
            "observed": observed,
            "value_previous": a,
            "value_current": b,
        }
    converged = bool(transitions) and all(t["status"] == "pass" for t in transitions.values())
    return {
        "grid_order": list(ordered),
        "values": {grid: values_by_grid.get(grid) for grid in grid_order},
        "transitions": transitions,
        "converged": converged,
    }
