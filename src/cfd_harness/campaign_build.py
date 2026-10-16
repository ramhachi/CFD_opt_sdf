"""harness v1.1 build / smoke / freeze: render the pinned per-kernel runners from a campaign.json, check that every bound byte is committed at the source commit, and freeze.

All functions take `repo` (default: this checkout) so tests can use a scratch repository.  Nothing here pushes to Kaggle or to git.
"""
from __future__ import annotations

import datetime
import json
import os
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


INCLUDE = re.compile(r"\binclude\(")


def julia_includes(rel, text):
    """The repo-relative files a Julia source includes: include("x.jl"), include(joinpath(@__DIR__, "a", "x.jl")) and Base.include(Module, joinpath(@__DIR__, ...)); anything else fails closed."""
    text, found = re.sub(r"#[^\n]*", "", text), []  # ponytail: a '#' inside a string literal drops the rest of that line; no include path contains one
    for m in INCLUDE.finditer(text):
        depth, j = 1, m.end()
        while j < len(text) and depth:
            depth += (text[j] == "(") - (text[j] == ")")
            j += 1
        args = text[m.end():j - 1]
        literals = re.findall(r'"([^"]*)"', args)
        SC.req(depth == 0 and literals and ("joinpath(@__DIR__" in args or (len(literals) == 1 and "@__DIR__" not in args and "joinpath" not in args)), f"unresolvable Julia include in {rel}: include({args.strip()[:80]})")
        target = os.path.normpath(os.path.join(os.path.dirname(rel), *literals))
        SC.req(not target.startswith("..") and not os.path.isabs(target), f"Julia include escapes the repository: {rel} -> {target}")
        found.append(target)
    return found


def check_include_closure(repo, paths):
    """Every Julia file included (recursively) by a pinned .jl file is itself pinned, as a file or inside a pinned directory (whose own contents are covered by its hash and not scanned)."""
    repo, pinned = Path(repo), set(paths)
    todo, done = sorted(p for p in pinned if p.endswith(".jl") and (repo / p).is_file()), set()
    while todo:
        rel = todo.pop()
        if rel in done:
            continue
        done.add(rel)
        for inc in julia_includes(rel, (repo / rel).read_text()):
            SC.req(inc in pinned or any(inc.startswith(p + "/") for p in pinned), f"{rel} includes {inc}, which is not pinned (add it to the kernel's pins)")
            SC.req((repo / inc).is_file(), f"{rel} includes a missing file: {inc}")
            if inc in pinned and inc.endswith(".jl"):
                todo.append(inc)


def pins(c, rel, k, repo=REPO):
    """The runtime pin map of kernel k: harness files, the campaign, the baseline and direction raws (checked against the declared hashes), the kernel's job and the declared extras."""
    kernel = c["kernels"][k]
    raws = [c["baseline"]] + list(c["directions"].values())
    paths = set(BASE_PINS) | {rel, kernel["job"]} | {d["path"] for d in raws} | set(c["pins"]) | set(kernel.get("pins", []))
    check_include_closure(repo, paths)
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


def norm_url(url):
    url = re.sub(r"\.git$", "", url.strip().rstrip("/"))
    m = re.fullmatch(r"git@([^:]+):(.+)", url)
    return f"https://{m[1]}/{m[2]}".lower() if m else url.lower() if url.startswith("https://") else url


def require_on_remote(repo, source_commit, repo_url):
    """The runner fetches the campaign's repo_url, so: origin must be that repository, then (fresh, not cache-based) after `git fetch origin` the source commit equals or is an ancestor of a current
    remote branch head (`git ls-remote`); offline or any mismatch -> fail closed."""
    origin = git(repo, "remote", "get-url", "origin", check=False)
    SC.req(origin.returncode == 0 and norm_url(origin.stdout.decode()) == norm_url(repo_url), f"git origin is not the campaign repo_url {repo_url} that the Kaggle runner fetches")
    SC.req(git(repo, "fetch", "-q", "origin", check=False).returncode == 0, "cannot fetch origin (offline?); the remote reachability of the source commit cannot be verified")
    listing = git(repo, "ls-remote", "--heads", "origin", check=False)
    heads = [line.split()[0] for line in listing.stdout.decode().splitlines() if line.strip()] if listing.returncode == 0 else []
    SC.req(any(h == source_commit or git(repo, "merge-base", "--is-ancestor", source_commit, h, check=False).returncode == 0 for h in heads),
           "the source commit is not on a remote branch of the campaign repo_url; push it before building (the Kaggle runner fetches it from GitHub)")


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


def refuse_legacy(c):
    SC.req(not c["legacy_replay"], "a legacy_replay campaign describes pre-harness outputs for verification only; it cannot be built, smoked or frozen")


def build(campaign_path, source_commit, repo=REPO):
    c, rel, _ = load(campaign_path, repo)
    refuse_legacy(c)
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
    refuse_legacy(c)
    k = smoke_kernel(c, k)
    SC.req(k in c["kernels"], f"unknown kernel {k}")
    verify_source(repo, source_commit, bound_paths(c, rel, repo))
    require_on_remote(repo, source_commit, c["repo_url"])
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
    """Authenticated, fully paginated listing of the owner's kernels and datasets: no target slug (or title that normalizes to it) may exist; positive access control on an existing resource.
    Pagination continues until a page adds no new ref (an empty page, or a repeated one), whatever the server's page size, and fails closed at FREE_MAX_PAGES."""
    owner, targets = c["owner"], {k["kernel_id"].split("/")[1] for k in c["kernels"].values()}
    record = {"kind": SC.FREE_KIND, "owner": owner, "captured_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(), "kernel_ids": [k["kernel_id"] for k in c["kernels"].values()],
              "listings": {}, "positive_controls": {}}
    for kind in ("kernels", "datasets"):
        pages, rows, seen = [], [], set()
        for number in range(1, SC.FREE_MAX_PAGES + 1):
            result = kaggle(SC.page_command(kind, number)[1:])
            SC.req(not result["exit_code"] and not SC.kaggle_bad(result), f"{kind} authenticated listing failed")
            parsed = SC.parse_listing(result["stdout"])
            SC.req(all(r.get("ref", "").startswith(owner + "/") for r in parsed), f"{kind} listing returned a different owner or malformed CSV")
            pages.append({**result, "rows": parsed})
            new = [r for r in parsed if r["ref"] not in seen]
            seen |= {r["ref"] for r in new}
            rows += new
            if not new:
                break
        else:
            raise ValueError("listing pagination limit reached")
        SC.req(rows, "positive owned listing missing")
        SC.req(not targets & SC.taken_names(rows), f"{kind} provider identity collision: {sorted(targets & SC.taken_names(rows))}")
        control = kaggle(SC.control_command(kind, rows[0]["ref"])[1:])
        SC.req(not control["exit_code"] and control["stdout"].strip() and not SC.kaggle_bad(control), "existing-resource positive access control failed")
        record["listings"][kind] = {"pages": pages, "rows": rows, "complete": True}
        record["positive_controls"][kind] = control
    record["all_free"] = True
    return record


def freeze_path(campaign_path):
    p = Path(campaign_path)
    return p.with_name(p.stem + ".prerun_freeze.json")


def check_smoke_record(smoke_table, c, campaign_sha, source_commit):
    """A smoke verify output (`harness.py verify --smoke ... --out`) of this campaign at this source commit must exist before the formal freeze; returns its SHA-256."""
    t = SC.jload(smoke_table)
    SC.req(isinstance(t, dict) and t.get("kind") == SC.TABLE_KIND and t.get("harness_version") == SC.HARNESS_VERSION and t.get("smoke") is True, "the smoke record is not a harness smoke verify output")
    SC.req(t.get("campaign_sha256") == campaign_sha and t.get("source_commit") == source_commit, "the smoke record is for another campaign or source commit")
    SC.req(t.get("integrity") == {"pass": True, "failures": []} and len(t.get("kernel_manifest_sha256", {})) == 1 and set(t["kernel_manifest_sha256"]) <= set(c["kernels"]), "the smoke record is not a passed single-kernel verification")
    return SC.sha256_path(smoke_table)


def freeze(campaign_path, source_commit, repo=REPO, smoke_table=None):
    c, rel, campaign_sha = load(campaign_path, repo)
    refuse_legacy(c)
    target = freeze_path(campaign_path)
    SC.req(not target.exists() and not target.with_name(target.name + ".sha256").exists(), "refusing to overwrite an immutable freeze")
    SC.req(smoke_table is not None, "freeze requires the verified smoke record (--smoke-table): no formal freeze before a smoke kernel of this campaign and commit passed `verify --smoke`")
    smoke_sha = check_smoke_record(smoke_table, c, campaign_sha, source_commit)
    SC.req(not git(repo, "status", "--porcelain", "--untracked-files=no").stdout.strip(), "tracked files have uncommitted changes; freeze only committed reviewed bytes")
    require_on_remote(repo, source_commit, c["repo_url"])
    verify_source(repo, source_commit, bound_paths(c, rel, repo))
    runtime, pin_maps = {}, {}
    for k, kernel in c["kernels"].items():
        d = kernel_dir(c, k, False, repo)
        SC.req((d / SC.RUNNER_FILE).read_text() == render(campaign_path, source_commit, k, False, repo), f"rendered worker differs from reviewed source: {k}")
        SC.req(SC.jload(d / SC.METADATA_FILE) == metadata(c, k), f"kernel metadata mismatch: {k}")
        pin_maps[k] = pins(c, rel, k, repo)
        runtime[k] = {"kernel_id": kernel["kernel_id"], "case_id": kernel["case"]["case_id"], "job": kernel["job"], "config": kernel["config"], "runner_sha256": SC.sha256_path(d / SC.RUNNER_FILE),
                      "metadata_sha256": SC.sha256_path(d / SC.METADATA_FILE), "machine_shape": "NvidiaTeslaT4"}
    free = identity_free_check(c)
    record = {"kind": SC.FREEZE_KIND, "harness_version": SC.HARNESS_VERSION, "legacy_replay": c["legacy_replay"], "campaign_path": rel, "campaign_sha256": campaign_sha, "source_commit": source_commit,
              "pins": pin_maps, "runtime": runtime, "smoke_verified_sha256": smoke_sha, "harness_tool_sha256": SC.tool_hashes(), "identity_free_check": free,
              "frozen_utc": datetime.datetime.now(datetime.timezone.utc).isoformat()}
    SC.validate_identity_free(free, c, record["frozen_utc"])  # what was just captured must pass the verifier's own re-validation
    data = (json.dumps(record, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()
    target.write_bytes(data)
    target.with_name(target.name + ".sha256").write_text(SC.sha256_bytes(data) + "\n")
    return target
