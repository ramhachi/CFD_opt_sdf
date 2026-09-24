"""Contract tests for the v16 continuation registration (no OpenFOAM runs).

Assertions check the immutable manifest, its sidecar, the pinned v15
checkpoint-10 start state, the registered carryover, the enabled
cap-stationarity exit and the attempt budget.
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
from scripts.pq3_3b_preflight_v6_2026_09 import sha256_array  # noqa: E402

MANIFEST = ROOT / "docs/evidence/pq3_3b_campaign_manifest_v16_2026_09.json"
V15_OUTCOME = ROOT / "docs/evidence/pq3_3b_campaign_v15_outcome_2026_09.json"
V15_CAMPAIGN = ROOT / "work/pq3_3b_campaign_v15"
LEVEL_NAME = "level_3_b128_margin"


def _manifest() -> dict:
    return json.loads(MANIFEST.read_text())


def test_manifest_and_sidecar_are_consistent():
    manifest = _manifest()
    assert manifest["kind"] == "pq3_3b_campaign_manifest_v16"
    assert manifest["immutable"] is True
    assert manifest["status"] == "registered_preflight_pending"
    sidecar = MANIFEST.with_suffix(".json.sha256").read_text().strip()
    assert sidecar == ca.sha256_file(MANIFEST)


def test_start_state_is_the_recorded_v15_checkpoint_10_unchanged():
    manifest = _manifest()
    outcome = json.loads(V15_OUTCOME.read_text())
    checkpoint = outcome["checkpoint"]
    stop = manifest["input_stop_state"]
    assert stop["level"] == LEVEL_NAME
    assert stop["state_path"] == f"work/pq3_3b_campaign_v15/{checkpoint['state_path']}"
    assert stop["state_sha256"] == checkpoint["state_sha256"]
    assert stop["rho_file_sha256"] == checkpoint["rho_file_sha256"]
    assert stop["rho_sha256"] == checkpoint["rho_sha256"]
    assert ca.sha256_file(ROOT / stop["state_path"]) == stop["state_sha256"]
    assert ca.sha256_file(ROOT / stop["rho_path"]) == stop["rho_file_sha256"]
    rho = np.load(ROOT / stop["rho_path"], allow_pickle=False)
    assert sha256_array(np.asarray(rho, dtype=np.float64)) == stop["rho_sha256"]
    assert "bootstrap" not in manifest
    assert "bootstrap_provenance" not in manifest


def test_carryover_matches_the_v15_stop_state():
    manifest = _manifest()
    outcome = json.loads(V15_OUTCOME.read_text())
    assert manifest["accepted_count_carryover"] == {LEVEL_NAME: 10}
    assert manifest["accepted_count_carryover"][LEVEL_NAME] == outcome["checkpoint"]["accepted_count"]
    last_metrics = list(outcome["level_records"][LEVEL_NAME]["last_metrics"])
    assert manifest["carryover_metrics"] == last_metrics
    assert manifest["convergence"]["window_reset"] is False
    assert manifest["convergence"]["window_accepted"] == 3
    assert manifest["convergence"]["objective_delta_abs_max"] == 1e-4


def test_cap_stationarity_exit_is_enabled_for_the_projected_policy_reasons():
    manifest = _manifest()
    exit_rule = manifest["cap_stationarity_exit"]
    assert exit_rule["enabled"] is True
    assert exit_rule["independent_repeat"] is True
    assert set(exit_rule["all_candidates_rejected_as"]) == {
        "machine_scale_update_rejected",
        "projected_volume_limit_exceeded",
    }
    assert exit_rule["last_accepted_objective_delta_max"] == 1e-4
    assert exit_rule["reproducibility_tolerance"] == 1e-6


def test_attempt_budget_and_min_accepted_iterations_are_registered():
    manifest = _manifest()
    level = next(level for level in manifest["levels"] if level["name"] == LEVEL_NAME)
    assert level["max_attempts"] == 90
    assert level["min_accepted_iterations"] == 10
    assert level["b"] == 128.0 and level["q"] == 100.0
    assert manifest["reject_stop_count"] == 1
    assert "independent repeat primal" in manifest["terminal_rule"]


def test_thresholds_and_inputs_are_inherited_from_v15_unmodified():
    manifest = _manifest()
    v15 = json.loads(
        (ROOT / "docs/evidence/pq3_3b_campaign_manifest_v15_2026_09.json").read_text()
    )
    assert manifest["registered_inputs"] == v15["registered_inputs"]
    assert manifest["phase2_policy"] == v15["phase2_policy"]
    assert manifest["path_b"] == v15["path_b"]
    assert manifest["noise_thresholds"] == v15["noise_thresholds"]
    assert manifest["v_max_projected"] == v15["v_max_projected"]
    assert manifest["volume_tolerance"] == v15["volume_tolerance"]
    assert manifest["openfoam_image"] == v15["openfoam_image"]
    assert manifest["openfoam_image_id"] == v15["openfoam_image_id"]
    assert manifest["output_directory"] == "work/pq3_3b_campaign_v16"


def test_pinned_evidence_and_source_tree_pin_are_recorded():
    manifest = _manifest()
    for key, ref in manifest["pinned_evidence"].items():
        assert ca.sha256_file(ROOT / ref["path"]) == ref["sha256"], key
    pin = manifest["source_tree_python_sha256"]
    assert isinstance(pin, str) and len(pin) == 64
    assert ca.sha256_file(ROOT / manifest["entry_preflight"]["script_path"]) == manifest["entry_preflight"]["script_sha256"]
