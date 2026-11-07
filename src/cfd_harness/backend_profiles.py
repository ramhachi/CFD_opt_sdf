"""Opt-in LOCAL-GPU-01 identity; the registered Kaggle T4 renderer stays unchanged.

Only local campaigns pin and import this module in the worker. It does no GPU
work itself: inventories and CUDA driver probes are supplied by the runner.
"""
from __future__ import annotations

import copy
import csv
import io
import importlib.util
import json
import os
import subprocess
import tomllib
import types
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
MODULE_REL = "src/cfd_harness/backend_profiles.py"
CHECKPOINT_REL = "julia/CFDSDFWaterLily/gen01/Checkpoint.jl"
DEFAULT, LOCAL = "kaggle_t4", "local_rtx4070ti"
LOCAL_GPU_NAME = "NVIDIA GeForce RTX 4070 Ti"
RUNTIME_ENV_PREFIXES = ("JULIA_", "CUDA_", "NVIDIA_", "WSL")
RESERVED_LOCAL_ENV_PREFIXES = RUNTIME_ENV_PREFIXES + ("LOCAL_GPU_",)


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
    if profile == DEFAULT:
        SC = _schema()
        SC.equal(observed, dict(SC.GPU_EXPECTED, visible_gpu_uuids=[selected["uuid"]], default_device_uuid=selected["uuid"]),
                 "observed CUDA singleton/default identity")
        return selected["uuid"]
    if not isinstance(observed, dict):
        raise ValueError("observed CUDA singleton/default identity must be an object")
    uuid = selected["uuid"] or observed.get("default_device_uuid")
    name = LOCAL_GPU_NAME
    expected = {"logical_device_count": 1, "visible_gpu_names": [name], "cuda_device_order": "PCI_BUS_ID", "cuda_visible_devices": "0",
                "visible_gpu_uuids": [uuid], "default_device_uuid": uuid}
    invalid_local_uuid = profile == LOCAL and (not isinstance(uuid, str) or not uuid.startswith("GPU-") or len(uuid) <= 4)
    if invalid_local_uuid or json.dumps(observed, sort_keys=True) != json.dumps(expected, sort_keys=True):
        raise ValueError("observed CUDA singleton/default identity differs from the backend profile or selected physical GPU")
    return uuid


def _schema():
    """Load the pinned schema by path, including in the sparse worker checkout."""
    spec = importlib.util.spec_from_file_location("_local_gpu_schema", REPO / "src/cfd_harness/campaign_schema.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def filtered_environment(env):
    return {key: env[key] for key in sorted(env) if key.startswith(RUNTIME_ENV_PREFIXES)}


def manifest_packages_identity(julia, project, depot, env=None):
    """Hash only Manifest-resolved package trees in a dedicated single depot.

    Pkg reports resolved sources without loading CUDA or running a solver.
    Absolute source paths are recorded, while the digest is path-independent.
    """
    SC = _schema()
    project, depot = Path(project).resolve(strict=True), Path(depot).expanduser().resolve(strict=True)
    SC.req(depot != (Path.home() / ".julia").resolve(), "a dedicated JULIA_DEPOT_PATH is required")
    manifest = tomllib.loads((project / "Manifest.toml").read_text())
    expected = {(entry["uuid"], name): entry["git-tree-sha1"] for name, entries in manifest["deps"].items()
                for entry in entries if "git-tree-sha1" in entry}
    code = ('using Pkg; for (uuid, info) in Pkg.dependencies(); '
            'info.tree_hash === nothing && continue; '
            'println(join((info.name,string(uuid),string(info.tree_hash),info.source), Char(9))); end')
    run_env = dict(os.environ if env is None else env, JULIA_DEPOT_PATH=str(depot))
    output = subprocess.check_output([str(julia), "--startup-file=no", f"--project={project}", "-e", code],
                                     env=run_env, text=True, timeout=120)
    packages, seen = [], set()
    for line in output.splitlines():
        fields = line.split("\t")
        SC.req(len(fields) == 4, "malformed Pkg.dependencies package identity")
        name, uuid, tree, source = fields
        key = (uuid, name)
        SC.req(key in expected and expected[key] == tree and key not in seen, "Pkg.dependencies differs from the pinned Manifest")
        path = Path(source).resolve(strict=True)
        SC.req(path.is_relative_to(depot / "packages") and path.is_dir(), "Manifest package source is outside the dedicated depot/packages")
        packages.append({"name": name, "uuid": uuid, "git_tree_sha1": tree, "source": str(path), "sha256": SC.sha256_path(path)})
        seen.add(key)
    SC.req(seen == set(expected), "Manifest-resolved package trees are missing from the dedicated depot")
    packages.sort(key=lambda row: (row["name"], row["uuid"]))
    digest = SC.sha256_bytes("".join(f"{r['name']}  {r['uuid']}  {r['git_tree_sha1']}  {r['sha256']}\n" for r in packages).encode())
    return {"path": str(depot), "manifest_packages_sha256": digest, "packages": packages}


def local_julia():
    """Use the lock-checked executable, installation tree and package depot."""
    SC = _schema()
    path = Path(os.environ["LOCAL_GPU_JULIA"]).resolve(strict=True)
    SC.req(SC.sha256_path(path) == os.environ["LOCAL_GPU_JULIA_SHA256"], "locked Julia executable SHA-256 mismatch")
    SC.req(SC.sha256_path(path.parent.parent) == os.environ["LOCAL_GPU_JULIA_ROOT_SHA256"], "locked Julia installation root SHA-256 mismatch")
    version = subprocess.check_output([str(path), "--startup-file=no", "--version"], text=True, timeout=30).strip()
    SC.req(version == "julia version 1.12.6", f"locked Julia must be 1.12.6: {version!r}")
    depot = os.environ["JULIA_DEPOT_PATH"]
    SC.req(depot and os.pathsep not in depot and Path(depot).is_absolute(), "JULIA_DEPOT_PATH must be one absolute dedicated depot")
    packages = manifest_packages_identity(path, REPO / "julia/CFDSDFWaterLilyT4", depot)
    SC.req(packages["manifest_packages_sha256"] == os.environ["LOCAL_GPU_DEPOT_PACKAGES_SHA256"], "locked Julia Manifest-resolved package tree SHA-256 mismatch")
    return path


def validate_local_campaign(campaign):
    SC = _schema()
    SC.req(profile_name(campaign) == LOCAL and not campaign["legacy_replay"], "a local backend requires a non-legacy local_rtx4070ti campaign")
    SC.validate_campaign({key: value for key, value in campaign.items() if key != "backend_profile"})
    SC.req(MODULE_REL in campaign["pins"], "local campaign must declare backend_profiles.py in top-level pins")
    channels = [("job_env_common", campaign["job_env_common"]), ("job_env_keys", campaign["job_env_keys"]),
                ("scrub_env", campaign["scrub_env"])]
    channels += [(f"kernels/{key}/runs/{index}/env", run["env"])
                 for key, kernel in campaign["kernels"].items() for index, run in enumerate(kernel["runs"])]
    for channel, keys in channels:
        for key in keys:
            SC.req(not key.startswith(RESERVED_LOCAL_ENV_PREFIXES),
                   f"local campaign cannot override or scrub locked runtime/control variable {key} in {channel}")


def adapt_runner(text):
    """Apply checked opt-in hooks; the registered template stays byte-exact."""
    replacements = [
        ("SC = load_schema(source)",
         'SC = load_schema(source)\n'
         '            bp_spec = importlib.util.spec_from_file_location("local_gpu_backend", source / "src/cfd_harness/backend_profiles.py")\n'
         '            BP = importlib.util.module_from_spec(bp_spec)\n'
         '            bp_spec.loader.exec_module(BP)'),
        ("SC.validate_campaign(campaign)",
         'BP.validate_local_campaign(campaign)\n'
         '            SC.validate_campaign({key: value for key, value in campaign.items() if key != "backend_profile"})'),
        ("selected_gpu = select_worker_gpu(gpu)", 'selected_gpu = BP.select_worker_gpu(gpu, BP.LOCAL)'),
        ('identity.update(selected_gpu=selected_gpu, cuda_device_order="PCI_BUS_ID", cuda_visible_devices="0")',
         'identity.update(selected_gpu=selected_gpu, cuda_device_order="PCI_BUS_ID", cuda_visible_devices="0", backend_profile=BP.LOCAL, filtered_environment=BP.filtered_environment(os.environ))'),
        ("julia = install_julia(base)", "julia = BP.local_julia()"),
        ('expected_device = dict(SC.GPU_EXPECTED, visible_gpu_uuids=[gpu_uuid], default_device_uuid=gpu_uuid)\n'
         '            if observed != expected_device:\n'
         '                raise RuntimeError("observed CUDA singleton/default UUID differs from selected physical GPU")',
         'gpu_uuid = BP.check_probe(BP.LOCAL, selected_gpu, observed)\n'
         '            identity.update(used_gpu_count=observed["logical_device_count"], used_gpu_count_evidence="gpu_device_probe.json:logical_device_count", cuda_uuid=gpu_uuid)'),
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
    campaign["pins"] = sorted(set(campaign["pins"]) | {MODULE_REL})
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
    validate_local_campaign(campaign)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("x") as handle:
        handle.write(json.dumps(campaign, sort_keys=True, indent=2, allow_nan=False) + "\n")
    return target


def render_local(campaign_path, source_commit, k, out, smoke=True, *, repo=REPO):
    """Render a committed, remotely reachable local campaign; never run or push."""
    from cfd_harness import campaign_build as B
    from cfd_harness import campaign_schema as SC

    campaign, rel, digest = load_local_campaign(campaign_path, repo)
    SC.req(profile_name(campaign) == LOCAL and not campaign["legacy_replay"], "render_local requires a local_rtx4070ti campaign")
    SC.req(k in campaign["kernels"], f"unknown kernel {k}")
    out = Path(out)
    SC.req(not out.exists(), f"refusing to overwrite local kernel: {out}")
    B.verify_source(repo, source_commit, B.bound_paths(campaign, rel, repo) | {"src/cfd_harness/campaign_build.py"})
    B.require_on_remote(repo, source_commit, campaign["repo_url"])
    text = render_runner(campaign_path, source_commit, k, smoke, repo)
    metadata = B.metadata(campaign, k, smoke)
    metadata.update(machine_shape=LOCAL, backend_profile=LOCAL, used_gpu_count=1)
    out.mkdir(parents=True)
    (out / SC.RUNNER_FILE).write_text(text)
    (out / SC.METADATA_FILE).write_text(json.dumps(metadata, sort_keys=True, indent=2) + "\n")
    record = {"backend_profile": LOCAL, "used_gpu_count": 1, "campaign_path": rel, "campaign_sha256": digest, "source_commit": source_commit, "kernel": k, "smoke": smoke,
              "runner_sha256": SC.sha256_bytes(text.encode())}
    (out / "local_kernel.json").write_text(json.dumps(record, sort_keys=True, indent=2, allow_nan=False) + "\n")
    return out


def load_local_campaign(campaign_path, repo=REPO):
    SC = _schema()
    path = Path(campaign_path).resolve()
    campaign = SC.jload(path)
    validate_local_campaign(campaign)
    return campaign, str(path.relative_to(Path(repo).resolve())), SC.sha256_path(path)


def render_runner(campaign_path, source_commit, k, smoke=False, repo=REPO):
    """Build local runner text using the unchanged registered pin helpers."""
    from cfd_harness import campaign_build as B
    from cfd_harness import campaign_schema as SC

    c, rel, _ = load_local_campaign(campaign_path, repo)
    SC.req(SC.COMMIT.fullmatch(source_commit or "") is not None, "source commit must be a full lowercase SHA")
    text = (Path(repo) / B.TEMPLATE_REL).read_text()
    SC.req(text.count(SC.PIN_BEGIN) == 1 and text.count(SC.PIN_END) == 1 and text.count("\nPIN_BLOCK\n") == 1, "runner template pin markers differ")
    text = text.replace("PIN_BLOCK", B.pin_block(c, rel, k, source_commit, smoke, B.pins(c, rel, k, repo)))
    return adapt_runner(text)


def _bind(function, **bindings):
    """Private globals for an unchanged harness function; never patch its module."""
    return types.FunctionType(function.__code__, dict(function.__globals__, **bindings), function.__name__, function.__defaults__, function.__closure__)


def verify_local(campaign_path, kernel_dirs, freeze_path=None, smoke=False, repo=REPO, source_commit=None):
    """Reuse every harness integrity check with explicit local GPU expectations.

    Per-call function bindings isolate these three adaptations (selector, CUDA
    probe, summary GPU name) from registered T4 verification, even in one process.
    """
    from cfd_harness import campaign_build as B
    from cfd_harness import campaign_schema as SC
    from cfd_harness import campaign_verify as V

    c, rel, digest = load_local_campaign(campaign_path, repo)
    uuids = set()

    def check_kernel(out, *args, **kwargs):
        out = Path(out)
        identity = SC.jload(out / SC.IDENTITY_NAME)
        selected = select_worker_gpu((out / SC.SMI_NAME).read_text(), LOCAL)
        probe = SC.jload(out / SC.PROBE_NAME)
        uuid = check_probe(LOCAL, selected, probe)
        SC.req(identity.get("backend_profile") == LOCAL, "run identity backend profile differs")
        SC.req(type(identity.get("used_gpu_count")) is int and identity["used_gpu_count"] == probe["logical_device_count"] == 1, "local used_gpu_count differs from the independent probe")
        SC.req(identity.get("used_gpu_count_evidence") == "gpu_device_probe.json:logical_device_count", "local singleton evidence source differs")
        SC.req(identity.get("cuda_uuid") == uuid, "local CUDA UUID differs from independent probe")
        SC.req(isinstance(identity.get("filtered_environment"), dict), "local filtered environment snapshot missing")

        def local_equal(actual, expected, label):
            if label == "observed CUDA singleton/default identity":
                check_probe(LOCAL, selected, actual)
            else:
                SC.equal(actual, expected, label)

        def expected_summary(*summary_args):
            return dict(SC.expected_summary(*summary_args), gpu_name=LOCAL_GPU_NAME, gpu_uuid=uuid)

        schema = types.SimpleNamespace(**dict(vars(SC), equal=local_equal,
                                               check_summary=_bind(SC.check_summary, expected_summary=expected_summary)))
        result = _bind(V.check_kernel, SC=schema, select_worker_gpu=lambda text: select_worker_gpu(text, LOCAL))(out, *args, **kwargs)
        uuids.add(uuid)
        return result

    schema = types.SimpleNamespace(**dict(vars(SC), tool_hashes=lambda: {**SC.tool_hashes(), MODULE_REL: SC.sha256_path(Path(repo) / MODULE_REL)}))
    builder = types.SimpleNamespace(**dict(vars(B), render=render_runner))
    verifier = _bind(V.verify, SC=schema, B=builder, check_kernel=check_kernel,
                     load_campaign=lambda path, repo: (c, digest, rel))
    table = verifier(campaign_path, kernel_dirs, freeze_path, smoke, repo, source_commit)
    SC.req(len(uuids) == 1, "local kernel outputs must share one CUDA UUID")
    return dict(table, backend_profile=LOCAL, used_gpu_count=1, used_gpu_count_evidence="gpu_device_probe.json:logical_device_count", cuda_uuid=uuids.pop())
