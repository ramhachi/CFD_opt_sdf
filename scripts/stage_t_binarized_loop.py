"""Stage T binarized optimization loop: Python-side Heaviside projection.

Reuses ``scripts/stage_t_python_loop.py`` (imported, not duplicated) for the
OC step, the transfer/injection/primal/adjoint plumbing, and canonical-state
persistence. What's new here, per ``docs/stage_t_optimizer_diagnosis_2026_09.md``'s
recommendation to own the projection in Python and leave OpenFOAM
(``function linear``) as a plain evaluator:

  1. ``project_beta``/``project_dbeta_drho``: the standard smoothed-Heaviside
     projection at threshold ``eta=0.5`` with sharpness ``b``. ``rho`` stays
     the design variable the OC step updates; ``beta(rho)`` is what actually
     gets injected into the solver contract (``rho_projected`` in the
     canonical-state schema -- see ``array_metadata.rho_projected`` in
     ``work/p0_closed_loop/topology_state.json``, which already documents
     "larger values apply stronger penalization").
  2. Chain rule: the solver returns ``d(+downforce)/d(beta)`` (topOSens on
     whatever was injected). ``d(+downforce)/d(rho) = d(+downforce)/d(beta)
     * dbeta/drho`` is what actually drives the OC step; ``dJ/drho`` is its
     negation (``J = -downforce``). Same sign assertion as the base loop:
     the first accepted step's predicted and actual objective deltas must
     agree in sign, or the run stops.
  3. Continuation on ``b``: starts at 1.0, doubles every few iterations, caps
     at 32.
  4. A floored, sharpening-aware move limit. The base loop's move limit is
     an unfloored ratchet that halves on every rejection; run
     ``stage_t_python_loop_v2_floor`` collapsed it to ~1e-29 and logged a
     6e-29 density change as "accepted" (see that run's
     ``candidate_manifest.json``: "known_defect_in_this_run"). Here the move
     limit has a floor, resets whenever ``b`` increases (a sharpening step
     legitimately changes the landscape), and a candidate whose actual
     density change is below ``MIN_MEANINGFUL_STEP`` is never accepted
     regardless of what the (possibly noisy) objective comparison says.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from cfd_sdf.canonical_grid_snapshot import load_and_verify_canonical_grid_snapshot
from cfd_sdf.fixed_grid_canonical_state_injection import (
    inject_canonical_state_into_fixed_grid_contract,
)
from cfd_sdf.fixed_grid_contract import _write_cell_vti
from cfd_sdf.fixed_grid_optimizer import _infer_beta_max, _updated_topology_state
from cfd_sdf.fixed_grid_primal import load_fixed_grid_density_state
from cfd_sdf.handoff import build_density_to_sdf_handoff
from cfd_sdf.openfoam_canonical_field_transfer import (
    reconstruct_and_write_canonical_gradient_transfer,
)
from cfd_sdf.problem_spec import load_problem_spec

import stage_t_python_loop as base

BASE = base.BASE
BASELINE_DOWNFORCE = base.BASELINE_DOWNFORCE
RESPONSE_ID = base.RESPONSE_ID
ADJOINT_SOLVER_ID = base.ADJOINT_SOLVER_ID

ETA = 0.5  # Heaviside projection threshold

B_START = 1.0
B_DOUBLE_EVERY = 3
B_MAX = 32.0

MOVE_LIMIT_START = 0.06
MOVE_LIMIT_FLOOR = 0.005
MIN_MEANINGFUL_STEP = 1.0e-6  # max|delta rho| below this is not a real step

V_FINAL = 0.25
V_RAMP_ITERS = 12
ZERO_FLOOR = 1.0e-3  # lets exact-zero cells escape the multiplicative OC update

MAX_ATTEMPTS_PER_ITERATION = 4


def b_schedule(iteration: int) -> float:
    """b=1 for the first B_DOUBLE_EVERY iterations, doubling thereafter, capped."""
    return min(B_MAX, B_START * (2.0 ** (iteration // B_DOUBLE_EVERY)))


def project_beta(rho: np.ndarray, b: float, eta: float = ETA) -> np.ndarray:
    denom = np.tanh(b * eta) + np.tanh(b * (1.0 - eta))
    return (np.tanh(b * eta) + np.tanh(b * (rho - eta))) / denom


def project_dbeta_drho(rho: np.ndarray, b: float, eta: float = ETA) -> np.ndarray:
    denom = np.tanh(b * eta) + np.tanh(b * (1.0 - eta))
    return b * (1.0 - np.tanh(b * (rho - eta)) ** 2) / denom


def _canonical_arrays(
    base_arrays: dict[str, np.ndarray],
    rho: np.ndarray,
    beta_field: np.ndarray,
    beta_max: float,
) -> dict[str, np.ndarray]:
    """Like ``fixed_grid_optimizer._updated_density_arrays`` but rho and its
    projection are different fields, so that helper (which stamps one field
    into rho/rho_filtered/rho_projected alike) does not apply."""
    return {
        "rho": rho.astype(np.float32),
        "rho_filtered": rho.astype(np.float32).copy(),
        "rho_projected": beta_field.astype(np.float32),
        "alpha": (beta_max * beta_field).astype(np.float32),
        "allowed_mask": np.asarray(base_arrays["allowed_mask"], dtype=np.uint8),
        "forbidden_mask": np.asarray(base_arrays["forbidden_mask"], dtype=np.uint8),
        "fixed_solid_mask": np.asarray(base_arrays["fixed_solid_mask"], dtype=np.uint8),
        "root_mask": np.asarray(base_arrays["root_mask"], dtype=np.uint8),
        "active_design_mask": np.asarray(base_arrays["active_design_mask"], dtype=np.uint8),
    }


def main(
    n_iterations: int,
    out_dir: Path,
    *,
    move_limit_start: float = MOVE_LIMIT_START,
    move_limit_floor: float = MOVE_LIMIT_FLOOR,
    v_final: float = V_FINAL,
    v_ramp_iters: int = V_RAMP_ITERS,
    zero_floor: float = ZERO_FLOOR,
) -> None:
    if out_dir.exists():
        raise SystemExit(f"{out_dir} already exists; remove it before re-running")
    out_dir.mkdir(parents=True)

    provenance = json.loads((BASE / "source_state" / "provenance.json").read_text())
    transfer = base.build_transfer(provenance)

    canonical0 = load_fixed_grid_density_state(BASE / "topology_state.json")
    rho = np.asarray(canonical0.arrays["rho"], dtype=np.float64).copy()
    active = (
        (np.asarray(canonical0.arrays["active_design_mask"]) > 0)
        & (np.asarray(canonical0.arrays["allowed_mask"]) > 0)
        & ~(np.asarray(canonical0.arrays["forbidden_mask"]) > 0)
        & ~(np.asarray(canonical0.arrays["fixed_solid_mask"]) > 0)
    )
    v0 = base.volume_fraction(rho, active)
    beta_max = _infer_beta_max(canonical0.arrays)

    spec = load_problem_spec(BASE / "project.yaml")
    verified_snapshot = load_and_verify_canonical_grid_snapshot(
        BASE / "canonical_grid_snapshot.json", spec
    )
    base_contract_topology_state_json = BASE / "injected_contract" / "topology_state.json"
    source_state_provenance_json = BASE / "source_state" / "provenance.json"
    source_cell_labels_npy = BASE / "cell_order" / "source_global_cell_labels_by_xfastest.npy"

    # Seed iteration 0 for free from the already-verified P0 base run. At P0,
    # the injected field equalled rho exactly (function linear = identity),
    # so this is exactly d(+downforce)/d(beta) at beta=rho0 -- a valid
    # g_beta to chain-rule against this run's projection derivative.
    g_beta = np.load(BASE / "canonical_gradient" / "canonical_gradient.npz")[
        "top_o_sensitivity_gradient"
    ].astype(np.float64)
    current_J = -BASELINE_DOWNFORCE
    current_downforce = BASELINE_DOWNFORCE

    parent_state = canonical0.state
    parent_json = canonical0.topology_state_json

    history: list[dict] = []
    sign_checked = False
    move_limit = move_limit_start
    b_prev: float | None = None
    last_state_dir: Path | None = None

    for i in range(n_iterations):
        v_target = v0 + (v_final - v0) * min(1.0, (i + 1) / v_ramp_iters)
        b_current = b_schedule(i)
        if b_prev is None or b_current > b_prev:
            # Sharpening step: the landscape genuinely changed, so the move
            # limit is relaxed back up rather than staying wherever the last
            # rejection sequence left it.
            move_limit = move_limit_start
        b_prev = b_current

        if not np.isfinite(g_beta).all():
            raise SystemExit(f"iteration {i}: canonical gradient contains non-finite values")
        if rho.min() < -1.0e-9 or rho.max() > 1.0 + 1.0e-9:
            raise SystemExit(f"iteration {i}: rho out of [0, 1]")

        dbeta_drho = project_dbeta_drho(rho, b_current)
        g_rho = g_beta * dbeta_drho  # d(+downforce)/drho, chain rule
        dJ_drho = -g_rho

        iteration_accepted = False
        for attempt in range(MAX_ATTEMPTS_PER_ITERATION):
            iter_dir = out_dir / f"iter_{i:03d}_attempt_{attempt:02d}"
            iter_dir.mkdir(parents=True)

            candidate_rho = base.oc_step(
                g_rho, rho, active, move_limit, v_target, zero_floor=zero_floor
            )
            if not np.isfinite(candidate_rho).all():
                raise SystemExit(f"iteration {i}: candidate rho contains non-finite values")
            if candidate_rho.min() < -1.0e-9 or candidate_rho.max() > 1.0 + 1.0e-9:
                raise SystemExit(f"iteration {i}: candidate rho out of [0, 1]")
            candidate_rho = np.clip(candidate_rho, 0.0, 1.0)

            step_size = (
                float(np.max(np.abs((candidate_rho - rho)[active]))) if active.any() else 0.0
            )
            row = {
                "iteration": i,
                "attempt": attempt,
                "b": b_current,
                "v_target": v_target,
                "move_limit": move_limit,
                "step_size_max_abs_delta_rho": step_size,
                "volume_fraction_before": base.volume_fraction(rho, active),
                "candidate_volume_fraction": base.volume_fraction(candidate_rho, active),
            }
            if step_size < MIN_MEANINGFUL_STEP:
                # The move-limit-collapse defect from stage_t_python_loop_v2_floor:
                # a candidate this close to a no-op must never be counted as
                # accepted, so don't even spend a solver run on it.
                row["accepted"] = False
                row["reject_reason"] = (
                    "candidate density change is numerically negligible "
                    f"(max|delta rho|={step_size:g} < {MIN_MEANINGFUL_STEP:g}); "
                    "not counted as accepted"
                )
                history.append(row)
                print(json.dumps(row, indent=2))
                break  # further attempts this iteration would be identical or worse

            candidate_beta = project_beta(candidate_rho, b_current)
            predicted_delta_J = float(np.dot(dJ_drho[active], (candidate_rho - rho)[active]))
            row["candidate_beta_volume_fraction"] = base.volume_fraction(candidate_beta, active)
            row["predicted_delta_J"] = predicted_delta_J

            source_beta = transfer.transfer_state_to_source(candidate_beta)
            source_npz = iter_dir / "source_state.npz"
            np.savez(source_npz, source_rho_xfastest=source_beta)
            contract = inject_canonical_state_into_fixed_grid_contract(
                openfoam_source_state_npz=source_npz,
                source_state_provenance_json=source_state_provenance_json,
                topology_state_json=base_contract_topology_state_json,
                output_directory=iter_dir / "contract",
            )
            result = base._run_case(contract.topology_state_json, iter_dir / "case")
            usable, downforce = base._extract(result.summary)
            row["primal_converged"] = usable
            row["downforce_coefficient"] = downforce

            if not usable:
                row["accepted"] = False
                row["reject_reason"] = "primal did not converge or produced a non-finite objective"
                history.append(row)
                print(json.dumps(row, indent=2))
                move_limit = max(move_limit * 0.5, move_limit_floor)
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
                row["accepted"] = False
                row["reject_reason"] = "objective got worse than the current accepted state"
                history.append(row)
                print(json.dumps(row, indent=2))
                move_limit = max(move_limit * 0.5, move_limit_floor)
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
                new_g_beta = np.asarray(payload["top_o_sensitivity_gradient"], dtype=np.float64)

            row["accepted"] = True
            history.append(row)
            print(json.dumps(row, indent=2))

            rho = candidate_rho
            g_beta = new_g_beta
            current_J = actual_J
            current_downforce = downforce

            state_dir = iter_dir / "canonical_state"
            density_vti_path = state_dir / "density.vti"
            arrays = _canonical_arrays(canonical0.arrays, rho, candidate_beta, beta_max)
            _write_cell_vti(canonical0.grid, arrays, density_vti_path, kind="fixed_grid_density")
            new_state = _updated_topology_state(
                parent_state,
                parent_topology_state_json=parent_json,
                density_vti=density_vti_path,
                sensitivity_vti=grad_artifacts.fields_npz,
                update_vti=result.case_dir,
                optimizer_backend="python-heaviside-projection-optimality-criteria",
            )
            # Stage S/handoff must contour the projected (physical) field,
            # not the raw design variable -- see array_metadata.rho_projected
            # and cfd_sdf.handoff._select_rho_variant.
            new_state["density_array"] = "rho_projected"
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
    print(f"final rho volume_fraction={base.volume_fraction(rho, active)}")
    if last_state_dir is not None:
        final_state_json = last_state_dir / "topology_state.json"
        print(f"final canonical state: {final_state_json}")
        _report_discreteness(final_state_json, active)
    else:
        print("no iteration was accepted; no final canonical state written")


def _report_discreteness(state_json: Path, active: np.ndarray) -> None:
    density_state = load_fixed_grid_density_state(state_json)
    rho = np.asarray(density_state.arrays["rho"], dtype=np.float64)
    beta = np.asarray(density_state.arrays["rho_projected"], dtype=np.float64)
    for label, field in (("raw rho", rho), ("projected beta", beta)):
        selected = field[active]
        mean_nd = float(np.mean(4.0 * selected * (1.0 - selected)))
        print(
            f"{label}: mean_nd={mean_nd:.6f} max={float(np.max(selected)):.6f} "
            f"n>0.9={int(np.count_nonzero(selected > 0.9))} "
            f"n<0.1={int(np.count_nonzero(selected < 0.1))} "
            f"grey={int(np.count_nonzero((selected >= 0.1) & (selected <= 0.9)))}"
        )
    try:
        artifacts = build_density_to_sdf_handoff(state_json)
        print(f"stage_s_handoff: ok={artifacts.ok} dir={artifacts.output_dir}")
        print(json.dumps(artifacts.fidelity_report.get("surface"), indent=2))
        print(json.dumps(artifacts.fidelity_report.get("discreteness"), indent=2))
    except Exception as exc:  # noqa: BLE001 - report and keep going, don't mask the run
        print(f"stage_s_handoff failed: {exc}")


def _write_history(out_dir: Path, history: list[dict]) -> None:
    (out_dir / "history.json").write_text(json.dumps(history, indent=2), encoding="utf-8")


def _selftest() -> None:
    """Assert-based check for the new logic: projection identity/limits, the
    chain rule, and the move-limit floor/reset behavior."""

    rng = np.random.default_rng(0)
    rho = rng.uniform(0.0, 1.0, 500)

    # b -> 0 is the identity map (within float tolerance for a small-but-finite b).
    tiny_b = 1.0e-6
    beta_tiny = project_beta(rho, tiny_b)
    assert np.allclose(beta_tiny, rho, atol=1.0e-4), np.max(np.abs(beta_tiny - rho))

    # beta(eta) == 0.5 exactly, for any b.
    for b in (1.0, 4.0, 32.0):
        assert abs(float(project_beta(np.array([ETA]), b)[0]) - 0.5) < 1.0e-12

    # beta stays within [0, 1] and is monotone increasing in rho.
    for b in (1.0, 8.0, 32.0):
        beta = project_beta(rho, b)
        assert np.all(beta >= -1.0e-9) and np.all(beta <= 1.0 + 1.0e-9)
        order = np.argsort(rho)
        assert np.all(np.diff(beta[order]) >= -1.0e-9)

    # dbeta/drho matches a central finite difference of project_beta.
    b = 8.0
    h = 1.0e-6
    rho_mid = np.clip(rho, h, 1.0 - h)
    fd = (project_beta(rho_mid + h, b) - project_beta(rho_mid - h, b)) / (2.0 * h)
    analytic = project_dbeta_drho(rho_mid, b)
    assert np.max(np.abs(fd - analytic)) < 1.0e-3, np.max(np.abs(fd - analytic))

    # Continuation schedule: starts at B_START, doubles every B_DOUBLE_EVERY
    # iterations, caps at B_MAX, and is non-decreasing.
    values = [b_schedule(i) for i in range(30)]
    assert values[0] == B_START
    assert values[-1] == B_MAX
    assert all(b2 >= b1 for b1, b2 in zip(values, values[1:]))

    # A step below MIN_MEANINGFUL_STEP must not be reachable from a properly
    # floored, reset move limit at any point in the schedule -- i.e. the
    # floor is comfortably above the negligible-step threshold.
    assert MOVE_LIMIT_FLOOR > 10.0 * MIN_MEANINGFUL_STEP

    print("stage_t_binarized_loop selftest: OK")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "selftest":
        _selftest()
        raise SystemExit(0)
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 24
    out = ROOT / "work" / (sys.argv[2] if len(sys.argv) > 2 else "stage_t_binarized")
    main(n, out)
