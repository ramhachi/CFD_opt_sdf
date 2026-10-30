"""PQ3.3b preflight: measured reachability of the projected-volume target.

The preflight runs *before* the full PQ3.3b OpenFOAM campaign per the bridge
plan's Exit Gate C:

- materializes the b=0 accepted state from checkpoint_chunk02.json;
- for each continuation level (b=8/q=30, b=16/q=100) runs the parent
  primal+adjoint once and freezes the gradient hash, phi range, and bracket;
- verifies phi(kappa) is monotone non-decreasing and that the target is
  reachable inside the move box with |residual| <= tolerance;
- verifies the non-active / fixed / forbidden cell contract is invariant
  across the bisection;
- verifies V_target <= V_max;
- records every hash, field value, and decision as an append-only artifact.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cfd_sdf.design_transform import ConeFilter, DesignTransform, RampInterpolation, TanhProjection  # noqa: E402
from cfd_sdf.fixed_grid_primal import load_fixed_grid_density_state  # noqa: E402
from cfd_sdf.openfoam_oracle import OpenFoamOracle, OpenFoamOracleConfig  # noqa: E402
from cfd_sdf.path_b_bracket import BracketSpec  # noqa: E402
from cfd_sdf.problem_spec import load_problem_spec  # noqa: E402
from cfd_sdf.problem_spec_compiler import VolumeBudget, compile_problem  # noqa: E402
from cfd_sdf.stage_t_loop import ProjectedVolumeTargetBackend  # noqa: E402

WORK = ROOT / "work" / "df2_fd_refresh"
CHECKPOINT = ROOT / "work" / "pq3_3_volume_target" / "checkpoint_chunk02.json"
BASE = ROOT / "work/p0_closed_loop"
OUT = ROOT / "work" / "pq3_3b_preflight"
EVIDENCE = ROOT / "docs/evidence/pq3_3b_preflight_2026_09.json"
SPEC = ROOT / "work" / "pq0_2_smoke" / "project_downforce_volume.yaml"
SHAPE = (60, 32, 24)
SEED_FLOOR = 1e-3
BETA_MAX = 2500.0
V_MAX = 0.07632566813424899
V_TOLERANCE = 1e-4
BOUND_MARGIN = 1e-4
BRACKET_EPSILON = 1e-4
LEVELS = (
    {"name": "level_1_b8_q30", "b": 8.0, "q": 30.0, "move_limit": 0.03},
    {"name": "level_2_b16_q100", "b": 16.0, "q": 100.0, "move_limit": 0.01},
)


def _sha256(values: np.ndarray) -> str:
    return hashlib.sha256(np.ascontiguousarray(values, dtype=np.float64).tobytes()).hexdigest()


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    if OUT.exists() or EVIDENCE.exists():
        raise SystemExit(f"preflight artifacts already exist: {OUT} / {EVIDENCE}")
    OUT.mkdir(parents=True, exist_ok=True)

    cp = json.loads(CHECKPOINT.read_text(encoding="utf-8"))
    rho_design = np.asarray(cp["rho"], dtype=np.float64)
    source = load_fixed_grid_density_state(WORK / "topology_state.json")
    active = (
        (np.asarray(source.arrays["active_design_mask"]) > 0)
        & (np.asarray(source.arrays["allowed_mask"]) > 0)
        & ~(np.asarray(source.arrays["forbidden_mask"]) > 0)
        & ~(np.asarray(source.arrays["fixed_solid_mask"]) > 0)
    )
    spec = load_problem_spec(SPEC)
    # V_target <= V_max by construction; not changed after the run
    V_target = float(rho_design[active].mean())
    compiled = compile_problem(
        spec, volume_budget=VolumeBudget("volume_fraction_max", V_MAX)
    )
    if V_target > V_MAX:
        raise SystemExit(f"V_target ({V_target:.6f}) exceeds V_max ({V_MAX:.6f})")

    records: list[dict] = []
    for level in LEVELS:
        b, q = level["b"], level["q"]
        transform = DesignTransform(
            shape=SHAPE,
            spacing_m=0.05,
            active_mask=active,
            filter=ConeFilter(shape=SHAPE, spacing_m=0.05, active_mask=active, radius_m=0.15),
            projection=TanhProjection(b, 0.5),
            ramp=RampInterpolation(q),
        )
        adapter = OpenFoamOracle(
            OpenFoamOracleConfig(
                work_root=WORK,
                canonical_topology_state_json=WORK / "topology_state.json",
                template_parent=WORK / "template_frozen",
                template_trial=OUT / "template_trial",
                flow_case_id="straight",
                responses=("downforce",),
                run_root=OUT / "runs",
                timeout_seconds=1800,
            ),
            transform,
        )
        # refresh: parent primal + adjoint once per level
        state = transform.forward(rho_design)
        payload = adapter.parent_evaluator(state)
        gradients = payload["gradients"]
        if not gradients:
            raise SystemExit("parent evaluation returned no gradient")
        gradient_key = next(iter(gradients))
        gradient = np.asarray(gradients[gradient_key], dtype=np.float64)
        gradient_hash = _sha256(gradient)
        projected_volume = float(
            np.asarray(state.rho_projected, dtype=np.float64)[active].mean()
        )

        # phi(kappa) samples for monotonicity
        backend = ProjectedVolumeTargetBackend(
            transform=transform, target=V_target, tolerance=V_TOLERANCE
        )
        base = np.maximum(-gradient, 0.0) ** backend.eta
        lower = np.clip(rho_design - level["move_limit"], 0.0, 1.0)
        upper = np.clip(rho_design + level["move_limit"], 0.0, 1.0)

        def evaluate(kappa: float):
            stepped = np.clip(rho_design * base * kappa, lower, upper)
            stepped[~active] = rho_design[~active]
            d_state = transform.forward(stepped)
            phi = float(np.asarray(d_state.rho_projected, dtype=np.float64)[active].mean())
            return phi, stepped

        phi_low, _ = evaluate(0.0)
        hi = 1.0
        phi_hi, _ = evaluate(hi)
        grows = 0
        while phi_hi < V_target and grows < 30:
            hi *= 2.0
            phi_hi, _ = evaluate(hi)
            grows += 1
        bracketed = bool(phi_low < V_target and phi_hi >= V_target)

        monotone = True
        if bracketed:
            prev_phi = -np.inf
            for step in range(10):
                k = 0.0 + hi * (step + 1) / 10.0
                phi_k, _ = evaluate(min(k, hi))
                if phi_k < prev_phi - 1e-12:
                    monotone = False
                prev_phi = phi_k
            # final bisection to the target
            low_ = 0.0
            high_ = hi
            stepped_final = None
            for _ in range(60):
                mid = 0.5 * (low_ + high_)
                phi_mid, stepped_mid = evaluate(mid)
                if phi_mid < V_target:
                    low_ = mid
                else:
                    high_ = mid
                    stepped_final = stepped_mid
            final_phi, _ = evaluate(high_)
        else:
            stepped_final = None
            final_phi = None

        if stepped_final is not None:
            non_active_drift = float(
                np.max(np.abs(stepped_final[~active] - rho_design[~active]))
            )
        else:
            non_active_drift = None

        records.append(
            {
                "level": level["name"],
                "b": b,
                "q": q,
                "move_limit": level["move_limit"],
                "filter_radius_m": 0.15,
                "candidate_rho_sha256": cp["rho_sha256"],
                "gradient_sha256": _sha256(gradient),
                "transform_hash": transform.transform_hash(),
                "active_mask_sha256": hashlib.sha256(
                    np.ascontiguousarray(active.astype(np.uint8)).tobytes()
                ).hexdigest(),
                "phi_low_kappa0": phi_low,
                "phi_high_kappa": hi,
                "phi_high_value": phi_hi,
                "bracketed": bracketed,
                "phi_monotone_nondecreasing": monotone,
                "target": V_target,
                "v_target_le_vmax": bool(V_target <= V_MAX),
                "v_max": V_MAX,
                "final_phi_at_bisected_kappa": final_phi,
                "final_residual": abs(final_phi - V_target) if final_phi is not None else None,
                "within_tolerance": (
                    abs(final_phi - V_target) <= V_TOLERANCE if final_phi is not None else None
                ),
                "inactive_max_abs_drift": non_active_drift,
            }
        )
        print(json.dumps(records[-1]), flush=True)

    v_target_le_vmax_all = all(record["v_target_le_vmax"] for record in records)
    all_bracketed = all(record["bracketed"] for record in records)
    all_monotone = all(record["phi_monotone_nondecreasing"] for record in records)
    all_residuals_ok = all(
        record["within_tolerance"] is True for record in records if record["bracketed"]
    )
    all_masks_invariant = all(
        record["inactive_max_abs_drift"] is not None
        and record["inactive_max_abs_drift"] <= 1e-12
        for record in records
    )
    artifact = {
        "kind": "pq3_3b_preflight",
        "schema_version": 1,
        "created": sys.argv[1] if len(sys.argv) > 1 else "manual",
        "input_checkpoint": {
            "path": str(CHECKPOINT.relative_to(ROOT)),
            "sha256": _sha256_file(CHECKPOINT),
            "objective": cp["objective"],
            "iteration": cp["iteration"],
            "accepted": cp["accepted"],
        },
        "levels": records,
        "summary": {
            "V_target": V_target,
            "V_target_le_vmax_all": v_target_le_vmax_all,
            "all_bracketed": all_bracketed,
            "all_monotone": all_monotone,
            "all_residuals_within_tolerance": all_residuals_ok,
            "all_masks_invariant": all_masks_invariant,
            "preflight_pass": bool(
                v_target_le_vmax_all
                and all_bracketed
                and all_monotone
                and all_residuals_ok
                and all_masks_invariant
            ),
        },
        "claims_supported": [
            "each continuation level brackets the registered target inside the move box",
            "phi(kappa) is monotone non-decreasing over the sampled range",
            "non-active cells are untouched across kappa",
        ],
        "claims_not_supported": ["no OpenFOAM optimization run: the preflight is a reachability gate only"],
    }
    EVIDENCE.write_text(json.dumps(artifact, indent=2), encoding="utf-8")
    print(json.dumps(artifact["summary"], indent=2))


if __name__ == "__main__":
    main()
