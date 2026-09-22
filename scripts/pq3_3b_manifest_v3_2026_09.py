"""Build the immutable PQ3.3b campaign manifest v3 (metric-backed, fail-closed).

The manifest is registered with a SHA-256 sidecar. Status is derived from the
preflight v4 evidence: preflight_pass true -> registered_preflight_pass_
awaiting_user_go; otherwise registered_blocked. Refuses to overwrite an
existing manifest.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cfd_sdf import campaign_assertions as ca  # noqa: E402

CHECKPOINT = ROOT / "work" / "pq3_3_volume_target" / "checkpoint_chunk02.json"
PROBLEM_SPEC = ROOT / "work" / "pq0_2_smoke" / "project_downforce_volume.yaml"
PREFLIGHT_V4 = ROOT / "docs" / "evidence" / "pq3_3b_preflight_v4_2026_09.json"
NOISE = ROOT / "docs" / "evidence" / "pq3_3b_noise_calibration_2026_09.json"
TEMPLATE_PARENT = ROOT / "work" / "df2_fd_refresh" / "template_frozen"
TOPOLOGY = ROOT / "work" / "df2_fd_refresh" / "topology_state.json"
MANIFEST = ROOT / "docs" / "evidence" / "pq3_3b_campaign_manifest_v3_2026_09.json"
TOLERANCE = 1e-4
REGISTERED_TARGET = 0.018
V_MAX = 0.07632566813424899
ALPHA_LADDER = (1.0, 0.5, 0.25, 0.125, 0.0625)
LEVELS = (
    {"name": "level_0_growth_b4_q15", "b": 4.0, "q": 15.0, "move_limit": 0.05, "max_iterations": 40},
    {"name": "level_1_b8_q30", "b": 8.0, "q": 30.0, "move_limit": 0.03, "max_iterations": 40},
    {"name": "level_2_b16_q100", "b": 16.0, "q": 100.0, "move_limit": 0.01, "max_iterations": 30},
)


def hash_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def hash_array(values) -> str:
    import numpy as np

    raw = np.ascontiguousarray(np.asarray(values, dtype=np.float64))
    return hashlib.sha256(raw.tobytes()).hexdigest()


def build_manifest() -> dict:
    pref = ca.load_json(PREFLIGHT_V4)
    noise = ca.load_json(NOISE)
    passed = bool(pref["summary"].get("preflight_pass"))
    manifest = {
        "kind": "pq3_3b_campaign_manifest_v3",
        "schema_version": 4,
        "immutable": True,
        "status": ca.STATUS_AWAITING_GO if passed else ca.STATUS_BLOCKED,
        "input_checkpoint": {
            "path": str(CHECKPOINT.relative_to(ROOT)),
            "sha256": hash_file(CHECKPOINT),
        },
        "input_rho_sha256": None,
        "problem_spec": {
            "path": str(PROBLEM_SPEC.relative_to(ROOT)),
            "sha256": hash_file(PROBLEM_SPEC),
        },
        "compiled_problem_hash": "recorded-by-runner-at-campaign-time",
        "canonical_grid": {"topology_state_sha256": hash_file(TOPOLOGY)},
        "openfoam_image": "opencfd/openfoam-default:2512",
        "template_tree_hash": ca.tree_sha256(TEMPLATE_PARENT),
        "solver_controls_hash": ca.tree_sha256(TEMPLATE_PARENT),
        "filter_radius_m": 0.15,
        "registered_target": REGISTERED_TARGET,
        "v_max_projected": V_MAX,
        "b_q_schedule": [
            {"name": lvl["name"], "b": lvl["b"], "q": lvl["q"]} for lvl in LEVELS
        ],
        "move_limit": {lvl["name"]: lvl["move_limit"] for lvl in LEVELS},
        "objective_alpha_ladder": list(ALPHA_LADDER),
        "volume_tolerance": TOLERANCE,
        "path_b_epsilon": 1e-4,
        "noise_calibration": {
            "path": str(NOISE.relative_to(ROOT)),
            "objective_noise_threshold": noise["objective_noise_threshold"],
            "downforce_noise_threshold": noise["downforce_noise_threshold"],
        },
        "iteration_bounds": {lvl["name"]: lvl["max_iterations"] for lvl in LEVELS},
        "convergence_thresholds": {
            "objective_improvement": noise["objective_noise_threshold"],
            "volume_residual": TOLERANCE,
            "field_residual": TOLERANCE,
        },
        "reject_stop_count": 8,
        "checkpoint_resume_rule": "every accepted state; resume asserts the sha256 rho chain",
        "fresh_output_rule": "work/pq3_3b_campaign must not exist when the runner starts",
        "preflight_v4": {
            "path": str(PREFLIGHT_V4.relative_to(ROOT)),
            "sha256": hash_file(PREFLIGHT_V4),
        },
        "state_lineage": "previous_level.accepted_rho_sha256 == next_level.input_rho_sha256",
        "objective": {"sense": "maximize", "canonical": "J = -downforce"},
        "phase_1_backend": {"id": "projected-volume-restoration-oc"},
        "phase_2_backend": {"id": "volume-corrected-objective-oc"},
    }
    manifest["pass_conditions_before_campaign"] = [
        "preflight v4 passes and the status is registered_preflight_pass_awaiting_user_go",
        "the runner turns off any implicit fall-back to the multiplicative OC backends",
        "Phase 1 states recorded as restoration_feasible; objective_accepted only after the full Phase 2 gate set",
    ]
    if not passed:
        manifest["blocked_reason"] = pref["summary"]
    return manifest


def main() -> None:
    if MANIFEST.exists():
        raise SystemExit("manifest v3 already exists; refusing to overwrite")
    manifest = build_manifest()
    MANIFEST.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    sidecar = MANIFEST.with_suffix(".json.sha256")
    sidecar.write_text(ca.sha256_file(MANIFEST) + "\n", encoding="utf-8")
    print(json.dumps({"status": manifest["status"], "manifest": str(MANIFEST)}))


if __name__ == "__main__":
    main()
