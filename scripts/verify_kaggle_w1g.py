#!/usr/bin/env python3
"""Independently check a version-specific Kaggle W1g artifact download."""

import argparse
import json
from pathlib import Path

from verify_kaggle_k0 import ROOT, require, sha256, verify_files


CRITERIA = ROOT / "docs/evidence/kaggle_w1g_criteria_2026_09_round2.json"
K0_RESULT = ROOT / "docs/evidence/kaggle_k0_result_2026_09.json"
RUNNER = ROOT / "infra/kaggle/kernel/runner.py"
FIXTURE = ROOT / "scripts/w1g_gpu_geometry_fixture.jl"


def verify(download):
    criteria = json.loads(CRITERIA.read_text())
    require(sha256(CRITERIA) == CRITERIA.with_suffix(".json.sha256").read_text().strip(),
            "W1g criteria hash mismatch")
    require(sha256(FIXTURE) == criteria["fixture"]["script_sha256"],
            "W1g registered fixture source mismatch")
    require(sha256(K0_RESULT) == criteria["inputs"]["k0_result_sha256"],
            "K0 prerequisite hash mismatch")
    folder = download / "w1g"
    nfiles = verify_files(folder)
    outcome = json.loads((folder / "outcome.json").read_text())
    summary = json.loads((folder / "fixture.summary.json").read_text())
    require(outcome["fixture_summary"] == summary, "W1g summary duplication mismatch")
    require(outcome["criteria_sha256"] == sha256(CRITERIA), "W1g criteria binding mismatch")
    require(outcome["source_commit"] == criteria["source_commit"], "W1g source commit mismatch")
    fingerprint = json.loads((folder / "fingerprint.json").read_text())
    require(fingerprint["source_commit"] == criteria["source_commit"],
            "W1g runner source commit mismatch")
    require(fingerprint["runner_sha256"] == sha256(RUNNER), "W1g runner source mismatch")
    require(outcome["project_sha256"] == criteria["inputs"]["project_sha256"],
            "W1g Project mismatch")
    require(outcome["manifest_sha256"] == criteria["inputs"]["manifest_sha256"],
            "W1g Manifest mismatch")
    rows = outcome["gpu_inventory"]
    require(fingerprint["gpu_csv"] == rows, "W1g inventory binding mismatch")
    require(len(rows) == 2 and all("Tesla T4" in row for row in rows), "W1g two-T4 inventory mismatch")
    require(all(row.split(", ")[-1] == "580.159.04" for row in rows), "W1g driver cohort mismatch")
    uuids = [row.split(", ")[2] for row in rows]
    require(len(set(uuids)) == 2 and all(uuid.startswith("GPU-") for uuid in uuids),
            "W1g GPU UUID inventory invalid")
    identity = summary["backend_identity"]
    require(identity == {
        "gpu_name": "Tesla T4", "gpu_uuid": uuids[0],
        "compute_capability": "7.5.0", "cuda_jl_version": "6.3.1",
        "waterlily_version": "1.8.0", "julia_version": "1.12.6",
        "cuda_runtime_version": "13.3.0",
    }, "W1g selected GPU/runtime identity mismatch")
    smoke = (folder / "julia_smoke.log").read_text()
    require("W0B_SMOKE_DONE" in smoke and "CUDA_FUNCTIONAL true" in smoke
            and "GPU_COMPUTE_CAPABILITY 7.5.0" in smoke
            and "CUDA_RUNTIME_VERSION 13.3.0" in smoke,
            "W1g Julia CUDA smoke mismatch")
    gates = {
        "G1_device_copy": summary["source_phi_sha256"] == criteria["inputs"]["canonical_cpu_phi_sha256"]
                          and summary["device_roundtrip_sha256"] == summary["source_phi_sha256"],
        "G2_kernel": summary["mode"] == "gpu" and summary["probe_count"] == 200012
                     and summary["bulk_box"] == 100000 and summary["bulk_band"] == 100000
                     and summary["representative_count"] == 12,
        "G3_finite": summary["all_finite"] is True,
        "G4_sign": summary["sign_violations"] == 0 and summary["sign_gated_probes"] > 0,
        "G5_value": summary["max_value_error_world_m"] <= 1e-5,
        "G6_normal": summary["max_normal_error"] <= 1e-3 and summary["normal_gated_probes"] > 0,
        "G7_outside": summary["outside_exact"] is True and summary["outside_probes"] == 6,
        "G8_no_scalar_fallback": summary["scalar_index_blocked"] is True,
        "G9_backend": True,
    }
    require(outcome["gates"] == gates and all(gates.values()), "W1g geometry gate failed")
    return {"verified_files": nfiles, "probe_count": summary["probe_count"],
            "max_value_error_world_m": summary["max_value_error_world_m"],
            "max_normal_error": summary["max_normal_error"],
            "selected_gpu_uuid": identity["gpu_uuid"]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("download", type=Path, help="version-specific kaggle kernels output directory")
    print(json.dumps(verify(parser.parse_args().download), indent=2, sort_keys=True))
