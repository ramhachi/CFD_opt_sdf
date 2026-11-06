"""LOCAL-GPU-01 opt-in identity and rendering, entirely CPU/fake-job checks."""
import ast
import io
import json
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import harness_testlib as T
from cfd_harness import backend_profiles as BP
from cfd_harness import campaign_build as B
from cfd_harness import campaign_verify as V

SC = T.SC
H01 = T.ROOT / "docs/harness/harness01_replay_campaign.json"
LOCAL_NAME = "NVIDIA GeForce RTX 4070 Ti"
LOCAL_SMI = f"0, {LOCAL_NAME}, {T.UUID}, 12282 MiB, 581.42\n"


def test_default_profile_keeps_registered_selector_and_exact_probe_rules():
    from grid01_gpu import select_worker_gpu
    # Preserve even the old selector's UUID spelling boundary; stronger local
    # checks must not silently alter the default T4 profile.
    smi = T.SMI.replace(T.UUID, "GPU-")
    selected = select_worker_gpu(smi)
    assert BP.select_worker_gpu(smi) == selected
    probe = dict(SC.GPU_EXPECTED, visible_gpu_uuids=["GPU-"], default_device_uuid="GPU-")
    assert BP.check_probe("kaggle_t4", selected, probe) == "GPU-"


@pytest.mark.parametrize("kernel_dir", ["kernel_harness01_replay_a_smoke", "kernel_unc01_u01_f24_smoke"])
def test_default_render_reproduces_committed_smoke_bytes_at_its_source(tmp_path, kernel_dir):
    """Historical pins come from their commit, rather than hashes of newer source."""
    saved = T.ROOT / "infra/kaggle" / kernel_dir
    text = (saved / "runner.py").read_text()
    literals = {node.targets[0].id: ast.literal_eval(node.value) for node in ast.parse(text).body
                if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id in {"SOURCE_COMMIT", "PINS", "CAMPAIGN", "KERNEL", "SMOKE"}}
    archive = subprocess.run(["git", "-C", str(T.ROOT), "archive", literals["SOURCE_COMMIT"],
                              *literals["PINS"], B.TEMPLATE_REL], check=True, capture_output=True)
    with tarfile.open(fileobj=io.BytesIO(archive.stdout)) as stream:
        stream.extractall(tmp_path, filter="data")
    if kernel_dir != "kernel_harness01_replay_a_smoke":
        # HARNESS-01 predates JOB-02's run-name addition. UNC-01 uses exactly
        # today's template, so this also guards the current default renderer.
        assert (tmp_path / B.TEMPLATE_REL).read_bytes() == (T.ROOT / B.TEMPLATE_REL).read_bytes()
    baseline = subprocess.run(["git", "-C", str(T.ROOT), "show", f"HEAD:{B.TEMPLATE_REL}"], check=True, capture_output=True)
    assert (T.ROOT / B.TEMPLATE_REL).read_bytes() == baseline.stdout
    campaign = tmp_path / literals["CAMPAIGN"]
    assert BP.profile_name(SC.jload(campaign)) == BP.DEFAULT
    assert B.render(campaign, literals["SOURCE_COMMIT"], literals["KERNEL"], literals["SMOKE"], tmp_path).encode() == text.encode()
    assert (json.dumps(B.metadata(SC.jload(campaign), literals["KERNEL"], literals["SMOKE"]), sort_keys=True, indent=2) + "\n").encode() == (saved / SC.METADATA_FILE).read_bytes()


@pytest.mark.parametrize("name", ["Tesla T4", "NVIDIA GeForce RTX 4070 Ti SUPER", "NVIDIA A100"])
def test_local_inventory_rejects_another_gpu(name):
    with pytest.raises(ValueError, match="4070 Ti"):
        BP.select_worker_gpu(LOCAL_SMI.replace(LOCAL_NAME, name), "local_rtx4070ti")


def test_local_inventory_and_cuda_probe_bind_name_uuid_and_singleton():
    selected = BP.select_worker_gpu(LOCAL_SMI, "local_rtx4070ti")
    assert selected == {"index": 0, "name": LOCAL_NAME, "uuid": T.UUID}
    probe = dict(SC.GPU_EXPECTED, visible_gpu_names=[LOCAL_NAME], visible_gpu_uuids=[T.UUID], default_device_uuid=T.UUID)
    assert BP.check_probe("local_rtx4070ti", selected, probe) == T.UUID
    for key, value in (("logical_device_count", 2), ("visible_gpu_names", ["Tesla T4"]), ("default_device_uuid", "GPU-other"), ("cuda_visible_devices", "1")):
        with pytest.raises(ValueError, match="singleton/default"):
            BP.check_probe("local_rtx4070ti", selected, dict(probe, **{key: value}))
    unavailable = BP.select_worker_gpu(LOCAL_SMI.replace(T.UUID, "[N/A]"), "local_rtx4070ti")
    assert unavailable["uuid"] == ""
    assert BP.check_probe("local_rtx4070ti", unavailable, probe) == T.UUID
    with pytest.raises(ValueError):
        BP.select_worker_gpu(LOCAL_SMI.replace(T.UUID, "bad-uuid"), "local_rtx4070ti")
    with pytest.raises(ValueError, match="exactly one"):
        BP.select_worker_gpu(LOCAL_SMI + LOCAL_SMI.replace("0,", "1,", 1), "local_rtx4070ti")


def test_create_local_campaign_is_new_and_removes_t4_reference(tmp_path):
    target = tmp_path / "local.json"
    before = H01.read_bytes()
    BP.create_local_campaign(H01, target, repo=tmp_path)
    local = SC.jload(target)
    assert H01.read_bytes() == before
    assert local["backend_profile"] == "local_rtx4070ti" and local["legacy_replay"] is False
    assert "first_state_csv_sha256" not in local["kernels"]["a"]
    SC.validate_campaign(local)
    with pytest.raises(ValueError, match="local backend"):
        B.refuse_legacy(local)
    with pytest.raises(FileExistsError):
        BP.create_local_campaign(H01, target, repo=tmp_path)
    with pytest.raises(ValueError, match="backend profile"):
        SC.validate_campaign(dict(local, backend_profile="unknown"))


def test_checkpoint_campaign_explicitly_pins_gen01_module_and_include_closure(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    for rel in ("julia", "scripts", "src", "docs/evidence"):
        destination = root / rel
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.symlink_to(T.ROOT / rel)
    target = root / "docs/harness/local_checkpoint.json"
    before = SC.sha256_path(T.ROOT / "julia/CFDSDFWaterLily/src")
    BP.create_local_campaign(T.ROOT / "docs/harness/screen01_f_campaign.json", target,
                             job="scripts/waterlily_local_gpu_job.jl", repo=root)
    campaign = SC.jload(target)
    for key, kernel in campaign["kernels"].items():
        assert kernel["job"] == "scripts/waterlily_local_gpu_job.jl"
        assert BP.CHECKPOINT_REL in kernel["pins"]
        pins = B.pins(campaign, str(target.relative_to(root)), key, root)
        assert pins[BP.CHECKPOINT_REL] == SC.sha256_path(T.ROOT / BP.CHECKPOINT_REL)
        B.check_include_closure(root, pins)
        with pytest.raises(ValueError, match="Checkpoint.jl.*not pinned"):
            B.check_include_closure(root, set(pins) - {BP.CHECKPOINT_REL})
    assert SC.sha256_path(T.ROOT / "julia/CFDSDFWaterLily/src") == before
    assert not (T.ROOT / "julia/CFDSDFWaterLily/src/Checkpoint.jl").exists()


def local_fake(tmp_path, monkeypatch, *, smi=LOCAL_SMI, probe_uuid=T.UUID):
    """Run the actual locally rendered Python using real saved force files only."""
    campaign = SC.jload(H01)
    campaign["backend_profile"] = "local_rtx4070ti"
    campaign["kernels"]["a"].pop("first_state_csv_sha256")
    campaign_file = tmp_path / "local_campaign.json"
    campaign_file.write_text(json.dumps(campaign, sort_keys=True, indent=2) + "\n")
    # The existing fake source loader expects a repository-contained campaign.
    # A scratch repo with symlinked immutable inputs keeps that helper unchanged.
    root = tmp_path / "repo"
    root.mkdir()
    for rel in ("julia", "scripts", "src", "docs/evidence"):
        destination = root / rel
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.symlink_to(T.ROOT / rel)
    (root / "docs/harness").mkdir()
    local = root / "docs/harness/local_campaign.json"
    local.write_bytes(campaign_file.read_bytes())
    text = B.render(local, T.DUMMY, "a", True, root)
    runner = tmp_path / "runner.py"
    runner.write_text(text)
    ns = {"__name__": "local_test_runner", "__file__": str(runner)}
    exec(compile(text, str(runner), "exec"), ns)
    out = tmp_path / "result"
    probe = dict(SC.GPU_EXPECTED, visible_gpu_names=[LOCAL_NAME], visible_gpu_uuids=[probe_uuid], default_device_uuid=probe_uuid)
    saved = T.EV / "kernel_output/grid02_f16"

    def fake_run(args, log_path, env=None, timeout=3600):
        Path(log_path).write_text("fake subprocess\n")
        if "-e" in args:
            if "Pkg.instantiate()" not in args[-1]:
                Path(env["GRID01_GPU_PROBE_OUT"]).write_text(json.dumps(probe))
            return 0
        outdir = Path(args[-1])
        for name in ("flow_16.forces.csv", "flow_16.summary.json", "W4_JOB_DONE"):
            shutil.copy(saved / "states/opt01b__parent" / name, outdir / name)
        summary_path = outdir / "flow_16.summary.json"
        summary = SC.jload(summary_path)
        summary.update(gpu_name=LOCAL_NAME, gpu_uuid=probe_uuid)
        summary_path.write_text(json.dumps(summary, sort_keys=True, indent=2) + "\n")
        return 0

    julia = tmp_path / "julia"
    julia.write_text("#!/bin/sh\nprintf 'julia version 1.12.6\\n'\n")
    julia.chmod(0o755)
    monkeypatch.setenv("LOCAL_GPU_JULIA", str(julia))
    monkeypatch.setenv("LOCAL_GPU_JULIA_SHA256", SC.sha256_path(julia))
    ns.update(OUT=out, nvidia_smi=lambda: smi, fetch_source=lambda _: root, run=fake_run)
    return ns, out, local, root


@pytest.mark.parametrize("inventory_uuid", [T.UUID, "[N/A]"])
def test_local_rendered_smoke_runs_and_existing_verifier_accepts_it(tmp_path, monkeypatch, inventory_uuid):
    ns, out, local, root = local_fake(tmp_path, monkeypatch, smi=LOCAL_SMI.replace(T.UUID, inventory_uuid))
    ns["main"]()
    identity = SC.jload(out / SC.IDENTITY_NAME)
    assert identity["backend_profile"] == "local_rtx4070ti" and identity["used_gpu_count"] == 1
    assert BP.MODULE_REL in identity["pins"]
    table = V.verify(local, [out], smoke=True, source_commit=T.DUMMY, repo=root)
    assert table["integrity"]["pass"] is True and table["backend_profile"] == "local_rtx4070ti"
    assert table["harness_tool_sha256"][BP.MODULE_REL] == SC.sha256_path(T.ROOT / BP.MODULE_REL)
    identity["used_gpu_count"] = 2
    (out / SC.IDENTITY_NAME).write_text(json.dumps(identity))
    (out / SC.MANIFEST_NAME).write_text(json.dumps(SC.build_manifest(out)))
    with pytest.raises(ValueError, match="used_gpu_count"):
        V.verify(local, [out], smoke=True, source_commit=T.DUMMY, repo=root)


def test_render_local_requires_committed_remote_source_and_refuses_overwrite(tmp_path, monkeypatch):
    _, _, local, root = local_fake(tmp_path, monkeypatch)
    calls = []
    monkeypatch.setattr(B, "verify_source", lambda repo, commit, paths: calls.append(("source", commit, paths)))
    monkeypatch.setattr(B, "require_on_remote", lambda repo, commit, url: calls.append(("remote", commit, url)))
    target = tmp_path / "kernel"
    assert BP.render_local(local, T.DUMMY, "a", target, repo=root) == target
    record = SC.jload(target / "local_kernel.json")
    assert record["runner_sha256"] == SC.sha256_path(target / SC.RUNNER_FILE)
    assert record["campaign_sha256"] == SC.sha256_path(local) and record["used_gpu_count"] == 1
    assert [row[0] for row in calls] == ["source", "remote"]
    assert {B.TEMPLATE_REL, "src/cfd_harness/campaign_build.py", BP.MODULE_REL} <= calls[0][2]
    with pytest.raises(ValueError, match="overwrite"):
        BP.render_local(local, T.DUMMY, "a", target, repo=root)
    assert len(calls) == 2
    # An uncommitted source failure must happen before any output is created.
    def reject_source(*args):
        raise ValueError("committed source differs")
    monkeypatch.setattr(B, "verify_source", reject_source)
    refused = tmp_path / "refused"
    with pytest.raises(ValueError, match="committed source"):
        BP.render_local(local, T.DUMMY, "a", refused, repo=root)
    assert not refused.exists()


def test_local_render_hooks_refuse_a_changed_template():
    text = (T.ROOT / B.TEMPLATE_REL).read_text()
    with pytest.raises(ValueError, match="render hook"):
        BP.adapt_runner(text.replace("selected_gpu = select_worker_gpu(gpu)", "selected_gpu = {}"))


@pytest.mark.parametrize("mutation", ["model", "uuid", "julia_sha"])
def test_local_runner_rejects_bad_identity_before_any_job(tmp_path, monkeypatch, mutation):
    ns, out, _, _ = local_fake(tmp_path, monkeypatch,
                                smi=LOCAL_SMI.replace(LOCAL_NAME, "Tesla T4") if mutation == "model" else LOCAL_SMI,
                                probe_uuid="GPU-other" if mutation == "uuid" else T.UUID)
    if mutation == "julia_sha":
        monkeypatch.setenv("LOCAL_GPU_JULIA_SHA256", "0" * 64)
    with pytest.raises(SystemExit) as exc:
        ns["main"]()
    assert exc.value.code == 1 and (out / SC.ERROR_NAME).is_file() and not (out / SC.DONE_NAME).exists()
    assert not (out / "states").exists()
