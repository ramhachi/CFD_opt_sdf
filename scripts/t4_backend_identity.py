"""Reusable T4 backend identity verifier.

The W0b record is the single registered T4 backend identity.  Future T4 jobs
must match it exactly; any drift is fail-closed.  Registered fields:

    W0b evidence SHA-256
    Project.toml SHA-256
    Manifest.toml SHA-256
    GPU name / UUID / compute capability
    CUDA.jl version
    WaterLily version
    Julia version
    CUDA runtime identity
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
W0B_RESULT_PATH = ROOT / "docs/evidence/sdf_native_w0b_t4_cuda_env_2026_09.json"
EXPECTED_W0B_SHA256 = "4f822429656f36020410bcae6c375591d512ac3f4f58011e263346515f1237e6"
T4_PROJECT_PATH = ROOT / "julia/CFDSDFWaterLilyT4/Project.toml"
T4_MANIFEST_PATH = ROOT / "julia/CFDSDFWaterLilyT4/Manifest.toml"

IDENTITY_FIELDS = (
    "gpu_name",
    "gpu_uuid",
    "compute_capability",
    "cuda_jl_version",
    "waterlily_version",
    "julia_version",
    "cuda_runtime_version",
)


def _sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def registered_identity() -> dict[str, str]:
    """The W0b-registered T4 backend identity, derived from the W0b evidence."""
    if _sha256_path(W0B_RESULT_PATH) != EXPECTED_W0B_SHA256:
        raise RuntimeError("W0b evidence sha256 drift; the registered T4 identity cannot be trusted")
    document = json.loads(W0B_RESULT_PATH.read_text(encoding="utf-8"))
    environment = document["environment"]
    return {
        "w0b_evidence_sha256": EXPECTED_W0B_SHA256,
        "project_sha256": environment["project"]["sha256"],
        "manifest_sha256": environment["manifest"]["sha256"],
        "gpu_name": environment["gpu"]["name"],
        "gpu_uuid": environment["gpu"]["uuid"],
        "compute_capability": environment["gpu"]["compute_capability"],
        "cuda_jl_version": environment["runtime"]["cuda_jl_version"],
        "waterlily_version": environment["runtime"]["waterlily_version"],
        "julia_version": environment["runtime"]["julia_version"],
        "cuda_runtime_version": environment["gpu"]["cuda_runtime_version"],
    }


def verify_backend_identity(observed: dict[str, str], *, root: Path = ROOT) -> dict[str, object]:
    """Compare an observed T4 identity against the W0b registration.

    Returns `{"pass": bool, "registered": {...}, "mismatches": [...]}`.
    The repository T4 Project/Manifest files are hashed as part of the check.
    """
    registered = registered_identity()
    mismatches: list[dict[str, str]] = []
    project_path = root / "julia/CFDSDFWaterLilyT4/Project.toml"
    manifest_path = root / "julia/CFDSDFWaterLilyT4/Manifest.toml"
    if _sha256_path(project_path) != registered["project_sha256"]:
        mismatches.append({
            "field": "project_sha256",
            "expected": registered["project_sha256"],
            "observed": _sha256_path(project_path),
        })
    if _sha256_path(manifest_path) != registered["manifest_sha256"]:
        mismatches.append({
            "field": "manifest_sha256",
            "expected": registered["manifest_sha256"],
            "observed": _sha256_path(manifest_path),
        })
    for field in IDENTITY_FIELDS:
        expected = registered[field]
        actual = observed.get(field)
        if actual is None or str(actual) != str(expected):
            mismatches.append({
                "field": field,
                "expected": str(expected),
                "observed": str(actual),
            })
    return {
        "pass": not mismatches,
        "registered": registered,
        "observed": dict(observed),
        "mismatches": mismatches,
    }


KAGGLE_EXACT_FIELDS = (
    "gpu_name",
    "compute_capability",
    "cuda_jl_version",
    "waterlily_version",
    "julia_version",
    "cuda_runtime_version",
    "cuda_driver_api_version",
)
_GPU_UUID = re.compile(r"GPU-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


def verify_kaggle_backend_identity(observed: dict, backend: dict) -> dict[str, object]:
    """Compare an observed Kaggle T4 identity against a registered `backend` block.

    Kaggle rotates the physical GPU per run, so the UUID is never compared with a
    registered value: it must only be well-formed, unique, and in the inventory.
    The NVIDIA driver is matched by the registered pattern.
    """
    mismatches: list[dict[str, str]] = []

    def check(field: str, ok: bool, expected: object) -> None:
        if not ok:
            mismatches.append({"field": field, "expected": str(expected), "observed": str(observed.get(field))})

    for field in KAGGLE_EXACT_FIELDS:
        check(field, str(observed.get(field)) == str(backend[field]), backend[field])
    check("driver_version", re.fullmatch(backend["driver_version_pattern"], str(observed.get("driver_version"))) is not None,
          backend["driver_version_pattern"])
    for field in ("memory_total_mib", "project_sha256", "manifest_sha256"):
        check(field, observed.get(field) == backend[field], backend[field])
    inventory = list(observed.get("inventory_uuids") or [])
    uuid = str(observed.get("gpu_uuid"))
    check("gpu_uuid", _GPU_UUID.fullmatch(uuid) is not None and uuid in inventory
          and len(set(inventory)) == len(inventory), "well-formed, unique, in inventory")
    check("gpu_count", len(inventory) >= backend["gpu_count_min"], f">={backend['gpu_count_min']}")
    return {"pass": not mismatches, "observed": dict(observed), "mismatches": mismatches}
