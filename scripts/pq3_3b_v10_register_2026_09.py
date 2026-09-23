"""Register the v10 campaign manifest: clearance margin mask + b=128 sharpening.

Two measured causes from the corrected PQ4.1 verdict are addressed
structurally: the 1.35 cm side-clearance shortfall is removed by restricting
the allowed mask to |y_center| <= 0.475 (surface reach <= 0.50 m, clearance
>= 0.30 m against the 0.25 m profile), and the discreteness failure is
addressed by the measured b-sweep (terminal rho mean_nd: 0.109 at b=16,
0.032 at b=32, 0.0119 at b=64, 0.00612 at b=128 against the 0.01 bound). The
campaign resumes from the trimmed terminal rho at the single registered
b=128 level with the policy, thresholds and cap-stationarity exit unchanged.
Refuses to overwrite.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

from cfd_sdf import campaign_assertions as ca  # noqa: E402
from scripts.pq3_3b_preflight_v6_2026_09 import sha256_array  # noqa: E402

V9_MANIFEST = ROOT / "docs/evidence/pq3_3b_campaign_manifest_v9_2026_09.json"
V9_OUTCOME = ROOT / "docs/evidence/pq3_3b_campaign_v9_outcome_2026_09.json"
PQ41_V2 = ROOT / "docs/evidence/pq4_1_terminal_stage_s_entry_v2_2026_09.json"
D2_MANIFEST = ROOT / "docs/evidence/pq3_3b_d2_change_manifest_2026_09.json"
D1_OUTCOME = ROOT / "docs/evidence/pq3_3b_d1_discriminant_outcome_2026_09.json"
PREFLIGHT_SCRIPT = ROOT / "scripts/pq3_3b_v10_entry_preflight_2026_09.py"
MANIFEST = ROOT / "docs/evidence/pq3_3b_campaign_manifest_v10_2026_09.json"
BOOTSTRAP = ROOT / "work/pq3_3b_campaign_v10_bootstrap.npy"
MARGIN_STATE = ROOT / "work/pq3_3b_margin_masks/topology_state.json"
MARGIN_VTI = ROOT / "work/pq3_3b_margin_masks/density.vti"
LEVEL_NAME = "level_3_b128_margin"


def build() -> dict:
    v9 = ca.load_json(V9_MANIFEST)
    rho = np.load(BOOTSTRAP, allow_pickle=False)
    level = {
        "name": LEVEL_NAME,
        "b": 128.0,
        "q": 100.0,
        "move_limit": 0.01,
        "min_accepted_iterations": 10,
        "max_attempts": 150,
    }
    return {
        "kind": "pq3_3b_campaign_manifest_v10",
        "schema_version": 9,
        "immutable": True,
        "status": "registered_preflight_pending",
        "plan": v9["plan"],
        "previous_registrations": {
            "manifest_v9": {"path": str(V9_MANIFEST.relative_to(ROOT)), "sha256": ca.sha256_file(V9_MANIFEST)},
            "campaign_v9_outcome": {"path": str(V9_OUTCOME.relative_to(ROOT)), "sha256": ca.sha256_file(V9_OUTCOME)},
        },
        "pinned_evidence": {
            "campaign_v9_outcome": {"path": str(V9_OUTCOME.relative_to(ROOT)), "sha256": ca.sha256_file(V9_OUTCOME)},
            "pq4_1_verdict_v2": {"path": str(PQ41_V2.relative_to(ROOT)), "sha256": ca.sha256_file(PQ41_V2)},
            "manifest_v9": {"path": str(V9_MANIFEST.relative_to(ROOT)), "sha256": ca.sha256_file(V9_MANIFEST)},
            "change_manifest_d2": {"path": str(D2_MANIFEST.relative_to(ROOT)), "sha256": ca.sha256_file(D2_MANIFEST)},
            "discriminant_outcome_d1": {"path": str(D1_OUTCOME.relative_to(ROOT)), "sha256": ca.sha256_file(D1_OUTCOME)},
        },
        "change": {
            "id": "clearance-margin-mask+b128-sharpening",
            "description": (
                "the canonical allowed mask is restricted to |y_center| <= 0.475 so the extracted "
                "surface stays >= 0.30 m from the side bounds (the PQ4.1 v2 verdict measured 0.2365 m "
                "against the 0.25 m profile); the continuation level is b=128 because the measured "
                "mean_nd on the terminal rho crosses the 0.01 bound only at higher sharpness"
            ),
            "does_not_relax": [
                "the clearance profile margin 0.25 m, the discreteness bound 0.01 and the volume cap",
                "the policy, the thresholds, the cap-stationarity exit and the terminal rule",
            ],
            "evidence": {
                "pq4_1_v2_clearance_m": {"sideMin": 0.23653261661529545, "sideMax": 0.23975591659545903},
                "mean_nd_sweep_terminal_rho": {"b16": 0.10903, "b32": 0.03215, "b64": 0.01188, "b128": 0.00612},
                "bootstrap_mean_nd_b128": 0.00580,
                "margin_excluded_active_cells": 4800,
                "active_cells_after_margin": 14400,
            },
        },
        "accepted_count_carryover": {LEVEL_NAME: 0},
        "cap_stationarity_exit": v9["cap_stationarity_exit"],
        "input_stop_state": {
            "level": LEVEL_NAME,
            "source": "v9 terminal rho trimmed to the margin mask",
            "rho_path": str(BOOTSTRAP.relative_to(ROOT)),
            "rho_file_sha256": ca.sha256_file(BOOTSTRAP),
            "rho_sha256": sha256_array(rho),
        },
        "registered_inputs": {
            **v9["registered_inputs"],
            "canonical_grid": {
                "path": str(MARGIN_STATE.relative_to(ROOT)),
                "sha256": ca.sha256_file(MARGIN_STATE),
            },
        },
        "margin_mask": {
            "state": str(MARGIN_STATE.relative_to(ROOT)),
            "state_sha256": ca.sha256_file(MARGIN_STATE),
            "density_vti": str(MARGIN_VTI.relative_to(ROOT)),
            "density_vti_sha256": ca.sha256_file(MARGIN_VTI),
            "rule": "allowed_mask = original allowed_mask AND |y_center| <= 0.475",
            "surface_reach_bound_m": 0.50,
            "profile_margin_m": 0.25,
        },
        "openfoam_image": v9["openfoam_image"],
        "openfoam_image_id": v9["openfoam_image_id"],
        "objective": v9["objective"],
        "phase1_policy": v9["phase1_policy"],
        "phase2_policy": v9["phase2_policy"],
        "filter_radius_m": v9["filter_radius_m"],
        "projection_eta": v9["projection_eta"],
        "registered_target": v9["registered_target"],
        "v_max_projected": v9["v_max_projected"],
        "volume_tolerance": v9["volume_tolerance"],
        "levels": [level],
        "path_b": v9["path_b"],
        "noise_thresholds": v9["noise_thresholds"],
        "convergence": v9["convergence"],
        "reject_stop_count": v9["reject_stop_count"],
        "restoration_step_cap": v9["restoration_step_cap"],
        "resume_rule": v9["resume_rule"],
        "terminal_rule": (
            "the b=128 level exits by the registered window or the cap-stationarity exit with at least "
            "ten accepted steps; then an independent repeat primal on the final rho with only the "
            "original projected V<=Vmax gate before the PQ4.1 judgment"
        ),
        "output_directory": "work/pq3_3b_campaign_v10",
        "entry_preflight": {
            "script_path": str(PREFLIGHT_SCRIPT.relative_to(ROOT)),
            "script_sha256": ca.sha256_file(PREFLIGHT_SCRIPT),
            "artifact_path": "docs/evidence/pq3_3b_v10_entry_preflight_2026_09.json",
            "requirement": "must pass before the v10 campaign",
        },
        "source_tree_python_sha256": ca.python_source_tree_sha256(ROOT / "src/cfd_sdf"),
        "claims_not_supported": [
            "the mask and sharpening changes are registered, not yet qualified",
            "no terminal evaluation and no Stage S readiness in this registration",
        ],
    }


def main() -> None:
    if MANIFEST.exists():
        raise SystemExit("v10 manifest already exists")
    manifest = build()
    MANIFEST.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    MANIFEST.with_suffix(".json.sha256").write_text(ca.sha256_file(MANIFEST) + "\n", encoding="utf-8")
    print(json.dumps({"sha256": ca.sha256_file(MANIFEST), "level": LEVEL_NAME}))


if __name__ == "__main__":
    main()
