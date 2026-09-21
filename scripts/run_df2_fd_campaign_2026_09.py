"""Run the registered P6 solver-side FD campaign on the refreshed P0 fixture.

Preconditions (all under ``work/df2_fd_refresh``):

1. ``source_state/provenance.json`` — qualified dual transfer built from the
   current ProblemSpec (``cfd-sdf transfer-stage-t-candidate-to-openfoam``);
2. ``injected_contract/topology_state.json`` — base source contract injected
   from ``P @ rho``;
3. ``canonical_gradient/canonical_gradient.npz`` — produced by
   ``cfd-sdf transfer-openfoam-gradient-to-canonical`` from the base run;
4. ``primal_base`` — the base OpenFOAM case (primal + qualified adjoint).

The campaign uses the three registered directions (gradient-aligned plus two
random seeds) at the four registered epsilons, evaluates the rows with
``evaluate_fd_campaign_rows`` against the registered manifest, and writes
``fd_campaign_result.json`` next to the runs. It never changes the manifest.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import p0_canonical_gradient_fd_suite as suite  # noqa: E402

from cfd_sdf.fd_preregistration import (  # noqa: E402
    evaluate_fd_campaign_rows,
    read_fd_campaign_manifest,
)
from cfd_sdf.fixed_grid_canonical_state_injection import (  # noqa: E402
    inject_canonical_state_into_fixed_grid_contract,
)
from cfd_sdf.execution import DEFAULT_OPENFOAM_DOCKER_IMAGE, run_openfoam_case  # noqa: E402
from cfd_sdf.fixed_grid_primal import (  # noqa: E402
    load_fixed_grid_density_state,
    prepare_fixed_grid_primal_case,
    run_fixed_grid_primal_case,
    summarize_fixed_grid_primal_case,
)

WORK = ROOT / "work" / "df2_fd_refresh"
OUT = WORK / "fd_campaign"  # overridden by DF2_CAMPAIGN_SUBDIR at runtime
MANIFEST = ROOT / "docs" / "evidence" / "fd_campaign_p6_solver_side_manifest_2026_09.json"
import os

TEMPLATE = Path(os.environ.get("DF2_TEMPLATE", str(WORK / "template_frozen")))
CAMPAIGN_SUBDIR = os.environ.get("DF2_CAMPAIGN_SUBDIR", "fd_campaign")
TIGHT_RESIDUAL = os.environ.get("DF2_TIGHT_RESIDUAL", "0") == "1"
TIGHT_PRIMAL_RESIDUAL = "5.e-9"
TIGHT_PRIMAL_NITERS = 5000
EPSILONS = (3.0e-5, 1.0e-4, 3.0e-4, 1.0e-3)
RANDOM_SEEDS = (11, 2026)


def _random_direction(support: np.ndarray, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    d = np.zeros(support.shape, dtype=np.float64)
    d[np.flatnonzero(support)] = rng.standard_normal(int(np.count_nonzero(support)))
    return d


def _array_sha256(values: np.ndarray) -> str:
    array = np.ascontiguousarray(np.asarray(values))
    header = json.dumps(
        {"dtype": array.dtype.str, "shape": list(array.shape)},
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(header + b"\n" + array.tobytes()).hexdigest()


def _write_candidate_sidecar(
    base_provenance: dict,
    rho_xfastest: np.ndarray,
    mapping: np.ndarray,
    *,
    npz_path: Path,
    provenance_path: Path,
) -> None:
    """Write a perturbed state NPZ with its own provenance sidecar.

    The injection is fail-closed on ``artifact_file`` and per-array hashes, so a
    perturbed state cannot reuse the base candidate's provenance.
    """

    rho_global = np.empty_like(rho_xfastest)
    rho_global[mapping] = rho_xfastest
    np.savez(
        npz_path,
        source_rho_xfastest=rho_xfastest,
        source_rho_global_label=rho_global,
        source_global_cell_labels_by_xfastest=mapping.astype(np.int64),
    )
    provenance = copy.deepcopy(base_provenance)
    provenance["artifact_file"] = {
        "path": str(npz_path),
        "sha256": hashlib.sha256(npz_path.read_bytes()).hexdigest(),
    }
    exported = provenance.get("exported_arrays")
    if not isinstance(exported, dict):
        raise SystemExit("base provenance is missing exported_arrays")
    for name, record in exported.items():
        if name == "source_rho_xfastest":
            record["sha256"] = _array_sha256(rho_xfastest)
            record["cell_count"] = int(rho_xfastest.size)
            record["range"] = [float(rho_xfastest.min()), float(rho_xfastest.max())]
        elif name == "source_rho_global_label":
            record["sha256"] = _array_sha256(rho_global)
            record["cell_count"] = int(rho_global.size)
        elif name == "source_global_cell_labels_by_xfastest":
            expected = _array_sha256(mapping.astype(np.int64))
            if record.get("sha256") != expected:
                raise SystemExit(
                    "base provenance cell-order hash does not match the loaded mapping"
                )
        else:
            raise SystemExit(f"unexpected exported array in base provenance: {name}")
    provenance_path.write_text(json.dumps(provenance, indent=2), encoding="utf-8")


def _tighten_primal_residual(case_dir: Path) -> None:
    """Match the p.*/U.* residualControl to 5e-9 and lift the primal nIters cap."""

    import re

    path = case_dir / "system" / "optimisationDict"
    text = path.read_text(encoding="utf-8")
    text = re.sub(r'("p\.\*"\s+)5\.e-7;', rf"\g<1>{TIGHT_PRIMAL_RESIDUAL};", text)
    text = re.sub(r'("U\.\*"\s+)5\.e-7;', rf"\g<1>{TIGHT_PRIMAL_RESIDUAL};", text)
    text, count = re.subn(r"\bnIters\s+1000\s*;", f"nIters {TIGHT_PRIMAL_NITERS};", text)
    if count != 1:
        raise SystemExit(
            f"expected exactly one primal nIters=1000 to patch in {path}, found {count}"
        )
    path.write_text(text, encoding="utf-8", newline="\n")


def run_signed_case(
    *,
    transfer,
    base_provenance: dict,
    mapping: np.ndarray,
    base_rho: np.ndarray,
    direction: np.ndarray,
    sign: float,
    epsilon: float,
    row_dir: Path,
) -> dict:
    tag = "plus" if sign > 0 else "minus"
    case_root = row_dir / tag
    case_root.mkdir(parents=True, exist_ok=True)
    rho_pm = base_rho + sign * epsilon * direction
    source_rho = transfer.transfer_state_to_source(rho_pm)
    npz_path = case_root / "perturbed_source_state.npz"
    provenance_path = case_root / "perturbed_source_state.provenance.json"
    _write_candidate_sidecar(
        base_provenance,
        source_rho,
        mapping,
        npz_path=npz_path,
        provenance_path=provenance_path,
    )
    contract = inject_canonical_state_into_fixed_grid_contract(
        openfoam_source_state_npz=npz_path,
        source_state_provenance_json=provenance_path,
        topology_state_json=WORK / "injected_contract" / "topology_state.json",
        output_directory=case_root / "contract",
    )
    if TIGHT_RESIDUAL:
        prepared = prepare_fixed_grid_primal_case(
            contract.topology_state_json,
            case_dir=case_root / "case",
            template_case_dir=TEMPLATE,
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
        primal_summary_json = prepared.case_dir / "fixed_grid_primal_summary.json"
    else:
        result = run_fixed_grid_primal_case(
            contract.topology_state_json,
            case_dir=case_root / "case",
            template_case_dir=TEMPLATE,
            density_variant="seed",
            backend="auto",
            execute=True,
            adjoint_iterations=1,
            timeout_seconds=1800,
        )
        summary = result.summary
        primal_summary_json = result.primal_summary_json
    convergence = summary.get("convergence") or {}
    downforce = summary.get("downforce_coefficient")
    primal_converged = bool(convergence.get("primal_converged"))
    return {
        "tag": tag,
        "primal_summary_json": str(primal_summary_json),
        "status": summary.get("status"),
        "primal_converged": primal_converged,
        "primal_iterations": convergence.get("primal_iterations"),
        "downforce_coefficient": downforce,
        "drag_coefficient": summary.get("drag_coefficient"),
        "objective_J": -float(downforce) if downforce is not None else None,
        "usable": primal_converged and downforce is not None,
        "tight_primal_residual": TIGHT_RESIDUAL,
    }


def main() -> None:
    global OUT
    OUT = WORK / CAMPAIGN_SUBDIR
    if OUT.exists():
        raise SystemExit(f"{OUT} already exists; remove it before re-running")
    print(f"template={TEMPLATE} out={OUT}", flush=True)

    manifest, manifest_hash = read_fd_campaign_manifest(MANIFEST)
    provenance = json.loads((WORK / "source_state" / "provenance.json").read_text())
    transfer = suite.build_transfer(provenance)
    mapping = np.load(
        WORK / "cell_order" / "source_global_cell_labels_by_xfastest.npy",
        allow_pickle=False,
    ).astype(np.int64)

    canonical_state = load_fixed_grid_density_state(WORK / "topology_state.json")
    rho = np.asarray(canonical_state.arrays["rho"], dtype=np.float64)
    active = np.asarray(canonical_state.arrays["active_design_mask"]) > 0

    gradient_path = WORK / "canonical_gradient" / "canonical_gradient.npz"
    if not gradient_path.is_file():
        raise SystemExit(
            f"{gradient_path} is missing; run the base case and "
            "transfer-openfoam-gradient-to-canonical first"
        )
    gradient = np.load(gradient_path)
    g_canonical = np.asarray(gradient["top_o_sensitivity_gradient"], dtype=np.float64)

    support = active & (rho > 0.1) & (rho < 0.9) & (g_canonical != 0.0)
    if int(np.count_nonzero(support)) == 0:
        raise SystemExit("the feasible support is empty; refusing to run the campaign")

    directions = {
        "gradient_aligned": suite._normalized_direction(g_canonical, support),
        **{
            f"random_seed_{seed}": suite._normalized_direction(
                _random_direction(support, seed), support
            )
            for seed in RANDOM_SEEDS
        },
    }

    OUT.mkdir(parents=True)
    print(f"campaign subdir: {CAMPAIGN_SUBDIR}", flush=True)
    rows: list[dict] = []
    for direction_name, direction in directions.items():
        for epsilon in EPSILONS:
            row_dir = OUT / "runs" / direction_name / f"{epsilon:.0e}"
            plus = run_signed_case(
                transfer=transfer,
                base_provenance=provenance,
                mapping=mapping,
                base_rho=rho,
                direction=direction,
                sign=+1.0,
                epsilon=epsilon,
                row_dir=row_dir,
            )
            minus = run_signed_case(
                transfer=transfer,
                base_provenance=provenance,
                mapping=mapping,
                base_rho=rho,
                direction=direction,
                sign=-1.0,
                epsilon=epsilon,
                row_dir=row_dir,
            )
            usable = bool(plus["usable"] and minus["usable"])
            if not usable:
                rows.append(
                    {
                        "direction": direction_name,
                        "epsilon": float(epsilon),
                        "converged": False,
                        "plus": plus,
                        "minus": minus,
                    }
                )
                continue
            fd = (plus["objective_J"] - minus["objective_J"]) / (2.0 * epsilon)
            analytic = -float(np.dot(g_canonical, direction))  # dJ/drho = -g
            rows.append(
                {
                    "direction": direction_name,
                    "epsilon": float(epsilon),
                    "converged": True,
                    "fd": fd,
                    "analytic": analytic,
                    "ratio": fd / analytic if analytic != 0.0 else None,
                    "primal_iterations_plus": plus["primal_iterations"],
                    "primal_iterations_minus": minus["primal_iterations"],
                }
            )
            print(
                f"{direction_name} eps={epsilon:.0e} ratio={rows[-1]['ratio']}",
                flush=True,
            )

    verdict = evaluate_fd_campaign_rows(
        manifest,
        [row for row in rows if row["converged"]],
    )
    result = {
        "kind": "df2_solver_side_fd_campaign_result",
        "manifest_hash": manifest_hash,
        "rows": rows,
        "verdict": verdict,
        "sign_convention": "dJ/drho = -d(downforce_coefficient)/drho",
        "solver_template": "work/df2_fd_refresh/template_frozen (regularise false, maxInitChange 0)",
        "claims_not_made": [
            "no target-physics claim",
            "no claim outside the reduced laminar fixture and the registered rows",
        ],
    }
    (OUT / "fd_campaign_result.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8"
    )
    print(json.dumps({"passed": verdict["passed"], "n_failures": verdict["n_failures"]}))


if __name__ == "__main__":
    main()
