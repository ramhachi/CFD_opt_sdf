"""PQ3 first bounded closed loop: interior seed, real oracle, <= 3 iterations.

Runs the reduced problem (maximize downforce, projected-volume inequality) for
a small number of iterations with the real solver:

- parent: one qualified full-template run (primal + adjoint), gradient
  reconstructed from the same artifact;
- trials and the Path B bracket: primal-only runs with the adjoint solvers
  deactivated;
- a checkpoint is written and resumed to reproduce the decision history.

This is execution-capability evidence, not an improvement claim.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cfd_sdf.design_transform import DesignTransform, IdentityFilter, RampInterpolation, TanhProjection  # noqa: E402
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
SMOKE = ROOT / "work" / "pq0_2_smoke"
SPEC = SMOKE / "project_downforce_volume.yaml"
EVIDENCE = ROOT / "docs/evidence/pq3_first_closed_loop_v2_2026_09.json"
SEED_FLOOR = 1e-3
VOLUME_MARGIN = 0.002


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    state = load_fixed_grid_density_state(WORK / "topology_state.json")
    rho = np.asarray(state.arrays["rho"], dtype=np.float64)
    active = (
        (np.asarray(state.arrays["active_design_mask"]) > 0)
        & (np.asarray(state.arrays["allowed_mask"]) > 0)
        & ~(np.asarray(state.arrays["forbidden_mask"]) > 0)
        & ~(np.asarray(state.arrays["fixed_solid_mask"]) > 0)
    )
    seed = rho.copy()
    seed[active] = np.maximum(seed[active], SEED_FLOOR)
    seed_volume = float(seed[active].mean())
    volume_limit = seed_volume + VOLUME_MARGIN
    print(f"seed projected volume {seed_volume:.6f}, V_max {volume_limit:.6f}")

    transform = DesignTransform(
        shape=(60, 32, 24),
        spacing_m=0.05,
        active_mask=active,
        filter=IdentityFilter(shape=(60, 32, 24), spacing_m=0.05, active_mask=active),
        projection=TanhProjection(0.0, 0.5),
        ramp=RampInterpolation(0.0),
    )
    spec = load_problem_spec(SPEC)
    compiled = compile_problem(
        spec, volume_budget=VolumeBudget("volume_fraction_max", volume_limit)
    )
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
    oracle = make_oracle_from_compiled(
        transform=transform,
        compiled=compiled,
        primal_evaluator=adapter.primal_evaluator,
        adjoint_evaluator=adapter.adjoint_evaluator,
        parent_evaluator=adapter.parent_evaluator,
    )
    loop_spec = LoopSpec(
        transform=transform,
        compiled=compiled,
        move_limit=0.02,
        max_iterations=3,
        bracket=BracketSpec(epsilon=1e-4, noise_floor_abs=1e-6),
        trust_veto=False,
    )
    checkpoint = SMOKE / "checkpoint.json"
    result = run_stage_t_loop(
        spec=loop_spec,
        oracle=oracle,
        backend=ProjectedGradientBackend(),
        initial_rho=seed,
        checkpoint_path=checkpoint,
    )
    print("counts", result.counts)
    print("accepted", result.accepted, "rejected", result.rejected)
    first_trace = result.trace

    resume_result = run_stage_t_loop(
        spec=loop_spec,
        oracle=oracle,
        backend=ProjectedGradientBackend(),
        resume_from=checkpoint,
    )

    evidence = {
        "artifact_id": "pq3_first_closed_loop_v2_2026_09",
        "evidence_class": "bounded_closed_loop_capability",
        "issue": "PQ3 first bounded closed loop (Path B)",
        "reduced_problem": {
            "objective": "minimize -C_DF (maximize downforce)",
            "volume_limit": volume_limit,
            "seed_projected_volume": seed_volume,
            "seed_rule": "max(rho_canonical, 1e-3) on active cells",
            "seed_sha256": hashlib.sha256(np.ascontiguousarray(seed).tobytes()).hexdigest(),
            "bracket": {"epsilon": 1e-4, "noise_floor_abs": 1e-6},
            "move_limit": 0.02,
            "max_iterations": 3,
        },
        "inputs": {
            "problem_spec": {"path": str(SPEC.relative_to(ROOT)), "sha256": _sha256(SPEC)},
            "template_parent": "work/df2_fd_refresh/template_frozen",
            "template_trial": "work/pq0_2_smoke/template_trial",
            "canonical_topology_state": "work/df2_fd_refresh/topology_state.json",
        },
        "counts": result.counts,
        "trace": first_trace,
        "accepted": result.accepted,
        "rejected": result.rejected,
        "resume": {
            "counts": resume_result.counts,
            "accepted": resume_result.accepted,
            "rejected": resume_result.rejected,
            "trace_matches_first_iteration": (
                resume_result.trace[: len(first_trace)] == first_trace
            ),
        },
        "claims_supported": [
            "the real parent run produces values and adjoint fields in one qualified invocation",
            "trials and bracket runs use the primal-only template (no adjoint solver active)",
            "the loop trace records the bracket decision and the rollback lineage",
        ],
        "claims_not_supported": [
            "no improvement claim; this is execution capability",
            "no grid/target-physics claim",
        ],
    }
    EVIDENCE.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print("wrote", EVIDENCE)


if __name__ == "__main__":
    main()
