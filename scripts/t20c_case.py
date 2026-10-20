#!/usr/bin/env python3
"""T2-0c (#57, registration docs/t20c_registration_2026_10_20.md): the xfine30 mesh level and the fixed-topology morph.

Remeshed cases go through the pinned T2-0a generator (scripts/t20_case.py, unchanged; this module only adds xfine30 to its MESHES). A morphed case copies a
baseline case and rewrites only the x, y of the nodes of its mesh.msh (node numbering, elements and physical groups untouched): p' = p + w(p) D(p), with D the
generator's own incidence transformation or a camber-type shape mode (registration section 4) and w a blend that is 1 on the airfoil layer stack and 0 on the
ground block and the outer boundaries. Asserted per morph (a failure exits non-zero = GENERATOR_FAILED): no 2D cell changes the sign of its area, the
fixed nodes are unmoved, the morphed contour equals the generator's target contour (incidence).
"""
from __future__ import annotations

import argparse
import json
import math
import shutil
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import t20_case as C  # noqa: E402

# Genua's family continued: ds halves, y1 fixed. The equal-area last layer (0.433 ds = 0.43 mm) is below y1; last = 0.65 gives two layers (1.32 mm) at every
# height (fine30's own four-layer stack fails the quality proxy at the LE): registration section 3
XFINE30 = dict(wall="wf", ds=1e-3, y1=0.6e-3, g=1.2, te=2, fan=4, last=0.65)   # added to t20_case.MESHES only during remesh_case (no import side effect)
MESHES = {**C.MESHES, "xfine30": XFINE30}
MODES = ("incidence", "camber", "flap", "heave")
SHAPES = ("camber", "flap", "heave")
FLAP_XI = 0.7
CONTOUR_TOL_M = 1e-9


def rotation(deg: float) -> np.ndarray:
    """The generator's rotation (row vectors: p @ R), counter-clockwise about the origin, LE toward the ground = +."""
    a = math.radians(deg)
    return np.array([[math.cos(a), math.sin(a)], [-math.sin(a), math.cos(a)]])


def shape_d(p: np.ndarray, mode: str, a_m: float, Q0: np.ndarray, i_le: int) -> np.ndarray:
    """Camber-type displacement D_s(p) [m] in the chord frame of the baseline contour (registration section 4); thickness unchanged."""
    le, te = Q0[i_le], Q0[0]
    L = float(np.hypot(*(te - le)))
    c_hat = (te - le) / L
    n_hat = np.array([-c_hat[1], c_hat[0]])          # away from the ground
    xi = (p - le) @ c_hat / L
    if mode == "camber":
        f = np.where((xi >= 0) & (xi <= 1), -4 * xi * (1 - xi), 0.0)
    elif mode == "flap":
        f = np.where(xi > 1, 1.0, np.where(xi >= FLAP_XI, ((xi - FLAP_XI) / (1 - FLAP_XI)) ** 2, 0.0))
    else:
        raise ValueError(mode)
    return a_m * f[:, None] * n_hat


def shape_contour(Q0: np.ndarray, i_le: int, h_over_c: float, mode: str, amp: float):
    """camber/flap: (D, s, moved contour) with h re-imposed at the lowest suction-surface point of the moved contour (D includes the shift s)."""
    a_m = amp * 1e-3
    moved = Q0 + shape_d(Q0, mode, a_m, Q0, i_le)
    s = float(h_over_c * C.CHORD - moved[:i_le + 1, 1].min())
    moved[:, 1] += s
    return (lambda p: shape_d(p, mode, a_m, Q0, i_le) + np.array([0.0, s])), s, moved


def displacement(h_over_c: float, mode: str, amp: float, base_da: float = 0.0):
    """(D, Q0, i_le, diagnostics) for a base generated at incidence base_da. incidence: amp = target incidence [deg]; camber/flap/heave: amp [mm] on a 0-deg base.
    D maps base positions to displacements [m]; the moved base contour is the generator's target contour."""
    Q0, _, i_le = C.airfoil_points(h_over_c, base_da)
    if mode == "incidence":
        Q1, i_low1, _ = C.airfoil_points(h_over_c, amp)
        RmI, t = rotation(amp - base_da) - np.eye(2), Q1[0] - Q0[0]
        D = lambda p: (p - Q0[0]) @ RmI + t           # = T1 + (p - T0) R - p, exactly zero for amp = base_da
        diag = {"contour_err_m": float(np.abs(Q0 + D(Q0) - Q1).max()), "x_lowest_m": float(Q1[i_low1, 0])}
    elif base_da != 0:
        raise ValueError("shape modes need a 0-deg base")
    elif mode == "heave":                              # ride height h + amp: a rigid translation away from the ground
        D = lambda p: np.broadcast_to(np.array([0.0, amp * 1e-3]), p.shape)
        diag = {"h_shift_m": amp * 1e-3, "x_lowest_m": float(Q0[int(np.argmin(Q0[:i_le + 1, 1])), 0])}
    elif mode in ("camber", "flap"):
        D, s, moved = shape_contour(Q0, i_le, h_over_c, mode, amp)
        diag = {"h_shift_m": s, "x_lowest_m": float(moved[int(np.argmin(moved[:i_le + 1, 1])), 0])}
    else:
        raise ValueError(f"mode must be one of {MODES}")
    diag["te_displacement_m"] = D(Q0[:1])[0].tolist()
    return D, Q0, i_le, diag


def _seg_dist(p, a, b):
    """Distance from points p to the polyline segments a->b (chunked)."""
    out = np.empty(len(p))
    ab = b - a
    L2 = (ab ** 2).sum(1)
    for k in range(0, len(p), 2000):
        q = p[k:k + 2000, None, :] - a[None]
        t = np.clip((q * ab[None]).sum(2) / L2[None], 0, 1)
        out[k:k + 2000] = np.hypot(*(q - t[..., None] * ab[None]).transpose(2, 0, 1)).min(1)
    return out


def blend(xy: np.ndarray, Q0: np.ndarray, b: float, kind: str = "smoothstep") -> np.ndarray:
    """w = 1 on the airfoil layer stack (distance <= b), 0 on the ground block (y <= b) and on the outer boundaries; in between smoothstep in phi (registered)
    or linear 1 - phi (the blend-sensitivity label)."""
    xl, xr, top = -C.UP * C.CHORD, C.DOWN * C.CHORD, C.TOP * C.CHORD
    r = np.maximum(_seg_dist(xy, Q0[:-1], Q0[1:]) - b, 0)
    df = np.maximum(np.minimum.reduce([xy[:, 1] - b, xy[:, 0] - xl, xr - xy[:, 0], top - xy[:, 1]]), 0)
    phi = r / np.maximum(r + df, 1e-300)
    w = 1 - phi * phi * (3 - 2 * phi) if kind == "smoothstep" else 1 - phi
    w[xy[:, 1] <= b] = 0.0
    return w


def _groups(lines: list[str]) -> dict[str, list[list[int]]]:
    """{physical name: [0-based node ids of each element]} of a t20_case mesh.msh."""
    names = {int(l.split()[1]): l.split('"')[1] for l in lines[lines.index("$PhysicalNames") + 2:lines.index("$EndPhysicalNames")]}
    j = lines.index("$Elements")
    out = {n: [] for n in names.values()}
    for l in lines[j + 2:j + 2 + int(lines[j + 1])]:
        r = l.split()
        out[names[int(r[3])]].append([int(n) - 1 for n in r[5:]])
    return out


def _areas(cells: list[list[int]], xy: np.ndarray) -> np.ndarray:
    return np.array([0.5 * float(np.sum(p[:, 0] * np.roll(p[:, 1], -1) - np.roll(p[:, 0], -1) * p[:, 1])) for p in (xy[c] for c in cells)])


def morph_msh(base_msh: Path, out_msh: Path, D, Q0: np.ndarray, b: float, kind: str = "smoothstep") -> dict:
    """Write out_msh = base_msh with moved x, y (same lines otherwise; node ids are 1..N in order, as t20_case._write_msh writes them)."""
    lines = Path(base_msh).read_text().split("\n")
    i = lines.index("$Nodes") + 2
    n = int(lines[i - 1])
    rows = [l.split() for l in lines[i:i + n]]
    assert [int(r[0]) for r in rows] == list(range(1, n + 1)), "node ids are not 1..N in order"
    xy = np.array([r[1:3] for r in rows], float)
    w = blend(xy, Q0, b, kind)
    new = xy + w[:, None] * D(xy)
    for k, (r, (x, y)) in enumerate(zip(rows, new)):
        lines[i + k] = f"{r[0]} {float(x)!r} {float(y)!r} {r[3]}"
    g = _groups(lines)
    a0, a1 = _areas(g["front"], xy), _areas(g["front"], new)
    ids = lambda *names: sorted({n for name in names for c in g[name] for n in c})
    fixed = sorted(set(ids("ground", "inlet", "outlet", "top")) | set(np.flatnonzero(xy[:, 1] <= b).tolist()))
    foil = ids("airfoil")
    out = {"inverted_cells": int((np.sign(a0) != np.sign(a1)).sum()), "area_ratio_min": float((a1 / a0).min()), "area_ratio_max": float((a1 / a0).max()),
           "fixed_nodes": len(fixed), "fixed_nodes_moved": int((new[fixed] != xy[fixed]).any(1).sum()),
           "airfoil_nodes": len(foil), "airfoil_min_weight": float(w[foil].min()), "max_node_displacement_m": float(np.hypot(*(new - xy).T).max())}
    Path(out_msh).write_text("\n".join(lines))
    return out


def morph_case(base: Path, out: Path, mode: str, amp: float, kind: str = "smoothstep") -> dict:
    """Copy the base case (dictionaries with the generator's uniform initial fields, manifest) to `out` with a morphed mesh.msh; returns the manifest.
    Raises on a failed assertion. The base is an unmorphed generator case (any incidence for the incidence mode, 0 deg for the shape modes)."""
    bman = json.loads((base / "case_manifest.json").read_text())
    if "morph" in bman or "shape" in bman:
        raise ValueError("the base must be an unmorphed generator case")
    h = bman["h_over_c"]
    D, Q0, i_le, diag = displacement(h, mode, amp, bman["delta_alpha_deg"])
    out.mkdir(parents=True)
    for d in ("0", "system", "constant"):
        shutil.copytree(base / d, out / d, ignore=shutil.ignore_patterns("polyMesh"))
    m = morph_msh(base / "mesh.msh", out / "mesh.msh", D, Q0, bman["mesh_stats"]["bl_thickness_m"], kind)
    q = C.mesh_quality(out / "mesh.msh")
    man = {**bman, "delta_alpha_deg": amp if mode == "incidence" else 0.0,
           "h_m": bman["h_m"] + (amp * 1e-3 if mode == "heave" else 0.0),
           "morph": {"mode": mode, "amp": amp, "amp_unit": "deg" if mode == "incidence" else "mm", "base_mesh_msh_sha256": bman["mesh_msh_sha256"],
                     "base_delta_alpha_deg": bman["delta_alpha_deg"], "blend": kind,
                     **diag, **m, "module_sha256": C.sha256(Path(__file__))},
           "mesh_msh_sha256": C.sha256(out / "mesh.msh"), "mesh_quality_failures": C.quality_failures(q)}
    man["mesh_stats"] = {**bman["mesh_stats"], "quality": q, "x_lowest_m": diag["x_lowest_m"]}
    (out / "case_manifest.json").write_text(json.dumps(man, indent=1, sort_keys=True) + "\n")
    bad = [k for k, ok in (("inverted_cells", m["inverted_cells"] == 0), ("fixed_nodes_moved", m["fixed_nodes_moved"] == 0),
                           ("airfoil_min_weight", m["airfoil_min_weight"] >= 1 - 1e-9), ("contour_err_m", diag.get("contour_err_m", 0.0) <= CONTOUR_TOL_M)) if not ok]
    if bad:
        raise RuntimeError(f"morph assertion failed: {bad} ({m}, {diag})")
    return man


def remesh_case(out: Path, h_over_c: float, mesh: str, delta_alpha_deg: float = 0.0, iters: int | None = None, shape: str | None = None, shape_amp: float = 0.0) -> dict:
    """A case meshed by the pinned generator: the T2-0b geometry, or (shape) the camber/flap contour of section 4 (the generator reads it through
    t20_case.airfoil_points, patched for this call only) or heave (ride height h + amp)."""
    orig, orig_meshes = C.airfoil_points, C.MESHES
    C.MESHES = MESHES
    if shape in ("camber", "flap"):
        def shaped(h, da=0.0):
            assert da == 0, "shape modes are meshed at 0 deg"
            Q0, _, i_le = orig(h, 0.0)
            moved = shape_contour(Q0, i_le, h, shape, shape_amp)[2]
            return moved, int(np.argmin(moved[:i_le + 1, 1])), i_le
        C.airfoil_points = shaped
    elif shape not in (None, "heave"):
        raise ValueError(f"shape must be one of {SHAPES}")
    try:
        h_eff = h_over_c + (shape_amp * 1e-3 / C.CHORD if shape == "heave" else 0.0)
        man = C.write_case(out, h_eff, "sa-wf", mesh, delta_alpha_deg, iters)
    finally:
        C.airfoil_points, C.MESHES = orig, orig_meshes
    man["generator_sha256"]["t20c_case.py"] = C.sha256(Path(__file__))
    if shape:
        man["shape"] = {"mode": shape, "amp": shape_amp, "amp_unit": "mm", "h_over_c_nominal": h_over_c}
    (out / "case_manifest.json").write_text(json.dumps(man, indent=1, sort_keys=True) + "\n")
    return man


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--h-over-c", type=float, help="remeshed case (t20_case.write_case)")
    ap.add_argument("--mesh", choices=sorted(MESHES))
    ap.add_argument("--delta-alpha-deg", type=float, default=0.0)
    ap.add_argument("--iters", type=int)
    ap.add_argument("--base", type=Path, help="morphed case: the baseline case directory")
    ap.add_argument("--mode", choices=MODES)
    ap.add_argument("--amp", type=float, help="morph: target incidence [deg] (incidence) or amplitude [mm] (camber, flap, heave)")
    ap.add_argument("--blend", choices=("smoothstep", "linear"), default="smoothstep", help="morph: registered smoothstep; linear for the blend-sensitivity label")
    ap.add_argument("--shape", choices=SHAPES, help="remeshed shape case")
    ap.add_argument("--shape-amp", type=float, default=0.0, help="mm")
    a = ap.parse_args(argv)
    if a.base:
        man = morph_case(a.base, a.out, a.mode, a.amp, a.blend)
        print(f"{a.out}: morph {a.mode} {a.amp:+g} of {a.base.name}: {json.dumps(man['morph'])}")
    else:
        man = remesh_case(a.out, a.h_over_c, a.mesh, a.delta_alpha_deg, a.iters, a.shape, a.shape_amp)
        print(f"{a.out}: {a.mesh} cells={man['mesh_stats']['cells_3d']} layers={man['mesh_stats']['n_layers']}")


if __name__ == "__main__":
    main()
