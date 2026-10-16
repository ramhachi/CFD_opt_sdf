"""harness v1 build / smoke / freeze: render the pinned per-kernel runners from a campaign.json, check that every bound byte is committed at the source commit, and freeze.

All functions take `repo` (default: this checkout) so tests can use a scratch repository.  Nothing here pushes to Kaggle or to git.
"""
from __future__ import annotations

import csv
import datetime
import io
import json
import re
import subprocess
from pathlib import Path

from cfd_harness import campaign_schema as SC

REPO = Path(__file__).resolve().parents[2]
PROJECT = "julia/CFDSDFWaterLilyT4"
SCHEMA_REL = "src/cfd_harness/campaign_schema.py"
TEMPLATE_REL = "src/cfd_harness/campaign_runner_template.py"
BASE_PINS = (f"{PROJECT}/Project.toml", f"{PROJECT}/Manifest.toml", "scripts/step01_states.py", "scripts/grid01_gpu.py", "scripts/fd08_v2_campaign_io.py", "julia/CFDSDFWaterLily/src", SCHEMA_REL)
ALWAYS_SPARSE = ("julia/", "scripts/", "src/cfd_harness/")


def git(repo, *args, check=True):
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, check=check)


def load(campaign_path, repo=REPO):
    path = Path(campaign_path).resolve()
    campaign = SC.jload(path)
    SC.validate_campaign(campaign)
    return campaign, str(path.relative_to(Path(repo).resolve())), SC.sha256_path(path)


def pins(c, rel, k, repo=REPO):
    """The runtime pin map of kernel k: harness files, the campaign, the baseline and direction raws (checked against the declared hashes), the kernel's job and the declared extras."""
    kernel = c["kernels"][k]
    raws = [c["baseline"]] + list(c["directions"].values())
    paths = set(BASE_PINS) | {rel, kernel["job"]} | {d["path"] for d in raws} | set(c["pins"]) | set(kernel.get("pins", []))
    out = {p: SC.sha256_path(Path(repo) / p) for p in sorted(paths)}
    for d in raws:
        SC.req(out[d["path"]] == d["sha256_fortran_raw"], f"the raw file differs from the campaign hash: {d['path']}")
    return out


def verify_source(repo, source_commit, paths):
    """Every bound path (file or directory) is committed at source_commit with exactly the working-tree bytes and, for a directory, the same members."""
    SC.req(SC.COMMIT.fullmatch(source_commit or "") is not None, "source commit must be a full lowercase SHA")
    repo = Path(repo)
    for rel in sorted(paths):
        path = repo / rel
        names = sorted(str(p.relative_to(repo)) for p in path.rglob("*") if p.is_file() and "__pycache__" not in p.parts) if path.is_dir() else [rel]
        for name in names:
            shown = git(repo, "show", f"{source_commit}:{name}", check=False)
            SC.req(shown.returncode == 0, f"not committed at the source commit: {name}")
            SC.req(SC.sha256_bytes(shown.stdout) == SC.sha256_path(repo / name), f"committed source differs: {name}")
        if path.is_dir():
            tracked = git(repo, "ls-tree", "-r", "--name-only", source_commit, "--", rel).stdout.decode().splitlines()
            SC.req(names == sorted(t for t in tracked if "__pycache__" not in t), f"source tree members differ: {rel}")


def require_on_remote(repo, source_commit):
    """Fresh (not cache-based) check: after `git fetch origin` the source commit equals or is an ancestor of a current remote branch head (`git ls-remote`); offline -> fail closed."""
    SC.req(git(repo, "fetch", "-q", "origin", check=False).returncode == 0, "cannot fetch origin (offline?); the remote reachability of the source commit cannot be verified")
    listing = git(repo, "ls-remote", "--heads", "origin", check=False)
    heads = [line.split()[0] for line in listing.stdout.decode().splitlines() if line.strip()] if listing.returncode == 0 else []
    SC.req(any(h == source_commit or git(repo, "merge-base", "--is-ancestor", source_commit, h, check=False).returncode == 0 for h in heads),
           "the source commit is not on a remote branch; push it before building (the Kaggle runner fetches it from GitHub)")


def pin_block(c, rel, k, source_commit, smoke, pinmap):
    kernel = c["kernels"][k]
    sparse = sorted(set(ALWAYS_SPARSE) | set(pinmap) | set(c["sparse"]))
    lines = {"KERNEL": k, "KERNEL_ID": kernel["kernel_id"] + ("-smoke" if smoke else ""), "SOURCE_COMMIT": source_commit, "REPO_URL": c["repo_url"], "CAMPAIGN": rel, "SMOKE": smoke,
             "OUT_DIR_NAME": SC.out_dir_name(c, k), "INDEX_NAME": SC.index_name(c), "SPARSE": sparse}
    return "\n".join([f"{key} = {value!r}" if isinstance(value, bool) else f"{key} = {json.dumps(value)}" for key, value in lines.items()]
                     + ["PINS = {"] + [f"    {json.dumps(p)}: {json.dumps(h)}," for p, h in pinmap.items()] + ["}"])


def render(campaign_path, source_commit, k, smoke=False, repo=REPO):
    c, rel, _ = load(campaign_path, repo)
    SC.req(SC.COMMIT.fullmatch(source_commit) is not None, "source commit must be a full lowercase SHA")
    text = (Path(repo) / TEMPLATE_REL).read_text()
    SC.req(text.count(SC.PIN_BEGIN) == 1 and text.count(SC.PIN_END) == 1 and text.count("\nPIN_BLOCK\n") == 1, "runner template pin markers differ")
    text = text.replace("PIN_BLOCK", pin_block(c, rel, k, source_commit, smoke, pins(c, rel, k, repo)))
    compile(text, "runner.py", "exec")
    return text


def split_pin(text):
    head, rest = text.split(SC.PIN_BEGIN + "\n")
    block, tail = rest.split("\n" + SC.PIN_END)
    return head, block, tail


def assert_pin_only_diff(formal, smoke):
    (h1, b1, t1), (h2, b2, t2) = split_pin(formal), split_pin(smoke)
    SC.req(h1 == h2 and t1 == t2 and b1 != b2, "a smoke runner may differ from the formal runner only inside the PIN block")


def metadata(c, k, smoke=False):
    kid = c["kernels"][k]["kernel_id"] + ("-smoke" if smoke else "")
    return {"id": kid, "title": kid.split("/")[1], "code_file": SC.RUNNER_FILE, "language": "python", "kernel_type": "script", "is_private": True, "enable_gpu": True, "enable_internet": True,
            "machine_shape": "NvidiaTeslaT4", "dataset_sources": [], "competition_sources": [], "kernel_sources": [], "model_sources": []}


def kernel_dir(c, k, smoke=False, repo=REPO):
    return Path(repo) / "infra/kaggle" / f"kernel_{c['campaign_id']}_{k}{'_smoke' if smoke else ''}"


def bound_paths(c, rel, repo=REPO):
    return {p for k in c["kernels"] for p in pins(c, rel, k, repo)} | {TEMPLATE_REL}


def write_kernel(c, k, text, smoke, repo=REPO):
    d = kernel_dir(c, k, smoke, repo)
    d.mkdir(parents=True)
    (d / SC.RUNNER_FILE).write_text(text)
    (d / SC.METADATA_FILE).write_text(json.dumps(metadata(c, k, smoke), sort_keys=True, indent=2) + "\n")
    return d


def build(campaign_path, source_commit, repo=REPO):
    c, rel, _ = load(campaign_path, repo)
    verify_source(repo, source_commit, bound_paths(c, rel, repo))
    for k in c["kernels"]:
        SC.req(not kernel_dir(c, k, False, repo).exists(), f"refusing to overwrite rendered worker: {kernel_dir(c, k, False, repo).name}")
    return [write_kernel(c, k, render(campaign_path, source_commit, k, False, repo), False, repo) for k in c["kernels"]]


def smoke_kernel(c, k=None):
    """The cheapest case (smallest solver length, then per-state timeout) unless a kernel is named."""
    return k or min(c["kernels"], key=lambda n: (c["kernels"][n]["case"]["solver_length"], c["kernels"][n]["config"]["per_state_timeout_s"]))


def smoke(campaign_path, source_commit, k=None, repo=REPO):
    """Render the SAME runner as the formal one for the cheapest kernel under a -smoke slug (first state only); returns (directory, push command).  Does not push."""
    c, rel, _ = load(campaign_path, repo)
    k = smoke_kernel(c, k)
    SC.req(k in c["kernels"], f"unknown kernel {k}")
    verify_source(repo, source_commit, bound_paths(c, rel, repo))
    require_on_remote(repo, source_commit)
    SC.req(not kernel_dir(c, k, True, repo).exists(), f"refusing to overwrite rendered smoke worker: {kernel_dir(c, k, True, repo).name}")
    formal, smoked = render(campaign_path, source_commit, k, False, repo), render(campaign_path, source_commit, k, True, repo)
    assert_pin_only_diff(formal, smoked)
    d = write_kernel(c, k, smoked, True, repo)
    cmd = ["kaggle", "kernels", "push", "-p", str(d.relative_to(Path(repo))), "--accelerator", "NvidiaTeslaT4", "--timeout", str(c["kernels"][k]["config"]["kernel_timeout_s"])]
    return d, cmd


# ---- freeze ---------------------------------------------------------------------------------------------------------------------------------------
def kaggle(args):
    r = subprocess.run(["kaggle", *args], capture_output=True, text=True)
    return {"command": ["kaggle", *args], "exit_code": r.returncode, "stdout": r.stdout, "stderr": r.stderr}


def identity_free_check(c):
    """Authenticated, fully paginated listing of the owner's kernels and datasets: no target slug (or title that normalizes to it) may exist; positive access control on an existing resource."""
    owner, targets = c["owner"], {k["kernel_id"].split("/")[1] for k in c["kernels"].values()}
    record = {"kind": "harness_authenticated_identity_free_check", "owner": owner, "captured_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(), "kernel_ids": [k["kernel_id"] for k in c["kernels"].values()],
              "listings": {}, "positive_controls": {}}
    forbidden = re.compile("403|forbidden|unauthorized", re.I)

    def bad_text(r):  # stderr, and stdout unless it is a CSV listing (a slug may legitimately contain "403")
        return forbidden.search(r["stderr"] + ("" if r["stdout"].lstrip().startswith("ref") else r["stdout"]))
    for kind in ("kernels", "datasets"):
        pages, rows = [], []
        for page in range(1, 101):
            result = kaggle([kind, "list", "--mine", "--page-size", "100", "--page", str(page), "--csv"])
            SC.req(not result["exit_code"] and not bad_text(result), f"{kind} authenticated listing failed")
            parsed = [] if result["stdout"].strip() in ("Not found", "No datasets found", "No kernels found", "") else list(csv.DictReader(io.StringIO(result["stdout"])))
            SC.req(all(r.get("ref", "").startswith(owner + "/") for r in parsed), f"{kind} listing returned a different owner or malformed CSV")
            pages.append({**result, "rows": parsed})
            rows.extend(parsed)
            if len(parsed) < 100:
                break
        else:
            raise ValueError("listing pagination limit reached")
        SC.req(rows and len({r["ref"] for r in rows}) == len(rows), "positive owned listing or unique rows missing")
        taken = {r["ref"].split("/")[1] for r in rows} | {re.sub(r"[^a-z0-9]+", "-", r.get("title", "").lower()).strip("-") for r in rows}
        SC.req(not targets & taken, f"{kind} provider identity collision: {sorted(targets & taken)}")
        control = kaggle([kind, "status", rows[0]["ref"]] if kind == "kernels" else [kind, "files", rows[0]["ref"], "--csv"])
        SC.req(not control["exit_code"] and control["stdout"].strip() and not bad_text(control), "existing-resource positive access control failed")
        record["listings"][kind] = {"pages": pages, "rows": rows, "complete": True}
        record["positive_controls"][kind] = control
    record["all_free"] = True
    return record


def freeze_path(campaign_path):
    p = Path(campaign_path)
    return p.with_name(p.stem + ".prerun_freeze.json")


def freeze(campaign_path, source_commit, repo=REPO):
    c, rel, campaign_sha = load(campaign_path, repo)
    target = freeze_path(campaign_path)
    SC.req(not target.exists() and not target.with_name(target.name + ".sha256").exists(), "refusing to overwrite an immutable freeze")
    SC.req(not git(repo, "status", "--porcelain", "--untracked-files=no").stdout.strip(), "tracked files have uncommitted changes; freeze only committed reviewed bytes")
    require_on_remote(repo, source_commit)
    verify_source(repo, source_commit, bound_paths(c, rel, repo))
    runtime, pin_maps = {}, {}
    for k, kernel in c["kernels"].items():
        d = kernel_dir(c, k, False, repo)
        SC.req((d / SC.RUNNER_FILE).read_text() == render(campaign_path, source_commit, k, False, repo), f"rendered worker differs from reviewed source: {k}")
        SC.req(SC.jload(d / SC.METADATA_FILE) == metadata(c, k), f"kernel metadata mismatch: {k}")
        pin_maps[k] = pins(c, rel, k, repo)
        runtime[k] = {"kernel_id": kernel["kernel_id"], "case_id": kernel["case"]["case_id"], "job": kernel["job"], "config": kernel["config"], "runner_sha256": SC.sha256_path(d / SC.RUNNER_FILE),
                      "metadata_sha256": SC.sha256_path(d / SC.METADATA_FILE), "machine_shape": "NvidiaTeslaT4"}
    record = {"kind": SC.FREEZE_KIND, "harness_version": SC.HARNESS_VERSION, "frozen_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(), "campaign_path": rel, "campaign_sha256": campaign_sha,
              "source_commit": source_commit, "pins": pin_maps, "runtime": runtime, "identity_free_check": identity_free_check(c)}
    data = (json.dumps(record, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()
    target.write_bytes(data)
    target.with_name(target.name + ".sha256").write_text(SC.sha256_bytes(data) + "\n")
    return target
