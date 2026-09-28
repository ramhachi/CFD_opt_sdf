import csv
import hashlib
import importlib.util
import json
import re
import subprocess
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
VERIFY_PATH = ROOT / "scripts/verify_kaggle_w3_v16_cuda_diagnostic.py"
spec = importlib.util.spec_from_file_location("w3_cuda_diagnostic_host", VERIFY_PATH)
host = importlib.util.module_from_spec(spec)
spec.loader.exec_module(host)


def lattice_rows():
    rows = []
    for i, x in ((1, 0.5), (2, 1.5)):
        candidate = [0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0] if i == 1 else [0.5, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0]
        ground = [0.5, 0.0, 0.0, 1.0, 1.0, 0.0, 0.0]
        combined = candidate if i == 1 else ground
        rows.append([i, 1, 1, x, 0.5, 0.5,
                     *candidate, *candidate, *ground, *ground, *combined, *combined,
                     *combined[:1], *combined[:1], 0.5, 0.5])
    return rows


def write_lattice(path: Path):
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(host.expected_header())
        writer.writerows(lattice_rows())


def test_flow_lattice_csv_layout_and_ground_contract(tmp_path):
    path = tmp_path / "lattice.csv"
    write_lattice(path)

    result = host.read_lattice_csv(path, (2, 1, 1))

    assert result["row_count"] == 2
    assert result["candidate_cpu"][:, 0].tolist() == [0.0, 0.5]
    assert result["ground_cpu"][:, 0].tolist() == [0.5, 0.5]
    assert result["combined_cpu"][:, 0].tolist() == [0.0, 0.5]
    assert result["ground_cpu"][:, 3].tolist() == [1.0, 1.0]
    assert result["ground_cpu"][:, 4].tolist() == [1.0, 1.0]
    assert len(host.expected_header()) == 52


def test_numpy_reference_recomputes_candidate_distance_and_normal(tmp_path):
    lattice_path = tmp_path / "lattice.csv"
    write_lattice(lattice_path)
    lattice = host.read_lattice_csv(lattice_path, (2, 1, 1))
    x = (np.arange(5, dtype=np.float32) * np.float32(0.025) - np.float32(0.0125))
    phi = np.broadcast_to(x[:, None, None], (5, 3, 3)).copy()
    geometry = {"canonical_sdf_origin_m": [0.0, 0.0, 0.0], "spacing_m": 0.05}
    profile = {"flow_origin_m": [0.0, 0.0, 0.0]}

    result = host.host_candidate_reference(phi, lattice, geometry, profile)

    assert np.allclose(result["distance_solver"], [0.0, 0.5], atol=1e-6)
    assert np.allclose(result["normal"], [[1.0, 0.0, 0.0], [1.0, 0.0, 0.0]], atol=1e-6)
    assert result["host_cpu_max_abs_distance_error_m"] == pytest.approx(0.0, abs=1e-7)


def test_force_snapshot_checks_component_closure_and_projection():
    snapshot = {
        "waterlily_pressure_force_raw": [-2.0, 0.5, 3.0],
        "waterlily_viscous_force_raw": [-1.0, -0.5, 1.0],
        "waterlily_total_force_raw": [-3.0, 0.0, 4.0],
        "registered_drag_plus_fx_from_raw": 3.0,
        "registered_downforce_minus_fz_from_raw": 4.0,
    }

    result = host.verify_force_snapshot(snapshot)

    assert result["pressure_plus_viscous_componentwise_residual"] == [0.0, 0.0, 0.0]
    assert result["repository_drag_plus_fx"] == 3.0
    assert result["repository_downforce_minus_fz"] == 4.0

    snapshot["waterlily_total_force_raw"] = [-4.0, 0.0, 4.0]
    with pytest.raises(ValueError, match="does not exactly close"):
        host.verify_force_snapshot(snapshot)


def test_w2b_sign_precedent_is_audited_without_extending_its_claim():
    audit = host.audit_w2b_drag_sign_precedent()

    assert audit["registered_T4_drag_sign_gate"] is True
    assert all(value > 0 for value in audit["time_weighted_drag_solver_units_by_cells_per_diameter"].values())
    assert "no v16 target" in audit["interpretation"]


def test_error_bundle_can_be_verified_as_diagnostic_only(tmp_path):
    output = tmp_path / "w3_v16_cuda_diagnostic"
    output.mkdir()
    (output / "ERROR.txt").write_text("CUDA diagnostic stage failed\n")
    payload_sha = hashlib.sha256((output / "ERROR.txt").read_bytes()).hexdigest()
    (output / "sha256.json").write_text(json.dumps({"ERROR.txt": payload_sha}))

    manifest, manifest_sha, status = host.verify_output_files(output)

    assert manifest == {"ERROR.txt": payload_sha}
    assert len(manifest_sha) == 64
    assert status == "ERROR"


def test_error_classification_uses_julia_exception_after_last_checkpoint(tmp_path):
    (tmp_path / "ERROR.txt").write_text("Julia job failed\n")
    (tmp_path / "w3_cuda_diagnostic.log").write_text(
        "ERROR: LoadError: UndefVarError: `f` not defined in `Main`\n"
        " [1] v16_representative_probes(grid::GridSDF)\n")

    result = host.classify_failure(
        tmp_path, {"last_completed_stage": "input_and_device_identity"}, None)

    assert result["last_completed_stage"] == "input_and_device_identity"
    assert result["failed_stage"] == "representative_probe_definitions"
    assert result["failure_class"] == "julia_diagnostic_probe_fixture_bug"
    assert result["solver_started"] is False
    assert "UndefVarError" in result["exact_exception"]


def test_error_classification_identifies_float_literal_in_probe_comparison(tmp_path):
    (tmp_path / "w3_cuda_diagnostic.log").write_text(
        "ERROR: UndefVarError: `f0` not defined\n"
        " [6] compare_rows(cpu::Matrix{Float32}, gpu::Matrix{Float32})\n")

    result = host.classify_failure(
        tmp_path, {"last_completed_stage": "candidate_representative_probes_started"}, None)

    assert result["failed_stage"] == "representative_probe_cpu_cuda_comparison"
    assert result["failure_class"] == "julia_diagnostic_float_literal_bug"
    assert result["solver_started"] is False


def test_diagnostic_job_uses_valid_julia_float32_literal_suffixes():
    source = (ROOT / "scripts/waterlily_w3_v16_cuda_diagnostic_job.jl").read_text()
    malformed = re.search(
        r"(?<![\w.])(?:\d+(?:\.\d*)?|\.\d+)(?:e[-+][0-9]+f[0-9]+|f(?![0-9+\-]))",
        source,
        re.IGNORECASE,
    )

    assert malformed is None


def test_checkout_job_identity_uses_exact_commit_in_kaggle_output(tmp_path):
    commit = subprocess.check_output(
        ["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True).strip()
    job = subprocess.check_output(
        ["git", "-C", str(ROOT), "show",
         f"{commit}:scripts/waterlily_w3_v16_cuda_diagnostic_job.jl"])
    (tmp_path / "git_checkout.log").write_text(f"HEAD is now at {commit[:7]} diagnostic\n")

    assert host.checkout_job_identity(tmp_path) == (
        commit, hashlib.sha256(job).hexdigest())


def test_partial_fingerprint_binds_backend_and_exact_source_checkout(tmp_path):
    dataset = tmp_path / "dataset"
    dataset.mkdir()
    (dataset / "w3_v16_criteria.json.sha256").write_text("sidecar\n")
    (dataset / "w3_v16_dataset_manifest.json").write_text("manifest\n")
    criteria = {
        "backend": {
            "gpu_count": 2,
            "gpu_name": "Tesla T4",
            "driver_version": "535.0",
            "julia_archive_sha256": "julia",
            "cuda_visible_devices": "0",
        },
        "inputs": {
            "job": {"sha256": "w3-job"},
            "project": {"sha256": "project"},
            "manifest": {"sha256": "manifest-julia"},
        },
        "geometry": {
            "state_sha256": "state",
            "source_surface_sha256": "surface",
            "design_domain_sha256": "domain",
        },
    }
    commit_job = ("a" * 40, "b" * 64)
    inventory = [
        "0, Tesla T4, GPU-a, 16000 MiB, 535.0",
        "1, Tesla T4, GPU-b, 16000 MiB, 535.0",
    ]
    fingerprint = {
        "criteria_sha256": "criteria",
        "criteria_sidecar_sha256": hashlib.sha256(b"sidecar\n").hexdigest(),
        "dataset_id": host.EXPECTED_W3_DATASET_ID,
        "dataset_manifest_sha256": hashlib.sha256(b"manifest\n").hexdigest(),
        "runner_sha256": "runner",
        "w3_source_commit": host.EXPECTED_W3_SOURCE_COMMIT,
        "w3_source_job_sha256": "w3-job",
        "project_sha256": "project",
        "manifest_sha256": "manifest-julia",
        "julia_archive_sha256": "julia",
        "state_sha256": "state",
        "source_surface_sha256": "surface",
        "design_domain_sha256": "domain",
        "cuda_visible_devices": "0",
        "source_commit": commit_job[0],
        "diagnostic_job_sha256": commit_job[1],
        "gpu_inventory": inventory,
        "selected_gpu_uuid": "GPU-a",
        "cuda_smoke_sha256": "smoke",
    }

    result = host.verify_partial_fingerprint(
        fingerprint, criteria, "criteria", dataset, "runner", commit_job)

    assert result["checkout_diagnostic_source_commit"] == commit_job[0]
    assert result["checkout_diagnostic_job_sha256"] == commit_job[1]
