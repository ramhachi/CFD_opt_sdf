"""Minimum length scale for Stage T: cone density filter in front of RAMP.

Continues ``scripts/stage_t_ramp_interp.py`` (imported as ``base``; Ctx,
write_candidate, evaluate, discreteness, iso_metrics, phase_export, ramp/dramp
are reused unchanged) and adds the audit's C3 chain:

    rho --H--> rho_tilde --f_RAMP--> beta --> inject
    g_rho = H.T @ ( f'(rho_tilde) * g_beta )

``H`` is a linear-hat (cone) filter over a PHYSICAL radius, restricted to the
active design cells and normalised per cell. Written as H = M K M / d with
M = active mask, K = symmetric cone convolution, d = K M (per-cell weight sum),
the exact transpose is H.T = M K (M . / d): the division moves from the output
side to the input side. Both are implemented with ``scipy.ndimage.convolve``
(uniform cells, so volume weighting is a constant) and checked by the adjoint
identity <Hx, y> == <x, H.T y> in ``selftest``.

The filter radius is derived from the ProblemSpec's ``minimum_solid_width_m``
(already parsed, listed and preflight-checked, never enforced by Stage T):
``filter_radius_m = minimum_solid_width_m / 2``. Each radius therefore gets its
own fixture whose ``project.yaml`` declares it, with regenerated spec/grid
snapshots so every candidate binding carries the declared length scale.

Phases: selftest | fd <w_min> <q> | optimize <w_min> <q csv> <steps csv> <v_final>
        | geom <w_min> <candidate csv> (mesh-only Stage V at V0/V1/V2 + metrics)
        | stagev_level <w_min> <candidate> <level> <voxel> [eta]
        | control (8-cell cube through the same mesh sweep) | export <w_min> <cids>
"""

from __future__ import annotations

import json
import re
import shutil
import sys
import tempfile
from pathlib import Path

import numpy as np
import trimesh
import yaml
from scipy.ndimage import convolve, distance_transform_edt

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

import stage_t_ramp_interp as base  # noqa: E402

from cfd_sdf.canonical_geometry_masks import build_canonical_geometry_mask_snapshot  # noqa: E402
from cfd_sdf.cfd import evaluate_check_mesh  # noqa: E402
from cfd_sdf.execution import run_openfoam_case  # noqa: E402
from cfd_sdf.openfoam import generate_openfoam_case, problem_spec_to_project_config  # noqa: E402
from cfd_sdf.problem_spec import load_problem_spec, problem_spec_sha256, write_problem_spec_snapshot  # noqa: E402
from cfd_sdf.sdf import build_fields  # noqa: E402

SWEEP_ROOT = ROOT / "work" / "filtered_ramp"
SV_SPEC = ROOT / "work/stage_sv_laminar/project_matched_re_laminar.yaml"
OLD_CELL_ORDER = ROOT / "work/ramp_interp/cell_order/source_global_cell_labels_by_xfastest.npy"
ALPHA_MAX = 250.0
STAGE_V_LEVELS = {"V0": 0.1, "V1": 0.05, "V2": 0.025}
MESH_ONLY_ALLRUN = """#!/usr/bin/env bash
set -euo pipefail
blockMesh
surfaceFeatureExtract || true
snappyHexMesh -overwrite
checkMesh -allGeometry -allTopology | tee log.checkMesh
"""


# --- fixture per declared minimum_solid_width_m -----------------------------------------


def setup(width_m: float, eta: float = 0.5, kind: str = "cone") -> "base.Ctx":
    out = SWEEP_ROOT / f"wmin_{width_m:g}"
    base.OUT, base.FIXTURE, base.TEMPLATE = out, out / "fixture", out / "template"
    fixture = base.FIXTURE
    if not fixture.exists():
        shutil.copytree(base.BASE, fixture, ignore=shutil.ignore_patterns("stage_t_candidate_binding.json"))
        yml = fixture / "project.yaml"
        doc = yaml.safe_load(yml.read_text())
        doc["topology_policy"]["minimum_solid_width_m"] = width_m
        yml.write_text(yaml.safe_dump(doc, sort_keys=False))
        spec = load_problem_spec(yml)
        assert spec.topology_policy.minimum_solid_width_m == width_m and spec.migration.execution_ready
        write_problem_spec_snapshot(spec, fixture / "problem_spec_snapshot.json")
        build_canonical_geometry_mask_snapshot(spec, output_dir=fixture)  # rewrites snapshot, masks, manifest
        state = json.loads((fixture / "topology_state.json").read_text())
        state["problem_spec_sha256"] = problem_spec_sha256(spec)
        state["provenance"]["minimum_solid_width_m"] = width_m
        state["provenance"]["fixture_note"] = "copy of work/p0_closed_loop with topology_policy.minimum_solid_width_m declared; snapshots regenerated"
        (fixture / "topology_state.json").write_text(json.dumps(state, indent=2))
        (out / "cell_order").mkdir(parents=True, exist_ok=True)
        shutil.copy2(OLD_CELL_ORDER, out / "cell_order" / OLD_CELL_ORDER.name)
    ctx = base.Ctx(ALPHA_MAX)
    ctx.width_m = width_m
    ctx.filter = ConeFilter(ctx, width_m / 2.0) if kind == "cone" else BlockFilter(ctx, width_m)
    ctx.b = 0.0  # projection sharpness; set per continuation stage
    ctx.eta = eta  # projection threshold; > 0.5 = eroded physical design (larger guaranteed solid size)
    ctx.name_tag = ("" if eta == 0.5 else f"_eta{eta:g}") + ("" if kind == "cone" else f"_{kind}")
    # 1-D hat-filter estimate: a slab of thickness t at rho=1 reaches centre value 1-(1-t/2R)^2
    ctx.filter.meta["predicted_min_slab_thickness_cells_1d_estimate"] = 2 * ctx.filter.radius_cells * (1 - (1 - eta) ** 0.5)
    ctx.filter.meta["projection_eta"] = eta
    return ctx


class ConeFilter:
    """H = M K M / d, H.T = M K (M ./ d); K = cone convolution, d = K M."""

    def __init__(self, ctx: "base.Ctx", radius_m: float) -> None:
        voxel = float(ctx.grid.spacing[0])
        assert all(abs(s - voxel) < 1e-12 for s in ctx.grid.spacing)
        self.radius_m, self.radius_cells = radius_m, radius_m / voxel
        r = int(np.ceil(self.radius_cells))
        ijk = np.mgrid[-r:r + 1, -r:r + 1, -r:r + 1]
        dist = np.sqrt((ijk ** 2).sum(axis=0))
        self.kernel = np.maximum(self.radius_cells - dist, 0.0)
        self.mask = ctx.to3d(ctx.active).astype(np.float64)
        self.denom = convolve(self.mask, self.kernel, mode="constant", cval=0.0)
        self.denom_safe = np.where(self.mask > 0, self.denom, 1.0)
        self.ctx = ctx
        self.meta = {
            "kind": "cone_density_filter", "minimum_solid_width_m": 2 * radius_m,
            "relation": "filter_radius_m = minimum_solid_width_m / 2", "filter_radius_m": radius_m,
            "filter_radius_cells": self.radius_cells, "weights": "max(R - |x_i - x_j|, 0), uniform cell volume",
            "boundary": "restricted to active design cells; normalised by the sum of weights present",
            "transpose": "H.T y = M K (M y / d) with d = K M (exact; H is not symmetric)",
        }

    def H(self, x: np.ndarray) -> np.ndarray:
        x3 = self.ctx.to3d(x) * self.mask
        return self.ctx.flat(self.mask * convolve(x3, self.kernel, mode="constant", cval=0.0) / self.denom_safe)

    def HT(self, y: np.ndarray) -> np.ndarray:
        y3 = self.ctx.to3d(y) * self.mask / self.denom_safe
        return self.ctx.flat(self.mask * convolve(y3, self.kernel, mode="constant", cval=0.0))


ETA = 0.5


def project(x: np.ndarray, b: float, eta: float = ETA) -> np.ndarray:
    """tanh Heaviside projection at threshold eta; b -> 0 is the identity, b large is a step."""
    if b <= 0:
        return x
    den = np.tanh(b * eta) + np.tanh(b * (1 - eta))
    return (np.tanh(b * eta) + np.tanh(b * (x - eta))) / den


def dproject(x: np.ndarray, b: float, eta: float = ETA) -> np.ndarray:
    if b <= 0:
        return np.ones_like(x)
    den = np.tanh(b * eta) + np.tanh(b * (1 - eta))
    return b * (1 - np.tanh(b * (x - eta)) ** 2) / den


def physical(ctx, rho: np.ndarray, q: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """rho -> rho_tilde = H rho -> p = tanh_b(rho_tilde; eta) -> beta = f_q(p)."""
    rho_tilde = np.clip(ctx.filter.H(rho), 0.0, 1.0)
    p = np.clip(project(rho_tilde, ctx.b, ctx.eta), 0.0, 1.0)  # tanh rounding can exceed 1 by 1e-7; the binding refuses that
    return rho_tilde, p, base.ramp(p, q)


class BlockFilter:
    """Piecewise-constant (super-cell) filter: rho_tilde = block mean of rho over
    non-overlapping blocks tiling the active design box. Every block is one
    effective design variable, so no solid feature can be thinner than a block:
    the minimum length scale is enforced exactly rather than statistically.
    H = B D^-1 B^T (B: cell-in-block indicator, D: block cell counts) is an
    orthogonal projection, hence symmetric: H.T == H (checked in selftest)."""

    def __init__(self, ctx: "base.Ctx", width_m: float) -> None:
        voxel = float(ctx.grid.spacing[0])
        idx = np.flatnonzero(ctx.active)
        nx, ny, nz = ctx.shape
        ix, iy, iz = idx % nx, (idx // nx) % ny, idx // (nx * ny)
        self.lo = np.array([ix.min(), iy.min(), iz.min()])
        ext = np.array([ix.max(), iy.max(), iz.max()]) - self.lo + 1
        assert int(ctx.active.sum()) == int(np.prod(ext)), "active design cells must form one box"
        n = int(round(width_m / voxel))
        # the block edge must tile the box; x (50 cells) is not divisible by 4 -> nearest divisor
        self.block = np.array([min((d for d in range(1, e + 1) if e % d == 0), key=lambda d: abs(d - n)) for e in ext])
        self.nblocks = ext // self.block
        self.ext = ext
        self.mask = ctx.to3d(ctx.active).astype(np.float64)
        self.ctx = ctx
        self.radius_cells = float(self.block.min()) / 2.0
        self.meta = {
            "kind": "block_average_filter", "minimum_solid_width_m": width_m,
            "block_cells": self.block.tolist(), "block_m": (self.block * voxel).tolist(),
            "relation": "block edge (y, z) = minimum_solid_width_m; x edge = nearest divisor of the box length",
            "guaranteed_min_solid_thickness_cells": int(self.block.min()),
            "transpose": "H = B D^-1 B^T is an orthogonal projection: H.T == H (exact)",
        }

    def _blocks(self, x3: np.ndarray) -> np.ndarray:
        s = tuple(slice(self.lo[i], self.lo[i] + self.ext[i]) for i in range(3))
        sub = x3[s]
        b = self.block
        return sub.reshape(self.nblocks[0], b[0], self.nblocks[1], b[1], self.nblocks[2], b[2]), s

    def H(self, x: np.ndarray) -> np.ndarray:
        x3 = self.ctx.to3d(x) * self.mask
        blocks, s = self._blocks(x3)
        mean = blocks.mean(axis=(1, 3, 5), keepdims=True)
        out = np.zeros_like(x3)
        out[s] = np.broadcast_to(mean, blocks.shape).reshape(tuple(self.ext))
        return self.ctx.flat(out * self.mask)

    def HT(self, y: np.ndarray) -> np.ndarray:
        return self.H(y)


def chain_gradient(ctx: "base.Ctx", rho: np.ndarray, q: float, g_beta: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """g_rho = H.T ( h_b'(rho_tilde) * f_q'(h_b(rho_tilde)) * g_beta )."""
    rho_tilde, p, _ = physical(ctx, rho, q)
    return rho_tilde, ctx.filter.HT(dproject(rho_tilde, ctx.b, ctx.eta) * base.dramp(p, q) * g_beta)


def write(ctx, cid, rho, q, *, parent, iteration, note):
    rho_tilde, p, _ = physical(ctx, rho, q)
    meta = {"filter": ctx.filter.meta, "projection": {"kind": "tanh_heaviside", "eta": ctx.eta, "b": ctx.b,
                                                       "chain": "beta = f_q(h_b(H rho)); g_rho = H.T(h_b'(H rho) f_q'(h_b(H rho)) g_beta)"}}
    return base.write_candidate(ctx, cid, rho, q, parent=parent, iteration=iteration, note=note,
                                rho_tilde=rho_tilde, ramp_arg=p, extra_meta=meta)


# --- ported unchanged in substance from scripts/stage_t_wide_margin.py (importing it would
#     re-point base.OUT to that run's directory as a side effect) ---------------------------


def oc_step_ineq(g, rho, active, move_limit, v_target, eta=0.5, zero_floor=0.0):
    """OC update with the volume budget as an upper bound. KKT with the constraint
    inactive (multiplier 0) is the move-limited ascent step: every cell with
    positive gradient goes to its upper box, the rest to their lower box. If
    that respects the budget it is taken; otherwise the equality OC (bisection
    on the multiplier) applies. (The wide-margin script's kappa=1 'natural'
    step is not this: unscaled sqrt(g) < 1 shrinks every cell.)"""
    lower_box, upper_box = np.clip(rho - move_limit, 0, 1), np.clip(rho + move_limit, 0, 1)
    natural = np.where(g > 0.0, upper_box, lower_box)
    natural[~active] = rho[~active]
    if float(np.mean(natural[active])) <= v_target:
        return natural
    return base.oc_step(g, rho, active, move_limit, v_target, eta=eta, zero_floor=zero_floor)


def thickness_metrics(ctx, beta: np.ndarray, threshold: float = 0.5) -> dict:
    """Thickness (cells) of the beta > 0.5 body. ``local_thickness`` is the
    Hildebrand-Ruegsegger measure: for each solid cell, the diameter of the
    largest inscribed sphere covering it (2 x EDT of the covering centre),
    computed by dilating {EDT >= r} by a ball of radius r for each r. A slab of
    thickness t reports t everywhere; the EDT-based half-thickness percentiles
    of the earlier metric under-read a 4-cell slab as 2, so both are kept."""
    from scipy.ndimage import binary_dilation as _dil
    solid = ctx.to3d(beta) > threshold
    if not solid.any():
        return {"n_solid_cells": 0}
    edt = distance_transform_edt(solid)
    vals = edt[solid]
    local = np.zeros(solid.shape)
    for r in np.unique(np.round(vals, 3))[::-1]:
        if r <= 0:
            continue
        rr = int(np.ceil(r))
        g = np.mgrid[-rr:rr + 1, -rr:rr + 1, -rr:rr + 1]
        ball = (g ** 2).sum(axis=0) <= r * r + 1e-9
        covered = _dil(edt >= r - 1e-9, structure=ball) & solid & (local == 0)
        local[covered] = 2 * r
    lt = local[solid]
    return {
        "n_solid_cells": int(solid.sum()),
        "half_thickness_cells_p10": float(np.percentile(vals, 10)),
        "half_thickness_cells_median": float(np.median(vals)),
        "half_thickness_cells_max": float(vals.max()),
        "estimated_min_slab_thickness_cells": float(2 * np.percentile(vals, 10)),
        "thin_fraction_within_1cell_of_surface": float((vals <= 1.0).mean()),
        "local_thickness_cells_p10": float(np.percentile(lt, 10)),
        "local_thickness_cells_median": float(np.median(lt)),
        "local_thickness_cells_max": float(lt.max()),
        "fraction_thinner_than_4_cells": float((lt < 4 - 1e-9).mean()),
    }


def phase_derive(ctx, seed_cid: str, q: float, keep: str) -> None:
    """Derive a smaller SOLID design from an evaluated one by deleting whole blocks
    (``keep`` = 'front' keeps blocks with centre x below the solid median x, 'rear'
    the opposite, 'lower'/'upper' likewise in z) and evaluate it at the same q, b:
    a same-penalisation partner for the ranking test with a large force margin."""
    seed = base.FIXTURE / "candidates" / seed_cid
    st = base.load_fixed_grid_density_state(seed / "topology_state.json")
    ctx.b = float(st.state.get("projection", {}).get("b", 0.0))
    rho = np.asarray(st.arrays["rho"], dtype=np.float64)
    beta = physical(ctx, rho, q)[2]
    solid = ctx.to3d(beta) > 0.5
    if keep == "round":  # snap every block to 0/1 by its filtered density: a fully binary block body
        rho_new = np.where(ctx.filter.H(rho) >= 0.5, 1.0, 0.0) * ctx.active
    else:
        axis = {"front": 0, "rear": 0, "lower": 2, "upper": 2}[keep]
        coords = np.nonzero(solid)[axis]
        med = np.median(coords)
        grid = np.indices(ctx.shape)[axis]
        drop = (grid > med) if keep in ("front", "lower") else (grid < med)
        rho3 = ctx.to3d(rho).copy()
        rho3[drop & (ctx.to3d(ctx.active) > 0)] = 0.0
        rho_new = ctx.flat(rho3)
    cid = f"{seed_cid}_keep_{keep}"
    cdir = write(ctx, cid, rho_new, q, parent=seed_cid, iteration=int(st.state["iteration"]) + 1,
                 note=f"derived from {seed_cid}: {'every block snapped to 0/1 by filtered density' if keep == 'round' else f'blocks beyond the solid median removed ({keep} kept)'}")
    ev = base.evaluate(ctx, cdir, q, gradient=True)
    print(cid, "DF", ev["downforce_coefficient"], "drag", ev["drag_coefficient"], "thickness", thickness_metrics(ctx, physical(ctx, rho_new, q)[2]))


# --- phases ----------------------------------------------------------------------------------


def phase_fd(ctx, q: float, b: float = 0.0, eps_list=(3e-3, 1e-2, 3e-2)) -> None:
    ctx.b = b
    rho = ctx.rho0.copy()
    cid = f"fd_base_q{q:g}_b{b:g}"
    cdir = write(ctx, cid, rho, q, parent=None, iteration=0, note="FD baseline (filtered)")
    ev = base.evaluate(ctx, cdir, q, gradient=True)
    assert ev["downforce_adjoint_converged"]
    g_beta = base.load_gradient(cdir)
    _, g_rho = chain_gradient(ctx, rho, q, g_beta)
    S = ctx.rho0 > 0  # perturb only cells at 0.5: no clipping for eps <= 0.03
    rng = np.random.default_rng(1)
    dirs = {
        "gradient": np.where(S, g_rho, 0.0),
        "smooth_random": np.where(S, ctx.filter.H(np.where(S, rng.normal(size=rho.size), 0.0)), 0.0),
    }
    rows = []
    for name, d in dirs.items():
        d = d / np.max(np.abs(d))
        pred = float(np.dot(g_rho, d))
        for eps in eps_list:
            vals = {}
            for sign in (+1, -1):
                c = write(ctx, f"fd_q{q:g}_b{b:g}_{name}_eps{eps:g}_{'p' if sign > 0 else 'm'}", np.clip(rho + sign * eps * d, 0, 1), q,
                          parent=cid, iteration=1, note="FD probe")
                vals[sign] = base.evaluate(ctx, c, q, gradient=False)["downforce_coefficient"]
            fd = (vals[1] - vals[-1]) / (2 * eps)
            rows.append({"direction": name, "eps": eps, "fd": fd, "predicted": pred, "ratio": fd / pred})
            print(rows[-1], flush=True)
    (base.OUT / f"fd_check_q{q:g}_b{b:g}.json").write_text(json.dumps({
        "status": base.STATUS, "q": q, "b": b, "filter": ctx.filter.meta, "baseline": base._forces(ev),
        "adjoint_iterations": ev["iterations"], "chain": "g_rho = H.T (h_b'(H rho) f'(h_b(H rho)) g_beta); predicted = <g_rho, d>",
        "rows": rows}, indent=2))


def phase_optimize(ctx, q_schedule, steps_per_q, v_final, move_limit=0.1, move_floor=0.01, zero_floor=1e-3,
                   resume_from: str | None = None, b_schedule=None) -> None:
    b_schedule = b_schedule or [0.0] * len(q_schedule)
    rho = ctx.rho0.copy()
    if isinstance(ctx.filter, BlockFilter):
        rho = ctx.filter.H(rho)  # start block-uniform so every cell of a block moves together (same budget)
    v0 = float(rho[ctx.active].mean())
    history, parent, it, n_acc, tag = [], None, 0, 0, ""
    if resume_from:  # continue a lineage (same fixture / filter); its evaluation and gradient already exist
        seed = base.FIXTURE / "candidates" / resume_from
        st = base.load_fixed_grid_density_state(seed / "topology_state.json")
        rho = np.asarray(st.arrays["rho"], dtype=np.float64)
        parent, it, n_acc = resume_from, int(st.state["iteration"]) + 1, 6
        history = json.loads((base.OUT / f"optimize_history{ctx.name_tag}.json").read_text())["history"]
        tag = f"_r{it}"
    for q, b, n_steps in zip(q_schedule, b_schedule, steps_per_q):
        ctx.b = b
        seed_ev = json.loads((base.FIXTURE / "candidates" / parent / "evaluation.json").read_text()) if resume_from and parent == resume_from else None
        seed_state = json.loads((base.FIXTURE / "candidates" / parent / "topology_state.json").read_text()) if seed_ev else None
        if seed_ev is not None and seed_ev["q"] == q and seed_state.get("projection", {}).get("b", 0.0) == b and (base.FIXTURE / "candidates" / parent / "gradient").exists():
            cid, cdir, ev = parent, base.FIXTURE / "candidates" / parent, seed_ev
        else:
            cid = f"opt_q{q:g}_b{b:g}_baseline{tag}{ctx.name_tag}"
            cdir = write(ctx, cid, rho, q, parent=parent, iteration=it, note="continuation baseline")
            ev = base.evaluate(ctx, cdir, q, gradient=True)
            parent, it = cid, it + 1
            history.append({"q": q, "b": b, "kind": "baseline", "candidate": cid, **base._forces(ev), "adjoint_iterations": ev["iterations"]})
        if not ev["downforce_adjoint_converged"]:
            raise SystemExit(f"{cid}: downforce adjoint did not converge")
        J, g_beta = -ev["downforce_coefficient"], base.load_gradient(cdir)
        ml = move_limit
        for step in range(n_steps):
            rho_tilde, g_rho = chain_gradient(ctx, rho, q, g_beta)
            for attempt in range(3):
                v_target = v0 + (v_final - v0) * min(1.0, (n_acc + 1) / 6)
                cand = np.clip(oc_step_ineq(g_rho, rho, ctx.active, ml, v_target, zero_floor=zero_floor), 0, 1)
                if float(np.max(np.abs((cand - rho)[ctx.active]))) < 1e-6:
                    print(f"q={q:g} step {step}: no-op candidate, lineage plateaued", flush=True)
                    break
                pred_dJ = -float(np.dot(g_rho[ctx.active], (cand - rho)[ctx.active]))
                cid = f"opt_q{q:g}_b{b:g}_step{step}_try{attempt}{tag}{ctx.name_tag}"
                cdir = write(ctx, cid, cand, q, parent=parent, iteration=it, note="OC candidate (filtered, projected, inequality volume)")
                ev = base.evaluate(ctx, cdir, q, gradient=True)
                ok = ev["primal_converged"] and ev["downforce_adjoint_converged"] and ev["downforce_coefficient"] is not None
                dJ = (-ev["downforce_coefficient"] - J) if ok else None
                beta = physical(ctx, cand, q)[2]
                row = {"q": q, "b": b, "kind": "step", "candidate": cid, "move_limit": ml, "v_target": v_target, "predicted_dJ": pred_dJ,
                       "actual_dJ": dJ, **base._forces(ev), "adjoint_iterations": ev["iterations"], "accepted": bool(ok and dJ <= 1e-9),
                       "design_rho": base.discreteness(cand, ctx.active), "physical_beta": base.discreteness(beta, ctx.active),
                       "thickness": thickness_metrics(ctx, beta)}
                history.append(row)
                print(json.dumps({k: row[k] for k in ("candidate", "predicted_dJ", "actual_dJ", "accepted", "downforce_coefficient")}),
                      "thick p10x2=%.2f thin=%.2f" % (row["thickness"].get("estimated_min_slab_thickness_cells", 0), row["thickness"].get("thin_fraction_within_1cell_of_surface", 1)), flush=True)
                (base.OUT / f"optimize_history{ctx.name_tag}.json").write_text(json.dumps({"status": base.STATUS, "filter": ctx.filter.meta, "history": history}, indent=2))
                if row["accepted"]:
                    rho, J, g_beta = cand, -ev["downforce_coefficient"], base.load_gradient(cdir)
                    parent, it, n_acc = cid, it + 1, n_acc + 1
                    break
                ml = max(ml / 2, move_floor)
    (base.OUT / f"final_candidate{ctx.name_tag}.txt").write_text(parent or "")
    print("final candidate:", parent)


# --- Stage V mesh-only geometry sweep ------------------------------------------------------------


def _patch_area(case_dir: Path, patch: str) -> float:
    pm = case_dir / "constant" / "polyMesh"
    btxt = (pm / "boundary").read_text()
    m = re.search(rf"{patch}\s*\{{[^}}]*?nFaces\s+(\d+);\s*startFace\s+(\d+);", btxt, re.S)
    n, start = int(m.group(1)), int(m.group(2))
    ptxt = (pm / "points").read_text()
    pts = np.array(re.findall(r"\(([-\d.eE+]+) ([-\d.eE+]+) ([-\d.eE+]+)\)", ptxt.split("(", 1)[1]), dtype=float)
    ftxt = (pm / "faces").read_text()
    body = ftxt.split("\n(\n", 1)[1]
    faces = re.findall(r"(\d+)\(([^)]*)\)", body)
    area = 0.0
    for k in range(start, start + n):
        idx = np.array(faces[k][1].split(), dtype=int)
        p = pts[idx]
        for i in range(1, len(idx) - 1):
            area += 0.5 * np.linalg.norm(np.cross(p[i] - p[0], p[i + 1] - p[0]))
    return float(area)


def mesh_sweep(stl: Path, out_dir: Path, tag: str) -> dict:
    """Mesh one STL at V0/V1/V2 (mesh only), run checkMesh's hard gate, and measure
    the meshed body's wetted area (design_candidate patch) and volume (box - fluid)."""
    spec = load_problem_spec(SV_SPEC)
    levels = {}
    for name, vox in STAGE_V_LEVELS.items():
        case_dir = out_dir / tag / name
        if not (case_dir / "log.checkMesh").exists():
            cfg = problem_spec_to_project_config(spec, candidate_stl=stl, voxel_size_m=vox)
            generate_openfoam_case(cfg, build_fields(cfg), case_dir)
            (case_dir / "Allrun").write_text(MESH_ONLY_ALLRUN)
            run_openfoam_case(case_dir, backend="docker", dry_run=False, timeout_seconds=3600)
        log = (case_dir / "log.checkMesh").read_text(errors="replace")
        cm = evaluate_check_mesh(log)
        meta = json.loads((case_dir / "case_metadata.json").read_text())
        lo, hi = np.array(meta["grid"]["bounds"])
        box = float(np.prod(hi - lo))
        total = float(re.search(r"Total volume = ([-+]?[0-9]*\.?[0-9]+(?:[eE][-+]?[0-9]+)?)", log).group(1))
        levels[name] = {"cells": cm.get("total_cells"), "check_mesh_qualified": cm.get("qualified"), "failed_checks": cm.get("failed_check_lines"),
                        "body_volume_m3": box - total, "wetted_area_m2": _patch_area(case_dir, "design_candidate")}
        print(tag, name, levels[name], flush=True)
    def drift(key):
        v = np.array([levels[n][key] for n in STAGE_V_LEVELS])
        return float((v.max() - v.min()) / v.mean())
    return {"levels": levels, "wetted_area_drift": drift("wetted_area_m2"), "volume_drift": drift("body_volume_m3"),
            "check_mesh_all_pass": all(levels[n]["check_mesh_qualified"] for n in STAGE_V_LEVELS)}


def phase_geom(ctx, cids: list[str]) -> None:
    base.phase_export(ctx, cids)
    out = {}
    for cid in cids:
        edir = base.OUT / "export" / cid
        man = json.loads((edir / "candidate_manifest.json").read_text())
        st = base.load_fixed_grid_density_state(base.FIXTURE / "candidates" / cid / "topology_state.json")
        beta = np.asarray(st.arrays["rho_projected"], dtype=np.float64)
        man["thickness_metrics"] = thickness_metrics(ctx, beta)
        man["filter"] = ctx.filter.meta
        sq = man["iso_surface_metrics"].get("handoff_surface_quality") or {}
        row = {"downforce": man["stage_t_predicted_forces"]["downforce_coefficient"], "thickness": man["thickness_metrics"],
               "surface_quality": {"faces_removed_by_cleaning": sq.get("faces_removed_by_cleaning"),
                                   "aspect_gt_100_after": (sq.get("after_cleaning") or {}).get("count_aspect_ratio_above_100"),
                                   "max_aspect_after": (sq.get("after_cleaning") or {}).get("max_aspect_ratio")},
               "stage_t_solid_volume_m3": float((beta > 0.5).sum() * ctx.cell_volume)}
        if (edir / "iso_surface.stl").exists():
            row["mesh_sweep"] = mesh_sweep(edir / "iso_surface.stl", base.OUT / "stage_v_mesh", cid)
        else:
            row["mesh_sweep"] = {"error": man["stage_s_handoff"].get("error")}
        man["geometry_sweep"] = row
        (edir / "candidate_manifest.json").write_text(json.dumps(man, indent=2))
        out[cid] = row
    (base.OUT / "geometry_sweep.json").write_text(json.dumps({"status": base.STATUS, "minimum_solid_width_m": ctx.width_m, "rows": out}, indent=2))


SOLVE_ONLY_ALLRUN = """#!/usr/bin/env bash
set -euo pipefail
simpleFoam | tee log.simpleFoam
python3 postprocess_forces.py || python postprocess_forces.py || true
"""


def phase_stagev(ctx, cids: list[str]) -> None:
    """Solve the already-meshed V0/V1/V2 cases (qualified Stage V gates via
    cfd.qualify_stage_v_case) and report successive-difference ratios
    |V2-V1| / |V1-V0| for Cd and downforce: ~1 means the force is not converging."""
    from cfd_sdf.cfd import qualify_stage_v_case, write_stage_v_qualification
    out = {}
    for cid in cids:
        rows = {}
        for name in STAGE_V_LEVELS:
            case_dir = base.OUT / "stage_v_mesh" / cid / name
            if not (case_dir / "log.simpleFoam").exists():
                (case_dir / "Allrun").write_text(SOLVE_ONLY_ALLRUN)
                run_openfoam_case(case_dir, backend="docker", dry_run=False, timeout_seconds=7200)
            write_stage_v_qualification(case_dir)  # persists checkMesh/residual/force evidence in the case
            qual = qualify_stage_v_case(case_dir)
            resp = qual.force_stationarity.get("responses", {})
            rows[name] = {"qualified": qual.qualified, "reasons": qual.reasons, "iterations": qual.solver.get("iteration_count"),
                          "Cd": (resp.get("Cd") or {}).get("mean"), "downforce": (resp.get("downforce") or {}).get("mean")}
            print(cid, name, rows[name], flush=True)
        def sdr(key):
            v = [rows[n][key] for n in STAGE_V_LEVELS]
            if any(x is None for x in v):
                return None
            d01, d12 = abs(v[1] - v[0]), abs(v[2] - v[1])
            return {"V0": v[0], "V1": v[1], "V2": v[2], "abs_change_V0_V1": d01, "abs_change_V1_V2": d12,
                    "successive_difference_ratio": (d12 / d01) if d01 > 1e-12 else None}
        out[cid] = {"levels": rows, "Cd": sdr("Cd"), "downforce": sdr("downforce")}
        man_path = base.OUT / "export" / cid / "candidate_manifest.json"
        if man_path.exists():
            man = json.loads(man_path.read_text())
            man["stage_v_forces"] = out[cid]
            man_path.write_text(json.dumps(man, indent=2))
    path = base.OUT / "stage_v_forces.json"
    prev = json.loads(path.read_text())["rows"] if path.exists() else {}
    prev.update(out)
    path.write_text(json.dumps({"status": base.STATUS, "minimum_solid_width_m": ctx.width_m, "rows": prev}, indent=2))


def plan_stagev_level(cid: str, level: str, voxel: float) -> dict:
    """Resolve one single-level Stage V job without creating or running anything."""
    stl = base.OUT / "export" / cid / "iso_surface.stl"
    case_dir = base.OUT / "stage_v_mesh" / cid / level
    return {"stl": stl, "stl_exists": stl.exists(), "case_dir": case_dir, "level": level,
            "voxel_size_m": voxel, "done": (case_dir / "stage_v_qualification.json").exists()}


def _write_stagev_level_preflight(case_dir: Path, cid: str, level: str, voxel: float,
                                  check_mesh: dict, solver_log_preexisting: bool,
                                  profile_id: str, solver_launch_attempted: bool = False) -> Path:
    """Deterministic preflight artifact written BEFORE any simpleFoam launch, so a later reader
    can tell from the directory alone whether the mesh gate passed, whether a solver log already
    existed, and whether this invocation was allowed to launch the solver."""
    doc = {"schema_version": 1, "candidate": cid, "level": level, "voxel_size_m": voxel,
           "qualification_profile_id": profile_id,
           "check_mesh": {k: check_mesh[k] for k in ("status", "qualified", "reasons", "total_cells",
                                                     "failed_check_lines", "concave_cell_fraction")},
           "solver_qualified_to_start": check_mesh["qualified"],
           "solver_log_preexisting": solver_log_preexisting,
           "solver_launch_attempted_by_this_invocation": solver_launch_attempted}
    path = case_dir / "stage_v_level_preflight.json"
    path.write_text(json.dumps(doc, indent=2, sort_keys=True), encoding="utf-8")
    return path


def phase_stagev_level(ctx, cid: str, level: str, voxel: float) -> None:
    """Prepare/run/qualify ONE Stage V level (e.g. V3 at voxel_size_m=0.0125) for one
    exported candidate without looping over or touching the other levels. A level whose
    stage_v_qualification.json already exists is reported, never overwritten. The mesh is
    gated by evaluate_check_mesh (STAGE_V_QUALIFICATION_PROFILE_V1) BEFORE simpleFoam: a
    failing mesh terminates nonzero and never launches or relaunches the solver."""
    from cfd_sdf.cfd import STAGE_V_QUALIFICATION_PROFILE_V1, qualify_stage_v_case, write_stage_v_qualification
    plan = plan_stagev_level(cid, level, voxel)
    if not plan["stl_exists"]:
        raise SystemExit(f"stagev_level: missing exported STL: {plan['stl']}")
    case_dir = plan["case_dir"]
    if not plan["done"]:
        if not (case_dir / "log.checkMesh").exists():
            spec = load_problem_spec(SV_SPEC)
            cfg = problem_spec_to_project_config(spec, candidate_stl=plan["stl"], voxel_size_m=voxel)
            generate_openfoam_case(cfg, build_fields(cfg), case_dir)
            (case_dir / "Allrun").write_text(MESH_ONLY_ALLRUN)
            run_openfoam_case(case_dir, backend="docker", dry_run=False, timeout_seconds=3600)
        if not (case_dir / "log.checkMesh").exists():
            missing_log = {"status": "fail", "qualified": False,
                           "reasons": ["log_checkMesh_missing"], "total_cells": None,
                           "failed_check_lines": [], "concave_cell_fraction": None}
            _write_stagev_level_preflight(case_dir, cid, level, voxel, missing_log,
                                          (case_dir / "log.simpleFoam").exists(),
                                          str(STAGE_V_QUALIFICATION_PROFILE_V1["profile_id"]))
            raise SystemExit(f"stagev_level: mesh execution produced no log.checkMesh for {cid}/{level}")
        # Fail-closed mesh gate: reuse log.checkMesh when present, judge it against the
        # pre-registered profile, and never let simpleFoam see a failing mesh.
        check_mesh = evaluate_check_mesh((case_dir / "log.checkMesh").read_text(errors="ignore"),
                                         STAGE_V_QUALIFICATION_PROFILE_V1)
        solver_log_preexisting = (case_dir / "log.simpleFoam").exists()
        _write_stagev_level_preflight(case_dir, cid, level, voxel, check_mesh,
                                      solver_log_preexisting, str(STAGE_V_QUALIFICATION_PROFILE_V1["profile_id"]))
        if not check_mesh["qualified"]:
            raise SystemExit(f"stagev_level: checkMesh gate failed for {cid}/{level}; solver launch blocked: "
                             f"{check_mesh['reasons']}")
        if not solver_log_preexisting:
            (case_dir / "Allrun").write_text(SOLVE_ONLY_ALLRUN)
            _write_stagev_level_preflight(case_dir, cid, level, voxel, check_mesh, False,
                                          str(STAGE_V_QUALIFICATION_PROFILE_V1["profile_id"]),
                                          solver_launch_attempted=True)
            run_openfoam_case(case_dir, backend="docker", dry_run=False, timeout_seconds=7200)
        write_stage_v_qualification(case_dir)
    qual = qualify_stage_v_case(case_dir)
    print(json.dumps({"candidate": cid, "level": plan["level"], "voxel_size_m": plan["voxel_size_m"],
                      "case_dir": str(case_dir), "qualified": qual.qualified, "reasons": qual.reasons,
                      "iterations": qual.solver.get("iteration_count"),
                      "check_mesh_total_cells": qual.check_mesh.get("total_cells")}), flush=True)
    if not qual.qualified:
        raise SystemExit(f"stagev_level: qualification failed for {cid}/{level}: {qual.reasons}")


def phase_control() -> None:
    """Eight-cell (0.4 m) cube at the plate's location through the same mesh sweep."""
    out = SWEEP_ROOT / "control_cube"
    out.mkdir(parents=True, exist_ok=True)
    cube = trimesh.creation.box(extents=[0.4, 0.4, 0.4])
    cube.apply_translation([0.35, 0.0, 0.0])
    cube.export(out / "cube.stl")
    res = mesh_sweep(out / "cube.stl", out, "cube")
    res["stl_volume_m3"] = float(cube.volume)
    res["stl_area_m2"] = float(cube.area)
    (out / "geometry_sweep.json").write_text(json.dumps(res, indent=2))
    print(json.dumps({k: res[k] for k in ("wetted_area_drift", "volume_drift", "check_mesh_all_pass")}))


def selftest() -> None:
    ctx = setup(0.2)  # builds the wmin_0.2 fixture; R = 2 cells
    F = ctx.filter
    rng = np.random.default_rng(0)
    x, y = rng.normal(size=ctx.rho0.size), rng.normal(size=ctx.rho0.size)
    lhs, rhs = float(np.dot(F.H(x), y)), float(np.dot(x, F.HT(y)))
    assert abs(lhs - rhs) < 1e-9 * max(abs(lhs), 1.0), (lhs, rhs)
    ones = ctx.active.astype(float)
    assert np.allclose(F.H(ones)[ctx.active], 1.0)  # normalisation: constants preserved on active cells
    if isinstance(F, ConeFilter):
        assert not np.allclose(F.H(x)[ctx.active], F.HT(x)[ctx.active])  # cone H is not symmetric near the boundary
    delta = np.zeros_like(x); delta[np.flatnonzero(ctx.active)[5000]] = 1.0
    assert int((F.H(delta) > 0).sum()) > 1 and int((F.H(delta) > 0).sum()) <= (2 * int(np.ceil(F.radius_cells)) + 1) ** 3
    # chain rule on a synthetic linear objective J = <c, f(H rho)>: dJ/drho = H.T (f' c)
    q, c = 30.0, rng.normal(size=x.size)
    rho = np.clip(rng.uniform(0.2, 0.8, size=x.size) * ctx.active, 0, 1)
    d = rng.normal(size=x.size) * ctx.active
    ctx.b = 8.0
    J = lambda r: float(np.dot(c, physical(ctx, r, q)[2]))  # noqa: E731
    h = 1e-6
    fd = (J(rho + h * d) - J(rho - h * d)) / (2 * h)
    _, g = chain_gradient(ctx, rho, q, c)
    assert abs(fd - np.dot(g, d)) < 1e-6 * abs(fd), (fd, np.dot(g, d))
    Bf = BlockFilter(ctx, 0.2)
    assert np.allclose(np.dot(Bf.H(x), y), np.dot(x, Bf.HT(y))) and np.allclose(Bf.H(Bf.H(x)), Bf.H(x))  # symmetric projection
    assert np.allclose(Bf.H(ones)[ctx.active], 1.0) and Bf.block.tolist() == [5, 4, 4], Bf.block
    print("block filter ok", Bf.meta["block_cells"], Bf.nblocks.tolist())
    # single-level Stage V planning: level selection + voxel passthrough + done guard key
    p = plan_stagev_level("cid_x", "V3", 0.0125)
    assert p["case_dir"] == base.OUT / "stage_v_mesh" / "cid_x" / "V3" and p["voxel_size_m"] == 0.0125
    assert not p["done"] and p["stl"] == base.OUT / "export" / "cid_x" / "iso_surface.stl"
    # preflight artifact: deterministic JSON, blocked mesh records solver_qualified_to_start=false
    with tempfile.TemporaryDirectory() as td:
        pf = _write_stagev_level_preflight(Path(td), "cid_x", "V3", 0.0125,
                                           {"status": "fail", "qualified": False, "reasons": ["x"], "total_cells": 10,
                                            "failed_check_lines": ["y"], "concave_cell_fraction": 0.5},
                                           solver_log_preexisting=False, profile_id="stage_v_v1")
        doc = json.loads(pf.read_text())
    assert doc["candidate"] == "cid_x" and doc["level"] == "V3" and doc["voxel_size_m"] == 0.0125
    assert doc["check_mesh"]["qualified"] is False and doc["solver_qualified_to_start"] is False
    assert doc["solver_log_preexisting"] is False
    assert doc["solver_launch_attempted_by_this_invocation"] is False
    print("selftest ok: adjoint identity", lhs, rhs, "| radius cells", F.radius_cells, "| spec sha", ctx.state0.state["problem_spec_sha256"][:12],
          "| min width declared", ctx.spec.topology_policy.minimum_solid_width_m)


if __name__ == "__main__":
    import os
    KIND = os.environ.get("FILTER_KIND", "cone")  # cone (linear hat) or block (super-cell)
    _setup = setup
    setup = lambda w, eta=0.5: _setup(w, eta, KIND)  # noqa: E731
    phase = sys.argv[1]
    if phase == "selftest":
        selftest()
    elif phase == "fd":  # fd <w_min> <q> [b]
        phase_fd(setup(float(sys.argv[2])), float(sys.argv[3]), float(sys.argv[4]) if len(sys.argv) > 4 else 0.0)
    elif phase == "optimize":  # optimize <w_min> <q csv> <steps csv> <v_final> [move_limit] [resume_from|-] [b csv] [eta]
        phase_optimize(setup(float(sys.argv[2]), float(sys.argv[9]) if len(sys.argv) > 9 else 0.5), [float(x) for x in sys.argv[3].split(",")],
                       [int(x) for x in sys.argv[4].split(",")], float(sys.argv[5]),
                       move_limit=float(sys.argv[6]) if len(sys.argv) > 6 else 0.1,
                       resume_from=(sys.argv[7] if len(sys.argv) > 7 and sys.argv[7] != "-" else None),
                       b_schedule=[float(x) for x in sys.argv[8].split(",")] if len(sys.argv) > 8 else None)
    elif phase == "geom":  # geom <w_min> <cids csv> [eta]
        phase_geom(setup(float(sys.argv[2]), float(sys.argv[4]) if len(sys.argv) > 4 else 0.5), sys.argv[3].split(","))
    elif phase == "stagev":  # stagev <w_min> <cids csv> [eta] (after geom)
        phase_stagev(setup(float(sys.argv[2]), float(sys.argv[4]) if len(sys.argv) > 4 else 0.5), sys.argv[3].split(","))
    elif phase == "stagev_level":  # stagev_level <w_min> <cid> <level> <voxel> [eta] — one level only
        phase_stagev_level(setup(float(sys.argv[2]), float(sys.argv[6]) if len(sys.argv) > 6 else 0.5),
                           sys.argv[3], sys.argv[4], float(sys.argv[5]))
    elif phase == "derive":  # derive <w_min> <seed_cid> <q> <front|rear|lower|upper> [eta]
        phase_derive(setup(float(sys.argv[2]), float(sys.argv[6]) if len(sys.argv) > 6 else 0.5), sys.argv[3], float(sys.argv[4]), sys.argv[5])
    elif phase == "control":
        phase_control()
    elif phase == "export":  # export <w_min> <cids csv>
        phase_geom(setup(float(sys.argv[2])), sys.argv[3].split(","))
    else:
        raise SystemExit(__doc__)
