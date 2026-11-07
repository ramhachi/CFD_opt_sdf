"""Authenticate Claude's committed GRAD-00 reference against real FD-08 bytes."""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from scripts import analyze_grad00 as A

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = Path("docs/evidence/grad00_lambda_2026_11/reference.json")


def test_load_reference_accepts_committed_fd08_reference():
    reference = A.load_reference(ROOT / REFERENCE)
    assert set(reference["directions"]) == set(A.DIRECTIONS)
    assert len(reference["sources"]) == 2


def test_committed_reference_matches_generator_recomputation():
    checked = subprocess.run(
        [sys.executable, str(ROOT / "scripts/grad00_reference_from_fd08.py"), "--check"],
        cwd=ROOT, capture_output=True, text=True,
    )
    assert checked.returncode == 0, checked.stdout + checked.stderr


@pytest.mark.parametrize("source_name", ["formal_analysis.json", "formal_criteria.json"])
def test_one_byte_source_change_rejects_reference(tmp_path, source_name):
    reference = A.load_reference(ROOT / REFERENCE)
    for name in (*reference["sources"], str(REFERENCE)):
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, target)
    assert A.load_reference(tmp_path / REFERENCE, repo_root=tmp_path) == reference
    source = next(tmp_path / name for name in reference["sources"] if Path(name).name == source_name)
    original = source.read_bytes()
    changed = bytes([original[0] ^ 1]) + original[1:]
    assert sum(a != b for a, b in zip(original, changed)) == 1
    source.write_bytes(changed)
    with pytest.raises(ValueError, match="reference source SHA mismatch"):
        A.load_reference(tmp_path / REFERENCE, repo_root=tmp_path)


def test_reference_uses_one_positive_epsilon_within_five_mm_for_all_directions():
    reference = A.load_reference(ROOT / REFERENCE)
    epsilon = [reference["directions"][name]["epsilon_m"] for name in A.DIRECTIONS]
    assert len(epsilon) == 4 and len(set(epsilon)) == 1
    assert all(0 < value <= 0.005 for value in epsilon)
