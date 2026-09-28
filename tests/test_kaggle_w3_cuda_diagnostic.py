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
RUNNER_PATH = ROOT / "infra/kaggle/kernel_w3_cuda_diagnostic/runner.py"
runner_spec = importlib.util.spec_from_file_location("w3_cuda_diagnostic_runner", RUNNER_PATH)
runner = importlib.util.module_from_spec(runner_spec)
runner_spec.loader.exec_module(runner)


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


def test_geometry_contract_returns_independent_ground_and_sdf_checks():
    candidate = np.asarray([
        [0.5, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0],
        [1.5, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0],
    ], dtype=np.float32)
    ground = np.asarray([
        [0.5, 0.0, 0.0, 1.0, 1.0, 0.0, 0.0],
        [0.5, 0.0, 0.0, 1.0, 1.0, 0.0, 0.0],
    ], dtype=np.float32)
    combined = candidate.copy()
    lattice = {
        "raw": np.asarray([[1, 1, 1, 0.5, 0.5, 0.5],
                           [2, 1, 1, 1.5, 0.5, 0.5]], dtype=np.float64),
        "candidate_cpu": candidate,
        "candidate_gpu": candidate.copy(),
        "ground_cpu": ground,
        "ground_gpu": ground.copy(),
        "combined_cpu": combined,
        "combined_gpu": combined.copy(),
        "cpu_sigma": combined[:, 0].copy(),
        "gpu_sigma": combined[:, 0].copy(),
        "cpu_mu0_sum": np.zeros(2, dtype=np.float32),
        "gpu_mu0_sum": np.zeros(2, dtype=np.float32),
    }
    x = np.arange(5, dtype=np.float32) * np.float32(0.05)
    phi = np.broadcast_to(x[:, None, None], (5, 3, 3)).copy()
    criteria = {
        "geometry": {"canonical_sdf_origin_m": [0.0, 0.0, 0.0], "spacing_m": 0.05},
        "profile_adapter": {"cell_dims": [2, 1, 1], "flow_origin_m": [0.0, 0.0, 0.0]},
    }

    checks = host.verify_geometry_contract(lattice, criteria, phi)

    assert checks["expected_ground_support_cells"] == 2
    assert checks["cpu_sigma_vs_combined_distance_max_error"] == 0
    assert checks["candidate_sdf_reference"]["host_cpu_max_abs_distance_error_m"] == pytest.approx(0)


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


def test_owner_round4_criteria_and_job_are_immutable_and_hash_bound():
    criteria, criteria_sha, sidecar_sha = host.load_owner_lifetime_criteria()

    assert criteria["immutable"] is True
    assert criteria["registered_before_computation"] is True
    assert criteria["round"] == 4
    assert criteria["inputs"]["owner_lifetime_job"]["sha256"] == host.sha256(
        host.OWNER_LIFETIME_JOB)
    assert criteria["supersedes_before_measurement"]["sha256"] == host.sha256(
        ROOT / "docs/evidence/kaggle_w3_v16_cuda_owner_lifetime_criteria_2026_09_round3.json")
    assert criteria["execution"]["weakref_target_path"] == "owner.grid.phi"
    assert criteria["execution"]["weakref_target_type"] == (
        "CuArray{Float32, 3, CUDA.DeviceMemory}")
    assert criteria["execution"]["unrooted_gc_policy"][
        "automatic_gc_disabled_until_forced_gc"] is True
    assert criteria["execution"]["unrooted_gc_policy"][
        "automatic_gc_must_be_enabled_before_each_forced_gc"] is True
    assert runner.OWNER_LIFETIME_CRITERIA_PATH.endswith("round4.json")
    assert runner.OWNER_LIFETIME_JOB_SHA256 == criteria["inputs"][
        "owner_lifetime_job"]["sha256"]
    assert criteria_sha == host.sha256(host.OWNER_LIFETIME_CRITERIA_PATH)
    assert host.OWNER_LIFETIME_CRITERIA_PATH.with_suffix(
        host.OWNER_LIFETIME_CRITERIA_PATH.suffix + ".sha256").read_text().strip() == criteria_sha
    assert len(sidecar_sha) == 64


def test_owner_weakref_gc_schema_and_collection_bracketing():
    retained = {
        "strategy": "GC.@preserve owner",
        "strong_owner_reference_escaped_helper": True,
        "weakref_created": True,
        "owner_type": "CuArray{Float32, 3, CUDA.DeviceMemory}",
        "weakref_target_path": "owner.grid.phi",
        "weakref_target_type": "CuArray{Float32, 3, CUDA.DeviceMemory}",
        "weakref_before_gc": "alive",
        "weakref_after_each_gc": ["alive", "alive"],
        "weakref_after_gc": "alive",
        "owner_collected_during_forced_gc": False,
        "full_gc_calls": 2,
        "cuda_synchronize_before_gc": True,
        "cuda_synchronize_after_gc": True,
    }
    assert host.verify_owner_ownership_schema("A", retained)["forced_gc_calls"] == 2

    unrooted = {
        "strategy": "helper returns bodies,simulation,WeakRef only",
        "strong_owner_reference_escaped_helper": False,
        "weakref_created": True,
        "owner_type": "CuArray{Float32, 3, CUDA.DeviceMemory}",
        "weakref_target_path": "owner.grid.phi",
        "weakref_target_type": "CuArray{Float32, 3, CUDA.DeviceMemory}",
        "weakref_before_gc": "alive",
        "weakref_after_each_gc": ["alive", "cleared"],
        "weakref_after_gc": "cleared",
        "owner_collected_during_forced_gc": True,
        "full_gc_calls": 2,
        "unrooted_automatic_gc_disabled_until_forced_gc": True,
        "automatic_gc_was_enabled_before_unrooted_bracket": True,
        "automatic_gc_reenabled_before_each_forced_gc": [True, True],
        "cuda_synchronize_before_gc": True,
        "cuda_synchronize_after_gc": True,
    }
    assert host.verify_owner_ownership_schema("B1", unrooted)[
        "owner_collected_during_forced_gc"] is True
    unrooted["weakref_target_path"] = "owner"
    with pytest.raises(ValueError, match="WeakRef does not target"):
        host.verify_owner_ownership_schema("B1", unrooted)
    unrooted["weakref_target_path"] = "owner.grid.phi"
    unrooted["automatic_gc_reenabled_before_each_forced_gc"] = [True, False]
    with pytest.raises(ValueError, match="GC schedule mismatch"):
        host.verify_owner_ownership_schema("B1", unrooted)
    unrooted["automatic_gc_reenabled_before_each_forced_gc"] = [True, True]
    unrooted["owner_collected_during_forced_gc"] = False
    with pytest.raises(ValueError, match="collection boolean mismatch"):
        host.verify_owner_ownership_schema("B1", unrooted)

    structural_wrapper_weakref = {
        "strategy": "OwnedV16Diagnostic owns owner,bodies,simulation",
        "strong_owner_reference_escaped_helper": True,
        "weakref_created": True,
        "owner_type": "CuArray{Float32, 3, CUDA.DeviceMemory}",
        "weakref_target_path": "owner.grid.phi",
        "weakref_target_type": "CuArray{Float32, 3, CUDA.DeviceMemory}",
        "weakref_before_pre_gc_observations": "alive",
        "weakref_before_gc": "cleared",
        "weakref_after_each_gc": ["cleared", "cleared"],
        "weakref_after_gc": "cleared",
        "owner_collected_during_forced_gc": False,
        "full_gc_calls": 2,
        "cuda_synchronize_before_gc": True,
        "cuda_synchronize_after_gc": True,
    }
    structural = host.verify_owner_ownership_schema("C", structural_wrapper_weakref)
    assert structural["registered_lifetime_contract_satisfied"] is False
    assert structural["owner_cleared_before_forced_gc"] is True


def test_owner_force_closure_and_registered_projections_are_host_recomputed():
    snapshot = {
        "waterlily_pressure_force_raw": [-2.0, 0.5, 3.0],
        "waterlily_viscous_force_raw": [-1.0, -0.5, 1.0],
        "waterlily_total_force_raw": [-3.0, 0.0, 4.0],
        "body_pressure_force": [2.0, -0.5, -3.0],
        "body_viscous_force": [1.0, 0.5, -1.0],
        "body_total_force": [3.0, 0.0, -4.0],
        "registered_drag_plus_fx_body": 3.0,
        "registered_downforce_minus_fz_body": 4.0,
    }

    result = host._verify_owner_force(snapshot)

    assert result["pressure_plus_viscous_residual"] == [0.0, 0.0, 0.0]
    assert result["drag_plus_fx_body"] == 3.0
    assert result["downforce_minus_fz_body"] == 4.0
    snapshot["registered_drag_plus_fx_body"] = -3.0
    with pytest.raises(ValueError, match="projection mismatch"):
        host._verify_owner_force(snapshot)


def test_owner_a_c_controls_and_b_divergence_are_compared_by_geometry_field_force():
    criteria, _, _ = host.load_owner_lifetime_criteria()
    base = {
        "geometry_arrays": {
            name: np.zeros((3, 7), dtype=np.float32)
            for name in host.OWNER_GEOMETRY_ARRAYS
        },
        "field_arrays": {name: np.zeros((2,), dtype=np.float32)
                         for name in host.OWNER_FIELD_ARRAYS},
        "force_history": {
            phase: {
                "waterlily_pressure_force_raw": [0.0, 0.0, 0.0],
                "waterlily_viscous_force_raw": [0.0, 0.0, 0.0],
                "waterlily_total_force_raw": [0.0, 0.0, 0.0],
            } for phase in ("step0_after_gc", "step1", "step2")
        },
    }
    retained = {
        "geometry_arrays": {key: value.copy() for key, value in base["geometry_arrays"].items()},
        "field_arrays": {key: value.copy() for key, value in base["field_arrays"].items()},
        "force_history": json.loads(json.dumps(base["force_history"])),
    }
    candidate = {
        "geometry_arrays": {key: value.copy() for key, value in base["geometry_arrays"].items()},
        "field_arrays": {key: value.copy() for key, value in base["field_arrays"].items()},
        "force_history": json.loads(json.dumps(base["force_history"])),
    }
    assert host._owner_pair_divergences(retained, candidate, criteria) == set()
    candidate["geometry_arrays"]["candidate_cuda"][0, 0] = 1.0
    candidate["field_arrays"]["u"][0] = 1.0
    candidate["force_history"]["step1"]["waterlily_total_force_raw"][0] = 1.0
    divergence = host._owner_pair_divergences(retained, candidate, criteria)
    assert divergence == {"candidate_geometry", "simulation_fields", "force_history"}


def test_owner_binary_bundle_hash_layout_and_field_order_are_verified(tmp_path):
    first = np.asarray([[1.0, 2.0], [3.0, 4.0]], dtype="<f4", order="F")
    second = np.asarray([[5.0, 6.0]], dtype="<f4", order="F")
    first_bytes = first.tobytes(order="F")
    second_bytes = second.tobytes(order="F")
    path = tmp_path / "bundle.f32"
    path.write_bytes(first_bytes + second_bytes)
    spec = {
        "artifact": path.name,
        "artifact_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "layout": {
            "first": {"offset_bytes": 0, "nbytes": len(first_bytes), "shape": [2, 2],
                      "dtype": "<f4", "order": "F",
                      "sha256": hashlib.sha256(first_bytes).hexdigest()},
            "second": {"offset_bytes": len(first_bytes), "nbytes": len(second_bytes), "shape": [1, 2],
                       "dtype": "<f4", "order": "F",
                       "sha256": hashlib.sha256(second_bytes).hexdigest()},
        },
    }

    arrays = host._owner_read_bundle(tmp_path, spec, ("first", "second"), spec["artifact_sha256"])

    assert np.array_equal(arrays["first"], first)
    assert np.array_equal(arrays["second"], second)
    spec["layout"]["second"]["offset_bytes"] = 0
    with pytest.raises(ValueError, match="array SHA mismatch"):
        host._owner_read_bundle(tmp_path, spec, ("first", "second"), spec["artifact_sha256"])


def test_owner_arm_failure_classification_separates_b_hazard_from_bootstrap_error():
    collected = {"ownership": {"owner_collected_during_forced_gc": True}, "status": "running"}
    expected = runner.classify_owner_arm("B1", 139, collected, "full_grid_geometry_started")
    assert expected["acceptable"] is True
    assert expected["classification"] == "expected_unrooted_post_gc_hazard"

    bootstrap = {"ownership": {"owner_collected_during_forced_gc": False}, "status": "running"}
    failed = runner.classify_owner_arm("B2", 1, bootstrap, "canonical_input_load_started")
    assert failed["acceptable"] is False
    assert failed["classification"] == "unexpected_arm_failure"
    retained_crash = runner.classify_owner_arm("A", 139, collected, "primal_step_1_started")
    assert retained_crash["acceptable"] is False


def test_owner_runner_workspace_expiry_is_distinguished_from_julia_failure(tmp_path):
    folder = tmp_path / "w3_v16_cuda_diagnostic"
    folder.mkdir()
    (folder / "w3_cuda_diagnostic.log").write_text(
        "W3_V16_CUDA_DIAGNOSTIC_DONE solver_steps_v16=1\n")
    wrapper_error = (
        "Traceback (most recent call last):\n"
        "  File \"/kaggle/src/script.py\", in run_owner_lifetime_arms\n"
        "FileNotFoundError: [Errno 2] No such file or directory: "
        "'/tmp/w3/julia-1.12.6/bin/julia'\n"
    )
    (folder / "ERROR.txt").write_text(wrapper_error)

    result = host.classify_failure(
        folder,
        {"last_completed_stage": "diagnostic_report_written"},
        {"v16_one_step_reproducer": {"cuda_solver_steps": 1}},
    )

    assert result["failed_stage"] == "owner-lifetime arm Julia process launch before A"
    assert result["failure_class"] == "owner_lifetime_runner_workspace_expired"
    assert result["solver_started"] is True
    assert result["exact_exception"] == wrapper_error


def test_owner_missing_import_is_separated_from_arm_or_lifetime_failure(tmp_path):
    folder = tmp_path / "w3_v16_cuda_diagnostic"
    folder.mkdir()
    exception = (
        "UndefVarError: `v16_physical_profile_bodies` not defined in `Main`\n"
        "Stacktrace: owner_lifetime_job.jl:501"
    )
    arms = []
    for arm_id in ("A", "C", "B1", "B2"):
        report_name = f"w3_v16_cuda_owner_lifetime_{arm_id}.json"
        (folder / report_name).write_text(json.dumps({
            "status": "operation_error",
            "last_stage": "canonical_input_load_started",
            "exact_exception": exception,
        }))
        arms.append({
            "arm_id": arm_id,
            "classification": "unexpected_arm_failure",
            "last_stage": "canonical_input_load_started",
            "report_path": report_name,
        })
    (folder / "owner_lifetime_execution.json").write_text(json.dumps({
        "arms": arms,
        "unexpected_arm_failures": ["A", "C", "B1", "B2"],
    }))
    wrapper_error = "RuntimeError: unexpected owner-lifetime arm failure(s)"
    (folder / "ERROR.txt").write_text(wrapper_error)

    result = host.classify_failure(
        folder,
        {"last_completed_stage": "diagnostic_report_written"},
        {"v16_one_step_reproducer": {"cuda_solver_steps": 1}},
    )

    assert result["failed_stage"] == (
        "owner-lifetime Julia import resolution before candidate body construction")
    assert result["failure_class"] == "owner_lifetime_julia_missing_import"
    assert result["solver_started"] is True
    assert result["owner_arm_processes_started"] is True
    assert result["owner_primal_step_reached"] is False
    assert set(result["owner_arm_exceptions"]) == {"A", "C", "B1", "B2"}
    assert result["exact_exception"] == exception
    assert result["runner_exception"] == wrapper_error


def test_owner_complete_but_unbracketed_wrapper_weakrefs_stay_unresolved(tmp_path):
    folder = tmp_path / "w3_v16_cuda_diagnostic"
    folder.mkdir()
    arms = []
    observations = {
        "A": ("alive", "alive"),
        "C": ("cleared", "cleared"),
        "B1": ("cleared", "cleared"),
        "B2": ("cleared", "cleared"),
    }
    for arm_id, (before, after) in observations.items():
        report_name = f"w3_v16_cuda_owner_lifetime_{arm_id}.json"
        (folder / report_name).write_text(json.dumps({
            "status": "completed",
            "ownership": {
                "weakref_before_pre_gc_observations": "alive",
                "weakref_before_gc": before,
                "weakref_after_gc": after,
            },
        }))
        arms.append({"arm_id": arm_id, "report_path": report_name})
    (folder / "owner_lifetime_execution.json").write_text(json.dumps({
        "status": "captured",
        "arms": arms,
        "unexpected_arm_failures": [],
    }))

    result = host.classify_failure(
        folder,
        {"last_completed_stage": "diagnostic_report_written"},
        {"v16_one_step_reproducer": {"cuda_solver_steps": 1}},
    )

    assert result["failure_class"] == (
        "owner_lifetime_weakref_target_or_bracket_unresolved")
    assert result["failed_stage"] == (
        "owner-lifetime WeakRef target or forced-GC causal bracket")
    assert result["owner_primal_step_reached"] is True
    assert set(result["owner_diagnostic_detail"][
        "arms_with_unregistered_ownership_observation"]) == {"C", "B1", "B2"}


def test_owner_probe_world_to_flow_mapping_and_append_only_evidence_guard(tmp_path):
    criteria, _, _ = host.load_owner_lifetime_criteria()
    origin = np.asarray(criteria["fixture"]["flow_origin_m"], dtype=np.float32)
    spacing = criteria["fixture"]["spacing_m"]
    world = [0.0, 0.0, 0.0]
    solver = ((np.asarray(world, dtype=np.float32) - origin) / np.float32(spacing)).tolist()
    names = [
        "candidate_solid_min_phi", "candidate_surface_min_abs_phi",
        "candidate_nearest_positive_phi", "registered_world_center",
        "outside_x_low", "outside_x_high", "outside_y_low", "outside_y_high",
        "outside_z_low", "outside_z_high",
    ]
    records = [{"name": name, "world_m": world, "flow_solver": solver,
                "cpu_measure": [0.0] * 7, "cuda_measure": [0.0] * 7}
               for name in names]
    report = {
        "fixed_probes_before_gc": {"candidate": records, "combined": records},
        "fixed_probes_after_gc": {"candidate": records, "combined": records},
    }
    result = host._verify_owner_probe_sets(report, criteria, origin, spacing)
    assert result["fixed_probes_after_gc"] == 20

    target = tmp_path / "result.json"
    sidecar = tmp_path / "result.json.sha256"
    host.require_append_only_evidence_target(target, sidecar)
    target.write_text("already registered\n")
    with pytest.raises(ValueError, match="append-only"):
        host.require_append_only_evidence_target(target, sidecar)
