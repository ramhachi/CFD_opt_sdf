"""Register the v9 campaign manifest (b=16 attempt-budget extension, resume at v8).

Resumes the b=16 level from the v8 final checkpoint with the registered policy
unchanged; only the b=16 attempt budget is extended to 150 so the registered
convergence window (or the cap-stationarity exit) can be reached. Pins the v8
outcome/manifest, the prior evidence and the v9 entry-preflight script.
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

V8_MANIFEST = ROOT / "docs/evidence/pq3_3b_campaign_manifest_v8_2026_09.json"
V8_OUTCOME = ROOT / "docs/evidence/pq3_3b_campaign_v8_outcome_2026_09.json"
V7_OUTCOME = ROOT / "docs/evidence/pq3_3b_campaign_v7_outcome_2026_09.json"
V6_OUTCOME = ROOT / "docs/evidence/pq3_3b_campaign_v6_outcome_2026_09.json"
D2_MANIFEST = ROOT / "docs/evidence/pq3_3b_d2_change_manifest_2026_09.json"
D1_OUTCOME = ROOT / "docs/evidence/pq3_3b_d1_discriminant_outcome_2026_09.json"
PREFLIGHT_SCRIPT = ROOT / "scripts/pq3_3b_v9_entry_preflight_2026_09.py"
MANIFEST = ROOT / "docs/evidence/pq3_3b_campaign_manifest_v9_2026_09.json"
V8_CAMPAIGN = ROOT / "work/pq3_3b_campaign_v8"


def _v8_final_rho() -> tuple[Path, dict]:
    pointer = ca.load_json(V8_CAMPAIGN / "latest.json")
    state = ca.load_json(V8_CAMPAIGN / pointer["state_path"])
    rho_path = V8_CAMPAIGN / state["rho_path"]
    rho = np.load(rho_path, allow_pickle=False)
    if sha256_array(rho) != state["rho_sha256"]:
        raise SystemExit("v8 final rho hash mismatch")
    return rho_path, state


def build() -> dict:
    v8 = ca.load_json(V8_MANIFEST)
    v8_outcome = ca.load_json(V8_OUTCOME)
    v8_record = list(v8_outcome["level_records"].values())[0]
    level_name = "level_2_b16_q100"
    rho_path, state = _v8_final_rho()
    levels = []
    for level in v8["levels"]:
        if level["name"] == level_name:
            levels.append({**level, "max_attempts": 150})
        else:
            levels.append(level)
    return {
        "kind": "pq3_3b_campaign_manifest_v9",
        "schema_version": 8,
        "immutable": True,
        "status": "registered_preflight_pending",
        "plan": v8["plan"],
        "previous_registrations": {
            "manifest_v8": {"path": str(V8_MANIFEST.relative_to(ROOT)), "sha256": ca.sha256_file(V8_MANIFEST)},
            "campaign_v8_outcome": {"path": str(V8_OUTCOME.relative_to(ROOT)), "sha256": ca.sha256_file(V8_OUTCOME)},
        },
        "pinned_evidence": {
            "campaign_v8_outcome": {"path": str(V8_OUTCOME.relative_to(ROOT)), "sha256": ca.sha256_file(V8_OUTCOME)},
            "manifest_v8": {"path": str(V8_MANIFEST.relative_to(ROOT)), "sha256": ca.sha256_file(V8_MANIFEST)},
            "campaign_v7_outcome": {"path": str(V7_OUTCOME.relative_to(ROOT)), "sha256": ca.sha256_file(V7_OUTCOME)},
            "campaign_v6_outcome": {"path": str(V6_OUTCOME.relative_to(ROOT)), "sha256": ca.sha256_file(V6_OUTCOME)},
            "change_manifest_d2": {"path": str(D2_MANIFEST.relative_to(ROOT)), "sha256": ca.sha256_file(D2_MANIFEST)},
            "discriminant_outcome_d1": {"path": str(D1_OUTCOME.relative_to(ROOT)), "sha256": ca.sha256_file(D1_OUTCOME)},
        },
        "change": {
            "id": "b16-attempt-budget-extension",
            "description": (
                "the b=16 attempt budget is extended from 30 to 150; the policy, the convergence window, "
                "the thresholds, the cap-stationarity exit and the terminal rule are unchanged"
            ),
            "does_not_relax": [
                "the 1e-4 objective window bound and the 1e-3 field/volume bounds",
                "the 1e-6 improvement thresholds, Path B rules and the 1e-8 machine-scale gate",
            ],
            "evidence": {
                "v8_b16_accepted_steps": v8_record["accepted_steps"],
                "v8_b16_last_objective_delta_abs": v8_record["last_metrics"][-1]["objective_delta_abs"],
                "v8_stop_reason": v8_outcome["status"]["reason"],
            },
        },
        "accepted_count_carryover": {level_name: int(v8_record["accepted_steps"])},
        "carryover_last_metric": v8_record["last_metrics"][-1],
        "cap_stationarity_exit": v8["cap_stationarity_exit"],
        "input_stop_state": {
            "level": level_name,
            "source": "v8 final accepted checkpoint",
            "checkpoint_index": state["checkpoint_index"],
            "rho_path": str(rho_path.relative_to(ROOT)),
            "rho_file_sha256": ca.sha256_file(rho_path),
            "rho_sha256": state["rho_sha256"],
        },
        "registered_inputs": v8["registered_inputs"],
        "openfoam_image": v8["openfoam_image"],
        "openfoam_image_id": v8["openfoam_image_id"],
        "objective": v8["objective"],
        "phase1_policy": v8["phase1_policy"],
        "phase2_policy": v8["phase2_policy"],
        "filter_radius_m": v8["filter_radius_m"],
        "projection_eta": v8["projection_eta"],
        "registered_target": v8["registered_target"],
        "v_max_projected": v8["v_max_projected"],
        "volume_tolerance": v8["volume_tolerance"],
        "levels": levels,
        "path_b": v8["path_b"],
        "noise_thresholds": v8["noise_thresholds"],
        "convergence": v8["convergence"],
        "reject_stop_count": v8["reject_stop_count"],
        "restoration_step_cap": v8["restoration_step_cap"],
        "resume_rule": v8["resume_rule"],
        "terminal_rule": v8["terminal_rule"],
        "output_directory": "work/pq3_3b_campaign_v9",
        "entry_preflight": {
            "script_path": str(PREFLIGHT_SCRIPT.relative_to(ROOT)),
            "script_sha256": ca.sha256_file(PREFLIGHT_SCRIPT),
            "artifact_path": "docs/evidence/pq3_3b_v9_entry_preflight_2026_09.json",
            "requirement": "must pass before the v9 campaign",
        },
        "source_tree_python_sha256": ca.python_source_tree_sha256(ROOT / "src/cfd_sdf"),
        "claims_not_supported": [
            "the budget extension is not a convergence claim",
            "no terminal evaluation and no Stage S readiness in this registration",
        ],
    }


def main() -> None:
    if MANIFEST.exists():
        raise SystemExit("v9 manifest already exists")
    manifest = build()
    MANIFEST.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    MANIFEST.with_suffix(".json.sha256").write_text(ca.sha256_file(MANIFEST) + "\n", encoding="utf-8")
    print(json.dumps({"sha256": ca.sha256_file(MANIFEST), "carryover": manifest["accepted_count_carryover"]}))


if __name__ == "__main__":
    main()
