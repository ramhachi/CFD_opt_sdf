"""Register the v16 campaign manifest: b=128 continuation from v15 checkpoint 10.

The start state is the recorded v15 final accepted checkpoint (checkpoint 10 of
the paused learning budget) used unchanged. v15 stopped at its registered
budget while still improving, so v16 continues the same b=128 margin level with
a fresh attempt budget; it carries over the cumulative accepted count and the
last three accepted metrics so the registered convergence window is evaluated
across the v15/v16 boundary, and it enables the cap-stationarity exit and the
independent terminal repeat that v15 explicitly did not evaluate. Refuses to
overwrite the immutable manifest or its sidecar.
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

V15_MANIFEST = ROOT / "docs/evidence/pq3_3b_campaign_manifest_v15_2026_09.json"
V15_OUTCOME = ROOT / "docs/evidence/pq3_3b_campaign_v15_outcome_2026_09.json"
PQ41_V15 = ROOT / "docs/evidence/pq4_1_v15_state_stage_s_entry_2026_09.json"
P20_CORRECTION = ROOT / "docs/evidence/pq4_volume_fidelity_calibration_correction_2026_09.json"
PREFLIGHT_SCRIPT = ROOT / "scripts/pq3_3b_v16_entry_preflight_2026_09.py"
MANIFEST = ROOT / "docs/evidence/pq3_3b_campaign_manifest_v16_2026_09.json"
V15_CAMPAIGN = ROOT / "work/pq3_3b_campaign_v15"
LEVEL_NAME = "level_3_b128_margin"
MAX_ATTEMPTS = 90
MIN_ACCEPTED_ITERATIONS = 10


def _verify_v15_stop_state() -> dict:
    """Confirm the pinned v15 checkpoint hashes before registering the start state."""

    outcome = ca.load_json(V15_OUTCOME)
    checkpoint = outcome["checkpoint"]
    state_path = V15_CAMPAIGN / checkpoint["state_path"]
    if ca.sha256_file(state_path) != checkpoint["state_sha256"]:
        raise SystemExit("v15 checkpoint state hash mismatch")
    state = ca.load_json(state_path)
    rho_path = V15_CAMPAIGN / state["rho_path"]
    if ca.sha256_file(rho_path) != state["rho_file_sha256"]:
        raise SystemExit("v15 checkpoint rho file hash mismatch")
    if sha256_array(np.asarray(np.load(rho_path), dtype=np.float64)) != state["rho_sha256"]:
        raise SystemExit("v15 checkpoint rho array hash mismatch")
    if int(state["accepted_count"]) != int(checkpoint["accepted_count"]):
        raise SystemExit("v15 accepted count disagrees with its outcome")
    if int(checkpoint["index"]) != 10:
        raise SystemExit("v15 checkpoint index is not the registered continuation point")
    return {
        "state_path": str(state_path.relative_to(ROOT)),
        "state_sha256": checkpoint["state_sha256"],
        "rho_path": str(rho_path.relative_to(ROOT)),
        "rho_file_sha256": state["rho_file_sha256"],
        "rho_sha256": state["rho_sha256"],
        "accepted_count": int(state["accepted_count"]),
        "last_metrics": list(state["metrics"]),
    }


def build() -> dict:
    v15 = ca.load_json(V15_MANIFEST)
    stop = _verify_v15_stop_state()
    return {
        "kind": "pq3_3b_campaign_manifest_v16",
        "schema_version": 12,
        "immutable": True,
        "status": "registered_preflight_pending",
        "plan": {
            **v15["plan"],
            "scope": (
                "unrestricted continuation of the b=128 margin level from the "
                "recorded v15 checkpoint 10 (no state transformation)"
            ),
            "result_semantics": (
                "the level exits by the registered convergence window or the "
                "cap-stationarity exit; the terminal record is not a Stage S "
                "qualification and a fresh PQ4.1 judgment is required"
            ),
        },
        "previous_registrations": {
            "manifest_v15": {
                "path": str(V15_MANIFEST.relative_to(ROOT)),
                "sha256": ca.sha256_file(V15_MANIFEST),
            },
            "campaign_v15_outcome": {
                "path": str(V15_OUTCOME.relative_to(ROOT)),
                "sha256": ca.sha256_file(V15_OUTCOME),
            },
            "pq4_1_v15_state": {
                "path": str(PQ41_V15.relative_to(ROOT)),
                "sha256": ca.sha256_file(PQ41_V15),
            },
        },
        "pinned_evidence": {
            "manifest_v15": {
                "path": str(V15_MANIFEST.relative_to(ROOT)),
                "sha256": ca.sha256_file(V15_MANIFEST),
            },
            "campaign_v15_outcome": {
                "path": str(V15_OUTCOME.relative_to(ROOT)),
                "sha256": ca.sha256_file(V15_OUTCOME),
            },
            "pq4_1_v15_state": {
                "path": str(PQ41_V15.relative_to(ROOT)),
                "sha256": ca.sha256_file(PQ41_V15),
            },
            "p20_volume_calibration_correction": {
                "path": str(P20_CORRECTION.relative_to(ROOT)),
                "sha256": ca.sha256_file(P20_CORRECTION),
            },
        },
        "change": {
            "id": "b128-continuation-from-v15-checkpoint-10",
            "description": (
                "the v15 learning campaign stopped at its registered budget while "
                "still improving; v16 continues the same b=128 margin level from the "
                "recorded checkpoint 10 without transforming the state, carries over "
                "the cumulative accepted count and the last three accepted metrics so "
                "the registered convergence window is evaluated, and enables the "
                "cap-stationarity exit and the independent terminal repeat that v15 "
                "explicitly did not evaluate"
            ),
            "does_not_relax": [
                "the 0.25 m clearance profile, the 0.01 discreteness bound, the volume cap and every threshold",
                "the PQ4.1 composite gate requirements",
            ],
            "evidence": {
                "v15_stop_status": "paused_learning_budget",
                "v15_fresh_attempts": 10,
                "v15_accepted_this_campaign": 10,
                "v15_last_objective_deltas_abs": [
                    metric["objective_delta_abs"] for metric in stop["last_metrics"]
                ],
                "v15_projected_volume": 0.06406567400358908,
                "v15_v_max_fraction": 0.8393725933837114,
                "v15_mean_nd": 0.003213044195919047,
                "v15_convergence_window_observed": False,
            },
        },
        "input_stop_state": {
            "level": LEVEL_NAME,
            "source": (
                "recorded v15 final accepted checkpoint (checkpoint 10, "
                "paused_learning_budget); used unchanged"
            ),
            "state_path": stop["state_path"],
            "state_sha256": stop["state_sha256"],
            "rho_path": stop["rho_path"],
            "rho_file_sha256": stop["rho_file_sha256"],
            "rho_sha256": stop["rho_sha256"],
        },
        "accepted_count_carryover": {LEVEL_NAME: stop["accepted_count"]},
        "carryover_metrics": stop["last_metrics"],
        "registered_inputs": v15["registered_inputs"],
        "margin_mask": v15["margin_mask"],
        "openfoam_image": v15["openfoam_image"],
        "openfoam_image_id": v15["openfoam_image_id"],
        "objective": v15["objective"],
        "phase1_policy": v15["phase1_policy"],
        "phase2_policy": v15["phase2_policy"],
        "filter_radius_m": v15["filter_radius_m"],
        "projection_eta": v15["projection_eta"],
        "registered_target": v15["registered_target"],
        "v_max_projected": v15["v_max_projected"],
        "volume_tolerance": v15["volume_tolerance"],
        "levels": [
            {
                **level,
                "max_attempts": MAX_ATTEMPTS,
                "min_accepted_iterations": MIN_ACCEPTED_ITERATIONS,
            }
            if level["name"] == LEVEL_NAME
            else level
            for level in v15["levels"]
        ],
        "path_b": v15["path_b"],
        "noise_thresholds": v15["noise_thresholds"],
        "convergence": {
            **v15["convergence"],
            "window_reset": False,
            "note": (
                "thresholds and the window are unchanged from v15; the last three "
                "v15 accepted metrics are carried over, so the window is evaluated "
                "across the v15/v16 boundary"
            ),
        },
        "cap_stationarity_exit": {
            "id": "cap-stationarity-exit",
            "enabled": True,
            "all_candidates_rejected_as": [
                "machine_scale_update_rejected",
                "projected_volume_limit_exceeded",
            ],
            "last_accepted_objective_delta_max": 0.0001,
            "min_accepted_iterations": (
                "cumulative accepted count for the level including the registered carryover"
            ),
            "reproducibility_tolerance": 1e-06,
            "independent_repeat": True,
            "does_not_claim_convergence": True,
        },
        "reject_stop_count": v15["reject_stop_count"],
        "restoration_step_cap": v15["restoration_step_cap"],
        "resume_rule": (
            "resume only from a verified v16 checkpoint while below the registered "
            "attempt budget"
        ),
        "terminal_rule": (
            "the level exits by the registered convergence window or the "
            "cap-stationarity exit with at least ten cumulative accepted steps; then "
            "an independent repeat primal on the final rho with only the original "
            "projected V<=Vmax gate; the terminal record is not a Stage S "
            "qualification and a fresh PQ4.1 composite judgment on the repaired gate "
            "is required"
        ),
        "output_directory": "work/pq3_3b_campaign_v16",
        "entry_preflight": {
            "script_path": str(PREFLIGHT_SCRIPT.relative_to(ROOT)),
            "script_sha256": ca.sha256_file(PREFLIGHT_SCRIPT),
            "artifact_path": "docs/evidence/pq3_3b_v16_entry_preflight_2026_09.json",
            "requirement": "must pass before the v16 campaign",
        },
        "source_tree_python_sha256": ca.python_source_tree_sha256(ROOT / "src/cfd_sdf"),
        "claims_not_supported": [
            "the continuation is registered, not yet qualified",
            "no convergence, terminal or Stage S readiness claim in this registration",
        ],
    }


def main() -> None:
    if MANIFEST.exists():
        raise SystemExit("v16 manifest already exists; refuse overwrite")
    manifest = build()
    MANIFEST.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    MANIFEST.with_suffix(".json.sha256").write_text(ca.sha256_file(MANIFEST) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "sha256": ca.sha256_file(MANIFEST),
                "input_stop_state": manifest["input_stop_state"],
                "accepted_count_carryover": manifest["accepted_count_carryover"],
                "levels": manifest["levels"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
