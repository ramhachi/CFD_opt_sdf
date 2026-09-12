"""Stage T penalized-interpolation (RAMP) test on the same-grid T1 fixture.

Formulation-hypothesis test, NOT qualification evidence. It asks one question:
does a convex material interpolation ``beta = f(rho)`` make the optimizer build
a solid body instead of the diffuse haze every previous run produced?

Chain (same grid, no transfer operator, no injection step):

    design rho (46080 canonical cells)
      -> beta = f_q(rho) = rho / (1 + q (1 - rho))          [Python owns this]
      -> solver contract whose ``rho`` array IS beta         [what OpenFOAM sees]
      -> adjointOptimisationFoam, regularisation reduced to identity
         (Helmholtz radius 1e-4 cells, ``function linear``; beta == alpha is
         asserted from the VTK output of every run, i.e. no double projection)
      -> converged ``topOSens`` = d(+downforce)/d(beta)      [gate-enforced]
      -> g_rho = g_beta * f_q'(rho)                          [chain rule]

Why not ``regularise false``: v2512 then never creates ``alphaTilda`` and the
repaired gradient-export gate (``reconstruct_final_decomposed_openfoam_fields``)
refuses the run. A near-zero Helmholtz radius is the identity to ~1e-10 and
keeps the artifact contract intact; the identity is measured, not assumed.

Phases (run in this order):
    selftest   pure-python asserts on f, f', the iso-surface metric
    check      mechanism check: equal-budget spreading series + fixed-shape
               density series, linear interpolation, primal only
    fd         chain-rule/sign check: converged adjoint at q, central FD along
               the masked gradient direction, primal only for the +/- runs
    optimize   OC steps with continuation on q, converged adjoints only
    report     discreteness / force-by-beta-band / iso-surface, before vs after
"""

from __future__ import annotations

import json
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pyvista as pv
import trimesh
from scipy.ndimage import binary_dilation

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from cfd_sdf.canonical_grid_snapshot import load_and_verify_canonical_grid_snapshot
from cfd_sdf.fixed_grid_contract import _write_cell_vti
from cfd_sdf.fixed_grid_primal import load_fixed_grid_density_state, run_fixed_grid_primal_case
from cfd_sdf.handoff import build_density_to_sdf_handoff
from cfd_sdf.openfoam_canonical_field_transfer import (
    reconstruct_and_write_canonical_gradient_transfer,
)
from cfd_sdf.openfoam_cell_order_derivation import derive_and_write_openfoam_cell_order_mapping
from cfd_sdf.problem_spec import load_problem_spec, problem_spec_sha256
from cfd_sdf.stage_t_candidate_binding import write_stage_t_candidate_binding

from stage_t_python_loop import oc_step

BASE = ROOT / "work" / "p0_closed_loop"
OUT = ROOT / "work" / "ramp_interp"
FIXTURE = OUT / "fixture"
TEMPLATE = OUT / "template"  # alphaMax 2500 (project value); other alphaMax -> template_alphamax<value>
EXAMPLE_TEMPLATE = ROOT / "examples/fixed_grid_backend_spike/openfoam/porous_force_3d_fd_base"
STATUS = "formulation_hypothesis_test_not_qualification_evidence"

RESPONSE_ID = "downforce"
ADJOINT_SOLVER_ID = "downforce"
AREF, UINF = 0.64, 1.0  # template optimisationDict; checked against the case at read time
BANDS = [(0.0, 0.1), (0.1, 0.3), (0.3, 0.5), (0.5, 0.7), (0.7, 0.9), (0.9, 1.0 + 1e-9)]

# --- interpolation -------------------------------------------------------------


def ramp(rho: np.ndarray, q: float) -> np.ndarray:
    return rho / (1.0 + q * (1.0 - rho))


def dramp(rho: np.ndarray, q: float) -> np.ndarray:
    return (1.0 + q) / (1.0 + q * (1.0 - rho)) ** 2


# --- fixture / template ------------------------------------------------------------


def ensure_dirs(alpha_max: float) -> Path:
    OUT.mkdir(parents=True, exist_ok=True)
    if not FIXTURE.exists():
        shutil.copytree(BASE, FIXTURE, ignore=shutil.ignore_patterns("stage_t_candidate_binding.json"))
    template = TEMPLATE if alpha_max == 2500.0 else OUT / f"template_alphamax{alpha_max:g}"
    if not template.exists():
        shutil.copytree(EXAMPLE_TEMPLATE, template)
        path = template / "system" / "optimisationDict"
        text = path.read_text()
        assert "regularise     true;" in text and "function       linear;" in text
        text, n = re.subn(r"meanRadiusMult\s+[0-9.eE+-]+;", "meanRadiusMult 1e-4;", text)
        assert n == 1
        text, n = re.subn(r"betaMax\s+[0-9.eE+-]+;", f"betaMax    {alpha_max:g};", text)
        assert n == 1
        path.write_text(text)
    return template


class Ctx:
    def __init__(self, alpha_max: float = 2500.0) -> None:
        self.template = ensure_dirs(alpha_max)
        self.spec = load_problem_spec(FIXTURE / "project.yaml")
        self.snapshot = load_and_verify_canonical_grid_snapshot(
            FIXTURE / "canonical_grid_snapshot.json", self.spec
        )
        self.state0 = load_fixed_grid_density_state(FIXTURE / "topology_state.json")
        assert self.state0.state["problem_spec_sha256"] == problem_spec_sha256(self.spec)
        a = self.state0.arrays
        self.active = (
            (a["active_design_mask"] > 0) & (a["allowed_mask"] > 0)
            & ~(a["forbidden_mask"] > 0) & ~(a["fixed_solid_mask"] > 0)
        )
        self.rho0 = np.asarray(a["rho"], dtype=np.float64)
        self.grid = self.state0.grid
        self.shape = tuple(self.grid.cell_shape)
        self.cell_volume = float(np.prod(self.grid.spacing))
        self.beta_max = float(
            re.search(r"betaMax\s+([0-9.eE+-]+);", (self.template / "system/optimisationDict").read_text()).group(1)
        )
        assert self.beta_max == alpha_max
        self.cell_order_npy = OUT / "cell_order" / "source_global_cell_labels_by_xfastest.npy"

    def to3d(self, flat: np.ndarray) -> np.ndarray:
        return np.asarray(flat).reshape(self.shape, order="F")

    def flat(self, arr3: np.ndarray) -> np.ndarray:
        return np.asarray(arr3).ravel(order="F")

    def labels(self) -> np.ndarray:
        return np.load(self.cell_order_npy)


# --- candidate -> solver contract -> run ----------------------------------------------------


def write_candidate(
    ctx: Ctx, cid: str, rho: np.ndarray, q: float, *, parent: str | None, iteration: int, note: str
) -> Path:
    """Write the design state, its verified candidate binding, and the same-grid
    solver contract whose ``rho`` array is the physical field f_q(rho)."""

    beta = ramp(rho, q)
    cdir = FIXTURE / "candidates" / cid
    cdir.mkdir(parents=True)
    a = ctx.state0.arrays
    masks = {k: np.asarray(a[k], dtype=np.uint8) for k in
             ("allowed_mask", "forbidden_mask", "fixed_solid_mask", "root_mask", "active_design_mask")}
    arrays = {
        "rho": rho.astype(np.float32),
        "rho_filtered": rho.astype(np.float32),
        "rho_projected": beta.astype(np.float32),
        "alpha": (ctx.beta_max * beta).astype(np.float32),
        **masks,
    }
    _write_cell_vti(ctx.grid, arrays, cdir / "density.vti", kind="fixed_grid_density")
    state = json.loads(json.dumps(ctx.state0.state))
    state.update(
        created_at_utc=datetime.now(timezone.utc).isoformat(),
        density_vti="density.vti",
        density_array="rho_projected",  # Stage S contours the field the solver saw
        iso_value=0.5,
        candidate_id=cid,
        parent_candidate_id=parent,
        iteration=iteration,
        qualification_status=STATUS,
        interpolation={
            "kind": "ramp", "q": q, "alpha_max_1_s": ctx.beta_max, "convention": "rho=1 solid",
            "formula": "rho_projected = rho / (1 + q (1 - rho)); alpha = betaMax * rho_projected",
            "derivative": "(1 + q) / (1 + q (1 - rho))**2",
            "owner": "python", "openfoam_regularisation": "Helmholtz radius 1e-4 cells + function linear == identity (asserted per run)",
        },
        note=note,
    )
    state["array_metadata"]["rho"]["source"] = "design variable (RAMP argument)"
    state["array_metadata"]["rho_filtered"]["source"] = "identity filter (H = I in this test)"
    state["array_metadata"]["rho_projected"]["source"] = f"RAMP q={q:g} of rho; the field injected into the solver"
    state["source_solver"].pop("initial_vtk", None)
    state["source_solver"].pop("final_vtk", None)
    state_json = cdir / "topology_state.json"
    state_json.write_text(json.dumps(state, indent=2))
    binding = write_stage_t_candidate_binding(
        FIXTURE / f"{cid}.binding.json",
        problem=ctx.spec,
        problem_snapshot=FIXTURE / "problem_spec_snapshot.json",
        canonical_grid_snapshot=FIXTURE / "canonical_grid_snapshot.json",
        canonical_geometry_manifest=FIXTURE / "canonical_geometry_mask_manifest.json",
        topology_state=state_json,
        density_vti=cdir / "density.vti",
        candidate_id=cid,
        parent_candidate_id=parent,
        iteration=iteration,
        rho_variant="rho_projected",
    )
    # Solver contract: same grid, rho := physical beta. This replaces the T0
    # transfer+injection step; provenance ties it to the candidate binding.
    sdir = cdir / "solver_contract"
    sdir.mkdir()
    solver_arrays = dict(arrays, rho=beta.astype(np.float32), rho_filtered=beta.astype(np.float32))
    _write_cell_vti(ctx.grid, solver_arrays, sdir / "density.vti", kind="fixed_grid_density")
    sstate = json.loads(json.dumps(state))
    sstate["density_array"] = "rho"
    sstate["array_metadata"]["rho"]["source"] = "physical field rho_projected of the bound candidate (same grid)"
    (sdir / "topology_state.json").write_text(json.dumps(sstate, indent=2))
    (sdir / "same_grid_contract_provenance.json").write_text(json.dumps({
        "kind": "same_grid_physical_field_contract",
        "candidate_binding": {"path": str(binding.path), "sha256": _sha(binding.path)},
        "candidate_topology_state": {"path": str(state_json), "sha256": _sha(state_json)},
        "rho_written": "rho_projected (RAMP q=%g) of the candidate, all cells" % q,
        "grid_sha256": ctx.snapshot.snapshot.grid_sha256,
        "transfer_operator": "none (design grid == solver grid == handoff grid)",
    }, indent=2))
    return cdir


def _sha(path: Path) -> str:
    import hashlib
    return hashlib.sha256(path.read_bytes()).hexdigest()


def evaluate(ctx: Ctx, cdir: Path, q: float, *, gradient: bool) -> dict:
    """Run primal (+ converged adjoints when ``gradient``), assert beta == injected,
    decompose the reported forces by beta band, and export the canonical gradient."""

    contract = cdir / "solver_contract" / "topology_state.json"
    result = run_fixed_grid_primal_case(
        contract,
        case_dir=cdir / "case",
        template_case_dir=ctx.template,
        density_variant="seed",
        backend="docker",
        execute=True,
        adjoint_iterations=None if gradient else 1,
        timeout_seconds=7200,
        problem_binding={
            "candidate_binding_json": str(FIXTURE / f"{cdir.name}.binding.json"),
            "response_id": RESPONSE_ID, "adjoint_solver_id": ADJOINT_SOLVER_ID,
            "interpolation": {"kind": "ramp", "q": q, "alpha_max_1_s": ctx.beta_max}, "qualification_status": STATUS,
            "audit_only_primal_check": not gradient,
        },
    )
    s = result.summary
    conv = s.get("convergence") or {}
    row = {
        "candidate": cdir.name, "q": q, "case_dir": str(result.case_dir),
        "primal_converged": bool(conv.get("primal_converged")),
        "downforce_adjoint_converged": bool(conv.get("downforce_adjoint_converged")),
        "iterations": {k: conv.get(k) for k in ("primal_iterations", "drag_adjoint_iterations", "downforce_adjoint_iterations")},
        "drag_coefficient": s.get("drag_coefficient"),
        "downforce_coefficient": s.get("downforce_coefficient"),
        "wall_seconds": _exec_time(result.case_dir),
    }
    if not ctx.cell_order_npy.exists():
        art = derive_and_write_openfoam_cell_order_mapping(
            result.case_dir, block_mesh_dict=result.case_dir / "system/blockMeshDict",
            output_directory=ctx.cell_order_npy.parent, backend="docker",
        )
        labels = np.load(art.mapping_npy)
        assert np.array_equal(labels, np.arange(labels.size)), "T1 blockMesh is not x-fastest; density injection order would be wrong"
    injected = np.asarray(load_fixed_grid_density_state(contract).arrays["rho"], dtype=np.float64)
    row.update(decompose(ctx, result.case_dir, injected))
    if gradient and row["primal_converged"]:
        art = reconstruct_and_write_canonical_gradient_transfer(
            case_dir=result.case_dir,
            adjoint_solver_id=ADJOINT_SOLVER_ID,
            block_mesh_dict=result.case_dir / "system/blockMeshDict",
            verified_snapshot=ctx.snapshot,
            source_global_cell_labels_by_xfastest=ctx.cell_order_npy,
            output_directory=cdir / "gradient",
            response_id=RESPONSE_ID,
            problem_spec=ctx.spec,
        )
        row["gradient_npz"] = str(art.fields_npz)
    (cdir / "evaluation.json").write_text(json.dumps(row, indent=2))
    print(json.dumps({k: v for k, v in row.items() if k != "bands"}), flush=True)
    return row


def _exec_time(case_dir: Path) -> float | None:
    m = re.findall(r"ClockTime = (\d+) s", (case_dir / "log.adjointOptimisationFoam").read_text(errors="replace"))
    return float(m[-1]) if m else None


def load_gradient(cdir: Path) -> np.ndarray:
    (npz,) = (cdir / "gradient").glob("*.npz")
    with np.load(npz) as z:
        return np.asarray(z["top_o_sensitivity_gradient"], dtype=np.float64)


# --- measurements ---------------------------------------------------------------------


def decompose(ctx: Ctx, case_dir: Path, injected: np.ndarray) -> dict:
    """Exact per-cell force decomposition: J = 2/(Aref UInf^2) * betaMax * sum(beta (U.d) V).
    Same integrand as objectivePorousDirectionalForce::J(); totals are checked
    against the solver's reported coefficients."""

    mesh = pv.read(sorted(case_dir.glob("VTK/**/internal.vtu"))[-1])
    labels = ctx.labels()
    beta = np.asarray(mesh.cell_data["beta"], dtype=np.float64)[labels]
    U = np.asarray(mesh.cell_data["U"], dtype=np.float64)[labels]
    txt = (case_dir / "system/optimisationDict").read_text()
    assert f"Aref            {AREF:g}" in txt and f"UInf            {UINF:g}" in txt
    scale = 2.0 / (AREF * UINF**2) * ctx.beta_max * ctx.cell_volume
    gap = float(np.max(np.abs(beta - injected)))
    out = {"solver_beta_minus_injected_max_abs": gap, "solver_beta_max": float(beta.max())}
    assert gap < 1e-5, f"OpenFOAM still alters the injected field: max|beta - injected| = {gap}"
    summary = json.loads((case_dir / "fixed_grid_primal_summary.json").read_text())
    bands = {}
    for name, d, key in (("downforce", np.array([0, 0, -1.0]), "downforce_coefficient"),
                         ("drag", np.array([1.0, 0, 0]), "drag_coefficient")):
        contrib = scale * beta * (U @ d)
        total = float(contrib.sum())
        reported = summary.get(key)
        bands[name] = {
            "total_from_cells": total, "reported": reported,
            "relative_mismatch": abs(total - reported) / max(abs(reported), 1e-30) if reported is not None else None,
            "by_beta_band": {
                f"[{lo:g},{hi:.2g})": {
                    "cells": int(((beta >= lo) & (beta < hi)).sum()),
                    "force": float(contrib[(beta >= lo) & (beta < hi)].sum()),
                    "fraction": float(contrib[(beta >= lo) & (beta < hi)].sum() / total) if abs(total) > 1e-30 else None,
                } for lo, hi in BANDS
            },
        }
    speed = np.linalg.norm(U, axis=1) / UINF
    out["leak_mean_speed_ratio_by_band"] = {
        f"[{lo:g},{hi:.2g})": (float(speed[(beta >= lo) & (beta < hi)].mean()) if ((beta >= lo) & (beta < hi)).any() else None)
        for lo, hi in BANDS
    }
    out["bands"] = bands
    return out


def discreteness(field: np.ndarray, active: np.ndarray) -> dict:
    v = np.asarray(field, dtype=np.float64)[active]
    return {
        "mean_nd_4x(1-x)": float(np.mean(4 * v * (1 - v))), "max": float(v.max()),
        "n_gt_0.9": int((v > 0.9).sum()), "n_lt_0.1": int((v < 0.1).sum()),
        "n_grey_0.1_0.9": int(((v >= 0.1) & (v <= 0.9)).sum()), "mean": float(v.mean()),
    }


def iso_metrics(ctx: Ctx, field: np.ndarray, iso: float = 0.5) -> dict:
    """0.5 iso-surface of a cell field after cell->point averaging (as the handoff does)."""
    img = pv.ImageData(dimensions=np.array(ctx.shape) + 1, spacing=ctx.grid.spacing, origin=ctx.grid.origin)
    img.cell_data["rho"] = np.asarray(field, dtype=np.float64)
    surf = img.cell_data_to_point_data().contour([iso], scalars="rho").triangulate()
    if surf.n_cells == 0:
        return {"faces": 0, "note": "empty iso-surface"}
    faces = surf.faces.reshape(-1, 4)[:, 1:]
    mesh = trimesh.Trimesh(np.asarray(surf.points), faces, process=True)
    return {
        "faces": int(len(mesh.faces)), "vertices": int(len(mesh.vertices)),
        "watertight": bool(mesh.is_watertight),
        "components": int(len(mesh.split(only_watertight=False))),
        "volume_m3": float(abs(mesh.volume)) if mesh.is_watertight else None,
        "bounds_m": np.asarray(mesh.bounds).tolist(),
    }


# --- phases ----------------------------------------------------------------------------


def phase_check(ctx: Ctx) -> None:
    """Mechanism check under the CURRENT (linear) interpolation, primal only.
    A: equal design budget spread over dilations of the base plate.
    B: fixed base-plate shape at decreasing uniform density (saturation curve)."""
    S = ctx.rho0 > 0
    budget = float(ctx.rho0[S].sum() * 2)  # plate at 0.5 -> same cells at 1.0
    rows = []
    for r in (0, 1, 2, 3, 4):
        m = ctx.flat(binary_dilation(ctx.to3d(S), iterations=r)) & ctx.active if r else S
        rho = np.zeros_like(ctx.rho0)
        rho[m] = budget / m.sum()
        cid = f"check_A_spread_r{r}"
        cdir = write_candidate(ctx, cid, rho, 0.0, parent=None, iteration=0,
                               note=f"equal budget {budget:g} cell-volumes over {int(m.sum())} cells (dilation {r})")
        row = evaluate(ctx, cdir, 0.0, gradient=False)
        rows.append({"series": "A_equal_budget", "dilation": r, "cells": int(m.sum()), "rho": float(budget / m.sum()), **_forces(row)})
    for level in (0.5, 0.3, 0.1, 0.03, 0.01):
        rho = np.where(S, level, 0.0)
        cdir = write_candidate(ctx, f"check_B_level_{level:g}", rho, 0.0, parent=None, iteration=0,
                               note=f"base plate shape at uniform rho={level:g}")
        row = evaluate(ctx, cdir, 0.0, gradient=False)
        rows.append({"series": "B_fixed_shape", "cells": int(S.sum()), "rho": level, **_forces(row)})
    (OUT / "mechanism_check.json").write_text(json.dumps({"status": STATUS, "rows": rows}, indent=2))
    for r in rows:
        print(r)


def _forces(row: dict) -> dict:
    return {k: row[k] for k in ("downforce_coefficient", "drag_coefficient", "primal_converged", "wall_seconds", "solver_beta_minus_injected_max_abs")}


def phase_check2(alpha_max: float, q: float, levels=(1.0, 0.3, 0.1, 0.03, 0.01), dilations=(0, 1, 2, 3, 4)) -> None:
    """Same two series as ``check`` but through a candidate (alphaMax, q) map:
    B = fixed-shape saturation curve at this alphaMax (linear), A = equal DESIGN
    budget spread, physical field f_q(rho). If downforce now falls with spreading,
    the haze stopped paying under this map."""
    ctx = Ctx(alpha_max)
    S = ctx.rho0 > 0
    budget = float(ctx.rho0[S].sum() * 2)
    tag = f"a{alpha_max:g}"
    rows = []
    for level in levels:
        cdir = write_candidate(ctx, f"check2_{tag}_B_level_{level:g}", np.where(S, level, 0.0), 0.0, parent=None, iteration=0,
                               note=f"base plate at uniform physical beta={level:g}, alphaMax={alpha_max:g}")
        rows.append({"series": "B_fixed_shape", "alpha_max": alpha_max, "rho": level, **_forces(evaluate(ctx, cdir, 0.0, gradient=False))})
    for r in dilations:
        m = ctx.flat(binary_dilation(ctx.to3d(S), iterations=r)) & ctx.active if r else S
        rho = np.zeros_like(ctx.rho0)
        rho[m] = budget / m.sum()
        cdir = write_candidate(ctx, f"check2_{tag}_q{q:g}_A_spread_r{r}", rho, q, parent=None, iteration=0,
                               note=f"equal design budget {budget:g} over {int(m.sum())} cells, RAMP q={q:g}, alphaMax={alpha_max:g}")
        rows.append({"series": "A_equal_design_budget", "alpha_max": alpha_max, "q": q, "dilation": r, "cells": int(m.sum()),
                     "rho": float(budget / m.sum()), "physical_beta": float(ramp(budget / m.sum(), q)), **_forces(evaluate(ctx, cdir, q, gradient=False))})
    (OUT / f"mechanism_check2_{tag}_q{q:g}.json").write_text(json.dumps({"status": STATUS, "rows": rows}, indent=2))
    for r in rows:
        print(r)


def phase_fd(ctx: Ctx, q: float, eps_list=(1e-2, 3e-2)) -> None:
    """Chain-rule and sign check at the base plate, RAMP q: converged adjoint once,
    then central FD along the masked gradient direction (primal only)."""
    rho = ctx.rho0.copy()
    cid = f"fd_base_q{q:g}"
    cdir = write_candidate(ctx, cid, rho, q, parent=None, iteration=0, note="FD baseline")
    base = evaluate(ctx, cdir, q, gradient=True)
    g_beta = load_gradient(cdir)
    g_rho = g_beta * dramp(rho, q)
    S = ctx.rho0 > 0
    d = np.where(S, g_rho, 0.0)
    d /= np.max(np.abs(d))
    pred = float(np.dot(g_rho, d))  # d(+downforce)/d eps along d
    rows = []
    for eps in eps_list:
        vals = {}
        for sign in (+1, -1):
            c = write_candidate(ctx, f"fd_q{q:g}_eps{eps:g}_{'plus' if sign > 0 else 'minus'}",
                                np.clip(rho + sign * eps * d, 0, 1), q, parent=cid, iteration=1, note="FD probe")
            vals[sign] = evaluate(ctx, c, q, gradient=False)["downforce_coefficient"]
        fd = (vals[1] - vals[-1]) / (2 * eps)
        rows.append({"eps": eps, "fd_d_downforce": fd, "predicted_g_rho_dot_d": pred, "ratio_fd_over_pred": fd / pred})
        print(rows[-1], flush=True)
    (OUT / f"fd_check_q{q:g}.json").write_text(json.dumps({
        "status": STATUS, "q": q, "baseline": _forces(base), "adjoint_iterations": base["iterations"],
        "sign_convention": "gradient array = d(+downforce)/d(beta); J = -downforce so dJ/drho = -(g_beta * f'(rho))",
        "rows": rows}, indent=2))


def phase_optimize(ctx: Ctx, q_schedule: list[float], steps_per_q: int, v_final: float,
                   move_limit: float = 0.1, move_floor: float = 0.01, zero_floor: float = 1e-3,
                   resume_from: str | None = None) -> None:
    rho = ctx.rho0.copy()
    v0 = float(rho[ctx.active].mean())
    history = []
    parent, it = None, 0
    n_accepted = 0
    if resume_from:  # continue from an accepted candidate (same lineage, volume ramp finished)
        prev = load_fixed_grid_density_state(FIXTURE / "candidates" / resume_from / "topology_state.json")
        rho = np.asarray(prev.arrays["rho"], dtype=np.float64)
        parent, it, n_accepted = resume_from, int(prev.state["iteration"]) + 1, 6
        history = json.loads((OUT / "optimize_history.json").read_text())["history"]
        run_tag = f"_r{it}"
    else:
        run_tag = ""
    for q in q_schedule:
        # C4: every q is its own problem; re-baseline J and g at the new q --
        # unless we resume from a candidate already evaluated at this q.
        if resume_from and q == history[-1]["q"] and history[-1]["candidate"] == resume_from:
            cid, cdir = resume_from, FIXTURE / "candidates" / resume_from
            base = json.loads((cdir / "evaluation.json").read_text())
        else:
            cid = f"opt_q{q:g}_baseline{run_tag}"
            cdir = write_candidate(ctx, cid, rho, q, parent=parent, iteration=it, note="continuation baseline")
            base = evaluate(ctx, cdir, q, gradient=True)
            parent, it = cid, it + 1
            history.append({"q": q, "kind": "baseline", "candidate": cid, "J": -base["downforce_coefficient"], **_forces(base), "adjoint_iterations": base["iterations"]})
        if not base["downforce_adjoint_converged"]:
            raise SystemExit(f"{cid}: downforce adjoint did not converge; stopping (no unconverged gradient is stepped on)")
        J = -base["downforce_coefficient"]
        g_beta = load_gradient(cdir)
        ml = move_limit
        for step in range(steps_per_q):
            g_rho = g_beta * dramp(rho, q)
            for attempt in range(3):
                v_target = v0 + (v_final - v0) * min(1.0, (n_accepted + 1) / 6)
                cand = np.clip(oc_step(g_rho, rho, ctx.active, ml, v_target, zero_floor=zero_floor), 0, 1)
                pred_dJ = -float(np.dot(g_rho[ctx.active], (cand - rho)[ctx.active]))
                cid = f"opt_q{q:g}_step{step}_try{attempt}{run_tag}"
                cdir = write_candidate(ctx, cid, cand, q, parent=parent, iteration=it, note="OC candidate")
                ev = evaluate(ctx, cdir, q, gradient=True)
                ok = ev["primal_converged"] and ev["downforce_adjoint_converged"] and ev["downforce_coefficient"] is not None
                dJ = (-ev["downforce_coefficient"] - J) if ok else None
                row = {"q": q, "kind": "step", "candidate": cid, "move_limit": ml, "v_target": v_target,
                       "predicted_dJ": pred_dJ, "actual_dJ": dJ, **_forces(ev), "adjoint_iterations": ev["iterations"],
                       "design_rho": discreteness(cand, ctx.active), "physical_beta": discreteness(ramp(cand, q), ctx.active)}
                accepted = ok and dJ <= 1e-9
                row["accepted"] = accepted
                history.append(row)
                print(json.dumps({k: row[k] for k in ("candidate", "predicted_dJ", "actual_dJ", "accepted", "downforce_coefficient")}), flush=True)
                (OUT / "optimize_history.json").write_text(json.dumps({"status": STATUS, "history": history}, indent=2))
                if accepted:
                    rho, J, g_beta = cand, -ev["downforce_coefficient"], load_gradient(cdir)
                    parent, it, n_accepted = cid, it + 1, n_accepted + 1
                    break
                ml = max(ml / 2, move_floor)
    (OUT / "final_candidate.txt").write_text(parent or "")
    print("final candidate:", parent)


def phase_report(ctx: Ctx) -> None:
    final = (OUT / "final_candidate.txt").read_text().strip()
    fdir = FIXTURE / "candidates" / final
    st = load_fixed_grid_density_state(fdir / "topology_state.json")
    q = st.state["interpolation"]["q"]
    rho = np.asarray(st.arrays["rho"], dtype=np.float64)
    beta = np.asarray(st.arrays["rho_projected"], dtype=np.float64)
    ev = json.loads((fdir / "evaluation.json").read_text())
    before_state = load_fixed_grid_density_state(ROOT / "work/stage_t_python_loop_export/candidate_b_zero_floor/topology_state.json")
    before_rho = np.asarray(before_state.arrays["rho"], dtype=np.float64)
    before_case = ROOT / "work/brinkman_scoping/alphamax_sweep/alpha_2500/case"
    before_dec = _decompose_existing(ctx, before_case)
    report = {
        "status": STATUS, "final_candidate": final, "q": q,
        "final_forces": _forces(ev), "adjoint_iterations": ev["iterations"],
        "after": {
            "design_rho": discreteness(rho, ctx.active), "physical_beta": discreteness(beta, ctx.active),
            "force_by_beta_band": ev["bands"], "leak_by_band": ev["leak_mean_speed_ratio_by_band"],
            "iso_0.5_of_design_rho": iso_metrics(ctx, rho), "iso_0.5_of_physical_beta": iso_metrics(ctx, beta),
        },
        "before_candidate_b_zero_floor_T1": {
            "rho": discreteness(before_rho, ctx.active), "force_by_beta_band": before_dec,
            "iso_0.5": iso_metrics(ctx, before_rho),
        },
        "base_plate": {"rho": discreteness(ctx.rho0, ctx.active), "iso_0.5": iso_metrics(ctx, ctx.rho0)},
    }
    try:
        h = build_density_to_sdf_handoff(fdir / "topology_state.json", output_dir=fdir / "stage_s_handoff")
        report["stage_s_handoff"] = {"ok": h.ok, "surface": h.fidelity_report.get("surface"), "discreteness": h.fidelity_report.get("discreteness")}
    except Exception as exc:  # noqa: BLE001 - report the refusal, it is a result
        report["stage_s_handoff"] = {"ok": False, "error": str(exc)}
    (OUT / "report.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


def phase_export(ctx: Ctx, cids: list[str]) -> None:
    """Hash-bound export (same form as work/stage_t_python_loop_export/*) for the
    cross-fidelity ranking test: topology_state.json, density.vti, iso_surface.stl
    from the handoff, plus Stage T forces, normalization, discreteness and the
    STL-volume-vs-design-volume check."""
    for cid in cids:
        cdir = FIXTURE / "candidates" / cid
        st = load_fixed_grid_density_state(cdir / "topology_state.json")
        rho = np.asarray(st.arrays["rho"], dtype=np.float64)
        beta = np.asarray(st.arrays["rho_projected"], dtype=np.float64)
        ev = json.loads((cdir / "evaluation.json").read_text())
        hdir = cdir / "stage_s_handoff"
        handoff_error = None
        if not (hdir / "iso_surface.stl").exists():
            try:
                build_density_to_sdf_handoff(cdir / "topology_state.json", output_dir=hdir)
            except Exception as exc:  # noqa: BLE001 - a refusal is a result to export, not to hide
                handoff_error = str(exc)
        fr = json.loads((hdir / "fidelity_report.json").read_text()) if (hdir / "fidelity_report.json").exists() else {}
        edir = OUT / "export" / cid
        edir.mkdir(parents=True, exist_ok=True)
        files = {}
        for src, name in ((cdir / "topology_state.json", "topology_state.json"), (cdir / "density.vti", "density.vti"),
                          (hdir / "iso_surface.stl", "iso_surface.stl")):
            if src.exists():
                shutil.copy2(src, edir / name)
                files[name.replace(".", "_")] = {"path": name, "sha256": _sha(edir / name)}
        iso = iso_metrics(ctx, beta)
        v_beta = float(beta[ctx.active].sum() * ctx.cell_volume)
        v_thr = float((beta[ctx.active] > 0.5).sum() * ctx.cell_volume)
        manifest = {
            "kind": "stage_t_ramp_interp_export_manifest", "schema_version": 1,
            "qualification_status": STATUS,
            "candidate_id": cid, "run_directory": str(cdir.relative_to(ROOT)),
            "candidate_binding_json": str((FIXTURE / f"{cid}.binding.json").relative_to(ROOT)),
            "formulation": st.state["interpolation"],
            "grid": "same grid for design, solver and handoff: 60x32x24 canonical cells, voxel 0.05 m (no transfer operator)",
            "contoured_field": "rho_projected (= the physical field the solver integrated forces on; solver beta == injected to <1e-8)",
            "files": files,
            "stage_s_handoff": {"dir": str(hdir.relative_to(ROOT)), "ok": handoff_error is None and (hdir / "iso_surface.stl").exists(),
                                "error": handoff_error},
            "stage_t_predicted_forces": {
                "source": str((cdir / "case/fixed_grid_primal_summary.json").relative_to(ROOT)),
                "primal_converged": ev["primal_converged"], "downforce_adjoint_converged": ev["downforce_adjoint_converged"],
                "drag_coefficient": ev["drag_coefficient"], "downforce_coefficient": ev["downforce_coefficient"],
                "sign_convention": {"drag": "positive in +X", "downforce": "positive in -Z"},
                "force_fraction_from_beta_lt_0.1_cells": {k: ev["bands"][k]["by_beta_band"]["[0,0.1)"]["fraction"] for k in ("downforce", "drag")},
                "force_fraction_from_beta_ge_0.9_cells": {k: ev["bands"][k]["by_beta_band"]["[0.9,1)"]["fraction"] for k in ("downforce", "drag")},
                "caveat": "Stage T integrates the porous force over ALL cells; the share from beta<0.1 cells is force the contoured STL does not represent.",
            },
            "normalization": {
                "objective_function_type": "porousDirectionalForce: 2/(Aref UInf^2) * alphaMax * sum(beta (U.d) V) over the whole domain",
                "alpha_max_1_s": ctx.beta_max, "Aref_m2": AREF, "UInf": UINF,
                "drag_direction": [1.0, 0.0, 0.0], "downforce_direction": [0.0, 0.0, -1.0],
                "note": "alphaMax=250 here (project value was 2500); a fixed solid shape gives 0.2595 vs 0.2774 downforce at 250 vs 2500 (work/ramp_interp/mechanism_check*.json). Body-fitted comparison must use Aref=0.64, UInf=1.",
                "flow_conditions_source": "work/p0_closed_loop/project.yaml:flow_cases[0] (declared); solver ran laminar, nu=0.01, U=1 as the template does",
            },
            "discreteness_active_cells": {"design_rho": discreteness(rho, ctx.active), "physical_beta": discreteness(beta, ctx.active)},
            "iso_surface_metrics": {"iso_value": 0.5, **iso, "handoff_surface": fr.get("surface")},
            "volume_check": {
                "design_solid_volume_sum_beta_m3": v_beta, "design_threshold_volume_beta_gt_0.5_m3": v_thr,
                "iso_surface_volume_m3": iso.get("volume_m3"),
                "iso_over_threshold": (iso["volume_m3"] / v_thr) if iso.get("volume_m3") and v_thr else None,
                "note": "for a binary field the 0.5 iso-surface volume should be close to the threshold volume; a large gap is an extraction defect",
            },
        }
        (edir / "candidate_manifest.json").write_text(json.dumps(manifest, indent=2))
        print(cid, "DF=%.4f" % ev["downforce_coefficient"], "drag=%.4f" % ev["drag_coefficient"],
              "beta>0.9:", manifest["discreteness_active_cells"]["physical_beta"]["n_gt_0.9"],
              "beta<0.1 share DF/drag:", manifest["stage_t_predicted_forces"]["force_fraction_from_beta_lt_0.1_cells"],
              "iso:", {k: iso.get(k) for k in ("faces", "watertight", "components", "volume_m3")}, "iso/thr", manifest["volume_check"]["iso_over_threshold"])


def _decompose_existing(ctx: Ctx, case_dir: Path) -> dict:
    """Band decomposition of an existing (regularise true) T1 run: solver beta from VTK."""
    mesh = pv.read(sorted(case_dir.glob("VTK/**/internal.vtu"))[-1])
    beta = np.asarray(mesh.cell_data["beta"], dtype=np.float64)
    U = np.asarray(mesh.cell_data["U"], dtype=np.float64)
    beta_max = float(re.search(r"betaMax\s+([0-9.eE+-]+);", (case_dir / "system/optimisationDict").read_text()).group(1))
    scale = 2.0 / (AREF * UINF**2) * beta_max * ctx.cell_volume
    out = {"solver_beta_max": float(beta.max()), "alpha_max_1_s": beta_max}
    for name, d in (("downforce", np.array([0, 0, -1.0])), ("drag", np.array([1.0, 0, 0]))):
        c = scale * beta * (U @ d)
        out[name] = {f"[{lo:g},{hi:.2g})": {"cells": int(((beta >= lo) & (beta < hi)).sum()),
                                            "fraction": float(c[(beta >= lo) & (beta < hi)].sum() / c.sum())} for lo, hi in BANDS}
    return out


def selftest() -> None:
    rng = np.random.default_rng(0)
    r = rng.uniform(0, 1, 1000)
    assert np.allclose(ramp(r, 0.0), r)
    for q in (8.0, 100.0, 300.0):
        assert ramp(np.array([0.0, 1.0]), q).tolist() == [0.0, 1.0]
        assert np.all(np.diff(ramp(np.sort(r), q)) > 0)
        h = 1e-6
        assert np.allclose(dramp(r, q), (ramp(r + h, q) - ramp(r - h, q)) / (2 * h), rtol=1e-5)
        n = 1000  # spreading a budget over n cells: convex f makes it worth less
        assert n * ramp(np.array([0.1 / n]), q)[0] < ramp(np.array([0.1]), q)[0]
    ctx = Ctx()
    cube = np.zeros(ctx.shape)
    cube[20:30, 10:20, 8:16] = 1.0
    m = iso_metrics(ctx, ctx.flat(cube))
    assert m["watertight"] and m["components"] == 1 and abs(m["volume_m3"] - 10 * 10 * 8 * ctx.cell_volume) / (800 * ctx.cell_volume) < 0.2, m
    print("selftest ok", m)


if __name__ == "__main__":
    phase = sys.argv[1]
    if phase == "selftest":
        selftest()
    elif phase == "check":
        phase_check(Ctx())
    elif phase == "check2":  # check2 <alpha_max> <q> [levels csv]
        kw = {"levels": tuple(float(x) for x in sys.argv[4].split(","))} if len(sys.argv) > 4 else {}
        if len(sys.argv) > 5:
            kw["dilations"] = tuple(int(x) for x in sys.argv[5].split(",") if x)
        phase_check2(float(sys.argv[2]), float(sys.argv[3]), **kw)
    elif phase == "fd":  # fd <alpha_max> <q>
        phase_fd(Ctx(float(sys.argv[2])), float(sys.argv[3]))
    elif phase == "optimize":  # optimize <alpha_max> <q csv> <steps per q> <v_final> [resume_from candidate]
        phase_optimize(Ctx(float(sys.argv[2])), [float(x) for x in sys.argv[3].split(",")], int(sys.argv[4]), float(sys.argv[5]),
                       resume_from=sys.argv[6] if len(sys.argv) > 6 else None)
    elif phase == "export":  # export <alpha_max> <candidate ids csv>
        phase_export(Ctx(float(sys.argv[2])), sys.argv[3].split(","))
    elif phase == "report":  # report <alpha_max>
        phase_report(Ctx(float(sys.argv[2])))
    else:
        raise SystemExit(__doc__)
