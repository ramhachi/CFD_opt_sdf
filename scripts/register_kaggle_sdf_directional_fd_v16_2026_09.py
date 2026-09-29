#!/usr/bin/env python3
"""Freeze a directional-FD round only after exact W3/W4 host PASS evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import platform
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from cfd_sdf.design.sdf_state import SDFDesignState
from cfd_sdf.gradients.directional_fd import (
    DIRECTION_IDS,
    EPSILON_LADDER_M,
    SDF_MARGIN_GATE_M,
    direction_sha256,
    generate_directions,
    perturbation_case_id,
    perturbed_state,
    phi_sha256,
    registered_run_order,
    validate_directions,
    zero_level_margin_m,
)


ROOT = Path(__file__).resolve().parents[1]
DRAFT = ROOT / "docs/evidence/sdf_directional_fd_v16_criteria_draft_2026_09.json"
OUTPUT = ROOT / "docs/evidence/sdf_directional_fd_v16_criteria_2026_09_round1.json"
DEFAULT_STATE = ROOT / "work/kaggle_w3_v16_dataset_registered_3c54f386/sdf_design_state.npz"
W3_CRITERIA = "docs/evidence/kaggle_w3_v16_primal_criteria_2026_09_round4.json"
W3_RESULT = "docs/evidence/kaggle_w3_v16_primal_result_round4_2026_09.json"
W4_CRITERIA = "docs/evidence/kaggle_w4_v16_sensitivity_criteria_2026_09_round4.json"
W4_RESULT = "docs/evidence/kaggle_w4_v16_sensitivity_result_round4_2026_09.json"
DATASET_ID = "ramhachi888/cfd-opt-sdf-v16-directional-fd-oracle"
ROUND1_CRITERIA = "docs/evidence/sdf_directional_fd_v16_criteria_2026_09_round1.json"
ROUND1_SUBMISSION_DIAGNOSTIC = (
    "docs/evidence/sdf_directional_fd_v16_round1_kernel_submission_diagnostic_2026_09.json"
)
ROUND2_CRITERIA = "docs/evidence/sdf_directional_fd_v16_criteria_2026_09_round2.json"
ROUND2_KERNEL1_DIAGNOSTIC = (
    "docs/evidence/sdf_directional_fd_v16_round2_kernel1_diagnostic_2026_09.json"
)
ROUND3_CRITERIA = "docs/evidence/sdf_directional_fd_v16_criteria_2026_09_round3.json"
ROUND3_KERNEL2_SUBMISSION = (
    "docs/evidence/sdf_directional_fd_v16_round3_kernel2_submission_2026_09.json"
)
ROUND3_KERNEL2_DIAGNOSTIC = (
    "docs/evidence/sdf_directional_fd_v16_round3_kernel2_diagnostic_2026_09.json"
)
ROUND3_FAILURE_ANALYSIS = (
    "docs/evidence/sdf_directional_fd_v16_round3_kernel2_failure_analysis_2026_09.json"
)
ROUND3_DATASET_VERIFICATION = (
    "docs/evidence/sdf_directional_fd_v16_dataset_round3_verification_2026_09.json"
)
ROUND4_CRITERIA = "docs/evidence/sdf_directional_fd_v16_criteria_2026_09_round4.json"
ROUND4_KERNEL3_SUBMISSION = (
    "docs/evidence/sdf_directional_fd_v16_round4_kernel3_submission_2026_09.json"
)
ROUND4_KERNEL3_DIAGNOSTIC = (
    "docs/evidence/sdf_directional_fd_v16_round4_kernel3_diagnostic_2026_09.json"
)
ROUND4_DATASET_VERIFICATION = (
    "docs/evidence/sdf_directional_fd_v16_dataset_round4_verification_2026_09.json"
)
ROUND1_CRITERIA_FILE_SHA256 = "ad0bd7dcc6f8e2f0927799fe1c9818e58c43fbc4205312a5ad4c397d61f6fdc6"
ROUND1_CRITERIA_CANONICAL_SHA256 = "a110132ff6df6859fe4e38b5e4cb634c8ef2ac0015cfb6fbc5562d63c5bc292c"
ROUND1_SUBMISSION_DIAGNOSTIC_SHA256 = "3cabf32761785ac1f9cf1bf353b92e80649259a36197ba88e89f644b62edb9b8"
ROUND2_CRITERIA_FILE_SHA256 = "150a60232f1adb413fa7021833943c8effe5b91ef068909d4d9364112c248e1b"
ROUND2_CRITERIA_CANONICAL_SHA256 = "91756109ce69fbe7c77cb0f18417f6d48619bb0020585db1aab7f8e891d19bfa"
ROUND2_KERNEL1_DIAGNOSTIC_SHA256 = "1c39d56953ef6e15979ea84bd2a5cca209af8689bb491be777d50e6f16a6d06a"
ROUND2_SOURCE_COMMIT = "178792e9065df87d87ea1d445baaedace404304e"
ROUND3_CRITERIA_FILE_SHA256 = "45fb570bc3628ff083d5cd34f496e352f6ec0834ac93f381909bef1c4d13f6c5"
ROUND3_CRITERIA_CANONICAL_SHA256 = "fe49a91e5800460dc4560f453b72fd25f12158ecd4a099a1e940cbf434db8d52"
ROUND3_KERNEL2_SUBMISSION_SHA256 = "379ad6ac7968109bbb7962afbfc03f5a1be8f8e9d6a7e6eed3f15d90c3db4629"
ROUND3_KERNEL2_DIAGNOSTIC_SHA256 = "4044e4f01508590f622e89194427af47c599d00959cf721a0f143b136d746fae"
ROUND3_FAILURE_ANALYSIS_SHA256 = "faf0f9b8100b02f303b029a3644cbf5c3df4e3e0a18d935014401142936c8596"
ROUND3_DATASET_VERIFICATION_SHA256 = "aad6667f391543d78a338d089daf737203222e7ec54b4ffe871ffd740745d48c"
ROUND3_SOURCE_COMMIT = "9978eb4f19c716b9666c50c18261738edd978e4f"
ROUND4_CRITERIA_FILE_SHA256 = "ace4e53963ee7d37d7806f48ef1ef449380294c0a5216043e50558f1d31192fd"
ROUND4_CRITERIA_CANONICAL_SHA256 = "949d998bb9e5b83ddbb2a24efc25b57754f4db29568e0a0f6e8b062647206db9"
ROUND4_KERNEL3_SUBMISSION_SHA256 = "7906199306835e1da529b52313e7f27b7e18bf3665c091e6c4d099b340ee52bb"
ROUND4_KERNEL3_DIAGNOSTIC_SHA256 = "f53ce0cf2784db810cdec39ba05448795010210e5e39e664810ae9f84527ded8"
ROUND4_DATASET_VERIFICATION_SHA256 = "e3f4fecde25f4161595deda684a2db7a9bd5d83298d299cf22f4745dda4831aa"
ROUND4_SOURCE_COMMIT = "8bf88756791213ac75b3c36ab6316323653d5c9a"
RETRY_KERNEL_ID = DATASET_ID + "-kernel"
RETRY_KERNEL_TITLE = "CFD Opt SDF v16 Directional FD Oracle Kernel"
SOURCE_PATHS = {
    "directional_fd_contract": "src/cfd_sdf/gradients/directional_fd.py",
    "criteria_draft": "docs/evidence/sdf_directional_fd_v16_criteria_draft_2026_09.json",
    "criteria_registrar": "scripts/register_kaggle_sdf_directional_fd_v16_2026_09.py",
    "dataset_preparer": "scripts/prepare_kaggle_sdf_directional_fd_v16_dataset_2026_09.py",
    "julia_job": "scripts/waterlily_sdf_directional_fd_v16_job.jl",
    "kernel_runner": "infra/kaggle/kernel_sdf_directional_fd_v16/runner.py",
    "kernel_metadata": "infra/kaggle/kernel_sdf_directional_fd_v16/kernel-metadata.json",
    "host_verifier": "scripts/verify_kaggle_sdf_directional_fd_v16.py",
    "contract_tests": "tests/test_sdf_directional_fd_contract.py",
    "harness_tests": "tests/test_kaggle_sdf_directional_fd_v16.py",
    "owner_run_type": "julia/CFDSDFWaterLily/src/OwnedV16Run.jl",
    "profile_adapter": "julia/CFDSDFWaterLily/src/V16PhysicalProfile.jl",
    "grid_sdf": "julia/CFDSDFWaterLily/src/GridSDFBody.jl",
    "device_grid": "julia/CFDSDFWaterLily/src/DeviceGridSDF.jl",
    "w4_case_module": "julia/CFDSDFWaterLily/src/V16W4Sensitivity.jl",
    "project": "julia/CFDSDFWaterLilyT4/Project.toml",
    "manifest": "julia/CFDSDFWaterLilyT4/Manifest.toml",
    "kaggle_smoke": "scripts/w0b_t4_smoke.jl",
    "w3_criteria": W3_CRITERIA,
    "w3_result": W3_RESULT,
    "w3_host_verifier": "scripts/verify_kaggle_w3_v16.py",
    "w4_criteria": W4_CRITERIA,
    "w4_result": W4_RESULT,
    "w4_host_verifier": "scripts/verify_kaggle_w4_v16.py",
    "round1_submission_diagnostic": ROUND1_SUBMISSION_DIAGNOSTIC,
    "round2_criteria": ROUND2_CRITERIA,
    "round2_kernel1_diagnostic": ROUND2_KERNEL1_DIAGNOSTIC,
    "round3_criteria": ROUND3_CRITERIA,
    "round3_kernel2_submission": ROUND3_KERNEL2_SUBMISSION,
    "round3_kernel2_diagnostic": ROUND3_KERNEL2_DIAGNOSTIC,
    "round3_failure_analysis": ROUND3_FAILURE_ANALYSIS,
    "round3_dataset_verification": ROUND3_DATASET_VERIFICATION,
}
BACKEND_KEYS = (
    "accelerator", "machine_shape", "gpu_count", "gpu_name", "driver_version",
    "cuda_visible_devices", "julia_archive_sha256", "compute_capability",
    "cuda_driver_api_version", "cuda_runtime_version", "cuda_jl_version",
    "julia_version", "julia_threads", "waterlily_version", "waterlily_backend",
)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256(path: Path) -> str:
    return sha256_bytes(Path(path).read_bytes())


def json_hash(value: dict) -> str:
    return sha256_bytes(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                   allow_nan=False).encode())


def source_entry(path: str) -> dict:
    file_path = ROOT / path
    if not file_path.is_file():
        raise ValueError(f"required FD source file is missing: {path}")
    return {"path": path, "sha256": sha256(file_path), "location": "source_repo"}


def load_prerequisites() -> tuple[dict, dict, dict, dict, str, str, str, str]:
    def read(path_text):
        path = ROOT / path_text
        sidecar = path.with_suffix(path.suffix + ".sha256")
        if not path.is_file() or not sidecar.is_file():
            raise ValueError(f"required immutable prerequisite or sidecar missing: {path_text}")
        digest = sha256(path)
        if sidecar.read_text().strip() != digest:
            raise ValueError(f"prerequisite sidecar mismatch: {path_text}")
        return json.loads(path.read_text()), digest

    w3_criteria, w3_criteria_sha = read(W3_CRITERIA)
    w3_result, w3_result_sha = read(W3_RESULT)
    w4_criteria, w4_criteria_sha = read(W4_CRITERIA)
    w4_result, w4_result_sha = read(W4_RESULT)
    if (w3_criteria_sha != "eeae43e8930f1dc4bb8d3a1099edce76e75390fba24176c9ad70c8248ac1eebb"
            or w3_result_sha != "d00949d0ea2f2ddcd222f0f376449d9d7aba9b634a650cf75822c640b9e6f4a8"
            or w4_criteria_sha != "3efc8133c8d1b7d306041ee3f49ec5a708024f189095bdb0f13646fe329b578f"
            or w4_result_sha != "87a881784dd42ef9c2c43ee78be761e8165e727f01df7d544765006d9c1b2fae"):
        raise ValueError("exact registered W3/W4 prerequisite SHA differs from this task")
    if (w3_result.get("verdict") != "PASS"
            or w3_result.get("host_verification_passed") is not True
            or not all(w3_result.get("gates", {}).values())):
        raise ValueError("W3 prerequisite is not exact host-verified PASS")
    if (w4_result.get("verdict") != "PASS"
            or w4_result.get("host_verification_passed") is not True
            or w4_result.get("w4_sensitivity_matrix_passed") is not True
            or w4_result.get("fd_entry_gate") != "OPEN"
            or w4_result.get("formal_fd_measurement_started") is not False
            or w4_result.get("extended_domain_fine_grid_required") is not False
            or not all(w4_result.get("gates", {}).values())):
        raise ValueError("W4 prerequisite is not exact host-verified PASS with FD entry OPEN")
    observed_w4_backend = w4_result.get("backend_identity")
    backend = observed_w4_backend.get("registered_backend") if isinstance(observed_w4_backend, dict) else None
    if (not isinstance(backend, dict) or set(backend) != set(BACKEND_KEYS)
            or backend != w3_result.get("backend_identity")):
        raise ValueError("W3 and W4 observed backend identity does not match")
    selected_w4_gpu = observed_w4_backend.get("selected_gpu_uuid")
    if not str(selected_w4_gpu or "").startswith("GPU-"):
        raise ValueError("W4 result selected GPU UUID is missing or inconsistent")
    flow16 = w4_result.get("case_measurements", {}).get("flow_16", {}).get("force_metrics_host_recomputed", {})
    for key, draft_key in (("drag_time_weighted_n", "flow16_drag_reference_n"),
                           ("downforce_time_weighted_n", "flow16_downforce_reference_n")):
        if not math.isclose(float(flow16.get(key, math.nan)),
                            float(json.loads(DRAFT.read_text())["w4_cross_check"][draft_key]),
                            rel_tol=0.0, abs_tol=1e-12):
            raise ValueError(f"W4 flow_16 host-recomputed {key} differs from the preregistration draft")
    return (w3_criteria, w3_result, w4_criteria, w4_result,
            w3_criteria_sha, w3_result_sha, w4_criteria_sha, w4_result_sha)


def git_blob_sha(commit: str, path: str) -> str:
    data = subprocess.check_output(["git", "-C", str(ROOT), "show", f"{commit}:{path}"])
    return sha256_bytes(data)


def load_round1_submission_retry_binding() -> dict:
    criteria_path = ROOT / ROUND1_CRITERIA
    criteria_sidecar = criteria_path.with_suffix(criteria_path.suffix + ".sha256")
    diagnostic_path = ROOT / ROUND1_SUBMISSION_DIAGNOSTIC
    diagnostic_sidecar = diagnostic_path.with_suffix(diagnostic_path.suffix + ".sha256")
    if not all(path.is_file() for path in (
            criteria_path, criteria_sidecar, diagnostic_path, diagnostic_sidecar)):
        raise ValueError("round-1 immutable criteria and submission diagnostic must be preserved")
    criteria_sha = sha256(criteria_path)
    diagnostic_sha = sha256(diagnostic_path)
    if (criteria_sha != ROUND1_CRITERIA_FILE_SHA256
            or criteria_sidecar.read_text().strip() != criteria_sha
            or diagnostic_sha != ROUND1_SUBMISSION_DIAGNOSTIC_SHA256
            or diagnostic_sidecar.read_text().strip() != diagnostic_sha):
        raise ValueError("round-1 criteria or diagnostic identity changed")
    criteria = json.loads(criteria_path.read_text())
    diagnostic = json.loads(diagnostic_path.read_text())
    if (criteria.get("criteria_round") != 1
            or criteria.get("immutable") is not True
            or criteria.get("status") != "registered_not_run"
            or criteria.get("formal_measurement_started") is not False
            or criteria.get("criteria_sha256") != ROUND1_CRITERIA_CANONICAL_SHA256
            or criteria.get("kernel_id") != DATASET_ID
            or criteria.get("input_dataset_id") != DATASET_ID
            or diagnostic.get("criteria_round") != 1
            or diagnostic.get("submission", {}).get("kernel_version_created") is not False
            or diagnostic.get("measurement_started") is not False
            or diagnostic.get("dataset", {}).get("payload_hashes_match_local_manifest") is not True):
        raise ValueError("round-1 is not the preserved no-measurement slug-conflict diagnostic")
    return {
        "criteria_path": ROUND1_CRITERIA,
        "criteria_file_sha256": criteria_sha,
        "criteria_canonical_sha256": criteria["criteria_sha256"],
        "submission_diagnostic_path": ROUND1_SUBMISSION_DIAGNOSTIC,
        "submission_diagnostic_sha256": diagnostic_sha,
        "reason": "Kaggle SaveKernel returned HTTP 409 because the round-1 kernel title/slug conflicts with the same-ID private input dataset; no kernel version or solver measurement was created.",
    }


def load_round2_preflight_retry_binding() -> dict:
    criteria_path = ROOT / ROUND2_CRITERIA
    criteria_sidecar = criteria_path.with_suffix(criteria_path.suffix + ".sha256")
    diagnostic_path = ROOT / ROUND2_KERNEL1_DIAGNOSTIC
    diagnostic_sidecar = diagnostic_path.with_suffix(diagnostic_path.suffix + ".sha256")
    if not all(path.is_file() for path in (
            criteria_path, criteria_sidecar, diagnostic_path, diagnostic_sidecar)):
        raise ValueError("round-2 immutable criteria and kernel diagnostic must be preserved")
    criteria_sha = sha256(criteria_path)
    diagnostic_sha = sha256(diagnostic_path)
    if (criteria_sha != ROUND2_CRITERIA_FILE_SHA256
            or criteria_sidecar.read_text().strip() != criteria_sha
            or diagnostic_sha != ROUND2_KERNEL1_DIAGNOSTIC_SHA256
            or diagnostic_sidecar.read_text().strip() != diagnostic_sha):
        raise ValueError("round-2 criteria or kernel diagnostic identity changed")

    criteria = json.loads(criteria_path.read_text())
    diagnostic = json.loads(diagnostic_path.read_text())
    execution = diagnostic.get("runner_execution_state", {})
    julia = diagnostic.get("julia_progress_markers", {})
    expected_status = f'{RETRY_KERNEL_ID}/1 has status "KernelWorkerStatus.ERROR"'
    if (criteria.get("criteria_round") != 2
            or criteria.get("immutable") is not True
            or criteria.get("registered_before_computation") is not True
            or criteria.get("status") != "registered_not_run"
            or criteria.get("formal_measurement_started") is not False
            or criteria.get("source_commit") != ROUND2_SOURCE_COMMIT
            or criteria.get("registered_source_commit") != ROUND2_SOURCE_COMMIT
            or criteria.get("criteria_sha256") != ROUND2_CRITERIA_CANONICAL_SHA256
            or criteria.get("kernel_id") != RETRY_KERNEL_ID
            or criteria.get("input_dataset_id") != DATASET_ID
            or diagnostic.get("kind") != "sdf_directional_fd_flow16_diagnostic"
            or diagnostic.get("criteria_path") != ROUND2_CRITERIA
            or diagnostic.get("criteria_sha256") != criteria_sha
            or diagnostic.get("source_commit") != ROUND2_SOURCE_COMMIT
            or diagnostic.get("dataset_id") != DATASET_ID
            or diagnostic.get("dataset_version") != 2
            or diagnostic.get("kernel_id") != RETRY_KERNEL_ID
            or diagnostic.get("kernel_version") != 1
            or diagnostic.get("terminal_status") != expected_status
            or diagnostic.get("host_verification_passed") is not False
            or diagnostic.get("host_verifier_error") != "ValueError: FD Kaggle output has no DONE marker"
            or diagnostic.get("output_manifest_consistent") is not True
            or execution.get("stage") != "host_input_preflight"
            or execution.get("solver_started") is not False
            or execution.get("solver_step_invoked") != []
            or execution.get("solver_step_returned") != []
            or "NameError: name 'phi_sha256' is not defined" not in execution.get("failure", "")
            or any(julia.get(key) != [] for key in (
                "run_started", "run_finished", "solver_step_invoked", "solver_step_returned"))
            or diagnostic.get("runner_outcome") is not None
            or diagnostic.get("sdf_directional_fd_oracle_qualified") is not False
            or diagnostic.get("sdf_directional_fd_flow16_qualified") is not False
            or diagnostic.get("sdf_gradient_field_qualified") is not False
            or diagnostic.get("gradient_qualified") is not False
            or diagnostic.get("reverse_mode_qualified") is not False
            or diagnostic.get("optimizer_qualified") is not False
            or diagnostic.get("shape_update_allowed") is not False):
        raise ValueError("round-2 is not the exact preserved pre-solver host-input failure")

    return {
        "criteria_path": ROUND2_CRITERIA,
        "criteria_file_sha256": criteria_sha,
        "criteria_canonical_sha256": criteria["criteria_sha256"],
        "kernel1_diagnostic_path": ROUND2_KERNEL1_DIAGNOSTIC,
        "kernel1_diagnostic_sha256": diagnostic_sha,
        "kernel_id": RETRY_KERNEL_ID,
        "kernel_version": 1,
        "solver_started": False,
        "solver_step_invoked": [],
        "solver_step_returned": [],
        "reason": (
            "round 2 exact kernel /1 failed before GPU, Julia, or solver measurement because the "
            "registered Python runner referenced canonical host-preflight identity values outside "
            "the scope that created them."
        ),
    }


def load_round3_pre_primal_retry_binding() -> dict:
    paths = {
        "criteria": ROUND3_CRITERIA,
        "submission": ROUND3_KERNEL2_SUBMISSION,
        "diagnostic": ROUND3_KERNEL2_DIAGNOSTIC,
        "failure_analysis": ROUND3_FAILURE_ANALYSIS,
        "dataset_verification": ROUND3_DATASET_VERIFICATION,
    }
    files = {name: ROOT / path for name, path in paths.items()}
    sidecars = {name: path.with_suffix(path.suffix + ".sha256")
                for name, path in files.items()}
    if not all(path.is_file() for path in (*files.values(), *sidecars.values())):
        raise ValueError("round-3 criteria and exact /2 diagnostic evidence must be preserved")
    digests = {name: sha256(path) for name, path in files.items()}
    expected = {
        "criteria": ROUND3_CRITERIA_FILE_SHA256,
        "submission": ROUND3_KERNEL2_SUBMISSION_SHA256,
        "diagnostic": ROUND3_KERNEL2_DIAGNOSTIC_SHA256,
        "failure_analysis": ROUND3_FAILURE_ANALYSIS_SHA256,
        "dataset_verification": ROUND3_DATASET_VERIFICATION_SHA256,
    }
    if any(digests[name] != value for name, value in expected.items()):
        raise ValueError("round-3 evidence file SHA differs from its registered identity")
    if any(sidecars[name].read_text().strip() != digests[name] for name in paths):
        raise ValueError("round-3 evidence sidecar does not match its file")

    criteria = json.loads(files["criteria"].read_text())
    submission = json.loads(files["submission"].read_text())
    diagnostic = json.loads(files["diagnostic"].read_text())
    analysis = json.loads(files["failure_analysis"].read_text())
    dataset = json.loads(files["dataset_verification"].read_text())
    execution = diagnostic.get("runner_execution_state", {})
    julia = diagnostic.get("julia_progress_markers", {})
    exact_kernel = f"{RETRY_KERNEL_ID}/2"
    expected_status = f'{exact_kernel} has status "KernelWorkerStatus.ERROR"'
    expected_copy = "/kaggle/working/sdf_directional_fd_v16/run_queue.tsv"
    if (criteria.get("criteria_round") != 3
            or criteria.get("immutable") is not True
            or criteria.get("registered_before_computation") is not True
            or criteria.get("status") != "registered_not_run"
            or criteria.get("formal_measurement_started") is not False
            or criteria.get("source_commit") != ROUND3_SOURCE_COMMIT
            or criteria.get("registered_source_commit") != ROUND3_SOURCE_COMMIT
            or criteria.get("criteria_sha256") != ROUND3_CRITERIA_CANONICAL_SHA256
            or criteria.get("kernel_id") != RETRY_KERNEL_ID
            or criteria.get("input_dataset_id") != DATASET_ID
            or diagnostic.get("kind") != "sdf_directional_fd_flow16_diagnostic"
            or diagnostic.get("criteria_path") != ROUND3_CRITERIA
            or diagnostic.get("criteria_sha256") != digests["criteria"]
            or diagnostic.get("source_commit") != ROUND3_SOURCE_COMMIT
            or diagnostic.get("dataset_id") != DATASET_ID
            or diagnostic.get("dataset_version") != 3
            or diagnostic.get("kernel_id") != RETRY_KERNEL_ID
            or diagnostic.get("kernel_version") != 2
            or diagnostic.get("terminal_status") != expected_status
            or diagnostic.get("host_verification_passed") is not False
            or diagnostic.get("host_verifier_error") != "ValueError: FD Kaggle output has no DONE marker"
            or diagnostic.get("output_manifest_consistent") is not True
            or execution.get("stage") != "julia_job"
            or execution.get("solver_started") is not False
            or execution.get("solver_step_invoked") != []
            or execution.get("solver_step_returned") != []
            or any(julia.get(key) != [] for key in (
                "run_started", "run_finished", "solver_step_invoked", "solver_step_returned"))
            or diagnostic.get("runner_outcome") is not None
            or submission.get("exact_kernel_ref") != exact_kernel
            or submission.get("registered_criteria_path") != ROUND3_CRITERIA
            or submission.get("registered_source_commit") != ROUND3_SOURCE_COMMIT
            or submission.get("dataset_version") != 3
            or submission.get("terminal_status_observed") is not False
            or dataset.get("dataset_version") != 3
            or dataset.get("criteria_file_sha256") != digests["criteria"]
            or dataset.get("all_paths_sizes_and_sha256_match") is not True
            or dataset.get("host_input_preflight_passed") is not True
            or dataset.get("solver_started") is not False
            or analysis.get("parent_round3_diagnostic_path") != ROUND3_KERNEL2_DIAGNOSTIC
            or analysis.get("parent_round3_diagnostic_sha256") != digests["diagnostic"]
            or analysis.get("failure_stage") != "julia_job pre-primal run-queue snapshot initialization"
            or analysis.get("exact_exception") != "ArgumentError: 'src' and 'dst' refer to the same file/dir. This is not supported."
            or analysis.get("copy_source") != expected_copy
            or analysis.get("copy_destination") != expected_copy
            or analysis.get("copy_paths_identical") is not True
            or analysis.get("queue_rows_read_and_validated_before_failure") != 33
            or analysis.get("julia_job_started") is not True
            or analysis.get("cuda_t4_smoke_completed") is not True
            or analysis.get("solver_started") is not False
            or analysis.get("measurement_thresholds_changed") is not False
            or analysis.get("host_verifier_error") != "ValueError: FD Kaggle output has no DONE marker"
            or any(diagnostic.get(key) is not False for key in (
                "sdf_directional_fd_oracle_qualified", "sdf_directional_fd_flow16_qualified",
                "sdf_gradient_field_qualified", "gradient_qualified", "reverse_mode_qualified",
                "optimizer_qualified", "topology_qualified", "shape_update_allowed"))):
        raise ValueError("round-3 is not the exact preserved pre-primal queue self-copy failure")

    return {
        "criteria_path": ROUND3_CRITERIA,
        "criteria_file_sha256": digests["criteria"],
        "criteria_canonical_sha256": criteria["criteria_sha256"],
        "kernel2_submission_path": ROUND3_KERNEL2_SUBMISSION,
        "kernel2_submission_sha256": digests["submission"],
        "kernel2_diagnostic_path": ROUND3_KERNEL2_DIAGNOSTIC,
        "kernel2_diagnostic_sha256": digests["diagnostic"],
        "failure_analysis_path": ROUND3_FAILURE_ANALYSIS,
        "failure_analysis_sha256": digests["failure_analysis"],
        "dataset_verification_path": ROUND3_DATASET_VERIFICATION,
        "dataset_verification_sha256": digests["dataset_verification"],
        "kernel_id": RETRY_KERNEL_ID,
        "kernel_version": 2,
        "dataset_version": 3,
        "solver_started": False,
        "solver_step_invoked": [],
        "solver_step_returned": [],
        "failure_stage": analysis["failure_stage"],
        "exact_exception": analysis["exact_exception"],
        "copy_source": analysis["copy_source"],
        "copy_destination": analysis["copy_destination"],
        "measurement_thresholds_changed": False,
        "reason": (
            "round 3 exact kernel /2 failed after Julia startup but before any primal step because "
            "the Julia job attempted to copy the run queue from OUT/run_queue.tsv onto itself."
        ),
    }


def load_round4_host_recompute_lifetime_failure_binding() -> dict:
    paths = {
        "criteria": ROUND4_CRITERIA,
        "submission": ROUND4_KERNEL3_SUBMISSION,
        "diagnostic": ROUND4_KERNEL3_DIAGNOSTIC,
        "dataset_verification": ROUND4_DATASET_VERIFICATION,
    }
    expected = {
        "criteria": ROUND4_CRITERIA_FILE_SHA256,
        "submission": ROUND4_KERNEL3_SUBMISSION_SHA256,
        "diagnostic": ROUND4_KERNEL3_DIAGNOSTIC_SHA256,
        "dataset_verification": ROUND4_DATASET_VERIFICATION_SHA256,
    }
    files = {name: ROOT / path for name, path in paths.items()}
    sidecars = {name: path.with_suffix(path.suffix + ".sha256") for name, path in files.items()}
    if not all(path.is_file() for path in (*files.values(), *sidecars.values())):
        raise ValueError("round-4 criteria and terminal evidence with sidecars must be preserved")
    digests = {name: sha256(path) for name, path in files.items()}
    if (any(digests[name] != expected[name] for name in paths)
            or any(sidecars[name].read_text().strip() != digests[name] for name in paths)):
        raise ValueError("round-4 criteria or terminal evidence identity changed")

    criteria = json.loads(files["criteria"].read_text())
    submission = json.loads(files["submission"].read_text())
    diagnostic = json.loads(files["diagnostic"].read_text())
    dataset = json.loads(files["dataset_verification"].read_text())
    execution = diagnostic.get("runner_execution_state", {})
    progress = diagnostic.get("julia_progress_markers", {})
    run_order = criteria.get("run_order")
    exact_kernel = f"{RETRY_KERNEL_ID}/3"
    failure = execution.get("failure", "")
    committed_w4_result_sha = git_blob_sha(ROUND4_SOURCE_COMMIT, W4_RESULT)
    committed_runner_sha = git_blob_sha(
        ROUND4_SOURCE_COMMIT, "infra/kaggle/kernel_sdf_directional_fd_v16/runner.py")
    if (criteria.get("criteria_round") != 4
            or criteria.get("immutable") is not True
            or criteria.get("registered_before_computation") is not True
            or criteria.get("status") != "registered_not_run"
            or criteria.get("formal_measurement_started") is not False
            or criteria.get("criteria_sha256") != ROUND4_CRITERIA_CANONICAL_SHA256
            or criteria.get("source_commit") != ROUND4_SOURCE_COMMIT
            or criteria.get("registered_source_commit") != ROUND4_SOURCE_COMMIT
            or criteria.get("kernel_id") != RETRY_KERNEL_ID
            or criteria.get("input_dataset_id") != DATASET_ID
            or criteria.get("prerequisites", {}).get("w4", {}).get("result_sha256")
                != "87a881784dd42ef9c2c43ee78be761e8165e727f01df7d544765006d9c1b2fae"
            or committed_w4_result_sha != criteria["prerequisites"]["w4"]["result_sha256"]
            or committed_runner_sha != criteria["inputs"]["kernel_runner"]["sha256"]
            or diagnostic.get("kind") != "sdf_directional_fd_flow16_diagnostic"
            or diagnostic.get("criteria_path") != ROUND4_CRITERIA
            or diagnostic.get("criteria_sha256") != digests["criteria"]
            or diagnostic.get("source_commit") != ROUND4_SOURCE_COMMIT
            or diagnostic.get("dataset_id") != DATASET_ID
            or diagnostic.get("dataset_version") != 4
            or diagnostic.get("kernel_id") != RETRY_KERNEL_ID
            or diagnostic.get("kernel_version") != 3
            or diagnostic.get("terminal_status") != f'{exact_kernel} has status "KernelWorkerStatus.ERROR"'
            or diagnostic.get("host_verification_passed") is not False
            or diagnostic.get("host_verifier_error") != "ValueError: FD Kaggle output has no DONE marker"
            or diagnostic.get("output_manifest_consistent") is not True
            or diagnostic.get("runner_outcome") is not None
            or execution.get("stage") != "host_inside_runner_recompute"
            or execution.get("solver_started") is not True
            or progress.get("run_started") != run_order
            or progress.get("run_finished") != run_order
            or progress.get("solver_step_invoked") != run_order
            or progress.get("solver_step_returned") != run_order
            or len(run_order or []) != 33
            or "FileNotFoundError" not in failure
            or criteria["prerequisites"]["w4"]["result_path"] not in failure
            or "verify_runner(source" not in failure
            or submission.get("exact_kernel_ref") != exact_kernel
            or submission.get("registered_criteria_path") != ROUND4_CRITERIA
            or submission.get("registered_source_commit") != ROUND4_SOURCE_COMMIT
            or submission.get("criteria_file_sha256") != digests["criteria"]
            or submission.get("dataset_version") != 4
            or submission.get("kernel_version") != 3
            or submission.get("timeout_seconds") != 14400
            or submission.get("terminal_status_observed") is not False
            or dataset.get("dataset_version") != 4
            or dataset.get("downloaded_from_current_version_number") != 4
            or dataset.get("criteria_file_sha256") != digests["criteria"]
            or dataset.get("all_paths_sizes_and_sha256_match") is not True
            or dataset.get("host_input_preflight_passed") is not True
            or dataset.get("registered_source_commit") != ROUND4_SOURCE_COMMIT
            or dataset.get("source_repo_input_count") != 32
            or dataset.get("direction_count") != 3
            or dataset.get("perturbation_count") != 30
            or dataset.get("host_gpu_inventory_called") is not False):
        raise ValueError("round-4 is not the exact 33-run W4 prerequisite lifetime failure")

    return {
        "criteria_path": ROUND4_CRITERIA,
        "criteria_file_sha256": digests["criteria"],
        "criteria_canonical_sha256": criteria["criteria_sha256"],
        "kernel3_submission_path": ROUND4_KERNEL3_SUBMISSION,
        "kernel3_submission_sha256": digests["submission"],
        "kernel3_diagnostic_path": ROUND4_KERNEL3_DIAGNOSTIC,
        "kernel3_diagnostic_sha256": digests["diagnostic"],
        "dataset_verification_path": ROUND4_DATASET_VERIFICATION,
        "dataset_verification_sha256": digests["dataset_verification"],
        "kernel_id": RETRY_KERNEL_ID,
        "kernel_version": 3,
        "dataset_version": 4,
        "solver_started": True,
        "solver_step_invoked": list(run_order),
        "solver_step_returned": list(run_order),
        "completed_primal_count": len(run_order),
        "failure_stage": execution["stage"],
        "host_verifier_error": diagnostic["host_verifier_error"],
        "output_manifest_sha256": diagnostic["output_manifest_sha256"],
        "measurement_thresholds_changed": False,
        "prior_outputs_reusable_as_fresh_primal_run": False,
        "reason": (
            "Round-4 exact kernel /3 completed all 33 fresh primal calls, then failed during "
            "runner-side host recomputation because verify_runner read the W4 result from the "
            "source tree after its TemporaryDirectory had been deleted. Preserve /3 as failed; "
            "a successor run must recompute all 33 primals under the fixed source."
        ),
    }


def assert_same_measurement_contract(candidate: dict, registered: dict) -> None:
    fields = (
        "criteria_id", "input_dataset_id", "geometry", "responses", "directions",
        "perturbation", "measurement", "noise_and_plateau", "gates", "claims",
        "backend", "direction_audit", "direction_inventory", "perturbation_inventory",
        "run_order", "input_dataset_files",
    )
    changed = [field for field in fields if candidate.get(field) != registered.get(field)]
    if changed:
        raise ValueError("retry changed the registered measurement contract: " + ", ".join(changed))


def build_criteria(*, state_path: Path, round_number: int) -> dict:
    if round_number not in (1, 2, 3, 4, 5):
        raise ValueError("only directional-FD criteria rounds 1, 2, 3, 4, and 5 are defined")
    (w3_criteria, w3_result, w4_criteria, w4_result,
     w3_criteria_sha, w3_result_sha, w4_criteria_sha, w4_result_sha) = load_prerequisites()
    observed_w4_backend = w4_result["backend_identity"]
    backend = observed_w4_backend["registered_backend"]
    selected_w4_gpu = observed_w4_backend["selected_gpu_uuid"]
    state_path = Path(state_path)
    state = SDFDesignState.load(state_path)
    state_npz_sha = sha256(state_path)
    raw_phi_f = np.asarray(state.phi, dtype="<f4", order="F").tobytes(order="F")
    raw_phi_c_sha = phi_sha256(state.phi, order="C")
    raw_phi_f_sha = sha256_bytes(raw_phi_f)
    if (state.state_sha256 != "44507748807dfbff995eb146866776b4a292e2fa2ddfe6caa5c3a611c29f6de8"
            or state.shape != (61, 33, 25)
            or state.origin_m != (-1.0, -0.8, -0.6)
            or state.spacing_m != 0.05
            or raw_phi_c_sha != "45b6c8f46a3d7bc4c321ab13529babe62469c6fe5834ef8f88604847dbba0785"
            or raw_phi_f_sha != "9ed14a39a1456436ff40411c85ae54b04bfe28554ebe1b87677e7e9a62f632b7"
            or state_npz_sha != w3_criteria["inputs"]["canonical_state_npz"]["sha256"]
            or state_npz_sha != w4_criteria["inputs"]["canonical_state_npz"]["sha256"]):
        raise ValueError("canonical v16 state does not match exact W3/W4 evidence")

    draft = json.loads(DRAFT.read_text())
    if (draft.get("immutable") is not False
            or draft.get("registered_before_computation") is not False
            or draft.get("status") != "mutable_draft_no_measurement"):
        raise ValueError("criteria draft must remain mutable and unmeasured")
    kernel_metadata = json.loads((ROOT / SOURCE_PATHS["kernel_metadata"]).read_text())
    expected_kernel_id = DATASET_ID if round_number == 1 else RETRY_KERNEL_ID
    if (draft.get("criteria_round") != round_number
            or draft.get("kernel_id") != expected_kernel_id
            or kernel_metadata.get("id") != expected_kernel_id
            or kernel_metadata.get("dataset_sources") != [DATASET_ID]
            or (round_number >= 2 and kernel_metadata.get("title") != RETRY_KERNEL_TITLE)):
        raise ValueError("draft round, unique kernel slug/title, and kernel metadata do not agree")
    supersession_binding = {
        1: None,
        2: load_round1_submission_retry_binding,
        3: load_round2_preflight_retry_binding,
        4: load_round3_pre_primal_retry_binding,
        5: load_round4_host_recompute_lifetime_failure_binding,
    }[round_number]
    if callable(supersession_binding):
        supersession_binding = supersession_binding()
    directions = generate_directions(state)
    direction_audit = validate_directions(state, directions)
    direction_inputs, direction_records = {}, {}
    for direction_id in DIRECTION_IDS:
        direction = directions[direction_id]
        file_bytes = np.asarray(direction, dtype="<f4", order="C").tobytes(order="C")
        path = f"directions/{direction_id}.f4-c.raw"
        digest = sha256_bytes(file_bytes)
        if digest != direction_audit["direction_sha256"][direction_id]:
            raise ValueError(f"direction array/file SHA serialization mismatch: {direction_id}")
        direction_inputs[f"direction_{direction_id}"] = {
            "path": path, "sha256": digest, "location": "kaggle_dataset",
            "shape": list(state.shape), "dtype": "float32_little_endian", "order": "C",
        }
        direction_records[direction_id] = {
            "dataset_path": path,
            "sha256": digest,
            "shape": list(state.shape),
            "dtype": "float32_little_endian",
            "order": "C",
        }

    perturbations = []
    perturbation_inputs = {}
    margin_rows = []
    for direction_id in DIRECTION_IDS:
        for epsilon_m in EPSILON_LADDER_M:
            for sign in (1, -1):
                child, identity = perturbed_state(
                    state, directions[direction_id], epsilon_m=epsilon_m, sign=sign,
                    margin_gate_m=SDF_MARGIN_GATE_M,
                )
                raw = np.asarray(child.phi, dtype="<f4", order="F").tobytes(order="F")
                phi_f = sha256_bytes(raw)
                if phi_f != identity["phi_fortran_order_sha256"]:
                    raise ValueError("perturbed Fortran array hash changed during registration")
                case_id = perturbation_case_id(direction_id, epsilon_m, sign)
                path = f"perturbations/{case_id}.phi-f4-fortran.raw"
                entry = {
                    "case_id": case_id,
                    "direction_id": direction_id,
                    "direction_sha256": direction_records[direction_id]["sha256"],
                    "epsilon_m": epsilon_m,
                    "sign": sign,
                    "parent_state_sha256": state.state_sha256,
                    "state_sha256": child.state_sha256,
                    "dataset_path": path,
                    "phi_file_sha256": sha256_bytes(raw),
                    "phi_fortran_sha256": phi_f,
                    "phi_c_order_sha256": identity["phi_c_order_sha256"],
                    "shape": list(child.shape),
                    "origin_m": list(child.origin_m),
                    "spacing_m": child.spacing_m,
                    "maximum_pointwise_change_m": identity["maximum_pointwise_change_m"],
                    "changed_node_count": identity["changed_node_count"],
                    "zero_level_margin_m": identity["zero_level_margin_m"],
                    "margin_gate_m": SDF_MARGIN_GATE_M,
                    "masks_unchanged": identity["masks_unchanged"],
                    "outside_design_phi_identical": identity["outside_design_phi_identical"],
                    "reinitialization_applied": False,
                    "smoothing_applied": False,
                    "volume_correction_applied": False,
                    "clipping_applied": False,
                }
                perturbations.append(entry)
                margin_rows.append(identity["zero_level_margin_m"])
                perturbation_inputs[f"perturbation_{case_id}"] = {
                    "path": path, "sha256": sha256_bytes(raw), "location": "kaggle_dataset",
                    "shape": list(child.shape), "dtype": "float32_little_endian", "order": "Fortran",
                }
    if len(perturbations) != 30 or min(margin_rows) < SDF_MARGIN_GATE_M:
        raise ValueError("all 30 perturbations must pass the preregistered SDF margin preflight")

    branch = subprocess.check_output(["git", "-C", str(ROOT), "branch", "--show-current"], text=True).strip()
    expected_branch = "codex/kaggle-batch-migration" if round_number <= 4 else "exp/fd-02-round4"
    if branch != expected_branch:
        raise ValueError(f"round-{round_number} criteria must be registered from {expected_branch}, got {branch}")
    status = subprocess.check_output(["git", "-C", str(ROOT), "status", "--porcelain"], text=True)
    if status.strip():
        raise ValueError("source/harness commit must be clean before immutable FD registration")
    source_commit = subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True).strip()
    upstream = subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "@{u}"], text=True).strip()
    if source_commit != upstream:
        raise ValueError("source/harness commit must be pushed before immutable FD registration")
    inputs = {name: source_entry(path) for name, path in SOURCE_PATHS.items()}
    inputs["canonical_state_npz"] = {
        "path": "sdf_design_state.npz", "sha256": state_npz_sha, "location": "kaggle_dataset",
    }
    inputs["canonical_phi_fortran_raw"] = {
        "path": "canonical_v16_phi_f4_fortran.raw", "sha256": raw_phi_f_sha,
        "location": "kaggle_dataset", "dtype": "float32_little_endian", "order": "Fortran",
        "shape": list(state.shape),
    }
    inputs.update(direction_inputs)
    inputs.update(perturbation_inputs)

    final = json.loads(json.dumps(draft))
    final.update({
        "kind": "sdf_directional_fd_flow16_criteria",
        "criteria_round": round_number,
        "kernel_id": expected_kernel_id,
        "kernel_title": kernel_metadata["title"],
        "status": "registered_not_run",
        "immutable": True,
        "registered_before_computation": True,
        "registered_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "registered_source_commit": source_commit,
        "source_commit": source_commit,
        "input_dataset_id": DATASET_ID,
        "inputs": inputs,
        "source_input_sha256": {
            name: entry["sha256"] for name, entry in inputs.items()
            if entry.get("location") == "source_repo"
        },
        "direction_generation_runtime": {
            "python_version": platform.python_version(),
            "numpy_version": np.__version__,
        },
        "backend": backend,
        "prerequisites": {
            "w3": {"criteria_path": W3_CRITERIA, "criteria_sha256": w3_criteria_sha,
                   "result_path": W3_RESULT, "result_sha256": w3_result_sha,
                   "host_verified": True, "kernel_version": w3_result["kernel_version"],
                   "selected_gpu_uuid": w3_result["selected_gpu_uuid"],
                   "backend_identity": w3_result["backend_identity"]},
            "w4": {"criteria_path": W4_CRITERIA, "criteria_sha256": w4_criteria_sha,
                   "result_path": W4_RESULT, "result_sha256": w4_result_sha,
                   "host_verified": True, "kernel_version": w4_result["kernel_version"],
                   "fd_entry_gate": w4_result["fd_entry_gate"],
                   "extended_domain_fine_grid_required": w4_result["extended_domain_fine_grid_required"],
                   "formal_fd_measurement_started": w4_result["formal_fd_measurement_started"],
                   "selected_gpu_uuid": selected_w4_gpu,
                   "observed_backend_identity_sha256": json_hash(observed_w4_backend),
                   "backend_identity": backend},
        },
        "geometry": {
            **draft["geometry"],
            "canonical_state_npz_sha256": state_npz_sha,
            "canonical_state_sha256": state.state_sha256,
            "canonical_phi_c_order_sha256": raw_phi_c_sha,
            "canonical_phi_fortran_sha256": raw_phi_f_sha,
            "source_surface_sha256": state.source_sha256,
            "narrow_band_width_m": state.narrow_band_width_m,
            "fixed_solid_mask_sha256": sha256_bytes(np.ascontiguousarray(state.fixed_solid_mask, dtype="u1").tobytes()),
            "forbidden_mask_sha256": sha256_bytes(np.ascontiguousarray(state.forbidden_mask, dtype="u1").tobytes()),
            "root_mask_sha256": sha256_bytes(np.ascontiguousarray(state.root_mask, dtype="u1").tobytes()),
            "design_mask_sha256": sha256_bytes(np.ascontiguousarray(state.design_mask, dtype="u1").tobytes()),
            "canonical_phi_margin_m": zero_level_margin_m(state.phi, state.spacing_m),
        },
        "direction_inventory": direction_records,
        "direction_audit": direction_audit,
        "perturbation_inventory": perturbations,
        "run_order": list(registered_run_order()),
        "input_dataset_files": {
            entry["path"]: entry["sha256"] for entry in inputs.values()
            if entry.get("location") == "kaggle_dataset"
        },
        "source_tree_commit": source_commit,
        "formal_measurement_started": False,
    })
    if supersession_binding is not None:
        final["supersedes"] = supersession_binding
        predecessor_path = {
            2: ROUND1_CRITERIA,
            3: ROUND2_CRITERIA,
            4: ROUND3_CRITERIA,
            5: ROUND4_CRITERIA,
        }[round_number]
        predecessor = json.loads((ROOT / predecessor_path).read_text())
        assert_same_measurement_contract(final, predecessor)
    final["criteria_sha256"] = json_hash(final)
    return final


def criteria_output_path(round_number: int) -> Path:
    if round_number == 1:
        return OUTPUT
    return OUTPUT.with_name(f"sdf_directional_fd_v16_criteria_2026_09_round{round_number}.json")


def write_or_check(round_number: int, state_path: Path, check: bool) -> str:
    output = criteria_output_path(round_number)
    sidecar = output.with_suffix(output.suffix + ".sha256")
    if check:
        if not output.is_file() or not sidecar.is_file():
            raise SystemExit("immutable directional FD criteria or sidecar missing")
        digest = sha256(output)
        criteria = json.loads(output.read_text())
        if (sidecar.read_text().strip() != digest or criteria.get("immutable") is not True
                or criteria.get("criteria_sha256") != json_hash({k: v for k, v in criteria.items()
                                                                 if k != "criteria_sha256"})
                or criteria.get("source_commit") != criteria.get("registered_source_commit")):
            raise SystemExit("directional FD immutable criteria identity mismatch")
        current_commit = subprocess.check_output(
            ["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True
        ).strip()
        historical_source = criteria.get("source_commit") != current_commit
        for name, entry in criteria["inputs"].items():
            if entry.get("location") == "source_repo":
                if git_blob_sha(criteria["source_commit"], entry["path"]) != entry["sha256"]:
                    raise SystemExit(f"registered source input changed: {name}")
                if not historical_source and sha256(ROOT / entry["path"]) != entry["sha256"]:
                    raise SystemExit(f"checked-out source input changed: {name}")
        return digest
    if output.exists() or sidecar.exists():
        raise SystemExit("immutable criteria target already exists; never overwrite")
    criteria = build_criteria(state_path=state_path, round_number=round_number)
    payload = json.dumps(criteria, indent=2, sort_keys=True, allow_nan=False) + "\n"
    output.write_text(payload)
    digest = sha256(output)
    sidecar.write_text(digest + "\n")
    return digest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--round", type=int, default=1)
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    print(write_or_check(args.round, args.state, args.check))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
