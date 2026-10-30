"""Register the bounded v14 projected-direction learning campaign."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from cfd_sdf import campaign_assertions as ca  # noqa: E402
from cfd_sdf.phase2_discreteness_direction import POLICY_ID  # noqa: E402
from scripts.pq3_3b_preflight_v6_2026_09 import sha256_array  # noqa: E402

V12_MANIFEST = ROOT / "docs/evidence/pq3_3b_campaign_manifest_v12_2026_09.json"
V12_STATE = ROOT / "work/pq3_3b_campaign_v12/checkpoints/state_0001.json"
V12_RHO = ROOT / "work/pq3_3b_campaign_v12/checkpoints/rho_0001.npy"
V12_OUTCOME = ROOT / "docs/evidence/pq3_3b_campaign_v12_outcome_2026_09.json"
V13_AUDIT = ROOT / "docs/evidence/pq3_3b_v13_direction_audit_2026_09.json"
V13_MANIFEST = ROOT / "docs/evidence/pq3_3b_v13_discriminant_manifest_2026_09.json"
V13_PREFLIGHT = ROOT / "docs/evidence/pq3_3b_v13_entry_preflight_2026_09.json"
V13_PREFLIGHT_SCRIPT = ROOT / "scripts/pq3_3b_v13_entry_preflight_2026_09.py"
RUNNER = ROOT / "scripts/pq3_3b_campaign_v6_2026_09.py"
OUTCOME_RECORDER = ROOT / "scripts/pq3_3b_record_v6_outcome_2026_09.py"
DIRECTION_MODULE = ROOT / "src/cfd_sdf/phase2_discreteness_direction.py"
MANIFEST = ROOT / "docs/evidence/pq3_3b_campaign_manifest_v14_2026_09.json"


def _ref(path: Path) -> dict:
    return {"path": str(path.relative_to(ROOT)), "sha256": ca.sha256_file(path)}


def build() -> dict:
    v12 = ca.load_json(V12_MANIFEST)
    state = ca.load_json(V12_STATE)
    v13_manifest = ca.load_json(V13_MANIFEST)
    v13_preflight = ca.load_json(V13_PREFLIGHT)
    rho = np.load(V12_RHO, allow_pickle=False)
    if state.get("checkpoint_index") != 1 or state.get("accepted_count") != 6:
        raise ValueError("v14 requires v12 checkpoint 1 with accepted_count 6")
    if state.get("rho_sha256") != sha256_array(rho):
        raise ValueError("v12 checkpoint 1 rho lineage mismatch")
    if v13_preflight["summary"].get("entry_preflight_pass") is not True:
        raise ValueError("v13 projected-direction preflight did not pass")
    if v13_preflight["input_stop_state"]["rho_sha256"] != sha256_array(rho):
        raise ValueError("v13 preflight did not use the v12 checkpoint 1 design")
    if v13_manifest["direction_policy"].get("id") != POLICY_ID:
        raise ValueError("v13 policy identity mismatch")
    if v13_preflight["stage"].get("selected_rho_sha256") is None:
        raise ValueError("v13 preflight did not qualify a projected-direction step")
    level = dict(v12["levels"][0])
    level["max_attempts"] = 10
    return {
        "kind": "pq3_3b_campaign_manifest_v14",
        "schema_version": 12,
        "immutable": True,
        "status": "registered_entry_preflight_reused",
        "registration_base_git_head": subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip(),
        "change": {
            "id": "bounded-projected-raw-gradient-learning-campaign",
            "description": (
                "repeat the v13-qualified tangent step from the persisted v12 "
                "checkpoint, recomputing gJ, gD and the free set after every accepted step"
            ),
            "lineage_choice": (
                "start from v12 checkpoint 1 because v13 qualified but did not persist "
                "its candidate array"
            ),
            "does_not_relax": [
                "rho_projection active-cell mean_nd <= 0.01",
                "rho_projection active-cell mean <= Vmax",
                "Path B, response, occupancy, mask, move-box, or primal gates",
            ],
        },
        "plan": {
            "scope": "bounded learning campaign",
            "first_transform_feasible_only": True,
            "response_backtracking": False,
            "response_failure_action": "stop fail-closed; do not try a lower alpha",
            "per_accepted_step": (
                "evaluate a fresh parent/adjoint request, then recompute objective and "
                "discreteness gradients and the free-cell set"
            ),
            "result_semantics": (
                "a bounded stop or observed window is diagnostic and is not convergence"
            ),
        },
        "learning_campaign": {
            "max_fresh_attempts": 10,
            "max_new_accepted_attempts": 10,
            "stop_status": "paused_learning_budget",
            "does_not_claim_convergence": True,
            "unrestricted_campaign": False,
        },
        "pinned_evidence": {
            "campaign_v12_manifest": _ref(V12_MANIFEST),
            "campaign_v12_outcome": _ref(V12_OUTCOME),
            "v13_direction_audit": _ref(V13_AUDIT),
            "v13_discriminant_manifest": _ref(V13_MANIFEST),
            "v13_entry_preflight": _ref(V13_PREFLIGHT),
            "shared_campaign_runner": _ref(RUNNER),
            "shared_outcome_recorder": _ref(OUTCOME_RECORDER),
            "projected_direction_module": _ref(DIRECTION_MODULE),
        },
        "input_stop_state": {
            "source": (
                "v12 accepted checkpoint 1; v13 candidate is deliberately repeated, "
                "not treated as a persisted checkpoint"
            ),
            "level": state.get("level", v12["input_stop_state"]["level"]),
            "state_path": str(V12_STATE.relative_to(ROOT)),
            "state_sha256": ca.sha256_file(V12_STATE),
            "rho_path": str(V12_RHO.relative_to(ROOT)),
            "rho_file_sha256": ca.sha256_file(V12_RHO),
            "rho_sha256": sha256_array(rho),
            "accepted_count": int(state["accepted_count"]),
        },
        "accepted_count_carryover": {
            state.get("level", v12["input_stop_state"]["level"]): int(
                state["accepted_count"]
            )
        },
        "carryover_metrics": list(state["metrics"]),
        "carryover_last_metric": state["metrics"][-1],
        "levels": [level],
        "phase1_policy": v12["phase1_policy"],
        "phase2_policy": {
            "id": POLICY_ID,
            "module": "src/cfd_sdf/phase2_discreteness_direction.py",
            "alpha_ladder": v13_manifest["alpha_ladder"],
            "freeze_exact_box_faces": True,
            "volume_cap_correction": False,
            "discreteness_field": "rho_projection",
            "discreteness_scope": "active",
            "discreteness_metric": "mean(4*rho*(1-rho))",
            "discreteness_mean_nd_max": v13_manifest["gates"][
                "discreteness_mean_nd_max"
            ],
            "min_corrected_update_inf_norm": v13_manifest["gates"][
                "min_corrected_update_inf_norm"
            ],
            "extractability_fraction": v13_manifest["gates"][
                "extractability_fraction"
            ],
            "extractability_thresholds": v13_manifest["gates"][
                "extractability_thresholds"
            ],
            "no_joint_volume_projection": True,
            "stop_when_no_transform_candidate_satisfies_d_and_v": True,
        },
        "entry_preflight": {
            "reuse": "exact v13 preflight at the identical v12 checkpoint 1 parent",
            "script_path": str(V13_PREFLIGHT_SCRIPT.relative_to(ROOT)),
            "script_sha256": ca.sha256_file(V13_PREFLIGHT_SCRIPT),
            "artifact_path": str(V13_PREFLIGHT.relative_to(ROOT)),
            "artifact_sha256": ca.sha256_file(V13_PREFLIGHT),
            "requirement": "v13 first projected-direction step passed transform, Path B, and response gates",
        },
        "output_directory": "work/pq3_3b_campaign_v14",
        "registered_inputs": v12["registered_inputs"],
        "margin_mask": v12["margin_mask"],
        "filter_radius_m": v12["filter_radius_m"],
        "projection_eta": v12["projection_eta"],
        "registered_target": v12["registered_target"],
        "volume_tolerance": v12["volume_tolerance"],
        "v_max_projected": v12["v_max_projected"],
        "restoration_step_cap": v12["restoration_step_cap"],
        "reject_stop_count": 1,
        "path_b": v12["path_b"],
        "noise_thresholds": v12["noise_thresholds"],
        "objective": v12["objective"],
        "convergence": v12["convergence"],
        "cap_stationarity_exit": {"enabled": False},
        "openfoam_image": v12["openfoam_image"],
        "openfoam_image_id": v12["openfoam_image_id"],
        "resume_rule": (
            "resume only from a verified v14 checkpoint while below the immutable "
            "10-attempt learning budget"
        ),
        "terminal_rule": (
            "stop at the learning budget or first failed attempt; do not perform or "
            "claim a converged terminal qualification"
        ),
        "source_tree_python_sha256": ca.python_source_tree_sha256(
            ROOT / "src/cfd_sdf"
        ),
        "claims_not_supported": [
            "the bounded learning campaign does not establish convergence",
            "registration does not start OpenFOAM",
            "v14 does not establish Stage S readiness or a qualified Stage T ranking",
            "the result is not grid-independent or target-physics evidence",
        ],
    }


def main() -> None:
    sidecar = MANIFEST.with_suffix(".json.sha256")
    if MANIFEST.exists() or sidecar.exists():
        raise SystemExit("v14 campaign manifest already exists")
    manifest = build()
    MANIFEST.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    sidecar.write_text(ca.sha256_file(MANIFEST) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "manifest": str(MANIFEST.relative_to(ROOT)),
                "sha256": ca.sha256_file(MANIFEST),
                "policy": manifest["phase2_policy"]["id"],
                "max_fresh_attempts": manifest["learning_campaign"][
                    "max_fresh_attempts"
                ],
                "openfoam_started": False,
            }
        )
    )


if __name__ == "__main__":
    main()
