"""Deterministic runtime-identity and resume-compatibility contracts."""

from __future__ import annotations

import pytest

from cfd_sdf.runtime.fingerprint import (
    FingerprintError,
    FingerprintMismatch,
    RuntimeFingerprint,
    assert_resume_compatible,
    canonical_json_sha256,
)


def _fingerprint(**overrides) -> RuntimeFingerprint:
    kwargs = {
        "platform": "linux-x86_64",
        "backend": "waterlily",
        "solver_revision": "feed49f480b52047b4e9b8bfacdf3e4f8201106b",
        "precision": "float32",
        "grid_identity": {"origin": [0.0, 0.0, 0.0], "spacing": 0.05, "shape": [64, 32, 24]},
        "device": {"gpu": "unknown", "vram_bytes": None},
        "compiler": {"julia": "1.12.6", "enzyme": "pinned"},
    }
    kwargs.update(overrides)
    return RuntimeFingerprint(**kwargs)


def test_fingerprint_is_deterministic_and_key_order_independent():
    first = _fingerprint()
    second = _fingerprint(
        grid_identity={"shape": [64, 32, 24], "spacing": 0.05, "origin": [0.0, 0.0, 0.0]}
    )
    assert first.sha256() == second.sha256()
    assert canonical_json_sha256(first.to_dict()) == first.sha256()


def test_fingerprint_changes_with_backend_solver_precision_or_grid():
    assert _fingerprint().sha256() != _fingerprint(solver_revision="master").sha256()
    assert _fingerprint().sha256() != _fingerprint(precision="float64").sha256()
    assert _fingerprint().sha256() != _fingerprint(device={"gpu": "A100"}).sha256()
    assert _fingerprint().sha256() != _fingerprint(
        grid_identity={"origin": [0.0, 0.0, 0.0], "spacing": 0.025, "shape": [128, 64, 48]}
    ).sha256()


def test_resume_rejects_incompatible_backend_identity():
    registered = _fingerprint()
    assert_resume_compatible(registered, _fingerprint())
    assert_resume_compatible(registered, _fingerprint(device={"gpu": "L4"}), ignored_fields=("device",))
    with pytest.raises(FingerprintMismatch, match="device"):
        assert_resume_compatible(registered, _fingerprint(device={"gpu": "L4"}))
    with pytest.raises(FingerprintMismatch, match="solver_revision"):
        assert_resume_compatible(registered, _fingerprint(solver_revision="master"))
    with pytest.raises(FingerprintError, match="unknown fields"):
        assert_resume_compatible(registered, _fingerprint(), ignored_fields=("nonsense",))


def test_fingerprint_fails_closed_on_invalid_input():
    with pytest.raises(FingerprintError, match="backend"):
        _fingerprint(backend="")
    with pytest.raises(FingerprintError, match="hashable"):
        canonical_json_sha256({"value": float("nan")})
