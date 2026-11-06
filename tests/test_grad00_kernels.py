"""Local renderer checks; no Kaggle API, Julia process, or GPU is used."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))


def builder():
    spec = importlib.util.spec_from_file_location("grad00_builder_test", ROOT / "scripts/build_grad00_kernels.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def render_namespace(monkeypatch, arm="quick", configured=True):
    module = builder()
    monkeypatch.setattr(module, "tree_id", lambda _: "b" * 40)
    input_paths = [module.PHI_RAW, *(f"{module.INPUT_DIR}/{name}.dir_f4_fortran.raw" for name in module.DIRECTIONS)]
    pinned = {path: module.sha(ROOT / path) for path in input_paths}
    monkeypatch.setattr(module, "pins", lambda _: pinned)
    reference = {
        "path": "reference.json", "sha256": "a" * 64, "definition": "synthetic renderer fixture",
        "sources": {},
        "directions": {name: {"epsilon_m": (i + 1) * 1e-3, "spread_n_per_m": {"fx": 0.0, "fz": 0.0}}
                       for i, name in enumerate(module.DIRECTIONS)},
    } if configured else None
    source = module.render("a" * 40, arm, reference)
    namespace = {"__name__": "test_rendered_grad00", "__file__": "runner.py"}
    exec(compile(source, "runner.py", "exec"), namespace)
    return module, namespace


@pytest.mark.parametrize("arm", ["quick", "quick_nobound", "cds", "vanLeer"])
def test_render_routes_each_arm_and_preserves_frozen_template(monkeypatch, arm):
    template = (ROOT / "scripts/grad_ta1_runner_template.py").read_bytes()
    module, ns = render_namespace(monkeypatch, arm)
    assert ns["ARM"] == arm
    assert ns["SOURCE_COMMIT"] == "a" * 40
    assert ns["SOURCE_TREE_ID"] == "b" * 40
    assert ns["SCRIPT"] == "scripts/waterlily_grad00_lambda_2026_11.jl"
    assert ns["PROJECT"] == "julia/CFDSDFWaterLilyT4"
    assert ns["KERNEL_ID"] == f"ramhachi888/cfd-opt-sdf-grad00-{arm.lower().replace('_', '-')}"
    assert ns["OUT"] == Path(f"/kaggle/working/grad00_{arm}")
    assert ns["KERNEL_TIMEOUT_S"] == module.TIMEOUT_S == 10800
    assert ns["ACCEPTED_EXIT_CODES"] == (0, 3)
    assert (ROOT / "scripts/grad_ta1_runner_template.py").read_bytes() == template


@pytest.mark.parametrize("commit", ["HEAD", "f" * 39, "F" * 40, "0" * 41])
def test_render_requires_explicit_lowercase_commit(monkeypatch, commit):
    module = builder()
    with pytest.raises(ValueError, match="full lowercase SHA"):
        module.render(commit, "quick")


def test_unconfigured_runner_stops_before_gpu_inventory(monkeypatch, tmp_path):
    _, ns = render_namespace(monkeypatch, configured=False)
    ns["OUT"] = tmp_path / "unconfigured"
    ns["__file__"] = __file__  # an existing synthetic runner identity input
    monkeypatch.setattr(ns["subprocess"], "check_output", lambda *_a, **_kw: pytest.fail("GPU inventory must not be reached"))
    with pytest.raises(SystemExit) as exc:
        ns["main"]()
    assert exc.value.code == 1
    assert not (ns["OUT"] / "DONE").exists()
    assert "FD-08" in (ns["OUT"] / "ERROR.txt").read_text()
    assert json.loads((ns["OUT"] / "run_identity.json").read_text())["failure_stage"] == "reference_configuration"


@pytest.mark.parametrize("code,done,terminal", [(0, True, "COMPLETE"), (3, True, "BLOCKED"), (1, False, None),
                                               (0, False, None), (0, False, "BLOCKED"), (3, False, "COMPLETE")])
def test_runner_exit_propagation_and_measurement_env(monkeypatch, tmp_path, code, done, terminal):
    module, ns = render_namespace(monkeypatch, "quick_nobound")
    ns["OUT"] = tmp_path / f"run_{code}"
    ns["PINS"] = {f"{ns['PROJECT']}/{name}": "a" * 64 for name in ("Project.toml", "Manifest.toml")}
    ns["sha256"] = lambda _: "a" * 64
    ns["fetch_source"] = lambda _: (ROOT, True)
    ns["install_julia"] = lambda _: Path("/synthetic/julia")
    monkeypatch.setattr(ns["subprocess"], "check_output", lambda *_a, **_kw: "0, Tesla T4, synthetic, 15360, synthetic\n")
    # The original template uses this temporary directory only on Kaggle.
    real_temporary_directory = ns["tempfile"].TemporaryDirectory
    monkeypatch.setattr(ns["tempfile"], "TemporaryDirectory", lambda **_kw: real_temporary_directory(dir=tmp_path))
    for key in ns["DRYRUN_SWITCHES"]:
        monkeypatch.setenv(key, "1")
    monkeypatch.setenv("GRAD00_T", "Float64")
    monkeypatch.setenv("GRAD00_ARM", "cds")
    calls = []

    def fake_run(args, log_path, env, timeout):
        calls.append((args, env, timeout))
        if Path(log_path).name == "instantiate.log":
            return 0
        if terminal is not None:
            statuses = {"plain": "COMPLETE", **{name + suffix: "COMPLETE" for name in module.DIRECTIONS
                                                  for suffix in ("", "__plus", "__minus")}}
            if terminal == "BLOCKED":
                statuses[module.DIRECTIONS[0]] = "BLOCKED"
            index = {"status": terminal, "arm": "quick_nobound", "real_type": "Float32", "backend": "cuda",
                     "preflight": {"pass": True}, "runs": {name: 0.0 for name in statuses}, "run_status": statuses}
            for filename in ("g2_run_index.json", "grad00_index.json"):
                (ns["OUT"] / filename).write_text(json.dumps(index))
        return code

    ns["run"] = fake_run
    if done:
        ns["main"]()
    else:
        with pytest.raises(SystemExit) as exc:
            ns["main"]()
        assert exc.value.code == 1
    assert (ns["OUT"] / "DONE").exists() is done
    assert (ns["OUT"] / "ERROR.txt").exists() is not done
    args, env, _ = calls[-1]
    assert env["GRAD00_ARM"] == "quick_nobound"
    assert env["GRAD00_T"] == "Float32"
    assert env["G2_BACKEND"] == "cuda"
    assert all(key not in env for key in ns["DRYRUN_SWITCHES"])
    assert args[-4:] == [str((i + 1) * 1e-3) for i in range(4)]
    assert len(args) == 18  # julia/project/job + the 15 explicitly required job arguments
    identity = json.loads((ns["OUT"] / "run_identity.json").read_text())
    assert identity["arm"] == "quick_nobound"
    assert identity["reference"]["definition"] == "synthetic renderer fixture"
    assert identity["spike_exit_code"] == code
    assert set(identity["verified"]) == set(ns["PINS"])


def test_reference_files_are_included_in_sparse_clone(monkeypatch, tmp_path):
    _, ns = render_namespace(monkeypatch)
    ns["REFERENCE"]["sources"] = {"docs/epsilon_source.json": "a" * 64}

    def fake_git(args, **kwargs):
        if "init" in args:
            (tmp_path / "source/.git/info").mkdir(parents=True)
        return type("Result", (), {"returncode": 0})()

    monkeypatch.setattr(ns["subprocess"], "run", fake_git)
    monkeypatch.setattr(ns["subprocess"], "check_output", lambda args, **_kw: ("b" if "HEAD^{tree}" in args else "a") * 40 + "\n")
    ns["fetch_source"](tmp_path)
    patterns = (tmp_path / "source/.git/info/sparse-checkout").read_text().splitlines()
    assert "/reference.json" in patterns
    assert "/docs/epsilon_source.json" in patterns


def test_builder_refuses_overwrite_before_any_partial_write(monkeypatch, tmp_path):
    module = builder()
    occupied = tmp_path / "kernel_grad00_cds"
    occupied.mkdir()
    (occupied / "sentinel").write_text("preserve")
    monkeypatch.setattr(module, "verify_source", lambda *_: pytest.fail("overwrite must be checked first"))
    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        module.build("a" * 40, output_root=tmp_path)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["kernel_grad00_cds"]
    assert (occupied / "sentinel").read_text() == "preserve"


def test_builder_pins_source_and_writes_timeout(monkeypatch, tmp_path):
    module = builder()
    verified = []
    monkeypatch.setattr(module, "verify_source", lambda commit, paths: verified.append((commit, paths)))
    monkeypatch.setattr(module, "render", lambda commit, arm, reference: f"ARM = {arm!r}\n")
    module.build("a" * 40, output_root=tmp_path)
    assert len(verified) == 1
    assert module.SCRIPT in verified[0][1]
    assert "scripts/quick_nobound.jl" in verified[0][1]
    assert "scripts/grad_ta1_runner_template.py" in verified[0][1]
    assert {"scripts/analyze_grad00.py", "scripts/grad_g2_window.py", "scripts/verify_grad_g2_terminal.py"} <= verified[0][1]
    for arm in module.ARMS:
        directory = tmp_path / f"kernel_grad00_{arm}"
        assert sorted(p.name for p in directory.iterdir()) == ["kernel-metadata.json", "runner.py", "timeout"]
        assert (directory / "timeout").read_text() == "10800\n"
        metadata = json.loads((directory / "kernel-metadata.json").read_text())
        assert metadata["enable_gpu"] is True
        assert metadata["is_private"] is True
        assert metadata["machine_shape"] == "NvidiaTeslaT4"


def test_reference_requires_repo_local_provenance(monkeypatch, tmp_path):
    module = builder()
    with pytest.raises(ValueError, match="inside the repository"):
        module.reference_config(tmp_path / "outside.json")


def test_reference_config_uses_shared_provenance_loader(monkeypatch, tmp_path):
    module = builder()
    monkeypatch.setattr(module, "ROOT", tmp_path)
    source = tmp_path / "docs/synthetic_source.json"
    source.parent.mkdir()
    source.write_text('{"synthetic": true}\n')
    reference = {"schema_version": 1, "kind": "grad00_fd08_reference", "definition": "synthetic renderer schema fixture",
                 "sources": {"docs/synthetic_source.json": module.sha(source)},
                 "directions": {name: {"epsilon_m": 1e-3, "spread_n_per_m": {"fx": 0.0, "fz": 0.0}}
                                for name in module.DIRECTIONS}}
    path = tmp_path / "reference.json"
    path.write_text(json.dumps(reference))
    configured = module.reference_config(path)
    assert configured["path"] == "reference.json"
    assert configured["sha256"] == module.sha(path)
    assert configured["directions"] == reference["directions"]
    assert {"reference.json", "docs/synthetic_source.json"} <= module.pin_paths(configured)
