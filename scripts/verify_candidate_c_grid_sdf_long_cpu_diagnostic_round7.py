#!/usr/bin/env python3
"""Run or verify the bounded Candidate C round-7 CPU diagnostic.

Integrity checks are fail-closed. Numerical stationarity, body-flow accuracy,
and mass conservation are reported without acceptance thresholds.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import platform
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "docs/evidence/candidate_c_fixture_diagnostic_2026_10_round7/plan.json"
JOB = ROOT / "scripts/candidate_c_grid_sdf_long_cpu_diagnostic_round7.jl"
MANIFEST = ROOT / "docs/evidence/candidate_c_fixture_diagnostic_2026_10_round7/runner_sources.sha256"
PROJECT = ROOT / "julia/CFDSDFWaterLily"
OUTPUT_ROOT = ROOT / "work/candidate_c_fixture_diagnostic_2026_10_round7"
FIXTURES = ("sphere", "plate_1cell", "plate_2cell", "moving_ground_only")
MODES = ("native", "grid_upstream", "candidate_c")
GROUPS = ("candidate", "ground", "combined")
AXES = ("x", "y", "z")
WINDOWS = ((5.0, 7.5), (7.5, 10.0), (5.0, 10.0))
RUN_TIMEOUT_SECONDS = 3600


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_path(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def _expected_configuration(plan: dict[str, Any]) -> None:
    """Reject criteria edits that change this reviewed fixed diagnostic."""
    runtime = plan["runtime"]
    if (runtime.get("julia_version"), runtime.get("waterlily_version"), runtime.get("precision")) != (
        "1.12.6", "1.8.0", "Float32"
    ):
        raise ValueError("registered Julia/WaterLily/precision identity changed")
    flow = plan["flow"]
    expected_flow = {
        "dimensions_cells": [100, 48, 36],
        "origin_m": [-2.5, -1.2, -0.9],
        "spacing_m": 0.05,
        "solver_length_cells": 16.0,
        "freestream_mps": [1.0, 0.0, 0.0],
        "kinematic_viscosity_solver": 0.2,
        "density_kg_m3": 1.0,
        "target_time_t_u_over_l": 10.0,
        "force_window_t_u_over_l": [5.0, 10.0],
        "stationarity_split_t_u_over_l": 7.5,
        "sample_every_solver_steps": 4,
        "moving_ground": {"plane_z_solver": 8.0, "velocity_solver_units": [1.0, 0.0, 0.0]},
    }
    if any(flow.get(key) != value for key, value in expected_flow.items() if key != "moving_ground") or any(
        flow["moving_ground"].get(key) != value for key, value in expected_flow["moving_ground"].items()
    ):
        raise ValueError("registered flow/time/moving-ground configuration changed")
    grid = plan["canonical_grid_sdf"]
    if grid != {
        "origin_m": [-1.0, -0.8, -0.6],
        "spacing_m": [0.05, 0.05, 0.05],
        "point_shape": [61, 33, 25],
        "outside_value_m": 3.0,
        "minimum_margin_m": 0.15,
        "constructor_absolute_tolerance_m": 1e-6,
        "storage": "Float32",
        "construction": "sample exact analytic SDF at every grid node; negative inside",
    }:
        raise ValueError("registered canonical GridSDF contract changed")
    operator = plan["operator"]
    expected_operator = {
        "identity": "Candidate C moment blend + NormalFloorWaterLilyBody(normal_floor=0.25)",
        "normal_floor": 0.25,
        "transition_width_solver_cells": 1.1444091796875e-4,
        "mu1": "raw WaterLily mu1 and wrapped body normal; unchanged",
    }
    if any(operator.get(key) != value for key, value in expected_operator.items()):
        raise ValueError("registered composite Candidate C operator changed")
    expected_fixtures = [
        {"id": "sphere", "shape": "sphere", "center_m": [0.0, 0.0, -0.2], "half_extents_m": [0.25, 0.25, 0.25]},
        {"id": "plate_1cell", "shape": "box", "center_m": [0.0, 0.0, -0.2], "half_extents_m": [0.25, 0.025, 0.25]},
        {"id": "plate_2cell", "shape": "box", "center_m": [0.0, 0.0, -0.2], "half_extents_m": [0.25, 0.05, 0.25]},
        {"id": "moving_ground_only", "shape": "none", "center_m": [0.0, 0.0, -0.2], "half_extents_m": [0.0, 0.0, 0.0]},
    ]
    if len(plan["fixtures"]) != len(expected_fixtures) or any(
        any(actual.get(key) != value for key, value in expected.items())
        for actual, expected in zip(plan["fixtures"], expected_fixtures)
    ):
        raise ValueError("registered sampled analytic fixture matrix changed")
    expected_measurement = {
        "force_units": "body-on-fluid reaction negated once; physical forces in N",
        "force_scale_n_per_solver_unit": 0.0025,
        "mass_flow_units": "kg/s",
        "mass_flow_scale_kg_s_per_solver_velocity_unit": 0.0025,
        "external_face_indices": "normal faces x=2/nx,y=2/ny,z=2/nz; transverse indices 2:n-1 exclude ghost layers",
        "domain_divergence": "sum Float64(u_high)-Float64(u_low) over WaterLily inside(p), then multiply rho*U*h^2; cast operands before subtraction",
        "window_statistic": "endpoint-interpolated trapezoid from raw flushed samples on [5,7.5], [7.5,10], and [5,10]",
        "force_groups": ["candidate-only", "ground-only", "combined solver body"],
        "force_closure": "candidate-only pressure + viscous = total in N; identical arithmetic integrity checks are recorded for ground and combined groups",
        "mass_interpretation": "whole-domain external flux and divergence are integrity diagnostics, not immersed-body mass conservation",
        "wall_velocity": "record declared moving-ground velocity and z-face normal flow; the nearby differently staggered streamwise velocity is report-only and is not a wall-slip measurement; no numeric no-penetration threshold",
        "empty_grid": "moving_ground_only is an all-positive field with no zero level; phi_margin_m=NA and phi_has_zero_level=false",
        "raw_force": "persist raw WaterLily pressure/viscous body-on-fluid solver vectors separately from physical body-force SI columns; verify physical_N = -raw_solver*0.0025 exactly once",
        "stationarity": "report-only; no acceptance threshold",
        "native_vs_gridsdf": "report force differences only; no numerical accuracy threshold",
    }
    if any(plan["measurement"].get(key) != value for key, value in expected_measurement.items()):
        raise ValueError("registered measurement/interpretation contract changed")
    expected_flags = {
        "shape_update_allowed": False,
        "fd_oracle": False,
        "field_gradient": False,
        "reverse": False,
        "optimizer": False,
        "topology": False,
    }
    if plan["flags"] != expected_flags or plan["qualification_flags"] != expected_flags:
        raise ValueError("qualification flags must all remain false in both registered maps")


def _verify_registration(plan_path: Path = PLAN) -> dict[str, Any]:
    raw_plan = plan_path.read_bytes()
    plan_sha = sha256_bytes(raw_plan)
    sidecar = plan_path.with_suffix(".sha256")
    if not sidecar.is_file() or sidecar.read_text().split()[0] != plan_sha:
        raise ValueError("criteria sidecar does not match immutable plan")
    plan = json.loads(raw_plan)
    if plan["immutable"] is not True or plan["registered_before_measurement"] is not True:
        raise ValueError("diagnostic criteria are not preregistered")
    if plan["solver_steps_authorized"] is not False:
        raise ValueError("solver steps must remain unauthorized pending parent review")
    if plan["status"] != "immutable_preregistered_pending_parent_source_review_no_solver_steps_authorized":
        raise ValueError("unexpected round status")
    _expected_configuration(plan)
    if sha256_path(Path(__file__).resolve()) != plan["runner_sha256"]:
        raise ValueError("host runner source hash mismatch")
    if sha256_path(JOB) != plan["job_sha256"]:
        raise ValueError("Julia job source hash mismatch")
    if sha256_path(MANIFEST) != plan["source_manifest_sha256"]:
        raise ValueError("source manifest hash mismatch")
    for line in MANIFEST.read_text(encoding="utf-8").splitlines():
        expected, relative = line.split("  ", 1)
        source = Path(relative[9:]) if relative.startswith("external:") else ROOT / relative
        if not source.is_file() or sha256_path(source) != expected:
            raise ValueError(f"source inventory mismatch: {relative}")
    return plan


def _parse_runtime_record(stdout: str, plan: dict[str, Any]) -> dict[str, Any]:
    prefix = "CANDIDATE_C_LONG_CPU_RUNTIME "
    lines = [line[len(prefix):] for line in stdout.splitlines() if line.startswith(prefix)]
    if len(lines) != 1:
        raise ValueError("expected exactly one observed Julia runtime record")
    fields: dict[str, str] = {}
    for item in lines[0].split():
        key, separator, value = item.partition("=")
        if not separator or not value or key in fields:
            raise ValueError("malformed or duplicate observed runtime field")
        fields[key] = value
    expected_keys = {"julia", "waterlily", "threads", "backend", "precision", "source_sha256", "manifest_sha256"}
    if set(fields) != expected_keys:
        raise ValueError("observed runtime record has missing or unexpected fields")
    runtime = plan["runtime"]
    if fields["julia"] != runtime["julia_version"] or fields["waterlily"] != runtime["waterlily_version"]:
        raise ValueError("observed Julia/WaterLily version differs from the registered runtime")
    if fields["backend"] != "Array" or fields["precision"] != "Float32":
        raise ValueError("observed CPU backend or precision differs from the registered runtime")
    try:
        thread_count = int(fields["threads"])
    except ValueError as exc:
        raise ValueError("observed Julia thread count is not an integer") from exc
    if thread_count < 1:
        raise ValueError("observed Julia thread count must be positive")
    if fields["source_sha256"] != plan["job_sha256"] or fields["manifest_sha256"] != plan["source_manifest_sha256"]:
        raise ValueError("observed Julia runtime record is not bound to the registered job and source manifest")
    return {
        "julia_version": fields["julia"],
        "waterlily_version": fields["waterlily"],
        "threads": thread_count,
        "backend": fields["backend"],
        "precision": fields["precision"],
        "job_sha256": fields["source_sha256"],
        "source_manifest_sha256": fields["manifest_sha256"],
    }


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        if not reader.fieldnames or len(set(reader.fieldnames)) != len(reader.fieldnames):
            raise ValueError("raw history has missing or duplicate column names")
        rows = list(reader)
    if not rows:
        raise ValueError("raw history contains no samples")
    return rows


def _numeric(row: dict[str, str], key: str) -> float:
    value = float(row[key])
    if not math.isfinite(value):
        raise ValueError(f"non-finite {key}")
    return value


def _window_mean(rows: list[dict[str, str]], key: str, start: float, end: float) -> float:
    times = [_numeric(row, "t_u_over_l") for row in rows]
    if times != sorted(times) or len(set(times)) != len(times):
        raise ValueError("raw sample times must be strictly increasing")
    if times[0] > start or times[-1] < end:
        raise ValueError(f"raw samples do not bracket exact [{start},{end}] window")

    def at(target: float) -> float:
        for left, right in zip(rows, rows[1:]):
            t0, t1 = _numeric(left, "t_u_over_l"), _numeric(right, "t_u_over_l")
            if t0 <= target <= t1:
                a, b = _numeric(left, key), _numeric(right, key)
                return a if t1 == t0 else a + (target - t0) / (t1 - t0) * (b - a)
        raise ValueError(f"missing raw interpolation bracket at t={target}")

    interior = [row for row in rows if start < _numeric(row, "t_u_over_l") < end]
    ts = [start, *(_numeric(row, "t_u_over_l") for row in interior), end]
    vs = [at(start), *(_numeric(row, key) for row in interior), at(end)]
    integral = math.fsum((t1 - t0) * (v0 + v1) / 2.0 for t0, t1, v0, v1 in zip(ts, ts[1:], vs, vs[1:]))
    return integral / (end - start)


def _force_fields(group: str) -> tuple[str, ...]:
    return tuple(f"{group}_{kind}_f{axis}_n" for kind in ("pressure", "viscous", "total") for axis in AXES)


def _force_window(rows: list[dict[str, str]], group: str, start: float, end: float) -> dict[str, list[float]]:
    return {
        kind: [_window_mean(rows, f"{group}_{kind}_f{axis}_n", start, end) for axis in AXES]
        for kind in ("pressure", "viscous", "total")
    }


def _relative_drift(first: float, second: float, whole: float) -> float | None:
    denominator = abs(whole)
    return abs(first - second) / denominator if denominator > 0.0 else None


def verify_raw_history(path: Path, plan: dict[str, Any]) -> dict[str, Any]:
    rows = _rows(path)
    grouped: dict[tuple[str, str], list[dict[str, str]]] = {}
    numeric_keys = [
        "step", "t_u_over_l", "candidate_closure_n", "ground_closure_n", "combined_closure_n",
        "flux_x_minus_kg_s", "flux_x_plus_kg_s", "flux_y_minus_kg_s", "flux_y_plus_kg_s",
        "flux_z_minus_kg_s", "flux_z_plus_kg_s", "net_outward_kg_s", "integrated_divergence_kg_s",
        "divergence_boundary_difference_kg_s", "ground_velocity_x_solver", "ground_velocity_y_solver",
        "ground_velocity_z_solver", "ground_wall_normal_error_max_solver",
        "ground_nearby_streamwise_velocity_difference_max_solver", "ground_wall_face_samples",
    ] + [field for group in GROUPS for field in _force_fields(group)] + [
        f"{group}_raw_{kind}_f{axis}_solver"
        for group in GROUPS for kind in ("pressure", "viscous") for axis in AXES
    ]
    for row in rows:
        key = (row["fixture"], row["mode"])
        if key[0] not in FIXTURES or key[1] not in MODES:
            raise ValueError(f"unexpected fixture/mode pair {key}")
        grouped.setdefault(key, []).append(row)
        if row["finite_u"] != "true" or row["finite_p"] != "true":
            raise ValueError(f"non-finite solver field at {key}")
        if row["ground_velocity_matches_freestream"] != "true" or row["ground_body_has_no_normal_velocity"] != "true":
            raise ValueError(f"moving-ground body velocity contract failed at {key}")
        if row["phi_has_zero_level"] not in ("true", "false"):
            raise ValueError(f"invalid interface indicator at {key}")
        has_interface = row["phi_has_zero_level"] == "true"
        if (key[0] != "moving_ground_only") != has_interface:
            raise ValueError(f"unexpected analytic zero-level status at {key}")
        if has_interface:
            margin = _numeric(row, "phi_margin_m")
            if margin < float(plan["canonical_grid_sdf"]["minimum_margin_m"]) - float(plan["canonical_grid_sdf"]["constructor_absolute_tolerance_m"]):
                raise ValueError(f"sampled SDF margin below registered constructor tolerance at {key}")
        elif row["phi_margin_m"] != "NA":
            raise ValueError(f"empty-interface margin must be explicit NA at {key}")
        for name in numeric_keys:
            _numeric(row, name)
        for group in GROUPS:
            for axis in AXES:
                p = _numeric(row, f"{group}_pressure_f{axis}_n")
                v = _numeric(row, f"{group}_viscous_f{axis}_n")
                total = _numeric(row, f"{group}_total_f{axis}_n")
                raw_p = _numeric(row, f"{group}_raw_pressure_f{axis}_solver")
                raw_v = _numeric(row, f"{group}_raw_viscous_f{axis}_solver")
                scale = float(plan["measurement"]["force_scale_n_per_solver_unit"])
                if not math.isclose(p, -raw_p * scale, rel_tol=0.0, abs_tol=1e-12):
                    raise ValueError(f"pressure raw-to-physical sign/scale mismatch at {key}/{group}/{axis}")
                if not math.isclose(v, -raw_v * scale, rel_tol=0.0, abs_tol=1e-12):
                    raise ValueError(f"viscous raw-to-physical sign/scale mismatch at {key}/{group}/{axis}")
                measured_closure = abs(p + v - total)
                reported_closure = _numeric(row, f"{group}_closure_n")
                if not math.isclose(measured_closure, reported_closure, rel_tol=0.0, abs_tol=1e-12):
                    raise ValueError(f"reported pressure/viscous closure mismatch at {key}/{group}/{axis}")
                if measured_closure > 1e-12:
                    raise ValueError(f"pressure/viscous arithmetic closure failed at {key}/{group}/{axis}")
        net = math.fsum(_numeric(row, f"flux_{face}_kg_s") for face in (
            "x_minus", "x_plus", "y_minus", "y_plus", "z_minus", "z_plus"))
        if not math.isclose(net, _numeric(row, "net_outward_kg_s"), rel_tol=0.0, abs_tol=1e-12):
            raise ValueError(f"external-face flux sum mismatch at {key}")
        difference = _numeric(row, "integrated_divergence_kg_s") - net
        if not math.isclose(difference, _numeric(row, "divergence_boundary_difference_kg_s"), rel_tol=0.0, abs_tol=1e-12):
            raise ValueError(f"domain divergence/flux residual mismatch at {key}")
    expected = {(fixture, mode) for fixture in FIXTURES for mode in MODES}
    if set(grouped) != expected:
        raise ValueError(f"missing or duplicate fixture/mode coverage: expected {sorted(expected)}, got {sorted(grouped)}")

    results: dict[str, Any] = {}
    for fixture in FIXTURES:
        fixture_hashes = set()
        fixture_margins = set()
        for mode in MODES:
            arm_rows = grouped[(fixture, mode)]
            times = [_numeric(row, "t_u_over_l") for row in arm_rows]
            if times != sorted(times) or len(set(times)) != len(times):
                raise ValueError(f"sample times are not strictly increasing for {fixture}/{mode}")
            if times[-1] < float(plan["flow"]["target_time_t_u_over_l"]):
                raise ValueError(f"target time not reached for {fixture}/{mode}")
            hashes = {row["phi_sha256"] for row in arm_rows}
            margins = {row["phi_margin_m"] for row in arm_rows}
            if len(hashes) != 1 or len(margins) != 1:
                raise ValueError(f"sampled SDF identity drifts within {fixture}/{mode}")
            fixture_hashes.update(hashes)
            fixture_margins.update(margins)
            window_forces = {
                label: {group: _force_window(arm_rows, group, start, end) for group in GROUPS}
                for label, (start, end) in zip(("first_half", "second_half", "whole"), WINDOWS)
            }
            drifts = {}
            for group in GROUPS:
                for axis in AXES:
                    drifts[f"{group}_total_f{axis}"] = _relative_drift(
                        window_forces["first_half"][group]["total"][AXES.index(axis)],
                        window_forces["second_half"][group]["total"][AXES.index(axis)],
                        window_forces["whole"][group]["total"][AXES.index(axis)],
                    )
            results[f"{fixture}/{mode}"] = {
                "steps_recorded": len(arm_rows),
                "t_reached": times[-1],
                "phi_sha256": arm_rows[0]["phi_sha256"],
                "phi_has_zero_level": arm_rows[0]["phi_has_zero_level"] == "true",
                "phi_margin_m": None if arm_rows[0]["phi_margin_m"] == "NA" else _numeric(arm_rows[0], "phi_margin_m"),
                "forces_n": window_forces,
                "relative_half_window_drifts_report_only": drifts,
                "mean_net_outward_kg_s": {
                    field: _window_mean(arm_rows, field, 5.0, 10.0)
                    for field in ("net_outward_kg_s", "integrated_divergence_kg_s", "divergence_boundary_difference_kg_s")
                },
                "max_ground_wall_normal_error_solver_report_only": max(
                    _numeric(row, "ground_wall_normal_error_max_solver") for row in arm_rows),
                "max_nearby_streamwise_velocity_difference_solver_report_only": max(
                    _numeric(row, "ground_nearby_streamwise_velocity_difference_max_solver") for row in arm_rows),
            }
        if len(fixture_hashes) != 1 or len(fixture_margins) != 1:
            raise ValueError(f"fixture SDF differs between native/upstream/C arms: {fixture}")

    comparisons: dict[str, Any] = {}
    for fixture in FIXTURES:
        native = results[f"{fixture}/native"]["forces_n"]["whole"]["candidate"]["total"]
        upstream = results[f"{fixture}/grid_upstream"]["forces_n"]["whole"]["candidate"]["total"]
        candidate_c = results[f"{fixture}/candidate_c"]["forces_n"]["whole"]["candidate"]["total"]
        comparisons[fixture] = {
            "native_minus_grid_upstream_candidate_force_n_report_only": [a - b for a, b in zip(native, upstream)],
            "grid_upstream_minus_candidate_c_force_n_report_only": [a - b for a, b in zip(upstream, candidate_c)],
        }
    return {
        "status": "diagnostic_data_integrity_ok",
        "scope": "CPU-only bounded primal diagnostic; no stationarity, physical accuracy, or mass-conservation qualification",
        "solver_steps_completed": True,
        "registered_integrity_checks": [
            "all 12 fixture/mode arms present with finite raw fields",
            "every exact [5,7.5], [7.5,10], and [5,10] window is bracketed and independently recomputed from raw samples",
            "pressure plus viscous equals total for candidate-only, ground-only, and combined-body force groups",
            "six physical external-face fluxes sum to reported net outward flux; transverse ghost layers are excluded",
            "Float64-before-subtraction domain divergence residual matches its raw definition",
            "moving-ground body velocity equals freestream and has no normal component",
        ],
        "unresolved_physical_contracts": [
            "no justified no-penetration or moving-wall slip tolerance is registered",
            "no fluid-volume/immersed-boundary mass balance definition or justified acceptance uncertainty is registered",
            "native-versus-sampled GridSDF force differences have no accuracy threshold",
            "the half-window drift is descriptive only and is not a stationarity gate",
        ],
        "force_comparisons_report_only": comparisons,
        "arms": results,
        "qualification_flags": plan["flags"],
    }


def _write_new(path: Path, payload: bytes) -> None:
    if path.exists():
        raise FileExistsError(f"refusing to overwrite artifact: {path}")
    path.write_bytes(payload)


def _error_artifact(run_dir: Path, plan_sha: str, stage: str, detail: str) -> Path:
    error_path = run_dir / "terminal-ERROR.json"
    payload: dict[str, Any] = {
        "status": "ERROR",
        "stage": stage,
        "detail": detail,
        "criteria_sha256": plan_sha,
        "runner_sha256": sha256_path(Path(__file__).resolve()),
        "job_sha256": sha256_path(JOB),
        "partial_artifacts": [
            {"path": str(path.relative_to(ROOT)), "sha256": sha256_path(path)}
            for path in sorted(run_dir.rglob("*")) if path.is_file() and path != error_path
        ],
    }
    _write_new(error_path, (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode())
    return error_path


def _run(plan_path: Path, preflight_only: bool, parent_reviewed: bool, geometry_only: bool = False) -> int:
    plan = _verify_registration(plan_path)
    if not preflight_only and not parent_reviewed:
        raise ValueError("solver execution requires explicit --parent-reviewed after source/criteria review")
    plan_sha = sha256_path(plan_path)
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    run_id = (
        plan["execution"]["geometry_run_id"] if geometry_only else
        plan["execution"]["preflight_run_id"] if preflight_only else
        plan["execution"]["run_id"]
    )
    run_dir = OUTPUT_ROOT / run_id
    claim = OUTPUT_ROOT / f"{run_id}.claim"
    claim.mkdir()
    try:
        run_dir.mkdir()
    except FileExistsError as exc:
        raise SystemExit(f"refusing to reuse existing run directory: {run_dir}") from exc
    transcript_path = run_dir / "solver.transcript.txt"
    raw_path = run_dir / "raw_history.csv"
    command = [
        "julia", "--threads=auto", f"--project={PROJECT}", str(JOB),
        str(plan_path), str(raw_path), *(["--geometry-only"] if geometry_only else ["--preflight-only"] if preflight_only else []),
    ]
    try:
        try:
            completed = subprocess.run(command, capture_output=True, text=True, timeout=RUN_TIMEOUT_SECONDS, cwd=ROOT)
        except subprocess.TimeoutExpired as exc:
            stdout = exc.stdout or ""
            stderr = exc.stderr or ""
            if isinstance(stdout, bytes):
                stdout = stdout.decode("utf-8", errors="replace")
            if isinstance(stderr, bytes):
                stderr = stderr.decode("utf-8", errors="replace")
            transcript_path.write_text(stdout + "\n--- stderr ---\n" + stderr, encoding="utf-8")
            raise RuntimeError(f"Julia diagnostic timed out after {RUN_TIMEOUT_SECONDS}s; partial output retained") from exc
        transcript = completed.stdout + "\n--- stderr ---\n" + completed.stderr
        transcript_path.write_text(transcript, encoding="utf-8")
        if completed.returncode != 0:
            raise RuntimeError(f"Julia exited {completed.returncode}: {transcript[-4000:]}")
        runtime_record = _parse_runtime_record(completed.stdout, plan)
        if preflight_only:
            runtime_path = run_dir / "runtime.json"
            runtime_payload = {
                "status": "observed_runtime_record_only",
                "criteria_sha256": plan_sha,
                "runtime": runtime_record,
            }
            _write_new(runtime_path, (json.dumps(runtime_payload, indent=2, sort_keys=True) + "\n").encode())
            _write_new(run_dir / "runtime.sha256", f"{sha256_path(runtime_path)}  runtime.json\n".encode())
            if geometry_only and "CANDIDATE_C_LONG_CPU_GEOMETRY_PASS no simulation initialized" in completed.stdout:
                print(f"pure geometry diagnostic passed: {transcript_path.relative_to(ROOT)}")
                return 0
            if "CANDIDATE_C_LONG_CPU_INITIALIZATION_PASS no sim_step! called" not in completed.stdout:
                raise RuntimeError("no-solver initialization preflight completion marker is missing")
            print(f"no-solver initialization preflight passed: {transcript_path.relative_to(ROOT)}")
            return 0
        if "CANDIDATE_C_LONG_CPU_DONE " not in completed.stdout or not raw_path.is_file():
            raise RuntimeError("solver completion marker or raw history is missing")
        result = verify_raw_history(raw_path, plan)
        result.update({
            "criteria_path": plan_path.relative_to(ROOT).as_posix(),
            "criteria_sha256": plan_sha,
            "runner_sha256": sha256_path(Path(__file__).resolve()),
            "job_sha256": sha256_path(JOB),
            "raw_history_sha256": sha256_path(raw_path),
            "transcript_sha256": sha256_path(transcript_path),
            "platform": platform.platform(),
            "architecture": platform.machine(),
            "python": sys.version.split()[0],
            "runtime": runtime_record,
        })
        result_path = run_dir / "result.json"
        encoded = (json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()
        _write_new(result_path, encoded)
        inventory = {
            "criteria.json": plan_sha,
            "runner_sources.sha256": sha256_path(MANIFEST),
            "solver.transcript.txt": sha256_path(transcript_path),
            "raw_history.csv": sha256_path(raw_path),
            "result.json": sha256_path(result_path),
        }
        inventory_path = run_dir / "output.sha256.json"
        _write_new(inventory_path, (json.dumps(inventory, indent=2, sort_keys=True) + "\n").encode())
        _write_new(run_dir / "DONE", b"diagnostic_data_integrity_ok\n")
        print(f"diagnostic integrity complete; no physical qualification: {result_path.relative_to(ROOT)}")
        return 0
    except Exception as exc:
        error_path = _error_artifact(run_dir, plan_sha, "preflight" if preflight_only else "solver_or_host_verification", f"{type(exc).__name__}: {exc}")
        print(f"diagnostic failed; retained error artifact: {error_path.relative_to(ROOT)}", file=sys.stderr)
        raise


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", type=Path, default=PLAN)
    parser.add_argument("--geometry-only", action="store_true", help="sample analytic SDFs only; initialize no solver")
    parser.add_argument("--preflight-only", action="store_true", help="initialize CPU simulations without calling sim_step!")
    parser.add_argument("--parent-reviewed", action="store_true", help="authorize solver steps after parent reviewed exact runner/criteria")
    args = parser.parse_args()
    try:
        if args.geometry_only and args.preflight_only:
            raise ValueError("choose only one preflight mode")
        return _run(args.plan, args.preflight_only or args.geometry_only, args.parent_reviewed,
                    geometry_only=args.geometry_only)
    except Exception as exc:
        print(f"fail-closed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
