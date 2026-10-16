#!/usr/bin/env python3
"""T2-0a (#57, EXPLORATORY_COMMITTED): deterministic gmsh -> OpenFOAM v2512 case generator, 2D Tyrrell 026 wing in ground effect.

Geometry: Tyrrell026S (Genua 2009 Table 1) with ground at y = 0 (moving belt, U = U_inf), chord 0.2234 m, ride height h = distance from the
lowest point of the suction surface to the ground, domain 2c upstream / 5c downstream / 6.8c above the ground (slip top). The mesh is
2D (gmsh, quad boundary layers on airfoil and ground, fan at the sharp TE) extruded to one cell; patches: inlet outlet top ground airfoil front back.
Determinism: every dictionary and the manifest inputs are bit-reproducible; the gmsh mesh is NOT (gmsh 4.15.2's boundary-layer path
changes the triangle core by a few cells between runs, cause not isolated), so each run's mesh.msh and its SHA-256 are the artifact.
Generation only: nothing here is validated against OpenFOAM (see docs/evidence/t20a_exploratory_2026_10_16/README.md).
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
SIZE_FAR, GROW, PT_SPACING = 0.05, 0.25, 1e-3  # far-field size [m], size growth per distance, spline control-point spacing [m]
MODELS = {  # wall: wf = wall functions (y+ 30-40 mesh), wr = wall resolved (y+ <= 1 mesh)
    "sa-wf": dict(foam="SpalartAllmaras", wall="wf", iters=5000, relax=0.9),
    "sst-wf": dict(foam="kOmegaSST", wall="wf", iters=5000, relax=0.9),
    "sst-lm": dict(foam="kOmegaSSTLM", wall="wr", iters=10000, relax=0.7),
}
MESHES = {  # ds: surface spacing [m], y1: first layer [m], g: layer growth. Genua 2009 Tables 2-3 (Coa30, Med30, Fine30, Fine05) + a coarse wall-resolved smoke mesh
    "coa30": dict(wall="wf", ds=8e-3, y1=0.6e-3, g=1.2),
    "med30": dict(wall="wf", ds=4e-3, y1=0.6e-3, g=1.2),
    "fine30": dict(wall="wf", ds=2e-3, y1=0.6e-3, g=1.2),
    "wrc": dict(wall="wr", ds=8e-3, y1=0.01e-3, g=1.3),
    "wr2": dict(wall="wr", ds=2e-3, y1=0.01e-3, g=1.12),
}


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


def layers(ds: float, y1: float, g: float, gap: float):
    """Layer count: last layer ~ sqrt(3)/4 ds (Genua eq. 3, equal-area hand-over to the triangles), capped so each wall's stack stays <= 0.4 gap."""
    n_spec = math.ceil(math.log(math.sqrt(3) / 4 * ds / y1) / math.log(g)) + 1
    total = lambda n: y1 * (g ** n - 1) / (g - 1)
    n = n_spec
    while n > 3 and total(n) > 0.4 * gap:
        n -= 1
    return n_spec, n, total(n)


def _polygon_overlap_count(xy, conn, x0, y_lo, y_hi):
    """Number of 2D cells that the vertical segment {x0} x (y_lo, y_hi) passes through with positive length (cells tile, so this is the cell count along it)."""
    count = 0
    for cell in conn:
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
    """Write out_msh (gmsh 2.2 ascii, extruded one cell, physical groups = OpenFOAM patch names) and return the mesh statistics."""
    import gmsh
    Q, i_low, i_le = airfoil_points(h_over_c, delta_alpha_deg)
    h, x_low = Q[i_low, 1], Q[i_low, 0]
    ds, y1, g = mesh["ds"], mesh["y1"], mesh["g"]
    n_spec, n_lay, bl = layers(ds, y1, g, h)
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
        c = [geo.addPoint(xl, 0, 0), geo.addPoint(xr, 0, 0), geo.addPoint(xr, top, 0), geo.addPoint(xl, top, 0)]
        ground, outlet, tp, inlet = (geo.addLine(c[i], c[(i + 1) % 4]) for i in range(4))
        wake = geo.addLine(pt[0], geo.addPoint(xr, Q[0, 1], 0))   # free curve: only the wake size field reads it
        surf = geo.addPlaneSurface([geo.addCurveLoop([ground, outlet, tp, inlet]), geo.addCurveLoop([s1, s2, s3])])
        ext = geo.extrude([(2, surf)], 0, 0, Z, [1], [], True)
        geo.synchronize()
        bl_f = F.add("BoundaryLayer")
        F.setNumbers(bl_f, "CurvesList", [s1, s2, s3, ground])
        for k, v in {"Size": y1, "Ratio": g, "NbLayers": n_lay, "Thickness": bl, "Quads": 1}.items():
            F.setNumber(bl_f, k, v)
        F.setNumbers(bl_f, "FanPointsList", [pt[0]])
        F.setNumbers(bl_f, "FanPointsSizesList", [8])
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
        for k, v in {"InField": dist([ground], 400), "SizeMin": ds, "SizeMax": SIZE_FAR, "DistMin": 1.5 * bl, "DistMax": 1.5 * bl + (SIZE_FAR - ds) / GROW}.items():
            F.setNumber(gt, k, v)
        fields = [expr(f"{ds}+{GROW}*F{dist([s1, s2, s3], 200)}"), expr(f"{ds}+0.2*F{dist([wake], 100)}"), gt,
                  ball(Q[i_le], 0.012, ds / 3), ball(Q[0], 0.008, ds / 2), expr(str(SIZE_FAR))]
        mn = F.add("Min")
        F.setNumbers(mn, "FieldsList", fields)
        F.setAsBackgroundMesh(mn)
        m.mesh.generate(2)
        stats = _stats(m, surf, [s1, s2, s3], ground, i_low, h, x_low)
        m.mesh.generate(3)
        # lateral faces: ext = [top, volume, lateral(boundary curve k)...]; boundary order is the plane surface's curve order
        base = [cv for _, cv in m.getBoundary([(2, surf)], combined=False, oriented=False)]
        lat = dict(zip(base, (t for _, t in ext[2:])))
        for cv, t in lat.items():
            assert cv in [b for _, b in m.getBoundary([(2, t)], combined=False, oriented=False)], "lateral face / base curve mismatch"
        groups = {"inlet": [lat[inlet]], "outlet": [lat[outlet]], "top": [lat[tp]], "ground": [lat[ground]],
                  "airfoil": [lat[s1], lat[s2], lat[s3]], "front": [surf], "back": [ext[0][1]]}
        _write_msh(m, out_msh, groups, ext[1][1])
        stats["cells_3d"] = int(sum(len(t) for t in m.mesh.getElements(3)[1]))
    finally:
        gmsh.finalize()
    stats.update(ride_height_m=float(h), x_lowest_m=float(x_low), n_layers_spec=n_spec, n_layers=n_lay, bl_thickness_m=bl)
    return stats


def _write_msh(m, path: Path, groups: dict, volume: int):
    """Canonical gmsh-2.2 ascii: nodes sorted by coordinates, elements by node set (equal gmsh output gives equal bytes; gmsh itself varies run to run)."""
    nt, nc, _ = m.mesh.getNodes()
    nc = nc.reshape(-1, 3)
    order = np.lexsort((nc[:, 2], nc[:, 1], nc[:, 0]))
    new_id = {int(nt[i]): r + 1 for r, i in enumerate(order)}
    elems = []  # (physical tag, gmsh type, node ids)
    for ptag, (name, tags) in enumerate(groups.items(), 1):
        rows = []
        for t in tags:
            for et, nodes in zip(*[m.mesh.getElements(2, t)[i] for i in (0, 2)]):
                k = m.mesh.getElementProperties(int(et))[3]
                rows += [(int(et), [new_id[int(n)] for n in r]) for r in np.array(nodes).reshape(-1, k)]
        elems += [(ptag, et, ids) for et, ids in sorted(rows, key=lambda r: (r[0], sorted(r[1])))]
    vol = []
    for et, nodes in zip(*[m.mesh.getElements(3, volume)[i] for i in (0, 2)]):
        k = m.mesh.getElementProperties(int(et))[3]
        vol += [(int(et), [new_id[int(n)] for n in r]) for r in np.array(nodes).reshape(-1, k)]
    elems += [(10, et, ids) for et, ids in sorted(vol, key=lambda r: (r[0], sorted(r[1])))]
    out = ["$MeshFormat", "2.2 0 8", "$EndMeshFormat", "$PhysicalNames", str(len(groups) + 1)]
    out += [f'2 {i} "{n}"' for i, n in enumerate(groups, 1)] + ['3 10 "fluid"', "$EndPhysicalNames", "$Nodes", str(len(order))]
    out += [f"{r + 1} {float(nc[i, 0])!r} {float(nc[i, 1])!r} {float(nc[i, 2])!r}" for r, i in enumerate(order)] + ["$EndNodes", "$Elements", str(len(elems))]
    out += [f"{n} {et} 2 {ptag} {ptag} {' '.join(map(str, ids))}" for n, (ptag, et, ids) in enumerate(elems, 1)] + ["$EndElements", ""]
    Path(path).write_text("\n".join(out))


def _stats(m, surf, airfoil, ground, i_low, h, x_low) -> dict:
    nt, nc, _ = m.mesh.getNodes()
    nc = nc.reshape(-1, 3)[:, :2]
    row = {int(t): i for i, t in enumerate(nt)}
    cells = {}
    for et, k in ((2, 3), (3, 4)):
        nodes = m.mesh.getElementsByType(et, surf)[1]
        cells[et] = np.array([row[int(i)] for i in nodes]).reshape(-1, k) if len(nodes) else np.zeros((0, k), int)
    quads, tris = cells[3], cells[2]

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

    fa, fg = first_layer(airfoil), first_layer([ground])
    af_nodes = np.unique(np.concatenate([m.mesh.getNodes(1, cv, True)[0] for cv in airfoil]))
    af_y = nc[[row[int(i)] for i in af_nodes]][:, 1]
    all_cells = [*tris, *quads]
    return {
        "cells_2d": int(len(tris) + len(quads)), "tri_cells": int(len(tris)), "quad_cells": int(len(quads)),
        "first_cell_airfoil_m": {"median": float(np.median(fa)), "p05": float(np.percentile(fa, 5)), "p95": float(np.percentile(fa, 95))},
        "first_cell_ground_m": {"median": float(np.median(fg)), "p05": float(np.percentile(fg, 5)), "p95": float(np.percentile(fg, 95))},
        "airfoil_nodes": int(len(af_nodes)), "airfoil_node_min_y_m": float(af_y.min()),
        "gap_cells_at_lowest_point": _polygon_overlap_count(nc, all_cells, x_low, 0.0, h),
    }


def write_case(out: Path, h_over_c: float, model: str, mesh_name: str, delta_alpha_deg: float = 0.0, iters: int | None = None) -> dict:
    mdl, msh = MODELS[model], MESHES[mesh_name]
    if mdl["wall"] != msh["wall"]:
        raise ValueError(f"model {model} needs a {mdl['wall']} mesh, {mesh_name} is {msh['wall']}")
    out.mkdir(parents=True, exist_ok=True)
    stats = build_mesh(h_over_c, msh, out / "mesh.msh", delta_alpha_deg)
    p = dict(u=U_INF, nu=NU, chord=CHORD, z=Z, iters=iters or mdl["iters"])
    files = {f"0/{k}": v for k, v in t20_foam.fields(mdl, U_INF, NU, TU, L_INT).items()}
    files |= t20_foam.system_and_constant(mdl, msh, p)
    for rel, text in files.items():
        (out / rel).parent.mkdir(parents=True, exist_ok=True)
        (out / rel).write_text(text)
    manifest = {
        "h_over_c": h_over_c, "h_m": stats["ride_height_m"], "model": model, "foam_model": mdl["foam"], "mesh": mesh_name, "mesh_spec": msh,
        "delta_alpha_deg": delta_alpha_deg, "alpha_listing_deg": ALPHA_LISTING_DEG, "iterations": p["iters"],
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
