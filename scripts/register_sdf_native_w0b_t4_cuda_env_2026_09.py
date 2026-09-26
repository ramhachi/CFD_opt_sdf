#!/usr/bin/env python3
"""W0b T4 CUDA environment recorder.

Validates the captured Colab T4 session artifacts against the registered W0b
criteria, verifies the committed T4 environment pair, and writes the
immutable W0b evidence record plus its sha256 sidecar.  Fail-closed: on any
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

CRITERIA_PATH = ROOT / "docs/evidence/sdf_native_w0b_t4_cuda_env_criteria_2026_09.json"
T4_PROJECT = ROOT / "julia/CFDSDFWaterLilyT4/Project.toml"
T4_MANIFEST = ROOT / "julia/CFDSDFWaterLilyT4/Manifest.toml"
CPU_ENV_EVIDENCE = ROOT / "docs/evidence/sdf_native_w0_julia_env_2026_09.json"
CPU_MANIFEST_SHA256 = "65638d8164df7853821ee6cb52b2163df491700c6f96b903b76558bc2bd0ea1c"
WORK_DIR = ROOT / "work/sdf_native_w0b_t4_cuda_env_2026_09"
EVIDENCE_PATH = ROOT / "docs/evidence/sdf_native_w0b_t4_cuda_env_2026_09.json"


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


def _marker(text: str, key: str) -> str | None:
    match = re.search(rf"^{re.escape(key)} (.+)$", text, re.M)
    return match.group(1).strip() if match else None


def main() -> None:
    criteria_sidecar = CRITERIA_PATH.with_suffix(CRITERIA_PATH.suffix + ".sha256")
    if not CRITERIA_PATH.is_file() or not criteria_sidecar.is_file():
        raise SystemExit("W0b criteria or sidecar is missing")
    criteria_sha = _sha256_path(CRITERIA_PATH)
    if criteria_sidecar.read_text().strip() != criteria_sha:
        raise SystemExit("W0b criteria sidecar mismatch")
    if _sha256_path(CPU_ENV_EVIDENCE) != "9689ed58dfda87414bc1a4be8fce49d86405c2619217540bfe08391b98b3e5e7":
        raise SystemExit("W0 CPU evidence changed")
    if not T4_PROJECT.is_file() or not T4_MANIFEST.is_file():
        raise SystemExit("T4 environment pair is missing; resolve and commit it first")

    artifacts: dict[str, Path] = {
        "nvidia_smi": WORK_DIR / "nvidia_smi.txt",
        "resolve_stdout": WORK_DIR / "resolve_stdout.txt",
        "smoke_stdout": WORK_DIR / "smoke_stdout.txt",
    }
    for name, path in artifacts.items():
        if not path.is_file():
            raise SystemExit(f"captured W0b artifact is missing: {name} ({path})")

    nvidia_smi = artifacts["nvidia_smi"].read_text(encoding="utf-8", errors="replace")
    smoke = artifacts["smoke_stdout"].read_text(encoding="utf-8", errors="replace")
    base_commit_path = WORK_DIR / "base_commit.txt"
    base_commit = base_commit_path.read_text().strip() if base_commit_path.is_file() else ""

    project_sha = _sha256_path(T4_PROJECT)
    manifest_sha = _sha256_path(T4_MANIFEST)
    manifest_text = T4_MANIFEST.read_text(encoding="utf-8")

    def manifest_field(section: str, key: str) -> str | None:
        block = re.search(rf"\[\[deps\.{re.escape(section)}\]\].*?(?=\n\[|\Z)", manifest_text, re.S)
        if not block:
            return None
        match = re.search(rf'^{key} = "(.*)"$', block.group(0), re.M)
        return match.group(1) if match else None

    gates: dict[str, Any] = {}
    failures: list[str] = []

    def record(name: str, passed: bool, detail: str) -> None:
        gates[name] = {"pass": passed, "detail": detail}
        if not passed:
            failures.append(name)

    gpu_csv = None
    for line in nvidia_smi.splitlines():
        parts = [part.strip() for part in line.split(",")]
        if len(parts) == 5 and parts[0].startswith("Tesla T4") and "MiB" in parts[2]:
            gpu_csv = parts
    gpu_uuid = gpu_csv[1] if gpu_csv else None
    memory_mib = int(gpu_csv[2].split()[0]) if gpu_csv else None
    memory_bytes = memory_mib * 1024 * 1024 if memory_mib else None
    smoke_memory = _marker(smoke, "GPU_TOTAL_MEMORY_BYTES")
    if memory_bytes is None and smoke_memory and smoke_memory.isdigit():
        memory_bytes = int(smoke_memory)

    gpu_name = _marker(smoke, "GPU_NAME")
    record("G0_targeted_runtime", "Tesla T4" in nvidia_smi, f"nvidia-smi T4 match; GPU_NAME={gpu_name}")
    record("G1_cuda_functional", _marker(smoke, "CUDA_FUNCTIONAL") == "true",
           f"CUDA_FUNCTIONAL={_marker(smoke, 'CUDA_FUNCTIONAL')}")
    record("G2_cuarray_smoke", _marker(smoke, "CUARRAY_SMOKE") == "true",
           f"CUARRAY_SMOKE={_marker(smoke, 'CUARRAY_SMOKE')}")
    record("G3_ka_smoke", _marker(smoke, "KA_SMOKE") == "true",
           f"KA_SMOKE={_marker(smoke, 'KA_SMOKE')}")
    record("G4_waterlily_cuda_ext", _marker(smoke, "WATERLILY_CUDA_EXT") == "true",
           f"WATERLILY_CUDA_EXT={_marker(smoke, 'WATERLILY_CUDA_EXT')}")
    record("G5_no_solver_step", "NO_SOLVER_STEP" in smoke,
           "no Simulation/sim_step! marker present")
    identity_fields = {
        "julia_version": _marker(smoke, "JULIA_VERSION"),
        "waterlily_version": _marker(smoke, "WATERLILY_VERSION"),
        "cuda_jl_version": _marker(smoke, "CUDA_JL_VERSION"),
        "gpu_name": gpu_name,
        "gpu_compute_capability": _marker(smoke, "GPU_COMPUTE_CAPABILITY"),
        "gpu_total_memory_bytes": str(memory_bytes) if memory_bytes else smoke_memory,
        "gpu_uuid": gpu_uuid or "not exposed",
        "cuda_driver_version": _marker(smoke, "CUDA_DRIVER_VERSION"),
        "cuda_runtime_version": _marker(smoke, "CUDA_RUNTIME_VERSION"),
    }
    record(
        "G6_identity",
        all(value for key, value in identity_fields.items() if key != "gpu_uuid")
        and memory_bytes is not None,
        f"identity fields {identity_fields}",
    )

    if failures or not (WORK_DIR / "smoke_stdout.txt").is_file():
        print(json.dumps({"status": "fail_closed", "failures": failures, "gates": gates}, indent=2))
        raise SystemExit(1)

    manifest_julia = None
    match = re.search(r'^julia_version = "(.*)"$', manifest_text, re.M)
    if match:
        manifest_julia = match.group(1)
    manifest_project_hash = None
    match = re.search(r'^project_hash = "(.*)"$', manifest_text, re.M)
    if match:
        manifest_project_hash = match.group(1)
    if manifest_julia != "1.12.6":
        raise SystemExit(f"T4 Manifest julia_version is not the registered pin: {manifest_julia}")
    if manifest_field("WaterLily", "version") != "1.8.0":
        raise SystemExit("T4 Manifest WaterLily version drift")
    cuda_version = manifest_field("CUDA", "version")
    if cuda_version is None:
        raise SystemExit("T4 Manifest has no CUDA entry")

    document: dict[str, Any] = {
        "schema_version": 1,
        "kind": "sdf_native_w0b_t4_cuda_env",
        "gate_id": "sdf_native_w0b_t4_cuda_env_2026_09",
        "evidence_class": "capability_and_contract",
        "immutable": True,
        "solver_started": False,
        "existing_evidence_modified": False,
        "generated_on": {
            "platform": "Colab managed runtime (Linux x86_64) driven through the colab-mcp browser connection",
            "base_commit": base_commit,
            "recording_host": platform.platform(),
            "python": sys.version.split()[0],
        },
        "registered_criteria": {
            "path": CRITERIA_PATH.relative_to(ROOT).as_posix(),
            "sha256": criteria_sha,
        },
        "environment": {
            "project": {
                "path": T4_PROJECT.relative_to(ROOT).as_posix(),
                "sha256": project_sha,
                "deps": ["CUDA", "WaterLily"],
            },
            "manifest": {
                "path": T4_MANIFEST.relative_to(ROOT).as_posix(),
                "sha256": manifest_sha,
                "julia_version": manifest_julia,
                "project_hash": manifest_project_hash,
                "waterlily": manifest_field("WaterLily", "version"),
                "cuda_jl": cuda_version,
            },
            "gpu": {
                "name": gpu_name,
                "compute_capability": identity_fields["gpu_compute_capability"],
                "memory_total_mib": memory_mib,
                "total_memory_bytes": memory_bytes,
                "driver_version": identity_fields["cuda_driver_version"],
                "cuda_runtime_version": identity_fields["cuda_runtime_version"],
                "uuid": gpu_uuid,
            },
            "runtime": {
                "julia_version": identity_fields["julia_version"],
                "waterlily_version": identity_fields["waterlily_version"],
                "cuda_jl_version": identity_fields["cuda_jl_version"],
            },
            "cpu_environment_untouched": {
                "manifest_sha256": CPU_MANIFEST_SHA256,
                "evidence_path": CPU_ENV_EVIDENCE.relative_to(ROOT).as_posix(),
            },
        },
        "gates": gates,
        "artifacts": {
            name: {
                "path": path.relative_to(ROOT).as_posix(),
                "sha256": _sha256_path(path),
            }
            for name, path in artifacts.items()
        },
        "verdict": {
            "w0b_qualified": True,
            "fail_closed": False,
        },
        "claims_supported": [
            "the committed julia/CFDSDFWaterLilyT4 Project/Manifest pair instantiates on the explicitly selected Colab T4 runtime",
            "CUDA.jl is functional on the T4 and the WaterLily CUDA extension activates",
            "CuArray and KernelAbstractions CUDA smoke operations pass",
        ],
        "claims_not_supported": [
            "no WaterLily time step, force value or GridSDF GPU bridge qualification (W1g)",
            "no CUDA/Enzyme reverse capability",
            "no v16, FD gradient, topology or optimizer claim",
            "no absolute, grid-independent, high-Re or full-vehicle downforce claim",
        ],
        "flags": {
            "shape_update_allowed": False,
            "sdf_gradient_qualified": False,
            "waterlily_reverse_cpu_qualified": False,
            "waterlily_reverse_cuda_qualified": False,
            "topology_birth_qualified": False,
        },
    }
    payload = (json.dumps(document, indent=2, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
    _write_immutable(EVIDENCE_PATH, payload)
    sidecar = EVIDENCE_PATH.with_suffix(EVIDENCE_PATH.suffix + ".sha256")
    digest = _sha256_path(EVIDENCE_PATH)
    if sidecar.exists() and sidecar.read_text().strip() != digest:
        raise SystemExit("W0b evidence sidecar mismatch")
    if not sidecar.exists():
        _write_immutable(sidecar, (digest + "\n").encode("utf-8"))
    print(json.dumps({
        "status": "registered",
        "gate_id": document["gate_id"],
        "gpu": gpu_name,
        "cuda_jl": cuda_version,
        "manifest_sha256": manifest_sha,
        "gates_passed": len(gates),
        "evidence": EVIDENCE_PATH.relative_to(ROOT).as_posix(),
        "evidence_sha256": digest,
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
