#!/usr/bin/env python3
"""W2a analytic/sampled sphere CPU primal runner.

Registers the W2a fixture run: verifies the immutable criteria, generates the
Julia parameter file from the criteria (single source of truth), runs the
registered job for the analytic sphere, the sampled GridSDF sphere, and one
identical analytic repeat, applies the registered fail-closed gates, and
writes the W2a evidence record plus its sha256 sidecar.  On any gate failure
no evidence is written.
"""

from __future__ import annotations

import csv
import hashlib
import json
import platform
import resource
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

CRITERIA_PATH = ROOT / "docs/evidence/sdf_native_w2a_sphere_cpu_criteria_2026_09.json"
W1_RESULT_PATH = ROOT / "docs/evidence/sdf_native_w1_grid_sdf_body_2026_09.json"
W1_RESULT_SHA256 = "d618b556ec71c638f8d10f201c4ae4c62a2b163f824dd9466dd928e89c725567"
MANIFEST_PATH = ROOT / "julia/CFDSDFWaterLily/Manifest.toml"
MANIFEST_SHA256 = "65638d8164df7853821ee6cb52b2163df491700c6f96b903b76558bc2bd0ea1c"
JOB_PATH = ROOT / "scripts/waterlily_w2a_job.jl"
PROJECT_DIR = ROOT / "julia/CFDSDFWaterLily"
WORK_DIR = ROOT / "work/sdf_native_w2a_sphere_cpu_2026_09"
EVIDENCE_PATH = ROOT / "docs/evidence/sdf_native_w2a_sphere_cpu_2026_09.json"

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
    completed = subprocess.run(
        [
            "julia",
            "--threads=auto",
            f"--project={PROJECT_DIR}",
            str(JOB_PATH),
            str(params_path),
            mode,
            str(out_prefix),
        ],
        capture_output=True,
        text=True,
        timeout=RUN_TIMEOUT_SECONDS,
        check=False,
        cwd=ROOT,
    )
    transcript = completed.stdout + "\n--- stderr ---\n" + completed.stderr
    summary_path = out_prefix.with_suffix(".summary.json")
    if completed.returncode != 0 or "W2A_JOB_DONE" not in completed.stdout or not summary_path.is_file():
        print(transcript, file=sys.stderr)
        raise SystemExit(f"W2a job fail-closed: mode={mode} exit={completed.returncode}")
    with open(summary_path, "r", encoding="utf-8") as handle:
        summary = json.load(handle)
    transcript_path = out_prefix.with_suffix(".stdout.txt")
    transcript_path.write_text(transcript)
    csv_path = out_prefix.with_suffix(".forces.csv")
    return {
        "summary": summary,
        "summary_path": summary_path,
        "csv_path": csv_path,
        "transcript_path": transcript_path,
    }


def _read_force_rows(csv_path: Path) -> list[dict[str, float]]:
    rows: list[dict[str, float]] = []
    with open(csv_path, "r", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            rows.append({key: float(value) for key, value in row.items()})
    return rows


def _relative_difference(a: float, b: float) -> float:
    scale = max(abs(a), abs(b))
    return 0.0 if scale == 0.0 else abs(a - b) / scale


def main() -> None:
    criteria_sidecar = CRITERIA_PATH.with_suffix(CRITERIA_PATH.suffix + ".sha256")
    if not CRITERIA_PATH.is_file() or not criteria_sidecar.is_file():
        raise SystemExit("W2a criteria or sidecar is missing")
    criteria_sha = _sha256_path(CRITERIA_PATH)
    if criteria_sidecar.read_text().strip() != criteria_sha:
        raise SystemExit("W2a criteria sidecar mismatch")
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

    criteria = json.loads(CRITERIA_PATH.read_text(encoding="utf-8"))
    fixture = criteria["fixture"]

    WORK_DIR.mkdir(parents=True, exist_ok=True)
    params_path = WORK_DIR / "w2a_params.jl"
    params_path.write_text(_params_julia(fixture))

    modes = [
        ("analytic", WORK_DIR / "analytic"),
        ("gridsdf", WORK_DIR / "gridsdf"),
        ("analytic", WORK_DIR / "analytic_repeat"),
    ]
    runs: dict[str, dict[str, Any]] = {}
    names = ["analytic", "gridsdf", "analytic_repeat"]
    for name, (mode, prefix) in zip(names, modes):
        runs[name] = _run_job(params_path, mode, prefix)

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
    for name in names:
        summary = runs[name]["summary"]
        completion.append(
            summary["steps"] > 0 and summary["t_end_reached"] >= t_end
        )
        finiteness.append(bool(summary["finite_u"]) and bool(summary["finite_p"]))
        rows = _read_force_rows(runs[name]["csv_path"])
        if len(rows) == 0 or any(
            not all(map(lambda v: v == v and abs(v) != float("inf"), row.values()))
            for row in rows
        ):
            force_finite = False
        runs[name]["force_rows"] = len(rows)
    record("G1_completion", all(completion), f"t_end={t_end} reached for {names}")
    record("G2_finiteness", all(finiteness), f"finite u/p for {names}")
    record("G3_force_finite", force_finite, "every sampled force component finite")

    drags = {name: runs[name]["summary"]["window_mean_drag"] for name in names}
    record("G4_drag_sign", all(drags[name] > 0.0 for name in names), f"window drag {drags}")

    stationary = {}
    for name in names:
        summary = runs[name]["summary"]
        first = summary["first_half_mean_drag"]
        second = summary["second_half_mean_drag"]
        mean = summary["window_mean_drag"]
        stationary[name] = _relative_difference(first, second) if mean != 0.0 else 0.0
    record(
        "G5_stationarity",
        all(value <= STATIONARITY_BOUND for value in stationary.values()),
        f"half-window relative drifts {stationary} <= {STATIONARITY_BOUND}",
    )

    cd_analytic = runs["analytic"]["summary"]["cd"]
    cd_sampled = runs["gridsdf"]["summary"]["cd"]
    cd_difference = _relative_difference(cd_sampled, cd_analytic)
    record(
        "G6_cross_fixture",
        cd_difference <= CROSS_FIXTURE_BOUND,
        f"|Cd_sampled-Cd_analytic|/Cd_analytic={cd_difference:.6e} <= {CROSS_FIXTURE_BOUND}",
    )

    lift_ratios = {
        name: abs(runs[name]["summary"]["window_mean_lift"]) / runs[name]["summary"]["window_mean_drag"]
        for name in names
    }
    record(
        "G7_lift_bound",
        all(value <= LIFT_BOUND for value in lift_ratios.values()),
        f"|lift|/drag {lift_ratios} <= {LIFT_BOUND}",
    )

    repeat_difference = _relative_difference(
        runs["analytic_repeat"]["summary"]["window_mean_drag"], drags["analytic"]
    )
    record(
        "G8_reproducibility",
        repeat_difference <= REPEAT_BOUND,
        f"repeat relative drag difference {repeat_difference:.6e} <= {REPEAT_BOUND}",
    )

    if failures:
        print(json.dumps({"status": "fail_closed", "failures": failures, "gates": gates}, indent=2))
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
        "kind": "sdf_native_w2a_sphere_cpu",
        "gate_id": criteria["gate_id"],
        "evidence_class": "capability_and_numerical",
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
            "w1_result": {
                "path": W1_RESULT_PATH.relative_to(ROOT).as_posix(),
                "sha256": W1_RESULT_SHA256,
            },
        },
        "fixture": fixture,
        "runs": runs,
        "gates": gates,
        "verdict": {
            "w2a_qualified": True,
            "fail_closed": False,
        },
        "claims_supported": criteria["claims_supported"],
        "claims_not_supported": criteria["claims_not_supported"],
        "flags": criteria["flags"],
    }
    payload = (json.dumps(document, indent=2, ensure_ascii=False, sort_keys=True) + "\n").encode(
        "utf-8"
    )
    _write_immutable(EVIDENCE_PATH, payload)
    sidecar = EVIDENCE_PATH.with_suffix(EVIDENCE_PATH.suffix + ".sha256")
    digest = _sha256_path(EVIDENCE_PATH)
    if sidecar.exists() and sidecar.read_text().strip() != digest:
        raise SystemExit("W2a evidence sidecar mismatch")
    if not sidecar.exists():
        _write_immutable(sidecar, (digest + "\n").encode("utf-8"))

    print(
        json.dumps(
            {
                "status": "registered",
                "gate_id": criteria["gate_id"],
                "cd_analytic": cd_analytic,
                "cd_sampled": cd_sampled,
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
    main()
