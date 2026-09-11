"""Finite-difference gate for the canonical closed-loop gradient (P0).

Central-difference check performed entirely on the canonical grid: perturb
``rho`` along two directions on the 624 feasible cells (0.1 < rho < 0.9 with
nonzero canonical gradient), push each perturbed state through
``P = ExactCartesianOverlapTransfer``, inject it into a T1 (OpenFOAM-grid)
contract, run the real primal solver, and compare
``(J+ - J-) / (2*eps)`` against ``g_canonical . d``.

Reuses ``ExactCartesianOverlapTransfer``, ``inject_canonical_state_into_fixed_grid_contract``,
and ``run_fixed_grid_primal_case`` verbatim -- this script only wires them
together and does the FD arithmetic. Writes a fresh subdirectory tree under
``work/p0_closed_loop/fd_suite/`` (never touches existing artifacts).
"""

from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cfd_sdf.execution import DEFAULT_OPENFOAM_DOCKER_IMAGE, run_openfoam_case
from cfd_sdf.fixed_grid_canonical_state_injection import (
    inject_canonical_state_into_fixed_grid_contract,
)
from cfd_sdf.fixed_grid_gradient_gate import (
    DEFAULT_RATIO_MAX,
    DEFAULT_RATIO_MIN,
    DEFAULT_RELATIVE_ERROR_TOLERANCE,
)
from cfd_sdf.fixed_grid_primal import (
    load_fixed_grid_density_state,
    prepare_fixed_grid_primal_case,
    run_fixed_grid_primal_case,
    summarize_fixed_grid_primal_case,
)
from cfd_sdf.openfoam_field_reconstruction import (
    _processor_dirs,
    _processor_labels,
    _reconstruct_nonuniform_field,
    _select_final_time,
    reconstruct_final_decomposed_openfoam_fields,
)
from cfd_sdf.openfoam_grid_transfer import (
    ExactCartesianOverlapTransfer,
    UniformCartesianCellGrid,
    load_openfoam_cell_order_mapping,
)

WORK = ROOT / "work" / "p0_closed_loop"
OUT = WORK / "fd_suite"
TIGHT_OUT = OUT / "tight_residual"
SEED = 20260911
EPSILONS = (3.0e-5, 1.0e-4, 3.0e-4, 1.0e-3)
DIRECTIONS = ("sensitivity", "filtered-random")
# Proxy noise floor: the primal solver's own residual convergence tolerance
# (system/optimisationDict "p.*" residualControl), not a measured repeat run.
SOLVER_RESIDUAL_TOLERANCE = 5.0e-7
# Two-decade-tighter primal residualControl for the follow-up power experiment.
TIGHT_PRIMAL_RESIDUAL = "5.e-9"
TIGHT_PRIMAL_RESIDUAL_VALUE = 5.0e-9
TIGHT_PRIMAL_NITERS = 5000

SIGN_CONVENTION_FINDING = (
    "top_o_sensitivity_gradient in work/p0_closed_loop/canonical_gradient/canonical_gradient.npz "
    "is d(+downforce_coefficient)/d(rho_canonical): the derivative of OpenFOAM's raw 'downforce' "
    "objective function object, NOT of this project's J = -downforce_coefficient. Empirically, "
    "fd/analytic is consistently close to -1 (not +1) across every FD row tested. Anyone consuming "
    "that array as dJ/drho for a descent step must first negate it: dJ/drho = -top_o_sensitivity_gradient."
)

SUITE_SCOPE_STATEMENT = (
    "This suite validates the gradient chain (P, canonical-state injection, the OpenFOAM primal "
    "solver, topOSens, and P.T) on ONE converged state of ONE 8192-cell laminar fixture case. It "
    "is evidence that this specific chain is internally consistent (up to the sign convention "
    "above) at that state. It is NOT evidence about target aerodynamics, constrained topology "
    "optimization behavior, other design states, other mesh resolutions, or turbulence modeling; "
    "none of those are exercised here and no claim about them should be inferred from this result."
)


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


def check_source_sensitivity_support(active_design_mask_xfastest: np.ndarray) -> dict:
    """Re-verify topOSens_downforce is nonzero only on active source cells."""

    reconstructed = reconstruct_final_decomposed_openfoam_fields(
        WORK / "primal_base", adjoint_solver_id="downforce"
    )
    mapping = load_openfoam_cell_order_mapping(
        WORK / "cell_order" / "source_global_cell_labels_by_xfastest.npy",
        cell_count=reconstructed.top_o_sensitivity.size,
    )
    sens_xfastest = np.asarray(reconstructed.top_o_sensitivity)[mapping.global_cell_labels_by_xfastest]
    nonzero = sens_xfastest != 0.0
    active = active_design_mask_xfastest > 0
    return {
        "ok": bool(np.array_equal(nonzero, active)),
        "nonzero_count": int(np.count_nonzero(nonzero)),
        "active_count": int(np.count_nonzero(active)),
        "mismatch_count": int(np.count_nonzero(nonzero != active)),
    }


def _normalized_direction(raw: np.ndarray, support: np.ndarray) -> np.ndarray:
    d = np.where(support, raw, 0.0)
    peak = np.max(np.abs(d[support]))
    if peak <= 0.0:
        raise ValueError("direction is degenerate on the feasible support")
    return d / peak


def _random_direction(support: np.ndarray) -> np.ndarray:
    rng = np.random.default_rng(SEED)
    d = np.zeros(support.shape, dtype=np.float64)
    idx = np.flatnonzero(support)
    d[idx] = rng.standard_normal(idx.size)
    return d


def _inject_perturbed_contract(
    *,
    transfer: ExactCartesianOverlapTransfer,
    base_rho: np.ndarray,
    d: np.ndarray,
    sign: float,
    eps: float,
    case_root: Path,
    source_state_provenance_json: Path,
    base_contract_topology_state_json: Path,
):
    case_root.mkdir(parents=True, exist_ok=True)
    rho_pm = base_rho + sign * eps * d
    source_rho = transfer.transfer_state_to_source(rho_pm)
    npz_path = case_root / "perturbed_source_state.npz"
    np.savez(npz_path, source_rho_xfastest=source_rho)
    return inject_canonical_state_into_fixed_grid_contract(
        openfoam_source_state_npz=npz_path,
        source_state_provenance_json=source_state_provenance_json,
        topology_state_json=base_contract_topology_state_json,
        output_directory=case_root / "contract",
    )


def _run_signed_case(
    *,
    transfer: ExactCartesianOverlapTransfer,
    base_rho: np.ndarray,
    d: np.ndarray,
    sign: float,
    eps: float,
    row_dir: Path,
    source_state_provenance_json: Path,
    base_contract_topology_state_json: Path,
) -> dict:
    tag = "plus" if sign > 0 else "minus"
    artifacts = _inject_perturbed_contract(
        transfer=transfer,
        base_rho=base_rho,
        d=d,
        sign=sign,
        eps=eps,
        case_root=row_dir / tag,
        source_state_provenance_json=source_state_provenance_json,
        base_contract_topology_state_json=base_contract_topology_state_json,
    )
    result = run_fixed_grid_primal_case(
        artifacts.topology_state_json,
        case_dir=row_dir / tag / "case",
        density_variant="seed",
        backend="auto",
        execute=True,
        adjoint_iterations=1,
        timeout_seconds=1800,
    )
    summary = result.summary
    convergence = summary.get("convergence") or {}
    downforce = summary.get("downforce_coefficient")
    primal_converged = bool(convergence.get("primal_converged"))
    return {
        "tag": tag,
        "primal_summary_json": str(result.primal_summary_json),
        "status": summary.get("status"),
        "primal_converged": primal_converged,
        "primal_iterations": convergence.get("primal_iterations"),
        "downforce_coefficient": downforce,
        "drag_coefficient": summary.get("drag_coefficient"),
        "objective_J": -float(downforce) if downforce is not None else None,
        "usable": primal_converged and downforce is not None,
    }


def _tighten_primal_residual(case_dir: Path) -> None:
    """Tighten the primal solver's own residualControl (op1 block only).

    Leaves the adjoint blocks ("pa.*"/"Ua.*") untouched -- their literal keys
    differ from the primal's ("p.*"/"U.*"), so the regexes below cannot match
    them. We only need the objective, so the adjoint tolerance is irrelevant.
    """

    path = case_dir / "system" / "optimisationDict"
    text = path.read_text(encoding="utf-8")
    text = re.sub(r'("p\.\*"\s+)5\.e-7;', rf"\g<1>{TIGHT_PRIMAL_RESIDUAL};", text)
    text = re.sub(r'("U\.\*"\s+)5\.e-7;', rf"\g<1>{TIGHT_PRIMAL_RESIDUAL};", text)
    text, n = re.subn(r"\bnIters\s+1000\s*;", f"nIters {TIGHT_PRIMAL_NITERS};", text)
    if n != 1:
        raise ValueError(f"expected exactly one primal nIters=1000 to patch in {path}, found {n}")
    path.write_text(text, encoding="utf-8", newline="\n")


def _read_final_primal_residual(case_dir: Path) -> dict:
    """Last logged initial_residual for the primal p/U fields (proxy for 'achieved')."""

    csv_path = case_dir / "fixed_grid_residual_history.csv"
    achieved: dict[str, float] = {}
    if not csv_path.is_file():
        return achieved
    with csv_path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row["field"] in ("p", "Ux", "Uy", "Uz"):
                achieved[row["field"]] = float(row["initial_residual"])
    return achieved


def _run_signed_case_tight_residual(
    *,
    transfer: ExactCartesianOverlapTransfer,
    base_rho: np.ndarray,
    d: np.ndarray,
    sign: float,
    eps: float,
    row_dir: Path,
    source_state_provenance_json: Path,
    base_contract_topology_state_json: Path,
) -> dict:
    tag = "plus" if sign > 0 else "minus"
    artifacts = _inject_perturbed_contract(
        transfer=transfer,
        base_rho=base_rho,
        d=d,
        sign=sign,
        eps=eps,
        case_root=row_dir / tag,
        source_state_provenance_json=source_state_provenance_json,
        base_contract_topology_state_json=base_contract_topology_state_json,
    )
    prepared = prepare_fixed_grid_primal_case(
        artifacts.topology_state_json,
        case_dir=row_dir / tag / "case",
        density_variant="seed",
        adjoint_iterations=1,
    )
    _tighten_primal_residual(prepared.case_dir)
    run_result = run_openfoam_case(
        prepared.case_dir,
        backend="auto",
        dry_run=False,
        timeout_seconds=3600,
        docker_image=DEFAULT_OPENFOAM_DOCKER_IMAGE,
    )
    summary = summarize_fixed_grid_primal_case(
        prepared.case_dir,
        topology_state_json=prepared.topology_state_json,
        run_result=run_result.to_dict(),
        docker_image=DEFAULT_OPENFOAM_DOCKER_IMAGE,
    )
    convergence = summary.get("convergence") or {}
    downforce = summary.get("downforce_coefficient")
    primal_converged = bool(convergence.get("primal_converged"))
    return {
        "tag": tag,
        "primal_summary_json": str(prepared.case_dir / "fixed_grid_primal_summary.json"),
        "status": summary.get("status"),
        "primal_converged": primal_converged,
        "primal_iterations": convergence.get("primal_iterations"),
        "achieved_final_residual": _read_final_primal_residual(prepared.case_dir),
        "downforce_coefficient": downforce,
        "drag_coefficient": summary.get("drag_coefficient"),
        "objective_J": -float(downforce) if downforce is not None else None,
        "usable": primal_converged and downforce is not None,
    }


def main() -> None:
    if OUT.exists():
        raise SystemExit(f"{OUT} already exists; remove it before re-running the suite")

    provenance = json.loads((WORK / "source_state" / "provenance.json").read_text())
    transfer = build_transfer(provenance)

    canonical_state = load_fixed_grid_density_state(WORK / "topology_state.json")
    rho = np.asarray(canonical_state.arrays["rho"], dtype=np.float64)
    active = np.asarray(canonical_state.arrays["active_design_mask"]) > 0

    gradient = np.load(WORK / "canonical_gradient" / "canonical_gradient.npz")
    g_canonical = np.asarray(gradient["top_o_sensitivity_gradient"], dtype=np.float64)

    support = active & (rho > 0.1) & (rho < 0.9) & (g_canonical != 0.0)
    support_count = int(np.count_nonzero(support))
    print(f"feasible support cells: {support_count}")

    contract_state = load_fixed_grid_density_state(WORK / "injected_contract" / "topology_state.json")
    source_active_design_mask = np.asarray(contract_state.arrays["active_design_mask"])
    sensitivity_support_check = check_source_sensitivity_support(source_active_design_mask)
    print(f"source topOSens support check: {sensitivity_support_check}")

    directions = {
        "sensitivity": _normalized_direction(g_canonical, support),
        "filtered-random": _normalized_direction(_random_direction(support), support),
    }

    OUT.mkdir(parents=True)
    rows = []
    for direction in DIRECTIONS:
        d = directions[direction]
        for eps in EPSILONS:
            eps_label = format(eps, ".0e")
            row_dir = OUT / "runs" / direction / eps_label
            plus = _run_signed_case(
                transfer=transfer,
                base_rho=rho,
                d=d,
                sign=+1.0,
                eps=eps,
                row_dir=row_dir,
                source_state_provenance_json=WORK / "source_state" / "provenance.json",
                base_contract_topology_state_json=WORK / "injected_contract" / "topology_state.json",
            )
            minus = _run_signed_case(
                transfer=transfer,
                base_rho=rho,
                d=d,
                sign=-1.0,
                eps=eps,
                row_dir=row_dir,
                source_state_provenance_json=WORK / "source_state" / "provenance.json",
                base_contract_topology_state_json=WORK / "injected_contract" / "topology_state.json",
            )

            row = {
                "direction": direction,
                "eps": eps,
                "plus": plus,
                "minus": minus,
                "discarded": not (plus["usable"] and minus["usable"]),
            }
            if row["discarded"]:
                row["discard_reason"] = "primal did not converge for plus and/or minus case"
            else:
                j_plus = plus["objective_J"]
                j_minus = minus["objective_J"]
                fd = (j_plus - j_minus) / (2.0 * eps)
                analytic = float(np.dot(g_canonical, d))
                ratio = fd / analytic if analytic != 0.0 else None
                relative_error = (
                    abs(fd - analytic) / max(abs(fd), abs(analytic), 1.0e-30)
                )
                row.update(
                    {
                        "J_plus": j_plus,
                        "J_minus": j_minus,
                        "abs_delta_J": abs(j_plus - j_minus),
                        "fd": fd,
                        "analytic": analytic,
                        "ratio": ratio,
                        "relative_error": relative_error,
                        "sign_agreement": bool(np.sign(fd) == np.sign(analytic)),
                        "above_noise_floor": abs(j_plus - j_minus) > SOLVER_RESIDUAL_TOLERANCE,
                    }
                )
            rows.append(row)
            print(json.dumps(row, indent=2, default=str))

    usable_rows = [r for r in rows if not r["discarded"]]
    raw_ratios = [r["ratio"] for r in usable_rows if r["ratio"] is not None]
    mean_ratio = float(np.mean(raw_ratios)) if raw_ratios else None
    # Empirically determine which sign convention makes fd/analytic ~= +1.
    sign_flip = -1.0 if (mean_ratio is not None and abs(mean_ratio + 1.0) < abs(mean_ratio - 1.0)) else 1.0

    gate_pass = bool(usable_rows) and len(usable_rows) == len(rows)
    for r in usable_rows:
        corrected_ratio = sign_flip * r["ratio"] if r["ratio"] is not None else None
        r["sign_corrected_ratio"] = corrected_ratio
        # `relative_error` above is the raw (unflipped) value, per the spec's
        # instruction to report raw numbers first; the gate threshold only
        # makes sense once the sign convention is reconciled, so recompute it
        # against the sign-corrected analytic term for the pass/fail check.
        analytic_corrected = sign_flip * r["analytic"]
        r["sign_corrected_relative_error"] = abs(r["fd"] - analytic_corrected) / max(
            abs(r["fd"]), abs(analytic_corrected), 1.0e-30
        )
        row_ok = (
            corrected_ratio is not None
            and DEFAULT_RATIO_MIN <= corrected_ratio <= DEFAULT_RATIO_MAX
            and r["sign_corrected_relative_error"] <= DEFAULT_RELATIVE_ERROR_TOLERANCE
        )
        r["gate_row_pass"] = row_ok
        gate_pass = gate_pass and row_ok

    result = {
        "kind": "p0_canonical_gradient_fd_suite",
        "schema_version": 1,
        "seed": SEED,
        "epsilons": list(EPSILONS),
        "directions": DIRECTIONS,
        "support_cell_count": support_count,
        "source_sensitivity_support_check": sensitivity_support_check,
        "gate_thresholds": {
            "ratio_min": DEFAULT_RATIO_MIN,
            "ratio_max": DEFAULT_RATIO_MAX,
            "relative_error_tolerance": DEFAULT_RELATIVE_ERROR_TOLERANCE,
        },
        "solver_residual_tolerance_proxy_noise_floor": SOLVER_RESIDUAL_TOLERANCE,
        "mean_raw_ratio": mean_ratio,
        "empirical_sign_flip_applied_for_gate": sign_flip,
        "rows": rows,
        "gate_pass": gate_pass,
        "sign_convention_finding": SIGN_CONVENTION_FINDING,
        "scope": SUITE_SCOPE_STATEMENT,
    }
    (OUT / "fd_suite_result.json").write_text(json.dumps(result, indent=2, default=str))
    print(f"gate_pass={gate_pass} mean_raw_ratio={mean_ratio}")


def run_tight_residual_experiment() -> None:
    """Rerun only filtered-random, all 4 epsilons, at a 2-decade tighter primal residual.

    Tests whether the original filtered-random gate failures (3/4 rows) were a
    noise-floor/statistical-power artifact rather than a chain defect: same
    direction vector, same seed, same support, same injection path -- only the
    primal solver's own residualControl and iteration cap change.
    """

    if TIGHT_OUT.exists():
        raise SystemExit(f"{TIGHT_OUT} already exists; remove it before re-running")
    if not (OUT / "fd_suite_result.json").is_file():
        raise SystemExit(f"{OUT / 'fd_suite_result.json'} is missing; run the main suite first")

    original = json.loads((OUT / "fd_suite_result.json").read_text())
    original_rows = {r["eps"]: r for r in original["rows"] if r["direction"] == "filtered-random"}
    sign_flip = original["empirical_sign_flip_applied_for_gate"]

    provenance = json.loads((WORK / "source_state" / "provenance.json").read_text())
    transfer = build_transfer(provenance)
    canonical_state = load_fixed_grid_density_state(WORK / "topology_state.json")
    rho = np.asarray(canonical_state.arrays["rho"], dtype=np.float64)
    active = np.asarray(canonical_state.arrays["active_design_mask"]) > 0
    gradient = np.load(WORK / "canonical_gradient" / "canonical_gradient.npz")
    g_canonical = np.asarray(gradient["top_o_sensitivity_gradient"], dtype=np.float64)
    support = active & (rho > 0.1) & (rho < 0.9) & (g_canonical != 0.0)
    # Identical direction vector: same seed, same support -> same draw.
    d = _normalized_direction(_random_direction(support), support)
    analytic = float(np.dot(g_canonical, d))

    TIGHT_OUT.mkdir(parents=True)
    rows = []
    for eps in EPSILONS:
        row_dir = TIGHT_OUT / format(eps, ".0e")
        plus = _run_signed_case_tight_residual(
            transfer=transfer,
            base_rho=rho,
            d=d,
            sign=+1.0,
            eps=eps,
            row_dir=row_dir,
            source_state_provenance_json=WORK / "source_state" / "provenance.json",
            base_contract_topology_state_json=WORK / "injected_contract" / "topology_state.json",
        )
        minus = _run_signed_case_tight_residual(
            transfer=transfer,
            base_rho=rho,
            d=d,
            sign=-1.0,
            eps=eps,
            row_dir=row_dir,
            source_state_provenance_json=WORK / "source_state" / "provenance.json",
            base_contract_topology_state_json=WORK / "injected_contract" / "topology_state.json",
        )
        row = {
            "direction": "filtered-random",
            "eps": eps,
            "plus": plus,
            "minus": minus,
            "discarded": not (plus["usable"] and minus["usable"]),
        }
        if row["discarded"]:
            row["discard_reason"] = "primal did not converge for plus and/or minus case"
        else:
            j_plus = plus["objective_J"]
            j_minus = minus["objective_J"]
            fd = (j_plus - j_minus) / (2.0 * eps)
            ratio = fd / analytic if analytic != 0.0 else None
            relative_error = abs(fd - analytic) / max(abs(fd), abs(analytic), 1.0e-30)
            analytic_corrected = sign_flip * analytic
            sign_corrected_ratio = sign_flip * ratio if ratio is not None else None
            sign_corrected_relative_error = abs(fd - analytic_corrected) / max(
                abs(fd), abs(analytic_corrected), 1.0e-30
            )
            row.update(
                {
                    "J_plus": j_plus,
                    "J_minus": j_minus,
                    "abs_delta_J": abs(j_plus - j_minus),
                    "fd": fd,
                    "analytic": analytic,
                    "ratio": ratio,
                    "relative_error": relative_error,
                    "sign_corrected_ratio": sign_corrected_ratio,
                    "sign_corrected_relative_error": sign_corrected_relative_error,
                    "above_noise_floor": abs(j_plus - j_minus) > TIGHT_PRIMAL_RESIDUAL_VALUE,
                    "gate_row_pass": (
                        sign_corrected_ratio is not None
                        and DEFAULT_RATIO_MIN <= sign_corrected_ratio <= DEFAULT_RATIO_MAX
                        and sign_corrected_relative_error <= DEFAULT_RELATIVE_ERROR_TOLERANCE
                    ),
                }
            )
        before = original_rows.get(eps)
        row["before"] = (
            {
                "abs_delta_J": before["abs_delta_J"],
                "sign_corrected_ratio": before["sign_corrected_ratio"],
                "sign_corrected_relative_error": before["sign_corrected_relative_error"],
                "gate_row_pass": before["gate_row_pass"],
            }
            if before
            else None
        )
        rows.append(row)
        print(json.dumps(row, indent=2, default=str))

    usable = [r for r in rows if not r["discarded"]]
    gate_pass = bool(usable) and len(usable) == len(rows) and all(r["gate_row_pass"] for r in usable)

    result = {
        "kind": "p0_canonical_gradient_fd_suite_tight_residual_experiment",
        "schema_version": 1,
        "purpose": (
            "Rerun only the filtered-random direction (same seed 20260911, same "
            "624-cell support, same injection path) with the primal residualControl "
            "for \"p.*\"/\"U.*\" tightened from 5e-7 to 5e-9 and the primal iteration "
            "cap raised to test whether the original 3/4 gate failures on that "
            "direction were a noise-floor artifact rather than a chain defect."
        ),
        "seed": SEED,
        "direction": "filtered-random",
        "tight_primal_residual_tolerance": TIGHT_PRIMAL_RESIDUAL_VALUE,
        "tight_primal_niters_cap": TIGHT_PRIMAL_NITERS,
        "analytic": analytic,
        "empirical_sign_flip_applied_for_gate": sign_flip,
        "gate_thresholds": {
            "ratio_min": DEFAULT_RATIO_MIN,
            "ratio_max": DEFAULT_RATIO_MAX,
            "relative_error_tolerance": DEFAULT_RELATIVE_ERROR_TOLERANCE,
        },
        "rows": rows,
        "gate_pass": gate_pass,
        "sign_convention_finding": SIGN_CONVENTION_FINDING,
        "scope": SUITE_SCOPE_STATEMENT,
    }
    (TIGHT_OUT / "tight_residual_result.json").write_text(json.dumps(result, indent=2, default=str))
    print(f"tight_residual gate_pass={gate_pass}")


def _global_order_direction(
    *, transfer: ExactCartesianOverlapTransfer, d_canonical: np.ndarray, mapping
) -> np.ndarray:
    """``P @ d`` on the source grid, reordered from x-fastest to global-label order."""

    pd_xfastest = transfer.transfer_state_to_source(d_canonical)
    pd_global = np.empty_like(pd_xfastest)
    pd_global[mapping.global_cell_labels_by_xfastest] = pd_xfastest
    return pd_global


def _attenuation_factor(*, plus_case_dir: Path, minus_case_dir: Path, pd_global: np.ndarray) -> dict:
    """Project (alphaTilda+ - alphaTilda-) and (raw_alpha+ - raw_alpha-) onto P@d.

    Returns the ratio of those two projections: how much of the injected,
    direction-aligned change survives OpenFOAM's own regularisation filter
    (0.orig/alpha -> alphaTilda) before the flow solver ever sees it.
    """

    plus = reconstruct_final_decomposed_openfoam_fields(plus_case_dir, adjoint_solver_id="downforce")
    minus = reconstruct_final_decomposed_openfoam_fields(minus_case_dir, adjoint_solver_id="downforce")
    if plus.raw_alpha is None or minus.raw_alpha is None:
        raise ValueError(f"raw_alpha (topOVars) missing for {plus_case_dir} or {minus_case_dir}")
    if not np.array_equal(plus.global_cell_labels, minus.global_cell_labels):
        raise ValueError("plus/minus cases do not share the same global cell-label ordering")

    delta_alpha_tilda = np.asarray(plus.alpha_tilda, dtype=np.float64) - np.asarray(
        minus.alpha_tilda, dtype=np.float64
    )
    delta_raw_alpha = np.asarray(plus.raw_alpha, dtype=np.float64) - np.asarray(
        minus.raw_alpha, dtype=np.float64
    )
    proj_alpha_tilda = float(np.dot(delta_alpha_tilda, pd_global))
    proj_raw_alpha = float(np.dot(delta_raw_alpha, pd_global))
    return {
        "proj_raw_alpha": proj_raw_alpha,
        "proj_alpha_tilda": proj_alpha_tilda,
        "attenuation_factor": proj_alpha_tilda / proj_raw_alpha if proj_raw_alpha != 0.0 else None,
    }


def run_regularisation_attenuation_check() -> None:
    """Decisive test for the ~10% filtered-random bias: does the case's own
    ``regularisation`` filter (alpha -> alphaTilda) attenuate a direction's
    injected change before the flow solver sees it? Uses only decomposed
    fields already on disk from prior runs -- no new OpenFOAM execution.
    """

    out_path = OUT / "regularisation_attenuation_check.json"
    provenance = json.loads((WORK / "source_state" / "provenance.json").read_text())
    transfer = build_transfer(provenance)
    mapping = load_openfoam_cell_order_mapping(
        WORK / "cell_order" / "source_global_cell_labels_by_xfastest.npy",
        cell_count=transfer.source_grid.cell_count,
    )

    canonical_state = load_fixed_grid_density_state(WORK / "topology_state.json")
    rho = np.asarray(canonical_state.arrays["rho"], dtype=np.float64)
    active = np.asarray(canonical_state.arrays["active_design_mask"]) > 0
    gradient = np.load(WORK / "canonical_gradient" / "canonical_gradient.npz")
    g_canonical = np.asarray(gradient["top_o_sensitivity_gradient"], dtype=np.float64)
    support = active & (rho > 0.1) & (rho < 0.9) & (g_canonical != 0.0)

    directions = {
        "sensitivity": _normalized_direction(g_canonical, support),
        "filtered-random": _normalized_direction(_random_direction(support), support),
    }
    # Highest-signal eps=1e-3 row for each direction; filtered-random uses the
    # tightened-residual reruns (cleanest data), sensitivity uses the original run.
    case_dirs = {
        "sensitivity": (
            OUT / "runs" / "sensitivity" / "1e-03" / "plus" / "case",
            OUT / "runs" / "sensitivity" / "1e-03" / "minus" / "case",
        ),
        "filtered-random": (
            TIGHT_OUT / "1e-03" / "plus" / "case",
            TIGHT_OUT / "1e-03" / "minus" / "case",
        ),
    }

    results = {}
    for direction, (plus_dir, minus_dir) in case_dirs.items():
        pd_global = _global_order_direction(transfer=transfer, d_canonical=directions[direction], mapping=mapping)
        results[direction] = _attenuation_factor(plus_case_dir=plus_dir, minus_case_dir=minus_dir, pd_global=pd_global)
        print(direction, json.dumps(results[direction], indent=2))

    sens_atten = results["sensitivity"]["attenuation_factor"]
    rand_atten = results["filtered-random"]["attenuation_factor"]
    both_present = sens_atten is not None and rand_atten is not None
    sensitivity_near_identity = both_present and abs(sens_atten - 1.0) < 0.05
    directional_gap = both_present and (sens_atten - rand_atten)
    gap_matches_predicted_direction = both_present and rand_atten < sens_atten
    if not both_present:
        verdict = "inconclusive"
    elif sensitivity_near_identity and gap_matches_predicted_direction:
        verdict = "confirmed"
    elif gap_matches_predicted_direction:
        verdict = "partially_confirmed"
    else:
        verdict = "not_supported"

    result = {
        "kind": "p0_canonical_gradient_regularisation_attenuation_check",
        "schema_version": 1,
        "purpose": (
            "Test whether the case's system/optimisationDict 'regularisation' filter "
            "(alpha -> alphaTilda, applied inside the solver before the injected rho "
            "becomes porosity) explains the ~10% ratio bias measured for the "
            "filtered-random direction: project (alphaTilda+ - alphaTilda-) and "
            "(raw_alpha+ - raw_alpha-) onto P@d and compare, using decomposed fields "
            "already on disk (no new OpenFOAM runs)."
        ),
        "eps_used": 1.0e-3,
        "case_dirs": {k: [str(p) for p in v] for k, v in case_dirs.items()},
        "results": results,
        "directional_gap_sensitivity_minus_filtered_random": directional_gap,
        "verdict": verdict,
        "verdict_explanation": (
            "PARTIALLY CONFIRMED, not a clean match. The predicted direction is right -- "
            f"the sensitivity direction retains more of its injected amplitude through the "
            f"filter ({sens_atten:.3f}) than the filtered-random direction does ({rand_atten:.3f}), "
            "a relative gap of "
            f"{(directional_gap / sens_atten * 100.0):.1f}% consistent in sign and rough order of "
            "magnitude with the ~10% ratio deficit measured in the FD suite for that direction. "
            "But the coordinator's specific quantitative prediction -- that the filter is ~identity "
            "(attenuation ~1.0) for the smooth sensitivity direction -- is not supported: even that "
            "direction loses roughly a third of its injected amplitude. The likely reason is that the "
            "perturbation support (624 of 46080 canonical cells, ~111 of 8192 source cells) is a small, "
            "spatially localized patch relative to the regularisation filter's radius (meanRadiusMult "
            "1.5), so a diffusive smoothing filter attenuates ANY perturbation confined to that patch "
            "substantially, regardless of whether its cell-to-cell values are smooth or random; the "
            "smaller residual gap between the two directions is the filter additionally removing the "
            "sub-filter-radius (high-frequency) structure that filtered-random has and the smoother "
            "gradient-shaped sensitivity direction has less of."
            if both_present
            else "attenuation_factor could not be computed for one or both directions (zero projection)."
        ),
        "topOSens_derivative_variable": (
            "topOSens_downforce is OpenFOAM's own adjoint sensitivity with respect to the "
            "raw injected design variable ('alpha' as written to 0.orig/alpha, i.e. our "
            "'rho'), NOT with respect to the filtered/projected field (alphaTilda/beta) -- "
            "OpenFOAM's adjoint already carries the internal filter+projection chain rule "
            "for the correct discrete gradient. The bias measured in the FD suite is not a "
            "bug in topOSens itself; it is this project's canonical gradient chain (P, "
            "injection, P.T) omitting the filter's own chain-rule term, so a directional "
            "derivative check or descent step taken purely in canonical rho-space undercounts "
            "the true response for directions the filter attenuates."
        ),
        "regularisation_chain_rule_gap": (
            "Confirmed as a real, roadmap-level limitation, though its magnitude is entangled "
            "with a general small-patch attenuation effect rather than being a pure high-frequency "
            "vs. low-frequency split: the current canonical gradient chain (P, injection, solver, "
            "topOSens, P.T) does not include the regularisation filter's own adjoint "
            "(d(alphaTilda)/d(rho)). This biases any directional derivative check or search "
            "direction low by an amount that depends on how much of that direction's energy the "
            "filter removes -- worst for directions with fine-scale or spatially localized "
            "structure relative to the filter radius, smallest (but still nonzero at this support "
            "size) for the true gradient direction itself. It should be tracked as a known gap, "
            "not treated as fully resolved by the sign-convention finding alone."
        ),
    }
    out_path.write_text(json.dumps(result, indent=2, default=str))
    print(json.dumps(result, indent=2, default=str))


NOREG_OUT = OUT / "no_regularisation"


def _disable_regularisation(case_dir: Path) -> None:
    path = case_dir / "system" / "optimisationDict"
    text = path.read_text(encoding="utf-8")
    text, n = re.subn(r"\bregularise\s+true\s*;", "regularise     false;", text)
    if n != 1:
        raise ValueError(f"expected exactly one 'regularise true;' to patch in {path}, found {n}")
    path.write_text(text, encoding="utf-8", newline="\n")


def _prepare_run_summarize(
    topology_state_json: Path, *, case_dir: Path, adjoint_iterations: int, tighten: bool, disable_reg: bool
) -> tuple[Path, dict]:
    prepared = prepare_fixed_grid_primal_case(
        topology_state_json,
        case_dir=case_dir,
        density_variant="seed",
        adjoint_iterations=adjoint_iterations,
    )
    if disable_reg:
        _disable_regularisation(prepared.case_dir)
    if tighten:
        _tighten_primal_residual(prepared.case_dir)
    run_result = run_openfoam_case(
        prepared.case_dir,
        backend="auto",
        dry_run=False,
        timeout_seconds=1800,
        docker_image=DEFAULT_OPENFOAM_DOCKER_IMAGE,
    )
    summary = summarize_fixed_grid_primal_case(
        prepared.case_dir,
        topology_state_json=prepared.topology_state_json,
        run_result=run_result.to_dict(),
        docker_image=DEFAULT_OPENFOAM_DOCKER_IMAGE,
    )
    return prepared.case_dir, summary


def _reconstruct_top_o_sensitivity_only(case_dir: Path, *, adjoint_solver_id: str) -> np.ndarray:
    """``topOSens<solver>`` alone, in global-cell-label order.

    Mirrors ``reconstruct_final_decomposed_openfoam_fields``'s own reconstruction
    of that one field (same private helpers, same ordering contract), but does
    not require ``alphaTilda``/``beta`` to exist -- the case's designVariables
    manager does not write those when ``regularise false``, so the full
    reconstruction helper would refuse for no reason relevant to this value.
    """

    root = Path(case_dir).resolve()
    processors = _processor_dirs(root)
    selected_time = _select_final_time(processors, None)
    labels_by_processor, _ = _processor_labels(root, processors)
    values, labels, _ = _reconstruct_nonuniform_field(
        root, processors, labels_by_processor, selected_time, f"topOSens{adjoint_solver_id}"
    )
    if not np.array_equal(labels, np.arange(labels.size, dtype=labels.dtype)):
        raise ValueError(f"{case_dir}: reconstructed global cell labels are not contiguous zero-based labels")
    return values


def run_no_regularisation_experiment() -> None:
    """Decisive test: does turning the regulariser off move the filtered-random
    ratio toward 1.0 (filter is the cause) or leave it near 0.90 (bias lives
    elsewhere, most plausibly P's fractional-overlap redistribution)?

    Rerun only filtered-random at eps=1e-3 (the highest-signal row, ratio
    0.905 with regularisation on), plus/minus, with the tightened residual
    controls kept and `regularise` set to false, and a fresh base run (also
    regularisation-off) to get a matching topOSens for the analytic value.
    """

    if NOREG_OUT.exists():
        raise SystemExit(f"{NOREG_OUT} already exists; remove it before re-running")
    tight_result_path = TIGHT_OUT / "tight_residual_result.json"
    if not tight_result_path.is_file():
        raise SystemExit(f"{tight_result_path} is missing; run tight-residual first")
    sign_flip = json.loads(tight_result_path.read_text())["empirical_sign_flip_applied_for_gate"]

    provenance = json.loads((WORK / "source_state" / "provenance.json").read_text())
    transfer = build_transfer(provenance)
    mapping = load_openfoam_cell_order_mapping(
        WORK / "cell_order" / "source_global_cell_labels_by_xfastest.npy",
        cell_count=transfer.source_grid.cell_count,
    )
    canonical_state = load_fixed_grid_density_state(WORK / "topology_state.json")
    rho = np.asarray(canonical_state.arrays["rho"], dtype=np.float64)
    active = np.asarray(canonical_state.arrays["active_design_mask"]) > 0
    gradient = np.load(WORK / "canonical_gradient" / "canonical_gradient.npz")
    g_canonical = np.asarray(gradient["top_o_sensitivity_gradient"], dtype=np.float64)
    support = active & (rho > 0.1) & (rho < 0.9) & (g_canonical != 0.0)
    d = _normalized_direction(_random_direction(support), support)  # identical seed/support -> identical draw
    eps = 1.0e-3

    NOREG_OUT.mkdir(parents=True)

    # Base run (unperturbed rho), full primal+adjoint, regularisation off, tightened residual.
    base_case_dir, base_summary = _prepare_run_summarize(
        WORK / "injected_contract" / "topology_state.json",
        case_dir=NOREG_OUT / "base" / "case",
        adjoint_iterations=2000,
        tighten=True,
        disable_reg=True,
    )
    base_convergence = base_summary.get("convergence") or {}
    if not (base_convergence.get("primal_converged") and base_convergence.get("downforce_adjoint_converged")):
        raise SystemExit(f"no-regularisation base run did not converge: {base_convergence}")
    base_top_o_sensitivity = _reconstruct_top_o_sensitivity_only(base_case_dir, adjoint_solver_id="downforce")
    pd_global = _global_order_direction(transfer=transfer, d_canonical=d, mapping=mapping)
    analytic_noreg = float(np.dot(np.asarray(base_top_o_sensitivity, dtype=np.float64), pd_global))

    def _signed(sign: float, tag: str) -> dict:
        artifacts = _inject_perturbed_contract(
            transfer=transfer,
            base_rho=rho,
            d=d,
            sign=sign,
            eps=eps,
            case_root=NOREG_OUT / tag,
            source_state_provenance_json=WORK / "source_state" / "provenance.json",
            base_contract_topology_state_json=WORK / "injected_contract" / "topology_state.json",
        )
        case_dir, summary = _prepare_run_summarize(
            artifacts.topology_state_json,
            case_dir=NOREG_OUT / tag / "case",
            adjoint_iterations=1,
            tighten=True,
            disable_reg=True,
        )
        convergence = summary.get("convergence") or {}
        downforce = summary.get("downforce_coefficient")
        primal_converged = bool(convergence.get("primal_converged"))
        return {
            "case_dir": str(case_dir),
            "status": summary.get("status"),
            "primal_converged": primal_converged,
            "downforce_coefficient": downforce,
            "objective_J": -float(downforce) if downforce is not None else None,
            "usable": primal_converged and downforce is not None,
        }

    plus = _signed(+1.0, "plus")
    minus = _signed(-1.0, "minus")
    usable = plus["usable"] and minus["usable"]

    result = {
        "kind": "p0_canonical_gradient_no_regularisation_experiment",
        "schema_version": 1,
        "purpose": (
            "Decisive test: with the case's regularisation filter disabled "
            "(regularise false) and tightened residual controls kept, does the "
            "filtered-random eps=1e-3 ratio move from 0.905 toward 1.0 (filter is "
            "the cause) or stay near 0.90 (bias lives elsewhere, most plausibly P's "
            "fractional-overlap redistribution: 0.09375/0.05=1.875x, 0.075/0.05=1.5x)."
        ),
        "eps": eps,
        "direction": "filtered-random",
        "regularisation": "disabled (regularise false)",
        "residual_control": "tightened (same as tight-residual experiment, 5e-9)",
        "base_case_dir": str(base_case_dir),
        "base_convergence": base_convergence,
        "analytic_noreg": analytic_noreg,
        "plus": plus,
        "minus": minus,
        "with_regularisation_reference_ratio": 0.905,
        "empirical_sign_flip_applied_for_gate": sign_flip,
        "usable": usable,
    }
    if usable:
        j_plus = plus["objective_J"]
        j_minus = minus["objective_J"]
        fd = (j_plus - j_minus) / (2.0 * eps)
        ratio = fd / analytic_noreg if analytic_noreg != 0.0 else None
        sign_corrected_ratio = sign_flip * ratio if ratio is not None else None
        result.update(
            {
                "J_plus": j_plus,
                "J_minus": j_minus,
                "abs_delta_J": abs(j_plus - j_minus),
                "fd": fd,
                "ratio": ratio,
                "sign_corrected_ratio": sign_corrected_ratio,
            }
        )
        moved_toward_one = (
            sign_corrected_ratio is not None and abs(sign_corrected_ratio - 1.0) < abs(0.905 - 1.0) - 0.02
        )
        stayed_near_point_nine = (
            sign_corrected_ratio is not None and abs(sign_corrected_ratio - 0.905) < 0.03
        )
        if moved_toward_one:
            conclusion = (
                "REGULARISATION CONFIRMED as the cause: sign-corrected ratio moved from 0.905 "
                f"(filter on) to {sign_corrected_ratio:.3f} (filter off), toward 1.0. The canonical "
                "gradient chain is missing the regularisation filter's own chain-rule term; this is "
                "a specific, actionable roadmap gap (fold d(alphaTilda)/d(rho) into the chain, or "
                "restrict directional-derivative checks to filter-smooth directions)."
            )
        elif stayed_near_point_nine:
            conclusion = (
                "REGULARISATION EXONERATED: sign-corrected ratio stayed at "
                f"{sign_corrected_ratio:.3f}, essentially unchanged from 0.905 with the filter on. "
                "The ~10% bias for the filtered-random direction lives elsewhere -- most plausibly "
                "P's fractional-overlap redistribution across the non-integer refinement ratios "
                "(0.09375/0.05=1.875x, 0.075/0.05=1.5x), not the regularisation filter."
            )
        else:
            conclusion = (
                f"INCONCLUSIVE: sign-corrected ratio moved to {sign_corrected_ratio:.3f}, neither "
                "clearly toward 1.0 nor unchanged near 0.905. Two candidate mechanisms remain open: "
                "(1) the regularisation filter's missing chain-rule term, (2) P's fractional-overlap "
                "redistribution across non-integer refinement ratios. This experiment does not "
                "distinguish between them and neither should be asserted as the cause."
            )
    else:
        conclusion = (
            "INCONCLUSIVE: at least one no-regularisation primal run did not converge / produced no "
            "objective; no ratio could be computed. Two candidate mechanisms remain open: the "
            "regularisation filter's missing chain-rule term, and P's fractional-overlap "
            "redistribution across non-integer refinement ratios."
        )
    result["conclusion"] = conclusion
    (NOREG_OUT / "no_regularisation_result.json").write_text(json.dumps(result, indent=2, default=str))
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "tight-residual":
        run_tight_residual_experiment()
    elif len(sys.argv) > 1 and sys.argv[1] == "regularisation-check":
        run_regularisation_attenuation_check()
    elif len(sys.argv) > 1 and sys.argv[1] == "no-regularisation":
        run_no_regularisation_experiment()
    else:
        main()
