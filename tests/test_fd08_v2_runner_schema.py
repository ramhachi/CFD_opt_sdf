"""Shared runner schema and execution-path tests; external infrastructure is mocked.

These tests are not T4 runtime or formal scientific evidence. The required-path
inventory below covers the runner's criteria consumer, including its mode split.
"""

import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "infra/kaggle/kernel_fd08_v2_r6/runner.py"
CRITERIA_FILES = {
    "formal": ROOT / "docs/evidence/fd08_v2_formal_2026_10_07_amend1/formal_criteria.json",
    "r6": ROOT / "docs/evidence/fd08_v2_r6_2026_10_06/r6_retry2_criteria.json",
    "setup": ROOT / "docs/evidence/fd08_v2_r6_2026_10_06/setup_rehearsal_criteria_retry1.json",
}
COMMON_PATHS = (
    "immutable", "kind", "source_commit", "kernel_id", "input_dataset_id",
    "source_inputs", "source_inputs.kernel_runner.sha256",
    "source_inputs.julia_project.sha256", "source_inputs.julia_manifest.sha256",
    "canonical_state.shape", "canonical_state.spacing_m", "canonical_state.origin_m",
    "canonical_state.source_surface_sha256", "state_inventory",
    "runtime.gpu_count", "runtime.gpu_name", "runtime.julia_archive_sha256",
    "runtime.julia_threads", "runtime.cuda_visible_devices", "runtime.compute_capability",
    "runtime.cuda_driver_api_version", "runtime.cuda_runtime_version", "runtime.julia_version",
    "runtime.cuda_jl_version", "runtime.waterlily_version",
)
MEASUREMENT_PATHS = (
    "registered_before_computation", "status", "qualification_flags", "expected_state_count",
    "measurement.per_state_timeout_s", "measurement.solver_wall_time_cap_s",
    "measurement.kernel_execution_allowance_s",
)
STATE_KEYS = {
    "name", "kind", "phi_raw_file", "npz_file", "phi_fortran_order_sha256",
    "phi_c_order_sha256", "npz_sha256", "state_sha256", "margin_m",
}
MOUNTED_FILES = ("criteria.json", "criteria.json.sha256", "fd08_v2_dataset_manifest.json")
NPZ_MEMBERS = ("phi", "metadata", "design_mask", "fixed_solid_mask", "forbidden_mask", "root_mask")


def _load_runner():
    spec = importlib.util.spec_from_file_location("fd08_v2_runner_schema", RUNNER)
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    return runner


@pytest.fixture
def runner(monkeypatch):
    monkeypatch.delenv("FD08_V2_STOP_BEFORE_SOLVER", raising=False)
    monkeypatch.delenv("FD08_V2_SOURCE_REF", raising=False)
    return _load_runner()


@pytest.mark.parametrize("mode", CRITERIA_FILES)
def test_registered_schema_contains_every_required_consumer_path(runner, mode):
    criteria = json.loads(CRITERIA_FILES[mode].read_text())
    paths = COMMON_PATHS + (() if mode == "setup" else MEASUREMENT_PATHS)
    paths += {
        "formal": ("geometry.minimum_zero_level_margin_m",),
        "r6": ("geometry_reject_gates.minimum_zero_level_margin_m",
               "setup_rehearsal.evidence_sha256"),
        "setup": ("per_state_timeout_s",),
    }[mode]
    for path in paths:
        value = criteria
        for key in path.split("."):
            value = value[key]
    assert all(STATE_KEYS <= row.keys() for row in criteria["state_inventory"])
    assert all({"path", "sha256"} <= entry.keys() for entry in criteria["source_inputs"].values())
    assert {row[key] for row in criteria["state_inventory"] for key in ("npz_file", "phi_raw_file")} <= criteria["dataset_files"].keys()
    assert criteria["source_inputs"]["candidate_c_job"]["path"] == "scripts/waterlily_xfid_candidate_c_job.jl"
    assert criteria["source_inputs"]["t4_smoke"]["path"] == "scripts/w0b_t4_smoke.jl"
    if mode != "setup":
        assert runner.geometry_contract(criteria)["minimum_zero_level_margin_m"] == 0.15
    else:
        assert "geometry" not in criteria and "geometry_reject_gates" not in criteria


def test_exact_immutable_r6_v6_mounted_dataset_remains_runner_compatible(runner):
    """Read exact preserved R6 bytes; no source fetch, solver, or analyzer."""
    dataset = ROOT / "work/r6_parent_v6"
    if not dataset.is_dir():
        pytest.skip("exact downloaded immutable R6 dataset v6 is unavailable in this checkout")
    criteria_path, criteria, criteria_sha = runner.load_criteria(dataset)
    assert criteria_path.read_bytes() == CRITERIA_FILES["r6"].read_bytes()
    assert criteria_sha == "90e9e40ffebffc96891af12bdc7942a0a038d877fe6e7bffe7a88574679e1837"
    assert criteria["kind"] == "fd08_v2_r6_calibration"
    assert len(criteria["state_inventory"]) == criteria["expected_state_count"] == 49
    assert len([path for path in dataset.rglob("*") if path.is_file()]) == 103
    runner.verify_dataset(dataset, criteria, criteria_sha)
    runner.validate_state_files(dataset, criteria)


def _mounted_fixture(tmp_path, runner, mode):
    """Keep registered mode/schema/count, with small synthetic state bytes."""
    criteria = json.loads(CRITERIA_FILES[mode].read_text())
    dataset, source = tmp_path / "input", tmp_path / "source"
    dataset.mkdir()
    project = source / "julia/CFDSDFWaterLilyT4"
    project.mkdir(parents=True)
    (project / "Project.toml").write_text("# unit-test project\n")
    (project / "Manifest.toml").write_text("# unit-test manifest\n")
    (source / "scripts").mkdir()
    (source / "scripts/waterlily_xfid_candidate_c_job.jl").write_text("# unit-test job\n")
    (source / "scripts/w0b_t4_smoke.jl").write_text("# unit-test smoke\n")
    copied_runner = source / "infra/kaggle/kernel_fd08_v2_r6/runner.py"
    copied_runner.parent.mkdir(parents=True)
    copied_runner.write_bytes(RUNNER.read_bytes())
    files = {
        "kernel_runner": copied_runner, "julia_project": project / "Project.toml",
        "julia_manifest": project / "Manifest.toml",
        "candidate_c_job": source / "scripts/waterlily_xfid_candidate_c_job.jl",
        "t4_smoke": source / "scripts/w0b_t4_smoke.jl",
    }
    criteria["source_inputs"] = {
        name: {"path": path.relative_to(source).as_posix(), "sha256": runner.sha256(path)}
        for name, path in files.items()
    }
    criteria["canonical_state"].update(shape=[5, 5, 5], spacing_m=1.0)
    dataset_files = {}
    for index, row in enumerate(criteria["state_inventory"]):
        phi = np.ones((5, 5, 5), dtype="<f4")
        phi[2, 2, 2] = -0.25 - index / 256
        raw_path, npz_path = dataset / row["phi_raw_file"], dataset / row["npz_file"]
        raw_path.write_bytes(phi.tobytes(order="F"))
        np.savez(npz_path, phi=phi, metadata=json.dumps({"state_sha256": row["state_sha256"]}),
                 design_mask=np.ones(phi.shape, dtype=bool),
                 fixed_solid_mask=np.zeros(phi.shape, dtype=bool),
                 forbidden_mask=np.zeros(phi.shape, dtype=bool), root_mask=np.zeros(phi.shape, dtype=bool))
        row.update(phi_fortran_order_sha256=runner.sha256(raw_path),
                   phi_c_order_sha256=runner.sha256_bytes(phi.tobytes(order="C")),
                   npz_sha256=runner.sha256(npz_path), margin_m=runner.margin_m(phi, 1.0))
        dataset_files.update({raw_path.name: runner.sha256(raw_path), npz_path.name: runner.sha256(npz_path)})
    if mode == "r6":
        setup_path = dataset / "setup_rehearsal_evidence.json"
        runner.write_json(setup_path, {"status": "PASS_SETUP_ONLY",
            "source_commit": criteria["source_commit"], "force_history_present": False})
        criteria["setup_rehearsal"]["evidence_sha256"] = runner.sha256(setup_path)
        dataset_files[setup_path.name] = runner.sha256(setup_path)
    criteria["dataset_files"] = dataset_files
    runner.write_json(dataset / "criteria.json", criteria)
    criteria_sha = runner.sha256(dataset / "criteria.json")
    (dataset / "criteria.json.sha256").write_text(criteria_sha + "\n")
    runner.write_json(dataset / "fd08_v2_dataset_manifest.json", {
        "criteria_sha256": criteria_sha,
        "files": {name: runner.sha256(dataset / name) for name in
                  sorted([*dataset_files, "criteria.json", "criteria.json.sha256"])},
    })
    return dataset, source, project, criteria


def _mock_external_infrastructure(monkeypatch, runner, source, criteria):
    """Only mock GPU/process/download boundaries; actual runner validators execute."""
    calls = []
    actual_check_output = runner.subprocess.check_output

    def check_output(args, **kwargs):
        if args[0] == "nvidia-smi":
            calls.append("gpu_inventory")
            return "0, Tesla T4, GPU-unit-0, 15360 MiB, unit-driver\n1, Tesla T4, GPU-unit-1, 15360 MiB, unit-driver\n"
        if args[0] != "git":
            return actual_check_output(args, **kwargs)
        assert args == ["git", "-C", str(source), "rev-parse", "HEAD"]
        calls.append("verify_source")
        return criteria["source_commit"] + "\n"

    def fetch(base, bound, out):
        calls.append("source_fetch")
        return source

    def install(base, bound, out):
        calls.append("julia_install")
        return source / "julia-1.12.6/bin/julia"

    def command(args, log_path, *, env=None, timeout=3600, check=True):
        if args[-1] == "using Pkg; Pkg.instantiate()":
            calls.append("instantiate")
            text = "unit-test instantiate\n"
        elif args[-1].endswith("w0b_t4_smoke.jl"):
            calls.append("runtime_smoke")
            backend = criteria["runtime"]
            text = "W0B_SMOKE_DONE\nCUDA_FUNCTIONAL true\nNO_SOLVER_STEP\n" + "\n".join(
                f"{marker} {backend[key]}" for marker, key in (
                    ("GPU_COMPUTE_CAPABILITY", "compute_capability"),
                    ("CUDA_DRIVER_VERSION", "cuda_driver_api_version"),
                    ("CUDA_RUNTIME_VERSION", "cuda_runtime_version"), ("JULIA_VERSION", "julia_version"),
                    ("CUDA_JL_VERSION", "cuda_jl_version"), ("WATERLILY_VERSION", "waterlily_version"),
                    ("GPU_NAME", "gpu_name")))
        elif args[3].endswith("waterlily_fd08_v2_setup_rehearsal.jl"):
            calls.append("setup_state")
            runner.write_json(Path(args[-1]), {"evidence_class": "setup_only_not_calibration",
                "state_sha256": env["W4_STATE_SHA256"], "phi_fortran_sha256": env["W4_PHI_FORTRAN_SHA256"],
                "device_roundtrip_sha256": env["W4_PHI_FORTRAN_SHA256"], "finite_u": True, "finite_p": True})
            text = "FD08_V2_SETUP_DONE unit-test\n"
        else:
            assert args[3].endswith("waterlily_xfid_candidate_c_job.jl")
            assert env.get("FD08_V2_STOP_BEFORE_SOLVER") != "1", "measurement process launched during rehearsal"
            calls.append("measurement_state")
            outdir = Path(args[-1])
            csv = outdir / "flow_24.forces.csv"
            csv.write_text("unit-test force history\n")
            runner.write_json(outdir / "flow_24.summary.json", {
                "state_sha256": env["W4_STATE_SHA256"], "phi_fortran_sha256": env["W4_PHI_FORTRAN_SHA256"],
                "device_roundtrip_sha256": env["W4_PHI_FORTRAN_SHA256"],
                "finite_u": True, "finite_p": True, "finite_forces": True,
                "t_end_reached": 120.0, "force_csv_sha256": runner.sha256(csv), "wall_seconds": 0.01})
            (outdir / "W4_JOB_DONE").write_text("unit-test\n")
            text = "W4_SOLVER_STEP_INVOKED flow_24\nW4_SOLVER_STEP_RETURNED flow_24\n"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text(text)
        return text

    monkeypatch.setattr(runner.subprocess, "check_output", check_output)
    monkeypatch.setattr(runner, "fetch_source", fetch)
    monkeypatch.setattr(runner, "install_julia", install)
    monkeypatch.setattr(runner, "command", command)
    return calls


@pytest.mark.parametrize("mode", ("formal", "r6"))
def test_geometry_dispatch_uses_only_registered_mode_key_and_threshold(tmp_path, runner, mode):
    dataset, _, _, criteria = _mounted_fixture(tmp_path, runner, mode)
    runner.validate_state_files(dataset, criteria)
    key = "geometry" if mode == "formal" else "geometry_reject_gates"
    wrong_key = "geometry_reject_gates" if mode == "formal" else "geometry"
    criteria[wrong_key] = {"minimum_zero_level_margin_m": 0.0}
    criteria[key]["minimum_zero_level_margin_m"] = 2.0
    with pytest.raises(RuntimeError, match="zero-level margin failure"):
        runner.validate_state_files(dataset, criteria)
    del criteria[key]
    with pytest.raises(RuntimeError, match=key + ": geometry contract requires"):
        runner.validate_state_files(dataset, criteria)


@pytest.mark.parametrize("mode", CRITERIA_FILES)
@pytest.mark.parametrize("contract", ([], {}))
def test_geometry_dispatch_rejects_missing_threshold_or_nondict_contract(runner, mode, contract):
    kind = json.loads(CRITERIA_FILES[mode].read_text())["kind"]
    key = "geometry" if mode == "formal" else "geometry_reject_gates"
    with pytest.raises(RuntimeError, match=key + ": geometry contract requires"):
        runner.geometry_contract({"kind": kind, key: contract})


@pytest.mark.parametrize("mode", ("formal", "r6"))
def test_main_pre_solver_reaches_every_state_without_measurement_or_scientific_terminal(
        tmp_path, monkeypatch, runner, mode, capsys):
    dataset, source, project, criteria = _mounted_fixture(tmp_path, runner, mode)
    monkeypatch.setattr(runner, "INPUT_ROOT", dataset)
    monkeypatch.setattr(runner, "OUT_ROOT", tmp_path / "output")
    monkeypatch.setenv("FD08_V2_STOP_BEFORE_SOLVER", "1")
    monkeypatch.setenv("UNIT_TEST_SECRET", "must never be recorded")
    calls = _mock_external_infrastructure(monkeypatch, runner, source, criteria)
    runner.main()
    out = runner.OUT
    result = json.loads((out / "pre_solver_execution_path.json").read_text())
    count = 25 if mode == "formal" else 49
    assert calls == ["gpu_inventory", "source_fetch", "verify_source", "julia_install", "instantiate", "runtime_smoke"]
    assert result["verified_state_count"] == result["prepared_state_count"] == result["expected_state_count"] == count
    assert result["state_count"] == result["state_verification_count"] == count
    assert result["status"] == "PASS_PRE_SOLVER_EXECUTION_PATH"
    assert result["last_stage"] == "pre_solver_invocation"
    assert result["solver_started"] is result["force_history_present"] is False
    assert result["scientific_verdict"] is None
    assert all(value is False for value in result["qualification_flags"].values())
    assert result["runner_sha256"] == runner.sha256(RUNNER)
    assert result["criteria_sha256"] == runner.sha256(dataset / "criteria.json")
    assert result["dataset_manifest_sha256"] == runner.sha256(dataset / "fd08_v2_dataset_manifest.json")
    assert result["source_commit"] == criteria["source_commit"]
    assert result["measurement"] == criteria["measurement"]
    assert result["runtime"] == criteria["runtime"]
    assert result["source_inputs_sha256"] == runner.sha256_bytes(json.dumps(
        criteria["source_inputs"], sort_keys=True, allow_nan=False).encode())
    assert result["source_input_count"] == len(criteria["source_inputs"])
    assert result["dataset_inventory_sha256"] == runner.sha256_bytes(json.dumps({
        path.relative_to(dataset).as_posix(): runner.sha256(path)
        for path in sorted(dataset.rglob("*")) if path.is_file()
    }, sort_keys=True, allow_nan=False).encode())
    assert set(result["states"]) == {row["name"] for row in criteria["state_inventory"]}
    for row in criteria["state_inventory"]:
        state = result["states"][row["name"]]
        config = state["config"]
        env = config["environment"]
        assert state["status"] == "PRE_SOLVER_PREPARED" and state["solver_started"] is False
        assert state["state_sha256"] == env["W4_STATE_SHA256"] == row["state_sha256"]
        assert state["config_sha256"] == runner.sha256_bytes(json.dumps(config, sort_keys=True, allow_nan=False).encode())
        assert config["args"] == [str(source / "julia-1.12.6/bin/julia"), "--startup-file=no",
            f"--project={project}", str(source / "scripts/waterlily_xfid_candidate_c_job.jl"),
            str(dataset / row["phi_raw_file"]), str(out / "states" / row["name"])]
        assert config["timeout_s"] == criteria["measurement"]["per_state_timeout_s"]
        assert config["log_path"] == str(out / "states" / row["name"] / "job.log")
        assert env["W4_PHI_FORTRAN_SHA256"] == row["phi_fortran_order_sha256"]
        assert env["W4_STATE_NPZ_SHA256"] == row["npz_sha256"]
        assert env["W4_PHI_C_ORDER_SHA256"] == row["phi_c_order_sha256"]
        assert env["W4_SELECTED_GPU_UUID"] == "GPU-unit-0"
        assert env["CUDA_VISIBLE_DEVICES"] == "0" and env["JULIA_NUM_THREADS"] == "1"
        assert "UNIT_TEST_SECRET" not in env
        assert (out / "states" / row["name"]).is_dir()
    assert not any(path.is_file() for path in (out / "states").rglob("*"))
    assert not any((out / name).exists() for name in ("result.json", "partial_result.json", "DONE"))
    assert (out / "PASS_PRE_SOLVER_EXECUTION_PATH").read_text() == "PASS_PRE_SOLVER_EXECUTION_PATH\n"
    assert "FD08_V2_TERMINAL PASS_PRE_SOLVER_EXECUTION_PATH" in capsys.readouterr().out


@pytest.mark.parametrize("mode,flag", (("formal", None), ("r6", "0"), ("setup", None)))
def test_main_default_behavior_keeps_existing_measurement_and_setup_terminals(
        tmp_path, monkeypatch, runner, mode, flag):
    dataset, source, _, criteria = _mounted_fixture(tmp_path, runner, mode)
    monkeypatch.setattr(runner, "INPUT_ROOT", dataset)
    monkeypatch.setattr(runner, "OUT_ROOT", tmp_path / "output")
    if flag is not None:
        monkeypatch.setenv("FD08_V2_STOP_BEFORE_SOLVER", flag)
    calls = _mock_external_infrastructure(monkeypatch, runner, source, criteria)
    runner.main()
    result = json.loads((runner.OUT / "result.json").read_text())
    expected = len(criteria["state_inventory"])
    assert result["state_count"] == expected
    assert result["status"] == ("SETUP_ONLY_COMPLETE" if mode == "setup" else "COMPLETE")
    assert calls.count("setup_state" if mode == "setup" else "measurement_state") == expected
    assert (runner.OUT / "DONE").is_file()
    assert not (runner.OUT / "partial_result.json").exists()
    assert not (runner.OUT / "pre_solver_execution_path.json").exists()
    assert not (runner.OUT / "PASS_PRE_SOLVER_EXECUTION_PATH").exists()


def test_setup_only_kind_cannot_masquerade_as_pre_solver_measurement_rehearsal(tmp_path, monkeypatch, runner):
    dataset, _, _, _ = _mounted_fixture(tmp_path, runner, "setup")
    monkeypatch.setattr(runner, "INPUT_ROOT", dataset)
    monkeypatch.setattr(runner, "OUT_ROOT", tmp_path / "output")
    monkeypatch.setenv("FD08_V2_STOP_BEFORE_SOLVER", "1")
    with pytest.raises(RuntimeError, match="requires a measurement criteria kind"):
        runner.main()
    assert not runner.OUT_ROOT.exists()


def test_source_fetch_default_and_explicit_feature_override(monkeypatch, runner, tmp_path):
    assert runner.SOURCE_REF == "refs/heads/codex/kaggle-batch-migration"
    for ref in (runner.SOURCE_REF, "refs/heads/exp/issue46-fd08v2-formal-amend2-runner-schema-2026-10-07"):
        monkeypatch.setenv("FD08_V2_SOURCE_REF", ref)
        loaded = _load_runner()
        calls = []
        monkeypatch.setattr(loaded, "command", lambda args, log, **kwargs: calls.append(args))
        loaded.fetch_source(tmp_path, {"source_commit": "bound-commit"}, tmp_path / "logs")
        assert calls[1][-1] == ref
        assert calls[2][-1] == "bound-commit"


@pytest.mark.parametrize("flag", ("", "true", "yes", "2"))
def test_invalid_pre_solver_flag_fails_closed_before_process_or_output(tmp_path, monkeypatch, runner, flag):
    dataset, _, _, _ = _mounted_fixture(tmp_path, runner, "formal")
    monkeypatch.setattr(runner, "INPUT_ROOT", dataset)
    monkeypatch.setattr(runner, "OUT_ROOT", tmp_path / "output")
    monkeypatch.setenv("FD08_V2_STOP_BEFORE_SOLVER", flag)
    with pytest.raises(RuntimeError, match="must be absent, 0, or 1"):
        runner.main()
    assert not runner.OUT_ROOT.exists()


def test_pre_solver_main_rejects_source_integrity_failure_before_preparation(tmp_path, monkeypatch, runner):
    dataset, source, _, criteria = _mounted_fixture(tmp_path, runner, "formal")
    monkeypatch.setattr(runner, "INPUT_ROOT", dataset)
    monkeypatch.setattr(runner, "OUT_ROOT", tmp_path / "output")
    monkeypatch.setenv("FD08_V2_STOP_BEFORE_SOLVER", "1")
    calls = _mock_external_infrastructure(monkeypatch, runner, source, criteria)
    (source / "scripts/waterlily_xfid_candidate_c_job.jl").write_text("unexpected changed bytes\n")
    with pytest.raises(RuntimeError, match="registered source input SHA mismatch"):
        runner.main()
    assert "julia_install" not in calls and "runtime_smoke" not in calls
    assert not (runner.OUT / "states").exists()
    assert not (runner.OUT / "PASS_PRE_SOLVER_EXECUTION_PATH").exists()
