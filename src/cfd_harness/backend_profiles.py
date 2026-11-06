"""Opt-in LOCAL-GPU-01 identity; the registered Kaggle T4 renderer stays unchanged.

Only local campaigns pin and import this module in the worker. It does no GPU
work itself: inventories and CUDA driver probes are supplied by the runner.
"""
from __future__ import annotations

import copy
import csv
import io
import json
import os
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
MODULE_REL = "src/cfd_harness/backend_profiles.py"
CHECKPOINT_REL = "julia/CFDSDFWaterLily/gen01/Checkpoint.jl"
DEFAULT, LOCAL = "kaggle_t4", "local_rtx4070ti"
LOCAL_GPU_NAME = "NVIDIA GeForce RTX 4070 Ti"


def profile_name(campaign):
    name = campaign.get("backend_profile", DEFAULT)
    if name not in (DEFAULT, LOCAL):
        raise ValueError(f"unknown backend profile: {name!r}")
    return name


def select_worker_gpu(text, profile=DEFAULT):
    if profile == DEFAULT:
        from grid01_gpu import select_worker_gpu as select_t4
        return select_t4(text)
    if profile != LOCAL:
        raise ValueError(f"unknown backend profile: {profile!r}")
    rows = [row for row in csv.reader(io.StringIO(text)) if row and any(value.strip() for value in row)]
    if len(rows) != 1 or len(rows[0]) != 5:
        raise ValueError("local RTX 4070 Ti inventory must contain exactly one five-column device row")
    index, name, uuid, memory, driver = (value.strip() for value in rows[0])
    if index != "0" or name != LOCAL_GPU_NAME or not memory or not driver:
        raise ValueError("local backend requires physical index 0 to be NVIDIA GeForce RTX 4070 Ti with memory and driver identity")
    # WSL2 NVML can omit UUID; CUDA driver identity is still checked below.
    if uuid in ("", "[N/A]", "N/A", "[Not Supported]"):
        uuid = ""
    elif not uuid.startswith("GPU-") or len(uuid) <= 4:
        raise ValueError("local nvidia-smi inventory has a malformed GPU UUID")
    return {"index": 0, "name": name, "uuid": uuid}


def check_probe(profile, selected, observed):
    if profile not in (DEFAULT, LOCAL):
        raise ValueError(f"unknown backend profile: {profile!r}")
    if not isinstance(observed, dict):
        raise ValueError("observed CUDA singleton/default identity must be an object")
    uuid = selected["uuid"] or observed.get("default_device_uuid")
    name = "Tesla T4" if profile == DEFAULT else LOCAL_GPU_NAME
    expected = {"logical_device_count": 1, "visible_gpu_names": [name], "cuda_device_order": "PCI_BUS_ID", "cuda_visible_devices": "0",
                "visible_gpu_uuids": [uuid], "default_device_uuid": uuid}
    invalid_local_uuid = profile == LOCAL and (not isinstance(uuid, str) or not uuid.startswith("GPU-") or len(uuid) <= 4)
    if invalid_local_uuid or json.dumps(observed, sort_keys=True) != json.dumps(expected, sort_keys=True):
        raise ValueError("observed CUDA singleton/default identity differs from the backend profile or selected physical GPU")
    return uuid


def local_julia():
    """Use the lock-checked executable, rather than downloading a second Julia."""
    import hashlib

    path = Path(os.environ["LOCAL_GPU_JULIA"]).resolve(strict=True)
    expected = os.environ["LOCAL_GPU_JULIA_SHA256"]
    with path.open("rb") as handle:
        actual = hashlib.file_digest(handle, "sha256").hexdigest()
    if actual != expected:
        raise ValueError("locked Julia executable SHA-256 mismatch")
    version = subprocess.check_output([str(path), "--startup-file=no", "--version"], text=True, timeout=30).strip()
    if version != "julia version 1.12.6":
        raise ValueError(f"locked Julia must be 1.12.6: {version!r}")
    return path


def adapt_runner(text):
    """Apply explicit local-profile hooks; reject a changed upstream template.

    The default render never calls this function. Keeping the historical
    template byte-exact also preserves committed T4 runners and their freezes.
    """
    replacements = [
        ("selected_gpu = select_worker_gpu(gpu)", "selected_gpu = SC.select_profile_gpu(campaign, gpu)"),
        ('identity.update(selected_gpu=selected_gpu, cuda_device_order="PCI_BUS_ID", cuda_visible_devices="0")',
         'identity.update(selected_gpu=selected_gpu, cuda_device_order="PCI_BUS_ID", cuda_visible_devices="0", backend_profile="local_rtx4070ti", used_gpu_count=1)'),
        ("julia = install_julia(base)", "julia = SC.local_backend().local_julia()"),
        ('expected_device = dict(SC.GPU_EXPECTED, visible_gpu_uuids=[gpu_uuid], default_device_uuid=gpu_uuid)\n'
         '            if observed != expected_device:\n'
         '                raise RuntimeError("observed CUDA singleton/default UUID differs from selected physical GPU")',
         "gpu_uuid = SC.local_backend().check_probe(campaign['backend_profile'], selected_gpu, observed)"),
    ]
    for old, new in replacements:
        if text.count(old) != 1:
            raise ValueError(f"local backend render hook differs from the reviewed template: {old.splitlines()[0]}")
        text = text.replace(old, new)
    compile(text, "local_runner.py", "exec")
    return text


def create_local_campaign(campaign_path, target, *, job=None, repo=REPO):
    """Write a derived campaign; the caller commits/pushes it before rendering.

    A checkpoint job override applies only to the registered flow_32 job it
    copies. Other grids keep their registered jobs and force semantics.
    """
    from cfd_harness import campaign_schema as SC

    campaign = copy.deepcopy(SC.jload(campaign_path))
    SC.validate_campaign(campaign)
    SC.req(not campaign["legacy_replay"], "a local campaign must derive from a non-legacy registered harness campaign")
    SC.req(profile_name(campaign) == DEFAULT, "refusing to derive another local campaign from a local campaign")
    target = Path(target).resolve()
    target.relative_to(Path(repo).resolve())
    campaign["backend_profile"] = LOCAL
    campaign["campaign_id"] += "_local_gpu"
    campaign["out_prefix"] += "local_gpu_"
    changed = 0
    for kernel in campaign["kernels"].values():
        kernel["kernel_id"] += "-local-rtx4070ti"
        kernel.pop("first_state_csv_sha256", None)  # T4 bytes are descriptive only on a new backend.
        if job is not None and kernel["job"] == "scripts/waterlily_lowdim02_flow32_job.jl":
            SC.req(kernel["case"]["case_id"] == "flow_32", "checkpoint copy requires the registered flow_32 case")
            kernel["job"] = str(SC.safe_rel(job))
            # src/ is a registered directory pin: GEN-01 modules live outside
            # it and are explicit file pins of each job that includes them.
            kernel["pins"] = sorted(set(kernel.get("pins", [])) | {CHECKPOINT_REL})
            changed += 1
    SC.req(job is None or changed > 0, "checkpoint job override did not match a registered flow_32 job")
    SC.validate_campaign(campaign)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("x") as handle:
        handle.write(json.dumps(campaign, sort_keys=True, indent=2, allow_nan=False) + "\n")
    return target


def render_local(campaign_path, source_commit, k, out, smoke=True, *, repo=REPO):
    """Render a committed, remotely reachable local campaign; never run or push."""
    from cfd_harness import campaign_build as B
    from cfd_harness import campaign_schema as SC

    campaign, rel, digest = B.load(campaign_path, repo)
    SC.req(profile_name(campaign) == LOCAL and not campaign["legacy_replay"], "render_local requires a local_rtx4070ti campaign")
    SC.req(k in campaign["kernels"], f"unknown kernel {k}")
    out = Path(out)
    SC.req(not out.exists(), f"refusing to overwrite local kernel: {out}")
    B.verify_source(repo, source_commit, B.bound_paths(campaign, rel, repo) | {"src/cfd_harness/campaign_build.py"})
    B.require_on_remote(repo, source_commit, campaign["repo_url"])
    text = B.render(campaign_path, source_commit, k, smoke, repo)
    metadata = B.metadata(campaign, k, smoke)
    metadata.update(machine_shape=LOCAL, backend_profile=LOCAL, used_gpu_count=1)
    out.mkdir(parents=True)
    (out / SC.RUNNER_FILE).write_text(text)
    (out / SC.METADATA_FILE).write_text(json.dumps(metadata, sort_keys=True, indent=2) + "\n")
    record = {"backend_profile": LOCAL, "used_gpu_count": 1, "campaign_path": rel, "campaign_sha256": digest, "source_commit": source_commit, "kernel": k, "smoke": smoke,
              "runner_sha256": SC.sha256_bytes(text.encode())}
    (out / "local_kernel.json").write_text(json.dumps(record, sort_keys=True, indent=2, allow_nan=False) + "\n")
    return out
