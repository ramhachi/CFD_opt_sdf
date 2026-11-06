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


@pytest.mark.parametrize("arm", ["quick", "quick_nobound", "cds", "vanLeer", "vanLeer_safe"])
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
@pytest.mark.parametrize("arm", ["quick_nobound", "vanLeer_safe"])
def test_runner_exit_propagation_and_measurement_env(monkeypatch, tmp_path, code, done, terminal, arm):
    module, ns = render_namespace(monkeypatch, arm)
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
            index = {"status": terminal, "arm": arm, "real_type": "Float32", "backend": "cuda",
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
    assert env["GRAD00_ARM"] == arm
    assert env["GRAD00_T"] == "Float32"
    assert env["G2_BACKEND"] == "cuda"
    assert all(key not in env for key in ns["DRYRUN_SWITCHES"])
    assert args[-4:] == [str((i + 1) * 1e-3) for i in range(4)]
    assert len(args) == 18  # julia/project/job + the 15 explicitly required job arguments
    identity = json.loads((ns["OUT"] / "run_identity.json").read_text())
    assert identity["arm"] == arm
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
    assert "scripts/vanleer_safe.jl" in verified[0][1]
    assert "scripts/grad00_reference_from_fd08.py" in verified[0][1]
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


def write_reference(module, tmp_path):
    source = tmp_path / "docs/synthetic_source.json"
    source.parent.mkdir(exist_ok=True)
    source.write_text('{"synthetic": true}\n')
    reference = {"schema_version": 1, "kind": "grad00_fd08_reference", "definition": "synthetic renderer schema fixture",
                 "sources": {"docs/synthetic_source.json": module.sha(source)},
                 "directions": {name: {"epsilon_m": 1e-3, "spread_n_per_m": {"fx": 0.0, "fz": 0.0}}
                                for name in module.DIRECTIONS}}
    path = tmp_path / "reference.json"
    path.write_text(json.dumps(reference))
    return path, reference


def test_reference_config_uses_shared_provenance_loader(monkeypatch, tmp_path):
    module = builder()
    monkeypatch.setattr(module, "ROOT", tmp_path)
    path, reference = write_reference(module, tmp_path)
    configured = module.reference_config(path)
    assert configured["path"] == "reference.json"
    assert configured["sha256"] == module.sha(path)
    assert configured["directions"] == reference["directions"]
    assert {"reference.json", "docs/synthetic_source.json"} <= module.pin_paths(configured)


@pytest.mark.parametrize("initially_configured", [True, False])
def test_configured_default_render_overwrites_all_five_workers_and_preserves_extras(monkeypatch, tmp_path, initially_configured):
    module = builder()
    monkeypatch.setattr(module, "ROOT", tmp_path)
    path, _ = write_reference(module, tmp_path)
    reference = module.reference_config(path)
    verified = []
    monkeypatch.setattr(module, "verify_source", lambda commit, paths: verified.append((commit, paths)))
    monkeypatch.setattr(module, "render", lambda commit, arm, reference: f"ARM = {arm!r}\nREFERENCE = {reference!r}\n")
    module.build("a" * 40, reference=reference if initially_configured else None)
    assert module.ARMS == ("quick", "quick_nobound", "cds", "vanLeer", "vanLeer_safe")
    output_root = tmp_path / "infra/kaggle"
    for arm in module.ARMS:
        directory = output_root / f"kernel_grad00_{arm}"
        (directory / "notes").mkdir()
        (directory / "notes/keep.txt").write_text("preserve")
        for name in ("runner.py", "kernel-metadata.json", "timeout"):
            (directory / name).write_text("old generated bytes\n")
    for _ in range(2):
        module.build("a" * 40, reference=reference)
        for arm in module.ARMS:
            directory = output_root / f"kernel_grad00_{arm}"
            assert (directory / "runner.py").read_text() == module.render("a" * 40, arm, reference)
            assert json.loads((directory / "kernel-metadata.json").read_text()) == module.metadata(arm)
            assert (directory / "timeout").read_text() == "10800\n"
            assert (directory / "notes/keep.txt").read_text() == "preserve"
    assert len(verified) == 3
    assert {reference["path"], *reference["sources"], "scripts/vanleer_safe.jl"} <= verified[-1][1]


@pytest.mark.parametrize("failure", ["reference_source", "reference_config", "source", "render", "metadata"])
def test_configured_build_validates_and_renders_every_arm_before_overwrite(monkeypatch, tmp_path, failure):
    module = builder()
    monkeypatch.setattr(module, "ROOT", tmp_path)
    path, _ = write_reference(module, tmp_path)
    reference = module.reference_config(path)
    output_root = tmp_path / "infra/kaggle"
    for arm in ("quick", "quick_nobound", "cds", "vanLeer", "vanLeer_safe"):
        directory = output_root / f"kernel_grad00_{arm}"
        directory.mkdir(parents=True)
        for name in ("runner.py", "kernel-metadata.json", "timeout", "keep.txt"):
            (directory / name).write_text(f"original {arm} {name}\n")
    before = {p: p.read_bytes() for p in output_root.rglob("*") if p.is_file()}

    def check_unchanged():
        assert {p: p.read_bytes() for p in output_root.rglob("*") if p.is_file()} == before

    def verify(commit, paths):
        check_unchanged()
        assert commit == "a" * 40
        assert {reference["path"], *reference["sources"], "scripts/vanleer_safe.jl"} <= paths
        if failure == "source":
            raise ValueError("synthetic source verification failure")

    rendered = []

    def render(commit, arm, config):
        check_unchanged()
        assert config == reference
        rendered.append(arm)
        if failure == "render" and arm == "vanLeer_safe":
            raise ValueError("synthetic render failure")
        return f"ARM = {arm!r}\n"

    original_metadata = module.metadata

    def metadata(arm):
        check_unchanged()
        if failure == "metadata" and arm == "vanLeer_safe":
            raise ValueError("synthetic metadata failure")
        return original_metadata(arm)

    monkeypatch.setattr(module, "verify_source", verify)
    monkeypatch.setattr(module, "render", render)
    monkeypatch.setattr(module, "metadata", metadata)
    if failure == "reference_source":
        source = tmp_path / "docs/synthetic_source.json"
        source.write_bytes(source.read_bytes() + b" ")
    elif failure == "reference_config":
        reference["definition"] = "stale preloaded reference configuration"
    with pytest.raises(ValueError):
        module.build("a" * 40, reference=reference)
    check_unchanged()
    if failure in ("render", "metadata"):
        assert rendered == list(module.ARMS)


def test_reference_free_default_render_refuses_configured_worker_without_writes(monkeypatch, tmp_path):
    module = builder()
    monkeypatch.setattr(module, "ROOT", tmp_path)
    directory = tmp_path / "infra/kaggle/kernel_grad00_vanLeer_safe"
    directory.mkdir(parents=True)
    for name in ("runner.py", "kernel-metadata.json", "timeout", "keep.txt"):
        (directory / name).write_text(f"configured {name}\n")
    before = {p: p.read_bytes() for p in directory.iterdir()}
    monkeypatch.setattr(module, "verify_source", lambda *_: pytest.fail("refuse before source checks"))
    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        module.build("a" * 40)
    assert {p: p.read_bytes() for p in directory.iterdir()} == before
    assert sorted(p.name for p in directory.parent.iterdir()) == [directory.name]


@pytest.mark.parametrize("damaged", ["reference.json", "scripts/vanleer_safe.jl"])
def test_build_uses_committed_byte_verifier_before_render(monkeypatch, tmp_path, damaged):
    module = builder()
    monkeypatch.setattr(module, "ROOT", tmp_path)
    # Exercise the reused verifier against synthetic committed blobs, without Git mutations.
    monkeypatch.setitem(module.verify_source.__globals__, "ROOT", tmp_path)
    committed = {"reference.json": b"committed reference\n", "scripts/vanleer_safe.jl": b"committed D-prime\n"}
    for name, content in committed.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content + (b" " if name == damaged else b""))

    def git_show(args, **kwargs):
        assert args[:4] == ["git", "-C", str(tmp_path), "show"]
        name = args[4].removeprefix("a" * 40 + ":")
        return module.subprocess.CompletedProcess(args, 0, stdout=committed[name])

    monkeypatch.setattr(module.subprocess, "run", git_show)
    monkeypatch.setattr(module, "pin_paths", lambda _: set(committed))
    monkeypatch.setattr(module, "render", lambda *_: pytest.fail("source must verify before rendering"))
    with pytest.raises(ValueError, match=f"committed source differs: {damaged}"):
        module.build("a" * 40)
    assert not (tmp_path / "infra").exists()
