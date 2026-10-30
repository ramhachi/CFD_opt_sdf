#!/usr/bin/env python3
"""W2a-C inherited analytic/GridSDF Candidate C sphere CPU runner.

Registers the W2a fixture run: verifies the immutable criteria, generates the
Julia parameter file from the criteria (single source of truth), runs the registered job for the native analytic sphere, same-grid upstream
control, primary Candidate C body, and one identical analytic repeat, applies the registered fail-closed gates, and
writes the W2a-C evidence record plus its sha256 sidecar. Partial raw data and
an append-only terminal FAIL record are retained on execution or gate failure.
"""

from __future__ import annotations

import csv
import argparse
import hashlib
import json
import platform
import resource
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

CRITERIA_PATH = ROOT / "docs/evidence/candidate_c_w2a_sphere_cpu_criteria_2026_10_round4.json"
W1_RESULT_PATH = ROOT / "docs/evidence/sdf_native_w1_grid_sdf_body_2026_09.json"
W1_RESULT_SHA256 = "d618b556ec71c638f8d10f201c4ae4c62a2b163f824dd9466dd928e89c725567"
MANIFEST_PATH = ROOT / "julia/CFDSDFWaterLily/Manifest.toml"
MANIFEST_SHA256 = "65638d8164df7853821ee6cb52b2163df491700c6f96b903b76558bc2bd0ea1c"
JOB_PATH = ROOT / "scripts/waterlily_w2a_candidate_c_job.jl"
SOURCE_MANIFEST_PATH = ROOT / "docs/evidence/candidate_c_w2a_sphere_cpu_sources_2026_10_round4.sha256"
PROJECT_DIR = ROOT / "julia/CFDSDFWaterLily"
WORK_DIR = ROOT / "work/candidate_c_w2a_sphere_cpu_2026_10_round4"
EVIDENCE_PATH = ROOT / "docs/evidence/candidate_c_w2a_sphere_cpu_result_2026_10_round4.json"

STATIONARITY_BOUND = 0.02
CROSS_FIXTURE_BOUND = 0.10
LIFT_BOUND = 0.10
REPEAT_BOUND = 1e-6
RUN_TIMEOUT_SECONDS = 3600


def _sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_immutable(path: Path, payload: bytes) -> None:
    if path.exists():
        if path.read_bytes() == payload:
            return
        raise SystemExit(f"refusing to overwrite immutable artifact: {path.relative_to(ROOT)}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


def _julia_tuple(values: list[Any]) -> str:
    return "(" + ", ".join(repr(v) for v in values) + ")"


def _params_julia(fixture: dict[str, Any]) -> str:
    flow = fixture["flow"]
    phi = fixture["canonical_phi"]
    affine = fixture["affine_map"]
    time = fixture["time"]
    lines = [
        "const W2A_PARAMS = (",
        f"    flow_dims = {_julia_tuple(flow['dims'])},",
        f"    solver_center = {_julia_tuple(flow['solver_center'])},",
        f"    solver_radius = {float(flow['solver_radius'])!r},",
        f"    u_inf = {float(flow['u_inf'])!r},",
        f"    reynolds = {float(flow['reynolds_diameter'])!r},",
        f"    viscosity = {float(flow['kinematic_viscosity_solver'])!r},",
        f"    t_end = {float(time['t_end_tu_d'])!r},",
        f"    burn_in = {float(time['burn_in_tu_d'])!r},",
        f"    sample_every = {int(time['force_sampling'].split()[1])},",
        f"    phi_origin = {_julia_tuple(phi['origin_m'])},",
        f"    phi_spacing = {float(phi['spacing_m'][0])!r},",
        f"    phi_shape = {_julia_tuple(phi['shape'])},",
        f"    phi_center = {_julia_tuple(phi['center_m'])},",
        f"    phi_radius = {float(phi['radius_m'])!r},",
        f"    outside_value = {float(phi['outside_value_m'])!r},",
        f"    run_margin = {float(phi['margin_gate_m'])!r},",
        f"    world_origin = {_julia_tuple(affine['world_origin_m'])},",
        f"    world_per_solver = {float(affine['world_per_solver'])!r},",
        ")",
    ]
    return "\n".join(lines) + "\n"


def _run_job(params_path: Path, mode: str, out_prefix: Path) -> dict[str, Any]:
    summary_path = out_prefix.with_suffix(".summary.json")
    transcript_path = out_prefix.with_suffix(".stdout.txt")
    csv_path = out_prefix.with_suffix(".forces.csv")
    for path in (summary_path, transcript_path, csv_path):
        if path.exists():
            raise RuntimeError(f"refusing to overwrite existing run artifact: {path}")
    command = [
            "julia",
            "--threads=auto",
            f"--project={PROJECT_DIR}",
            str(JOB_PATH),
            str(params_path),
            mode,
            str(out_prefix),
        ]
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=RUN_TIMEOUT_SECONDS,
            check=False,
            cwd=ROOT,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout or ""
        stderr = exc.stderr or ""
        if isinstance(stdout, bytes):
            stdout = stdout.decode("utf-8", errors="replace")
        if isinstance(stderr, bytes):
            stderr = stderr.decode("utf-8", errors="replace")
        transcript = str(stdout) + "\n--- stderr ---\n" + str(stderr)
        transcript_path.write_text(transcript, encoding="utf-8")
        raise RuntimeError(
            f"W2a job timed out: mode={mode}; partial history={csv_path}; transcript={transcript_path}"
        ) from exc
    transcript = completed.stdout + "\n--- stderr ---\n" + completed.stderr
    transcript_path.write_text(transcript, encoding="utf-8")
    if completed.returncode != 0 or "W2A_JOB_DONE" not in completed.stdout or not summary_path.is_file():
        print(transcript, file=sys.stderr)
        raise RuntimeError(
            f"W2a job fail-closed: mode={mode} exit={completed.returncode}; "
            f"partial history={csv_path}; transcript={transcript_path}"
        )
    with open(summary_path, "r", encoding="utf-8") as handle:
        summary = json.load(handle)
    return {
        "summary": summary,
        "summary_path": summary_path,
        "csv_path": csv_path,
        "transcript_path": transcript_path,
    }


def _terminal_fail(run_dir: Path, criteria_sha: str, source_manifest_sha: str,
                   stage: str, detail: str) -> Path:
    """Write an append-only failure summary while preserving partial artifacts."""
    payload: dict[str, Any] = {
        "schema_version": 1,
        "status": "FAIL",
        "gate_id": "sdf_native_w2a_candidate_c_sphere_cpu_2026_10_round4",
        "stage": stage,
        "detail": detail,
        "criteria": {"path": CRITERIA_PATH.relative_to(ROOT).as_posix(), "sha256": criteria_sha},
        "source_manifest": {
            "path": SOURCE_MANIFEST_PATH.relative_to(ROOT).as_posix(),
            "sha256": source_manifest_sha,
        },
        "runner_sha256": _sha256_path(Path(__file__).resolve()),
        "job_sha256": _sha256_path(JOB_PATH),
        "scope": "failed W2a-C CPU registration only; no qualification or production claim",
        "partial_artifacts": [],
    }
    if run_dir.exists():
        for path in sorted(run_dir.rglob("*")):
            if path.is_file() and path.name != "terminal-FAIL.json":
                payload["partial_artifacts"].append({
                    "path": path.relative_to(ROOT).as_posix(), "sha256": _sha256_path(path)
                })
    terminal = run_dir / "terminal-FAIL.json"
    encoded = (json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()
    _write_immutable(terminal, encoded)
    return terminal


def _read_force_rows(csv_path: Path) -> list[dict[str, float]]:
    rows: list[dict[str, float]] = []
    with open(csv_path, "r", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            rows.append({key: float(value) for key, value in row.items()})
    return rows


def _relative_to_reference(value: float, reference: float) -> float:
    if not (value == value and reference == reference):
        return float("inf")
    if reference == 0.0 or abs(reference) == float("inf") or abs(value) == float("inf"):
        return float("inf")
    return abs(value - reference) / abs(reference)


def _stationarity_ratio(first: float, second: float, full_mean: float) -> float:
    """Registered equal-half drift divided by the full-window mean magnitude."""
    if not all(value == value and abs(value) != float("inf") for value in (first, second, full_mean)):
        return float("inf")
    if full_mean == 0.0:
        return float("inf")
    return abs(first - second) / abs(full_mean)


def _lift_ratio(lift: float, drag: float) -> float:
    if not all(value == value and abs(value) != float("inf") for value in (lift, drag)):
        return float("inf")
    if drag <= 0.0:
        return float("inf")
    return abs(lift) / drag


def _window_mean(rows: list[dict[str, float]], field: str, start: float, end: float) -> float:
    """Recompute a time mean from raw CSV rows using endpoint interpolation + trapezoids."""
    if end <= start or len(rows) < 2:
        raise ValueError("invalid window or insufficient raw samples")
    times = [row["t_ud"] for row in rows]
    if any(not (a < b) for a, b in zip(times, times[1:])):
        raise ValueError("raw sample times must be strictly increasing")

    def at(target: float) -> float:
        if target < times[0] or target > times[-1]:
            raise ValueError(f"raw samples do not bracket t={target}")
        for left, right in zip(rows, rows[1:]):
            if left["t_ud"] <= target <= right["t_ud"]:
                weight = (target - left["t_ud"]) / (right["t_ud"] - left["t_ud"])
                return left[field] + weight * (right[field] - left[field])
        raise ValueError(f"raw sample bracket missing at t={target}")

    interior = [row for row in rows if start < row["t_ud"] < end]
    points = [(start, at(start))]
    points.extend((row["t_ud"], row[field]) for row in interior)
    points.append((end, at(end)))
    area = sum((t1 - t0) * (v0 + v1) / 2.0 for (t0, v0), (t1, v1) in zip(points, points[1:]))
    return area / (end - start)


def _raw_window_statistics(rows: list[dict[str, float]]) -> dict[str, float]:
    return {
        "window_mean_drag": _window_mean(rows, "drag_solver", 40.0, 60.0),
        "window_mean_lift": _window_mean(rows, "lift_solver", 40.0, 60.0),
        "window_mean_side": _window_mean(rows, "side_solver", 40.0, 60.0),
        "first_half_mean_drag": _window_mean(rows, "drag_solver", 40.0, 50.0),
        "second_half_mean_drag": _window_mean(rows, "drag_solver", 50.0, 60.0),
    }


def _summary_matches_raw(summary: dict[str, Any], stats: dict[str, float]) -> bool:
    for key, raw_value in stats.items():
        reported = float(summary[key])
        if not all(value == value and abs(value) != float("inf") for value in (reported, raw_value)):
            return False
        if abs(reported - raw_value) > 1e-10 * max(1.0, abs(raw_value)):
            return False
    return True


def _qualification_claims(criteria: dict[str, Any]) -> list[str]:
    return list(criteria["claims_supported_if_all_gates_pass"])


def main(preflight_only: bool = False) -> None:
    criteria_sidecar = CRITERIA_PATH.with_suffix(CRITERIA_PATH.suffix + ".sha256")
    if not CRITERIA_PATH.is_file() or not criteria_sidecar.is_file():
        raise SystemExit("W2a-C criteria or sidecar is missing")
    criteria_sha = _sha256_path(CRITERIA_PATH)
    if criteria_sidecar.read_text().strip() != criteria_sha:
        raise SystemExit("W2a-C criteria sidecar mismatch")
    criteria = json.loads(CRITERIA_PATH.read_text(encoding="utf-8"))
    if _sha256_path(SOURCE_MANIFEST_PATH) != criteria["inputs"]["source_manifest_sha256"]:
        raise SystemExit("W2a-C source manifest mismatch")
    for line in SOURCE_MANIFEST_PATH.read_text(encoding="utf-8").splitlines():
        expected, relative = line.split("  ", 1)
        source_path = ROOT / relative
        if not source_path.is_file() or _sha256_path(source_path) != expected:
            raise SystemExit(f"W2a-C registered source mismatch: {relative}")
    w1_sidecar = W1_RESULT_PATH.with_suffix(W1_RESULT_PATH.suffix + ".sha256")
    if (
        not W1_RESULT_PATH.is_file()
        or not w1_sidecar.is_file()
        or w1_sidecar.read_text().strip() != W1_RESULT_SHA256
        or _sha256_path(W1_RESULT_PATH) != W1_RESULT_SHA256
    ):
        raise SystemExit("W1 result evidence is missing or inconsistent")
    if _sha256_path(MANIFEST_PATH) != MANIFEST_SHA256:
        raise SystemExit("pinned Manifest.toml changed; W0 environment identity is broken")

    fixture = criteria["fixture"]

    if preflight_only:
        with tempfile.TemporaryDirectory(prefix="candidate-c-w2a-preflight-") as temp_name:
            temp_dir = Path(temp_name)
            params_path = temp_dir / "w2a_params.jl"
            params_path.write_text(_params_julia(fixture))
            out_prefix = temp_dir / "candidate_c_init_preflight"
            completed = subprocess.run(
                [
                    "julia",
                    "--threads=auto",
                    f"--project={PROJECT_DIR}",
                    str(JOB_PATH),
                    str(params_path),
                    "preflight_candidate_c",
                    str(out_prefix),
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=RUN_TIMEOUT_SECONDS,
                check=False,
            )
            transcript = completed.stdout + "\n--- stderr ---\n" + completed.stderr
            if completed.returncode != 0 or "W2A_C_INITIALIZATION_PREFLIGHT_PASS" not in completed.stdout:
                print(transcript, file=sys.stderr)
                raise SystemExit("W2a-C initialization preflight failed before solver step")
            print(transcript)
            print("PREFLIGHT_ONLY: no sim_step!, no measurement artifacts, no qualification")
        return

    run_dir = WORK_DIR / "run-001"
    claim_dir = run_dir.with_name(run_dir.name + ".claim")
    if run_dir.exists():
        raise SystemExit(f"refusing to overwrite an existing W2a-C run directory: {run_dir}")
    claim_dir.parent.mkdir(parents=True, exist_ok=True)
    try:
        claim_dir.mkdir()
    except FileExistsError as exc:
        raise SystemExit(f"refusing to reuse an existing W2a-C output claim: {claim_dir}") from exc
    run_dir.mkdir()
    params_path = run_dir / "w2a_params.jl"
    params_path.write_text(_params_julia(fixture))

    modes = [
        ("analytic", run_dir / "analytic"),
        ("grid_upstream", run_dir / "grid_upstream"),
        ("candidate_c", run_dir / "candidate_c"),
        ("analytic", run_dir / "analytic_repeat"),
    ]
    runs: dict[str, dict[str, Any]] = {}
    names = ["analytic", "grid_upstream", "candidate_c", "analytic_repeat"]
    for name, (mode, prefix) in zip(names, modes):
        try:
            runs[name] = _run_job(params_path, mode, prefix)
        except Exception as exc:
            failure_path = _terminal_fail(
                run_dir, criteria_sha, criteria["inputs"]["source_manifest_sha256"],
                f"solver_job:{name}", f"{type(exc).__name__}: {exc}",
            )
            raise SystemExit(f"W2a-C run failed; terminal record: {failure_path}") from exc

    gates: dict[str, Any] = {}
    failures: list[str] = []

    def record(name: str, passed: bool, detail: str) -> None:
        gates[name] = {"pass": passed, "detail": detail}
        if not passed:
            failures.append(name)

    t_end = float(fixture["time"]["t_end_tu_d"])
    completion = []
    finiteness = []
    force_finite = True
    boundary_flow_finite = True
    raw_summary_consistent = True
    for name in names:
        summary = runs[name]["summary"]
        completion.append(
            summary["steps"] > 0 and summary["t_end_reached"] >= t_end
        )
        finiteness.append(bool(summary["finite_u"]) and bool(summary["finite_p"]))
        rows: list[dict[str, float]] = []
        try:
            rows = _read_force_rows(runs[name]["csv_path"])
            raw_stats = _raw_window_statistics(rows)
        except (KeyError, OSError, ValueError, ZeroDivisionError) as exc:
            raw_stats = {key: float("inf") for key in (
                "window_mean_drag", "window_mean_lift", "window_mean_side",
                "first_half_mean_drag", "second_half_mean_drag",
            )}
            runs[name]["raw_statistics_error"] = f"{type(exc).__name__}: {exc}"
            raw_summary_consistent = False
        else:
            raw_summary_consistent &= _summary_matches_raw(summary, raw_stats)
        runs[name]["raw_window_statistics"] = raw_stats
        force_fields = ("drag_solver", "lift_solver", "side_solver", "pressure_drag_solver", "viscous_drag_solver", "fx_n", "fy_n", "fz_n")
        flow_fields = ("inlet_kg_s", "outlet_kg_s", "yminus_kg_s", "yplus_kg_s", "zminus_kg_s", "zplus_kg_s", "net_outward_kg_s", "integrated_divergence_kg_s", "divergence_boundary_difference_kg_s")
        finite = lambda value: value == value and abs(value) != float("inf")
        if len(rows) == 0 or any(not all(field in row and finite(row[field]) for field in force_fields) for row in rows):
            force_finite = False
        if len(rows) == 0 or any(not all(field in row and finite(row[field]) for field in flow_fields) for row in rows):
            boundary_flow_finite = False
        runs[name]["force_rows"] = len(rows)
        runs[name]["artifact_prefix"] = str(runs[name]["csv_path"].relative_to(ROOT)).removesuffix(".forces.csv")
    record("G1_completion", all(completion), f"t_end={t_end} reached for {names}")
    record("G2_finiteness", all(finiteness), f"finite u/p for {names}")
    record("G3_force_finite", force_finite, "every sampled force component finite")
    record("G11_raw_summary_consistency", raw_summary_consistent, "independent Python endpoint interpolation/trapezoids over raw CSV reproduce reported 40-60, 40-50, and 50-60 drag/lift/side means within 1e-10 relative-scale integrity tolerance")
    record("G9_boundary_flow_finite", boundary_flow_finite, "all six physically weighted external-face mass flows and divergence diagnostics finite; no conservation threshold")
    minimum_margin = float(fixture["canonical_phi"]["margin_gate_m"])
    measured_margins = {
        name: runs[name]["summary"]["phi_margin_m"]
        for name in ("grid_upstream", "candidate_c")
    }
    record(
        "G10_sampled_geometry_margin",
        all(value >= minimum_margin for value in measured_margins.values()),
        f"measured sampled-SDF margin {measured_margins} >= registered 3h gate {minimum_margin} m",
    )

    formal_names = ["analytic", "candidate_c", "analytic_repeat"]
    drags = {name: runs[name]["raw_window_statistics"]["window_mean_drag"] for name in names}
    record("G4_drag_sign", all(drags[name] > 0.0 for name in formal_names), f"window drag {drags}")

    stationary = {}
    for name in formal_names:
        stats = runs[name]["raw_window_statistics"]
        first = stats["first_half_mean_drag"]
        second = stats["second_half_mean_drag"]
        mean = stats["window_mean_drag"]
        stationary[name] = _stationarity_ratio(first, second, mean)
    record(
        "G5_stationarity",
        all(value <= STATIONARITY_BOUND for value in stationary.values()),
        f"half-window relative drifts {stationary} <= {STATIONARITY_BOUND}",
    )

    area = 0.5 * 3.141592653589793 * float(fixture["flow"]["solver_radius"]) ** 2
    cd_analytic = drags["analytic"] / area
    cd_candidate = drags["candidate_c"] / area
    cd_difference = _relative_to_reference(cd_candidate, cd_analytic)
    record(
        "G6_candidate_c_vs_native",
        cd_difference <= CROSS_FIXTURE_BOUND,
        f"|Cd_candidate_c-Cd_analytic|/Cd_analytic={cd_difference:.6e} <= {CROSS_FIXTURE_BOUND}",
    )

    lift_ratios = {
        name: _lift_ratio(
            runs[name]["raw_window_statistics"]["window_mean_lift"],
            runs[name]["raw_window_statistics"]["window_mean_drag"],
        ) for name in formal_names
    }
    record(
        "G7_lift_bound",
        all(value <= LIFT_BOUND for value in lift_ratios.values()),
        f"|lift|/drag {lift_ratios} <= {LIFT_BOUND}",
    )

    repeat_difference = _relative_to_reference(
        drags["analytic_repeat"], drags["analytic"]
    )
    record(
        "G8_reproducibility",
        repeat_difference <= REPEAT_BOUND,
        f"repeat relative drag difference {repeat_difference:.6e} <= {REPEAT_BOUND}",
    )

    if failures:
        print(json.dumps({"status": "fail_closed", "failures": failures, "gates": gates}, indent=2))
        failure_path = _terminal_fail(
            run_dir, criteria_sha, criteria["inputs"]["source_manifest_sha256"],
            "registered_numeric_gates", json.dumps({"failures": failures, "gates": gates}, sort_keys=True),
        )
        print(f"terminal failure record: {failure_path.relative_to(ROOT)}")
        raise SystemExit(1)

    for name in names:
        runs[name]["summary_sha256"] = _sha256_path(runs[name]["summary_path"])
        runs[name]["csv_sha256"] = _sha256_path(runs[name]["csv_path"])
        runs[name]["transcript_sha256"] = _sha256_path(runs[name]["transcript_path"])
        del runs[name]["summary_path"]
        del runs[name]["csv_path"]
        del runs[name]["transcript_path"]

    fingerprint = runs["analytic"]["summary"]
    child_peak_rss = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
    document: dict[str, Any] = {
        "schema_version": 1,
        "kind": "candidate_c_w2a_sphere_cpu",
        "gate_id": criteria["gate_id"],
        "evidence_class": "inherited_W2a_capability_and_numerical",
        "qualification_scope": "registered CPU sphere fixture only; no production, mass-conservation, target-physics, W3-C, or W4-C claim",
        "immutable": True,
        "solver_started": True,
        "existing_evidence_modified": False,
        "generated_on": {
            "platform": platform.platform(),
            "machine": platform.machine(),
            "python": sys.version.split()[0],
            "julia": fingerprint["julia_version"],
            "julia_threads": fingerprint["julia_threads"],
            "waterlily": fingerprint["waterlily_version"],
            "waterlily_backend": fingerprint["waterlily_backend"],
            "child_peak_rss_bytes": child_peak_rss,
        },
        "registered_criteria": {
            "path": CRITERIA_PATH.relative_to(ROOT).as_posix(),
            "sha256": criteria_sha,
        },
        "inputs": {
            "manifest_sha256": MANIFEST_SHA256,
            "source_manifest_sha256": criteria["inputs"]["source_manifest_sha256"],
            "inherited_w2a_criteria_sha256": criteria["inputs"]["inherited_w2a_criteria_sha256"],
            "w1_result": {
                "path": W1_RESULT_PATH.relative_to(ROOT).as_posix(),
                "sha256": W1_RESULT_SHA256,
            },
        },
        "fixture": fixture,
        "runs": runs,
        "gates": gates,
        "verdict": {
            "candidate_c_w2a_qualified": True,
            "fail_closed": False,
        },
        "claims_supported": _qualification_claims(criteria),
        "claims_not_supported": criteria["claims_not_supported"],
        "flags": criteria["flags"],
    }
    payload = (json.dumps(document, indent=2, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n").encode(
        "utf-8"
    )
    _write_immutable(EVIDENCE_PATH, payload)
    sidecar = EVIDENCE_PATH.with_suffix(EVIDENCE_PATH.suffix + ".sha256")
    digest = _sha256_path(EVIDENCE_PATH)
    if sidecar.exists() and sidecar.read_text().strip() != digest:
        raise SystemExit("W2a-C evidence sidecar mismatch")
    if not sidecar.exists():
        _write_immutable(sidecar, (digest + "\n").encode("utf-8"))

    print(
        json.dumps(
            {
                "status": "registered",
                "gate_id": criteria["gate_id"],
                "evidence_class": "inherited_W2a_capability_and_numerical",
                "qualification_scope": "registered CPU sphere fixture only; no production, mass-conservation, target-physics, W3-C, or W4-C claim",
                "cd_analytic": cd_analytic,
                "cd_candidate_c": cd_candidate,
                "cd_relative_difference": cd_difference,
                "window_mean_drag": drags,
                "stationarity": stationary,
                "repeat_difference": repeat_difference,
                "steps": {name: runs[name]["summary"]["steps"] for name in names},
                "wall_seconds": {name: runs[name]["summary"]["wall_seconds"] for name in names},
                "gates_passed": len(gates),
                "evidence": EVIDENCE_PATH.relative_to(ROOT).as_posix(),
                "evidence_sha256": digest,
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--preflight-only",
        action="store_true",
        help="verify identities and initialize Candidate C without calling sim_step!",
    )
    main(preflight_only=parser.parse_args().preflight_only)
