"""Register the v11 campaign manifest: b=128 attempt-budget extension (150 -> 300).

Resumes the single registered b=128 level from the v10 final checkpoint with
the policy, thresholds and exit rules unchanged; only the attempt budget is
extended because the v10 outcome measured the accepted-step deltas trending
toward the window (last three 1.79e-4 / 1.19e-4 / 1.18e-4 against the 1e-4
bound) when the budget ran out.
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
V9_OUTCOME = ROOT / "docs/evidence/pq3_3b_campaign_v9_outcome_2026_09.json"
PQ41_V2 = ROOT / "docs/evidence/pq4_1_terminal_stage_s_entry_v2_2026_09.json"
D2_MANIFEST = ROOT / "docs/evidence/pq3_3b_d2_change_manifest_2026_09.json"
D1_OUTCOME = ROOT / "docs/evidence/pq3_3b_d1_discriminant_outcome_2026_09.json"
PREFLIGHT_SCRIPT = ROOT / "scripts/pq3_3b_v11_entry_preflight_2026_09.py"
MANIFEST = ROOT / "docs/evidence/pq3_3b_campaign_manifest_v11_2026_09.json"
BOOTSTRAP = ROOT / "work/pq3_3b_campaign_v11_bootstrap.npy"
LEVEL_NAME = "level_3_b128_margin"


def build() -> dict:
    v10 = ca.load_json(V10_MANIFEST)
    v10_outcome = ca.load_json(V10_OUTCOME)
    record = list(v10_outcome["level_records"].values())[0]
    rho = np.load(BOOTSTRAP, allow_pickle=False)
    levels = []
    for level in v10["levels"]:
        if level["name"] == LEVEL_NAME:
            levels.append({**level, "max_attempts": 300})
        else:
            levels.append(level)
    return {
        "kind": "pq3_3b_campaign_manifest_v11",
        "schema_version": 10,
        "immutable": True,
        "status": "registered_preflight_pending",
        "plan": v10["plan"],
        "previous_registrations": {
            "manifest_v10": {"path": str(V10_MANIFEST.relative_to(ROOT)), "sha256": ca.sha256_file(V10_MANIFEST)},
            "campaign_v10_outcome": {"path": str(V10_OUTCOME.relative_to(ROOT)), "sha256": ca.sha256_file(V10_OUTCOME)},
        },
        "pinned_evidence": {
            "campaign_v10_outcome": {"path": str(V10_OUTCOME.relative_to(ROOT)), "sha256": ca.sha256_file(V10_OUTCOME)},
            "campaign_v9_outcome": {"path": str(V9_OUTCOME.relative_to(ROOT)), "sha256": ca.sha256_file(V9_OUTCOME)},
            "pq4_1_verdict_v2": {"path": str(PQ41_V2.relative_to(ROOT)), "sha256": ca.sha256_file(PQ41_V2)},
            "manifest_v10": {"path": str(V10_MANIFEST.relative_to(ROOT)), "sha256": ca.sha256_file(V10_MANIFEST)},
            "change_manifest_d2": {"path": str(D2_MANIFEST.relative_to(ROOT)), "sha256": ca.sha256_file(D2_MANIFEST)},
            "discriminant_outcome_d1": {"path": str(D1_OUTCOME.relative_to(ROOT)), "sha256": ca.sha256_file(D1_OUTCOME)},
        },
        "change": {
            "id": "b128-attempt-budget-extension",
            "description": "the b=128 attempt budget is extended from 150 to 300; everything else is unchanged",
            "does_not_relax": [
                "the 1e-4 objective window bound, the 1e-3 field/volume bounds and every threshold",
            ],
            "evidence": {
                "v10_accepted_steps": record["accepted_steps"],
                "v10_last_objective_deltas": [m["objective_delta_abs"] for m in record["last_metrics"]],
                "v10_stop_reason": v10_outcome["status"]["reason"],
            },
        },
        "accepted_count_carryover": {LEVEL_NAME: int(record["accepted_steps"])},
        "carryover_last_metric": record["last_metrics"][-1],
        "cap_stationarity_exit": v10["cap_stationarity_exit"],
        "input_stop_state": {
            "level": LEVEL_NAME,
            "source": "v10 final accepted checkpoint",
            "rho_path": str(BOOTSTRAP.relative_to(ROOT)),
            "rho_file_sha256": ca.sha256_file(BOOTSTRAP),
            "rho_sha256": sha256_array(rho),
        },
        "registered_inputs": v10["registered_inputs"],
        "margin_mask": v10["margin_mask"],
        "openfoam_image": v10["openfoam_image"],
        "openfoam_image_id": v10["openfoam_image_id"],
        "objective": v10["objective"],
        "phase1_policy": v10["phase1_policy"],
        "phase2_policy": v10["phase2_policy"],
        "filter_radius_m": v10["filter_radius_m"],
        "projection_eta": v10["projection_eta"],
        "registered_target": v10["registered_target"],
        "v_max_projected": v10["v_max_projected"],
        "volume_tolerance": v10["volume_tolerance"],
        "levels": levels,
        "path_b": v10["path_b"],
        "noise_thresholds": v10["noise_thresholds"],
        "convergence": v10["convergence"],
        "reject_stop_count": v10["reject_stop_count"],
        "restoration_step_cap": v10["restoration_step_cap"],
        "resume_rule": v10["resume_rule"],
        "terminal_rule": v10["terminal_rule"],
        "output_directory": "work/pq3_3b_campaign_v11",
        "entry_preflight": {
            "script_path": str(PREFLIGHT_SCRIPT.relative_to(ROOT)),
            "script_sha256": ca.sha256_file(PREFLIGHT_SCRIPT),
            "artifact_path": "docs/evidence/pq3_3b_v11_entry_preflight_2026_09.json",
            "requirement": "must pass before the v11 campaign",
        },
        "source_tree_python_sha256": ca.python_source_tree_sha256(ROOT / "src/cfd_sdf"),
        "claims_not_supported": [
            "the budget extension is not a convergence claim",
            "no terminal evaluation and no Stage S readiness in this registration",
        ],
    }


def main() -> None:
    if MANIFEST.exists():
        raise SystemExit("v11 manifest already exists")
    manifest = build()
    MANIFEST.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    MANIFEST.with_suffix(".json.sha256").write_text(ca.sha256_file(MANIFEST) + "\n", encoding="utf-8")
    print(json.dumps({"sha256": ca.sha256_file(MANIFEST), "carryover": manifest["accepted_count_carryover"]}))


if __name__ == "__main__":
    main()
