"""Register v12: replay the last valid discrete b=128 checkpoint with an in-loop gate.

The v11 terminal field met its numerical convergence window but later failed
the Stage S discreteness gate.  V12 therefore restarts from the last v10
checkpoint within the bound, whose b=128 projected field was within the same
``mean(4 rho (1-rho)) <= 0.01`` bound, and applies that bound to every Phase 2
candidate before it can be accepted.  Refuses to overwrite existing evidence.
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

V10_MANIFEST = ROOT / "docs/evidence/pq3_3b_campaign_manifest_v10_2026_09.json"
V10_OUTCOME = ROOT / "docs/evidence/pq3_3b_campaign_v10_outcome_2026_09.json"
V11_MANIFEST = ROOT / "docs/evidence/pq3_3b_campaign_manifest_v11_2026_09.json"
V11_OUTCOME = ROOT / "docs/evidence/pq3_3b_campaign_v11_outcome_2026_09.json"
PQ41_V3 = ROOT / "docs/evidence/pq4_1_terminal_stage_s_entry_v3_2026_09.json"
PREFLIGHT_SCRIPT = ROOT / "scripts/pq3_3b_v12_entry_preflight_2026_09.py"
MANIFEST = ROOT / "docs/evidence/pq3_3b_campaign_manifest_v12_2026_09.json"
CHECKPOINT_STATE = ROOT / "work/pq3_3b_campaign_v10/checkpoints/state_0005.json"
CHECKPOINT_RHO = ROOT / "work/pq3_3b_campaign_v10/checkpoints/rho_0005.npy"
LEVEL_NAME = "level_3_b128_margin"
DISCRETENESS_MEAN_ND_MAX = 0.01


def _ref(path: Path) -> dict:
    return {"path": str(path.relative_to(ROOT)), "sha256": ca.sha256_file(path)}


def build() -> dict:
    v10 = ca.load_json(V10_MANIFEST)
    v11 = ca.load_json(V11_MANIFEST)
    checkpoint = ca.load_json(CHECKPOINT_STATE)
    rho = np.load(CHECKPOINT_RHO, allow_pickle=False)
    if checkpoint.get("checkpoint_index") != 5 or checkpoint.get("accepted_count") != 5:
        raise ValueError("v10 checkpoint 5 lineage mismatch")
    if checkpoint.get("rho_file_sha256") != ca.sha256_file(CHECKPOINT_RHO):
        raise ValueError("v10 checkpoint 5 file hash mismatch")
    if checkpoint.get("rho_sha256") != sha256_array(rho):
        raise ValueError("v10 checkpoint 5 array hash mismatch")
    level = next(level for level in v11["levels"] if level["name"] == LEVEL_NAME)
    return {
        "kind": "pq3_3b_campaign_manifest_v12",
        "schema_version": 11,
        "immutable": True,
        "status": "registered_preflight_pending",
        "plan": v11["plan"],
        "previous_registrations": {
            "manifest_v10": _ref(V10_MANIFEST),
            "manifest_v11": _ref(V11_MANIFEST),
        },
        "pinned_evidence": {
            "manifest_v10": _ref(V10_MANIFEST),
            "campaign_v10_outcome": _ref(V10_OUTCOME),
            "manifest_v11": _ref(V11_MANIFEST),
            "campaign_v11_outcome": _ref(V11_OUTCOME),
            "pq4_1_verdict_v3": _ref(PQ41_V3),
        },
        "change": {
            "id": "projected-discreteness-acceptance-gate",
            "description": (
                "replay b=128 from v10 checkpoint 5 and reject every Phase 2 "
                "candidate whose rho_projection over active cells has mean(4*rho*(1-rho)) > 0.01"
            ),
            "does_not_relax": [
                "the projected-volume cap, response thresholds, extraction guard, convergence window, or clearance mask",
                "the Stage S discreteness limit of 0.01",
            ],
            "evidence": {
                "checkpoint_0005_mean_nd_b128": 0.008562322527443773,
                "v11_terminal_mean_nd_b128": 0.05553531941937787,
                "v11_registered_window_met": True,
                "pq4_1_v3_ready_for_stage_s": False,
            },
        },
        "accepted_count_carryover": {LEVEL_NAME: int(checkpoint["accepted_count"])},
        "carryover_metrics": checkpoint["metrics"],
        "carryover_last_metric": checkpoint["metrics"][-1],
        "cap_stationarity_exit": v10["cap_stationarity_exit"],
        "input_stop_state": {
            "level": LEVEL_NAME,
            "source": "v10 accepted checkpoint 5, the last checkpoint measured within mean_nd <= 0.01",
            "state_path": str(CHECKPOINT_STATE.relative_to(ROOT)),
            "state_sha256": ca.sha256_file(CHECKPOINT_STATE),
            "rho_path": str(CHECKPOINT_RHO.relative_to(ROOT)),
            "rho_file_sha256": ca.sha256_file(CHECKPOINT_RHO),
            "rho_sha256": sha256_array(rho),
        },
        "registered_inputs": v10["registered_inputs"],
        "margin_mask": v10["margin_mask"],
        "openfoam_image": v10["openfoam_image"],
        "openfoam_image_id": v10["openfoam_image_id"],
        "objective": v10["objective"],
        "phase1_policy": v10["phase1_policy"],
        "phase2_policy": {
            **v10["phase2_policy"],
            "id": "objective-oc-inequality-v2",
            "discreteness_field": "rho_projection",
            "discreteness_scope": "active",
            "discreteness_metric": "mean(4*rho*(1-rho))",
            "discreteness_mean_nd_max": DISCRETENESS_MEAN_ND_MAX,
        },
        "filter_radius_m": v10["filter_radius_m"],
        "projection_eta": v10["projection_eta"],
        "registered_target": v10["registered_target"],
        "v_max_projected": v10["v_max_projected"],
        "volume_tolerance": v10["volume_tolerance"],
        "levels": [{**level, "max_attempts": 300}],
        "path_b": v10["path_b"],
        "noise_thresholds": v10["noise_thresholds"],
        "convergence": v10["convergence"],
        "reject_stop_count": v10["reject_stop_count"],
        "restoration_step_cap": v10["restoration_step_cap"],
        "resume_rule": v10["resume_rule"],
        "terminal_rule": (
            "the b=128 level must preserve mean_nd <= 0.01 on every accepted candidate and exit by "
            "the registered convergence window or the unchanged cap-stationarity rule; an independent "
            "terminal evaluation still does not establish Stage S readiness"
        ),
        "output_directory": "work/pq3_3b_campaign_v12",
        "entry_preflight": {
            "script_path": str(PREFLIGHT_SCRIPT.relative_to(ROOT)),
            "script_sha256": ca.sha256_file(PREFLIGHT_SCRIPT),
            "artifact_path": "docs/evidence/pq3_3b_v12_entry_preflight_2026_09.json",
            "requirement": "one fresh b=128 step must pass every v12 gate before the long campaign",
        },
        "source_tree_python_sha256": ca.python_source_tree_sha256(ROOT / "src/cfd_sdf"),
        "claims_not_supported": [
            "registration does not show that a feasible improving candidate exists under the new gate",
            "registration does not start the long campaign or qualify Stage S",
            "registration is not grid-independent or target-physics evidence",
        ],
    }


def main() -> None:
    if MANIFEST.exists() or MANIFEST.with_suffix(".json.sha256").exists():
        raise SystemExit("v12 manifest already exists")
    manifest = build()
    MANIFEST.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    MANIFEST.with_suffix(".json.sha256").write_text(ca.sha256_file(MANIFEST) + "\n", encoding="utf-8")
    print(json.dumps({"sha256": ca.sha256_file(MANIFEST), "level": LEVEL_NAME}))


if __name__ == "__main__":
    main()
