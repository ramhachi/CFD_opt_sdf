"""The evidence-manifest gate: every SHA256SUMS entry exists, hashes correctly and is tracked by git (not ignored)."""
import hashlib
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import check_sha256sums_tracked as G  # noqa: E402


def git(root, *args):
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


def test_gate_reports_missing_mismatched_untracked_and_ignored_entries(tmp_path):
    git(tmp_path, "init", "-q"); git(tmp_path, "config", "user.email", "t@t"); git(tmp_path, "config", "user.name", "t")
    (tmp_path / ".gitignore").write_text("*.log\n")
    for name, body in (("ok.txt", "a"), ("changed.txt", "b"), ("untracked.txt", "c"), ("ignored.log", "d")):
        (tmp_path / name).write_text(body)
    git(tmp_path, "add", ".gitignore", "ok.txt", "changed.txt"); git(tmp_path, "commit", "-qm", "x")
    h = lambda s: hashlib.sha256(s.encode()).hexdigest()
    lines = [f"{h('a')}  ok.txt", f"{h('WRONG')}  changed.txt", f"{h('c')}  untracked.txt", f"{h('d')}  ignored.log", f"{h('e')}  missing.txt", f"{h('z')}  living.md"]
    m = tmp_path / "SHA256SUMS"; m.write_text("\n".join(lines) + "\n")
    problems = G.check(m, tmp_path, excepted=("living.md",))
    assert "hash mismatch: changed.txt" in problems and "not tracked by git (ignored or uncommitted): untracked.txt" in problems
    assert "not tracked by git (ignored or uncommitted): ignored.log" in problems and "missing: missing.txt" in problems
    assert not any("ok.txt" in x or "living.md" in x for x in problems)
    m.write_text(f"{h('a')}  ok.txt\n")
    assert G.check(m, tmp_path) == []
    sub = tmp_path / "sub"; sub.mkdir(); (sub / "a.txt").write_text("a"); (sub / "b.log").write_text("d")
    git(tmp_path, "add", "sub/a.txt"); git(tmp_path, "commit", "-qm", "y")
    ms = sub / "SHA256SUMS"; ms.write_text(f"{h('a')}  ./a.txt\n{h('d')}  ./b.log\n{h('a')}  ./gone.txt\n")  # the older './name' form is relative to the manifest directory
    assert G.check(ms, tmp_path) == ["not tracked by git (ignored or uncommitted): ./b.log", "missing: ./gone.txt", "not tracked by git (ignored or uncommitted): ./gone.txt"]
    ms.write_text(f"{h('a')}  ../etc\n")
    import pytest
    with pytest.raises(ValueError):
        G.check(ms, tmp_path)
