"""Tests for Kaggle CLI budget parsing and fail-closed registration checks."""

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "scripts")]

from check_fd08_v2_kaggle_budget import parse_gpu_quota
from register_fd08_v2_r6 import load_budget_evidence


def test_parse_gpu_quota_reads_used_and_remaining_columns():
    output = (
        "resource  used   remaining  total   refreshAt\n"
        "--------  -----  ---------  ------  -------------------\n"
        "GPU       7.45h  22.55h     30.00h  2026-10-10T00:00:00\n"
        "TPU       0.00h  20.00h     20.00h  2026-10-10T00:00:00\n"
    )
    assert parse_gpu_quota(output) == (7.45, 22.55)


def test_registration_budget_evidence_requires_fresh_exact_caps_and_sidecar(tmp_path):
    evidence = {
        "kind": "fd08_v2_kaggle_budget_preflight",
        "status": "PASS_CAPABILITY_PREFLIGHT",
        "phase": "r6",
        "captured_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "cli_version": "Kaggle CLI 2.2.4",
        "timeout_option_help_lines": ["-t, --timeout TIMEOUT"],
        "platform_max_cpu_gpu_session_seconds": 43200,
        "gpu_quota_remaining_seconds_floor": 81180,
        "requested": {"solver_wall_time_cap_s": 6600, "kernel_execution_allowance_s": 11200},
        "checks": {
            "cli_timeout_option_available": True,
            "kernel_allowance_within_platform_session_limit": True,
            "kernel_allowance_within_current_gpu_quota": True,
        },
        "runtime_guarantee": False,
    }
    path = tmp_path / "budget.json"
    blob = json.dumps(evidence, sort_keys=True).encode()
    path.write_bytes(blob)
    path.with_suffix(".json.sha256").write_text(hashlib.sha256(blob).hexdigest() + "\n")

    verified, digest = load_budget_evidence(path, "r6", 6600, 11200)
    assert verified["phase"] == "r6"
    assert digest == hashlib.sha256(blob).hexdigest()
    with pytest.raises(ValueError, match="caps are not currently available"):
        load_budget_evidence(path, "r6", 6600, 11201)


def test_budget_registration_rejects_stale_snapshot_and_tampered_sidecar(tmp_path):
    evidence = {
        "kind": "fd08_v2_kaggle_budget_preflight",
        "status": "PASS_CAPABILITY_PREFLIGHT",
        "phase": "r6",
        "captured_utc": "2026-10-01T00:00:00Z",
        "cli_version": "Kaggle CLI 2.2.4",
        "timeout_option_help_lines": ["-t, --timeout TIMEOUT"],
        "platform_max_cpu_gpu_session_seconds": 43200,
        "gpu_quota_remaining_seconds_floor": 81180,
        "requested": {"solver_wall_time_cap_s": 6600, "kernel_execution_allowance_s": 11200},
        "checks": {
            "cli_timeout_option_available": True,
            "kernel_allowance_within_platform_session_limit": True,
            "kernel_allowance_within_current_gpu_quota": True,
        },
        "runtime_guarantee": False,
    }
    path = tmp_path / "budget.json"
    blob = json.dumps(evidence, sort_keys=True).encode()
    path.write_bytes(blob)
    sidecar = path.with_suffix(".json.sha256")
    sidecar.write_text(hashlib.sha256(blob).hexdigest() + "\n")
    with pytest.raises(ValueError, match="caps are not currently available"):
        load_budget_evidence(path, "r6", 6600, 11200)

    evidence["captured_utc"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    blob = json.dumps(evidence, sort_keys=True).encode()
    path.write_bytes(blob)
    sidecar.write_text("0" * 64 + "\n")
    with pytest.raises(ValueError, match="sidecar mismatch"):
        load_budget_evidence(path, "r6", 6600, 11200)
