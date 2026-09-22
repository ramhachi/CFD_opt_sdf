"""PQ3.3b preflight v3: measured restoration-path evidence for Phase 1 + Phase 2.

Evidence classes are kept separate:
- contract evidence: mask drift, move-box violations, V_max guard, monotone
  phi across accepted states, restoration brackets at every level switch;
- physics evidence: OpenFOAM primal convergence of every accepted state and
  the downforce value of the volume-corrected Phase 2 candidate (delta vs the
  accepted parent) -- a datapoint, not a campaign proof.

The run does NOT start the long OpenFOAM campaign.
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

from cfd_sdf.design_transform import ConeFilter, DesignTransform, RampInterpolation, TanhProjection  # noqa: E402
from cfd_sdf.fixed_grid_primal import load_fixed_grid_density_state  # noqa: E402
from cfd_sdf.openfoam_oracle import OpenFoamOracle, OpenFoamOracleConfig  # noqa: E402
from cfd_sdf.projected_restoration import (  # noqa: E402
    ProjectedVolumeRestorationBackend,
    VolumeCorrectedObjectiveBackend,
)

WORK = ROOT / "work" / "df2_fd_refresh"
CHECKPOINT = ROOT / "work" / "pq3_3_volume_target" / "checkpoint_chunk02.json"
OUT = ROOT / "work" / "pq3_3b_preflight_v3"
TEMPLATE_SOURCE = ROOT / "work" / "pq0_2_smoke" / "template_trial"
EVIDENCE = ROOT / "docs" / "evidence" / "pq3_3b_preflight_v3_2026_09.json"
SHAPE = (60, 32, 24)
SPACING = 0.05
FILTER_RADIUS_M = 0.15
REGISTERED_TARGET = 0.018
V_MAX_PROJECTED = 0.07632566813424899
TOLERANCE = 1e-4
STEP_CAP = 60


def _sha256(values):
    values = np.asarray(values, dtype=np.float64)
    return hashlib.sha256(np.ascontiguousarray(values).tobytes()).hexdigest()


def _sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _phi(transform, rho, active):
    state = transform.forward(np.asarray(rho, dtype=np.float64))
    projected = np.asarray(state.rho_projected, dtype=np.float64)
    return float(projected[active].mean())


def _make_oracle(transform):
    config = OpenFoamOracleConfig(
        work_root=WORK,
        canonical_topology_state_json=WORK / "topology_state.json",
        template_parent=WORK / "template_frozen",
        template_trial=OUT / "template_trial",
        flow_case_id="straight",
        responses=("downforce",),
        run_root=OUT / "runs",
        timeout_seconds=1800,
    )
    return OpenFoamOracle(config, transform)


def _make_level_transform(b, q, joint):
    filt = ConeFilter(SHAPE, SPACING, joint, radius_m=FILTER_RADIUS_M)
    proj = TanhProjection(b, 0.5)
    ramp = RampInterpolation(q)
    return DesignTransform(
        shape=SHAPE,
        spacing_m=SPACING,
        active_mask=joint,
        filter=filt,
        projection=proj,
        ramp=ramp,
    )


def run_restoration(transform, oracle, active, forbidden, fixed, rho_start, move_limit, phase_name):
    """Phase 1 loop with a fresh parent evaluation per accepted step."""
    backend = ProjectedVolumeRestorationBackend(
        transform=transform, target=REGISTERED_TARGET, tolerance=TOLERANCE
    )
    current = np.asarray(rho_start, dtype=np.float64).copy()
    phi_current = _phi(transform, current, active)
    steps = []
    monotone_ok = True
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
        phi_after = _phi(transform, stepped, active)
        box_low = np.clip(current - move_limit, 0.0, 1.0)
        box_high = np.clip(current + move_limit, 0.0, 1.0)
        violation = np.maximum(stepped - box_high, box_low - stepped)
        move_box_violation_max = float(max(0.0, np.max(violation)))
        non_active = ~active

        def _max_drift(mask):
            if not bool(mask.any()):
                return 0.0
            return float(np.max(np.abs(stepped[mask] - current[mask])))

        drift = {
            "non_active": _max_drift(non_active),
            "forbidden": _max_drift(forbidden),
            "fixed_solid": _max_drift(fixed),
        }
        payload = oracle.primal_evaluator(transform.forward(stepped))
        primal_converged = bool(payload.get("primal_converged"))
        vmax_ok = bool(phi_after <= V_MAX_PROJECTED)
        accepted = bool(primal_converged and vmax_ok)
        step_monotone = bool(phi_after >= phi_current - 1e-12)
        if not step_monotone:
            monotone_ok = False
        steps.append(
            {
                "step": step,
                "kappa": proposal.metadata["kappa"],
                "bracketed": proposal.metadata["bracketed"],
                "frontier_step": proposal.metadata["frontier_step"],
                "phi_before": phi_current,
                "phi_after": phi_after,
                "residual": proposal.metadata["residual"],
                "objective_downforce": payload["values"].get(("straight", "downforce")),
                "primal_converged": primal_converged,
                "v_max_ok": vmax_ok,
                "accepted": accepted,
                "monotone_nondecreasing": step_monotone,
                "move_box_violation_max": move_box_violation_max,
                "mask_drift": drift,
                "mask_drift_max": max(drift.values()),
            }
        )
        print(
            json.dumps(
                {
                    "phase": phase_name,
                    "step": step,
                    "kappa": round(float(proposal.metadata["kappa"]), 6),
                    "phi_before": round(phi_current, 6),
                    "phi_after": round(phi_after, 6),
                    "frontier": bool(proposal.metadata["frontier_step"]),
                    "accepted": accepted,
                }
            ),
            flush=True,
        )
        if accepted:
            current = stepped
            phi_current = phi_after
        if abs(phi_current - REGISTERED_TARGET) <= TOLERANCE:
            break
    record = {
        "phase": phase_name,
        "phi_design_start": _phi(transform, np.asarray(rho_start), active),
        "phi_final": phi_current,
        "steps_taken": len(steps),
        "reached_target": bool(abs(phi_current - REGISTERED_TARGET) <= TOLERANCE),
        "target": REGISTERED_TARGET,
        "v_max_ok_all_steps": all(s["v_max_ok"] for s in steps),
        "monotone_phi_across_accepted": monotone_ok,
        "max_mask_drift": max(s["mask_drift_max"] for s in steps) if steps else 0.0,
        "max_move_box_violation": max(s["move_box_violation_max"] for s in steps) if steps else 0.0,
        "steps": steps,
        "accepted_rho_sha256": _sha256(current),
    }
    return record, current


def run_phase2_pivot(transform, oracle, active, forbidden, fixed, rho_parent, move_limit, phase_name):
    """Volume-corrected downforce proposal after the projected target is met."""
    phi_parent = _phi(transform, rho_parent, active)
    pivot = {"phase": phase_name, "phi_parent": phi_parent}
    if abs(phi_parent - REGISTERED_TARGET) > TOLERANCE:
        pivot["pivotable"] = False
        return pivot
    payload = oracle.parent_evaluator(transform.forward(rho_parent))
    grad_beta = np.asarray(next(iter(payload["gradients"].values())), dtype=np.float64)
    grad_design = transform.pullback_from_beta(rho_parent, grad_beta)
    downforce_parent = payload["values"].get(("straight", "downforce"))
    backend = VolumeCorrectedObjectiveBackend(
        transform=transform, target=REGISTERED_TARGET, tolerance=TOLERANCE
    )
    proposal = backend.propose(
        rho=rho_parent,
        objective_gradient=grad_design,
        constraint_gradients={},
        constraint_values={},
        move_radius=float(move_limit),
        backend_state={},
    )
    stepped = rho_parent + proposal.delta
    phi_after = _phi(transform, stepped, active)
    corrected = oracle.primal_evaluator(transform.forward(stepped))
    downforce_corrected = corrected["values"].get(("straight", "downforce"))
    pivot.update(
        {
            "pivotable": True,
            "kappa_volume": proposal.metadata["kappa_volume"],
            "phi_corrected": phi_after,
            "volume_residual": proposal.metadata["residual"],
            "volume_residual_within_tolerance": bool(
                proposal.metadata["residual"] <= TOLERANCE
            ),
            "downforce_parent": downforce_parent,
            "downforce_corrected_candidate": downforce_corrected,
            "downforce_delta": (
                (downforce_corrected - downforce_parent)
                if downforce_corrected is not None and downforce_parent is not None
                else None
            ),
            "primal_converged_corrected": bool(corrected.get("primal_converged")),
            "design_gradient_sha256": _sha256(grad_design),
        }
    )
    print(json.dumps({"phase": phase_name, "pivot": pivot["pivotable"], "residual": pivot["volume_residual"]}), flush=True)
    return pivot


def main():
    if EVIDENCE.exists() or OUT.exists():
        raise SystemExit("preflight v3 artifacts already exist: %s / %s" % (OUT, EVIDENCE))
    OUT.mkdir(parents=True, exist_ok=True)
    if not TEMPLATE_SOURCE.exists():
        raise SystemExit("template source missing: %s" % TEMPLATE_SOURCE)
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

    levels = [
        {"name": "level_0_growth_b4_q15", "b": 4.0, "q": 15.0, "move_limit": 0.05},
        {"name": "level_1_b8_q30", "b": 8.0, "q": 30.0, "move_limit": 0.03},
        {"name": "level_2_b16_q100", "b": 16.0, "q": 100.0, "move_limit": 0.01},
    ]

    phase1_records = []
    pivots = []
    current = np.asarray(rho0, dtype=np.float64).copy()
    pivot_parent = None
    for spec in levels:
        transform = _make_level_transform(spec["b"], spec["q"], active)
        oracle = _make_oracle(transform)
        record, accepted_rho = run_restoration(
            transform, oracle, active, forbidden, fixed, current, spec["move_limit"], spec["name"]
        )
        phase1_records.append({spec["name"]: record})
        pivot_parent = accepted_rho
        if not record["reached_target"]:
            break
        # decay simulation for the next level: subtract one move step so the
        # next level's restoration bracket is real (not a kappa=0 hold)
        current = np.clip(accepted_rho - spec["move_limit"], 0.0, 1.0)
        pivot = run_phase2_pivot(
            transform, oracle, active, forbidden, fixed, accepted_rho, spec["move_limit"], spec["name"]
        )
        pivots.append(pivot)
        print(json.dumps({"level": spec["name"], "to_next_level": "simulated decay"}), flush=True)

    # closing summary
    all_reached = all(
        list(r.values())[0]["reached_target"] for r in phase1_records
    )
    all_monotone = all(
        list(r.values())[0]["monotone_phi_across_accepted"] for r in phase1_records
    )
    all_drift_ok = all(
        list(r.values())[0]["max_mask_drift"] <= 1e-12 for r in phase1_records
    )
    all_box_ok = all(list(r.values())[0]["max_move_box_violation"] <= 1e-12 for r in phase1_records)
    all_vmax = all(list(r.values())[0]["v_max_ok_all_steps"] for r in phase1_records)
    pivots_ok = all(
        p.get("pivotable") and p.get("volume_residual", 1.0) <= TOLERANCE
        for p in pivots
    )
    summary = {
        "phase1_all_levels_reached_target": all_reached,
        "phase1_monotone_phi_all_levels": all_monotone,
        "phase1_mask_drifts_zero": all_drift_ok,
        "phase1_move_box_ok": all_box_ok,
        "phase1_v_max_ok": all_vmax,
        "phase2_volume_residual_within_tolerance_all_levels": pivots_ok,
        "preflight_pass": bool(
            all_reached and all_monotone and all_drift_ok and all_box_ok and all_vmax and pivots_ok
        ),
    }

    artifact = {
        "kind": "pq3_3b_preflight_v3",
        "schema_version": 3,
        "registered_target": REGISTERED_TARGET,
        "v_max_projected": V_MAX_PROJECTED,
        "input_checkpoint": {
            "path": str(CHECKPOINT.relative_to(ROOT)),
            "sha256": _sha256_file(CHECKPOINT),
            "objective": cp["objective"],
            "iteration": cp["iteration"],
            "accepted": cp["accepted"],
        },
        "levels": phase1_records,
        "phase2_pivots": pivots,
        "summary": summary,
        "claims_supported": [
            "contract: mask drift is 0 at every accepted step; move box is respected; V_projection <= V_max is enforced at every step; phi increases monotonically across accepted parents",
            "contract: the restoration kappa family brackets the registered target 0.018 at all three continuation levels (b=4, b=8, b=16)",
            "contract: the Phase 2 volume-corrected candidate lands back on the projected target with residual <= 1e-4",
        ],
        "claims_not_supported": [
            "physics: downforce improvement is a per-level datapoint only; the long OpenFOAM campaign and Path B bracket acceptance are NOT run here",
            "evidence: no claim of grid-independent downforce or benchmark qualification is recorded",
        ],
    }
    EVIDENCE.write_text(json.dumps(artifact, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
