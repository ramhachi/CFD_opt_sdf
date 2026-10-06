#!/usr/bin/env python3
"""Capture a CLI-backed Kaggle T4 execution-budget preflight without submitting."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess


SESSION_MAX_SECONDS = 12 * 60 * 60
SESSION_DOC = "https://www.kaggle.com/docs/notebooks"
PHASE_BUDGETS = {
    "setup": {"solver_wall_time_cap_s": 0, "kernel_execution_allowance_s": 7200},
    "r6": {"solver_wall_time_cap_s": 6600, "kernel_execution_allowance_s": 11200},
    "formal": {"solver_wall_time_cap_s": 3300, "kernel_execution_allowance_s": 5600},
}


def parse_gpu_quota(quota: str) -> tuple[float, float]:
    match = re.search(r"^GPU\s+([0-9]+(?:\.[0-9]+)?)h\s+([0-9]+(?:\.[0-9]+)?)h",
                      quota, re.MULTILINE)
    if not match:
        raise ValueError("could not parse GPU used/remaining hours from `kaggle quota`")
    return tuple(map(float, match.groups()))


def capture(phase: str, output: Path) -> dict:
    budget = PHASE_BUDGETS[phase]
    version_run = subprocess.run(["kaggle", "--version"], check=True, capture_output=True, text=True)
    quota_run = subprocess.run(["kaggle", "quota"], check=True, capture_output=True, text=True)
    help_run = subprocess.run(["kaggle", "kernels", "push", "--help"],
                              check=True, capture_output=True, text=True)
    version = version_run.stdout.strip()
    quota = quota_run.stdout
    help_text = help_run.stdout + help_run.stderr
    gpu_used_h, gpu_remaining_h = parse_gpu_quota(quota)
    timeout_lines = [line.strip() for line in help_text.splitlines() if "--timeout" in line]
    if not timeout_lines or "Kaggle CLI 2.2.4" not in version:
        raise ValueError("pinned Kaggle CLI version or kernel timeout option is unavailable")
    remaining_s = int(gpu_remaining_h * 3600)
    fits = (budget["kernel_execution_allowance_s"] <= SESSION_MAX_SECONDS
            and budget["kernel_execution_allowance_s"] <= remaining_s)
    result = {
        "kind": "fd08_v2_kaggle_budget_preflight",
        "status": "PASS_CAPABILITY_PREFLIGHT" if fits else "BLOCKED_CAPABILITY_PREFLIGHT",
        "phase": phase,
        "captured_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "cli_version": version,
        "timeout_option_help_lines": timeout_lines,
        "timeout_help_sha256": hashlib.sha256(help_text.encode()).hexdigest(),
        "quota_command": "kaggle quota",
        "quota_output": quota,
        "gpu_quota_used_hours": gpu_used_h,
        "gpu_quota_remaining_hours": gpu_remaining_h,
        "gpu_quota_remaining_seconds_floor": remaining_s,
        "platform_max_cpu_gpu_session_seconds": SESSION_MAX_SECONDS,
        "platform_limit_source": SESSION_DOC,
        "requested": budget,
        "checks": {
            "cli_timeout_option_available": True,
            "kernel_allowance_within_platform_session_limit": budget["kernel_execution_allowance_s"] <= SESSION_MAX_SECONDS,
            "kernel_allowance_within_current_gpu_quota": budget["kernel_execution_allowance_s"] <= remaining_s,
        },
        "runtime_guarantee": False,
    }
    if output.exists():
        raise FileExistsError(f"refusing to overwrite budget preflight: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, sort_keys=True, indent=2, allow_nan=False) + "\n")
    output.with_suffix(output.suffix + ".sha256").write_text(
        hashlib.sha256(output.read_bytes()).hexdigest() + "\n"
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=PHASE_BUDGETS, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = capture(args.phase, args.output)
    print(json.dumps({key: result[key] for key in (
        "status", "phase", "cli_version", "gpu_quota_remaining_hours",
        "platform_max_cpu_gpu_session_seconds", "requested", "checks",
    )}, sort_keys=True, indent=2))
    return 0 if result["status"] == "PASS_CAPABILITY_PREFLIGHT" else 2


if __name__ == "__main__":
    raise SystemExit(main())
