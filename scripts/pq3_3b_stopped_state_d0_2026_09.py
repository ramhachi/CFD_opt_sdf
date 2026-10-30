"""PQ3.3b stopped-state diagnosis (D0 of docs/pq3_3b_post_v5_plan_2026_09.md).

No new OpenFOAM evaluation is performed. The stopped parent gradient is
reconstructed from the saved, SHA-256 verified v5 campaign case through the
oracle's content-addressed reuse path. For every registered alpha this script
records the pre/post-correction update norms, projected-volume changes, kappa,
proposal/corrected direction dot products, grad J and grad V directional
derivatives, active cells at 0/1, frozen box-face cells, mask drift and
move-box violations.

The verdict is limited to mechanism identification ("the volume correction
cancelled the update", "box-face freezing removed movable directions"). Small
update norms alone are not physical or mathematical convergence evidence.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

from cfd_sdf import campaign_assertions as ca  # noqa: E402
from cfd_sdf.canonical_objective import canonical_objective_from  # noqa: E402
from cfd_sdf.design_transform import ConeFilter, DesignTransform, RampInterpolation, TanhProjection  # noqa: E402
from cfd_sdf.fixed_grid_primal import load_fixed_grid_density_state  # noqa: E402
from cfd_sdf.phase2_policy import ALPHA_LADDER  # noqa: E402
from cfd_sdf.problem_spec import load_problem_spec  # noqa: E402
from cfd_sdf.problem_spec_compiler import VolumeBudget, compile_problem  # noqa: E402
from cfd_sdf.projected_restoration import _restore  # noqa: E402
from cfd_sdf.stage_t_loop import make_oracle_from_compiled  # noqa: E402

BISECTION_STEPS = 60

MANIFEST_V5 = ROOT / "docs/evidence/pq3_3b_campaign_manifest_v5_2026_09.json"
OUTCOME_V5 = ROOT / "docs/evidence/pq3_3b_campaign_v5_outcome_2026_09.json"
PLAN = ROOT / "docs/pq3_3b_post_v5_plan_2026_09.md"
ARTIFACT = ROOT / "docs/evidence/pq3_3b_stopped_state_diagnosis_2026_09.json"
CAMPAIGN = ROOT / "work/pq3_3b_campaign_v5"
WORK = ROOT / "work/df2_fd_refresh"
SHAPE = (60, 32, 24)
SPACING_M = 0.05
LEVEL_NAME = "level_1_b8_q30"
STOP_RHO_SHA256 = "ffb594427f56670068aeacc6742b0075c1fbd418f834f83033d079b014cecfcd"
STOP_RHO_FILE_SHA256 = "149eee70325d332996f134648404ae7eede2894140ad1bd9be09c8e719374455"
STATE_SHA256 = "9e7ad93885b34d22ec3f625246cfd4ca676652c1b18e229a32179b511252ed73"
LATEST_SHA256 = "f5d150914f225ad9c31a4f8135431bea3cad5ed50545fdd7981b23eef87196b5"
META_SHA256 = "af77307dc4ed0196ac5c13f00682456fb0ad0fffd5e2ae3b3233d9480aaeac14"
EVENTS_SHA256 = "2fb08315486abecbe1f5696c6420fd8251c9cb82cb3855e7ecca2228c03a8953"
PARENT_SUMMARY_SHA256 = "b0ff9faa3e0460b641b3fbcc8fab3d2da64c90bab32816a9e45b2c210b98e466"
PARENT_DOWNFORCE = 0.579818003757
FD_EPSILON = 1e-5
MACHINE_SCALE_NORM = 1e-8


def _array_sha256(values: np.ndarray) -> str:
    import hashlib

    raw = np.ascontiguousarray(np.asarray(values, dtype=np.float64))
    return hashlib.sha256(raw.tobytes()).hexdigest()


def _norms(delta: np.ndarray, active: np.ndarray) -> dict:
    values = np.asarray(delta, dtype=np.float64)
    selected = values[active] if bool(active.any()) else values
    return {
        "inf_norm": float(np.max(np.abs(values))) if values.size else 0.0,
        "inf_norm_active": float(np.max(np.abs(selected))) if selected.size else 0.0,
        "l2_norm": float(np.sqrt(np.sum(values * values))),
        "l2_norm_active": float(np.sqrt(np.sum(selected * selected))),
    }


def _projected_field(transform, rho: np.ndarray) -> np.ndarray:
    return np.asarray(
        transform.forward(np.asarray(rho, dtype=np.float64)).rho_projected,
        dtype=np.float64,
    )


def _fd_check_gradV(transform, rho: np.ndarray, grad_v: np.ndarray, active: np.ndarray, epsilon: float) -> dict:
    """Directional-derivative check of grad V along its own unit direction.

    Two variants are recorded: the raw direction (cells at exact 0/1 clip the
    perturbation) and an interior-only direction with the boundary cells
    zeroed, so that the finite difference probes the smooth interior instead
    of the clip.
    """
    values = np.asarray(rho, dtype=np.float64)
    peak = float(np.max(np.abs(grad_v[active]))) if bool(active.any()) else 0.0
    if peak <= 0.0:
        return {"applicable": False, "reason": "zero_gradV_peak"}
    direction = np.zeros_like(grad_v, dtype=np.float64)
    direction[active] = grad_v[active] / peak
    guard = (values <= epsilon) | (values >= 1.0 - epsilon)
    interior = direction.copy()
    interior[guard] = 0.0

    def variant(name: str, probe: np.ndarray) -> dict:
        plus = np.clip(values + epsilon * probe, 0.0, 1.0)
        minus = np.clip(values - epsilon * probe, 0.0, 1.0)
        phi_plus = float(_projected_field(transform, plus)[active].mean())
        phi_minus = float(_projected_field(transform, minus)[active].mean())
        phi_center = float(_projected_field(transform, values)[active].mean())
        fd = (phi_plus - phi_minus) / (2.0 * epsilon)
        analytic = float(np.dot(grad_v, probe))
        scale = max(abs(analytic), abs(fd), 1e-30)
        return {
            "name": name,
            "epsilon": float(epsilon),
            "analytic_directional": analytic,
            "finite_difference": float(fd),
            "relative_error": float(abs(fd - analytic) / scale),
            "phi_center": phi_center,
            "phi_plus": phi_plus,
            "phi_minus": phi_minus,
            "clipped_probe_cells": int(np.count_nonzero(np.abs(plus - (values + epsilon * probe)) > 0.0))
            + int(np.count_nonzero(np.abs(minus - (values - epsilon * probe)) > 0.0)),
        }

    raw = variant("all_cells", direction)
    interior_check = variant("interior_only", interior)
    return {
        "applicable": True,
        "all_cells": raw,
        "interior_only": interior_check,
        "interior_cells": int(np.count_nonzero(~guard)),
    }


def _registered_volume_correction(
    *,
    transform,
    proposal: np.ndarray,
    box_low: np.ndarray,
    box_high: np.ndarray,
    move_limit: float,
    target: float,
    volume_tolerance: float,
    restore_policy,
) -> tuple[float, np.ndarray, float] | None:
    """Verbatim replica of the registered v4/v5 Phase 2 step 3.

    The campaign scripts and manifest v5 pin the ``src/cfd_sdf`` source tree,
    so the diagnostic must not modify the registered module: this copy is kept
    byte-for-byte equivalent to ``phase2_policy.evaluate_phase2_candidate`` and
    the equivalence is asserted by tests/test_pq3_3b_d0_diagnosis.py against the
    registered function (kappa and corrected rho must match exactly).
    """
    active = np.asarray(transform.active, dtype=bool)
    move_limit = float(move_limit)

    def phi_at(kappa_volume: float) -> float:
        stepped = np.clip(proposal + kappa_volume * move_limit, box_low, box_high)
        stepped = restore_policy(stepped)
        state = transform.forward(stepped)
        projected = np.asarray(state.rho_projected, dtype=np.float64)
        return float(projected[active].mean())

    phi_low = phi_at(-1.0)
    phi_high = phi_at(1.0)
    if phi_low > target + volume_tolerance or phi_high < target - volume_tolerance:
        return None
    low_k, high_k, kappa_volume = -1.0, 1.0, None
    for _ in range(BISECTION_STEPS):
        mid = 0.5 * (low_k + high_k)
        phi_mid = phi_at(mid)
        if phi_mid < target:
            low_k = mid
        else:
            high_k = mid
            kappa_volume = mid
    phi_final = phi_at(float(kappa_volume))
    corrected = np.clip(
        proposal + float(kappa_volume) * move_limit, box_low, box_high
    )
    corrected = restore_policy(corrected)
    return float(kappa_volume), corrected, float(phi_final)


def proposal_and_correction(
    *,
    transform,
    rho: np.ndarray,
    grad_j: np.ndarray,
    alpha: float,
    move_limit: float,
    target: float,
    volume_tolerance: float,
) -> tuple[np.ndarray, np.ndarray | None, float | None]:
    """Registered alpha candidate: v5-freeze proposal + uniform volume correction.

    Returns ``(proposal, corrected, kappa_volume)``; ``corrected`` is ``None``
    when the registered target is not bracketed inside the move box. This is
    the exact code path used by the D0 diagnosis and the D1 discriminant.
    """
    values = np.asarray(rho, dtype=np.float64)
    active = np.asarray(transform.active, dtype=bool)
    box_low = np.clip(values - move_limit, 0.0, 1.0)
    box_high = np.clip(values + move_limit, 0.0, 1.0)
    frozen = active & ((values == 0.0) | (values == 1.0))

    def restore_policy(stepped: np.ndarray) -> np.ndarray:
        restored = _restore(stepped, values, active)
        restored[frozen] = values[frozen]
        return restored

    proposal = np.clip(values - float(alpha) * move_limit * np.sign(grad_j), box_low, box_high)
    proposal[frozen] = values[frozen]
    correction = _registered_volume_correction(
        transform=transform,
        proposal=proposal,
        box_low=box_low,
        box_high=box_high,
        move_limit=move_limit,
        target=target,
        volume_tolerance=volume_tolerance,
        restore_policy=restore_policy,
    )
    if correction is None:
        return proposal, None, None
    kappa_volume, corrected, _phi = correction
    return proposal, corrected, float(kappa_volume)


def alpha_diagnosis(
    *,
    transform,
    rho: np.ndarray,
    grad_j: np.ndarray,
    grad_v: np.ndarray,
    alpha: float,
    move_limit: float,
    target: float,
    volume_tolerance: float,
) -> dict:
    """Recompute one registered alpha's proposal and volume correction."""
    values = np.asarray(rho, dtype=np.float64)
    active = np.asarray(transform.active, dtype=bool)
    box_low = np.clip(values - move_limit, 0.0, 1.0)
    box_high = np.clip(values + move_limit, 0.0, 1.0)
    frozen = active & ((values == 0.0) | (values == 1.0))

    def restore_policy(stepped: np.ndarray) -> np.ndarray:
        restored = _restore(stepped, values, active)
        restored[frozen] = values[frozen]
        return restored

    proposal, corrected, kappa_volume = proposal_and_correction(
        transform=transform,
        rho=values,
        grad_j=grad_j,
        alpha=alpha,
        move_limit=move_limit,
        target=target,
        volume_tolerance=volume_tolerance,
    )
    phi_parent = float(_projected_field(transform, values)[active].mean())
    projected_proposal = _projected_field(transform, proposal)
    phi_proposal = float(projected_proposal[active].mean())
    record: dict = {
        "alpha": float(alpha),
        "frozen_box_face_cells": int(np.count_nonzero(frozen)),
        "active_cells_at_zero": int(np.count_nonzero(active & (values == 0.0))),
        "active_cells_at_one": int(np.count_nonzero(active & (values == 1.0))),
        "phi_parent": phi_parent,
        "phi_proposal": phi_proposal,
        "proposal_norms": _norms(proposal - values, active),
        "proposal_projected_field_mean_abs_delta": float(
            np.mean(np.abs(projected_proposal[active] - _projected_field(transform, values)[active]))
        ),
        "proposal_mask_drift_max": float(
            np.max(np.abs(proposal[~active] - values[~active])) if bool((~active).any()) else 0.0
        ),
        "proposal_move_box_violation_max": float(
            max(0.0, np.max(np.maximum(proposal - box_high, box_low - proposal)))
        ),
        "gradJ_dot_proposal": float(np.dot(grad_j, proposal - values)),
        "gradV_dot_proposal": float(np.dot(grad_v, proposal - values)),
    }
    if corrected is None:
        record.update(
            {
                "volume_correction": {"bracketed": False},
                "corrected_norms": None,
                "mechanism": "volume_correction_out_of_range",
            }
        )
        return record

    phi_final = float(_projected_field(transform, corrected)[active].mean())
    proposed_delta = proposal - values
    corrected_delta = corrected - values
    proposed_norm = float(np.linalg.norm(proposed_delta))
    corrected_norm = float(np.linalg.norm(corrected_delta))
    if proposed_norm > 0.0 and corrected_norm > 0.0:
        direction_dot = float(
            np.dot(proposed_delta, corrected_delta) / (proposed_norm * corrected_norm)
        )
    else:
        direction_dot = None
    projected_corrected = _projected_field(transform, corrected)
    corrected_inf = float(np.max(np.abs(corrected_delta)))
    if corrected_inf <= 1e-12:
        mechanism = "volume_correction_cancels_objective_step"
    elif corrected_inf <= MACHINE_SCALE_NORM:
        mechanism = "corrected_step_machine_scale"
    else:
        mechanism = "corrected_step_effective"
    record.update(
        {
            "volume_correction": {
                "bracketed": True,
                "kappa_volume": float(kappa_volume),
                "phi_corrected": float(phi_final),
                "volume_residual": abs(float(phi_final) - float(target)),
            },
            "phi_corrected": float(phi_final),
            "corrected_norms": _norms(corrected_delta, active),
            "corrected_projected_field_mean_abs_delta": float(
                np.mean(np.abs(projected_corrected[active] - _projected_field(transform, values)[active]))
            ),
            "corrected_mask_drift_max": float(
                np.max(np.abs(corrected[~active] - values[~active])) if bool((~active).any()) else 0.0
            ),
            "corrected_move_box_violation_max": float(
                max(0.0, np.max(np.maximum(corrected - box_high, box_low - corrected)))
            ),
            "direction_dot_proposed_vs_corrected": direction_dot,
            "gradJ_dot_corrected": float(np.dot(grad_j, corrected_delta)),
            "gradV_dot_corrected": float(np.dot(grad_v, corrected_delta)),
            "corrected_rho_sha256": _array_sha256(corrected),
            "mechanism": mechanism,
        }
    )
    return record


def _load_events_cross_check() -> dict:
    import json

    attempts = []
    with (CAMPAIGN / "events.jsonl").open(encoding="utf-8") as handle:
        for line in handle:
            payload = json.loads(line)
            if payload.get("kind") == "objective_attempt":
                attempts.append(payload)
    last = attempts[-1]
    lookup = {}
    for candidate in last["phase2"]["candidates"]:
        bracket = candidate.get("bracket") or {}
        lookup[str(float(candidate["alpha"]))] = {
            "kappa_volume": candidate.get("kappa_volume"),
            "direction_inf_norm": bracket.get("direction_inf_norm"),
            "bracket_reason": bracket.get("reason"),
            "trial_objective": candidate.get("trial_objective"),
            "trial_downforce": candidate.get("trial_downforce"),
        }
    return {
        "attempt": last["attempt"],
        "level": last["level"],
        "input_rho_sha256": last["input_rho_sha256"],
        "parent_downforce_coefficient": last["parent_run"]["downforce_coefficient"],
        "candidates": lookup,
    }


def main() -> None:
    import json

    if ARTIFACT.exists():
        raise SystemExit(f"D0 artifact already exists: {ARTIFACT}")
    manifest = ca.load_json(MANIFEST_V5)
    recorded_manifest_sha = ca.sha256_file(MANIFEST_V5)
    sidecar = MANIFEST_V5.with_suffix(".json.sha256").read_text(encoding="utf-8").strip()
    if recorded_manifest_sha != sidecar:
        raise SystemExit("manifest v5 sidecar mismatch")
    checks = {
        "manifest_v5_sha256": recorded_manifest_sha,
        "campaign_meta_sha256": ca.sha256_file(CAMPAIGN / "campaign_meta.json"),
        "latest_sha256": ca.sha256_file(CAMPAIGN / "latest.json"),
        "state_0003_sha256": ca.sha256_file(CAMPAIGN / "checkpoints/state_0003.json"),
        "rho_0003_file_sha256": ca.sha256_file(CAMPAIGN / "checkpoints/rho_0003.npy"),
        "events_sha256": ca.sha256_file(CAMPAIGN / "events.jsonl"),
    }
    expected = {
        "campaign_meta_sha256": META_SHA256,
        "latest_sha256": LATEST_SHA256,
        "state_0003_sha256": STATE_SHA256,
        "rho_0003_file_sha256": STOP_RHO_FILE_SHA256,
        "events_sha256": EVENTS_SHA256,
    }
    for key, value in expected.items():
        if checks[key] != value:
            raise SystemExit(f"input hash mismatch for {key}: {checks[key]} != {value}")
    meta = ca.load_json(CAMPAIGN / "campaign_meta.json")
    if meta.get("status") != "blocked" or meta.get("reason") != "objective_rejected":
        raise SystemExit("campaign meta does not record the expected stopped state")

    rho = np.load(CAMPAIGN / "checkpoints/rho_0003.npy", allow_pickle=False)
    if rho.shape != (int(np.prod(SHAPE)),) or _array_sha256(rho) != STOP_RHO_SHA256:
        raise SystemExit("stopped rho does not match the recorded array hash")

    grid = load_fixed_grid_density_state(WORK / "topology_state.json")
    arrays = grid.arrays
    active = (
        (np.asarray(arrays["active_design_mask"]) > 0)
        & (np.asarray(arrays["allowed_mask"]) > 0)
        & ~(np.asarray(arrays["forbidden_mask"]) > 0)
        & ~(np.asarray(arrays["fixed_solid_mask"]) > 0)
    )
    level = next(level for level in manifest["levels"] if level["name"] == LEVEL_NAME)
    transform = DesignTransform(
        shape=SHAPE,
        spacing_m=SPACING_M,
        active_mask=active,
        filter=ConeFilter(SHAPE, SPACING_M, active, radius_m=manifest["filter_radius_m"]),
        projection=TanhProjection(level["b"], manifest["projection_eta"]),
        ramp=RampInterpolation(level["q"]),
    )
    spec = load_problem_spec(ROOT / manifest["problem_spec"]["path"])
    compiled = compile_problem(
        spec, volume_budget=VolumeBudget("volume_fraction_max", manifest["v_max_projected"])
    )
    from cfd_sdf.openfoam_oracle import OpenFoamOracle, OpenFoamOracleConfig

    adapter = OpenFoamOracle(
        OpenFoamOracleConfig(
            work_root=WORK,
            canonical_topology_state_json=ROOT / manifest["canonical_grid"]["path"],
            template_parent=ROOT / manifest["template_parent"]["path"],
            template_trial=CAMPAIGN / "template_trial",
            flow_case_id="straight",
            responses=("downforce",),
            run_root=CAMPAIGN / "runs",
            timeout_seconds=1800,
            docker_image=manifest["openfoam_image"],
        ),
        transform,
    )
    oracle = make_oracle_from_compiled(
        transform=transform,
        compiled=compiled,
        primal_evaluator=adapter.primal_evaluator,
        parent_evaluator=adapter.parent_evaluator,
        adjoint_evaluator=None,
    )
    parent = oracle.evaluate_parent(np.asarray(rho, dtype=np.float64))
    from scripts.pq3_3b_preflight_v6_2026_09 import run_evidence

    parent_run = run_evidence(parent)
    if parent_run.get("reused") is not True:
        raise SystemExit("parent case was not reused; D0 must not run OpenFOAM")
    parent_summary_sha = parent_run.get("summary_sha256")
    if parent_summary_sha != PARENT_SUMMARY_SHA256:
        raise SystemExit("reused parent summary hash mismatch")
    if abs(float(parent_run["downforce_coefficient"]) - PARENT_DOWNFORCE) > 1e-12:
        raise SystemExit("reused parent downforce mismatch")
    parent_objective, grad_j = canonical_objective_from(parent)
    indicator = np.zeros_like(rho, dtype=np.float64)
    indicator[active] = 1.0 / float(np.count_nonzero(active))
    grad_v = transform.pullback_from_projected(np.asarray(rho, dtype=np.float64), indicator)
    grad_v_fd = _fd_check_gradV(transform, rho, grad_v, active, FD_EPSILON)

    alphas = [alpha_diagnosis(
        transform=transform, rho=rho, grad_j=grad_j, grad_v=grad_v, alpha=alpha,
        move_limit=level["move_limit"], target=manifest["registered_target"],
        volume_tolerance=manifest["volume_tolerance"],
    ) for alpha in manifest["phase2_policy"]["alpha_ladder"]]

    events_cross = _load_events_cross_check()
    cross_check = []
    for record in alphas:
        reference = events_cross["candidates"].get(str(record["alpha"]))
        kappa = (record.get("volume_correction") or {}).get("kappa_volume")
        cross_check.append(
            {
                "alpha": record["alpha"],
                "recomputed_kappa_volume": kappa,
                "campaign_kappa_volume": reference.get("kappa_volume") if reference else None,
                "kappa_match": (
                    reference is not None
                    and kappa is not None
                    and abs(kappa - float(reference["kappa_volume"])) <= 1e-12
                ),
                "recomputed_direction_inf_norm": record["corrected_norms"]["inf_norm"] if record.get("corrected_norms") else 0.0,
                "campaign_direction_inf_norm": reference.get("direction_inf_norm") if reference else None,
            }
        )

    mechanism_counts: dict[str, int] = {}
    for record in alphas:
        mechanism_counts[record["mechanism"]] = mechanism_counts.get(record["mechanism"], 0) + 1

    artifact = {
        "kind": "pq3_3b_stopped_state_diagnosis",
        "schema_version": 1,
        "plan": {
            "path": str(PLAN.relative_to(ROOT)),
            "sha256": ca.sha256_file(PLAN),
        },
        "input_verification": {
            "manifest_v5": checks["manifest_v5_sha256"],
            "campaign_meta_v5": checks["campaign_meta_sha256"],
            "latest_json": checks["latest_sha256"],
            "state_0003_json": checks["state_0003_sha256"],
            "rho_0003_file": checks["rho_0003_file_sha256"],
            "rho_array_sha256": STOP_RHO_SHA256,
            "events_jsonl": checks["events_sha256"],
            "outcome_v5": {
                "path": str(OUTCOME_V5.relative_to(ROOT)),
                "sha256": ca.sha256_file(OUTCOME_V5),
            },
            "all_hashes_verified": True,
        },
        "parent": {
            "level": LEVEL_NAME,
            "reused": parent_run.get("reused"),
            "case_dir": parent_run.get("case_dir"),
            "summary_json": parent_run.get("summary_json"),
            "summary_sha256": parent_summary_sha,
            "downforce_coefficient": parent_run.get("downforce_coefficient"),
            "primal_iterations": parent_run.get("primal_iterations"),
            "adjoint_iterations": parent_run.get("adjoint_iterations"),
            "canonical_objective": float(parent_objective),
            "canonical_gradient_sha256": _array_sha256(grad_j),
            "projected_volume_gradient_sha256": _array_sha256(grad_v),
            "projected_volume_gradient_inf_peak": float(np.max(np.abs(grad_v[active]))),
        },
        "gradV_fd_check": grad_v_fd,
        "alpha_records": alphas,
        "events_cross_check": {
            "attempt": events_cross["attempt"],
            "level": events_cross["level"],
            "candidates": cross_check,
        },
        "summary": {
            "registered_alphas": list(manifest["phase2_policy"]["alpha_ladder"]),
            "mechanism_counts": mechanism_counts,
            "frozen_box_face_cells": alphas[0]["frozen_box_face_cells"],
            "active_cells_at_zero": alphas[0]["active_cells_at_zero"],
            "active_cells_at_one": alphas[0]["active_cells_at_one"],
            "no_new_openfoam_evaluations": True,
            "recomputed_matches_campaign_kappa_all_alphas": all(
                entry["kappa_match"] for entry in cross_check
            ),
        },
        "claims_supported": [
            "the stopped parent gradient and all registered alpha candidates were reconstructed from verified saved artifacts without a new solver run",
            "the per-alpha pre/post-correction norms, direction dots, grad J / grad V directional derivatives and mask/box verdicts are measured",
        ],
        "claims_not_supported": [
            "small corrected updates or small objective changes are not convergence or KKT evidence",
            "no new physics evaluation is included in this diagnosis",
        ],
    }
    ARTIFACT.write_text(json.dumps(artifact, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(artifact["summary"], indent=2))


if __name__ == "__main__":
    main()
