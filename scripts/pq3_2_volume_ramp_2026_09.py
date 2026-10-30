"""PQ3.2: volume-ramp growth with a declared minimum solid width, toward a Stage S-ready candidate.

PQ3.1 reached solver-field discreteness but the fixed upper-bound volume budget
gave no growth incentive and the 1.5-cell filter left features too thin to
extract. This driver follows the registered chunk schedule:

- declared minimum solid width 0.3 m -> cone filter radius 0.15 m (3 cells);
- the volume limit ramps upward in registered chunks (growth), then the
  projection/RAMP continuation sharpens at the final limit;
- Path B brackets, per-trial primal re-evaluation, per-chunk checkpoints.

Hard gates at the end: solver-field mean_nd <= 0.01, max_rho >= 0.9, projected
volume within the final limit plus the registered absolute tolerance.
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
from cfd_sdf.stage_t_loop import (  # noqa: E402
    LoopSpec,
    ProjectedGradientBackend,
    VolumeTargetBackend,
    make_oracle_from_compiled,
    run_stage_t_loop,
)

WORK = ROOT / "work" / "df2_fd_refresh"
OUT = Path(os.environ.get("PQ32_OUT", str(ROOT / "work" / "pq3_2_volume_ramp")))
SPEC = ROOT / "work" / "pq0_2_smoke" / "project_downforce_volume.yaml"
MANIFEST = Path(
    os.environ.get(
        "PQ32_MANIFEST",
        str(ROOT / "docs" / "evidence" / "pq3_2_volume_ramp_manifest_2026_09.json"),
    )
)
EVIDENCE = Path(
    os.environ.get(
        "PQ32_EVIDENCE",
        str(ROOT / "docs" / "evidence" / "pq3_2_volume_ramp_2026_09.json"),
    )
)
SHAPE = (60, 32, 24)
SEED_FLOOR = 1e-3
BRACKET = BracketSpec(epsilon=1e-4, noise_floor_abs=1e-6)
BOUND_MARGIN = 1e-4
DISCRETENESS_LIMIT = 0.01
MIN_MAX_RHO = 0.9


def _sha256(values: np.ndarray) -> str:
    return hashlib.sha256(np.ascontiguousarray(values, dtype=np.float64).tobytes()).hexdigest()


def _seed(active: np.ndarray, rho: np.ndarray) -> np.ndarray:
    from scipy import ndimage

    body = rho.reshape(SHAPE, order="F") > 0.05
    neighbourhood = ndimage.binary_dilation(body, iterations=2)
    floor_mask = neighbourhood.ravel(order="F") & active
    seed = rho.copy()
    seed[floor_mask] = np.maximum(seed[floor_mask], SEED_FLOOR)
    return seed


def _transform(active: np.ndarray, *, radius_m: float, b: float, q: float) -> DesignTransform:
    return DesignTransform(
        shape=SHAPE,
        spacing_m=0.05,
        active_mask=active,
        filter=ConeFilter(shape=SHAPE, spacing_m=0.05, active_mask=active, radius_m=radius_m),
        projection=TanhProjection(b, 0.5),
        ramp=RampInterpolation(q),
    )


def main() -> None:
    document = json.loads(MANIFEST.read_text(encoding="utf-8"))
    chunks = document["chunks"]
    if EVIDENCE.exists() or (OUT / "runs").exists():
        raise SystemExit(f"{OUT} already holds evidence; refusing to overwrite")
    OUT.mkdir(parents=True, exist_ok=True)

    state = load_fixed_grid_density_state(WORK / "topology_state.json")
    rho = np.asarray(state.arrays["rho"], dtype=np.float64)
    active = (
        (np.asarray(state.arrays["active_design_mask"]) > 0)
        & (np.asarray(state.arrays["allowed_mask"]) > 0)
        & ~(np.asarray(state.arrays["forbidden_mask"]) > 0)
        & ~(np.asarray(state.arrays["fixed_solid_mask"]) > 0)
    )
    seed = _seed(active, rho)
    spec = load_problem_spec(SPEC)
    base_limit = float(_transform(active, radius_m=0.15, b=0.0, q=0.0).forward(seed).rho_projected[active].mean())

    current = seed
    records = []
    for index, chunk in enumerate(chunks):
        transform = _transform(
            active,
            radius_m=float(chunk["filter_radius_m"]),
            b=float(chunk["b"]),
            q=float(chunk["q"]),
        )
        limit = base_limit + float(chunk["volume_delta"])
        compiled = compile_problem(
            spec, volume_budget=VolumeBudget("volume_fraction_max", limit)
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
        compiled_oracle = make_oracle_from_compiled(
            transform=transform,
            compiled=compiled,
            primal_evaluator=adapter.primal_evaluator,
            adjoint_evaluator=adapter.adjoint_evaluator,
            parent_evaluator=adapter.parent_evaluator,
        )
        backend = (
            VolumeTargetBackend(target=float(chunk["volume_target"]))
            if chunk.get("volume_target") is not None
            else ProjectedGradientBackend(bound_margin=BOUND_MARGIN)
        )
        result = run_stage_t_loop(
            spec=LoopSpec(
                transform=transform,
                compiled=compiled,
                move_limit=float(chunk["move_limit"]),
                max_iterations=int(chunk["iterations"]),
                bracket=BRACKET,
                trust_veto=False,
                oracle_profile="pq3_2_volume_ramp",
                backend_id=getattr(backend, "backend_id", "projected-gradient-constrained"),
            ),
            oracle=compiled_oracle,
            backend=backend,
            initial_rho=current,
            checkpoint_path=OUT / f"checkpoint_chunk{index:02d}.json",
        )
        beta = np.asarray(transform.forward(result.final_rho).beta, dtype=np.float64)
        records.append(
            {
                "chunk": index,
                "b": chunk["b"],
                "q": chunk["q"],
                "filter_radius_m": chunk["filter_radius_m"],
                "volume_delta": chunk["volume_delta"],
                "volume_target": chunk.get("volume_target"),
                "accepted": result.accepted,
                "rejected": result.rejected,
                "final_objective": result.final_evaluation.objective,
                "volume_constraint": result.final_evaluation.constraint_values.get(
                    "volume_fraction_max"
                ),
                "beta_mean_nd": float(np.mean(4.0 * beta[active] * (1.0 - beta[active]))),
                "beta_max_rho": float(beta[active].max()),
                "projected_volume": float(
                    transform.forward(result.final_rho).rho_projected[active].mean()
                ),
                "rho_sha256": _sha256(result.final_rho),
                "transform_hash": result.transform_hash,
            }
        )
        print(json.dumps(records[-1]), flush=True)
        current = result.final_rho

    final_beta = np.asarray(
        _transform(
            active,
            radius_m=float(chunks[-1]["filter_radius_m"]),
            b=float(chunks[-1]["b"]),
            q=float(chunks[-1]["q"]),
        ).forward(current).beta,
        dtype=np.float64,
    )
    projected_volume = float(
        _transform(
            active,
            radius_m=float(chunks[-1]["filter_radius_m"]),
            b=float(chunks[-1]["b"]),
            q=float(chunks[-1]["q"]),
        ).forward(current).rho_projected[active].mean()
    )
    final_limit = base_limit + float(chunks[-1]["volume_delta"])
    tolerance = float(document.get("volume_absolute_tolerance", 0.0))
    gates = {
        "beta_mean_nd": float(np.mean(4.0 * final_beta[active] * (1.0 - final_beta[active]))),
        "beta_mean_nd_limit": DISCRETENESS_LIMIT,
        "max_rho": float(final_beta[active].max()),
        "max_rho_min": MIN_MAX_RHO,
        "projected_volume": projected_volume,
        "final_limit": final_limit,
        "volume_violation": projected_volume - final_limit,
        "volume_absolute_tolerance": tolerance,
    }
    gates["discrete_candidate"] = bool(
        gates["beta_mean_nd"] <= DISCRETENESS_LIMIT
        and gates["max_rho"] >= MIN_MAX_RHO
        and gates["volume_violation"] <= tolerance
    )
    evidence = {
        "artifact_id": "pq3_2_volume_ramp_2026_09",
        "evidence_class": "bounded_closed_loop_production_regime",
        "issue": "PQ3.2 volume-ramp candidate",
        "manifest": {"path": str(MANIFEST.relative_to(ROOT)), "registered_before_computation": True},
        "chunks": records,
        "hard_gates": gates,
        "final_rho_sha256": _sha256(current),
        "final_design_rho": [float(v) for v in current],
        "claims_supported": ["the registered volume-ramp continuation ran end to end"],
        "claims_not_supported": ["no Stage S claim", "no target-physics claim"],
    }
    EVIDENCE.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(json.dumps(gates, indent=2))


if __name__ == "__main__":
    main()
