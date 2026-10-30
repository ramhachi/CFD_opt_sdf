"""Register the v8 campaign manifest (cap-stationarity exit, resume at v7 end).

Pre-registers the cap-stationarity level exit separately from the accepted-step
window (per docs/pq3_3b_post_v5_plan_2026_09.md: measure the smallness of the
accepted steps and the absence of a feasible improving direction separately),
carries the cumulative b=8 accepted count forward, and pins the v7 final
checkpoint, the v6/v7 outcomes and the entry-preflight script. Refuses to
overwrite.
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

V7_MANIFEST = ROOT / "docs/evidence/pq3_3b_campaign_manifest_v7_2026_09.json"
V7_OUTCOME = ROOT / "docs/evidence/pq3_3b_campaign_v7_outcome_2026_09.json"
V6_OUTCOME = ROOT / "docs/evidence/pq3_3b_campaign_v6_outcome_2026_09.json"
D2_MANIFEST = ROOT / "docs/evidence/pq3_3b_d2_change_manifest_2026_09.json"
D1_OUTCOME = ROOT / "docs/evidence/pq3_3b_d1_discriminant_outcome_2026_09.json"
PREFLIGHT_SCRIPT = ROOT / "scripts/pq3_3b_v8_entry_preflight_2026_09.py"
MANIFEST = ROOT / "docs/evidence/pq3_3b_campaign_manifest_v8_2026_09.json"
V7_CAMPAIGN = ROOT / "work/pq3_3b_campaign_v7"


def _v7_final_rho() -> tuple[Path, dict]:
    pointer = ca.load_json(V7_CAMPAIGN / "latest.json")
    state = ca.load_json(V7_CAMPAIGN / pointer["state_path"])
    rho_path = V7_CAMPAIGN / state["rho_path"]
    rho = np.load(rho_path, allow_pickle=False)
    if sha256_array(rho) != state["rho_sha256"]:
        raise SystemExit("v7 final rho hash mismatch")
    return rho_path, state


def build() -> dict:
    v7 = ca.load_json(V7_MANIFEST)
    v6_outcome = ca.load_json(V6_OUTCOME)
    v7_outcome = ca.load_json(V7_OUTCOME)
    v6_steps = list(v6_outcome["level_records"].values())[0]["accepted_steps"]
    v7_steps = list(v7_outcome["level_records"].values())[0]["accepted_steps"]
    rho_path, state = _v7_final_rho()
    level_name = v7["input_stop_state"]["level"]
    v7_last_metric = list(v7_outcome["level_records"].values())[0]["last_metrics"][-1]
    return {
        "kind": "pq3_3b_campaign_manifest_v8",
        "schema_version": 7,
        "immutable": True,
        "status": "registered_preflight_pending",
        "plan": v7["plan"],
        "previous_registrations": {
            "manifest_v7": {"path": str(V7_MANIFEST.relative_to(ROOT)), "sha256": ca.sha256_file(V7_MANIFEST)},
            "campaign_v7_outcome": {"path": str(V7_OUTCOME.relative_to(ROOT)), "sha256": ca.sha256_file(V7_OUTCOME)},
        },
        "pinned_evidence": {
            "campaign_v7_outcome": {"path": str(V7_OUTCOME.relative_to(ROOT)), "sha256": ca.sha256_file(V7_OUTCOME)},
            "campaign_v6_outcome": {"path": str(V6_OUTCOME.relative_to(ROOT)), "sha256": ca.sha256_file(V6_OUTCOME)},
            "manifest_v7": {"path": str(V7_MANIFEST.relative_to(ROOT)), "sha256": ca.sha256_file(V7_MANIFEST)},
            "change_manifest_d2": {"path": str(D2_MANIFEST.relative_to(ROOT)), "sha256": ca.sha256_file(D2_MANIFEST)},
            "discriminant_outcome_d1": {"path": str(D1_OUTCOME.relative_to(ROOT)), "sha256": ca.sha256_file(D1_OUTCOME)},
        },
        "change": {
            "id": "cap-stationarity-exit",
            "description": (
                "pre-registered level exit measured separately from the convergence window: an attempt "
                "where every alpha is rejected as machine-scale or cap-unreachable, the last accepted "
                "objective delta is within the window bound, the cumulative accepted count meets the "
                "floor, and an independent fresh primal reproduces the parent response within tolerance"
            ),
            "does_not_relax": [
                "the 1e-4 accepted-step window bound is reused unchanged",
                "the 1e-6 improvement thresholds and Path B rules are unchanged",
                "the exit is recorded as cap_stationarity_exit, never as convergence",
            ],
            "evidence": {
                "v6_b8_accepted_steps": v6_steps,
                "v7_b8_accepted_steps": v7_steps,
                "v7_last_accepted_objective_delta_abs": 5.012135999971079e-05,
                "v7_stopping_attempt": 28,
                "v7_stopping_reasons": ["machine_scale_update_rejected"],
            },
        },
        "accepted_count_carryover": {level_name: int(v6_steps) + int(v7_steps)},
        "carryover_last_metric": v7_last_metric,
        "cap_stationarity_exit": {
            "enabled": True,
            "all_candidates_rejected_as": ["machine_scale_update_rejected", "volume_cap_unreachable"],
            "last_accepted_objective_delta_max": 1e-4,
            "reproducibility_tolerance": 1e-6,
            "independent_repeat": True,
            "min_accepted_iterations": "cumulative accepted count for the level including the registered carryover",
            "does_not_claim_convergence": True,
        },
        "input_stop_state": {
            "level": level_name,
            "source": "v7 final accepted checkpoint",
            "checkpoint_index": state["checkpoint_index"],
            "rho_path": str(rho_path.relative_to(ROOT)),
            "rho_file_sha256": ca.sha256_file(rho_path),
            "rho_sha256": state["rho_sha256"],
        },
        "registered_inputs": v7["registered_inputs"],
        "openfoam_image": v7["openfoam_image"],
        "openfoam_image_id": v7["openfoam_image_id"],
        "objective": v7["objective"],
        "phase1_policy": v7["phase1_policy"],
        "phase2_policy": v7["phase2_policy"],
        "filter_radius_m": v7["filter_radius_m"],
        "projection_eta": v7["projection_eta"],
        "registered_target": v7["registered_target"],
        "v_max_projected": v7["v_max_projected"],
        "volume_tolerance": v7["volume_tolerance"],
        "levels": v7["levels"],
        "path_b": v7["path_b"],
        "noise_thresholds": v7["noise_thresholds"],
        "convergence": v7["convergence"],
        "reject_stop_count": v7["reject_stop_count"],
        "restoration_step_cap": v7["restoration_step_cap"],
        "resume_rule": v7["resume_rule"],
        "terminal_rule": (
            "b16 exits by the registered window or the cap-stationarity exit with at least ten cumulative "
            "accepted steps; then an independent repeat primal on the final rho with only the original "
            "projected V<=Vmax gate before any Stage S assessment"
        ),
        "output_directory": "work/pq3_3b_campaign_v8",
        "entry_preflight": {
            "script_path": str(PREFLIGHT_SCRIPT.relative_to(ROOT)),
            "script_sha256": ca.sha256_file(PREFLIGHT_SCRIPT),
            "artifact_path": "docs/evidence/pq3_3b_v8_entry_preflight_2026_09.json",
            "requirement": "must pass before the v8 campaign",
        },
        "source_tree_python_sha256": ca.python_source_tree_sha256(ROOT / "src/cfd_sdf"),
        "claims_not_supported": [
            "the exit is a registered stopping rule, not a convergence or stationarity certificate",
            "no terminal evaluation and no Stage S readiness in this registration",
        ],
    }


def main() -> None:
    if MANIFEST.exists():
        raise SystemExit("v8 manifest already exists")
    manifest = build()
    MANIFEST.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    MANIFEST.with_suffix(".json.sha256").write_text(ca.sha256_file(MANIFEST) + "\n", encoding="utf-8")
    print(json.dumps({"sha256": ca.sha256_file(MANIFEST), "carryover": manifest["accepted_count_carryover"]}))


if __name__ == "__main__":
    main()
