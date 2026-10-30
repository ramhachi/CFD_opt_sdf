"""harness v1.1 acceptance (f): build / smoke / freeze against a scratch git repository with a local bare remote; the identity-free check paginates; nothing is pushed to Kaggle."""
import copy
import csv
import datetime
import io
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import harness_testlib as T  # noqa: E402
from cfd_harness import campaign_build as B  # noqa: E402
from cfd_harness import campaign_verify as V  # noqa: E402
import harness as H  # noqa: E402

SC = T.SC
REL = "docs/harness/mini.json"
ENV = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
SLUG = "cfd-opt-sdf-grid02-s24"


def g(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True, env=ENV).stdout.strip()


def put(repo, rel, text):
    p = Path(repo) / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)


@pytest.fixture
def scratch(tmp_path):
    """A repository holding the real template and schema, stub pinned files and a one-kernel campaign, committed and pushed to a bare remote."""
    repo, remote = tmp_path / "repo", tmp_path / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", str(remote)], check=True)
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
    for rel in (B.TEMPLATE_REL, B.SCHEMA_REL):
        put(repo, rel, (T.ROOT / rel).read_text())
    for rel in B.BASE_PINS:
        if rel not in (B.SCHEMA_REL, "julia/CFDSDFWaterLily/src"):
            put(repo, rel, f"stub {rel}\n")
    put(repo, "julia/CFDSDFWaterLily/src/a.jl", "stub\n")
    c = json.loads(T.REPLAY.read_text())
    kernel = c["kernels"]["s24"]
    names = SC.run_names(kernel)[:2]
    c["kernels"] = {"s24": {**kernel, "runs": kernel["runs"][:2]}}
    c["states"] = {n: c["states"][n] for n in names}
    c["pins"] = []
    c["legacy_replay"] = False
    c["repo_url"] = str(remote)  # the runner fetches repo_url: the scratch remote
    put(repo, kernel["job"], "stub job\n")
    put(repo, c["baseline"]["path"], "baseline raw\n")
    put(repo, c["directions"]["robust_opt01a"]["path"], "direction raw\n")
    c["baseline"]["sha256_fortran_raw"] = SC.sha256_path(repo / c["baseline"]["path"])
    c["directions"]["robust_opt01a"]["sha256_fortran_raw"] = SC.sha256_path(repo / c["directions"]["robust_opt01a"]["path"])
    put(repo, REL, json.dumps(c, indent=2, sort_keys=True))
    g(repo, "add", "-A")
    g(repo, "commit", "-qm", "base")
    g(repo, "remote", "add", "origin", str(remote))
    g(repo, "push", "-q", "origin", "main")
    return repo


def commit(repo):
    return g(repo, "rev-parse", "HEAD")


def fake_kaggle(kernel_rows=250, dataset_rows=3, collide_at=None, collide_title=None, fail_page=None, calls=None, page_size=100, repeat_last=False):
    def rows(kind, n, page):
        out = []
        if repeat_last and page > 2:  # a server that keeps returning its last page
            page = 2
        for i in range((page - 1) * page_size, min(page * page_size, n)):
            slug, title = f"{kind}-{i}", f"Title {kind} {i}"
            if kind == "kernels" and collide_at == i:
                slug = SLUG
            if kind == "kernels" and collide_title == i:
                title = "Cfd Opt Sdf Grid02 S24"
            out.append({"ref": f"ramhachi888/{slug}", "title": title})
        return out

    def kaggle(args):
        if calls is not None:
            calls.append(args)
        kind, cmd = args[0], args[1]
        if cmd == "list":
            page = int(args[args.index("--page") + 1])
            if fail_page == page:
                return {"command": ["kaggle", *args], "exit_code": 1, "stdout": "", "stderr": "403 Forbidden"}
            data = rows(kind, kernel_rows if kind == "kernels" else dataset_rows, page)
            buf = io.StringIO()
            w = csv.DictWriter(buf, ["ref", "title"])
            w.writeheader()
            w.writerows(data)
            return {"command": ["kaggle", *args], "exit_code": 0, "stdout": buf.getvalue() if data else "", "stderr": ""}
        return {"command": ["kaggle", *args], "exit_code": 0, "stdout": "ok\n", "stderr": ""}
    return kaggle


def built(repo):
    B.build(repo / REL, commit(repo), repo)
    return commit(repo)


def smoke_table(tmp, repo, src, **over):
    """The `verify --smoke --out` table a freeze requires (the verifier's own output shape)."""
    c, _, sha = B.load(repo / REL, repo)
    t = {"kind": SC.TABLE_KIND, "harness_version": SC.HARNESS_VERSION, "campaign_sha256": sha, "source_commit": src, "smoke": True, "integrity": {"pass": True, "failures": []},
         "kernel_manifest_sha256": {"s24": "0" * 64}, "state_forces_n": {"s24": {}}, **over}
    path = Path(tmp) / f"smoke_{len(over)}.json"
    path.write_text(json.dumps(t))
    return path


def freeze(tmp, repo, src, **over):
    return B.freeze(repo / REL, src, repo, smoke_table=smoke_table(tmp, repo, src, **over))


# ---------------------------------------------------------------- build
def test_build_renders_the_pinned_worker_and_refuses_to_overwrite_or_to_bind_uncommitted_bytes(scratch):
    src = commit(scratch)
    d = B.build(scratch / REL, src, scratch)[0]
    assert d.name == "kernel_grid02_s24" and (d / "runner.py").is_file() and json.loads((d / "kernel-metadata.json").read_text())["title"] == SLUG
    with pytest.raises(ValueError, match="refusing to overwrite"):
        B.build(scratch / REL, src, scratch)
    put(scratch, "scripts/step01_states.py", "changed after the commit\n")
    shutil.rmtree(d)
    with pytest.raises(ValueError, match="committed source differs"):
        B.build(scratch / REL, src, scratch)
    with pytest.raises(ValueError, match="full lowercase SHA"):
        B.build(scratch / REL, "abc", scratch)


def test_build_refuses_a_raw_that_differs_from_the_declared_campaign_hash(scratch):
    put(scratch, "docs/evidence/opt01b_stage_b_2026_10_15/inputs/parent.phi_f4_fortran.raw", "different bytes\n")
    g(scratch, "commit", "-qam", "change raw")
    with pytest.raises(ValueError, match="differs from the campaign hash"):
        B.build(scratch / REL, commit(scratch), scratch)


# ---------------------------------------------------------------- freeze
def test_freeze_writes_a_verifier_valid_record_with_a_paginated_identity_listing_and_is_write_once(scratch, monkeypatch, tmp_path):
    src = built(scratch)
    calls = []
    monkeypatch.setattr(B, "kaggle", fake_kaggle(calls=calls))
    target = freeze(tmp_path, scratch, src)
    record = json.loads(target.read_text())
    check = record["identity_free_check"]
    listing = check["listings"]["kernels"]
    assert [len(p["rows"]) for p in listing["pages"]] == [100, 100, 50, 0] and len(listing["rows"]) == 250 and [len(p["rows"]) for p in check["listings"]["datasets"]["pages"]] == [3, 0]
    assert sum(1 for a in calls if a[:2] == ["kernels", "list"]) == 4 and check["all_free"] is True and record["legacy_replay"] is False
    c, rel, sha = B.load(scratch / REL, scratch)
    V.validate_freeze(record, target, c, sha, rel)  # the verifier accepts exactly what freeze writes
    assert record["source_commit"] == src and record["pins"]["s24"][REL] == sha and record["runtime"]["s24"]["runner_sha256"] == SC.sha256_path(B.kernel_dir(c, "s24", False, scratch) / "runner.py")
    assert record["campaign_path"] == REL and record["smoke_verified_sha256"] == SC.sha256_path(tmp_path / "smoke_0.json") and set(record["harness_tool_sha256"]) == set(SC.TOOL_FILES)
    with pytest.raises(ValueError, match="refusing to overwrite"):
        freeze(tmp_path, scratch, src)


def test_freeze_requires_a_verified_smoke_record_of_this_campaign_and_commit(scratch, monkeypatch, tmp_path):
    src = built(scratch)
    monkeypatch.setattr(B, "kaggle", fake_kaggle())
    with pytest.raises(ValueError, match="requires the verified smoke record"):
        B.freeze(scratch / REL, src, scratch)
    for over in ({"smoke": False}, {"source_commit": "1" * 40}, {"campaign_sha256": "2" * 64}, {"integrity": {"pass": False, "failures": ["x"]}}, {"kind": "other"},
                 {"kernel_manifest_sha256": {"s24": "0" * 64, "s32": "0" * 64}}, {"kernel_manifest_sha256": {"zz": "0" * 64}}):
        with pytest.raises(ValueError, match="smoke record"):
            freeze(tmp_path, scratch, src, **over)
    assert not B.freeze_path(scratch / REL).exists()


@pytest.mark.parametrize("kw", [{"collide_at": 220}, {"collide_title": 230}, {"collide_at": 5}])
def test_freeze_detects_a_slug_collision_on_any_listing_page(scratch, monkeypatch, kw, tmp_path):
    src = built(scratch)
    monkeypatch.setattr(B, "kaggle", fake_kaggle(**kw))
    with pytest.raises(ValueError, match="identity collision"):
        freeze(tmp_path, scratch, src)
    assert not B.freeze_path(scratch / REL).exists()


def test_freeze_fails_closed_when_a_listing_page_is_forbidden_or_the_pagination_never_ends(scratch, monkeypatch, tmp_path):
    src = built(scratch)
    monkeypatch.setattr(B, "kaggle", fake_kaggle(fail_page=2))
    with pytest.raises(ValueError, match="authenticated listing failed"):
        freeze(tmp_path, scratch, src)
    monkeypatch.setattr(B, "kaggle", fake_kaggle(kernel_rows=100 * 101))
    with pytest.raises(ValueError, match="pagination limit"):
        freeze(tmp_path, scratch, src)


def test_identity_free_pagination_does_not_stop_on_a_short_page_and_stops_on_a_repeated_one(scratch, monkeypatch, tmp_path):
    """A server that returns fewer than 100 rows per page (S3: the old `len(page) < 100` rule stopped after page 1 and missed a colliding slug on page 3)."""
    src = built(scratch)
    monkeypatch.setattr(B, "kaggle", fake_kaggle(collide_at=45, page_size=20))
    with pytest.raises(ValueError, match="identity collision"):
        freeze(tmp_path, scratch, src)
    monkeypatch.setattr(B, "kaggle", fake_kaggle(page_size=20, kernel_rows=60))
    record = json.loads(freeze(tmp_path, scratch, src).read_text())
    assert [len(p["rows"]) for p in record["identity_free_check"]["listings"]["kernels"]["pages"]] == [20, 20, 20, 0] and len(record["identity_free_check"]["listings"]["kernels"]["rows"]) == 60
    B.freeze_path(scratch / REL).unlink()
    B.freeze_path(scratch / REL).with_name("mini.prerun_freeze.json.sha256").unlink()
    monkeypatch.setattr(B, "kaggle", fake_kaggle(kernel_rows=150, repeat_last=True, page_size=100))  # page 3 repeats page 2: zero new refs ends the listing
    pages = json.loads(freeze(tmp_path, scratch, src).read_text())["identity_free_check"]["listings"]["kernels"]["pages"]
    assert [len(p["rows"]) for p in pages] == [100, 50, 50]


def test_freeze_refuses_a_dirty_tracked_tree(scratch, monkeypatch, tmp_path):
    src = built(scratch)
    monkeypatch.setattr(B, "kaggle", fake_kaggle())
    put(scratch, "scripts/grid01_gpu.py", "edited, not committed\n")
    with pytest.raises(ValueError, match="uncommitted changes"):
        freeze(tmp_path, scratch, src)
    g(scratch, "checkout", "scripts/grid01_gpu.py")
    put(scratch, "untracked_note.txt", "untracked files do not block\n")
    assert freeze(tmp_path, scratch, src).is_file()


def test_freeze_refuses_a_commit_that_is_not_on_a_remote_head_and_an_offline_remote(scratch, monkeypatch, tmp_path):
    src = built(scratch)
    monkeypatch.setattr(B, "kaggle", fake_kaggle())
    put(scratch, "docs/note.txt", "new local commit\n")
    g(scratch, "add", "-A")
    g(scratch, "commit", "-qm", "unpushed")
    unpushed = commit(scratch)
    with pytest.raises(ValueError, match="not on a remote branch"):
        freeze(tmp_path, scratch, unpushed)
    g(scratch, "push", "-q", "origin", "main")
    assert freeze(tmp_path, scratch, src).is_file()  # an ancestor of a pushed head is reachable
    shutil.rmtree(tmp_path / "remote.git")
    B.freeze_path(scratch / REL).unlink()
    B.freeze_path(scratch / REL).with_name("mini.prerun_freeze.json.sha256").unlink()
    with pytest.raises(ValueError, match="cannot fetch origin"):
        freeze(tmp_path, scratch, src)


def test_the_remote_check_is_against_the_campaign_repo_url_not_whatever_origin_is(scratch, monkeypatch, tmp_path):
    """S4: the runner fetches repo_url; a commit pushed to a different origin proves nothing about it."""
    src = built(scratch)
    monkeypatch.setattr(B, "kaggle", fake_kaggle())
    other = tmp_path / "other.git"
    subprocess.run(["git", "init", "-q", "--bare", str(other)], check=True)
    g(scratch, "remote", "set-url", "origin", str(other))
    g(scratch, "push", "-q", "origin", "main")  # the commit IS on origin, but origin is not the campaign's repo_url
    with pytest.raises(ValueError, match="not the campaign repo_url"):
        freeze(tmp_path, scratch, src)
    with pytest.raises(ValueError, match="not the campaign repo_url"):
        B.smoke(scratch / REL, src, repo=scratch)
    assert B.norm_url("git@github.com:Foo/Bar.git") == B.norm_url("https://github.com/foo/bar/") == "https://github.com/foo/bar"


def test_freeze_refuses_a_rendered_worker_that_differs_from_the_reviewed_source(scratch, monkeypatch, tmp_path):
    src = built(scratch)
    monkeypatch.setattr(B, "kaggle", fake_kaggle())
    runner = scratch / "infra/kaggle/kernel_grid02_s24/runner.py"
    runner.write_text(runner.read_text() + "# edited by hand\n")
    with pytest.raises(ValueError, match="rendered worker differs"):
        freeze(tmp_path, scratch, src)


def test_a_legacy_replay_campaign_cannot_be_built_smoked_or_frozen(scratch, tmp_path):
    c = json.loads((scratch / REL).read_text())
    c["legacy_replay"] = True
    put(scratch, REL, json.dumps(c, indent=2, sort_keys=True))
    g(scratch, "commit", "-qam", "legacy")
    g(scratch, "push", "-q", "origin", "main")
    for call in (lambda: B.build(scratch / REL, commit(scratch), scratch), lambda: B.smoke(scratch / REL, commit(scratch), repo=scratch),
                 lambda: B.freeze(scratch / REL, commit(scratch), scratch, smoke_table=tmp_path / "x.json")):
        with pytest.raises(ValueError, match="legacy_replay"):
            call()


# ---------------------------------------------------------------- freeze re-validation by the verifier (S5)
@pytest.fixture
def frozen(scratch, monkeypatch, tmp_path):
    src = built(scratch)
    monkeypatch.setattr(B, "kaggle", fake_kaggle())
    target = freeze(tmp_path, scratch, src)
    c, rel, sha = B.load(scratch / REL, scratch)
    return json.loads(target.read_text()), target, c, sha, rel


def revalidate(record, target, c, sha, rel):
    target.write_text(json.dumps(record, sort_keys=True, indent=2) + "\n")
    target.with_name(target.name + ".sha256").write_text(SC.sha256_path(target) + "\n")
    V.validate_freeze(record, target, c, sha, rel)


def test_validate_freeze_does_not_trust_the_all_free_flag(frozen):
    record, target, c, sha, rel = frozen
    revalidate(copy.deepcopy(record), target, c, sha, rel)
    mutations = {
        "bare all_free": (lambda r: r.update(identity_free_check={"all_free": True}), "identity-free check"),
        "other owner": (lambda r: r["identity_free_check"].update(owner="someone"), "identity-free check"),
        "other kernels": (lambda r: r["identity_free_check"].update(kernel_ids=["ramhachi888/other"]), "different kernels"),
        "older than 24 h": (lambda r: r["identity_free_check"].update(captured_utc=(datetime.datetime.fromisoformat(r["frozen_utc"]) - datetime.timedelta(hours=25)).isoformat()), "older than 24 h"),
        "captured after the freeze": (lambda r: r["identity_free_check"].update(captured_utc=(datetime.datetime.fromisoformat(r["frozen_utc"]) + datetime.timedelta(hours=1)).isoformat()), "older than 24 h"),
        "frozen in the future": (lambda r: r.update(frozen_utc=(datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=1)).isoformat()), "future"),
        "listing page command": (lambda r: r["identity_free_check"]["listings"]["kernels"]["pages"][0].update(command=["kaggle", "kernels", "list"]), "page 1 failed"),
        "listing page exit code": (lambda r: r["identity_free_check"]["listings"]["kernels"]["pages"][1].update(exit_code=1), "page 2 failed"),
        "dropped page": (lambda r: r["identity_free_check"]["listings"]["kernels"]["pages"].pop(1), "failed|rows differ"),
        "missing positive control": (lambda r: r["identity_free_check"]["positive_controls"]["kernels"].update(stdout=""), "positive control"),
        "collision rows": (lambda r: r["identity_free_check"]["listings"]["kernels"]["rows"].append({"ref": f"ramhachi888/{SLUG}", "title": "x"}), "rows differ"),
        "campaign path": (lambda r: r.update(campaign_path="docs/harness/other.json"), "campaign path"),
        "legacy flag": (lambda r: r.update(legacy_replay=True), "legacy_replay"),
        "smoke hash": (lambda r: r.pop("smoke_verified_sha256"), "smoke record"),
        "missing pin": (lambda r: r["pins"]["s24"].pop("scripts/step01_states.py"), "do not cover"),
        "missing campaign pin": (lambda r: r["pins"]["s24"].pop(REL), "do not cover"),
        "missing job pin": (lambda r: r["pins"]["s24"].pop(c["kernels"]["s24"]["job"]), "do not cover"),
        "raw pin differs": (lambda r: r["pins"]["s24"].update({c["baseline"]["path"]: "0" * 64}), "differ from the campaign"),
    }
    for label, (mutate, message) in mutations.items():
        bad = copy.deepcopy(record)
        mutate(bad)
        with pytest.raises(ValueError, match=message):
            revalidate(bad, target, c, sha, rel)
        assert label


# ---------------------------------------------------------------- pin closure (S6)
def with_job(repo, text, extra=None, extra_pins=()):
    """Replace the s24 job by `text`, add `extra` files (rel -> text) and kernel pins, commit."""
    c = json.loads((repo / REL).read_text())
    put(repo, c["kernels"]["s24"]["job"], text)
    for rel, body in (extra or {}).items():
        put(repo, rel, body)
    c["kernels"]["s24"]["pins"] = list(extra_pins)
    put(repo, REL, json.dumps(c, indent=2, sort_keys=True))
    g(repo, "add", "-A")
    g(repo, "commit", "-qm", "job")
    return c["kernels"]["s24"]["job"]


def test_a_job_include_must_be_pinned_recursively(scratch):
    job = with_job(scratch, 'include(joinpath(@__DIR__, "helper.jl"))\n')
    with pytest.raises(ValueError, match="scripts/helper.jl, which is not pinned"):
        B.build(scratch / REL, commit(scratch), scratch)
    with_job(scratch, 'include(joinpath(@__DIR__, "helper.jl"))\n', {"scripts/helper.jl": 'include("deep.jl")\n', "scripts/deep.jl": "x = 1\n"}, ["scripts/helper.jl"])
    with pytest.raises(ValueError, match="scripts/deep.jl, which is not pinned"):  # the included file's own includes count
        B.build(scratch / REL, commit(scratch), scratch)
    with_job(scratch, 'Base.include(M,\n    joinpath(@__DIR__, "..", "julia", "CFDSDFWaterLily", "src", "a.jl"))\ninclude(joinpath(@__DIR__, "helper.jl"))\n', extra_pins=["scripts/helper.jl", "scripts/deep.jl"])
    assert B.build(scratch / REL, commit(scratch), scratch)[0].is_dir()  # pinned, and a file under a pinned directory counts as pinned
    assert job.endswith(".jl")


def test_julia_include_forms_and_unresolvable_includes():
    assert B.julia_includes("scripts/j.jl", 'include("x.jl")\ninclude(joinpath(@__DIR__, "..", "julia", "a.jl"))\nBase.include(M, joinpath(@__DIR__, "y.jl")) # include("c.jl")\n') == ["scripts/x.jl", "julia/a.jl", "scripts/y.jl"]
    for bad in ("include(path)", 'include(@__DIR__ * "/x.jl")', 'include("../../../etc/x.jl")'):
        with pytest.raises(ValueError, match="unresolvable|escapes"):
            B.julia_includes("scripts/j.jl", bad)


# ---------------------------------------------------------------- smoke
def test_smoke_renders_under_a_smoke_slug_prints_the_push_command_and_never_pushes(scratch, monkeypatch):
    monkeypatch.setattr(B, "kaggle", lambda a: pytest.fail("smoke must not call kaggle"))
    put(scratch, "docs/note.txt", "local only\n")
    g(scratch, "add", "-A")
    g(scratch, "commit", "-qm", "unpushed")
    with pytest.raises(ValueError, match="not on a remote branch"):
        B.smoke(scratch / REL, commit(scratch), repo=scratch)
    g(scratch, "push", "-q", "origin", "main")
    d, cmd = B.smoke(scratch / REL, commit(scratch), repo=scratch)
    meta = json.loads((d / "kernel-metadata.json").read_text())
    assert d.name == "kernel_grid02_s24_smoke" and meta["id"] == f"ramhachi888/{SLUG}-smoke" and meta["title"] == f"{SLUG}-smoke" and 'SMOKE = True' in (d / "runner.py").read_text()
    assert cmd == ["kaggle", "kernels", "push", "-p", "infra/kaggle/kernel_grid02_s24_smoke", "--accelerator", "NvidiaTeslaT4", "--timeout", "10800"]
    B.assert_pin_only_diff(B.render(scratch / REL, commit(scratch), "s24", False, scratch), (d / "runner.py").read_text())
    with pytest.raises(ValueError, match="refusing to overwrite"):
        B.smoke(scratch / REL, commit(scratch), repo=scratch)


def test_cli_surface_is_exactly_the_four_subcommands_and_fails_closed(capsys):
    with pytest.raises(SystemExit):
        H.main(["status"])
    with pytest.raises(SystemExit) as e:
        H.main(["build", str(T.REPLAY), "--source-commit", "abc"])
    assert e.value.code == 3 and "FAILED (fail closed)" in capsys.readouterr().err
    with pytest.raises(SystemExit) as e:  # the saved GRID-02 kernel dirs exist: the replay campaign can never be built over them
        H.main(["smoke", str(T.REPLAY), "--source-commit", "0" * 40])
    assert e.value.code == 3
