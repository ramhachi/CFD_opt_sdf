"""LOCAL-GPU-01 tools: CPU-only probes and fake subprocesses; never launch CUDA."""
import hashlib
import json
import sys
from contextlib import contextmanager
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "infra/local_gpu"))
import capture_lock as C
import local_gpu as L


def locked(tmp_path):
    env = {
        "backend_profile": "local_rtx4070ti",
        "gpu": {"name": "NVIDIA GeForce RTX 4070 Ti", "uuid": "GPU-test", "driver_version": "592.02"},
        "julia": {"version": "julia version 1.12.6", "executable": "/fake/julia", "sha256": "a" * 64,
                  "root": "/fake/julia-install", "root_sha256": "f" * 64},
        "julia_depot": {"path": str(tmp_path / "dedicated-depot"), "manifest_packages_sha256": "e" * 64},
        "project": {"path": "julia/CFDSDFWaterLilyT4", "manifest_sha256": "b" * 64, "project_sha256": "d" * 64},
        "cuda_visible_devices": "0", "cuda_device_order": "PCI_BUS_ID",
    }
    lock = {"schema_version": 1, "captured_utc": "2026-11-06T00:00:00+00:00", "environment": env,
            "observations": {"cuda_versioninfo": "free memory changes"}, "errors": []}
    path = tmp_path / "lock.json"
    path.write_bytes(C.canonical_bytes(lock))
    path.with_name("lock.json.sha256").write_text(C.sha(path) + "\n")
    return path, lock


def test_canonical_json_and_sha(tmp_path):
    a = {"z": [2, 1], "a": {"unicode": "日本語", "x": 1}}
    b = {"a": {"x": 1, "unicode": "日本語"}, "z": [2, 1]}
    assert C.canonical_bytes(a) == C.canonical_bytes(b)
    assert C.canonical_bytes(a).endswith(b"\n") and not C.canonical_bytes(a).endswith(b"\n\n")
    p = tmp_path / "canonical.json"
    p.write_bytes(C.canonical_bytes(a))
    assert C.sha(p) == hashlib.sha256(p.read_bytes()).hexdigest()
    with pytest.raises(ValueError):
        C.canonical_bytes({"bad": float("nan")})


def test_check_lock_ignores_observation_time_but_detects_driver_and_manifest(tmp_path, monkeypatch):
    path, lock = locked(tmp_path)
    now = json.loads(json.dumps(lock))
    now.update(captured_utc="later", observations={"cuda_versioninfo": "different free memory"})
    monkeypatch.setattr(C, "capture", lambda **kw: now)
    assert L.check_lock(path)["environment"] == lock["environment"]
    for component, key in (("gpu", "driver_version"), ("project", "manifest_sha256")):
        original = now["environment"][component][key]
        now["environment"][component][key] = "changed"
        with pytest.raises(ValueError, match="environment differs"):
            L.check_lock(path)
        now["environment"][component][key] = original


def test_lock_tamper_and_missing_fields_refused(tmp_path, monkeypatch):
    path, lock = locked(tmp_path)
    path.write_text(path.read_text() + " ")
    with pytest.raises(ValueError, match="SHA|canonical"):
        L.check_lock(path)
    path.write_bytes(C.canonical_bytes(lock))
    lock["environment"]["gpu"]["name"] = {"error": "nvidia-smi unavailable"}
    monkeypatch.setattr(C, "capture", lambda **kw: lock)
    with pytest.raises(ValueError, match="mandatory|GPU|gpu"):
        L.check_lock(path)


def test_capture_missing_gpu_is_json_error_without_traceback(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(C, "probe", lambda argv, **kw: {"error": f"not available: {argv[0]}"})
    out = tmp_path / "not-a-lock.json"
    assert C.main(["--out", str(out), "--julia", "/missing/julia"]) != 0
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "ERROR" and result["errors"]
    assert not out.exists()
    assert "gpu.name" in " ".join(result["errors"])
    assert "null" not in C.canonical_bytes(result).decode()


def fake_kernel(tmp_path, code=None):
    kernel = tmp_path / "kernel"
    kernel.mkdir()
    runner = kernel / "runner.py"
    pins = {"julia/CFDSDFWaterLilyT4/Manifest.toml": "b" * 64, "julia/CFDSDFWaterLilyT4/Project.toml": "d" * 64}
    header = (f"PINS = {pins!r}\nPROJECT = 'julia/CFDSDFWaterLilyT4'\nSOURCE_COMMIT = {'c' * 40!r}\n"
              "CAMPAIGN = 'infra/local_gpu/fake.campaign.json'\nKERNEL = 'a'\nSMOKE = True\n")
    runner.write_text(header + (code or "import os\nfrom pathlib import Path\np=Path(os.environ['CAMPAIGN_WORK_ROOT'])\n(p/'DONE').write_text('fake CPU runner only\\n')\n"))
    (kernel / "local_kernel.json").write_text(json.dumps({
        "backend_profile": "local_rtx4070ti", "used_gpu_count": 1,
        "runner_sha256": C.sha(runner), "campaign_path": "infra/local_gpu/fake.campaign.json",
        "source_commit": "c" * 40, "kernel": "a", "smoke": True,
    }))
    return kernel


def no_telemetry(monkeypatch):
    monkeypatch.setattr(L, "query_memory", lambda: {"error": "synthetic: no GPU"})
    monkeypatch.setattr(L, "query_watch", lambda: {"error": "synthetic: no GPU"})
    monkeypatch.setattr(L, "query_resets", lambda started: {"error": "synthetic: no reset observer"})


def test_run_fake_runner_done_and_local_record(tmp_path, monkeypatch):
    path, lock = locked(tmp_path)
    monkeypatch.setattr(C, "capture", lambda **kw: lock)
    no_telemetry(monkeypatch)
    kernel = fake_kernel(tmp_path)
    out = tmp_path / "run"
    assert L.run(kernel, out, lock_path=path) == 0
    assert (out / "DONE").is_file()
    record = json.loads((out / "local_run.json").read_text())
    assert record["returncode"] == 0 and record["done"] is True
    assert record["lock_sha256"] == C.sha(path)
    assert record["cuda_visible_devices"] == "0"
    assert record["output_sha256"]["DONE"] == C.sha(out / "DONE")
    assert record["started_utc"] <= record["finished_utc"]
    assert record["wall_seconds"] >= 0 and record["stage_wall_seconds"]
    assert record["peak_vram_mib"]["error"]
    with pytest.raises(ValueError, match="overwrite|exists"):
        L.run(kernel, out, lock_path=path)


def test_run_nonzero_and_missing_done_are_not_success(tmp_path, monkeypatch):
    path, lock = locked(tmp_path)
    monkeypatch.setattr(C, "capture", lambda **kw: lock)
    no_telemetry(monkeypatch)
    kernel = fake_kernel(tmp_path, "raise SystemExit(7)\n")
    out = tmp_path / "failed"
    assert L.run(kernel, out, lock_path=path) == 7
    record = json.loads((out / "local_run.json").read_text())
    assert record["returncode"] == 7 and record["done"] is False


def test_run_cleanup_failure_is_not_a_successful_done(tmp_path, monkeypatch):
    path, lock = locked(tmp_path)
    monkeypatch.setattr(C, "capture", lambda **kw: lock)
    no_telemetry(monkeypatch)
    kernel = fake_kernel(tmp_path)

    @contextmanager
    def failed_cleanup(*args):
        yield
        raise OSError("synthetic bind cleanup failed")

    monkeypatch.setattr(L, "dataset_mount", failed_cleanup)
    out = tmp_path / "cleanup_failed"
    assert L.run(kernel, out, lock_path=path) != 0
    record = C.jload(out / "local_run.json")
    assert record["done"] is False
    assert record["execution_error"] == "synthetic bind cleanup failed"


def test_run_refuses_changed_kernel_before_launch(tmp_path, monkeypatch):
    path, lock = locked(tmp_path)
    monkeypatch.setattr(C, "capture", lambda **kw: lock)
    kernel = fake_kernel(tmp_path)
    (kernel / "runner.py").write_text("raise RuntimeError('never launch')\n")
    with pytest.raises(ValueError, match="runner.*SHA|runner.*hash"):
        L.run(kernel, tmp_path / "out", lock_path=path)
    assert not (tmp_path / "out").exists()


def test_duplicate_json_keys_and_nonfinite_refused(tmp_path):
    p = tmp_path / "bad.json"
    for text in ('{"a":1,"a":2}', '{"x":NaN}', '{"x":1e309}'):
        p.write_text(text)
        with pytest.raises(ValueError):
            C.jload(p)


def test_repeat_runs_are_cold_and_group_watch_is_closed(tmp_path, monkeypatch):
    path, lock = locked(tmp_path)
    monkeypatch.setattr(C, "capture", lambda **kw: lock)
    no_telemetry(monkeypatch)
    kernel = fake_kernel(tmp_path)
    out = tmp_path / "repeat_group"
    assert L.main(["run", str(kernel), "--out", str(out), "--repeat", "2", "--lock", str(path)]) == 0
    records = [C.jload(out / f"repeat_{i:03d}" / "local_run.json") for i in (1, 2)]
    assert all(r["done"] for r in records)
    assert records[0]["finished_utc"] <= records[1]["started_utc"]
    status = C.jload(out / "watchdog_status.json")
    assert status["completed"] and status["watchdog_sha256"] == C.sha(out / "watchdog.csv")
    assert status["driver_reset_monitor"]["available"] is False
    assert L.main(["run", str(kernel), "--out", str(out), "--repeat", "2", "--lock", str(path)]) == 2


def test_interruption_and_resume_provenance_is_immutable(tmp_path, monkeypatch):
    path, lock = locked(tmp_path)
    monkeypatch.setattr(C, "capture", lambda **kw: lock)
    no_telemetry(monkeypatch)
    kernel = fake_kernel(tmp_path, "import os,time\nfrom pathlib import Path\nPath(os.environ['LOCAL_GPU_CHECKPOINT_PATH']).write_bytes(b'CPU fake checkpoint')\ntime.sleep(30)\n")
    old = tmp_path / "R5_interrupted"
    assert L.run(kernel, old, lock_path=path, checkpoint_every=10, interrupt_after=0.5) < 0
    before = C.sha(old / "local_run.json")
    record = C.jload(old / "local_run.json")
    assert record["done"] is False and record["interrupted"] is True
    resume = tmp_path / "R5"
    resume.mkdir()
    result = L.copy_resume(resume, old / "local_run.json", old / "checkpoint.bin", C.sha(path))
    assert result["resumed"] and C.sha(resume / result["checkpoint_path"]) == result["checkpoint_sha256"]
    assert C.sha(old / "local_run.json") == before
    (old / "checkpoint.bin").write_bytes(b'tampered')
    bad = tmp_path / "bad_resume"
    bad.mkdir()
    with pytest.raises(ValueError, match="checkpoint SHA"):
        L.copy_resume(bad, old / "local_run.json", old / "checkpoint.bin", C.sha(path))


def test_telemetry_and_reset_failures_are_explicit(monkeypatch):
    monkeypatch.setattr(C, "probe", lambda *args, **kw: "NaN")
    assert "non-finite" in L.query_memory()["error"]
    assert "unrecognized" in L.query_resets("2026-11-06T00:00:00+00:00")["error"]
    monkeypatch.setattr(C, "probe", lambda *args, **kw: "NO_RESET")
    assert L.query_resets("2026-11-06T00:00:00+00:00") is False
    monkeypatch.setattr(C, "probe", lambda *args, **kw: "RESET")
    assert L.query_resets("2026-11-06T00:00:00+00:00") is True


def test_wsl_optional_query_fallback_and_utf16_decode(tmp_path, monkeypatch):
    def probe(argv, **kw):
        query = next((s for s in argv if str(s).startswith("--query-gpu=")), "")
        field = query.removeprefix("--query-gpu=")
        return {"name": "NVIDIA GeForce RTX 4070 Ti", "driver_version": "592.02", "uuid": "GPU-test"}.get(field, C.error("unsupported query"))
    monkeypatch.setattr(C, "probe", probe)
    lock = C.capture(julia="/missing/julia", wslconfig=tmp_path / "missing.ini")
    assert lock["environment"]["gpu"]["name"] == "NVIDIA GeForce RTX 4070 Ti"
    assert lock["environment"]["gpu"]["power_limit"]["error"]
    assert C.decode("WSL version: 3.0".encode("utf-16-le")) == "WSL version: 3.0"


@pytest.mark.parametrize("name", ["Manifest", "Project"])
def test_run_refuses_kernel_runtime_pins_different_from_lock_before_launch(tmp_path, monkeypatch, name):
    path, lock = locked(tmp_path)
    monkeypatch.setattr(C, "capture", lambda **kw: lock)
    kernel = fake_kernel(tmp_path)
    runner = kernel / "runner.py"
    old_sha = "b" * 64 if name == "Manifest" else "d" * 64
    runner.write_text(runner.read_text().replace(old_sha, "e" * 64))
    metadata = C.jload(kernel / "local_kernel.json")
    metadata["runner_sha256"] = C.sha(runner)
    (kernel / "local_kernel.json").write_text(json.dumps(metadata))
    with pytest.raises(ValueError, match="pin differs from environment lock"):
        L.run(kernel, tmp_path / "never_started", lock_path=path)
    assert not (tmp_path / "never_started").exists()


def test_check_lock_recaptures_explicit_wslconfig_path(tmp_path, monkeypatch):
    path, lock = locked(tmp_path)
    source = str(tmp_path / "custom.wslconfig")
    lock["environment"]["wsl"] = {"settings": {"wslconfig_path": source}}
    path.write_bytes(C.canonical_bytes(lock))
    path.with_name(path.name + ".sha256").write_text(C.sha(path) + "\n")
    def capture(**kw):
        assert kw["wslconfig"] == source
        return lock
    monkeypatch.setattr(C, "capture", capture)
    assert L.check_lock(path) == lock


def test_julia_install_and_depot_are_required_lock_identity(tmp_path):
    _, lock = locked(tmp_path)
    for section, key in (("julia", "root_sha256"), ("julia_depot", "manifest_packages_sha256")):
        missing = json.loads(json.dumps(lock))
        missing["environment"][section].pop(key)
        assert any(f"{section}.{key}" in reason for reason in C.required_errors(missing))


def test_watch_query_preserves_supported_fields_and_missing_reasons(monkeypatch):
    def probe(argv, **kwargs):
        field = next(s.split("=", 1)[1] for s in argv if s.startswith("--query-gpu="))
        values = {"clocks.sm": "2000", "temperature.gpu": "55", "power.draw": "[Not Supported]",
                  "memory.used": "4096", "utilization.gpu": "90", "uuid": "GPU-test", "memory.total": "12288"}
        return values.get(field, C.error("WSL2 rejects combined query"))
    monkeypatch.setattr(C, "probe", probe)
    row = L.query_watch()
    assert row["utilization_gpu_pct"] == 90 and row["gpu_uuid"] == "GPU-test"
    assert row["memory_total_mib"] == 12288 and row["memory_used_mib"] == 4096
    assert row["power_draw_w"] == "" and "power.draw" in row["missing_reason"]
    assert not row.get("error")


def test_run_records_the_effective_filtered_child_environment(tmp_path, monkeypatch):
    path, lock = locked(tmp_path)
    monkeypatch.setattr(C, "capture", lambda **kw: lock)
    no_telemetry(monkeypatch)
    monkeypatch.setenv("JULIA_LOAD_PATH", "@:@stdlib")
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "7")
    monkeypatch.setenv("JULIA_DEPOT_PATH", "/foreign/depot")
    monkeypatch.setenv("UNRELATED_FOR_TEST", "do not retain")
    kernel = fake_kernel(tmp_path, "import json,os\nfrom pathlib import Path\np=Path(os.environ['CAMPAIGN_WORK_ROOT'])\n(p/'effective_env.json').write_text(json.dumps({k:v for k,v in os.environ.items() if k.startswith(('JULIA_','CUDA_','NVIDIA_','WSL'))}))\n(p/'DONE').write_text('CPU stub\\n')\n")
    out = tmp_path / "environment_run"
    assert L.run(kernel, out, lock_path=path) == 0
    record, effective = C.jload(out / "local_run.json"), C.jload(out / "effective_env.json")
    expected = {key: value for key, value in effective.items() if key.startswith(("JULIA_", "CUDA_", "NVIDIA_", "WSL"))}
    assert record["filtered_environment"] == expected
    assert expected["CUDA_VISIBLE_DEVICES"] == "0" and expected["JULIA_LOAD_PATH"] == "@:@stdlib"
    assert expected["JULIA_DEPOT_PATH"] == lock["environment"]["julia_depot"]["path"]
    assert record["julia_depot"] == lock["environment"]["julia_depot"]
    assert "logical_device_count" in record["used_gpu_count_evidence"]


def test_capture_records_root_sha_and_expected_archive_separately(tmp_path, monkeypatch):
    install = tmp_path / "julia-install"
    (install / "bin").mkdir(parents=True)
    executable = install / "bin/julia"
    executable.write_text("synthetic Julia launcher")
    (install / "lib").mkdir()
    (install / "lib/libjulia.so").write_bytes(b"synthetic library")
    monkeypatch.setattr(C.shutil, "which", lambda name: str(executable))
    monkeypatch.setattr(C, "probe", lambda argv, **kw: C.error("synthetic unavailable"))
    monkeypatch.setattr(C, "package_identity", lambda *args, **kwargs: {"path": str(tmp_path / "depot"), "manifest_packages_sha256": "e" * 64})
    capture = C.capture(julia=str(executable), depot=str(tmp_path / "depot"), wslconfig=tmp_path / "missing")
    julia = capture["environment"]["julia"]
    assert julia["root"] == str(install)
    before = julia["root_sha256"]
    (install / "lib/libjulia.so").write_bytes(b"changed library, identical launcher")
    assert C.capture(julia=str(executable), depot=str(tmp_path / "depot"), wslconfig=tmp_path / "missing")["environment"]["julia"]["root_sha256"] != before
    assert julia["expected_archive_sha256"] == C.runner_constants()["JULIA_SHA256"]
    assert "archive_sha256" not in julia
    assert capture["environment"]["host"]["hardware_accelerated_gpu_scheduling"]["error"]


def test_bench_passes_lock_binding_and_dedicated_runtime_environment(tmp_path, monkeypatch):
    path, lock = locked(tmp_path)
    monkeypatch.setattr(L, "check_lock", lambda path: lock)
    observed = {}
    def run(argv, **kwargs):
        observed.update(argv=argv, env=kwargs["env"])
        return type("Completed", (), {"returncode": 0})()
    monkeypatch.setattr(L.subprocess, "run", run)
    assert L.main(["bench", "--out", str(tmp_path / "bench.json"), "--lock", str(path)]) == 0
    argv = observed["argv"]
    assert argv[argv.index("--lock-sha256") + 1] == C.sha(path)
    assert observed["env"]["JULIA_DEPOT_PATH"] == lock["environment"]["julia_depot"]["path"]


def test_watch_nonfinite_is_failure_but_missing_required_is_incomplete(monkeypatch):
    def probe(argv, **kwargs):
        query = next(s.split("=", 1)[1] for s in argv if s.startswith("--query-gpu="))
        return {"memory.used": "NaN", "uuid": "[N/A]"}.get(query, C.error("not supported"))
    monkeypatch.setattr(C, "probe", probe)
    row = L.query_watch()
    assert "non-finite" in row["error"]
    assert "uuid" in row["missing_reason"]
    monkeypatch.setattr(C, "probe", lambda *args, **kwargs: "[N/A]")
    assert "incomplete" in L.query_memory()


def test_verify_cli_calls_local_wrapper_with_source_and_smoke(tmp_path, monkeypatch):
    def verify(campaign, outputs, **kwargs):
        assert campaign == tmp_path / "campaign.json" and outputs == [tmp_path / "output"]
        assert kwargs["smoke"] is True and kwargs["source_commit"] == "a" * 40
        return {"kind": "local_test"}
    monkeypatch.setattr(L.BP, "verify_local", verify)
    assert L.main(["verify", "--campaign", str(tmp_path / "campaign.json"), "--kernel-output", str(tmp_path / "output"),
                   "--smoke", "--source-commit", "a" * 40]) == 0


@pytest.mark.parametrize("value,enabled", [(1, False), (2, True)])
def test_hags_records_observed_explicit_registry_state(monkeypatch, value, enabled):
    monkeypatch.setattr(C, "probe", lambda *args, **kwargs: f"HwSchMode    REG_DWORD    0x{value:x}")
    assert C.hags_state()["enabled"] is enabled
