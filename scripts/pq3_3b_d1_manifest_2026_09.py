"""Register the D1 discriminant manifest (docs/pq3_3b_post_v5_plan_2026_09.md).

The manifest fixes, before any new solver evaluation: the stopped input rho,
the two independent parent primals, the four direction constructions with two
amplitudes each, the total solver budget (<= 10 new primals), the registered
improvement thresholds, the verdict rules and the fail-closed rules. It refuses
to overwrite an existing registration.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cfd_sdf import campaign_assertions as ca  # noqa: E402

PLAN = ROOT / "docs/pq3_3b_post_v5_plan_2026_09.md"
D0 = ROOT / "docs/evidence/pq3_3b_stopped_state_diagnosis_2026_09.json"
MANIFEST_V5 = ROOT / "docs/evidence/pq3_3b_campaign_manifest_v5_2026_09.json"
OUTCOME_V5 = ROOT / "docs/evidence/pq3_3b_campaign_v5_outcome_2026_09.json"
MANIFEST = ROOT / "docs/evidence/pq3_3b_d1_manifest_2026_09.json"
STOP_RHO = ROOT / "work/pq3_3b_campaign_v5/checkpoints/rho_0003.npy"
STOP_RHO_SHA256 = "ffb594427f56670068aeacc6742b0075c1fbd418f834f83033d079b014cecfcd"
STOP_RHO_FILE_SHA256 = "149eee70325d332996f134648404ae7eede2894140ad1bd9be09c8e719374455"
MANIFEST_V5_SHA256 = "38dbd9a476ebe72de1f49b51928b6b4c9bb6570d135df4db47c00107eb7a786d"
OUTPUT_DIRECTORY = "work/pq3_3b_d1"
SHAPE = [60, 32, 24]
SPACING_M = 0.05
FILTER_RADIUS_M = 0.15
PROJECTION_ETA = 0.5
LEVEL = {"name": "level_1_b8_q30", "b": 8.0, "q": 30.0, "move_limit": 0.03}
REGISTERED_TARGET = 0.018
V_MAX_PROJECTED = 0.07632566813424899
VOLUME_TOLERANCE = 1e-4
PATH_B = {"epsilon": 0.0008, "noise_floor_abs": 1e-06, "requires_centered_pair": True}
IMPROVEMENT_THRESHOLD = 1e-06
ALPHA_LADDER = [1.0, 0.5, 0.25, 0.125, 0.0625]
AMPLITUDES = [1.0, 0.5]


def build_manifest() -> dict:
    return {
        "kind": "pq3_3b_d1_discriminant_manifest",
        "schema_version": 1,
        "status": "registered_awaiting_execution",
        "immutable": True,
        "plan": {"path": str(PLAN.relative_to(ROOT)), "sha256": ca.sha256_file(PLAN)},
        "diagnosis": {"path": str(D0.relative_to(ROOT)), "sha256": ca.sha256_file(D0)},
        "source_registration": {
            "manifest_v5": {
                "path": str(MANIFEST_V5.relative_to(ROOT)),
                "sha256": MANIFEST_V5_SHA256,
            },
            "campaign_v5_outcome": {
                "path": str(OUTCOME_V5.relative_to(ROOT)),
                "sha256": ca.sha256_file(OUTCOME_V5),
            },
        },
        "stop_state": {
            "level": LEVEL["name"],
            "rho_path": str(STOP_RHO.relative_to(ROOT)),
            "rho_file_sha256": STOP_RHO_FILE_SHA256,
            "rho_sha256": STOP_RHO_SHA256,
            "campaign_status": "blocked",
            "campaign_reason": "objective_rejected",
        },
        "fixed_configuration": {
            "shape": SHAPE,
            "spacing_m": SPACING_M,
            "filter_radius_m": FILTER_RADIUS_M,
            "projection_eta": PROJECTION_ETA,
            "level": LEVEL,
            "registered_target": REGISTERED_TARGET,
            "v_max_projected": V_MAX_PROJECTED,
            "volume_tolerance": VOLUME_TOLERANCE,
            "path_b": PATH_B,
            "phase2_policy": {
                "id": "volume-corrected-objective-oc",
                "freeze_exact_box_faces": True,
                "alpha_ladder": ALPHA_LADDER,
            },
        },
        "diagnosis_notes": {
            "frozen_box_face_cells": 9495,
            "active_cells_at_zero": 9263,
            "active_cells_at_one": 232,
            "alpha_1_corrected_inf_norm": 2.6710116959205443e-05,
            "smaller_alpha_corrected_inf_norm_max": 2.7755575615628914e-17,
            "mechanism": "the uniform volume correction cancels the sign step at machine scale for alphas <= 0.5; the effective alpha=1 update is 2.67e-5 in inf-norm",
        },
        "directions": [
            {
                "id": "d1_corrected_alpha1",
                "construction": "the registered alpha=1 volume-corrected candidate delta from the D0 diagnosis (identical code path), re-evaluated with independent fresh primals",
                "amplitudes": AMPLITUDES,
                "purpose": "remeasure the only non-machine-scale corrected update and test detectability against the independent parent spread",
                "path_b_qualified_aspiration": True,
            },
            {
                "id": "d2_objective_only_no_volume_pullback",
                "construction": "clip(rho - move_limit * sign(gradJ), box) with the registered v5 box-face freeze applied; no uniform volume correction",
                "amplitudes": AMPLITUDES,
                "purpose": "test whether the equality target V=0.018 blocks the objective; candidates are measured only against V<=Vmax and all mask/box gates",
                "path_b_qualified_aspiration": True,
            },
            {
                "id": "d3_volume_exchange_orthogonal",
                "construction": "on the movable subspace S = active & ~frozen: e = gradJ - (gradJ . gradV)/(gradV . gradV) * gradV; delta = -e normalized to inf-norm 1 on S, zero elsewhere; clip to the move box",
                "amplitudes": AMPLITUDES,
                "purpose": "first-order volume-preserving exchange direction; the nonlinear projected volume and the real primal are measured and no linearization is treated as acceptance evidence",
                "path_b_qualified_aspiration": True,
            },
            {
                "id": "d4_inward_from_box_faces",
                "construction": "one-sided: +move_limit on frozen cells with rho == 0 whose canonical descent direction is positive; -move_limit on frozen cells with rho == 1 whose descent direction is negative; zero elsewhere; the box-face freeze is deliberately not applied",
                "amplitudes": AMPLITUDES,
                "purpose": "measure the inward perturbation removed by the full box-face freeze; not Path B qualified (one-sided)",
                "path_b_qualified_aspiration": False,
            },
        ],
        "budget": {
            "max_new_primals": 10,
            "parent_repeat_primals": 2,
            "direction_primals": 8,
            "fresh_run_roots": [
                "work/pq3_3b_d1/parent_repeat_a/runs",
                "work/pq3_3b_d1/parent_repeat_b/runs",
                "work/pq3_3b_d1/directions/runs",
            ],
            "case_reuse_prohibited_for_parent_repeat": True,
        },
        "noise": {
            "improvement_threshold_objective": IMPROVEMENT_THRESHOLD,
            "improvement_threshold_downforce": IMPROVEMENT_THRESHOLD,
            "parent_spread_measured_in_run": True,
            "do_not_lower_after_results": True,
        },
        "verdict_rules": [
            "per evaluation: solver converged, primal converged, V<=Vmax, mask drift 0, move-box violation 0",
            "detectable improvement: canonical improvement > max(threshold, parent spread) AND raw downforce improvement > max(threshold, parent spread)",
            "direction verdict detectable_improvement only if both amplitudes are detectable (sign-stable)",
            "any constraint violation makes the direction infeasible and is recorded fail-closed",
            "failure to find an improving direction in this finite set is NOT a KKT stationarity conclusion",
        ],
        "fail_closed_rules": [
            "any solver non-convergence, mask violation or box violation is recorded and never treated as improvement",
            "machine-scale corrected updates are rejected by the corrected-update norm gate before any normalization could qualify them",
            "the registered thresholds are not relaxed after seeing results",
            "no v4/v5 result is retroactively re-passed",
        ],
        "claims_not_supported": [
            "D1 is a bounded discriminant; it does not prove convergence or non-stationarity",
            "no b16, terminal or Stage S qualification is included",
        ],
    }


def main() -> None:
    if MANIFEST.exists():
        raise SystemExit("D1 manifest already exists; refusing to overwrite")
    if ca.sha256_file(MANIFEST_V5) != MANIFEST_V5_SHA256:
        raise SystemExit("manifest v5 hash does not match the registered value")
    manifest = build_manifest()
    MANIFEST.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    sidecar = MANIFEST.with_suffix(".json.sha256")
    sidecar.write_text(ca.sha256_file(MANIFEST) + "\n", encoding="utf-8")
    print(json.dumps({"status": manifest["status"], "manifest": str(MANIFEST), "sha256": ca.sha256_file(MANIFEST)}))


if __name__ == "__main__":
    main()
