"""Campaign preparation tests; these never start OpenFOAM."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]


def _runner():
    spec = importlib.util.spec_from_file_location(
        "pq3_3b_campaign_v4", ROOT / "scripts/pq3_3b_campaign_v4_2026_09.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_checkpoint_resume_verifies_entire_accepted_rho_chain(tmp_path):
    runner = _runner()
    initial = np.array([0.1, 0.2, 0.3], dtype=np.float64)
    runner._checkpoint(tmp_path, {
        "checkpoint_index": 0, "level_index": 0, "accepted_count": 0,
    }, initial)
    accepted = np.array([0.15, 0.2, 0.3], dtype=np.float64)
    runner._checkpoint(tmp_path, {
        "checkpoint_index": 1, "level_index": 0, "accepted_count": 1,
    }, accepted)
    state, rho = runner._load_checkpoint(tmp_path)
    assert state["checkpoint_index"] == 1
    np.testing.assert_array_equal(rho, accepted)
    with pytest.raises(ValueError, match="already exists"):
        runner._checkpoint(tmp_path, {"checkpoint_index": 1}, accepted)

    first_file = tmp_path / "checkpoints/rho_0000.npy"
    first_file.write_bytes(first_file.read_bytes() + b"tampered")
    with pytest.raises(ValueError, match="rho file SHA-256"):
        runner._load_checkpoint(tmp_path)


def test_bad_manifest_hash_cannot_create_output(tmp_path, monkeypatch):
    runner = _runner()
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"status": "unknown"}), encoding="utf-8")
    monkeypatch.setattr(runner, "MANIFEST", manifest)
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        runner.verify_preconditions("0" * 64)
    assert list(tmp_path.iterdir()) == [manifest]
