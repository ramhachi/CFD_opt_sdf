"""Tests for the v6 campaign runner convergence window (no OpenFOAM)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from scripts.pq3_3b_campaign_v6_2026_09 import (  # noqa: E402
    cap_stationarity_exit_allowed,
    level_converged,
    parent_discreteness_guard,
)
import scripts.pq3_3b_campaign_v6_2026_09 as campaign  # noqa: E402

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


def test_cap_stationarity_exit_requires_separate_criteria():
    reasons = {"machine_scale_update_rejected", "volume_cap_unreachable"}
    allowed = {
        "all_rejected_as": reasons,
        "last_metric": {"objective_delta_abs": 5e-5},
        "last_metric_limit": 1e-4,
        "accepted_count": 36,
        "min_accepted": 10,
    }
    assert cap_stationarity_exit_allowed(enabled=True, reasons=reasons, **allowed) is True
    # a feasible-direction rejection reason disqualifies the exit
    assert cap_stationarity_exit_allowed(
        enabled=True, reasons={"gates_failed"}, **allowed
    ) is False
    # a large last accepted delta disqualifies the exit
    assert cap_stationarity_exit_allowed(
        enabled=True, reasons=reasons, **{**allowed, "last_metric": {"objective_delta_abs": 2e-4}}
    ) is False
    # the min-accepted floor is enforced separately
    assert cap_stationarity_exit_allowed(
        enabled=True, reasons=reasons, **{**allowed, "accepted_count": 9}
    ) is False
    # disabled means disabled
    assert cap_stationarity_exit_allowed(enabled=False, reasons=reasons, **allowed) is False


def test_parent_discreteness_guard_is_optional_and_fail_closed():
    class _Projection:
        def __init__(self, values):
            self.rho_projected = values

    class _Transform:
        active = [True, True]

        def forward(self, _rho):
            return _Projection(np.array([0.5, 0.5]))

    transform = _Transform()
    rho = np.zeros(2)
    assert parent_discreteness_guard(transform, rho, None) == {
        "enabled": False,
        "mean_nd": None,
        "mean_nd_max": None,
        "pass": True,
    }
    guarded = parent_discreteness_guard(transform, rho, 0.01)
    assert guarded["mean_nd"] == 1.0
    assert guarded["pass"] is False


def test_v12_replays_checkpoint_five_with_the_discreteness_gate():
    manifest = json.loads(
        (ROOT / "docs/evidence/pq3_3b_campaign_manifest_v12_2026_09.json").read_text()
    )
    level = manifest["input_stop_state"]["level"]
    assert manifest["schema_version"] == 11
    assert manifest["input_stop_state"]["rho_path"].endswith("checkpoints/rho_0005.npy")
    assert manifest["accepted_count_carryover"][level] == 5
    assert len(manifest["carryover_metrics"]) == 3
    assert manifest["phase2_policy"]["discreteness_mean_nd_max"] == 0.01
    assert manifest["output_directory"] == "work/pq3_3b_campaign_v12"


def test_phase2_dispatch_preserves_inequality_and_selects_projected_direction(monkeypatch):
    calls = []

    def old_policy(**kwargs):
        calls.append(("old", kwargs))
        return "old"

    def projected_policy(**kwargs):
        calls.append(("projected", kwargs))
        return "projected"

    monkeypatch.setattr(campaign, "evaluate_phase2_inequality", old_policy)
    monkeypatch.setattr(
        campaign, "evaluate_phase2_discreteness_direction", projected_policy
    )
    base = {
        "alpha_ladder": [1.0, 0.5],
        "min_corrected_update_inf_norm": 1e-8,
        "extractability_fraction": 0.5,
        "discreteness_mean_nd_max": 0.01,
        "freeze_exact_box_faces": True,
    }
    old_manifest = {
        "phase2_policy": {
            **base,
            "id": campaign.DISCRETENESS_POLICY_ID,
            "volume_cap_correction": True,
        }
    }
    projected_manifest = {
        "phase2_policy": {
            **base,
            "id": campaign.PROJECTED_DIRECTION_POLICY_ID,
            "volume_cap_correction": False,
        }
    }

    assert campaign.evaluate_registered_phase2(manifest=old_manifest, marker=1) == "old"
    assert calls[-1][1]["volume_cap_correction"] is True
    assert campaign.evaluate_registered_phase2(
        manifest=projected_manifest, marker=2
    ) == "projected"
    assert "volume_cap_correction" not in calls[-1][1]
    assert calls[-1][1]["ladder"] == (1.0, 0.5)

    projected_manifest["phase2_policy"]["volume_cap_correction"] = True
    with pytest.raises(ValueError, match="does not permit volume correction"):
        campaign.evaluate_registered_phase2(manifest=projected_manifest, marker=3)


def test_v14_is_a_bounded_nonconvergence_learning_campaign():
    manifest = json.loads(
        (ROOT / "docs/evidence/pq3_3b_campaign_manifest_v14_2026_09.json").read_text()
    )
    level = manifest["input_stop_state"]["level"]

    assert manifest["schema_version"] == 12
    assert manifest["input_stop_state"]["rho_path"].endswith(
        "pq3_3b_campaign_v12/checkpoints/rho_0001.npy"
    )
    assert manifest["accepted_count_carryover"][level] == 6
    assert manifest["phase2_policy"]["id"] == campaign.PROJECTED_DIRECTION_POLICY_ID
    assert manifest["phase2_policy"]["volume_cap_correction"] is False
    assert manifest["phase2_policy"]["discreteness_mean_nd_max"] == 0.01
    assert manifest["v_max_projected"] == 0.07632566813424899
    assert manifest["learning_campaign"]["max_fresh_attempts"] == 10
    assert manifest["learning_campaign"]["max_new_accepted_attempts"] == 10
    assert manifest["learning_campaign"]["does_not_claim_convergence"] is True
    assert manifest["plan"]["response_backtracking"] is False
    assert manifest["output_directory"] == "work/pq3_3b_campaign_v14"
