#!/usr/bin/env python3
"""T2-0a (#57, EXPLORATORY_COMMITTED): deterministic gmsh -> OpenFOAM v2512 case generator, 2D Tyrrell 026 wing in ground effect.

Geometry: Tyrrell026S (Genua 2009 Table 1) with ground at y = 0 (moving belt, U = U_inf), chord 0.2234 m, ride height h = distance from the
lowest point of the suction surface to the ground, domain 2c upstream / 5c downstream / 6.8c above the ground (slip top). The mesh is
2D (gmsh: gmsh quad boundary layer on the airfoil with a fan at the sharp TE, an explicit structured quad block on the ground, triangle core) extruded to one cell; patches: inlet outlet top ground airfoil front back.
Determinism: every dictionary and the manifest inputs are bit-reproducible; the gmsh mesh is NOT (gmsh 4.15.2's boundary-layer path
changes the triangle core by a few cells between runs, cause not isolated), so each run's mesh.msh and its SHA-256 are the artifact.
Generation only: mesh_quality() is a local proxy of checkMesh (definitions checked against the Kaggle attempt-2 logs), not OpenFOAM; see docs/evidence/t20a_exploratory_2026_10_16/README.md.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import sys
from pathlib import Path

os.environ.setdefault("OMP_NUM_THREADS", "1")  # fewer run-to-run differences from gmsh's boundary-layer mesher; must be set before gmsh loads. It does NOT make the mesh bit-reproducible
import numpy as np
from scipy.interpolate import CubicSpline

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import t20_foam  # noqa: E402

COORDS = ROOT / "data/t20/tyrrell026s_genua2009.dat"
CHORD, U_INF, RE_C = 0.2234, 30.0, 4.6e5
NU = U_INF * CHORD / RE_C                      # 1.457e-5 m2/s
TU, L_INT = 0.003, 0.01                        # Genua 2009: Tu 0.3 %, integral length scale 1 cm
Z = 0.002                                      # extrusion thickness [m]; Aref = chord * Z
UP, DOWN, TOP = 2.0, 5.0, 6.8                  # domain in chords
ALPHA_LISTING_DEG = 3.6                        # incidence of the Tyrrell026 listing; the table is used as given (LE toward ground = positive)
END_AR, END_R = 20, 1.15                       # inlet/outlet end columns of the ground layer block: width END_AR first-layer heights, growing by END_R per cell to ds
TE_GROW = 0.2                                  # surface spacing grows away from the sharp TE by this much per unit length (starting at mesh["te"] first-layer heights, <= ds/2)
SIZE_FAR, GROW, PT_SPACING = 0.05, 0.25, 1e-3  # far-field size [m], size growth per distance, spline control-point spacing [m]
MODELS = {  # wall: wf = wall functions (y+ 30-40 mesh), wr = wall resolved (y+ <= 1 mesh)
    "sa-wf": dict(foam="SpalartAllmaras", wall="wf", iters=5000, relax=0.9),
    "sst-wf": dict(foam="kOmegaSST", wall="wf", iters=5000, relax=0.9),
    "sst-lm": dict(foam="kOmegaSSTLM", wall="wr", iters=10000, relax=0.7, sst_iters=2000),   # two stages in one case: sst_iters of kOmegaSST, then kOmegaSSTLM (t20_foam.LM_RELAX)
}
MESHES = {  # ds: surface spacing [m], y1: first layer [m], g: layer growth. Genua 2009 Tables 2-3 (Coa30, Med30, Fine30) + two own wall-resolved meshes.
    # checkMesh's cell-determinant check flags an interior quad above aspect ratio ~89 and a wall cell above ~141 (see mesh_quality), so a wall-resolved
    # mesh needs ds <= ~60-80 y1: wrc 1.2 mm / 20 um (y+ ~ 2, smoke only), wr2 0.6 mm / 10 um (y+ <= 1.2); te/fan = sharp-TE surface spacing [first-layer heights] and fan element count, tuned by sweep;
    # last = last layer / ds (0.3 for wall-resolved): the sharp-TE fan's best face weight is ~1/(1 + sqrt(1.5 R/y1)) for stack thickness R, so R/y1 must stay <= ~90 to clear checkMesh's 0.05. The wall-function meshes sit at aspect ratio <= 13.
    "coa30": dict(wall="wf", ds=8e-3, y1=0.6e-3, g=1.2, te=2, fan=4),
    "med30": dict(wall="wf", ds=4e-3, y1=0.6e-3, g=1.2, te=2, fan=4),
    "fine30": dict(wall="wf", ds=2e-3, y1=0.6e-3, g=1.2, te=2, fan=4),
    "wrc": dict(wall="wr", ds=1.2e-3, y1=0.02e-3, g=1.25, last=0.3, te=4, fan=4),
    "wr2": dict(wall="wr", ds=0.6e-3, y1=0.01e-3, g=1.25, last=0.3, te=4, fan=4),
}
# local proxy limits (mesh_quality, OpenFOAM v2512 definitions reproduced against the Kaggle attempt-2 checkMesh logs); limits are tighter than checkMesh's
LIMITS = dict(nonorth_max=70.0, skew_max=3.0, skew_boundary_max=3.0, weight_min=0.06, vol_ratio_min=0.02, det_min=1.2e-3, min_sicn=0.1)


def sha256(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def airfoil_points(h_over_c: float, delta_alpha_deg: float = 0.0):
    """Dense closed contour TE -> suction -> LE -> pressure -> TE [m], ground at y = 0, lowest suction point exactly at y = h.
    Returns (Q, i_low, i_le); Q[0] == Q[-1] is the TE. delta_alpha rotates counter-clockwise about the LE (LE toward the ground = +)."""
    rows = np.loadtxt(COORDS)
    suc, prs = rows[:, 0:2], rows[:, 2:4]
    P = np.vstack([suc[::-1], prs[1:]]) * CHORD
    a = math.radians(delta_alpha_deg)
    P = P @ np.array([[math.cos(a), math.sin(a)], [-math.sin(a), math.cos(a)]])
    t = np.r_[0, np.cumsum(np.hypot(*np.diff(P, axis=0).T))]
    t_le = t[len(suc) - 1]
    tt = np.unique(np.r_[np.linspace(0, t[-1], int(t[-1] / PT_SPACING) + 1), t_le])
    Q = CubicSpline(t, P, bc_type="natural")(tt)
    i_le = int(np.argmin(np.abs(tt - t_le)))
    i_low = int(np.argmin(Q[:i_le + 1, 1]))          # suction side only (TE -> LE)
    Q[:, 1] += h_over_c * CHORD - Q[i_low, 1]
    Q[-1] = Q[0]
    return Q, i_low, i_le


def layers(ds: float, y1: float, g: float, gap: float, last: float = math.sqrt(3) / 4):
    """Layer count: last layer ~ `last` * ds (default sqrt(3)/4: Genua eq. 3, equal-area hand-over to the triangles), capped so each wall's stack stays <= 0.4 gap."""
    n_spec = math.ceil(math.log(last * ds / y1) / math.log(g)) + 1
    total = lambda n: y1 * (g ** n - 1) / (g - 1)
    n = n_spec
    while n > 3 and total(n) > 0.4 * gap:
        n -= 1
    return n_spec, n, total(n)


def _polygon_overlap_count(xy, conn, x0, y_lo, y_hi):
    """Number of 2D cells that the vertical segment {x0} x (y_lo, y_hi) passes through with positive length (cells tile, so this is the cell count along it)."""
    count = 0
    for cell in (c for c in conn if xy[c, 0].min() <= x0 <= xy[c, 0].max()):
        p = xy[cell]
        ys = []
        for a, b in zip(p, np.roll(p, -1, axis=0)):
            if (a[0] - x0) * (b[0] - x0) < 0 or (a[0] == x0) != (b[0] == x0):
                s = (x0 - a[0]) / (b[0] - a[0]) if b[0] != a[0] else 0.0
                ys.append(a[1] + s * (b[1] - a[1]))
        if len(ys) >= 2 and min(max(ys), y_hi) - max(min(ys), y_lo) > 1e-12:
            count += 1
    return count


def build_mesh(h_over_c: float, mesh: dict, out_msh: Path, delta_alpha_deg: float = 0.0, verbose: bool = False) -> dict:
    """Write out_msh (gmsh 2.2 ascii, extruded one cell, physical groups = OpenFOAM patch names) and return the mesh statistics.
    The ground boundary layer is an explicit structured block (transfinite, quads, exact first layer/growth, ends on the vertical inlet/outlet edges): gmsh's
    boundary-layer field left sliver triangles and 90-degree non-orthogonal faces where a wall layer ends on the inlet/outlet. The airfoil layer is gmsh's."""
    import gmsh
    Q, i_low, i_le = airfoil_points(h_over_c, delta_alpha_deg)
    h, x_low = Q[i_low, 1], Q[i_low, 0]
    ds, y1, g = mesh["ds"], mesh["y1"], mesh["g"]
    n_spec, n_lay, bl = layers(ds, y1, g, h, mesh.get("last", math.sqrt(3) / 4))
    s_te = min(ds / 2, mesh["te"] * y1)   # along-wall spacing at the sharp TE: the fan cells there are ~y1 wide, a wider neighbour gives tiny volume ratios / face weights
    gmsh.initialize()
    gmsh.option.setNumber("General.Verbosity", 5 if verbose else 0)
    try:
        m, geo, F = gmsh.model, gmsh.model.geo, gmsh.model.mesh.field
        m.add("t20")
        for k, v in {"General.NumThreads": 1, "Mesh.MeshSizeFromPoints": 0, "Mesh.MeshSizeFromCurvature": 0, "Mesh.MeshSizeExtendFromBoundary": 0,
                     "Mesh.Algorithm": 6}.items():
            gmsh.option.setNumber(k, v)
        pt = [geo.addPoint(x, y, 0) for x, y in Q[:-1]]
        pt.append(pt[0])
        s1, s2, s3 = (geo.addSpline(pt[a:b + 1]) for a, b in ((0, i_low), (i_low, i_le), (i_le, len(pt) - 1)))
        xl, xr, top = -UP * CHORD, DOWN * CHORD, TOP * CHORD
        c0, c1, g1, g0, t1, t0 = (geo.addPoint(x, y, 0) for x, y in ((xl, 0), (xr, 0), (xr, bl), (xl, bl), (xr, top), (xl, top)))
        # ground block bottom/top are split into [graded end piece | uniform ds | graded end piece]: a wall cell that has its short side on the inlet/outlet
        # (boundary faces do not count in checkMesh's cell determinant) fails above an aspect ratio of ~35, so the end columns are ~END_AR y1 wide
        d0 = min(ds, END_AR * y1)
        n_end = math.ceil(math.log(ds / d0) / math.log(END_R)) + 1 if d0 < ds else 0
        le = d0 * (END_R ** n_end - 1) / (END_R - 1) if n_end else 0.0
        xs = [xl, xl + le, xr - le, xr] if n_end else [xl, xr]
        bot = [geo.addPoint(x, 0, 0) for x in xs[1:-1]]
        tops = [geo.addPoint(x, bl, 0) for x in xs[1:-1]]
        pb, pt_ = [c0, *bot, c1], [g0, *tops, g1]
        ground_c = [geo.addLine(a, b) for a, b in zip(pb[:-1], pb[1:])]
        gtop_c = [geo.addLine(a, b) for a, b in zip(pt_[:-1], pt_[1:])]
        vr, vl = geo.addLine(c1, g1), geo.addLine(c0, g0)
        outlet, tp, inlet = geo.addLine(g1, t1), geo.addLine(t1, t0), geo.addLine(t0, g0)
        wake = geo.addLine(pt[0], geo.addPoint(xr, Q[0, 1], 0))   # free curve: only the wake size field reads it
        blk = geo.addPlaneSurface([geo.addCurveLoop([*ground_c, vr, *(-c for c in gtop_c[::-1]), -vl])])
        surf = geo.addPlaneSurface([geo.addCurveLoop([*gtop_c, outlet, tp, inlet]), geo.addCurveLoop([s1, s2, s3])])
        counts = [n_end, round((xs[-2] - xs[1]) / ds), n_end] if n_end else [round((xr - xl) / ds)]
        for cs in (ground_c, gtop_c):
            for k, (cv, n) in enumerate(zip(cs, counts)):
                if n_end and k != 1:
                    geo.mesh.setTransfiniteCurve(cv, n + 1, "Progression", END_R if k == 0 else 1 / END_R)
                else:
                    geo.mesh.setTransfiniteCurve(cv, n + 1)
        for cv in (vl, vr):
            geo.mesh.setTransfiniteCurve(cv, n_lay + 1, "Progression", g)   # first element = y1 because bl = y1 (g^n - 1)/(g - 1)
        geo.mesh.setTransfiniteSurface(blk, "Left", [c0, c1, g1, g0])
        geo.mesh.setRecombine(2, blk)
        ext_b = geo.extrude([(2, blk)], 0, 0, Z, [1], [], True)
        ext = geo.extrude([(2, surf)], 0, 0, Z, [1], [], True)
        geo.synchronize()
        bl_f = F.add("BoundaryLayer")
        F.setNumbers(bl_f, "CurvesList", [s1, s2, s3])
        for k, v in {"Size": y1, "Ratio": g, "NbLayers": n_lay, "Thickness": bl, "Quads": 1}.items():
            F.setNumber(bl_f, k, v)
        F.setNumbers(bl_f, "FanPointsList", [pt[0]])
        F.setNumbers(bl_f, "FanPointsSizesList", [mesh["fan"]])
        F.setAsBoundaryLayer(bl_f)

        def dist(curves, n):
            f = F.add("Distance")
            F.setNumbers(f, "CurvesList", curves)
            F.setNumber(f, "Sampling", n)
            return f

        def expr(s):
            f = F.add("MathEval")
            F.setString(f, "F", s)
            return f

        def ball(xy, r, vin):
            f = F.add("Ball")
            for k, v in {"Radius": r, "Thickness": 2.5 * r, "VIn": vin, "VOut": SIZE_FAR, "XCenter": xy[0], "YCenter": xy[1]}.items():
                F.setNumber(f, k, v)
            return f

        gt = F.add("Threshold")
        for k, v in {"InField": dist(gtop_c, 3000), "SizeMin": ds, "SizeMax": SIZE_FAR, "DistMin": 0.5 * bl, "DistMax": 0.5 * bl + (SIZE_FAR - ds) / GROW}.items():
            F.setNumber(gt, k, v)
        corners = [expr(f"{d0:.9f}+{TE_GROW}*Sqrt((x-({cx:.9f}))^2+(y-({bl:.9f}))^2)") for cx in (xl, xr)] if n_end else []
        fields = [*corners, expr(f"{ds}+{GROW}*F{dist([s1, s2, s3], 200)}"), expr(f"{ds}+0.2*F{dist([wake], 100)}"), gt,
                  ball(Q[i_le], 0.012, ds / 3), expr(f"{s_te:.9f}+{TE_GROW}*Sqrt((x-({Q[0, 0]:.9f}))^2+(y-({Q[0, 1]:.9f}))^2)"), expr(str(SIZE_FAR))]
        mn = F.add("Min")
        F.setNumbers(mn, "FieldsList", fields)
        F.setAsBackgroundMesh(mn)
        m.mesh.generate(2)
        stats = _stats(m, [blk, surf], [s1, s2, s3], ground_c, i_low, h, x_low)
        m.mesh.generate(3)
        # lateral faces: ext = [top, volume, lateral(boundary curve k)...]; boundary order is the plane surface's curve order
        lat = {}
        for base, e in ((blk, ext_b), (surf, ext)):
            curves = [cv for _, cv in m.getBoundary([(2, base)], combined=False, oriented=False)]
            for cv, t in zip(curves, (t for _, t in e[2:])):
                assert cv in [b for _, b in m.getBoundary([(2, t)], combined=False, oriented=False)], "lateral face / base curve mismatch"
                lat[cv] = t
        groups = {"inlet": [lat[inlet], lat[vl]], "outlet": [lat[outlet], lat[vr]], "top": [lat[tp]], "ground": [lat[c] for c in ground_c],
                  "airfoil": [lat[s1], lat[s2], lat[s3]], "front": [blk, surf], "back": [ext_b[0][1], ext[0][1]]}
        _write_msh(m, out_msh, groups, [ext_b[1][1], ext[1][1]])
        stats["cells_3d"] = int(sum(len(t) for v in (ext_b[1][1], ext[1][1]) for t in m.mesh.getElements(3, v)[1]))
    finally:
        gmsh.finalize()
    stats.update(ride_height_m=float(h), x_lowest_m=float(x_low), n_layers_spec=n_spec, n_layers=n_lay, bl_thickness_m=bl, quality=mesh_quality(out_msh))
    return stats


def _write_msh(m, path: Path, groups: dict, volumes: list):
    """Canonical gmsh-2.2 ascii: only nodes used by a volume cell (the geometry points and spline control points are not cells' nodes: written as
    nodes they became OpenFOAM's `1024 unused points`), sorted by coordinates, elements sorted by node set (equal gmsh output gives equal bytes; gmsh itself varies)."""
    def read(dim, tag):
        out = []
        for et, nodes in zip(*[m.mesh.getElements(dim, tag)[i] for i in (0, 2)]):
            k = m.mesh.getElementProperties(int(et))[3]
            out += [(int(et), [int(n) for n in r]) for r in np.array(nodes).reshape(-1, k)]
        return out
    vol = [r for v in volumes for r in read(3, v)]
    used = sorted({n for _, ids in vol for n in ids})
    nt, nc, _ = m.mesh.getNodes()
    coord = dict(zip(nt.tolist(), nc.reshape(-1, 3)))
    order = sorted(used, key=lambda n: (coord[n][0], coord[n][1], coord[n][2]))
    new_id = {n: r + 1 for r, n in enumerate(order)}
    elems = []  # (physical tag, gmsh type, node ids)
    for ptag, (name, tags) in enumerate(groups.items(), 1):
        rows = [(et, [new_id[n] for n in ids]) for t in tags for et, ids in read(2, t)]
        elems += [(ptag, et, ids) for et, ids in sorted(rows, key=lambda r: (r[0], sorted(r[1])))]
    rows = [(et, [new_id[n] for n in ids]) for et, ids in vol]
    elems += [(10, et, ids) for et, ids in sorted(rows, key=lambda r: (r[0], sorted(r[1])))]
    out = ["$MeshFormat", "2.2 0 8", "$EndMeshFormat", "$PhysicalNames", str(len(groups) + 1)]
    out += [f'2 {i} "{n}"' for i, n in enumerate(groups, 1)] + ['3 10 "fluid"', "$EndPhysicalNames", "$Nodes", str(len(order))]
    out += [f"{r + 1} {float(coord[n][0])!r} {float(coord[n][1])!r} {float(coord[n][2])!r}" for r, n in enumerate(order)] + ["$EndNodes", "$Elements", str(len(elems))]
    out += [f"{n} {et} 2 {ptag} {ptag} {' '.join(map(str, ids))}" for n, (ptag, et, ids) in enumerate(elems, 1)] + ["$EndElements", ""]
    Path(path).write_text("\n".join(out))


def _stats(m, surfs, airfoil, ground, i_low, h, x_low) -> dict:
    nt, nc, _ = m.mesh.getNodes()
    nc = nc.reshape(-1, 3)[:, :2]
    row = {int(t): i for i, t in enumerate(nt)}
    cells = {2: [], 3: []}
    sicn = {2: [], 3: []}
    for sf in surfs:
        for et, k in ((2, 3), (3, 4)):
            tags, nodes = m.mesh.getElementsByType(et, sf)
            if len(nodes):
                cells[et].append(np.array([row[int(i)] for i in nodes]).reshape(-1, k))
                sicn[et].append(m.mesh.getElementQualities(list(tags), "minSICN"))
    quads, tris = (np.vstack(cells[et]) if cells[et] else np.zeros((0, k), int) for et, k in ((3, 4), (2, 3)))

    def first_layer(curves):
        edge_area = {}
        for q in quads:
            p = nc[q]
            area = 0.5 * abs(np.sum(p[:, 0] * np.roll(p[:, 1], -1) - np.roll(p[:, 0], -1) * p[:, 1]))
            for a, b in zip(q, np.roll(q, -1)):
                edge_area[frozenset((int(a), int(b)))] = area
        hs = []
        for cv in curves:
            ln = m.mesh.getElements(1, cv)[2][0]
            for a, b in ln.reshape(-1, 2):
                ia, ib = row[int(a)], row[int(b)]
                area = edge_area.get(frozenset((ia, ib)))
                if area:
                    hs.append(area / np.hypot(*(nc[ia] - nc[ib])))
        return np.array(hs)

    fa, fg = first_layer(airfoil), first_layer(ground)
    af_nodes = np.unique(np.concatenate([m.mesh.getNodes(1, cv, True)[0] for cv in airfoil]))
    af_y = nc[[row[int(i)] for i in af_nodes]][:, 1]
    all_cells = [*tris, *quads]
    return {
        "cells_2d": int(len(tris) + len(quads)), "tri_cells": int(len(tris)), "quad_cells": int(len(quads)), "gmsh_min_sicn_tri": float(np.concatenate(sicn[2]).min()), "gmsh_min_sicn_quad": float(np.concatenate(sicn[3]).min()),   # quad SICN ~ 1/aspect ratio: informative only
        "first_cell_airfoil_m": {"median": float(np.median(fa)), "p05": float(np.percentile(fa, 5)), "p95": float(np.percentile(fa, 95))},
        "first_cell_ground_m": {"median": float(np.median(fg)), "p05": float(np.percentile(fg, 5)), "p95": float(np.percentile(fg, 95))},
        "airfoil_nodes": int(len(af_nodes)), "airfoil_node_min_y_m": float(af_y.min()),
        "gap_cells_at_lowest_point": _polygon_overlap_count(nc, all_cells, x_low, 0.0, h),
    }


def mesh_quality(msh_path) -> dict:
    """Local proxy of `checkMesh -allGeometry -allTopology` on the written one-cell-thick mesh (the extrusion is orthogonal, so the 2D cells decide).
    Definitions follow OpenFOAM v2512 and were checked against the Kaggle attempt-2 checkMesh logs of the old coa30/wrc meshes: unused points, max
    non-orthogonality (89.938), faces with weight < 0.05 (2/23), volume ratio < 0.01 (33), max aspect ratio (797.857) and the cell determinant (cells
    < 1e-3: 14/2359; minimum 4.744e-06 / 3.813e-08) are reproduced exactly. The determinant is det(sum over INTERNAL faces of (S/avg|S|)(S/avg|S|)^T)/8, so a
    wall cell (3 internal faces) fails above an aspect ratio of ~141, an interior quad above ~353. Skewness: internal exact definition (not verified
    digit for digit); `skew_boundary` follows my recollection of OpenFOAM's wall-normal definition and is UNVERIFIED (the old logs' 29 skew faces were mostly
    the inlet/outlet slivers). gmsh's own minSICN is in the manifest too."""
    lines = Path(msh_path).read_text().split("\n")
    names = {int(l.split()[1]): l.split('"')[1] for l in lines[lines.index("$PhysicalNames") + 2:lines.index("$EndPhysicalNames")]}
    front = next(t for t, n in names.items() if n == "front")
    i = lines.index("$Nodes")
    xy = np.array([l.split()[1:3] for l in lines[i + 2:i + 2 + int(lines[i + 1])]], float)
    j = lines.index("$Elements")
    els = [list(map(int, l.split())) for l in lines[j + 2:j + 2 + int(lines[j + 1])]]
    used = {n for r in els if r[1] in (5, 6) for n in r[5:]}
    cells = [[n - 1 for n in r[5:]] for r in els if r[3] == front]
    ncell = len(cells)
    cid, ea, eb = [], [], []
    for c, ids in enumerate(cells):
        cid += [c] * len(ids)
        ea += ids
        eb += ids[1:] + ids[:1]
    cid, ea, eb = np.array(cid), np.array(ea), np.array(eb)
    p, q = xy[ea], xy[eb]
    cr = p[:, 0] * q[:, 1] - q[:, 0] * p[:, 1]
    area = np.bincount(cid, cr) / 2
    flip = area[cid] < 0                       # make every cell counter-clockwise
    ea[flip], eb[flip] = eb[flip], ea[flip].copy()
    p, q = xy[ea], xy[eb]
    cr = p[:, 0] * q[:, 1] - q[:, 0] * p[:, 1]
    area = np.bincount(cid, cr) / 2
    cen = np.c_[np.bincount(cid, (p[:, 0] + q[:, 0]) * cr), np.bincount(cid, (p[:, 1] + q[:, 1]) * cr)] / (6 * area[:, None])
    e = q - p
    S = np.c_[e[:, 1], -e[:, 0]]               # outward area vector (per unit thickness)
    L = np.hypot(*S.T)
    mid = (p + q) / 2
    key = np.minimum(ea, eb) * len(xy) + np.maximum(ea, eb)
    order = np.argsort(key, kind="stable")
    ks = key[order]
    pair = np.flatnonzero(ks[1:] == ks[:-1])
    assert np.unique(key, return_counts=True)[1].max() <= 2, "a face is shared by more than two cells"
    o, n = order[pair], order[pair + 1]
    swap = cid[o] > cid[n]
    o, n = np.where(swap, n, o), np.where(swap, o, n)     # owner = lower cell index; S[o] points from owner to neighbour
    internal = np.zeros(len(key), bool)
    internal[o] = internal[n] = True
    d = cen[cid[n]] - cen[cid[o]]
    Sd = (S[o] * d).sum(1)
    nonorth = np.degrees(np.arccos(np.clip(Sd / (L[o] * np.hypot(*d.T)), -1, 1)))
    Cf, Co, Cn = mid[o], cen[cid[o]], cen[cid[n]]
    skew = np.hypot(*(Co + ((S[o] * (Cf - Co)).sum(1) / Sd)[:, None] * d - Cf).T) / np.hypot(*d.T)
    wo, wn = abs((S[o] * (Cf - Co)).sum(1)), abs((S[o] * (Cn - Cf)).sum(1))
    weight = np.minimum(wo / (wo + wn), wn / (wo + wn))
    vr = np.minimum(area[cid[o]], area[cid[n]]) / np.maximum(area[cid[o]], area[cid[n]])
    bnd = np.flatnonzero(~internal)
    db = mid[bnd] - cen[cid[bnd]]
    nb = S[bnd] / L[bnd, None]
    dn = (db * nb).sum(1)
    skew_b = np.hypot(*(db - dn[:, None] * nb).T) / (2 * abs(dn))
    nint = np.bincount(cid, internal)
    avg = np.bincount(cid, L * internal) / np.maximum(nint, 1)
    T = [np.bincount(cid, internal * S[:, a] * S[:, b] / avg[cid] ** 2, ncell) for a, b in ((0, 0), (1, 1), (0, 1))]
    det = np.where(nint > 0, (T[0] * T[1] - T[2] ** 2) / 8, 1.0)
    sx, sy = np.bincount(cid, abs(S[:, 0]), ncell), np.bincount(cid, abs(S[:, 1]), ncell)
    ar = np.maximum(sx, sy) / np.minimum(sx, sy)
    return {"unused_nodes": len(xy) - len(used), "cells": ncell, "nonorth_max": float(nonorth.max()), "nonorth_gt70_faces": int((nonorth > 70).sum()),
            "skew_max": float(skew.max()), "skew_gt4_faces": int((skew > 4).sum()), "skew_boundary_max": float(skew_b.max()),
            "weight_min": float(weight.min()), "weight_lt0.05_faces": int((weight < 0.05).sum()), "vol_ratio_min": float(vr.min()), "vol_ratio_lt0.01_faces": int((vr < 0.01).sum()),
            "det_min": float(det.min()), "det_lt1e-3_cells": int((det < 1e-3).sum()), "aspect_ratio_max": float(ar.max()),
            "worst_xy_m": {"nonorth": Cf[nonorth.argmax()].round(6).tolist(), "weight": Cf[weight.argmin()].round(6).tolist(), "vol_ratio": Cf[vr.argmin()].round(6).tolist(),
                           "det": cen[det.argmin()].round(6).tolist(), "aspect_ratio": cen[ar.argmax()].round(6).tolist()}}


def quality_failures(qual: dict, sicn: float | None = None) -> list[str]:
    """Which LIMITS (and the exact checkMesh failures: unused nodes, counts below checkMesh thresholds) the proxy metrics violate; [] = would pass."""
    bad = [k for k in ("unused_nodes", "weight_lt0.05_faces", "vol_ratio_lt0.01_faces", "det_lt1e-3_cells", "skew_gt4_faces") if qual[k]]
    bad += [k for k in ("nonorth_max", "skew_max", "skew_boundary_max") if qual[k] > LIMITS[k]]
    bad += [k for k in ("weight_min", "vol_ratio_min", "det_min") if qual[k] < LIMITS[k]]
    if qual["aspect_ratio_max"] > 1000:
        bad.append("aspect_ratio_max")
    if sicn is not None and sicn < LIMITS["min_sicn"]:
        bad.append("min_sicn")
    return bad


def write_case(out: Path, h_over_c: float, model: str, mesh_name: str, delta_alpha_deg: float = 0.0, iters: int | None = None) -> dict:
    mdl, msh = MODELS[model], MESHES[mesh_name]
    if mdl["wall"] != msh["wall"]:
        raise ValueError(f"model {model} needs a {mdl['wall']} mesh, {mesh_name} is {msh['wall']}")
    out.mkdir(parents=True, exist_ok=True)
    stats = build_mesh(h_over_c, msh, out / "mesh.msh", delta_alpha_deg)
    p = dict(u=U_INF, nu=NU, chord=CHORD, z=Z, iters=iters or mdl["iters"])
    files = {f"0/{k}": v for k, v in t20_foam.fields(mdl, U_INF, NU, TU, L_INT).items()}
    n1 = n2 = None
    if mdl["foam"] == "kOmegaSSTLM":   # stage 1 = kOmegaSST on the same mesh (the 0/ gammaInt, ReThetat are ignored by it), stage 2 files wait in stage2/ for the runner to swap in
        n1 = min(mdl["sst_iters"], p["iters"] // 2)
        n2 = p["iters"] - n1
        files |= t20_foam.system_and_constant({**mdl, "foam": "kOmegaSST"}, msh, {**p, "iters": n1})
        two = t20_foam.system_and_constant({**mdl, "stage2": True}, msh, {**p, "iters": p["iters"], "start": "latestTime"})
        files |= {f"stage2/{k}": v for k, v in two.items() if k.startswith(("system/controlDict", "system/fvSchemes", "system/fvSolution", "constant/momentumTransport", "constant/turbulenceProperties"))}
        files["stage2/system/fvOptions"] = t20_foam.fv_options(2 * U_INF)
    else:
        files |= t20_foam.system_and_constant(mdl, msh, p)
    for rel, text in files.items():
        (out / rel).parent.mkdir(parents=True, exist_ok=True)
        (out / rel).write_text(text)
    manifest = {
        "h_over_c": h_over_c, "h_m": stats["ride_height_m"], "model": model, "foam_model": mdl["foam"], "mesh": mesh_name, "mesh_spec": msh,
        "delta_alpha_deg": delta_alpha_deg, "alpha_listing_deg": ALPHA_LISTING_DEG, "iterations": p["iters"], "iterations_stage1_sst": n1, "iterations_stage2_lm": n2,
        "mesh_quality_failures": quality_failures(stats["quality"], stats["gmsh_min_sicn_tri"]),
        "chord_m": CHORD, "U_inf": U_INF, "Re_c": RE_C, "nu": NU, "Tu": TU, "L_int_m": L_INT, "z_m": Z, "Aref_m2": CHORD * Z,
        "domain_chords": {"up": UP, "down": DOWN, "top": TOP}, "size_far_m": SIZE_FAR, "size_growth": GROW,
        "inlet": {"k": 1.5 * (TU * U_INF) ** 2, "omega": math.sqrt(1.5 * (TU * U_INF) ** 2) / (0.09 ** 0.25 * L_INT), "nuTilda": 5 * NU,
                  "ReThetat": t20_foam.retheta_t(100 * TU), "gammaInt": 1},
        "force_convention": "Cl = downforce coefficient (liftDir -y), Cd drag, per unit span, reference chord and Aref = chord*z",
        "mesh_stats": stats, "gmsh_version": __import__("gmsh").__version__, "python": platform.python_version(),
        "coords_file": str(COORDS.relative_to(ROOT)), "coords_sha256": sha256(COORDS),
        "generator_sha256": {n: sha256(ROOT / "scripts" / n) for n in ("t20_case.py", "t20_foam.py")},
        "mesh_msh_sha256": sha256(out / "mesh.msh"),
    }
    (out / "case_manifest.json").write_text(json.dumps(manifest, indent=1, sort_keys=True) + "\n")
    return manifest


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--h-over-c", type=float, required=True)
    ap.add_argument("--model", choices=sorted(MODELS), required=True)
    ap.add_argument("--mesh", choices=sorted(MESHES), help="default: med30 for wall-function models, wr2 for sst-lm")
    ap.add_argument("--delta-alpha-deg", type=float, default=0.0, help="rotation about the LE relative to the listing (LE toward ground = +)")
    ap.add_argument("--iters", type=int)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args(argv)
    mesh = a.mesh or ("wr2" if MODELS[a.model]["wall"] == "wr" else "med30")
    man = write_case(a.out, a.h_over_c, a.model, mesh, a.delta_alpha_deg, a.iters)
    s = man["mesh_stats"]
    print(f"{a.out}: {mesh} cells={s['cells_3d']} layers={s['n_layers']} gap_cells={s['gap_cells_at_lowest_point']} h={man['h_m']*1e3:.3f} mm")


if __name__ == "__main__":
    main()
