#!/usr/bin/env python3
"""W2-T4a analytic sphere CUDA primal recorder.

Validates the captured Colab T4 run outputs against the registered W2-T4a
criteria, compares against the immutable W2a CPU analytic result, and writes
the W2-T4a evidence record plus its sha256 sidecar.  Fail-closed: on any
failed gate no evidence is written.
"""

from __future__ import annotations

import hashlib
import json
import platform
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

CRITERIA_PATH = ROOT / "docs/evidence/sdf_native_w2t4a_analytic_sphere_criteria_2026_09.json"
W0B_RESULT = ROOT / "docs/evidence/sdf_native_w0b_t4_cuda_env_2026_09.json"
W2A_RESULT = ROOT / "docs/evidence/sdf_native_w2a_sphere_cpu_2026_09.json"
W2A_RESULT_SHA256 = "26b6a65f6a2f89dde7e9976b2209b776eeb90d895432707214a582e9192f920b"
T4_PROJECT = ROOT / "julia/CFDSDFWaterLilyT4/Project.toml"
T4_MANIFEST = ROOT / "julia/CFDSDFWaterLilyT4/Manifest.toml"
PROJECT_SHA256 = "e4b56407b8df30b5abe0e26fede29520dbbf69c0580be39bb7d5e657bb984194"
MANIFEST_SHA256 = "c537ae8ef4eaacf7a6e8e906fce8f524a20b9f2ce7e571db9de2a50ec9ed4707"
WORK_DIR = ROOT / "work/sdf_native_w2t4a_analytic_sphere_2026_09"
EVIDENCE_PATH = ROOT / "docs/evidence/sdf_native_w2t4a_analytic_sphere_2026_09.json"

STATIONARITY_BOUND = 0.02
CPU_T4_BOUND = 0.01
REPEAT_BOUND = 1e-6


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


def _relative_difference(a: float, b: float) -> float:
    scale = max(abs(a), abs(b))
    return 0.0 if scale == 0.0 else abs(a - b) / scale


def _extract_summary(text: str, label: str) -> dict[str, Any]:
    match = re.search(r"W2T4_SUMMARY_BEGIN\s*(\{.*?\})\s*W2T4_SUMMARY_END", text, re.S)
    if not match:
        raise SystemExit(f"no summary block in {label}")
    return json.loads(match.group(1))


def main() -> None:
    criteria_sidecar = CRITERIA_PATH.with_suffix(CRITERIA_PATH.suffix + ".sha256")
    if not CRITERIA_PATH.is_file() or not criteria_sidecar.is_file():
        raise SystemExit("W2-T4a criteria or sidecar is missing")
    criteria_sha = _sha256_path(CRITERIA_PATH)
    if criteria_sidecar.read_text().strip() != criteria_sha:
        raise SystemExit("W2-T4a criteria sidecar mismatch")
    w2a_sidecar = W2A_RESULT.with_suffix(W2A_RESULT.suffix + ".sha256")
    if (
        not W2A_RESULT.is_file()
        or not w2a_sidecar.is_file()
        or _sha256_path(W2A_RESULT) != W2A_RESULT_SHA256
        or w2a_sidecar.read_text().strip() != W2A_RESULT_SHA256
    ):
        raise SystemExit("W2a result evidence is missing or inconsistent")
    if not W0B_RESULT.is_file():
        raise SystemExit("W0b result evidence is missing")
    if _sha256_path(T4_PROJECT) != PROJECT_SHA256 or _sha256_path(T4_MANIFEST) != MANIFEST_SHA256:
        raise SystemExit("T4 environment pair changed after W0b")

    criteria = json.loads(CRITERIA_PATH.read_text(encoding="utf-8"))
    runs: dict[str, dict[str, Any]] = {}
    artifacts = {
        "run": WORK_DIR / "run_stdout.txt",
        "repeat": WORK_DIR / "run_repeat_stdout.txt",
    }
    for name, path in artifacts.items():
        if not path.is_file():
            raise SystemExit(f"captured W2-T4a artifact is missing: {name}")
        text = path.read_text(encoding="utf-8", errors="replace")
        if "W2T4_JOB_DONE analytic" not in text:
            raise SystemExit(f"artifact {name} does not contain a completed analytic job")
        runs[name] = _extract_summary(text, name)

    w2a = json.loads(W2A_RESULT.read_text(encoding="utf-8"))
    cpu_drag = w2a["runs"]["analytic"]["summary"]["window_mean_drag"]

    gates: dict[str, Any] = {}
    failures: list[str] = []

    def record(name: str, passed: bool, detail: str) -> None:
        gates[name] = {"pass": passed, "detail": detail}
        if not passed:
            failures.append(name)

    t_end = float(criteria["fixture"]["time"]["t_end_tu_d"])
    run = runs["run"]
    repeat = runs["repeat"]

    record(
        "T0_environment",
        run.get("gpu_name") == "Tesla T4" and run.get("cuda_jl_version", "").startswith("6."),
        f"GPU={run.get('gpu_name')} cuda_jl={run.get('cuda_jl_version')} manifest={MANIFEST_SHA256[:16]}",
    )
    record(
        "T1_completion",
        run["steps"] > 0 and run["t_end_reached"] >= t_end,
        f"steps={run['steps']} t_end_reached={run['t_end_reached']}",
    )
    record("T2_finiteness", bool(run["finite_u"]) and bool(run["finite_p"]),
           f"finite_u={run['finite_u']} finite_p={run['finite_p']}")
    record("T3_force_finite", bool(run["finite_forces"]),
           f"force_samples={run['force_samples']} finite={run['finite_forces']}")
    record("T4_drag_sign", run["window_mean_drag"] > 0.0,
           f"window_mean_drag={run['window_mean_drag']}")
    stationarity = _relative_difference(run["first_half_mean_drag"], run["second_half_mean_drag"])
    record("T5_stationarity", stationarity <= STATIONARITY_BOUND,
           f"relative drift={stationarity:.6e} <= {STATIONARITY_BOUND}")
    cpu_t4 = _relative_difference(run["window_mean_drag"], cpu_drag)
    record("T6_cpu_t4_agreement", cpu_t4 <= CPU_T4_BOUND,
           f"|drag_T4-drag_CPU|/drag_CPU={cpu_t4:.6e} <= {CPU_T4_BOUND} "
           f"(T4={run['window_mean_drag']} CPU={cpu_drag})")
    repeat_difference = _relative_difference(repeat["window_mean_drag"], run["window_mean_drag"])
    record("T7_repeatability", repeat_difference <= REPEAT_BOUND,
           f"repeat relative difference={repeat_difference:.6e} <= {REPEAT_BOUND}")
    vram_ok = (
        0 < int(run["peak_vram_bytes"]) < int(run["vram_total_bytes"])
        and float(run["wall_seconds"]) > 0.0
        and float(run["ms_per_step"]) > 0.0
    )
    record("T8_runtime_and_vram", vram_ok,
           f"peak_vram={run['peak_vram_bytes']} total={run['vram_total_bytes']} "
           f"wall={run['wall_seconds']} ms_per_step={run['ms_per_step']}")

    if failures:
        print(json.dumps({"status": "fail_closed", "failures": failures, "gates": gates}, indent=2))
        raise SystemExit(1)

    document: dict[str, Any] = {
        "schema_version": 1,
        "kind": "sdf_native_w2t4a_analytic_sphere",
        "gate_id": criteria["gate_id"],
        "evidence_class": "capability_and_numerical",
        "immutable": True,
        "solver_started": True,
        "existing_evidence_modified": False,
        "generated_on": {
            "platform": "Colab T4 runtime (Linux x86_64) driven through the colab-mcp browser connection",
            "recording_host": platform.platform(),
            "python": sys.version.split()[0],
        },
        "registered_criteria": {
            "path": CRITERIA_PATH.relative_to(ROOT).as_posix(),
            "sha256": criteria_sha,
        },
        "inputs": {
            "w0b_result": {
                "path": W0B_RESULT.relative_to(ROOT).as_posix(),
                "sha256": _sha256_path(W0B_RESULT),
            },
            "w2a_result": {
                "path": W2A_RESULT.relative_to(ROOT).as_posix(),
                "sha256": W2A_RESULT_SHA256,
            },
            "cpu_analytic_window_mean_drag": cpu_drag,
            "manifest_sha256": MANIFEST_SHA256,
            "project_sha256": PROJECT_SHA256,
        },
        "runs": runs,
        "artifacts": {
            name: {
                "path": path.relative_to(ROOT).as_posix(),
                "sha256": _sha256_path(path),
            }
            for name, path in artifacts.items()
        },
        "gates": gates,
        "verdict": {
            "w2t4a_qualified": True,
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
        raise SystemExit("W2-T4a evidence sidecar mismatch")
    if not sidecar.exists():
        _write_immutable(sidecar, (digest + "\n").encode("utf-8"))
    print(
        json.dumps(
            {
                "status": "registered",
                "gate_id": document["gate_id"],
                "t4_window_mean_drag": run["window_mean_drag"],
                "cpu_window_mean_drag": cpu_drag,
                "cpu_t4_relative_difference": cpu_t4,
                "stationarity": stationarity,
                "repeat_difference": repeat_difference,
                "time_weighted_mean_drag": run["time_weighted_mean_drag"],
                "steps": run["steps"],
                "wall_seconds": run["wall_seconds"],
                "peak_vram_bytes": run["peak_vram_bytes"],
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
