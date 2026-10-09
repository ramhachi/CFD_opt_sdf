"""STEP-01 Kaggle runner: pins, kernel identity, and the fail-closed behaviour with a fake solver job."""
import hashlib
import importlib.util
import json
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import build_step01_kernels as B  # noqa: E402
import step01_states as S  # noqa: E402

BASELINE_CSV = b"step,t_u_l,fx_solver\n8,0.09,544.8\n"


def load_runner(tmp_path, kernel="c"):
    path = tmp_path / f"runner_{kernel}.py"
    path.write_text(B.render(kernel, "0" * 40))
    spec = importlib.util.spec_from_file_location(f"step01_runner_{kernel}", path)
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return mod


def patch_environment(mod, monkeypatch, tmp_path, job_behaviour):
    real_tmp = tempfile.TemporaryDirectory
    monkeypatch.setattr(mod.tempfile, "TemporaryDirectory", lambda prefix, dir: real_tmp(prefix=prefix, dir=tmp_path))
    monkeypatch.setattr(mod, "OUT", tmp_path / "out")
    monkeypatch.setattr(mod.subprocess, "check_output", lambda *a, **k: "0, Tesla T4, GPU-abc, 15360 MiB, 535.1\n")
    monkeypatch.setattr(mod, "fetch_source", lambda base: ROOT)
    monkeypatch.setattr(mod, "install_julia", lambda base: Path("julia"))
    monkeypatch.setattr(mod, "FD08_BASELINE_CSV_SHA256", hashlib.sha256(BASELINE_CSV).hexdigest())
    calls = []

    def fake_run(args, log_path, env=None, timeout=3600):
        Path(log_path).write_text("fake")
        if "Pkg.instantiate()" in " ".join(map(str, args)):
            return 0
        phi, outdir = Path(args[-2]), Path(args[-1])
        calls.append((phi.name, env["W4_PHI_FORTRAN_SHA256"], hashlib.sha256(phi.read_bytes()).hexdigest()))
        return job_behaviour(len(calls), outdir)
    monkeypatch.setattr(mod, "run", fake_run)
    return calls


def good_job(n, outdir, baseline=BASELINE_CSV):
    (outdir / "flow_24.forces.csv").write_bytes(baseline if n == 1 else b"step,t_u_l\n" + str(n).encode() + b"\n")
    (outdir / "flow_24.summary.json").write_text("{}"); (outdir / "W4_JOB_DONE").write_text("x")
    return 0


def test_rendering_fills_every_pin_and_the_three_kernels_differ_only_in_the_kernel_constants(tmp_path):
    texts = {k: B.render(k, "a" * 40) for k in S.KERNELS}
    assert all("PIN_" not in t for t in texts.values())
    norm = {k: t.replace(f'KERNEL = "{k}"', 'KERNEL = "?"').replace(f"KERNEL_TIMEOUT_S = {B.TIMEOUT_S[k]}", "KERNEL_TIMEOUT_S = T") for k, t in texts.items()}
    assert len(set(norm.values())) == 1
    meta = {k: B.metadata(k) for k in S.KERNELS}
    assert [m["id"] for m in meta.values()] == ["ramhachi888/cfd-opt-sdf-step01-a", "ramhachi888/cfd-opt-sdf-step01-b", "ramhachi888/cfd-opt-sdf-step01-c"]
    assert all(m["id"].split("/")[1] == B.slugify(m["title"]) and m["machine_shape"] == "NvidiaTeslaT4" and m["dataset_sources"] == [] for m in meta.values())
    assert B.TIMEOUT_S == {"a": 7200, "b": 7200, "c": 3600}


def test_a_complete_kernel_writes_done_and_runs_every_state_with_the_registered_phi(tmp_path, monkeypatch):
    mod = load_runner(tmp_path)
    calls = patch_environment(mod, monkeypatch, tmp_path, good_job)
    mod.main()
    out = tmp_path / "out"
    index = json.loads((out / "step01_index.json").read_text())
    assert (out / "DONE").is_file() and not (out / "ERROR.txt").exists() and index["status"] == "COMPLETE"
    assert [e["name"] for e in index["states"]] == [p["name"] for p in S.state_plan("c")] and all(e["complete"] for e in index["states"])
    assert index["states"][0]["matches_fd08_baseline_v17"] is True
    assert all(c[1] == c[2] for c in calls)                                    # the phi handed to the job has the SHA the job is told to expect
    assert json.loads((out / "output_manifest.json").read_text())["files"]


def test_a_baseline_that_differs_from_fd08_stops_before_any_perturbed_state(tmp_path, monkeypatch):
    mod = load_runner(tmp_path)
    calls = patch_environment(mod, monkeypatch, tmp_path, lambda n, o: good_job(n, o, baseline=BASELINE_CSV + b"x"))
    with pytest.raises(SystemExit):
        mod.main()
    out = tmp_path / "out"
    assert not (out / "DONE").exists() and "differs from FD-08" in (out / "ERROR.txt").read_text() and len(calls) == 1
    assert json.loads((out / "step01_index.json").read_text())["status"] == "ERROR"


def test_a_failing_job_or_missing_output_never_writes_done(tmp_path, monkeypatch):
    mod = load_runner(tmp_path)
    patch_environment(mod, monkeypatch, tmp_path, lambda n, o: good_job(n, o) if n < 3 else 2)
    with pytest.raises(SystemExit):
        mod.main()
    assert not (tmp_path / "out" / "DONE").exists() and (tmp_path / "out" / "ERROR.txt").is_file()
    mod2 = load_runner(tmp_path / "x" if (tmp_path / "x").mkdir() is None else tmp_path)
    patch_environment(mod2, monkeypatch, tmp_path / "x", lambda n, o: (good_job(n, o), (o / "W4_JOB_DONE").unlink())[0] if n == 2 else good_job(n, o))
    with pytest.raises(SystemExit):
        mod2.main()
    assert not (tmp_path / "x" / "out" / "DONE").exists()


def test_a_wrong_gpu_or_a_tampered_inventory_is_refused(tmp_path, monkeypatch):
    mod = load_runner(tmp_path)
    patch_environment(mod, monkeypatch, tmp_path, good_job)
    monkeypatch.setattr(mod.subprocess, "check_output", lambda *a, **k: "0, Tesla P100, GPU-abc, 16384 MiB, 535.1\n")
    with pytest.raises(SystemExit):
        mod.main()
    assert "T4 worker was not present" in (tmp_path / "out" / "ERROR.txt").read_text() and not (tmp_path / "out" / "DONE").exists()
    # a state whose generated phi differs from the registered SHA is refused before the job runs
    inv = json.loads((ROOT / "docs/evidence/step01_finite_step_secant_2026_10_09/inventory.json").read_text())
    row = next(r for r in inv["states"] if r["kernel"] == "c" and r["kind"] == "combo")
    row = {**row, "phi_fortran_order_sha256": "0" * 64}
    S_mod = sys.modules["step01_states"]
    with pytest.raises(RuntimeError, match="differs from the registered inventory"):
        mod.generate_phi(S_mod, ROOT, inv, row)


def test_the_generated_phi_of_every_registered_state_matches_the_inventory(tmp_path):
    mod = load_runner(tmp_path)
    inv = json.loads((ROOT / "docs/evidence/step01_finite_step_secant_2026_10_09/inventory.json").read_text())
    for row in inv["states"]:
        raw = mod.generate_phi(S, ROOT, inv, row)
        assert hashlib.sha256(raw).hexdigest() == row["phi_fortran_order_sha256"]


def test_the_job_environment_of_the_baseline_equals_the_fd08_runner_state_env(tmp_path):
    spec = importlib.util.spec_from_file_location("fd08_r6_runner", ROOT / "infra/kaggle/kernel_fd08_v2_r6/runner.py")
    fd08 = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(fd08)
    except Exception as err:  # noqa: BLE001
        pytest.skip(f"the FD-08 runner cannot be imported here: {err}")
    formal = json.loads((ROOT / "docs/evidence/fd08_v2_formal_2026_10_07_amend3/formal_criteria.json").read_text())
    base_row = next(r for r in formal["state_inventory"] if r["name"] == "baseline_v17")
    row = {"state_sha256": base_row["state_sha256"], "npz_sha256": base_row["npz_sha256"], "phi_c_order_sha256": base_row["phi_c_order_sha256"],
           "phi_fortran_order_sha256": base_row["phi_fortran_order_sha256"], "margin_m": base_row["margin_m"]}
    theirs = fd08.state_env({}, row, formal, "GPU-x")
    mod = load_runner(tmp_path)
    inv = json.loads((ROOT / "docs/evidence/step01_finite_step_secant_2026_10_09/inventory.json").read_text())
    mine_row = next(r for r in inv["states"] if r["kind"] == "baseline")
    ours = mod.state_env({}, inv, mine_row, "GPU-x")
    assert {k: v for k, v in ours.items()} == {k: v for k, v in theirs.items()}


def test_the_baseline_csv_pin_is_one_constant_and_the_rendered_runner_carries_it(tmp_path):
    assert S.FD08_BASELINE_CSV_SHA256 == B.FD08_BASELINE_CSV_SHA == "39370386fd27a7ecd1160a295298798326078a4c5342be07bfb257267a1fbcb3"
    mod = load_runner(tmp_path)
    assert mod.FD08_BASELINE_CSV_SHA256 == S.FD08_BASELINE_CSV_SHA256


def test_a_pin_that_does_not_match_the_checked_out_source_stops_the_kernel_before_julia(tmp_path, monkeypatch):
    mod = load_runner(tmp_path)
    patch_environment(mod, monkeypatch, tmp_path, good_job)
    pins = dict(mod.PINS); pins[mod.JOB] = "0" * 64
    monkeypatch.setattr(mod, "PINS", pins)
    with pytest.raises(SystemExit):
        mod.main()
    assert "pinned file SHA-256 mismatch" in (tmp_path / "out" / "ERROR.txt").read_text() and not (tmp_path / "out" / "DONE").exists()


def test_a_tampered_direction_pin_is_refused(tmp_path, monkeypatch):
    mod = load_runner(tmp_path)
    patch_environment(mod, monkeypatch, tmp_path, good_job)
    files = dict(mod.DIRECTION_FILES); k = sorted(files)[0]; files[k] = "0" * 64
    monkeypatch.setattr(mod, "DIRECTION_FILES", files)
    with pytest.raises(SystemExit):
        mod.main()
    assert k in (tmp_path / "out" / "ERROR.txt").read_text()


def test_run_identity_records_the_runner_and_the_python_environment(tmp_path, monkeypatch):
    mod = load_runner(tmp_path)
    patch_environment(mod, monkeypatch, tmp_path, good_job)
    mod.main()
    ident = json.loads((tmp_path / "out" / "run_identity.json").read_text())
    assert len(ident["runner_sha256"]) == 64 and ident["python_version"] and ident["platform"]
