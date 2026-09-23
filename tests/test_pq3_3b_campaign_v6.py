"""Tests for the v6 campaign runner convergence window (no OpenFOAM)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from scripts.pq3_3b_campaign_v6_2026_09 import level_converged  # noqa: E402

LIMITS = {
    "window_accepted": 3,
    "objective_delta_abs_max": 1e-4,
    "projected_field_mean_abs_delta_max": 1e-3,
    "projected_volume_delta_abs_max": 1e-3,
}
GOOD = {
    "objective_delta_abs": 5e-5,
    "projected_field_mean_abs_delta": 1e-5,
    "projected_volume_delta_abs": 1e-5,
}
BAD_OBJECTIVE = {**GOOD, "objective_delta_abs": 2e-4}
BAD_FIELD = {**GOOD, "projected_field_mean_abs_delta": 2e-3}
BAD_VOLUME = {**GOOD, "projected_volume_delta_abs": 2e-3}
ZERO_DELTA = {**GOOD, "objective_delta_abs": 0.0}


def test_convergence_requires_min_accepted_and_full_window():
    assert level_converged(accepted_count=10, window=[GOOD] * 3, limits=LIMITS, min_accepted=10) is True
    assert level_converged(accepted_count=9, window=[GOOD] * 3, limits=LIMITS, min_accepted=10) is False
    assert level_converged(accepted_count=10, window=[GOOD] * 2, limits=LIMITS, min_accepted=10) is False


def test_convergence_rejects_window_failures():
    assert level_converged(accepted_count=10, window=[GOOD, BAD_OBJECTIVE, GOOD], limits=LIMITS, min_accepted=10) is False
    assert level_converged(accepted_count=10, window=[GOOD, BAD_FIELD, GOOD], limits=LIMITS, min_accepted=10) is False
    assert level_converged(accepted_count=10, window=[GOOD, BAD_VOLUME, GOOD], limits=LIMITS, min_accepted=10) is False
    assert level_converged(accepted_count=10, window=[GOOD, ZERO_DELTA, GOOD], limits=LIMITS, min_accepted=10) is False
