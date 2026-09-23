"""PQ3.3b preflight v6: centered Path B on a box-face tangent subspace.

The earlier preflights remain immutable diagnostics. This bounded experiment
records every failed alpha and uses two independent OpenFOAM runs for its
noise measurement. Exact design box-face cells stay fixed during Phase 2, so
the registered centered difference can test the full feasible proposal.
It does not start the long optimization campaign.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cfd_sdf.canonical_objective import (  # noqa: E402
    canonical_sense_sign,
    record_from_parent_result,
)
from cfd_sdf.design_transform import ConeFilter, DesignTransform, RampInterpolation, TanhProjection  # noqa: E402
from cfd_sdf.fixed_grid_primal import load_fixed_grid_density_state  # noqa: E402
from cfd_sdf.openfoam_oracle import OpenFoamOracle, OpenFoamOracleConfig  # noqa: E402
from cfd_sdf.path_b_bracket import BracketSpec  # noqa: E402
from cfd_sdf.phase2_policy import ALPHA_LADDER, evaluate_phase2  # noqa: E402
from cfd_sdf.problem_spec import load_problem_spec  # noqa: E402
from cfd_sdf.problem_spec_compiler import VolumeBudget, compile_problem  # noqa: E402
from cfd_sdf.projected_restoration import ProjectedVolumeRestorationBackend  # noqa: E402
from cfd_sdf.stage_t_loop import make_oracle_from_compiled  # noqa: E402

WORK = ROOT / "work" / "df2_fd_refresh"
CHECKPOINT = ROOT / "work" / "pq3_3_volume_target" / "checkpoint_chunk02.json"
PROBLEM_SPEC = ROOT / "work" / "pq0_2_smoke" / "project_downforce_volume.yaml"
OUT = ROOT / "work" / "pq3_3b_preflight_v6"
TEMPLATE_SOURCE = ROOT / "work" / "pq0_2_smoke" / "template_trial"
EVIDENCE = ROOT / "docs" / "evidence" / "pq3_3b_preflight_v6_2026_09.json"
NOISE_EVIDENCE = ROOT / "docs" / "evidence" / "pq3_3b_noise_calibration_v3_2026_09.json"
SHAPE = (60, 32, 24)
SPACING = 0.05
FILTER_RADIUS_M = 0.15
REGISTERED_TARGET = 0.018
V_MAX_PROJECTED = 0.07632566813424899
VOLUME_TOLERANCE = 1e-4
BRACKET_EPSILON = 1e-4
BRACKET_NOISE_FLOOR_ABS = 1e-6
STEP_CAP = 60
LEVELS = (
    {"name": "level_0_growth_b4_q15", "b": 4.0, "q": 15.0, "move_limit": 0.05, "max_iterations": 40},
    {"name": "level_1_b8_q30", "b": 8.0, "q": 30.0, "move_limit": 0.03, "max_iterations": 40},
    {"name": "level_2_b16_q100", "b": 16.0, "q": 100.0, "move_limit": 0.01, "max_iterations": 30},
)


def sha256_array(values) -> str:
    raw = np.ascontiguousarray(np.asarray(values, dtype=np.float64))
    return hashlib.sha256(raw.tobytes()).hexdigest()


def sha256_file(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def objective_accepted_lineage(previous_record: dict, rho: np.ndarray) -> dict:
    """Check that the next level starts from the previous Phase 2 design."""
    accepted = previous_record.get("objective_accepted") or {}
    expected = accepted.get("rho_sha256")
    actual = sha256_array(rho)
    return {
        "previous_objective_accepted_rho_sha256": expected,
        "input_rho_sha256": actual,
        "exact_rho_carryover": bool(expected is not None and expected == actual),
    }


def independent_noise_runs(run_a: dict, run_b: dict) -> bool:
    """Cache reuse cannot be interpreted as a solver-noise measurement."""
    return bool(
        run_a.get("case_dir")
        and run_b.get("case_dir")
        and run_a["case_dir"] != run_b["case_dir"]
        and run_a.get("reused") is False
        and run_b.get("reused") is False
        and run_a.get("summary_sha256")
        and run_b.get("summary_sha256")
    )


def completed_objective_chain(records: list[dict], levels: tuple[dict, ...]) -> bool:
    """Every registered level must produce an accepted objective design."""
    return bool(
        len(records) == len(levels)
        and all(
            record.get("level") == level["name"]
            and (record.get("objective_accepted") or {}).get("rho_sha256")
            for record, level in zip(records, levels, strict=True)
        )
    )


def phi_of(transform, rho, active):
    projected = np.asarray(
        transform.forward(np.asarray(rho, dtype=np.float64)).rho_projected,
        dtype=np.float64,
    )
    return float(projected[active].mean())


def run_evidence(result) -> dict:
    """Extract per-run traceability from an evaluator payload's run record."""
    payload = result.primal_artifact if result is not None else None
    if not isinstance(payload, dict):
        return {}
    record = payload.get("artifact", payload)
    summary = record.get("summary", {})
    return {
        "case_dir": record.get("case_dir"),
        "summary_json": record.get("summary_json"),
        "summary_sha256": record.get("summary_sha256"),
        "source_rho_sha256": record.get("source_rho_sha256"),
        "primal_iterations": record.get("primal_iterations"),
        "adjoint_iterations": record.get("adjoint_iterations"),
        "solver_status": record.get("summary", {}).get("status", result.solver_status),
        "reused": bool(record.get("reused", False)),
        "downforce_coefficient": (
            summary.get("downforce_coefficient") if isinstance(summary, dict) else None
        ),
    }


def make_canonical_oracle(transform, compiled, *, run_root=None):
    adapter = OpenFoamOracle(
        OpenFoamOracleConfig(
            work_root=WORK,
            canonical_topology_state_json=WORK / "topology_state.json",
            template_parent=WORK / "template_frozen",
            template_trial=OUT / "template_trial",
            flow_case_id="straight",
            responses=("downforce",),
            run_root=OUT / "runs" if run_root is None else run_root,
            timeout_seconds=1800,
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
    return adapter, oracle


def run_restoration(
    transform, oracle, active, forbidden, fixed, rho_start, move_limit, phase_name
):
    """Phase 1 loop: propose -> real primal -> accept (restoration_feasible)."""
    backend = ProjectedVolumeRestorationBackend(
        transform=transform, target=REGISTERED_TARGET, tolerance=VOLUME_TOLERANCE
    )
    current = np.asarray(rho_start, dtype=np.float64).copy()
    phi_current = phi_of(transform, current, active)
    steps = []
    for step in range(1, STEP_CAP + 1):
        proposal = backend.propose(
            rho=current,
            objective_gradient=None,
            constraint_gradients={},
            constraint_values={},
            move_radius=float(move_limit),
            backend_state={},
        )
        stepped = current + proposal.delta
        phi_after = phi_of(transform, stepped, active)
        box_low = np.clip(current - move_limit, 0.0, 1.0)
        box_high = np.clip(current + move_limit, 0.0, 1.0)
        drift_masks = {"non_active": ~active, "forbidden": forbidden, "fixed_solid": fixed}
        drift = {}
        for name, mask in drift_masks.items():
            if bool(mask.any()):
                drift[name] = float(np.max(np.abs(stepped[mask] - current[mask])))
            else:
                drift[name] = 0.0
        violation = np.maximum(stepped - box_high, box_low - stepped)
        move_box_violation_max = float(max(0.0, np.max(violation)))
        result = oracle.evaluate_values(stepped)
        evidence = run_evidence(result)
        evidence["transform_sha256"] = transform.transform_hash()
        primal_ok = bool(result.primal_converged)
        vmax_ok = bool(phi_after <= V_MAX_PROJECTED)
        target_not_overshot = bool(phi_after <= REGISTERED_TARGET + VOLUME_TOLERANCE)
        mask_ok = bool(max(drift.values()) == 0.0)
        box_ok = bool(move_box_violation_max <= 1e-12)
        growth_ok = bool(phi_after > phi_current or abs(phi_after - REGISTERED_TARGET) <= VOLUME_TOLERANCE)
        accepted = bool(
            primal_ok and vmax_ok and target_not_overshot
            and mask_ok and box_ok and growth_ok
        )
        steps.append(
            {
                "step": step,
                "kappa": proposal.metadata["kappa"],
                "bracketed": proposal.metadata["bracketed"],
                "frontier_step": proposal.metadata["frontier_step"],
                "phi_before": phi_current,
                "phi_after": phi_after,
                "residual": proposal.metadata["residual"],
                "primal_converged": primal_ok,
                "v_max_ok": vmax_ok,
                "target_not_overshot": target_not_overshot,
                "accepted": accepted,
                "move_box_violation_max": move_box_violation_max,
                "mask_drift_max": max(drift.values()),
                "run": evidence,
                "status": "restoration_feasible" if accepted else "rejected",
            }
        )
        print(
            json.dumps(
                {
                    "phase": phase_name,
                    "step": step,
                    "kappa": round(float(proposal.metadata["kappa"]), 6),
                    "phi": round(phi_after, 6),
                    "frontier": bool(proposal.metadata["frontier_step"]),
                    "accepted": accepted,
                }
            ),
            flush=True,
        )
        if accepted:
            current = stepped
            phi_current = phi_after
        else:
            break
        if abs(phi_current - REGISTERED_TARGET) <= VOLUME_TOLERANCE:
            break
    record = {
        "phase": phase_name,
        "phi_design_start": phi_of(transform, np.asarray(rho_start), active),
        "phi_final": phi_current,
        "steps_taken": len(steps),
        "reached_target": bool(abs(phi_current - REGISTERED_TARGET) <= VOLUME_TOLERANCE),
        "target": REGISTERED_TARGET,
        "v_max_ok": all(s["v_max_ok"] for s in steps),
        "max_mask_drift": max(s["mask_drift_max"] for s in steps) if steps else 0.0,
        "max_move_box_violation": max(s["move_box_violation_max"] for s in steps) if steps else 0.0,
        "steps": steps,
        "accepted_rho_sha256": sha256_array(current),
    }
    return record, current


def _trial(oracle):
    def evaluate(rho):
        result = oracle.evaluate_values(rho)
        return result, run_evidence(result)
    return evaluate


def main():
    if EVIDENCE.exists() or NOISE_EVIDENCE.exists() or OUT.exists():
        raise SystemExit("preflight v6 artifacts already exist; refusing to overwrite")
    OUT.mkdir(parents=True, exist_ok=True)
    if not TEMPLATE_SOURCE.exists():
        raise SystemExit(f"template source missing: {TEMPLATE_SOURCE}")
    shutil.copytree(TEMPLATE_SOURCE, OUT / "template_trial")

    cp = json.loads(CHECKPOINT.read_text(encoding="utf-8"))
    rho0 = np.asarray(cp["rho"], dtype=np.float64)
    source = load_fixed_grid_density_state(WORK / "topology_state.json")
    active = (
        (np.asarray(source.arrays["active_design_mask"]) > 0)
        & (np.asarray(source.arrays["allowed_mask"]) > 0)
        & ~(np.asarray(source.arrays["forbidden_mask"]) > 0)
        & ~(np.asarray(source.arrays["fixed_solid_mask"]) > 0)
    )
    forbidden = np.asarray(source.arrays["forbidden_mask"]) > 0
    fixed = np.asarray(source.arrays["fixed_solid_mask"]) > 0
    spec = load_problem_spec(PROBLEM_SPEC)
    compiled = compile_problem(
        spec, volume_budget=VolumeBudget("volume_fraction_max", V_MAX_PROJECTED)
    )
    objective_sense = str(spec.objectives[0].sense)
    sense_sign = canonical_sense_sign(objective_sense)

    # ---- noise calibration (registered BEFORE any Phase 2 candidate)
    b4_transform = DesignTransform(
        shape=SHAPE,
        spacing_m=SPACING,
        active_mask=active,
        filter=ConeFilter(SHAPE, SPACING, active, radius_m=FILTER_RADIUS_M),
        projection=TanhProjection(4.0, 0.5),
        ramp=RampInterpolation(15.0),
    )
    _, noise_oracle_a = make_canonical_oracle(
        b4_transform, compiled, run_root=OUT / "noise_repeat_a"
    )
    _, noise_oracle_b = make_canonical_oracle(
        b4_transform, compiled, run_root=OUT / "noise_repeat_b"
    )
    n1 = noise_oracle_a.evaluate_values(rho0)
    n2 = noise_oracle_b.evaluate_values(rho0)
    noise_a, noise_b = run_evidence(n1), run_evidence(n2)
    if not independent_noise_runs(noise_a, noise_b):
        raise RuntimeError("noise measurements were reused or share one OpenFOAM case")
    spread = abs(float(n1.objective) - float(n2.objective))
    downforce1 = run_evidence(n1).get("downforce_coefficient")
    downforce2 = run_evidence(n2).get("downforce_coefficient")
    downforce_spread = abs(float(downforce1) - float(downforce2))
    noise_threshold = max(1e-6, float(spread), float(downforce_spread))
    noise_record = {
        "kind": "pq3_3b_noise_calibration",
        "schema_version": 1,
        "measurement": "two independent OpenFOAM primals of identical rho via distinct fresh run roots",
        "rho_sha256": sha256_array(rho0),
        "canonical_objective_values": [float(n1.objective), float(n2.objective)],
        "canonical_objective_spread": float(spread),
        "raw_downforce_values": [float(downforce1), float(downforce2)],
        "raw_downforce_spread": float(downforce_spread),
        "run_a": noise_a,
        "run_b": noise_b,
        "independent_runs": True,
        "objective_noise_threshold": noise_threshold,
        "downforce_noise_threshold": noise_threshold,
    }
    NOISE_EVIDENCE.write_text(json.dumps(noise_record, indent=2), encoding="utf-8")
    print(json.dumps({"noise_threshold": noise_threshold}), flush=True)

    bracket_spec = BracketSpec(
        epsilon=BRACKET_EPSILON, noise_floor_abs=BRACKET_NOISE_FLOOR_ABS
    )
    levels_records = []
    accepted_rho = np.asarray(rho0, dtype=np.float64).copy()
    lineage_pass = True
    level_passes = []
    canonical_sign_pass = True
    path_b_pass = True
    objective_improvement_pass = True
    raw_improvement_pass = True
    volume_pass = True
    mask_pass = True
    box_pass = True
    phase1_contract_pass = True
    b16_improved = False
    for index, spec_level in enumerate(LEVELS):
        transform = DesignTransform(
            shape=SHAPE,
            spacing_m=SPACING,
            active_mask=active,
            filter=ConeFilter(SHAPE, SPACING, active, radius_m=FILTER_RADIUS_M),
            projection=TanhProjection(spec_level["b"], 0.5),
            ramp=RampInterpolation(spec_level["q"]),
        )
        record = {
            "level": spec_level["name"],
            "b": spec_level["b"],
            "q": spec_level["q"],
            "move_limit": spec_level["move_limit"],
            "input_rho_sha256": sha256_array(accepted_rho),
        }
        if index > 0:
            record["objective_lineage"] = objective_accepted_lineage(
                levels_records[-1], accepted_rho
            )
            if not record["objective_lineage"]["exact_rho_carryover"]:
                lineage_pass = False
                record["status"] = "objective_lineage_failed"
                levels_records.append(record)
                break
        _, oracle = make_canonical_oracle(transform, compiled)
        phase1, accepted_rho = run_restoration(
            transform, oracle, active, forbidden, fixed, accepted_rho,
            spec_level["move_limit"], spec_level["name"],
        )
        record["phase1"] = phase1
        phase1_ok = bool(
            phase1["reached_target"]
            and phase1["v_max_ok"]
            and phase1["max_mask_drift"] == 0.0
            and phase1["max_move_box_violation"] <= 1e-12
            and all(step["accepted"] for step in phase1["steps"])
        )
        if not phase1_ok:
            volume_pass = False
            mask_pass = mask_pass and phase1["max_mask_drift"] == 0.0
            box_pass = box_pass and phase1["max_move_box_violation"] <= 1e-12
            phase1_contract_pass = False
            record["status"] = "restoration_failed"
            levels_records.append(record)
            break
        # fresh parent evaluation (primal + adjoint) on the accepted design
        parent_result = oracle.evaluate_parent(accepted_rho)
        raw_downforce = float(run_evidence(parent_result)["downforce_coefficient"])
        raw_sens = np.asarray(
            next(iter(parent_result.primal_artifact["gradients"].values())),
            dtype=np.float64,
        )
        record["parent"] = {
            **dict(
                record_from_parent_result(
                    result=parent_result,
                    raw_downforce=raw_downforce,
                    raw_response_gradient=raw_sens,
                    objective_sense=f"{objective_sense}:downforce",
                    objective_sign=sense_sign,
                ).__dict__
            ),
            "run": run_evidence(parent_result),
        }
        if objective_sense != "maximize" or sense_sign != -1:
            canonical_sign_pass = False
        # The new policy freezes exact box-face cells in both the proposal and
        # volume correction, preserving a symmetric Path B direction.
        phase2, objective_rho = evaluate_phase2(
            transform=transform,
            parent_result=parent_result,
            rho_parent=accepted_rho,
            parent_downforce=raw_downforce,
            move_limit=spec_level["move_limit"],
            ladder=ALPHA_LADDER,
            target=REGISTERED_TARGET,
            v_max=V_MAX_PROJECTED,
            volume_tolerance=VOLUME_TOLERANCE,
            objective_noise_threshold=noise_threshold,
            downforce_noise_threshold=noise_threshold,
            bracket_spec=bracket_spec,
            evaluate_values=oracle.evaluate_values,
            evaluate_trial=_trial(oracle),
            return_rho=True,
            freeze_box_faces=True,
        )
        record["phase2"] = phase2
        if phase2.get("successful"):
            if objective_rho is None:
                raise RuntimeError("accepted Phase 2 result has no corrected rho")
            accepted_rho = np.asarray(objective_rho, dtype=np.float64).copy()
            accepted_hash = sha256_array(accepted_rho)
            if accepted_hash != phase2.get("corrected_rho_sha256"):
                raise RuntimeError("accepted Phase 2 rho hash disagrees with the ledger")
            if index == 2:
                b16_improved = True
            record["objective_accepted"] = {
                "status": "objective_accepted",
                "alpha": phase2["accepted_alpha"],
                "rho_sha256": accepted_hash,
            }
            levels_records.append(record)
        else:
            if objective_rho is not None:
                raise RuntimeError("failed Phase 2 result unexpectedly returned a rho")
            path_b_pass = False
            objective_improvement_pass = False
            raw_improvement_pass = False
            if index == 2:
                # A b=16 candidate must beat the solver noise for a v6 pass.
                b16_improved = False
            record["objective_accepted"] = None
            record["status"] = "phase2_failed"
            levels_records.append(record)
            break

    chain_reached_b16 = completed_objective_chain(levels_records, LEVELS)
    summary = {
        "evaluated_levels": [record["level"] for record in levels_records],
        "phase1_contract_pass": phase1_contract_pass,
        "exact_level_lineage_pass": lineage_pass,
        "canonical_objective_sign_pass": canonical_sign_pass,
        "path_b_bracket_pass": path_b_pass,
        "real_trial_objective_improvement_pass": objective_improvement_pass,
        "raw_downforce_improvement_pass": raw_improvement_pass,
        "mask_invariance_pass": mask_pass,
        "move_box_pass": box_pass,
        "projected_volume_pass": volume_pass,
        "b16_candidate_rule": {
            "chain_reached_b16": chain_reached_b16,
            "improved_candidate_at_b16": bool(b16_improved),
            "verdict": (bool(b16_improved) if chain_reached_b16 else False),
        },
        "preflight_pass": bool(
            chain_reached_b16
            and b16_improved
            and phase1_contract_pass
            and lineage_pass
            and canonical_sign_pass
            and path_b_pass
            and objective_improvement_pass
            and raw_improvement_pass
            and mask_pass
            and box_pass
            and volume_pass
        ),
    }

    artifact = {
        "kind": "pq3_3b_preflight_v6",
        "schema_version": 6,
        "phase2_policy": "freeze_exact_box_faces_for_centered_path_b",
        "registered_target": REGISTERED_TARGET,
        "v_max_projected": V_MAX_PROJECTED,
        "objective": {"sense": objective_sense, "canonical": "J = -downforce", "sense_sign": sense_sign},
        "noise_calibration": {
            "path": str(NOISE_EVIDENCE.relative_to(ROOT)),
            "objective_noise_threshold": noise_threshold,
            "downforce_noise_threshold": noise_threshold,
        },
        "alpha_ladder": list(ALPHA_LADDER),
        "levels": levels_records,
        "summary": summary,
        "claims_supported": [
            "contract: canonical objective sign and routing are measured on evaluated levels",
            "contract: objective-accepted rho is inherited exactly between evaluated levels",
            "diagnostic: exact box-face cells are fixed during Phase 2 proposals",
            "diagnostic: per-alpha Phase 2 failures are retained for each evaluated level",
        ],
        "claims_not_supported": [
            "no long OpenFOAM campaign is run here; feasibility is a preflight",
            "unreached levels have no preflight result and cannot be counted as passed",
            "no claim of grid-independent downforce or full-vehicle benchmark qualification",
        ],
    }
    EVIDENCE.write_text(json.dumps(artifact, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
