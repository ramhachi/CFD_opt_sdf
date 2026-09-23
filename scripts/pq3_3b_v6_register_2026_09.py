"""Register the D2 change manifest and the v6 campaign manifest (post-v5 plan).

Registration order: this generator runs before any v6-entry qualification run.
It pins the D1 discriminant outcome, the source tree at registration time, the
new inequality policy thresholds and the entry-preflight script hash. Both
manifests are immutable and refuse to overwrite.
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
from cfd_sdf.design_transform import ConeFilter, DesignTransform, RampInterpolation, TanhProjection  # noqa: E402
from cfd_sdf.fixed_grid_primal import load_fixed_grid_density_state  # noqa: E402
from cfd_sdf.phase2_inequality_policy import (  # noqa: E402
    EXTRACTABILITY_FRACTION,
    EXTRACTABILITY_THRESHOLDS,
    MIN_CORRECTED_UPDATE_INF_NORM,
    POLICY_ID,
    occupancy_metrics,
)
from scripts.pq3_3b_preflight_v6_2026_09 import sha256_array  # noqa: E402

PLAN = ROOT / "docs/pq3_3b_post_v5_plan_2026_09.md"
D1_OUTCOME = ROOT / "docs/evidence/pq3_3b_d1_discriminant_outcome_2026_09.json"
D0 = ROOT / "docs/evidence/pq3_3b_stopped_state_diagnosis_2026_09.json"
MANIFEST_V5 = ROOT / "docs/evidence/pq3_3b_campaign_manifest_v5_2026_09.json"
OUTCOME_V5 = ROOT / "docs/evidence/pq3_3b_campaign_v5_outcome_2026_09.json"
PREFLIGHT_SCRIPT = ROOT / "scripts/pq3_3b_v6_entry_preflight_2026_09.py"
D2_MANIFEST = ROOT / "docs/evidence/pq3_3b_d2_change_manifest_2026_09.json"
V6_MANIFEST = ROOT / "docs/evidence/pq3_3b_campaign_manifest_v6_2026_09.json"
STOP_RHO = ROOT / "work/pq3_3b_campaign_v5/checkpoints/rho_0003.npy"
WORK = ROOT / "work/df2_fd_refresh"
SHAPE = (60, 32, 24)
SPACING_M = 0.05
V_MAX = 0.07632566813424899
REGISTERED_TARGET = 0.018
VOLUME_TOLERANCE = 1e-4
ALPHA_LADDER = [1.0, 0.5, 0.25, 0.125, 0.0625]
NOISE = {"objective": 1e-06, "downforce": 1e-06}
PATH_B = {"epsilon": 0.0008, "noise_floor_abs": 1e-06, "requires_centered_pair": True}
LEVELS = [
    {"name": "level_0_growth_b4_q15", "b": 4.0, "q": 15.0, "move_limit": 0.05,
     "min_accepted_iterations": 10, "max_attempts": 30},
    {"name": "level_1_b8_q30", "b": 8.0, "q": 30.0, "move_limit": 0.03,
     "min_accepted_iterations": 10, "max_attempts": 30},
    {"name": "level_2_b16_q100", "b": 16.0, "q": 100.0, "move_limit": 0.01,
     "min_accepted_iterations": 10, "max_attempts": 30},
]


def _occupancy_baseline(v5: dict) -> dict:
    rho = np.load(STOP_RHO, allow_pickle=False)
    grid = load_fixed_grid_density_state(ROOT / v5["canonical_grid"]["path"])
    arrays = grid.arrays
    active = (
        (np.asarray(arrays["active_design_mask"]) > 0)
        & (np.asarray(arrays["allowed_mask"]) > 0)
        & ~(np.asarray(arrays["forbidden_mask"]) > 0)
        & ~(np.asarray(arrays["fixed_solid_mask"]) > 0)
    )
    transform = DesignTransform(
        shape=SHAPE,
        spacing_m=SPACING_M,
        active_mask=active,
        filter=ConeFilter(SHAPE, SPACING_M, active, radius_m=v5["filter_radius_m"]),
        projection=TanhProjection(8.0, v5["projection_eta"]),
        ramp=RampInterpolation(30.0),
    )
    return occupancy_metrics(transform, rho, active)


def build_d2(v5: dict) -> dict:
    return {
        "kind": "pq3_3b_d2_change_manifest",
        "schema_version": 1,
        "immutable": True,
        "status": "registered_awaiting_entry_qualification",
        "plan": {"path": str(PLAN.relative_to(ROOT)), "sha256": ca.sha256_file(PLAN)},
        "discriminant_evidence": {
            "path": str(D1_OUTCOME.relative_to(ROOT)),
            "sha256": ca.sha256_file(D1_OUTCOME),
        },
        "diagnosis_evidence": {
            "path": str(D0.relative_to(ROOT)),
            "sha256": ca.sha256_file(D0),
        },
        "decision": {
            "table_rows_applied": [
                "upper-bound-only direction improves detectably",
                "volume-exchange direction improves detectably",
            ],
            "adopted": (
                "objective-oc-inequality-v1: the Phase 2 ladder now uses the objective sign step "
                "without the equality volume correction; the original inequality V <= Vmax is enforced"
            ),
            "evidence": {
                "d1_registered_corrected_step_improvement": 2.7124e-07,
                "d2_objective_only_improvement_amp1": 0.13399131714800006,
                "d3_exchange_improvement_amp1": 0.02789471006200006,
                "d4_one_sided_inward_improvement_amp1": 8.056980299997463e-05,
                "parent_spread": 0.0,
            },
            "recorded_alternative": (
                "d3 orthogonal volume exchange direction remains registered in the D1 outcome for a "
                "future manifest if the inequality campaign shows projected-volume drift"
            ),
            "not_adopted": (
                "d4 one-sided inward perturbation is recorded as a diagnostic only; it is not "
                "qualified by the centered Path B bracket"
            ),
        },
        "change": {
            "id": POLICY_ID,
            "module": "src/cfd_sdf/phase2_inequality_policy.py",
            "min_corrected_update_inf_norm": MIN_CORRECTED_UPDATE_INF_NORM,
            "min_norm_rationale": (
                "D0 measured machine-scale corrected norms <= 2.8e-17 and the smallest detectable "
                "D1 step at 0.03 inf-norm; 1e-8 is far above float noise and far below meaningful steps"
            ),
            "extractability_fraction": EXTRACTABILITY_FRACTION,
            "extractability_thresholds": list(EXTRACTABILITY_THRESHOLDS),
            "extractability_baseline_b8_stop": _occupancy_baseline(v5),
            "extractability_guard_is_not_a_pq41_substitute": True,
            "unchanged": [
                "Phase 1 projected-volume restoration to the formation target 0.018",
                "Path B centered bracket epsilon 8e-4 and noise floor 1e-6",
                "improvement thresholds 1e-6 (objective and raw downforce)",
                "b/q schedule, move limits, filter radius and projection eta",
                "box-face freeze policy in Phase 2",
            ],
        },
        "budget": {
            "entry_preflight_max_new_primals": 20,
            "long_campaign_not_in_this_slice": True,
        },
        "rules": [
            "registered thresholds are not relaxed after seeing results",
            "no v4/v5 result is retroactively re-passed",
            "a rejection at every alpha stops the level fail-closed until a new manifest",
        ],
        "claims_not_supported": [
            "the change is registered; it is not yet qualified by the entry preflight",
        ],
    }


def build_v6(v5: dict) -> dict:
    rho = np.load(STOP_RHO, allow_pickle=False)
    return {
        "kind": "pq3_3b_campaign_manifest_v6",
        "schema_version": 5,
        "immutable": True,
        "status": "registered_preflight_pending",
        "plan": {"path": str(PLAN.relative_to(ROOT)), "sha256": ca.sha256_file(PLAN)},
        "change_manifest_d2": {
            "path": str(D2_MANIFEST.relative_to(ROOT)),
            "sha256": ca.sha256_file(D2_MANIFEST),
        },
        "discriminant_outcome_d1": {
            "path": str(D1_OUTCOME.relative_to(ROOT)),
            "sha256": ca.sha256_file(D1_OUTCOME),
        },
        "previous_registrations": {
            "manifest_v5": {"path": str(MANIFEST_V5.relative_to(ROOT)), "sha256": ca.sha256_file(MANIFEST_V5)},
            "campaign_v5_outcome": {"path": str(OUTCOME_V5.relative_to(ROOT)), "sha256": ca.sha256_file(OUTCOME_V5)},
        },
        "input_stop_state": {
            "level": "level_1_b8_q30",
            "rho_path": str(STOP_RHO.relative_to(ROOT)),
            "rho_file_sha256": ca.sha256_file(STOP_RHO),
            "rho_sha256": sha256_array(rho),
        },
        "registered_inputs": {
            "canonical_grid": v5["canonical_grid"],
            "source_grid": v5["source_grid"],
            "problem_spec": v5["problem_spec"],
            "template_parent": v5["template_parent"],
            "template_trial": v5["template_trial"],
            "solver_controls": v5["solver_controls"],
            "noise_calibration": v5["noise_calibration"],
        },
        "openfoam_image": v5["openfoam_image"],
        "openfoam_image_id": v5["openfoam_image_id"],
        "objective": v5["objective"],
        "phase1_policy": {
            "id": "projected-volume-restoration-oc",
            "ascent_only": True,
            "unchanged_from_v5": True,
            "formation_target": REGISTERED_TARGET,
        },
        "phase2_policy": {
            "id": POLICY_ID,
            "module": "src/cfd_sdf/phase2_inequality_policy.py",
            "alpha_ladder": ALPHA_LADDER,
            "freeze_exact_box_faces": True,
            "min_corrected_update_inf_norm": MIN_CORRECTED_UPDATE_INF_NORM,
            "extractability_fraction": EXTRACTABILITY_FRACTION,
            "extractability_thresholds": list(EXTRACTABILITY_THRESHOLDS),
        },
        "filter_radius_m": v5["filter_radius_m"],
        "projection_eta": v5["projection_eta"],
        "registered_target": REGISTERED_TARGET,
        "v_max_projected": V_MAX,
        "volume_tolerance": VOLUME_TOLERANCE,
        "levels": LEVELS,
        "path_b": PATH_B,
        "noise_thresholds": NOISE,
        "convergence": {
            "window_accepted": 3,
            "objective_delta_abs_max": 1e-04,
            "projected_field_mean_abs_delta_max": 1e-03,
            "projected_volume_delta_abs_max": 1e-03,
            "note": "the equality volume residual criterion is replaced by volume stability under the inequality policy",
        },
        "reject_stop_count": 1,
        "restoration_step_cap": 60,
        "resume_rule": "resume only from the verified objective_accepted rho chain; incomplete solver cases block automatic resume",
        "terminal_rule": "b16 has at least ten accepted steps and level convergence; repeat primal on the final rho with only the original projected V<=Vmax gate before any Stage S assessment",
        "output_directory": "work/pq3_3b_campaign_v6",
        "entry_preflight": {
            "script_path": str(PREFLIGHT_SCRIPT.relative_to(ROOT)),
            "script_sha256": ca.sha256_file(PREFLIGHT_SCRIPT),
            "artifact_path": "docs/evidence/pq3_3b_v6_entry_preflight_2026_09.json",
            "requirement": "both stages must pass before any long campaign; the long campaign additionally requires an explicit user go",
        },
        "source_tree_python_sha256": ca.python_source_tree_sha256(ROOT / "src/cfd_sdf"),
        "campaign_runner": "not implemented in this registration slice; a runner must pin this manifest and the entry preflight evidence",
        "claims_not_supported": [
            "no long campaign result, no b16 terminal evaluation and no Stage S readiness in this registration",
        ],
    }


def main() -> None:
    for path in (D2_MANIFEST, V6_MANIFEST):
        if path.exists():
            raise SystemExit(f"registration already exists: {path}")
    v5 = ca.load_json(MANIFEST_V5)
    d2 = build_d2(v5)
    D2_MANIFEST.write_text(json.dumps(d2, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    D2_MANIFEST.with_suffix(".json.sha256").write_text(
        ca.sha256_file(D2_MANIFEST) + "\n", encoding="utf-8"
    )
    v6 = build_v6(v5)
    V6_MANIFEST.write_text(json.dumps(v6, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    V6_MANIFEST.with_suffix(".json.sha256").write_text(
        ca.sha256_file(V6_MANIFEST) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "d2_manifest_sha256": ca.sha256_file(D2_MANIFEST),
                "v6_manifest_sha256": ca.sha256_file(V6_MANIFEST),
                "source_tree_python_sha256": v6["source_tree_python_sha256"],
            }
        )
    )


if __name__ == "__main__":
    main()
