"""Wide-margin binarized candidate set for the Stage T vs Stage V re-test.

Reuses ``scripts/stage_t_ramp_interp.py`` in full (Ctx, write_candidate,
evaluate, discreteness, iso_metrics, phase_export, ramp/dramp, ...) via
import, redirected to a NEW ``work/`` directory so ``work/ramp_interp`` is
never touched -- see that module's docstring for the RAMP/adjoint mechanism
this inherits unchanged.

Adds only what is new for this task:

  * ``reuse`` phase: six q=100 candidates already fully evaluated in
    ``work/ramp_interp`` (opt_q100_step{0,1,2}_try0[_r12]) are copied byte-
    identical into the new fixture and re-exported here -- no new Docker
    runs, since primal+adjoint+VTK already exist for them.
  * ``oc_step_ineq``: the volume constraint as an INEQUALITY (mean(rho) <=
    v_target) instead of the base loop's equality. Equality forces the OC
    bisection to spread any unused budget into marginal cells even once the
    gradient no longer wants more material -- the "surplus dumped at beta
    near 0.003" defect this task's brief names. Inequality only bisects
    when the unconstrained (kappa=1) step would exceed the target; otherwise
    it is accepted as-is and surplus is released, not spread.
  * ``thickness_metrics``: distance-transform half-thickness of the solid
    (beta > 0.5) body, in grid cells, to check candidates are not 1-2 cell
    slabs before spending a Stage V mesh on them.
  * ``continue_q`` phase: resumes a lineage with more OC steps at a FIXED q
    (no continuation to a new q), using the inequality step, to push the
    downforce margin within one q-series without the higher-q roughness
    that broke q300's watertightness.

No density filter is added: the q100 lineage this continues is already
watertight/single-component/thick enough (see report), so the filter named
as a possible remedy in the brief was not needed to reach the required
margins. See the run's own report printed at the end for whether that
holds.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import numpy as np
from scipy.ndimage import distance_transform_edt

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

import stage_t_ramp_interp as base  # noqa: E402

# Redirect the imported module's output location -- everything it writes
# (fixture, template, candidates, export) lands under a fresh directory.
# work/ramp_interp is only ever read (to copy specific finished runs from).
NEW_OUT = ROOT / "work" / "wide_margin_binarized"
base.OUT = NEW_OUT
base.FIXTURE = NEW_OUT / "fixture"
base.TEMPLATE = NEW_OUT / "template"

OLD_OUT = ROOT / "work" / "ramp_interp"
OLD_FIXTURE = OLD_OUT / "fixture"
ALPHA_MAX = 250.0
Q100 = 100.0
Q30 = 30.0

REUSE_Q100 = [
    "opt_q100_step0_try0", "opt_q100_step1_try0", "opt_q100_step2_try0",
    "opt_q100_step0_try0_r12", "opt_q100_step1_try0_r12", "opt_q100_step2_try0_r12",
]
REUSE_Q30 = ["opt_q30_step0_try0", "opt_q30_step1_try0", "opt_q30_step2_try0"]


# --- inequality OC step -------------------------------------------------------


def oc_step_ineq(g, rho, active, move_limit, v_target, eta=0.5, iters=60, zero_floor=0.0):
    """Same multiplicative OC update as ``base.oc_step``, but the volume
    budget is an upper bound, not an exact target. If the unconstrained
    (kappa=1) candidate already respects it, take it unmodified -- the
    ratchet doesn't force extra material into marginal (low-beta) cells
    just to hit the target exactly."""
    lower_box = np.clip(rho - move_limit, 0.0, 1.0)
    upper_box = np.clip(rho + move_limit, 0.0, 1.0)
    b = np.maximum(g, 0.0) ** eta
    rho_eff = np.where(active & (rho <= 0.0), zero_floor, rho) if zero_floor > 0.0 else rho

    def candidate(kappa: float) -> np.ndarray:
        result = np.clip(rho_eff * b * kappa, lower_box, upper_box)
        result[~active] = rho[~active]
        return result

    natural = candidate(1.0)
    if float(np.mean(natural[active])) <= v_target:
        return natural
    return base.oc_step(g, rho, active, move_limit, v_target, eta=eta, iters=iters, zero_floor=zero_floor)


# --- thickness -----------------------------------------------------------------


def thickness_metrics(ctx: "base.Ctx", beta: np.ndarray, threshold: float = 0.5) -> dict:
    """Distance-transform half-thickness (in grid cells) of the solid body.
    A slab of true thickness T cells has every interior voxel's distance to
    the nearest void <= T/2, so ``2 * p10(edt)`` estimates the thinnest
    typical cross-section; ``thin_fraction`` is the share of solid cells
    within 1 cell of the surface (i.e. inside a <=2-cell-thick slab)."""
    solid = ctx.to3d(beta) > threshold
    if not solid.any():
        return {"n_solid_cells": 0}
    edt = distance_transform_edt(solid)
    vals = edt[solid]
    return {
        "n_solid_cells": int(solid.sum()),
        "half_thickness_cells_p10": float(np.percentile(vals, 10)),
        "half_thickness_cells_median": float(np.median(vals)),
        "half_thickness_cells_max": float(vals.max()),
        "estimated_min_slab_thickness_cells": float(2 * np.percentile(vals, 10)),
        "thin_fraction_within_1cell_of_surface": float((vals <= 1.0).mean()),
    }


# --- reuse already-evaluated candidates ----------------------------------------


def reuse_candidate(ctx: "base.Ctx", cid: str) -> Path:
    dst = base.FIXTURE / "candidates" / cid
    if dst.exists():
        return dst
    src = OLD_FIXTURE / "candidates" / cid
    if not src.exists():
        raise SystemExit(f"{cid}: not found in {src}")
    shutil.copytree(src, dst)
    state = json.loads((dst / "topology_state.json").read_text())
    base.write_stage_t_candidate_binding(
        base.FIXTURE / f"{cid}.binding.json",
        problem=ctx.spec,
        problem_snapshot=base.FIXTURE / "problem_spec_snapshot.json",
        canonical_grid_snapshot=base.FIXTURE / "canonical_grid_snapshot.json",
        canonical_geometry_manifest=base.FIXTURE / "canonical_geometry_mask_manifest.json",
        topology_state=dst / "topology_state.json",
        density_vti=dst / "density.vti",
        candidate_id=cid,
        parent_candidate_id=state.get("parent_candidate_id"),
        iteration=int(state["iteration"]),
        rho_variant="rho_projected",
    )
    return dst


def phase_reuse() -> None:
    ctx = base.Ctx(ALPHA_MAX)
    if not ctx.cell_order_npy.exists():
        ctx.cell_order_npy.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(OLD_OUT / "cell_order" / "source_global_cell_labels_by_xfastest.npy", ctx.cell_order_npy)
    cids = []
    for cid in REUSE_Q100 + REUSE_Q30:
        reuse_candidate(ctx, cid)
        cids.append(cid)
    base.phase_export(ctx, cids)
    annotate_thickness(ctx, cids)


def annotate_thickness(ctx: "base.Ctx", cids: list[str]) -> None:
    for cid in cids:
        edir = NEW_OUT / "export" / cid
        manifest_path = edir / "candidate_manifest.json"
        if not manifest_path.exists():
            continue
        manifest = json.loads(manifest_path.read_text())
        cdir = base.FIXTURE / "candidates" / cid
        st = base.load_fixed_grid_density_state(cdir / "topology_state.json")
        beta = np.asarray(st.arrays["rho_projected"], dtype=np.float64)
        manifest["thickness_metrics"] = thickness_metrics(ctx, beta)
        manifest_path.write_text(json.dumps(manifest, indent=2))
        print(cid, manifest["thickness_metrics"])


# --- continue an existing lineage at a fixed q, inequality constraint ---------


def phase_continue(seed_cid: str, q: float, n_steps: int, v_target: float,
                    move_limit: float = 0.1, move_floor: float = 0.01, zero_floor: float = 1e-3) -> None:
    """Resume OC stepping on ``seed_cid`` (already at q, already evaluated
    with a converged gradient) using the inequality volume constraint, same
    q throughout (no continuation), for up to ``n_steps`` accepted steps."""
    ctx = base.Ctx(ALPHA_MAX)
    seed_dir = base.FIXTURE / "candidates" / seed_cid
    if not seed_dir.exists():
        raise SystemExit(f"{seed_cid}: run phase_reuse first")
    ev0 = json.loads((seed_dir / "evaluation.json").read_text())
    if not ev0["downforce_adjoint_converged"]:
        raise SystemExit(f"{seed_cid}: downforce adjoint not converged; cannot step on it")
    st = base.load_fixed_grid_density_state(seed_dir / "topology_state.json")
    rho = np.asarray(st.arrays["rho"], dtype=np.float64)
    g_beta = base.load_gradient(seed_dir)
    J = -ev0["downforce_coefficient"]
    parent, it = seed_cid, int(st.state["iteration"]) + 1
    ml = move_limit
    tag = f"_ineq_from_{seed_cid.split('_')[-2]}"
    for step in range(n_steps):
        g_rho = g_beta * base.dramp(rho, q)
        for attempt in range(4):
            cand = np.clip(oc_step_ineq(g_rho, rho, ctx.active, ml, v_target, zero_floor=zero_floor), 0, 1)
            step_size = float(np.max(np.abs((cand - rho)[ctx.active]))) if ctx.active.any() else 0.0
            cid = f"cont_q{q:g}_step{step}_try{attempt}{tag}"
            print(f"-- {cid}: max|drho|={step_size:g} v_before={float(rho[ctx.active].mean()):g} v_target={v_target:g}", flush=True)
            if step_size < 1e-6:
                print(f"{cid}: candidate is a numerical no-op (max|drho|={step_size:g}); stopping this lineage (plateau)")
                (NEW_OUT / "final_candidate_note.txt").open("a").write(f"{parent}: plateaued at step {step} (no-op candidate)\n")
                return
            cdir = base.write_candidate(ctx, cid, cand, q, parent=parent, iteration=it, note="inequality-constrained OC continuation")
            ev = base.evaluate(ctx, cdir, q, gradient=True)
            ok = ev["primal_converged"] and ev["downforce_adjoint_converged"] and ev["downforce_coefficient"] is not None
            dJ = (-ev["downforce_coefficient"] - J) if ok else None
            accepted = ok and dJ is not None and dJ <= 1e-9
            print(json.dumps({"candidate": cid, "downforce": ev.get("downforce_coefficient"), "drag": ev.get("drag_coefficient"),
                              "actual_dJ": dJ, "accepted": accepted, "design_rho_mean_nd": base.discreteness(cand, ctx.active)["mean_nd_4x(1-x)"]}), flush=True)
            if accepted:
                rho, J, g_beta = cand, -ev["downforce_coefficient"], base.load_gradient(cdir)
                parent, it = cid, it + 1
                break
            ml = max(ml / 2, move_floor)
        else:
            print(f"no attempt accepted at step {step}; stopping this lineage")
            break
    (NEW_OUT / f"final_candidate_{seed_cid}.txt").write_text(parent)
    print("lineage final candidate:", parent)


if __name__ == "__main__":
    phase = sys.argv[1]
    if phase == "reuse":
        phase_reuse()
    elif phase == "continue":  # continue <seed_cid> <q> <n_steps> <v_target>
        phase_continue(sys.argv[2], float(sys.argv[3]), int(sys.argv[4]), float(sys.argv[5]))
    elif phase == "export":  # export <candidate ids csv> -- after `continue`
        ctx = base.Ctx(ALPHA_MAX)
        cids = sys.argv[2].split(",")
        base.phase_export(ctx, cids)
        annotate_thickness(ctx, cids)
    else:
        raise SystemExit(__doc__)
