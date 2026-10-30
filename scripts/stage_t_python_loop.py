"""Python-driven Stage T optimization loop, bypassing the native ISQP optimizer.

Per iteration, starting from the last accepted canonical ``rho``:
  1. transfer canonical -> OpenFOAM source state (``rho_source = P @ rho_canonical``)
  2. inject into a T1 (active-design-cell) contract
  3. run the real primal + adjoint (one converged OpenFOAM run gives both the
     objective and, via reconstruction, the adjoint sensitivity)
  4. pull ``topOSens`` back to the canonical grid (``g = P.T @ topOSens``) and
     take a move-limited, volume-projected optimality-criteria step
  5. re-evaluate with a real run; accept only if it converged and did not
     make the objective worse than the current accepted state -- otherwise
     reject, shrink the move limit, and retry. An accepted run's objective
     and gradient become next iteration's starting point, so one real
     OpenFOAM run buys one iteration, not two.

Iteration 0 is seeded for free from the already-verified P0 artifacts in
``work/p0_closed_loop/`` (``primal_base`` for J0, ``canonical_gradient`` for g0)
instead of re-running the identical base case.

Reuses, rather than reimplements: ``ExactCartesianOverlapTransfer``,
``inject_canonical_state_into_fixed_grid_contract``, ``run_fixed_grid_primal_case``,
``reconstruct_and_write_canonical_gradient_transfer`` (backs the
``transfer-openfoam-gradient-to-canonical`` CLI), and fixed_grid_optimizer's
``_updated_density_arrays``/``_updated_topology_state`` to persist each accepted
canonical state in the same schema ``build_density_to_sdf_handoff`` expects.

The only new logic is the classic optimality-criteria update (``oc_step``)
with its volume-equality bisection over a Lagrange multiplier, plus the
accept/reject/retry acceptance rule around it: the native ISQP optimizer's
failure mode (mean density pinned at ~0.007) is precisely what an
unconstrained or unconditionally-accepted step reproduces, so volume is
driven explicitly and every step is checked against the current accepted
objective rather than hoped for.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cfd_sdf.canonical_grid_snapshot import load_and_verify_canonical_grid_snapshot
from cfd_sdf.fixed_grid_canonical_state_injection import (
    inject_canonical_state_into_fixed_grid_contract,
)
from cfd_sdf.fixed_grid_contract import _write_cell_vti
from cfd_sdf.fixed_grid_optimizer import _updated_density_arrays, _updated_topology_state
from cfd_sdf.fixed_grid_primal import load_fixed_grid_density_state, run_fixed_grid_primal_case
from cfd_sdf.openfoam_canonical_field_transfer import (
    reconstruct_and_write_canonical_gradient_transfer,
)
from cfd_sdf.openfoam_grid_transfer import ExactCartesianOverlapTransfer, UniformCartesianCellGrid
from cfd_sdf.problem_spec import load_problem_spec

BASE = ROOT / "work" / "p0_closed_loop"

RESPONSE_ID = "drag"  # only response declared in project.yaml; see report note
ADJOINT_SOLVER_ID = "downforce"
BASELINE_DOWNFORCE = 0.775975568032  # work/p0_closed_loop/primal_base/fixed_grid_primal_summary.json

MOVE_LIMIT = 0.06
V_FINAL = 0.25
V_RAMP_ITERS = 8


def _grid(section: dict) -> UniformCartesianCellGrid:
    return UniformCartesianCellGrid(
        origin=section["origin"], spacing=section["spacing"], cell_shape=section["cell_shape"]
    )


def build_transfer(provenance: dict) -> ExactCartesianOverlapTransfer:
    source = provenance["source"]
    target = provenance["target"]
    source_grid = _grid(source)
    target_grid = _grid(target)
    return ExactCartesianOverlapTransfer.build(
        source_grid=source_grid,
        target_grid=target_grid,
        source_active_mask=np.ones(source_grid.cell_count, dtype=bool),
        target_active_mask=np.ones(target_grid.cell_count, dtype=bool),
        expected_source_grid_sha256=source["block_mesh"]["grid_sha256"],
        expected_target_grid_sha256=target["grid_sha256"],
    )


def volume_fraction(rho: np.ndarray, active: np.ndarray) -> float:
    return float(np.mean(rho[active]))


def oc_step(
    g: np.ndarray,
    rho: np.ndarray,
    active: np.ndarray,
    move_limit: float,
    v_target: float,
    eta: float = 0.5,
    iters: int = 60,
    zero_floor: float = 0.0,
) -> np.ndarray:
    """Classic optimality-criteria update, move-limited and volume-projected.

    ``rho_new = clip(rho * (max(-dJ/drho, 0) / lambda) ** eta, rho - move,
    rho + move, 0, 1)`` with ``-dJ/drho = +g`` (topOSens is d(+downforce)/drho,
    J = -downforce): cells with positive ``g`` are where material helps, so
    they get a positive base and grow; everything else gets base 0 and is
    driven toward its lower move-limit bound. ``lambda`` (folded here into a
    single scalar multiplier ``kappa = lambda ** -eta``, since only that
    combination ever matters) is found by bisection in log-space -- the
    multiplicative update is monotone in ``kappa`` -- so that
    ``mean(rho_new[active]) == v_target`` (subject to feasibility).

    Being multiplicative, this update cannot move a cell that is already
    exactly zero (``0 * anything == 0``), which caps the achievable volume
    fraction when most of the active domain starts at ``rho == 0`` -- unless
    ``zero_floor > 0``, in which case only the multiplication (not the stored
    state or the move-limit box) treats an exactly-zero, otherwise-active
    cell as if it started at ``zero_floor``, so a favorable cell can be
    nudged out of zero by up to the move limit; an unfavorable zero cell
    (``base == 0``) is unaffected either way.
    """

    lower_box = np.clip(rho - move_limit, 0.0, 1.0)
    upper_box = np.clip(rho + move_limit, 0.0, 1.0)
    base = np.maximum(g, 0.0) ** eta
    rho_eff = np.where(active & (rho <= 0.0), zero_floor, rho) if zero_floor > 0.0 else rho

    def candidate(kappa: float) -> np.ndarray:
        result = np.clip(rho_eff * base * kappa, lower_box, upper_box)
        result[~active] = rho[~active]
        return result

    def excess(kappa: float) -> float:
        return float(np.mean(candidate(kappa)[active])) - v_target

    kappa_lo, kappa_hi = 1.0, 1.0
    while excess(kappa_lo) > 0.0 and kappa_lo > 1.0e-16:
        kappa_lo /= 10.0
    while excess(kappa_hi) < 0.0 and kappa_hi < 1.0e16:
        kappa_hi *= 10.0
    for _ in range(iters):
        kappa_mid = (kappa_lo * kappa_hi) ** 0.5
        if excess(kappa_mid) > 0.0:
            kappa_hi = kappa_mid
        else:
            kappa_lo = kappa_mid
    return candidate((kappa_lo * kappa_hi) ** 0.5)


def _run_case(topology_state_json: Path, case_dir: Path):
    return run_fixed_grid_primal_case(
        topology_state_json,
        case_dir=case_dir,
        density_variant="seed",
        backend="auto",
        execute=True,
        adjoint_iterations=1,
        timeout_seconds=1800,
    )


def _extract(summary: dict) -> tuple[bool, float | None]:
    convergence = summary.get("convergence") or {}
    converged = bool(convergence.get("primal_converged"))
    downforce = summary.get("downforce_coefficient")
    finite = downforce is not None and bool(np.isfinite(downforce))
    return (converged and finite), (float(downforce) if finite else None)


MAX_ATTEMPTS_PER_ITERATION = 4


def main(
    n_iterations: int,
    out_dir: Path,
    *,
    move_limit_start: float = MOVE_LIMIT,
    v_final: float = V_FINAL,
    v_ramp_iters: int = V_RAMP_ITERS,
    zero_floor: float = 0.0,
) -> None:
    if out_dir.exists():
        raise SystemExit(f"{out_dir} already exists; remove it before re-running")
    out_dir.mkdir(parents=True)

    provenance = json.loads((BASE / "source_state" / "provenance.json").read_text())
    transfer = build_transfer(provenance)

    canonical0 = load_fixed_grid_density_state(BASE / "topology_state.json")
    rho = np.asarray(canonical0.arrays["rho"], dtype=np.float64).copy()
    active = (
        (np.asarray(canonical0.arrays["active_design_mask"]) > 0)
        & (np.asarray(canonical0.arrays["allowed_mask"]) > 0)
        & ~(np.asarray(canonical0.arrays["forbidden_mask"]) > 0)
        & ~(np.asarray(canonical0.arrays["fixed_solid_mask"]) > 0)
    )
    v0 = volume_fraction(rho, active)

    spec = load_problem_spec(BASE / "project.yaml")
    verified_snapshot = load_and_verify_canonical_grid_snapshot(
        BASE / "canonical_grid_snapshot.json", spec
    )
    base_contract_topology_state_json = BASE / "injected_contract" / "topology_state.json"
    source_state_provenance_json = BASE / "source_state" / "provenance.json"
    source_cell_labels_npy = BASE / "cell_order" / "source_global_cell_labels_by_xfastest.npy"

    # Seed iteration 0 for free from the already-verified P0 base run instead
    # of re-running the identical base case.
    g = np.load(BASE / "canonical_gradient" / "canonical_gradient.npz")[
        "top_o_sensitivity_gradient"
    ].astype(np.float64)
    current_J = -BASELINE_DOWNFORCE
    current_downforce = BASELINE_DOWNFORCE

    parent_state = canonical0.state
    parent_json = canonical0.topology_state_json

    history: list[dict] = []
    sign_checked = False
    move_limit = move_limit_start
    last_state_dir: Path | None = None

    for i in range(n_iterations):
        v_target = v0 + (v_final - v0) * min(1.0, (i + 1) / v_ramp_iters)

        if not np.isfinite(g).all():
            raise SystemExit(f"iteration {i}: canonical gradient contains non-finite values")
        dJ_drho = -g  # topOSens is d(+downforce)/drho; J = -downforce

        iteration_accepted = False
        for attempt in range(MAX_ATTEMPTS_PER_ITERATION):
            iter_dir = out_dir / f"iter_{i:03d}_attempt_{attempt:02d}"
            iter_dir.mkdir(parents=True)

            candidate_rho = oc_step(
                g, rho, active, move_limit, v_target, zero_floor=zero_floor
            )
            if not np.isfinite(candidate_rho).all():
                raise SystemExit(f"iteration {i}: candidate rho contains non-finite values")
            if candidate_rho.min() < -1.0e-9 or candidate_rho.max() > 1.0 + 1.0e-9:
                raise SystemExit(f"iteration {i}: candidate rho out of [0, 1]")
            candidate_rho = np.clip(candidate_rho, 0.0, 1.0)
            predicted_delta_J = float(np.dot(dJ_drho[active], (candidate_rho - rho)[active]))

            source_rho = transfer.transfer_state_to_source(candidate_rho)
            source_npz = iter_dir / "source_state.npz"
            np.savez(source_npz, source_rho_xfastest=source_rho)
            contract = inject_canonical_state_into_fixed_grid_contract(
                openfoam_source_state_npz=source_npz,
                source_state_provenance_json=source_state_provenance_json,
                topology_state_json=base_contract_topology_state_json,
                output_directory=iter_dir / "contract",
            )
            result = _run_case(contract.topology_state_json, iter_dir / "case")
            usable, downforce = _extract(result.summary)

            row = {
                "iteration": i,
                "attempt": attempt,
                "v_target": v_target,
                "move_limit": move_limit,
                "volume_fraction_before": volume_fraction(rho, active),
                "candidate_volume_fraction": volume_fraction(candidate_rho, active),
                "predicted_delta_J": predicted_delta_J,
                "primal_converged": usable,
                "downforce_coefficient": downforce,
            }

            if not usable:
                row["accepted"] = False
                row["reject_reason"] = "primal did not converge or produced a non-finite objective"
                history.append(row)
                print(json.dumps(row, indent=2))
                move_limit *= 0.5
                continue

            actual_J = -downforce
            actual_delta_J = actual_J - current_J
            row["actual_objective_J"] = actual_J
            row["actual_delta_J"] = actual_delta_J

            if not sign_checked:
                sign_checked = True
                if abs(predicted_delta_J) > 1.0e-9 and predicted_delta_J * actual_delta_J < 0.0:
                    row["accepted"] = False
                    row["sign_check"] = "FAILED"
                    history.append(row)
                    print(json.dumps(row, indent=2))
                    _write_history(out_dir, history)
                    raise SystemExit(
                        "Sign assertion failed on the first accepted step: predicted and "
                        f"actual objective changes disagree in sign (predicted="
                        f"{predicted_delta_J}, actual={actual_delta_J}). Stopping per spec."
                    )
                row["sign_check"] = "passed"

            if actual_delta_J > 1.0e-9:
                # Worse than the current accepted state: reject, shrink the
                # move limit, and retry -- a loop that cannot reject cannot
                # converge.
                row["accepted"] = False
                row["reject_reason"] = "objective got worse than the current accepted state"
                history.append(row)
                print(json.dumps(row, indent=2))
                move_limit *= 0.5
                continue

            grad_artifacts = reconstruct_and_write_canonical_gradient_transfer(
                case_dir=result.case_dir,
                adjoint_solver_id=ADJOINT_SOLVER_ID,
                block_mesh_dict=result.case_dir / "system" / "blockMeshDict",
                verified_snapshot=verified_snapshot,
                source_global_cell_labels_by_xfastest=source_cell_labels_npy,
                output_directory=iter_dir / "gradient",
                response_id=RESPONSE_ID,
            )
            with np.load(grad_artifacts.fields_npz) as payload:
                new_g = np.asarray(payload["top_o_sensitivity_gradient"], dtype=np.float64)

            # accept
            row["accepted"] = True
            history.append(row)
            print(json.dumps(row, indent=2))

            rho = candidate_rho
            g = new_g
            current_J = actual_J
            current_downforce = downforce

            state_dir = iter_dir / "canonical_state"
            density_vti_path = state_dir / "density.vti"
            arrays = _updated_density_arrays(canonical0.arrays, rho)
            _write_cell_vti(canonical0.grid, arrays, density_vti_path, kind="fixed_grid_density")
            new_state = _updated_topology_state(
                parent_state,
                parent_topology_state_json=parent_json,
                density_vti=density_vti_path,
                sensitivity_vti=grad_artifacts.fields_npz,
                update_vti=result.case_dir,
                optimizer_backend="python-optimality-criteria-volume-bisection",
            )
            state_json_path = state_dir / "topology_state.json"
            state_json_path.write_text(json.dumps(new_state, indent=2), encoding="utf-8")
            parent_state = new_state
            parent_json = state_json_path
            last_state_dir = state_dir
            iteration_accepted = True
            break

        if not iteration_accepted:
            print(f"iteration {i}: no attempt was accepted after {MAX_ATTEMPTS_PER_ITERATION} tries")

    _write_history(out_dir, history)
    print(f"final downforce_coefficient={current_downforce} baseline={BASELINE_DOWNFORCE}")
    print(f"final volume_fraction={volume_fraction(rho, active)}")
    if last_state_dir is not None:
        print(f"final canonical state: {last_state_dir / 'topology_state.json'}")
    else:
        print("no iteration was accepted; no final canonical state written")


def _write_history(out_dir: Path, history: list[dict]) -> None:
    (out_dir / "history.json").write_text(json.dumps(history, indent=2), encoding="utf-8")


def _selftest() -> None:
    """Assert-based check for oc_step, the one piece of new, non-trivial logic."""

    rng = np.random.default_rng(0)
    n = 200
    active = np.ones(n, dtype=bool)
    active[:20] = False  # some inactive cells that must never move
    rho = rng.uniform(0.05, 0.3, n)  # all strictly positive: multiplicative update can move them
    rho[~active] = rng.uniform(0.0, 1.0, (~active).sum())
    move_limit = 0.05

    # All-favorable g: every active cell can grow, so a target within the
    # move-limit box must be hit exactly, respecting the box and [0, 1], and
    # leaving inactive cells untouched.
    g_all_favorable = rng.uniform(0.1, 1.0, n)
    v_target = float(np.mean(rho[active])) + 0.03
    candidate = oc_step(g_all_favorable, rho, active, move_limit, v_target)
    assert np.array_equal(candidate[~active], rho[~active])
    assert np.all(candidate >= -1.0e-9) and np.all(candidate <= 1.0 + 1.0e-9)
    assert np.all(np.abs(candidate[active] - rho[active]) <= move_limit + 1.0e-9)
    achieved = float(np.mean(candidate[active]))
    assert abs(achieved - v_target) < 1.0e-6, achieved

    # Mixed g: unfavorable cells (g <= 0) must be driven exactly to their
    # lower move-limit bound, never grown, regardless of the volume target.
    g_mixed = rng.standard_normal(n)
    mixed_candidate = oc_step(g_mixed, rho, active, move_limit, v_target)
    unfavorable = active & (g_mixed <= 0.0)
    lower_box = np.clip(rho - move_limit, 0.0, 1.0)
    assert np.allclose(mixed_candidate[unfavorable], lower_box[unfavorable])

    # A cell starting at exactly zero cannot be moved by a pure multiplicative
    # update -- this is the documented structural limitation, not a bug.
    rho_with_zero = rho.copy()
    zero_idx = np.flatnonzero(active)[0]
    rho_with_zero[zero_idx] = 0.0
    candidate_zero = oc_step(g_all_favorable, rho_with_zero, active, move_limit, v_target)
    assert candidate_zero[zero_idx] == 0.0

    # With a zero_floor, a favorable zero cell CAN move (up to the move
    # limit); an unfavorable zero cell still cannot.
    floored = oc_step(
        g_mixed, rho_with_zero, active, move_limit, v_target, zero_floor=1.0e-3
    )
    if g_mixed[zero_idx] > 0.0:
        assert floored[zero_idx] > 0.0
    else:
        assert floored[zero_idx] == 0.0

    # An infeasible target (beyond what the move limit can reach in one step)
    # must saturate, not raise or overshoot.
    infeasible_target = 0.99
    saturated = oc_step(g_all_favorable, rho, active, move_limit, infeasible_target)
    upper_box = np.clip(rho + move_limit, 0.0, 1.0)
    assert np.all(saturated[active] <= upper_box[active] + 1.0e-9)

    print("stage_t_python_loop selftest: OK")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "selftest":
        _selftest()
        raise SystemExit(0)
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 16
    out = ROOT / "work" / (sys.argv[2] if len(sys.argv) > 2 else "stage_t_python_loop")
    kwargs = {}
    if len(sys.argv) > 3:
        kwargs["move_limit_start"] = float(sys.argv[3])
    if len(sys.argv) > 4:
        kwargs["v_final"] = float(sys.argv[4])
    if len(sys.argv) > 5:
        kwargs["v_ramp_iters"] = int(sys.argv[5])
    if len(sys.argv) > 6:
        kwargs["zero_floor"] = float(sys.argv[6])
    main(n, out, **kwargs)
