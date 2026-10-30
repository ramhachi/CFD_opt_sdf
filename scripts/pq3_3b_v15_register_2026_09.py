"""Register the v15 campaign manifest: clearance support gate + response ladder.

The start state is a deterministic trim of the pinned v14 final checkpoint
(work/pq3_3b_campaign_v14/checkpoints/rho_0005.npy): design cells whose centers
fall outside the permitted solid-support box are zeroed and every other value is
kept unchanged. Because the trimmed bootstrap is a materially transformed
v14 state, v15 does not carry v14 accepted counts or convergence metrics: it
starts accepted_count at 0 with an empty convergence window, and the v14 counts
are recorded as provenance only. The run is a bounded discriminant/learning
campaign under the fresh-attempt and accepted-step budgets in
``learning_campaign``; the runner Stops fail-closed with the registered
``paused_learning_budget`` status. The response-level ladder continues to
smaller transform-feasible alphas only after Path B passes and the trial
response gates fail (the measured v14 stall); a Path B failure stops the
attempt fail-closed, because v15 is diagnosing nonlinear response, not
bypassing gradient qualification. Refuses to overwrite the immutable
manifest, the sidecar or a bootstrap file whose content differs from the
deterministic build.
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
from cfd_sdf.design_transform import (  # noqa: E402
    ConeFilter,
    DesignTransform,
    RampInterpolation,
    TanhProjection,
)
from cfd_sdf.fixed_grid_primal import load_fixed_grid_density_state  # noqa: E402
from scripts.pq3_3b_preflight_v6_2026_09 import sha256_array  # noqa: E402

V14_MANIFEST = ROOT / "docs/evidence/pq3_3b_campaign_manifest_v14_2026_09.json"
V14_OUTCOME = ROOT / "docs/evidence/pq3_3b_campaign_v14_outcome_2026_09.json"
V13_MANIFEST = ROOT / "docs/evidence/pq3_3b_v13_discriminant_manifest_2026_09.json"
V13_PREFLIGHT = ROOT / "docs/evidence/pq3_3b_v13_entry_preflight_2026_09.json"
V12_OUTCOME = ROOT / "docs/evidence/pq3_3b_campaign_v12_outcome_2026_09.json"
PQ41_V14 = ROOT / "docs/evidence/pq4_1_v14_state_stage_s_entry_2026_09.json"
MARGIN_STATE = ROOT / "work/pq3_3b_margin_masks/topology_state.json"
PREFLIGHT_SCRIPT = ROOT / "scripts/pq3_3b_v15_entry_preflight_2026_09.py"
MANIFEST = ROOT / "docs/evidence/pq3_3b_campaign_manifest_v15_2026_09.json"
SOURCE_RHO = ROOT / "work/pq3_3b_campaign_v14/checkpoints/rho_0005.npy"
BOOTSTRAP = ROOT / "work/pq3_3b_campaign_v15_bootstrap.npy"
LEVEL_NAME = "level_3_b128_margin"
MAX_FRESH_ATTEMPTS = 10
MAX_NEW_ACCEPTED_ATTEMPTS = 10
SUPPORT_BOX = {"x": [-0.675, 1.675], "y": [-0.475, 0.475], "z": [-0.275, 0.275]}


def _support_allowed_centers(state_meta: dict) -> np.ndarray:
    """Boolean design-grid mask for centers inside the registered support box."""

    shape = tuple(int(v) for v in state_meta["cell_shape"])
    origin = np.asarray(state_meta["origin"], dtype=np.float64)
    spacing = np.asarray(state_meta["spacing"], dtype=np.float64)
    centers = [origin[i] + spacing[i] * (np.arange(shape[i]) + 0.5) for i in range(3)]
    x = np.broadcast_to(centers[0].reshape(-1, 1, 1), shape)
    y = np.broadcast_to(centers[1].reshape(1, -1, 1), shape)
    z = np.broadcast_to(centers[2].reshape(1, 1, -1), shape)
    allowed = (
        (x >= float(SUPPORT_BOX["x"][0]) - 1e-9)
        & (x <= float(SUPPORT_BOX["x"][1]) + 1e-9)
        & (y >= float(SUPPORT_BOX["y"][0]) - 1e-9)
        & (y <= float(SUPPORT_BOX["y"][1]) + 1e-9)
        & (z >= float(SUPPORT_BOX["z"][0]) - 1e-9)
        & (z <= float(SUPPORT_BOX["z"][1]) + 1e-9)
    )
    return np.asarray(allowed).ravel(order="F")


def _build_bootstrap(state_meta: dict) -> np.ndarray:
    """Deterministically trim the pinned v14 checkpoint to the support box."""

    source = np.asarray(np.load(SOURCE_RHO, allow_pickle=False), dtype=np.float64)
    if source.size != np.prod(state_meta["cell_shape"]):
        raise ValueError(f"source rho size does not match the registered grid: {SOURCE_RHO}")
    return np.where(_support_allowed_centers(state_meta), source.ravel(order="F"), 0.0)


def _ensure_bootstrap(state_meta: dict) -> np.ndarray:
    bootstrap = _build_bootstrap(state_meta)
    if BOOTSTRAP.exists():
        if not np.array_equal(np.load(BOOTSTRAP, allow_pickle=False).ravel(order="F"), bootstrap):
            raise SystemExit(
                f"refusing to overwrite a bootstrap that differs from the "
                f"deterministic build: {BOOTSTRAP}"
            )
    else:
        np.save(BOOTSTRAP, np.ascontiguousarray(bootstrap), allow_pickle=False)
    return bootstrap


def _bootstrap_metrics(bootstrap: np.ndarray, v14: dict, level: dict) -> dict:
    grid_state = load_fixed_grid_density_state(_path(v14["registered_inputs"]["canonical_grid"]))
    ply = grid_state.arrays
    grid_meta = grid_state.grid
    shape = tuple(int(v) for v in grid_meta.cell_shape)
    active = (
        (np.asarray(ply["active_design_mask"], dtype=np.float64) > 0)
        & (np.asarray(ply["allowed_mask"], dtype=np.float64) > 0)
        & ~(np.asarray(ply["forbidden_mask"], dtype=np.float64) > 0)
        & ~(np.asarray(ply["fixed_solid_mask"], dtype=np.float64) > 0)
    )
    transform = DesignTransform(
        shape=shape,
        spacing_m=float(grid_meta.spacing[0]),
        active_mask=active,
        filter=ConeFilter(shape, float(grid_meta.spacing[0]), active, radius_m=float(v14["filter_radius_m"])),
        projection=TanhProjection(float(level["b"]), float(v14["projection_eta"])),
        ramp=RampInterpolation(float(level["q"])),
    )
    projected = np.asarray(
        transform.forward(bootstrap).rho_projected, dtype=np.float64
    ).ravel(order="F")
    values = projected[active.ravel(order="F")]
    support = _support_allowed_centers(
        {
            "origin": grid_meta.origin,
            "spacing": grid_meta.spacing,
            "cell_shape": grid_meta.cell_shape,
        }
    )
    return {
        "grid_cells": int(values.size),
        "projected_volume_measured": float(values.mean()),
        "mean_nd_measured": float(np.mean(4.0 * values * (1.0 - values))),
        "support_violations_measured": int(
            np.count_nonzero((projected > 0.5) & ~support)
        ),
    }


def _verify_bootstrap_provenance() -> dict:
    """Confirm the pinned v14 checkpoint hashes before deriving the bootstrap."""

    v14_outcome = ca.load_json(V14_OUTCOME)
    checkpoint = v14_outcome["checkpoint"]
    if ca.sha256_file(SOURCE_RHO) != checkpoint["rho_file_sha256"]:
        raise SystemExit("pinned v14 checkpoint rho file hash mismatch")
    if sha256_array(np.asarray(np.load(SOURCE_RHO), dtype=np.float64)) != checkpoint["rho_sha256"]:
        raise SystemExit("pinned v14 checkpoint rho array hash mismatch")
    state_path = ROOT / "work/pq3_3b_campaign_v14" / checkpoint["state_path"]
    if ca.sha256_file(state_path) != checkpoint["state_sha256"]:
        raise SystemExit("pinned v14 checkpoint state hash mismatch")
    state = ca.load_json(state_path)
    v14_manifest = ca.load_json(V14_MANIFEST)
    if state.get("accepted_count") is None:
        raise SystemExit("v14 checkpoint lacks an accepted count")
    return {
        "v14_checkpoint": {
            "rho_path": str(SOURCE_RHO.relative_to(ROOT)),
            "rho_file_sha256": checkpoint["rho_file_sha256"],
            "rho_sha256": checkpoint["rho_sha256"],
            "state_path": str((ROOT / "work/pq3_3b_campaign_v14" / checkpoint["state_path"]).relative_to(ROOT)),
            "state_sha256": checkpoint["state_sha256"],
            "accepted_count_v14_cumulative": int(state["accepted_count"]),
            "learning_accepted_count_v14": int(state.get("learning_accepted_count", 0)),
            "outcome_checkpoint_index": int(checkpoint["index"]),
            "not_carried_into_v15": True,
            "note": (
                "recorded as provenance only; the trimmed bootstrap is a materially "
                "transformed state, so v15 starts accepted_count at 0 with an empty "
                "convergence window"
            ),
        }
    }


def _path(ref):
    return ROOT / ref["path"]


def build() -> dict:
    v14 = ca.load_json(V14_MANIFEST)
    v14_outcome = ca.load_json(V14_OUTCOME)
    v14_stall_attempt = 6
    canonical_meta = ca.load_json(_path(v14["registered_inputs"]["canonical_grid"]))["grid"]
    bootstrap = _ensure_bootstrap(canonical_meta)
    record = list(v14_outcome["level_records"].values())[0]
    levels = [
        {**level, "max_attempts": MAX_FRESH_ATTEMPTS}
        if level["name"] == LEVEL_NAME
        else level
        for level in v14["levels"]
    ]
    provenance = _verify_bootstrap_provenance()
    return {
        "kind": "pq3_3b_campaign_manifest_v15",
        "schema_version": 12,
        "immutable": True,
        "status": "registered_preflight_pending",
        "plan": {
            **v14["plan"],
            "first_transform_feasible_only": False,
            "response_backtracking": True,
            "response_failure_action": (
                "continue to the next smaller transform-feasible alpha only after "
                "Path B passes and the trial response gates fail; a Path B failure "
                "stops the attempt fail-closed, and transform-infeasible alphas "
                "never consume solver calls"
            ),
            "scope": "bounded fresh-attempt learning campaign from a trimmed bootstrap",
        },
        "previous_registrations": {
            "manifest_v14": {"path": str(V14_MANIFEST.relative_to(ROOT)), "sha256": ca.sha256_file(V14_MANIFEST)},
            "campaign_v14_outcome": {"path": str(V14_OUTCOME.relative_to(ROOT)), "sha256": ca.sha256_file(V14_OUTCOME)},
        },
        "pinned_evidence": {
            "campaign_v14_outcome": {"path": str(V14_OUTCOME.relative_to(ROOT)), "sha256": ca.sha256_file(V14_OUTCOME)},
            "v13_discriminant": {"path": str(V13_MANIFEST.relative_to(ROOT)), "sha256": ca.sha256_file(V13_MANIFEST)},
            "v13_entry_preflight": {"path": str(V13_PREFLIGHT.relative_to(ROOT)), "sha256": ca.sha256_file(V13_PREFLIGHT)},
            "campaign_v12_outcome": {"path": str(V12_OUTCOME.relative_to(ROOT)), "sha256": ca.sha256_file(V12_OUTCOME)},
            "pq4_1_v14_state": {"path": str(PQ41_V14.relative_to(ROOT)), "sha256": ca.sha256_file(PQ41_V14)},
            "manifest_v14": {"path": str(V14_MANIFEST.relative_to(ROOT)), "sha256": ca.sha256_file(V14_MANIFEST)},
        },
        "change": {
            "id": "support-clearance-gate+response-level-ladder",
            "description": (
                "start state: a deterministic trim of the v14 final checkpoint in which "
                "cells whose centers fall outside the registered support box are zeroed, "
                "so the start satisfies the volume cap, the discreteness bound and zero "
                "support violations. policy: a transform-level support-clearance gate "
                "(solid cells inside the box) and a response-level ladder (backtracking "
                "continues only after Path B passes and the trial response gates fail; "
                "a Path B failure stops the attempt fail-closed). fresh bounded "
                "learning budgets; no v14 count or metric carryover."
            ),
            "does_not_relax": [
                "the 0.25 m clearance profile, the 0.01 discreteness bound, the volume cap and every threshold",
                "the PQ4.1 composite gate requirements",
            ],
            "evidence": {
                "pq4_1_v14_state_reasons": ["clearance:the extracted surface fails the clearance preflight"],
                "pq4_1_v14_state_top_z_clearance_m": 0.21055865883827207,
                "pq4_1_v14_state_side_clearance_m": 0.350000011920929,
                "v14_stall_attempt": v14_stall_attempt,
                "v14_stall_reason": "response_gates_failed at alpha 1.0; smaller alphas were never response-evaluated",
                "v14_stall_trial_downforce_delta": -2.909377100000175e-04,
                "v14_last_accepted_step_provenance_only": record["last_metrics"][-1],
            },
        },
        "bootstrap_provenance": {
            **provenance,
            "trim_rule": {
                "description": "cells whose centers fall outside the registered support box are set to zero; every other design value is kept unchanged",
                "deterministic": True,
                "tolerance_m": 1e-9,
                "implementation": "np.where on the support-center mask over the flattened design array",
                "support_box": SUPPORT_BOX,
            },
            "bootstrap": {
                "rho_path": str(BOOTSTRAP.relative_to(ROOT)),
                "rho_file_sha256": ca.sha256_file(BOOTSTRAP),
                "rho_sha256": sha256_array(bootstrap),
                "generated_by": "scripts/pq3_3b_v15_register_2026_09.py",
                "overwrite_refused": True,
                **_bootstrap_metrics(bootstrap, v14, levels[0]),
            },
            "clean_start": (
                "v15 resets accepted_count to 0 and starts with an empty convergence "
                "window; the v14 accepted counts and final metrics are provenance, not "
                "carried state"
            ),
        },
        "cap_stationarity_exit": v14["cap_stationarity_exit"],
        "input_stop_state": {
            "level": LEVEL_NAME,
            "source": "pinned v14 final checkpoint deterministically trimmed to the registered support box",
            "rho_path": str(BOOTSTRAP.relative_to(ROOT)),
            "rho_file_sha256": ca.sha256_file(BOOTSTRAP),
            "rho_sha256": sha256_array(bootstrap),
        },
        "registered_inputs": v14["registered_inputs"],
        "margin_mask": {
            "state": str(MARGIN_STATE.relative_to(ROOT)),
            "state_sha256": ca.sha256_file(MARGIN_STATE),
            "rule": "v10-qualified |y_center| <= 0.475",
        },
        "openfoam_image": v14["openfoam_image"],
        "openfoam_image_id": v14["openfoam_image_id"],
        "objective": v14["objective"],
        "phase1_policy": v14["phase1_policy"],
        "phase2_policy": {
            **v14["phase2_policy"],
            "support_box": SUPPORT_BOX,
            "response_level_ladder": True,
        },
        "filter_radius_m": v14["filter_radius_m"],
        "projection_eta": v14["projection_eta"],
        "registered_target": v14["registered_target"],
        "v_max_projected": v14["v_max_projected"],
        "volume_tolerance": v14["volume_tolerance"],
        "levels": levels,
        "path_b": v14["path_b"],
        "noise_thresholds": v14["noise_thresholds"],
        "convergence": {
            **v14["convergence"],
            "window_reset": True,
            "note": (
                "thresholds are unchanged from v14; the window itself is reset because "
                "the trimmed bootstrap is a new, materially transformed start state"
            ),
        },
        "reject_stop_count": v14["reject_stop_count"],
        "restoration_step_cap": v14["restoration_step_cap"],
        "learning_campaign": {
            "max_fresh_attempts": MAX_FRESH_ATTEMPTS,
            "max_new_accepted_attempts": MAX_NEW_ACCEPTED_ATTEMPTS,
            "does_not_claim_convergence": True,
            "stop_status": "paused_learning_budget",
            "unrestricted_campaign": False,
            "budget_note": (
                "fresh-attempt and accepted-step budgets against the trimmed bootstrap "
                "state; unrelated to the v14 counters, which are provenance only"
            ),
        },
        "solver_budget": {
            "scope": "per fresh attempt",
            "parent_adjoint_requests_max": 1,
            "transform_feasible_alphas_max": len(v14["phase2_policy"]["alpha_ladder"]),
            "path_b_primal_requests_per_tried_alpha": 2,
            "trial_primal_requests_per_tried_alpha": 1,
            "evaluator_requests_max_per_attempt": 1
            + len(v14["phase2_policy"]["alpha_ladder"]) * (2 + 1),
            "transform_infeasible_alpha_evaluator_requests": 0,
            "semantics": (
                "these are evaluator request bounds, not solver-run counts; "
                "request freshness is recorded separately per request in the "
                "campaign evaluator_calls evidence"
            ),
        },
        "resume_rule": (
            "resume only from a verified v15 checkpoint while below the registered "
            "fresh-attempt and accepted-step learning budgets"
        ),
        "terminal_rule": (
            "the v15 run is a bounded discriminant/learning campaign: it stops "
            "fail-closed at the learning budget (paused_learning_budget, as enforced by "
            "the runner) or at the first failed attempt, without evaluating the window "
            "exit or the cap-stationarity exit; no independent terminal repeat, no "
            "convergence and no Stage S readiness claim in this registration; any "
            "continuation and the PQ4.1 composite judgment require a later immutable "
            "manifest"
        ),
        "output_directory": "work/pq3_3b_campaign_v15",
        "entry_preflight": {
            "script_path": str(PREFLIGHT_SCRIPT.relative_to(ROOT)),
            "script_sha256": ca.sha256_file(PREFLIGHT_SCRIPT),
            "artifact_path": "docs/evidence/pq3_3b_v15_entry_preflight_2026_09.json",
            "requirement": "must pass before the v15 campaign",
        },
        "source_tree_python_sha256": ca.python_source_tree_sha256(ROOT / "src/cfd_sdf"),
        "claims_not_supported": [
            "the gate and ladder changes are registered, not yet qualified",
            "no terminal evaluation and no Stage S readiness in this registration",
        ],
    }


def main() -> None:
    if MANIFEST.exists():
        raise SystemExit("v15 manifest already exists; refuse overwrite")
    manifest = build()
    MANIFEST.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    MANIFEST.with_suffix(".json.sha256").write_text(ca.sha256_file(MANIFEST) + "\n", encoding="utf-8")
    print(json.dumps({"sha256": ca.sha256_file(MANIFEST), "learning_campaign": manifest["learning_campaign"]}, indent=2))


if __name__ == "__main__":
    main()
