"""PQ3.1: production-regime Stage T closed loop (continuation) toward a discrete candidate.

The PQ3 capability loop used the identity transform and produced a grey field
that the composite Stage S entry gate correctly rejects. This driver runs the
same bounded loop with a declared production transform and a continuation
schedule:

    stage 1: cone filter, b=0,  q=0    (growth)
    stage 2: cone filter, b=8,  q=30   (sharpening)
    stage 3: cone filter, b=16, q=100  (binarization)

Each stage starts from the previous stage's final design, keeps the Path B
bracket and per-trial primal re-evaluation, and ends at its own checkpoint
(the transform hash changes per stage). The hard gates at the end:

    mean_nd = mean(4 rho (1 - rho)) <= 0.01
    max_rho >= 0.9
    volume constraint feasible
    every accepted step bracket-confirmed
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
    make_oracle_from_compiled,
    run_stage_t_loop,
)

WORK = ROOT / "work" / "df2_fd_refresh"
SMOKE = Path(os.environ.get("PQ31_OUT", str(ROOT / "work" / "pq3_1_production_loop")))
SPEC = ROOT / "work" / "pq0_2_smoke" / "project_downforce_volume.yaml"
MANIFEST = Path(
    os.environ.get(
        "PQ31_MANIFEST",
        str(ROOT / "docs" / "evidence" / "pq3_1_production_loop_manifest_2026_09.json"),
    )
)
EVIDENCE = Path(
    os.environ.get(
        "PQ31_EVIDENCE",
        str(ROOT / "docs" / "evidence" / "pq3_1_production_loop_2026_09.json"),
    )
)

def _stages_from_manifest(path: Path) -> tuple[dict, ...]:
    document = json.loads(path.read_text(encoding="utf-8"))
    return tuple(document["transform"]["continuation"])


STAGES = _stages_from_manifest(MANIFEST)
FILTER_RADIUS_M = 0.075
SEED_FLOOR = 1e-3
VOLUME_MARGIN = 0.002
BRACKET = BracketSpec(epsilon=1e-4, noise_floor_abs=1e-6)
BOUND_MARGIN = 1e-4
DISCRETENESS_LIMIT = 0.01
MIN_MAX_RHO = 0.9
SHAPE = (60, 32, 24)


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


def _make_transform(active: np.ndarray, *, b: float, q: float) -> DesignTransform:
    return DesignTransform(
        shape=SHAPE,
        spacing_m=0.05,
        active_mask=active,
        filter=ConeFilter(
            shape=SHAPE, spacing_m=0.05, active_mask=active, radius_m=FILTER_RADIUS_M
        ),
        projection=TanhProjection(b, 0.5),
        ramp=RampInterpolation(q),
    )


def main() -> None:
    if EVIDENCE.exists() or (SMOKE / "runs").exists():
        raise SystemExit(f"{SMOKE} already holds evidence; refusing to overwrite")
    if not MANIFEST.exists():
        raise SystemExit(f"the campaign manifest must be registered first: {MANIFEST}")
    SMOKE.mkdir(parents=True, exist_ok=True)

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

    stage1_transform = _make_transform(active, b=0.0, q=0.0)
    seed_volume = float(stage1_transform.forward(seed).rho_projected[active].mean())
    volume_limit = seed_volume + VOLUME_MARGIN
    compiled = compile_problem(
        spec, volume_budget=VolumeBudget("volume_fraction_max", volume_limit)
    )

    current = seed
    stage_records = []
    for stage in STAGES:
        transform = _make_transform(active, b=stage["b"], q=stage["q"])
        adapter = OpenFoamOracle(
            OpenFoamOracleConfig(
                work_root=WORK,
                canonical_topology_state_json=WORK / "topology_state.json",
                template_parent=WORK / "template_frozen",
                template_trial=SMOKE / "template_trial",
                flow_case_id="straight",
                responses=("downforce",),
                run_root=SMOKE / "runs",
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
        result = run_stage_t_loop(
            spec=LoopSpec(
                transform=transform,
                compiled=compiled,
                move_limit=stage["move_limit"],
                max_iterations=stage["iterations"],
                bracket=BRACKET,
                trust_veto=False,
                oracle_profile="pq3_1_production",
            ),
            oracle=compiled_oracle,
            backend=ProjectedGradientBackend(bound_margin=BOUND_MARGIN),
            initial_rho=current,
            checkpoint_path=SMOKE / f"checkpoint_{stage['name']}.json",
        )
        projected = transform.forward(result.final_rho).rho_projected
        mean_nd = float(np.mean(4.0 * result.final_rho[active] * (1.0 - result.final_rho[active])))
        stage_records.append(
            {
                "stage": stage["name"],
                "b": stage["b"],
                "q": stage["q"],
                "accepted": result.accepted,
                "rejected": result.rejected,
                "counts": result.counts,
                "final_objective": result.final_evaluation.objective,
                "constraints": dict(result.final_evaluation.constraint_values),
                "mean_nd_design": mean_nd,
                "max_rho_design": float(result.final_rho[active].max()),
                "projected_volume": float(projected[active].mean()),
                "rho_sha256": _sha256(result.final_rho),
                "transform_hash": result.transform_hash,
            }
        )
        print(json.dumps(stage_records[-1]), flush=True)
        current = result.final_rho

    final_rho = current
    mean_nd_final = float(np.mean(4.0 * final_rho[active] * (1.0 - final_rho[active])))
    max_rho_final = float(final_rho[active].max())
    gates = {
        "mean_nd": mean_nd_final,
        "mean_nd_limit": DISCRETENESS_LIMIT,
        "mean_nd_pass": mean_nd_final <= DISCRETENESS_LIMIT,
        "max_rho": max_rho_final,
        "max_rho_min": MIN_MAX_RHO,
        "max_rho_pass": max_rho_final >= MIN_MAX_RHO,
        "volume_limit": volume_limit,
        "volume_feasible": bool(
            stage_records[-1]["constraints"].get("volume_fraction_max", 1.0) <= 0.0
        ),
        "accepted_steps": sum(record["accepted"] for record in stage_records),
    }
    gates["discrete_candidate"] = bool(
        gates["mean_nd_pass"] and gates["max_rho_pass"] and gates["volume_feasible"]
    )
    evidence = {
        "artifact_id": "pq3_1_production_loop_2026_09",
        "evidence_class": "bounded_closed_loop_production_regime",
        "issue": "PQ3.1 discrete Stage T candidate",
        "manifest": {"path": str(MANIFEST.relative_to(ROOT)), "registered_before_computation": True},
        "stages": stage_records,
        "hard_gates": gates,
        "final_rho_sha256": _sha256(final_rho),
        "claims_supported": [
            "the continuation loop runs with the real oracle, Path B brackets and per-trial primal",
        ],
        "claims_not_supported": [
            "no Stage S claim", "no target-physics claim", "no grid-independent claim",
        ],
    }
    EVIDENCE.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(json.dumps(gates, indent=2))


if __name__ == "__main__":
    main()
