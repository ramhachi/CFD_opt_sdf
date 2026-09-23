"""Focused tests for campaign outcome checkpoint and optional-field recording."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from scripts.pq3_3b_campaign_v4_2026_09 import _checkpoint
from scripts.pq3_3b_record_v6_outcome_2026_09 import (
    _candidate_record,
    _final_rho_and_state,
)


def test_final_rho_verifies_the_entire_checkpoint_chain(tmp_path: Path) -> None:
    initial = np.array([0.1, 0.2], dtype=np.float64)
    accepted = np.array([0.15, 0.2], dtype=np.float64)
    _checkpoint(tmp_path, {"checkpoint_index": 0, "level_index": 0}, initial)
    _checkpoint(tmp_path, {"checkpoint_index": 1, "level_index": 0}, accepted)

    rho, state = _final_rho_and_state(tmp_path)
    np.testing.assert_array_equal(rho, accepted)
    assert state["checkpoint_index"] == 1

    first_rho = tmp_path / "checkpoints/rho_0000.npy"
    first_rho.write_bytes(first_rho.read_bytes() + b"tampered")
    with pytest.raises(ValueError, match="rho file SHA-256"):
        _final_rho_and_state(tmp_path)


def test_candidate_record_preserves_optional_discreteness_fields() -> None:
    candidate = {
        "alpha": 0.0625,
        "phi_after": 0.0687,
        "corrected_update_inf_norm": 0.000625,
        "volume_cap_correction_applied": False,
        "volume_cap_kappa": None,
        "reason": "discreteness_limit_exceeded",
        "discreteness_field": "rho_projection",
        "discreteness_scope": "transform.active",
        "discreteness_mean_nd_parent": 0.0097,
        "discreteness_mean_nd_candidate": 0.0104,
        "discreteness_mean_nd_max": 0.01,
        "gates": {"projected_discreteness_within_limit": False},
    }

    record = _candidate_record(candidate, v_max=0.0763)

    assert record["discreteness_mean_nd_parent"] == 0.0097
    assert record["discreteness_mean_nd_candidate"] == 0.0104
    assert record["discreteness_mean_nd_max"] == 0.01
    assert record["projected_discreteness_within_limit"] is False
    assert record["projected_volume_within_v_max"] is True
