"""harness v1 acceptance (f): build / smoke / freeze against a scratch git repository with a local bare remote; the identity-free check paginates; nothing is pushed to Kaggle."""
import csv
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


def fake_kaggle(kernel_rows=250, dataset_rows=3, collide_at=None, collide_title=None, fail_page=None, calls=None):
    def rows(kind, n, page):
        out = []
        for i in range((page - 1) * 100, min(page * 100, n)):
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
def test_freeze_writes_a_verifier_valid_record_with_a_paginated_identity_listing_and_is_write_once(scratch, monkeypatch):
    src = built(scratch)
    calls = []
    monkeypatch.setattr(B, "kaggle", fake_kaggle(calls=calls))
    target = B.freeze(scratch / REL, src, scratch)
    record = json.loads(target.read_text())
    listing = record["identity_free_check"]["listings"]["kernels"]
    assert [len(p["rows"]) for p in listing["pages"]] == [100, 100, 50] and len(listing["rows"]) == 250 and [len(p["rows"]) for p in record["identity_free_check"]["listings"]["datasets"]["pages"]] == [3]
    assert sum(1 for a in calls if a[:2] == ["kernels", "list"]) == 3 and record["identity_free_check"]["all_free"] is True
    c, _, sha = B.load(scratch / REL, scratch)
    V.validate_freeze(record, target, c, sha)  # the verifier accepts exactly what freeze writes
    assert record["source_commit"] == src and record["pins"]["s24"][REL] == sha and record["runtime"]["s24"]["runner_sha256"] == SC.sha256_path(B.kernel_dir(c, "s24", False, scratch) / "runner.py")
    with pytest.raises(ValueError, match="refusing to overwrite"):
        B.freeze(scratch / REL, src, scratch)


@pytest.mark.parametrize("kw", [{"collide_at": 220}, {"collide_title": 230}, {"collide_at": 5}])
def test_freeze_detects_a_slug_collision_on_any_listing_page(scratch, monkeypatch, kw):
    src = built(scratch)
    monkeypatch.setattr(B, "kaggle", fake_kaggle(**kw))
    with pytest.raises(ValueError, match="identity collision"):
        B.freeze(scratch / REL, src, scratch)
    assert not B.freeze_path(scratch / REL).exists()


def test_freeze_fails_closed_when_a_listing_page_is_forbidden_or_the_pagination_never_ends(scratch, monkeypatch):
    src = built(scratch)
    monkeypatch.setattr(B, "kaggle", fake_kaggle(fail_page=2))
    with pytest.raises(ValueError, match="authenticated listing failed"):
        B.freeze(scratch / REL, src, scratch)
    monkeypatch.setattr(B, "kaggle", fake_kaggle(kernel_rows=100 * 101))
    with pytest.raises(ValueError, match="pagination limit"):
        B.freeze(scratch / REL, src, scratch)


def test_freeze_refuses_a_dirty_tracked_tree(scratch, monkeypatch):
    src = built(scratch)
    monkeypatch.setattr(B, "kaggle", fake_kaggle())
    put(scratch, "scripts/grid01_gpu.py", "edited, not committed\n")
    with pytest.raises(ValueError, match="uncommitted changes"):
        B.freeze(scratch / REL, src, scratch)
    g(scratch, "checkout", "scripts/grid01_gpu.py")
    put(scratch, "untracked_note.txt", "untracked files do not block\n")
    assert B.freeze(scratch / REL, src, scratch).is_file()


def test_freeze_refuses_a_commit_that_is_not_on_a_remote_head_and_an_offline_remote(scratch, monkeypatch):
    src = built(scratch)
    monkeypatch.setattr(B, "kaggle", fake_kaggle())
    put(scratch, "docs/note.txt", "new local commit\n")
    g(scratch, "add", "-A")
    g(scratch, "commit", "-qm", "unpushed")
    unpushed = commit(scratch)
    with pytest.raises(ValueError, match="not on a remote branch"):
        B.freeze(scratch / REL, unpushed, scratch)
    g(scratch, "push", "-q", "origin", "main")
    assert B.freeze(scratch / REL, src, scratch).is_file()  # an ancestor of a pushed head is reachable
    g(scratch, "remote", "set-url", "origin", str(scratch / "gone.git"))
    B.freeze_path(scratch / REL).unlink()
    B.freeze_path(scratch / REL).with_name("mini.prerun_freeze.json.sha256").unlink()
    with pytest.raises(ValueError, match="cannot fetch origin"):
        B.freeze(scratch / REL, src, scratch)


def test_freeze_refuses_a_rendered_worker_that_differs_from_the_reviewed_source(scratch, monkeypatch):
    src = built(scratch)
    monkeypatch.setattr(B, "kaggle", fake_kaggle())
    runner = scratch / "infra/kaggle/kernel_grid02_s24/runner.py"
    runner.write_text(runner.read_text() + "# edited by hand\n")
    with pytest.raises(ValueError, match="rendered worker differs"):
        B.freeze(scratch / REL, src, scratch)


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
