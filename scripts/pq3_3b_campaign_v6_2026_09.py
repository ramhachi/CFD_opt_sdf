"""PQ3.3b v6 registered campaign (inequality Phase 2 policy).

Resumes at the v6 manifest's input_stop_state level with the registered
``objective-oc-inequality-v1`` policy: Phase 1 restoration to the formation
target, then objective sign-step ladder under the original ``V <= Vmax``,
machine-scale rejection and the extractability guard. Checkpoints and resume
follow the v4 machinery; the long run is bounded by the manifest's per-level
max_attempts. The runner verifies the entry-preflight pass, the D2 change
manifest and every registered input hash before touching the output directory.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from cfd_sdf import campaign_assertions as ca  # noqa: E402
from cfd_sdf.design_transform import ConeFilter, DesignTransform, RampInterpolation, TanhProjection  # noqa: E402
from cfd_sdf.fixed_grid_primal import load_fixed_grid_density_state  # noqa: E402
from cfd_sdf.openfoam_oracle import OpenFoamOracle, OpenFoamOracleConfig  # noqa: E402
from cfd_sdf.path_b_bracket import BracketSpec  # noqa: E402
from cfd_sdf.phase2_discreteness_direction import (  # noqa: E402
    POLICY_ID as PROJECTED_DIRECTION_POLICY_ID,
    evaluate_phase2_discreteness_direction,
)
from cfd_sdf.phase2_inequality_policy import (  # noqa: E402
    DISCRETENESS_POLICY_ID,
    POLICY_ID as INEQUALITY_POLICY_ID,
    evaluate_phase2_inequality,
    projected_discreteness_mean_nd,
)
from cfd_sdf.problem_spec import load_problem_spec  # noqa: E402
from cfd_sdf.problem_spec_compiler import VolumeBudget, compile_problem  # noqa: E402
from cfd_sdf.stage_t_loop import make_oracle_from_compiled  # noqa: E402
from scripts.pq3_3b_campaign_v4_2026_09 import (  # noqa: E402
    _append_event,
    _checkpoint,
    _load_checkpoint,
    _write_json_atomic,
    _path,
    _verify_ref,
)
from scripts.pq3_3b_preflight_v6_2026_09 import phi_of, run_evidence, run_restoration, sha256_array  # noqa: E402

MANIFEST = ROOT / "docs/evidence/pq3_3b_campaign_manifest_v6_2026_09.json"
D2_MANIFEST = ROOT / "docs/evidence/pq3_3b_d2_change_manifest_2026_09.json"
PREFLIGHT = ROOT / "docs/evidence/pq3_3b_v6_entry_preflight_2026_09.json"
D1_OUTCOME = ROOT / "docs/evidence/pq3_3b_d1_discriminant_outcome_2026_09.json"
WORK = ROOT / "work/df2_fd_refresh"
SHAPE = (60, 32, 24)
SPACING_M = 0.05


def verify_preconditions(*, resume: bool = False, manifest_path: Path | None = None) -> tuple[dict, Path]:
    manifest_path = Path(manifest_path) if manifest_path is not None else MANIFEST
    sidecar = manifest_path.with_suffix(".json.sha256").read_text(encoding="utf-8").strip()
    if ca.sha256_file(manifest_path) != sidecar:
        raise ValueError("campaign manifest sidecar mismatch")
    manifest = ca.load_json(manifest_path)
    if manifest.get("schema_version") not in (5, 6, 7, 8, 9, 10, 11, 12):
        raise ValueError("campaign manifest schema mismatch")
    learning = manifest.get("learning_campaign") or {}
    if learning:
        for key in ("max_fresh_attempts", "max_new_accepted_attempts"):
            value = learning.get(key)
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                raise ValueError(f"learning campaign requires a positive integer {key}")
    if "change_manifest_d2" in manifest and ca.sha256_file(D2_MANIFEST) != manifest["change_manifest_d2"]["sha256"]:
        raise ValueError("D2 change manifest hash mismatch")
    if "discriminant_outcome_d1" in manifest and ca.sha256_file(D1_OUTCOME) != manifest["discriminant_outcome_d1"]["sha256"]:
        raise ValueError("D1 outcome hash mismatch")
    for key, ref in manifest.get("pinned_evidence", {}).items():
        path = ROOT / ref["path"]
        actual = ca.tree_sha256(path) if path.is_dir() else ca.sha256_file(path)
        if actual != ref["sha256"]:
            raise ValueError(f"pinned evidence mismatch: {key}")
    preflight_path = ROOT / manifest["entry_preflight"]["artifact_path"]
    if ca.sha256_file(preflight_path) != manifest["entry_preflight"].get("artifact_sha256", ca.sha256_file(preflight_path)):
        raise ValueError("entry preflight artifact hash mismatch")
    preflight = ca.load_json(preflight_path)
    if preflight["summary"].get("entry_preflight_pass") is not True:
        raise ValueError("entry preflight did not pass; campaign refused")
    if ca.sha256_file(ROOT / manifest["entry_preflight"]["script_path"]) != manifest["entry_preflight"]["script_sha256"]:
        raise ValueError("entry preflight script hash mismatch")
    if ca.python_source_tree_sha256(ROOT / "src/cfd_sdf") != manifest["source_tree_python_sha256"]:
        raise ValueError("source tree differs from the v6 registration")
    for key in ("canonical_grid", "source_grid", "problem_spec", "noise_calibration"):
        _verify_ref(manifest["registered_inputs"][key])
    for key in ("template_parent", "template_trial", "solver_controls"):
        _verify_ref(manifest["registered_inputs"][key], directory=True)
    rho_ref = manifest["input_stop_state"]
    if "state_path" in rho_ref:
        if ca.sha256_file(ROOT / rho_ref["state_path"]) != rho_ref["state_sha256"]:
            raise ValueError("stop state file hash mismatch")
    rho_path = ROOT / rho_ref["rho_path"]
    if ca.sha256_file(rho_path) != rho_ref["rho_file_sha256"]:
        raise ValueError("stop rho file hash mismatch")
    rho = np.load(rho_path, allow_pickle=False)
    if sha256_array(rho) != rho_ref["rho_sha256"]:
        raise ValueError("stop rho array hash mismatch")
    image = subprocess.run(
        ["docker", "image", "inspect", manifest["openfoam_image"], "--format", "{{.Id}}"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    if image != manifest["openfoam_image_id"]:
        raise ValueError("OpenFOAM image ID differs from the registration")
    output = ROOT / manifest["output_directory"]
    if resume:
        if not output.is_dir():
            raise ValueError("resume output directory missing")
        incomplete = [
            case for root in (output / "runs", output / "terminal_independent")
            if root.is_dir() for case in root.glob("*/case")
            if not (case / "fixed_grid_primal_summary.json").is_file()
        ]
        if incomplete:
            raise ValueError(f"incomplete solver cases require recovery: {incomplete}")
        metadata = ca.load_json(output / "campaign_meta.json")
        if metadata.get("manifest_sha256") != sidecar or metadata.get("status") not in ("running", "blocked"):
            raise ValueError("resume campaign status mismatch")
        _load_checkpoint(output)
    else:
        if output.exists():
            raise ValueError(f"output directory already exists: {output}")
    return manifest, output


def _oracle(manifest: dict, transform, compiled, output: Path, run_root: Path):
    adapter = OpenFoamOracle(
        OpenFoamOracleConfig(
            work_root=WORK,
            canonical_topology_state_json=_path(manifest["registered_inputs"]["canonical_grid"]),
            template_parent=_path(manifest["registered_inputs"]["template_parent"]),
            template_trial=output / "template_trial",
            flow_case_id="straight",
            responses=("downforce",),
            run_root=run_root,
            timeout_seconds=1800,
            docker_image=manifest["openfoam_image"],
        ),
        transform,
    )
    return make_oracle_from_compiled(
        transform=transform,
        compiled=compiled,
        primal_evaluator=adapter.primal_evaluator,
        parent_evaluator=adapter.parent_evaluator,
        adjoint_evaluator=None,
    )


def _transform(manifest: dict, active: np.ndarray, level: dict) -> DesignTransform:
    return DesignTransform(
        shape=SHAPE,
        spacing_m=SPACING_M,
        active_mask=active,
        filter=ConeFilter(SHAPE, SPACING_M, active, radius_m=manifest["filter_radius_m"]),
        projection=TanhProjection(level["b"], manifest["projection_eta"]),
        ramp=RampInterpolation(level["q"]),
    )


def level_converged(*, accepted_count: int, window: list[dict], limits: dict, min_accepted: int) -> bool:
    """Registered v6 convergence window check (pure, unit-tested)."""
    return bool(
        accepted_count >= min_accepted
        and len(window) == limits["window_accepted"]
        and all(
            0 < item["objective_delta_abs"] <= limits["objective_delta_abs_max"]
            and item["projected_field_mean_abs_delta"] <= limits["projected_field_mean_abs_delta_max"]
            and item["projected_volume_delta_abs"] <= limits["projected_volume_delta_abs_max"]
            for item in window
        )
    )


def cap_stationarity_exit_allowed(
    *,
    enabled: bool,
    reasons: set,
    all_rejected_as: set,
    last_metric: dict | None,
    last_metric_limit: float,
    accepted_count: int,
    min_accepted: int,
) -> bool:
    """Registered cap-stationarity exit (pure, unit-tested).

    The accepted-step smallness criterion and the no-feasible-direction
    criterion are checked separately; the exit never claims convergence.
    """
    if not enabled or not all_rejected_as:
        return False
    if not set(reasons) <= set(all_rejected_as):
        return False
    if last_metric is None or last_metric["objective_delta_abs"] > last_metric_limit:
        return False
    return accepted_count >= min_accepted


def parent_discreteness_guard(transform, rho: np.ndarray, limit: float | None) -> dict:
    """Measure the registered parent invariant without invoking a flow solver."""
    if limit is None:
        return {"enabled": False, "mean_nd": None, "mean_nd_max": None, "pass": True}
    bound = float(limit)
    mean_nd = projected_discreteness_mean_nd(transform, rho)
    return {
        "enabled": True,
        "mean_nd": mean_nd,
        "mean_nd_max": bound,
        "pass": bool(mean_nd <= bound),
    }


def _stop(output: Path, reason: str, level: str) -> dict:
    meta = ca.load_json(output / "campaign_meta.json")
    _write_json_atomic(output / "campaign_meta.json", {**meta, "status": "blocked", "reason": reason, "level": level})
    result = {"status": "blocked", "reason": reason, "level": level}
    print(json.dumps(result), flush=True)
    return result


def _pause_learning(
    *, output: Path, manifest_sha: str, level: str, state: dict, rho: np.ndarray,
    window_criteria_observed: bool,
) -> dict:
    result = {
        "status": "paused_learning_budget",
        "level": level,
        "fresh_attempts": int(state["learning_attempt_count"]),
        "accepted_this_learning_campaign": int(state["learning_accepted_count"]),
        "accepted_count": int(state["accepted_count"]),
        "rho_sha256": sha256_array(rho),
        "registered_convergence_window_observed": bool(window_criteria_observed),
        "does_not_claim_convergence": True,
    }
    _append_event(output, {"kind": "learning_budget_stop", **result})
    _write_json_atomic(
        output / "campaign_meta.json",
        {
            "manifest_sha256": manifest_sha,
            "status": result["status"],
            "level": level,
            "learning_budget_stop": result,
        },
    )
    print(json.dumps(result), flush=True)
    return result


def evaluate_registered_phase2(*, manifest: dict, **kwargs):
    """Dispatch one Phase 2 attempt without changing registered v1/v2 behavior."""

    policy = manifest["phase2_policy"]
    policy_id = policy["id"]
    common = {
        **kwargs,
        "ladder": tuple(policy["alpha_ladder"]),
        "min_update_inf_norm": policy["min_corrected_update_inf_norm"],
        "extractability_fraction": policy["extractability_fraction"],
    }
    if policy_id == PROJECTED_DIRECTION_POLICY_ID:
        if bool(policy.get("volume_cap_correction", False)):
            raise ValueError(
                "projected discreteness direction does not permit volume correction"
            )
        return evaluate_phase2_discreteness_direction(
            **common,
            discreteness_mean_nd_max=policy["discreteness_mean_nd_max"],
            freeze_box_faces=bool(policy.get("freeze_exact_box_faces", True)),
        )
    if policy_id in (INEQUALITY_POLICY_ID, DISCRETENESS_POLICY_ID):
        return evaluate_phase2_inequality(
            **common,
            volume_cap_correction=bool(policy.get("volume_cap_correction", False)),
            discreteness_mean_nd_max=policy.get("discreteness_mean_nd_max"),
        )
    raise ValueError(f"unsupported Phase 2 policy id: {policy_id}")


def run_campaign(*, resume: bool = False, manifest_path: Path | None = None, max_new_attempts: int | None = None) -> dict:
    manifest_path = Path(manifest_path) if manifest_path is not None else MANIFEST
    manifest, output = verify_preconditions(resume=resume, manifest_path=manifest_path)
    spec = load_problem_spec(_path(manifest["registered_inputs"]["problem_spec"]))
    compiled = compile_problem(spec, volume_budget=VolumeBudget("volume_fraction_max", manifest["v_max_projected"]))
    grid = load_fixed_grid_density_state(_path(manifest["registered_inputs"]["canonical_grid"]))
    arrays = grid.arrays
    active = (
        (np.asarray(arrays["active_design_mask"]) > 0)
        & (np.asarray(arrays["allowed_mask"]) > 0)
        & ~(np.asarray(arrays["forbidden_mask"]) > 0)
        & ~(np.asarray(arrays["fixed_solid_mask"]) > 0)
    )
    forbidden = np.asarray(arrays["forbidden_mask"]) > 0
    fixed = np.asarray(arrays["fixed_solid_mask"]) > 0
    bracket = BracketSpec(epsilon=manifest["path_b"]["epsilon"], noise_floor_abs=manifest["path_b"]["noise_floor_abs"])
    levels = manifest["levels"]
    start_index = next(
        index for index, level in enumerate(levels) if level["name"] == manifest["input_stop_state"]["level"]
    )
    manifest_sha = ca.sha256_file(manifest_path)
    if resume:
        state, rho = _load_checkpoint(output)
        if manifest.get("learning_campaign") and not all(
            key in state
            for key in ("learning_attempt_count", "learning_accepted_count")
        ):
            raise ValueError("learning campaign checkpoint lacks budget counters")
    else:
        output.mkdir(parents=True)
        shutil.copytree(_path(manifest["registered_inputs"]["template_trial"]), output / "template_trial")
        _write_json_atomic(output / "campaign_meta.json", {"manifest_sha256": manifest_sha, "status": "running"})
        rho = np.load(ROOT / manifest["input_stop_state"]["rho_path"], allow_pickle=False)
        carryover = manifest.get("accepted_count_carryover", {})
        state = {
            "checkpoint_index": 0,
            "level_index": start_index,
            "accepted_count": int(carryover.get(levels[start_index]["name"], 0)),
            "attempts_this_cycle": 0,
            "metrics": list(manifest.get("carryover_metrics", [])),
            "completed_levels": [level["name"] for level in levels[:start_index]],
            "phase1_done": None,
        }
        if manifest.get("learning_campaign"):
            state["learning_attempt_count"] = 0
            state["learning_accepted_count"] = 0
        _checkpoint(output, state, np.asarray(rho, dtype=np.float64))
    for level_index in range(state["level_index"], len(levels)):
        level = levels[level_index]
        transform = _transform(manifest, active, level)
        oracle = _oracle(manifest, transform, compiled, output, output / "runs")
        if state["phase1_done"] is None or not state["phase1_done"]:
            phi_now = phi_of(transform, rho, active)
            # Phase 1 is formation-only: the ascent-only restoration raises the
            # projected volume to the formation target; a state already at or
            # above that floor (for example a v6 cap-policy resume) is done.
            if phi_now >= manifest["registered_target"] - manifest["volume_tolerance"]:
                state = {**state, "phase1_done": True}
            else:
                phase1, restored = run_restoration(
                    transform, oracle, active, forbidden, fixed, rho, level["move_limit"], level["name"]
                )
                _append_event(output, {"kind": "restoration", "level": level["name"], "record": phase1})
                if not phase1["reached_target"] or not all(step["accepted"] for step in phase1["steps"]):
                    return _stop(output, "restoration_failed", level["name"])
                rho = restored
                state = {**state, "phase1_done": True}
                _checkpoint(output, {**state, "checkpoint_index": state["checkpoint_index"] + 1}, rho)
        session_attempts = 0
        for attempt in range(state.get("attempts_this_cycle", 0), level["max_attempts"]):
            learning_campaign = manifest.get("learning_campaign") or {}
            if learning_campaign and (
                state["learning_attempt_count"]
                >= int(learning_campaign["max_fresh_attempts"])
                or state["learning_accepted_count"]
                >= int(learning_campaign["max_new_accepted_attempts"])
            ):
                return _pause_learning(
                    output=output,
                    manifest_sha=manifest_sha,
                    level=level["name"],
                    state=state,
                    rho=rho,
                    window_criteria_observed=False,
                )
            session_attempts += 1
            if learning_campaign:
                state["learning_attempt_count"] += 1
            discreteness_limit = manifest["phase2_policy"].get("discreteness_mean_nd_max")
            parent_guard = parent_discreteness_guard(transform, rho, discreteness_limit)
            if parent_guard["enabled"]:
                _append_event(
                    output,
                    {
                        "kind": "parent_discreteness_guard",
                        "level": level["name"],
                        "attempt": attempt + 1,
                        "rho_sha256": sha256_array(rho),
                        "mean_nd": parent_guard["mean_nd"],
                        "mean_nd_max": parent_guard["mean_nd_max"],
                        "pass": parent_guard["pass"],
                    },
                )
                if not parent_guard["pass"]:
                    return _stop(output, "parent_discreteness_limit_exceeded", level["name"])
            parent = oracle.evaluate_parent(rho)
            parent_run = run_evidence(parent)
            parent_downforce = float(parent_run["downforce_coefficient"])
            before = np.asarray(transform.forward(rho).rho_projected, dtype=np.float64)

            def trial(candidate, _oracle=oracle):
                result = _oracle.evaluate_values(candidate)
                return result, run_evidence(result)

            payload, accepted = evaluate_registered_phase2(
                manifest=manifest,
                transform=transform,
                parent_result=parent,
                rho_parent=rho,
                parent_downforce=parent_downforce,
                move_limit=level["move_limit"],
                v_max=manifest["v_max_projected"],
                objective_noise_threshold=manifest["noise_thresholds"]["objective"],
                downforce_noise_threshold=manifest["noise_thresholds"]["downforce"],
                bracket_spec=bracket,
                evaluate_values=oracle.evaluate_values,
                evaluate_trial=trial,
                return_rho=True,
            )
            evaluator_calls = payload.get("evaluator_calls") or {}
            payload["attempt_request_counts"] = {
                "parent_adjoint_requests": 1,
                "path_b_primal_requests": int(
                    evaluator_calls.get("path_b_evaluator_requests", 0)
                ),
                "trial_primal_requests": int(
                    evaluator_calls.get("trial_evaluator_requests", 0)
                ),
                "note": (
                    "requests are not fresh-run claims; Path B run evidence and "
                    "trial_run record summary hashes and reuse separately"
                ),
            }
            _append_event(
                output,
                {"kind": "objective_attempt", "level": level["name"], "attempt": attempt + 1,
                 "input_rho_sha256": sha256_array(rho), "parent_run": parent_run, "phase2": payload},
            )
            if accepted is None:
                exit_rule = manifest.get("cap_stationarity_exit") or {}
                reasons = {candidate["reason"] for candidate in payload["candidates"]}
                last_metric = state["metrics"][-1] if state["metrics"] else manifest.get("carryover_last_metric")
                exit_allowed = cap_stationarity_exit_allowed(
                    enabled=bool(exit_rule.get("enabled")),
                    reasons=reasons,
                    all_rejected_as=set(exit_rule.get("all_candidates_rejected_as", [])),
                    last_metric=last_metric,
                    last_metric_limit=float(exit_rule.get("last_accepted_objective_delta_max", 0.0)),
                    accepted_count=state["accepted_count"],
                    min_accepted=level["min_accepted_iterations"],
                )
                if exit_allowed:
                    repeat_oracle = _oracle(manifest, transform, compiled, output, output / "stationarity_repeat")
                    repeat = repeat_oracle.evaluate_values(rho)
                    repeat_run = run_evidence(repeat)
                    tolerance = float(exit_rule.get("reproducibility_tolerance", 1e-6))
                    reproducible = bool(
                        repeat.primal_converged
                        and abs(float(repeat.objective) - float(parent.objective)) <= tolerance
                        and abs(float(repeat_run["downforce_coefficient"]) - parent_downforce) <= tolerance
                    )
                    _append_event(
                        output,
                        {
                            "kind": "cap_stationarity_check",
                            "level": level["name"],
                            "attempt": attempt + 1,
                            "all_candidates_rejected_as": sorted(reasons),
                            "last_accepted_objective_delta_abs": last_metric["objective_delta_abs"] if last_metric else None,
                            "cumulative_accepted_count": state["accepted_count"],
                            "repeat_run": repeat_run,
                            "reproducible": reproducible,
                        },
                    )
                    if not reproducible:
                        return _stop(output, "stationarity_reproducibility_failed", level["name"])
                    _append_event(
                        output,
                        {"kind": "level_exit_cap_stationarity", "level": level["name"], "rho_sha256": sha256_array(rho),
                         "accepted_count": state["accepted_count"]},
                    )
                    state = {
                        **state,
                        "checkpoint_index": state["checkpoint_index"] + 1,
                        "level_index": level_index + 1,
                        "accepted_count": 0,
                        "attempts_this_cycle": 0,
                        "metrics": [],
                        "completed_levels": state["completed_levels"] + [level["name"]],
                        "phase1_done": False,
                        "exit_reason": "cap_stationarity_exit",
                    }
                    _checkpoint(output, state, rho)
                    break
                return _stop(output, "objective_rejected", level["name"])
            candidate = payload["candidates"][-1]
            if not candidate["accepted"] or payload["corrected_rho_sha256"] != sha256_array(accepted):
                raise ValueError("inequality acceptance or rho lineage mismatch")
            after = np.asarray(transform.forward(accepted).rho_projected, dtype=np.float64)
            metric = {
                "objective_delta_abs": float(parent.objective - candidate["trial_objective"]),
                "projected_field_mean_abs_delta": float(np.mean(np.abs(after[active] - before[active]))),
                "projected_volume_delta_abs": abs(float(candidate["projected_volume_delta"])),
            }
            rho = accepted
            state = {
                **state,
                "checkpoint_index": state["checkpoint_index"] + 1,
                "level_index": level_index,
                "accepted_count": state["accepted_count"] + 1,
                "attempts_this_cycle": attempt + 1,
                "metrics": (state["metrics"] + [metric])[-manifest["convergence"]["window_accepted"]:],
                "phase1_done": True,
                "last_trial_objective": candidate["trial_objective"],
                "last_trial_downforce": candidate["trial_downforce"],
            }
            learning_limit = learning_campaign.get(
                "max_new_accepted_attempts"
            )
            if learning_campaign:
                state["learning_accepted_count"] = (
                    int(state.get("learning_accepted_count", 0)) + 1
                )
            _checkpoint(output, state, rho)
            _append_event(output, {"kind": "objective_accepted", "level": level["name"], "rho_sha256": sha256_array(rho), "metric": metric})
            limits = manifest["convergence"]
            window = state["metrics"]
            window_criteria_observed = level_converged(
                accepted_count=state["accepted_count"],
                window=window,
                limits=limits,
                min_accepted=level["min_accepted_iterations"],
            )
            converged = bool(window_criteria_observed and not learning_campaign)
            if learning_campaign:
                _append_event(
                    output,
                    {
                        "kind": "learning_window_observation",
                        "level": level["name"],
                        "attempt": attempt + 1,
                        "registered_convergence_window_observed": bool(
                            window_criteria_observed
                        ),
                        "does_not_claim_convergence": True,
                    },
                )
            if not converged and max_new_attempts is not None and session_attempts >= max_new_attempts:
                result = {"status": "paused_session_budget", "level": level["name"], "attempts_this_session": session_attempts,
                          "accepted_count": state["accepted_count"], "rho_sha256": sha256_array(rho)}
                print(json.dumps(result), flush=True)
                return result
            learning_budget_exhausted = bool(
                learning_limit is not None
                and state["learning_accepted_count"] >= int(learning_limit)
            ) or bool(
                learning_campaign
                and state["learning_attempt_count"]
                >= int(learning_campaign["max_fresh_attempts"])
            )
            if not converged and learning_budget_exhausted:
                return _pause_learning(
                    output=output,
                    manifest_sha=manifest_sha,
                    level=level["name"],
                    state=state,
                    rho=rho,
                    window_criteria_observed=window_criteria_observed,
                )
            if converged:
                _append_event(output, {"kind": "level_converged", "level": level["name"], "accepted_count": state["accepted_count"], "rho_sha256": sha256_array(rho)})
                state = {
                    **state,
                    "checkpoint_index": state["checkpoint_index"] + 1,
                    "level_index": level_index + 1,
                    "accepted_count": 0,
                    "attempts_this_cycle": 0,
                    "metrics": [],
                    "completed_levels": state["completed_levels"] + [level["name"]],
                    "phase1_done": False,
                }
                _checkpoint(output, state, rho)
                break
        else:
            return _stop(output, "level_not_converged", level["name"])
    terminal_level = manifest["levels"][-1]
    terminal_oracle = _oracle(
        manifest, _transform(manifest, active, terminal_level), compiled, output,
        output / "terminal_independent",
    )
    terminal = terminal_oracle.evaluate_values(rho)
    phi = phi_of(_transform(manifest, active, terminal_level), rho, active)
    ca.assert_projected_volume_upper_bound(phi, manifest["v_max_projected"])
    terminal_run = run_evidence(terminal)
    if (
        not terminal.primal_converged
        or abs(float(terminal.objective) - float(state["last_trial_objective"])) > manifest["noise_thresholds"]["objective"]
        or abs(float(terminal_run["downforce_coefficient"]) - float(state["last_trial_downforce"])) > manifest["noise_thresholds"]["downforce"]
    ):
        return _stop(output, "independent_terminal_response_mismatch", terminal_level["name"])
    result = {
        "status": "terminal_evaluated_not_stage_s_qualified",
        "rho_sha256": sha256_array(rho),
        "projected_volume": phi,
        "objective": float(terminal.objective),
        "run": terminal_run,
    }
    _write_json_atomic(output / "terminal.json", result)
    _write_json_atomic(output / "campaign_meta.json", {"manifest_sha256": manifest_sha, "status": result["status"]})
    print(json.dumps(result), flush=True)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="PQ3.3b v6 registered campaign")
    parser.add_argument("--verify-preconditions", action="store_true")
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--manifest", default=str(MANIFEST))
    parser.add_argument("--max-new-attempts", type=int, default=None)
    args = parser.parse_args()
    if args.verify_preconditions:
        manifest, output = verify_preconditions(resume=args.resume, manifest_path=Path(args.manifest))
        print(json.dumps({"status": "preconditions_ok", "output": str(output), "policy": manifest["phase2_policy"]["id"], "volume_cap_correction": bool(manifest["phase2_policy"].get("volume_cap_correction", False))}))
    elif args.run:
        run_campaign(resume=args.resume, manifest_path=Path(args.manifest), max_new_attempts=args.max_new_attempts)
    else:
        parser.error("specify --verify-preconditions or --run")


if __name__ == "__main__":
    main()
