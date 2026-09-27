from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from t4_backend_identity import registered_identity, verify_backend_identity  # noqa: E402


def _observed_from_registered() -> dict[str, str]:
    identity = registered_identity()
    return {
        key: identity[key]
        for key in (
            "gpu_name",
            "gpu_uuid",
            "compute_capability",
            "cuda_jl_version",
            "waterlily_version",
            "julia_version",
            "cuda_runtime_version",
        )
    }


def test_registered_identity_matches_w0b_record() -> None:
    identity = registered_identity()
    assert identity["gpu_name"] == "Tesla T4"
    assert identity["gpu_uuid"].startswith("GPU-")
    assert identity["compute_capability"] == "7.5.0"
    assert identity["cuda_jl_version"] == "6.3.1"
    assert identity["waterlily_version"] == "1.8.0"
    assert identity["julia_version"] == "1.12.6"
    assert identity["cuda_runtime_version"] == "12.8.0"


def test_verify_matching_identity_passes() -> None:
    result = verify_backend_identity(_observed_from_registered())
    assert result["pass"] is True
    assert result["mismatches"] == []


def test_verify_drifted_gpu_fails_fail_closed() -> None:
    observed = _observed_from_registered()
    observed["gpu_uuid"] = "GPU-00000000-0000-0000-0000-000000000000"
    result = verify_backend_identity(observed)
    assert result["pass"] is False
    assert any(item["field"] == "gpu_uuid" for item in result["mismatches"])


def test_verify_drifted_version_fails_fail_closed() -> None:
    observed = _observed_from_registered()
    observed["cuda_jl_version"] = "0.0.1"
    result = verify_backend_identity(observed)
    assert result["pass"] is False
    assert any(item["field"] == "cuda_jl_version" for item in result["mismatches"])


def test_verify_missing_field_fails_fail_closed() -> None:
    observed = _observed_from_registered()
    del observed["julia_version"]
    result = verify_backend_identity(observed)
    assert result["pass"] is False
    assert any(item["field"] == "julia_version" for item in result["mismatches"])
