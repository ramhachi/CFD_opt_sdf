"""GRAD-TA1 worker, builder and freeze: rendered runner is well formed and fail-closed (exit 0 / BLOCKED=3 accepted, anything else ERROR), the pins cover every imported file,
the identity-free proof rejects collisions and stale proofs."""
import copy
import csv
import datetime
import hashlib
import importlib.util
import io
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import build_grad_ta1_kernel as K  # noqa: E402
import freeze_grad_ta1 as F  # noqa: E402

HEAD = subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True).strip()


@pytest.fixture()
def runner(tmp_path, monkeypatch):
    path = tmp_path / "runner.py"
    path.write_text(K.render(HEAD))
    spec = importlib.util.spec_from_file_location("ta1_runner", path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    monkeypatch.setattr(module, "OUT", tmp_path / "out")

    class TD:
        def __init__(self, **kw): self.base = tmp_path / "work"
        def __enter__(self): self.base.mkdir(exist_ok=True); return str(self.base)
        def __exit__(self, *a): return False

    monkeypatch.setattr(module.tempfile, "TemporaryDirectory", TD)
    return module


def fake_environment(module, monkeypatch, *, code=0, tamper=False, tree=None):
    source = module.OUT.parent / "src"
    for rel in module.PINS:
        (source / rel).parent.mkdir(parents=True, exist_ok=True)
        (source / rel).write_bytes(b"x")
    monkeypatch.setattr(module, "PINS", {rel: hashlib.sha256(b"x" + (b"!" if tamper else b"")).hexdigest() for rel in module.PINS})
    monkeypatch.setattr(module.subprocess, "check_output", lambda *a, **k: "0, Tesla T4, GPU-x, 15360 MiB, 580\n")
    monkeypatch.setattr(module, "fetch_source", lambda base: (source, True))
    monkeypatch.setattr(module, "install_julia", lambda base: Path("julia"))
    envs = []

    def fake_run(args, log, env=None, timeout=0, cwd=None):
        Path(log).write_text("log\n"); envs.append((str(log), dict(env or {}), timeout))
        return code if "measurement" in str(log) else 0

    monkeypatch.setattr(module, "run", fake_run)
    return envs


def test_rendered_runner_pins_every_imported_file_and_matches_the_template_inputs(runner):
    assert set(runner.PINS) == set(K.PIN_PATHS) and all(re.fullmatch(r"[0-9a-f]{64}", v) for v in runner.PINS.values())
    assert runner.SOURCE_COMMIT == HEAD and runner.SOURCE_TREE_ID == K.tree_id(HEAD) and runner.KERNEL_ID == "ramhachi888/cfd-opt-sdf-grad-ta1"
    assert "scripts/quick_tie.jl" in runner.PINS and runner.SCRIPT in runner.PINS and "julia/CFDSDFWaterLily/src" in runner.PINS
    assert runner.KERNEL_TIMEOUT_S == F.KERNEL_TIMEOUT_S == 10800 and runner.ACCEPTED_EXIT_CODES == (0, 3)
    assert "PIN_" not in Path(runner.__file__).read_text()


def test_metadata_is_a_private_t4_script_without_datasets():
    meta = K.metadata()
    assert meta["machine_shape"] == "NvidiaTeslaT4" and meta["enable_gpu"] and meta["is_private"] and meta["dataset_sources"] == [] and meta["kernel_sources"] == []
    assert meta["title"] == meta["id"].split("/")[1] == re.sub(r"[^a-z0-9]+", "-", meta["title"].lower()).strip("-")


def test_complete_and_blocked_exit_codes_write_done(runner, monkeypatch):
    fake_environment(runner, monkeypatch, code=3)
    runner.main()
    assert (runner.OUT / "DONE").is_file() and not (runner.OUT / "ERROR.txt").exists()
    assert json.loads((runner.OUT / "run_identity.json").read_text())["spike_exit_code"] == 3


@pytest.mark.parametrize("kind", ["exit2", "pin_mismatch"])
def test_other_failures_exit_nonzero_write_error_and_never_done(runner, monkeypatch, kind):
    fake_environment(runner, monkeypatch, code=2 if kind == "exit2" else 0, tamper=(kind == "pin_mismatch"))
    with pytest.raises(SystemExit) as exc:
        runner.main()
    assert exc.value.code not in (0, None)
    assert (runner.OUT / "ERROR.txt").is_file() and not (runner.OUT / "DONE").exists()


def test_dry_run_switches_never_reach_the_registered_run_and_the_backend_is_cuda(runner, monkeypatch):
    for key in ("G2_DRYRUN_T_END", "TA1_PREFLIGHT_ONLY", "TA1_BLOCK_LIMIT"):
        monkeypatch.setenv(key, "1")
    envs = fake_environment(runner, monkeypatch)
    runner.main()
    measurement = [e for log, e, _ in envs if "measurement" in log][0]
    assert not any(k in measurement for k in ("G2_DRYRUN_T_END", "TA1_PREFLIGHT_ONLY", "TA1_BLOCK_LIMIT")) and measurement["G2_BACKEND"] == "cuda"
    assert measurement["JULIA_NUM_THREADS"] == "1" and measurement["CUDA_VISIBLE_DEVICES"] == "0"


def test_non_t4_and_exhausted_budget_fail_closed(runner, monkeypatch):
    fake_environment(runner, monkeypatch)
    monkeypatch.setattr(runner.subprocess, "check_output", lambda *a, **k: "0, Tesla V100, GPU-x, 16384 MiB, 580\n")
    with pytest.raises(SystemExit):
        runner.main()
    assert not (runner.OUT / "DONE").exists()


def test_script_timeout_is_clamped_to_the_remaining_kernel_budget(runner, monkeypatch):
    envs = fake_environment(runner, monkeypatch)
    monkeypatch.setattr(runner, "KERNEL_TIMEOUT_S", 1000)
    runner.main()
    assert max(t for _, _, t in envs) <= 1000 - runner.MARGIN_S


def test_a_template_with_a_wrong_direction_hash_is_not_rendered(tmp_path, monkeypatch):
    bad = tmp_path / "t.py"
    bad.write_text(K.TEMPLATE.read_text().replace("d0af58bd", "00000000", 1))
    monkeypatch.setattr(K, "TEMPLATE", bad)
    with pytest.raises(ValueError, match="direction hash"):
        K.render(HEAD)


# ---- identity-free proof -----------------------------------------------------------------------------------------------------------------------------------
def identity_record(extra_rows=(), age_s=60):
    rows = [{"ref": "ramhachi888/other-kernel", "title": "other kernel", "author": "x", "lastRunTime": "2026-10-13", "totalVotes": "0"}, *extra_rows]
    header = "ref,title,author,lastRunTime,totalVotes"

    def page(kind):
        out = io.StringIO(); w = csv.DictWriter(out, fieldnames=header.split(","), lineterminator="\n"); w.writeheader(); w.writerows(rows)
        return {"command": ["kaggle", kind, "list", "--mine", "--page-size", "100", "--page", "1", "--csv"], "exit_code": 0, "stdout": out.getvalue(), "stderr": "", "rows": rows}

    listings = {k: {"pages": [page(k)], "rows": rows, "complete": True} for k in ("kernels", "datasets")}
    controls = {"kernels": {"command": ["kaggle", "kernels", "status", rows[0]["ref"]], "exit_code": 0, "stdout": "ok", "stderr": ""},
                "datasets": {"command": ["kaggle", "datasets", "files", rows[0]["ref"], "--csv"], "exit_code": 0, "stdout": "ok", "stderr": ""}}
    stamp = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=age_s)).isoformat()
    return {"all_free": True, "owner": "ramhachi888", "kernel_ids": [K.KERNEL_ID], "captured_utc": stamp, "listings": listings, "positive_controls": controls}


def write_identity(tmp_path, monkeypatch, record):
    path = tmp_path / "identity_free_check.json"
    path.write_bytes(F.canonical_json(record))
    path.with_suffix(".json.sha256").write_text(K.sha(path) + "\n")
    monkeypatch.setattr(F, "IDENTITY", path)


def test_identity_proof_accepts_a_fresh_free_record(tmp_path, monkeypatch):
    record = identity_record(); write_identity(tmp_path, monkeypatch, record)
    F.require_identity(record)


@pytest.mark.parametrize("case", ["collision_slug", "collision_title", "stale", "wrong_kernel", "incomplete", "foreign_owner"])
def test_identity_proof_rejects_collision_staleness_and_malformation(tmp_path, monkeypatch, case):
    if case == "collision_slug":
        record = identity_record([{"ref": "ramhachi888/cfd-opt-sdf-grad-ta1", "title": "x", "author": "x", "lastRunTime": "t", "totalVotes": "0"}])
    elif case == "collision_title":
        record = identity_record([{"ref": "ramhachi888/zzz", "title": "CFD Opt SDF Grad TA1", "author": "x", "lastRunTime": "t", "totalVotes": "0"}])
    elif case == "stale":
        record = identity_record(age_s=90000)
    else:
        record = identity_record()
        if case == "wrong_kernel":
            record["kernel_ids"] = ["ramhachi888/other"]
        elif case == "incomplete":
            record["listings"]["kernels"]["complete"] = False
        else:
            record["owner"] = "someone"
    write_identity(tmp_path, monkeypatch, record)
    with pytest.raises(ValueError):
        F.require_identity(copy.deepcopy(record))


def test_freeze_closure_covers_the_analyzer_and_its_reused_verifiers_and_pins_the_kernel_inputs():
    closure = F.project_closure()
    assert {"scripts/analyze_grad_ta1.py", "scripts/analyze_grad_g2_bridge.py", "scripts/verify_grad_g2_terminal.py", "scripts/grad_g2_window.py",
            "scripts/build_grad_ta1_kernel.py", "scripts/freeze_grad_ta1.py", "scripts/build_lowdim04a_kernel.py"} <= closure
    assert F.A.ANALYZER_FREEZE_KEY == "scripts/analyze_grad_ta1.py"
    pins = F.package_pins()
    assert pins["WaterLily"]["version"] == "1.8.0" and pins["WaterLily"]["git_tree_sha1"] == "8e1d973f428df4bae450e1a45f19d0dba3ac6857"
    assert pins["ForwardDiff"]["version"] == F.RUNTIME_PINS["forwarddiff"] and pins["CUDA"]["version"] == F.RUNTIME_PINS["cuda_jl"]
