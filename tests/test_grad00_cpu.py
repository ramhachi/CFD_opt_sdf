"""CPU artifact-wrapper contracts using fake Julia subprocesses only."""
from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

from scripts import analyze_grad00 as A

ROOT = Path(__file__).resolve().parents[1]


def wrapper():
    spec = importlib.util.spec_from_file_location("grad00_cpu_wrapper_test", ROOT / "scripts/run_grad00_cpu.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def setup(monkeypatch, tmp_path, *, arm="quick", real_type="Float64", project="julia/CFDSDFWaterLily", code=0,
          terminal=None, error=None, damage=None):
    module = wrapper()
    source_path = "scripts/grad_g2_window.py"
    ref = {"schema_version": 1, "kind": "grad00_fd08_reference", "definition": "synthetic CPU wrapper fixture",
           "sources": {source_path: module.B.sha(ROOT / source_path)},
           "directions": {d: {"epsilon_m": (i + 1) * 1e-3, "spread_n_per_m": {"fx": 0.0, "fz": 0.0}}
                          for i, d in enumerate(module.B.DIRECTIONS)}}
    # The loader itself is exercised in test_grad00_kernels. This synthetic
    # path supplies an existing source-byte pin without creating repo fixtures.
    config = {"path": "tests/test_grad00.py", "sha256": module.B.sha(ROOT / "tests/test_grad00.py"),
              **{k: ref[k] for k in ("definition", "directions", "sources")}}
    verified, calls = [], []
    monkeypatch.setattr(module.B, "reference_config", lambda path: config)
    monkeypatch.setattr(module.B, "verify_source", lambda commit, paths: verified.append((commit, paths)))
    monkeypatch.setattr(module.B, "tree_id", lambda commit: "b" * 40)
    output = tmp_path / "output"
    kwargs = dict(source_commit="a" * 40, reference_path=Path("synthetic-reference.json"), output_dir=output,
                  arm=arm, real_type=real_type, project=project, timeout_s=60.0, julia="/synthetic/julia")

    def fake_run(args, *, env, stdout, stderr, timeout, cwd, check):
        calls.append((args, env, timeout, cwd))
        assert verified and (output / "run_identity.json").is_file()
        stdout.write("synthetic Julia log\n")
        if error is not None:
            raise error
        status = terminal if terminal is not None else "COMPLETE" if code == 0 else "BLOCKED" if code == 3 else "ERROR"
        dirs = module.B.DIRECTIONS[:2]
        order = ["plain", *(d + suffix for d in dirs for suffix in ("", "__plus", "__minus"))]
        statuses = {label: "COMPLETE" for label in order}
        if status == "BLOCKED":
            statuses[dirs[0]] = "BLOCKED"
        index = {"status": status, "arm": arm, "real_type": real_type, "backend": "cpu", "directions": list(dirs),
                 "waterlily": "1.10.0" if project.endswith("110") else "1.8.0", "preflight": {"pass": True},
                 "run_order": order, "run_status": statuses, "runs": {label: {} for label in order}}
        if damage == "inventory":
            index["runs"].pop(order[-1])
        elif damage == "backend":
            index["backend"] = "cuda"
        elif damage == "preflight":
            index["preflight"]["pass"] = False
        for filename in ("g2_run_index.json", "grad00_index.json"):
            if damage == "missing_index" and filename == "grad00_index.json":
                continue
            (output / filename).write_text(json.dumps(index))
        return type("Result", (), {"returncode": code})()

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    return module, kwargs, verified, calls, config, ref


@pytest.mark.parametrize("arm,real_type,project,count", [
    ("quick", "Float32", "julia/CFDSDFWaterLily", 7),
    ("quick_nobound", "Float32", "julia/CFDSDFWaterLily", 7),
    ("quick", "Float64", "julia/CFDSDFWaterLily", 7),
    ("quick_nobound", "Float64", "julia/CFDSDFWaterLily", 7),
    ("quick", "Float32", "julia/CFDSDFWaterLily110", 7),
])
def test_cpu_routing_provenance_and_analyzer_identity(monkeypatch, tmp_path, arm, real_type, project, count):
    module, kwargs, verified, calls, config, ref = setup(monkeypatch, tmp_path, arm=arm, real_type=real_type, project=project)
    for name in module.DRYRUN_SWITCHES:
        monkeypatch.setenv(name, "1")
    monkeypatch.setenv("G2_BACKEND", "cuda")
    monkeypatch.setenv("GRAD00_ARM", "cds")
    monkeypatch.setenv("GRAD00_T", "Float32" if real_type == "Float64" else "Float64")
    monkeypatch.setenv("JULIA_NUM_THREADS", "2")
    assert module.run_cpu(**kwargs) == 0
    args, env, timeout, cwd = calls[0]
    assert args[0] == "/synthetic/julia" and args[1] == f"--project={ROOT / project}"
    assert args[2] == str(ROOT / module.B.SCRIPT) and len(args) == 18
    assert args[-4:] == [str((i + 1) * 1e-3) for i in range(4)]
    assert env["G2_BACKEND"] == "cpu" and env["GRAD00_ARM"] == arm and env["GRAD00_T"] == real_type
    assert env["JULIA_NUM_THREADS"] == "10"
    assert all(name not in env for name in module.DRYRUN_SWITCHES)
    assert timeout == 60.0 and Path(cwd) == ROOT
    assert "Pkg.instantiate" not in " ".join(args)
    pins = verified[0][1]
    assert {f"{project}/Project.toml", f"{project}/Manifest.toml", "scripts/run_grad00_cpu.py", config["path"]} <= pins
    assert "julia/CFDSDFWaterLilyT4/Project.toml" not in pins
    output = kwargs["output_dir"]
    identity = json.loads((output / "run_identity.json").read_text())
    assert identity["reference"] == config and identity["verified"] == identity["pins"]
    assert identity["julia_threads"] == 10
    assert identity["source_tree_id"] == "b" * 40 and identity["failure_stage"] is None and identity["spike_exit_code"] == 0
    manifest = json.loads((output / "output_manifest.json").read_text())["files"]
    assert set(manifest) == {p.name for p in output.iterdir() if p.name != "output_manifest.json"}
    assert all(module.B.sha(output / name) == digest for name, digest in manifest.items())
    assert len(json.loads((output / "grad00_index.json").read_text())["runs"]) == count
    monkeypatch.setattr(A, "_git_output", lambda *args: ("b" * 40 + "\n").encode())
    monkeypatch.setattr(A, "committed_sha", lambda commit, name: identity["pins"][name])
    monkeypatch.setattr(A, "committed_reference", lambda commit, name: ref)
    A._source_identity(identity, {"waterlily": "1.10.0" if project.endswith("110") else "1.8.0", "backend": "cpu", "arm": arm}, ref)


@pytest.mark.parametrize("code,terminal,ok", [(3, "BLOCKED", True), (0, "BLOCKED", False), (3, "COMPLETE", False), (2, "ERROR", False)])
def test_exit_and_terminal_status_must_agree(monkeypatch, tmp_path, code, terminal, ok):
    module, kwargs, _, _, _, _ = setup(monkeypatch, tmp_path, code=code, terminal=terminal)
    assert module.run_cpu(**kwargs) == (0 if ok else 1)
    output = kwargs["output_dir"]
    assert (output / "DONE").exists() is ok
    assert (output / "output_manifest.json").is_file()
    assert (output / "ERROR.txt").exists() is not ok
    identity = json.loads((output / "run_identity.json").read_text())
    assert identity["spike_exit_code"] == code
    assert (identity["failure_stage"] is None) is ok
    if not ok:
        assert identity["error_reason"]
    manifest = json.loads((output / "output_manifest.json").read_text())["files"]
    assert set(manifest) == {p.name for p in output.iterdir() if p.name != "output_manifest.json"}
    assert all(module.B.sha(output / name) == digest for name, digest in manifest.items())


@pytest.mark.parametrize("error", [subprocess.TimeoutExpired("synthetic Julia", 60), OSError("synthetic executable missing")])
def test_timeout_and_process_error_fail_closed(monkeypatch, tmp_path, error):
    module, kwargs, _, _, _, _ = setup(monkeypatch, tmp_path, error=error)
    assert module.run_cpu(**kwargs) == 1
    output = kwargs["output_dir"]
    assert (output / "ERROR.txt").is_file() and not (output / "DONE").exists()
    assert (output / "output_manifest.json").is_file()
    assert json.loads((output / "run_identity.json").read_text())["failure_stage"] == "measurement"


@pytest.mark.parametrize("damage", ["missing_index", "inventory", "backend", "preflight"])
def test_missing_or_invalid_terminal_is_not_published(monkeypatch, tmp_path, damage):
    module, kwargs, _, _, _, _ = setup(monkeypatch, tmp_path, damage=damage)
    assert module.run_cpu(**kwargs) == 1
    output = kwargs["output_dir"]
    assert not (output / "DONE").exists() and (output / "output_manifest.json").is_file()
    assert json.loads((output / "run_identity.json").read_text())["failure_stage"] == "terminal_verification"


def test_manifest_change_is_detected_without_modifying_any_real_manifest(monkeypatch, tmp_path):
    module, kwargs, _, _, _, _ = setup(monkeypatch, tmp_path)
    real_run, real_sha = module.subprocess.run, module.B.sha
    executed = []

    def after_run(*args, **kwargs):
        result = real_run(*args, **kwargs)
        executed.append(True)
        return result

    monkeypatch.setattr(module.subprocess, "run", after_run)
    monkeypatch.setattr(module.B, "sha", lambda path: "f" * 64 if executed and str(path) == str(ROOT / kwargs["project"] / "Manifest.toml") else real_sha(path))
    assert module.run_cpu(**kwargs) == 1
    assert "Manifest.toml changed" in (kwargs["output_dir"] / "ERROR.txt").read_text()
    assert not (kwargs["output_dir"] / "DONE").exists()


def test_artifact_publication_error_cannot_leave_done(monkeypatch, tmp_path):
    module, kwargs, _, _, _, _ = setup(monkeypatch, tmp_path)
    real_write = module.write_json

    def fail_manifest(path, value):
        if path.name == "output_manifest.json":
            raise OSError("synthetic manifest write failure")
        real_write(path, value)

    monkeypatch.setattr(module, "write_json", fail_manifest)
    assert module.run_cpu(**kwargs) == 1
    assert not (kwargs["output_dir"] / "DONE").exists() and not (kwargs["output_dir"] / "output_manifest.json").exists()
    assert (kwargs["output_dir"] / "ERROR.txt").is_file()


@pytest.mark.parametrize("timeout", [0, -1, 216000.01, float("inf"), float("nan"), True])
def test_invalid_timeout_is_rejected_before_mutation(monkeypatch, tmp_path, timeout):
    module, kwargs, _, calls, _, _ = setup(monkeypatch, tmp_path)
    kwargs["timeout_s"] = timeout
    with pytest.raises(ValueError, match="timeout"):
        module.run_cpu(**kwargs)
    assert not calls and not kwargs["output_dir"].exists()


def test_existing_output_is_preserved_before_provenance_or_process(monkeypatch, tmp_path):
    module, kwargs, _, calls, _, _ = setup(monkeypatch, tmp_path)
    kwargs["output_dir"].mkdir()
    (kwargs["output_dir"] / "sentinel").write_text("preserve")
    monkeypatch.setattr(module.B, "reference_config", lambda _: pytest.fail("overwrite must be rejected first"))
    with pytest.raises(FileExistsError):
        module.run_cpu(**kwargs)
    assert not calls and (kwargs["output_dir"] / "sentinel").read_text() == "preserve"


def test_uncommitted_source_is_rejected_before_output_or_process(monkeypatch, tmp_path):
    module, kwargs, _, calls, _, _ = setup(monkeypatch, tmp_path)
    def reject(*_):
        raise ValueError("committed source differs")
    monkeypatch.setattr(module.B, "verify_source", reject)
    with pytest.raises(ValueError, match="committed source"):
        module.run_cpu(**kwargs)
    assert not calls and not kwargs["output_dir"].exists()


@pytest.mark.parametrize("change", [{"arm": "cds"}, {"real_type": "Float16"},
                                    {"project": "julia/CFDSDFWaterLily110", "real_type": "Float64"},
                                    {"project": "julia/CFDSDFWaterLily110", "arm": "quick_nobound"}])
def test_unsupported_precision_or_side_arm_is_rejected(monkeypatch, tmp_path, change):
    module, kwargs, _, calls, _, _ = setup(monkeypatch, tmp_path)
    kwargs.update(change)
    with pytest.raises(ValueError):
        module.run_cpu(**kwargs)
    assert not calls and not kwargs["output_dir"].exists()
