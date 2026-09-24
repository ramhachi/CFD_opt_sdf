"""Runner+manifest contract tests for the uncommitted v15 registration.

No OpenFOAM runs. Assertions check the immutable manifest, its sidecar, the
deterministic bootstrap against the pinned v14 checkpoint, the preserved
thresholds, and the runner-facing bounded learning budget contract.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from cfd_sdf import campaign_assertions as ca  # noqa: E402
from scripts.pq3_3b_campaign_v6_2026_09 import (  # noqa: E402
    support_allowed_cells_from_manifest,
)
import scripts.pq3_3b_campaign_v6_2026_09 as campaign  # noqa: E402
import scripts.pq3_3b_v15_register_2026_09 as register_v15  # noqa: E402

MANIFEST = ROOT / "docs/evidence/pq3_3b_campaign_manifest_v15_2026_09.json"
BOOTSTRAP = ROOT / "work/pq3_3b_campaign_v15_bootstrap.npy"


def _manifest() -> dict:
    return json.loads(MANIFEST.read_text())


def test_manifest_and_sidecar_are_consistent():
    manifest = _manifest()
    assert manifest["immutable"] is True
    assert manifest["status"] == "registered_preflight_pending"
    sidecar = MANIFEST.with_suffix(".json.sha256").read_text().strip()
    assert sidecar == ca.sha256_file(MANIFEST)


def test_v15_is_a_bounded_fresh_learning_campaign_without_v14_carryover():
    manifest = _manifest()
    learning = manifest["learning_campaign"]
    # the trimmed bootstrap is a transformed state: the v14 accepted count and
    # convergence metrics are provenance only and are not carried forward
    assert "accepted_count_carryover" not in manifest
    assert "carryover_metrics" not in manifest
    assert "carryover_last_metric" not in manifest
    assert manifest["convergence"]["window_reset"] is True
    for key in ("max_fresh_attempts", "max_new_accepted_attempts"):
        value = learning[key]
        assert isinstance(value, int) and not isinstance(value, bool) and value > 0
        assert value <= 10
    assert learning["does_not_claim_convergence"] is True
    assert learning["stop_status"] == "paused_learning_budget"
    assert learning["unrestricted_campaign"] is False
    level = next(l for l in manifest["levels"] if l["name"] == manifest["input_stop_state"]["level"])
    # runner behavior: the runner pauses inside the level's attempt loop when
    # either learning budget is reached, so a larger max_attempts would be an
    # unbounded path
    assert level["max_attempts"] == learning["max_fresh_attempts"] <= 10
    assert "paused_learning_budget" in manifest["terminal_rule"]
    assert "learning budget" in manifest["resume_rule"]
    assert manifest["cap_stationarity_exit"]["enabled"] is False


def test_v15_preserves_the_registered_thresholds():
    manifest = _manifest()
    assert manifest["phase2_policy"]["discreteness_mean_nd_max"] == 0.01
    assert manifest["v_max_projected"] == 0.07632566813424899
    assert manifest["phase2_policy"]["volume_cap_correction"] is False
    assert manifest["phase2_policy"]["response_level_ladder"] is True
    assert manifest["phase2_policy"]["support_box"] == {
        "x": [-0.675, 1.675],
        "y": [-0.475, 0.475],
        "z": [-0.275, 0.275],
    }
    assert manifest["noise_thresholds"] == {"downforce": 1e-06, "objective": 1e-06}
    assert manifest["phase2_policy"]["min_corrected_update_inf_norm"] == 1e-08
    assert "does_not_relax" in manifest["change"]
    assert all(
        "discreteness bound" in item or "volume cap" in item
        for item in manifest["change"]["does_not_relax"][:1]
    )


def test_v15_running_contract_declares_ladder_backtracking():
    manifest = _manifest()
    assert manifest["plan"]["response_backtracking"] is True
    assert manifest["plan"]["first_transform_feasible_only"] is False
    action = manifest["plan"]["response_failure_action"]
    assert "only after Path B passes and the trial response gates fail" in action
    assert "a Path B failure stops the attempt fail-closed" in action
    assert "transform-infeasible alphas never consume solver calls" in action


def test_v15_declares_the_per_attempt_solver_budget():
    manifest = _manifest()
    budget = manifest["solver_budget"]
    ladder = manifest["phase2_policy"]["alpha_ladder"]
    assert budget["scope"] == "per fresh attempt"
    assert budget["parent_adjoint_requests_max"] == 1
    assert budget["transform_feasible_alphas_max"] == len(ladder) == 5
    assert budget["path_b_primal_requests_per_tried_alpha"] == 2
    assert budget["trial_primal_requests_per_tried_alpha"] == 1
    assert budget["evaluator_requests_max_per_attempt"] == 1 + len(ladder) * 3 == 16
    assert budget["transform_infeasible_alpha_evaluator_requests"] == 0
    assert "request bounds" in budget["semantics"]
    assert "freshness is recorded separately" in budget["semantics"]


def test_v15_bootstrap_is_deterministic_from_the_pinned_v14_checkpoint():
    manifest = _manifest()
    provenance = manifest["bootstrap_provenance"]
    source = provenance["v14_checkpoint"]
    source_path = ROOT / source["rho_path"]
    assert ca.sha256_file(source_path) == source["rho_file_sha256"]
    source_array = np.asarray(np.load(source_path, allow_pickle=False), dtype=np.float64)
    assert register_v15.sha256_array(source_array) == source["rho_sha256"]
    state_path = ROOT / source["state_path"]
    assert ca.sha256_file(state_path) == source["state_sha256"]
    state = json.loads(state_path.read_text())
    assert state["accepted_count"] == source["accepted_count_v14_cumulative"]
    assert source["not_carried_into_v15"] is True
    # reproduce the registered trim rule independently and compare the pinned file
    allowed = support_allowed_cells_from_manifest(manifest)
    expected = np.where(allowed, source_array.ravel(order="F"), 0.0)
    bootstrap = np.asarray(np.load(BOOTSTRAP, allow_pickle=False), dtype=np.float64).ravel(order="F")
    assert np.array_equal(bootstrap, expected)
    assert ca.sha256_file(BOOTSTRAP) == manifest["input_stop_state"]["rho_file_sha256"]
    assert register_v15.sha256_array(bootstrap) == manifest["input_stop_state"]["rho_sha256"]
    recorded = provenance["bootstrap"]
    assert recorded["rho_file_sha256"] == manifest["input_stop_state"]["rho_file_sha256"]
    assert recorded["overwrite_refused"] is True
    assert recorded["generated_by"].endswith("pq3_3b_v15_register_2026_09.py")
    assert recorded["projected_volume_measured"] <= manifest["v_max_projected"]
    assert recorded["mean_nd_measured"] <= manifest["phase2_policy"]["discreteness_mean_nd_max"]
    assert recorded["support_violations_measured"] == 0


def test_v15_entry_preflight_is_registered_and_verifiable():
    manifest = _manifest()
    entry = manifest["entry_preflight"]
    assert entry["script_path"].endswith("pq3_3b_v15_entry_preflight_2026_09.py")
    assert ca.sha256_file(ROOT / entry["script_path"]) == entry["script_sha256"]
    assert "must pass before the v15 campaign" in entry["requirement"]


def test_pinned_evidence_and_margin_mask_hashes_verify():
    manifest = _manifest()
    for key, ref in manifest["pinned_evidence"].items():
        assert ca.sha256_file(ROOT / ref["path"]) == ref["sha256"]
    assert ca.sha256_file(ROOT / manifest["margin_mask"]["state"]) == manifest["margin_mask"]["state_sha256"]


def test_source_tree_pin_is_historical_after_the_recorded_budget_stop():
    manifest = _manifest()
    outcome = json.loads(
        (ROOT / "docs/evidence/pq3_3b_campaign_v15_outcome_2026_09.json").read_text()
    )
    # the learning budget is exhausted and recorded, so the campaign cannot
    # resume and the live-tree equality is no longer required; the runtime
    # runner still refuses any resume whose live tree differs from this pin
    # (scripts/pq3_3b_campaign_v6_2026_09.py)
    assert outcome["status"]["status"] == "paused_learning_budget"
    assert (
        outcome["checkpoint"]["accepted_count"]
        >= manifest["learning_campaign"]["max_new_accepted_attempts"]
    )
    pin = manifest["source_tree_python_sha256"]
    assert isinstance(pin, str) and len(pin) == 64


def test_registered_inputs_are_inherited_from_v14_unmodified():
    manifest = _manifest()
    v14 = json.loads(
        (ROOT / "docs/evidence/pq3_3b_campaign_manifest_v14_2026_09.json").read_text()
    )
    assert manifest["registered_inputs"] == v14["registered_inputs"]
    assert manifest["openfoam_image"] == v14["openfoam_image"]
    assert manifest["openfoam_image_id"] == v14["openfoam_image_id"]
    assert manifest["output_directory"] == "work/pq3_3b_campaign_v15"


def test_projected_dispatch_passes_support_cells_and_ladder_through(monkeypatch):
    captured = {}

    def fake_policy(**kwargs):
        captured.update(kwargs)
        return {}

    monkeypatch.setattr(campaign, "evaluate_phase2_discreteness_direction", fake_policy)
    manifest = {
        "phase2_policy": {
            "id": campaign.PROJECTED_DIRECTION_POLICY_ID,
            "volume_cap_correction": False,
            "alpha_ladder": [1.0, 0.5],
            "min_corrected_update_inf_norm": 1e-08,
            "extractability_fraction": 0.5,
            "discreteness_mean_nd_max": 0.01,
            "freeze_exact_box_faces": True,
            "support_box": register_v15.SUPPORT_BOX,
        }
    }
    cells = np.array([True, False])
    campaign.evaluate_registered_phase2(
        manifest=manifest, marker=1, support_allowed_cells=cells
    )
    assert captured["support_allowed_cells"] is not None
    assert captured["ladder"] == (1.0, 0.5)
    assert captured["discreteness_mean_nd_max"] == 0.01
