"""G2 runner: pins well-formed, fail-closed exit semantics (DONE only on success, non-zero exit on any failure)."""
import importlib.util
import json
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "infra/kaggle/kernel_grad_g2_bridge/runner.py"


@pytest.fixture()
def runner(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("g2_runner", PATH)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    monkeypatch.setattr(module, "OUT", tmp_path / "out")
    monkeypatch.setattr(module.tempfile, "TemporaryDirectory", lambda **kw: _TD(tmp_path))
    return module


class _TD:
    def __init__(self, base): self.base = base / "work"
    def __enter__(self): self.base.mkdir(exist_ok=True); return str(self.base)
    def __exit__(self, *a): return False


def fake_environment(module, monkeypatch, *, spike_code=0, tamper=False):
    source = module.OUT.parent / "src"
    for rel in module.PINS:
        (source / rel).parent.mkdir(parents=True, exist_ok=True)
        (source / rel).write_bytes(b"x")
    monkeypatch.setattr(module, "PINS", {rel: __import__("hashlib").sha256(b"x" + (b"!" if tamper else b"")).hexdigest() for rel in module.PINS})
    monkeypatch.setattr(module.subprocess, "check_output", lambda *a, **k: "0, Tesla T4, GPU-x, 15360 MiB, 580\n")
    monkeypatch.setattr(module, "fetch_source", lambda base: (source, True))
    monkeypatch.setattr(module, "install_julia", lambda base: Path("julia"))
    calls = []
    def fake_run(args, log, env=None, timeout=0, cwd=None):
        calls.append(args)
        Path(log).write_text("log\n")
        return spike_code if "g2" in str(args[-1]) or "measurement" in str(log) else 0
    monkeypatch.setattr(module, "run", fake_run)
    return calls


def test_pins_and_direction_inputs_are_well_formed_and_match_the_input_manifest():
    text = PATH.read_text()
    assert re.search(r'SOURCE_COMMIT = "(PIN_SOURCE_COMMIT|[0-9a-f]{40})"', text)
    manifest = json.loads((ROOT / "docs/evidence/grad03_gpu_dual_spike_2026_10_08/inputs/inputs_manifest.json").read_text())["directions"]
    spec = importlib.util.spec_from_file_location("g2_runner_static", PATH)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    assert [n for n, _ in module.DIRECTION_INPUTS] == list(manifest)
    assert dict(module.DIRECTION_INPUTS) == {n: v["sha256_fortran_raw"] for n, v in manifest.items()}
    meta = json.loads((ROOT / "infra/kaggle/kernel_grad_g2_bridge/kernel-metadata.json").read_text())
    assert meta["id"].split("/")[1] == re.sub(r"[^a-z0-9]+", "-", meta["title"].lower()).strip("-")
    assert meta["dataset_sources"] == [] and meta["enable_gpu"] and meta["machine_shape"] == "NvidiaTeslaT4"


def test_success_writes_done_and_returns(runner, monkeypatch):
    fake_environment(runner, monkeypatch)
    runner.main()
    assert (runner.OUT / "DONE").is_file() and not (runner.OUT / "ERROR.txt").exists()
    assert "output_manifest.json" not in json.loads((runner.OUT / "output_manifest.json").read_text())["files"]


@pytest.mark.parametrize("kind", ["spike_nonzero", "pin_mismatch"])
def test_failure_exits_nonzero_writes_error_and_never_done(runner, monkeypatch, kind):
    fake_environment(runner, monkeypatch, spike_code=2 if kind == "spike_nonzero" else 0, tamper=(kind == "pin_mismatch"))
    with pytest.raises(SystemExit) as exc:
        runner.main()
    assert exc.value.code not in (0, None)
    assert (runner.OUT / "ERROR.txt").is_file() and not (runner.OUT / "DONE").exists()
    assert json.loads((runner.OUT / "run_identity.json").read_text())["failure_stage"] is not None


def test_non_t4_worker_fails_closed(runner, monkeypatch):
    fake_environment(runner, monkeypatch)
    monkeypatch.setattr(runner.subprocess, "check_output", lambda *a, **k: "0, Tesla V100, GPU-x, 16384 MiB, 580\n")
    with pytest.raises(SystemExit):
        runner.main()
    assert not (runner.OUT / "DONE").exists()


def test_script_timeout_is_clamped_to_the_remaining_kernel_budget(runner, monkeypatch):
    seen = []
    calls = fake_environment(runner, monkeypatch)
    original = runner.run
    def spy(args, log, env=None, timeout=0, cwd=None):
        seen.append(timeout); return original(args, log, env, timeout, cwd)
    monkeypatch.setattr(runner, "run", spy)
    monkeypatch.setattr(runner, "KERNEL_TIMEOUT_S", 1000)
    runner.main()
    assert max(seen) <= 1000 - runner.MARGIN_S


def test_exhausted_budget_fails_closed(runner, monkeypatch):
    fake_environment(runner, monkeypatch)
    monkeypatch.setattr(runner, "KERNEL_TIMEOUT_S", 300)
    with pytest.raises(SystemExit):
        runner.main()
    assert not (runner.OUT / "DONE").exists()
