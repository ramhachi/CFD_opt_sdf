#!/usr/bin/env python3
"""WIDTH-RULE (EXPLORATORY_COMMITTED, solver-free, local CPU): why the GEOM-02 `min_feature_width` gate fails on the smooth v18 plate, and
placement-robust candidate rules compared on v18 sub-cell phase sweeps and mode combinations, synthetic shapes of known width and the historical
width failures.  Plan: docs/width_rule_plan_2026_10_20.md (rev. 2).  Imports (never edits) the registered estimator, v18_plate and the MODE-01 builders.

R0  registered: 2*EDT ridge minimum of the 4x-repeated cell occupancy (geometry_gates.min_feature_width_m, solid AABB + 1 cell); fail < 1.5h - h/4,
    unmeasured up to 1.5h + h/4.
R1  SDF ridge: the same ridge rule on -phi (solid) / +phi (void) at the lattice nodes, same thresholds.
R2  phase majority: R0 on the 8 occupancies resampled at cell centre +-h/4 per axis; passes when at least 5 of 8 pass.
R3  opening defect of the trilinear body: B = {trilinear phi < 0} on an h/4 refinement; D = largest distance from B minus its opening by a ball of
    radius 0.75h (strict erosion) to that opening; pass D <= h, unmeasured D <= 1.25h, fail beyond (solid and void).
R4  the same opening defect on the 4x-repeated registered cell occupancy (R0's own representation).
"""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
import sys
from multiprocessing import Pool
from pathlib import Path

import numpy as np
from scipy import ndimage

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]
from cfd_sdf.design.geometry_gates import FEATURE_SUPERSAMPLE, LENGTH_TOLERANCE_M, min_feature_width_m  # noqa: E402
from cfd_sdf.design.volume_semantics import _corner_mean  # noqa: E402  (the registered V_phi cell-centre rule)

OUT = ROOT / "docs/evidence/width_rule_2026_10_20"
V18_PRESCREEN = ROOT / "docs/evidence/mode01_v18_prescreen_2026_10_19/prescreen.json"
MODE01 = ROOT / "docs/evidence/mode01_prescreen_2026_10_16"
H = 0.025
LIMIT_CELLS, GUARD_CELLS = 1.5, 1 / FEATURE_SUPERSAMPLE      # registered 1.5h with the v1 h/4 sampling guard
# opening defect: ball radius = half the registered 1.5h; tau = right-angle 3D vertex r (sqrt3 - 1) = 0.55h + one h/4 voxel diagonal 0.43h, rounded up
OPEN_K, OPEN_RADIUS_CELLS, OPEN_TAU_CELLS, OPEN_PAD = 4, 0.75, 1.0, 3
R2_SHIFTS = list(itertools.product((-0.25, 0.25), repeat=3))
SEED = 20261020
SYN_N, SYN_K, SYN_DRAWS, ASLAB_PHASES = 26, 8, 16, 32
N_COMBOS, N_NOISY = 200, 50
RULES = ("r0", "r1", "r2", "r3", "r4")
ORDER = {"pass": 0, "unmeasured": 1, "fail": 2}


# ---------------------------------------------------------------- rules
def worst(*s: str) -> str:
    return max(s, key=ORDER.get)


def status(w, h, void=False) -> str:
    """Width rules (R0, R1): the registered limit and guard."""
    if w is None:
        return "pass" if void else "unmeasured"  # v2: no void ridge = not applicable; no solid ridge = unmeasured
    lo, hi = (LIMIT_CELLS - GUARD_CELLS) * h, (LIMIT_CELLS + GUARD_CELLS) * h
    return "fail" if w < lo - LENGTH_TOLERANCE_M else ("unmeasured" if w <= hi + LENGTH_TOLERANCE_M else "pass")


def defect_status(d, h, void=False) -> str:
    """Opening-defect rules (R3, R4): pass D <= tau, unmeasured up to tau + h/4, fail beyond; empty solid unmeasured, empty void pass."""
    if d is None:
        return "pass" if void else "unmeasured"
    tau = OPEN_TAU_CELLS * h
    return "pass" if d <= tau + LENGTH_TOLERANCE_M else ("unmeasured" if d <= tau + GUARD_CELLS * h + LENGTH_TOLERANCE_M else "fail")


def box(mask: np.ndarray, pad: int) -> tuple:
    idx = np.argwhere(mask)
    return tuple(slice(max(a - pad, 0), b + pad + 1) for a, b in zip(idx.min(0), idx.max(0)))


def r0(occ: np.ndarray, h: float) -> dict:
    if not occ.any():
        return {"solid": None, "void": None, "status": "unmeasured"}
    crop = occ[box(occ, 1)]  # = geometry_gates_v2._feature_gates
    s, v = min_feature_width_m(crop, h), min_feature_width_m(~crop, h)
    return {"solid": s, "void": v, "status": worst(status(s, h), status(v, h, void=True))}


def r0_location(occ: np.ndarray, h: float, origin) -> np.ndarray:
    """World coordinates of the minimal solid ridge voxels of R0 (the estimator's own steps, repeated only to locate the minimum)."""
    sl, k = box(occ, 1), FEATURE_SUPERSAMPLE
    up = np.pad(occ[sl], 1, mode="edge")
    for ax in range(3):
        up = np.repeat(up, k, axis=ax)
    d = ndimage.distance_transform_edt(up, sampling=h / k)
    ridge = up & (d >= ndimage.maximum_filter(d, size=3) - 1e-12)
    d, ridge = d[k:-k, k:-k, k:-k], ridge[k:-k, k:-k, k:-k]
    vox = np.argwhere(ridge & (d <= d[ridge].min() + 1e-12))
    return np.asarray(origin) + h * (np.array([s.start for s in sl]) + (vox + 0.5) / k)


def _ridge_min(f: np.ndarray, region: np.ndarray):
    inner = np.zeros(f.shape, bool)
    inner[1:-1, 1:-1, 1:-1] = True
    r = region & inner & (f >= ndimage.maximum_filter(f, size=3) - 1e-12)
    return 2.0 * float(f[r].min()) if r.any() else None


def r1(phi: np.ndarray, h: float) -> dict:
    f = phi.astype(np.float64)
    solid = f < 0
    if not solid.any():
        return {"solid": None, "void": None, "status": "unmeasured"}
    sl = box(solid, 1)
    s, v = _ridge_min(-f, solid), _ridge_min(f[sl], ~solid[sl])
    return {"solid": s, "void": v, "status": worst(status(s, h), status(v, h, void=True))}


def r2(phi: np.ndarray, h: float) -> dict:
    f = phi.astype(np.float64)
    centres = np.indices(tuple(n - 1 for n in f.shape), dtype=np.float64) + 0.5  # cell centres in node-index units
    st = [r0(ndimage.map_coordinates(f, centres + np.reshape(s, (3, 1, 1, 1)), order=1, mode="nearest") < 0, h)["status"] for s in R2_SHIFTS]
    n = sum(x == "pass" for x in st)
    return {"phases": st, "n_pass": n, "status": "pass" if n >= 5 else "fail", "worst_of_8": "pass" if n == 8 else "fail", "best_of_8": "pass" if n else "fail"}


def opening_defect(body: np.ndarray, step: float, radius: float):
    """Largest distance from the part of `body` no ball of `radius` inside it reaches, to the union of such balls; inf if none fits, None if empty."""
    if not body.any():
        return None
    eroded = ndimage.distance_transform_edt(body, sampling=step) > radius
    if not eroded.any():
        return math.inf
    opened = ndimage.distance_transform_edt(~eroded, sampling=step) <= radius
    removed = body & ~opened
    return float(ndimage.distance_transform_edt(~opened, sampling=step)[removed].max()) if removed.any() else 0.0


def _defect_rule(body: np.ndarray, h: float) -> dict:
    s, v = (opening_defect(m, h / OPEN_K, OPEN_RADIUS_CELLS * h) for m in (body, ~body))
    return {"solid": s, "void": v, "status": worst(defect_status(s, h), defect_status(v, h, void=True))}


def refine(phi: np.ndarray, k: int) -> np.ndarray:
    """Trilinear phi on the node-aligned k-fold refinement (what the solver's GridSDFBody interpolates)."""
    axes = [np.arange((n - 1) * k + 1) / k for n in phi.shape]
    return ndimage.map_coordinates(phi.astype(np.float64), np.meshgrid(*axes, indexing="ij"), order=1)


def r3(phi: np.ndarray, h: float) -> dict:
    solid = phi < 0
    if not solid.any():
        return {"solid": None, "void": None, "status": "unmeasured"}
    return _defect_rule(refine(phi[box(solid, OPEN_PAD)], OPEN_K) < 0, h)  # the trilinear body lies in cells touching a solid node


def r4(occ: np.ndarray, h: float) -> dict:
    if not occ.any():
        return {"solid": None, "void": None, "status": "unmeasured"}
    up = occ[box(occ, OPEN_PAD)]
    for ax in range(3):
        up = np.repeat(up, FEATURE_SUPERSAMPLE, axis=ax)
    return _defect_rule(up, h)


def measure(phi: np.ndarray, h: float = H, origin=None, frame=None, with_r2=True) -> dict:
    occ = _corner_mean(phi) < 0.0
    out = {"r0": r0(occ, h), "r1": r1(phi, h), "r2": r2(phi, h) if with_r2 else {"status": "not_evaluated"}, "r3": r3(phi, h), "r4": r4(occ, h)}
    if frame is not None and out["r0"]["solid"] is not None and status(out["r0"]["solid"], h) != "pass":
        out["r0_location"] = sorted(set(classify(frame, x) for x in r0_location(occ, h, origin)))
    return out


# ---------------------------------------------------------------- v18 decomposition
def classify(p: dict, x) -> str:
    """Region of a world point in the parent plate frame (u along the chord, + downstream; u < 0 is the leading edge)."""
    u = (x[0] - p["xc"]) * math.cos(p["alpha"]) + (x[2] - p["zc"]) * math.sin(p["alpha"])
    if abs(x[1]) > p["y_tip"] - H:
        return "tip"
    if u < -p["L"] / 2 + H / 2:
        return "leading_edge_round"
    if u > p["L"] / 2 - H / 2:
        return "trailing_edge_round"
    return "face"


def min_thickness_m(p: dict, mode: str, a: float) -> float:
    """Nominal smallest section thickness of the analytic state (the stadium thickness, changed only by thickness-type modes)."""
    if mode == "thick_chord":
        return p["t"] * (1 + a)
    if mode in ("thickness_D0", "offset_s400", "offset_s125", "offset_s050", "corrugation") and (a < 0 or mode == "corrugation"):
        return p["t"] - 2 * abs(a) / 1000
    return p["t"]


def shifted(s, d):
    from cfd_sdf.design.sdf_state import SDFDesignState
    return SDFDesignState.create(phi=s.phi, origin_m=tuple(o + x for o, x in zip(s.origin_m, d)), spacing_m=s.spacing_m, design_mask=s.design_mask,
                                 fixed_solid_mask=s.fixed_solid_mask, forbidden_mask=s.forbidden_mask, root_mask=s.root_mask,
                                 narrow_band_width_m=s.narrow_band_width_m, generation=0, source_sha256=s.source_sha256,
                                 topology_policy_id=s.topology_policy_id, reinitialization_policy_id=s.reinitialization_policy_id)


G: dict = {}


def _init() -> None:
    import mode01_v18_prescreen as P18
    G["v18"] = P18.load_parent()  # checks the genesis record


def basis() -> dict:
    b = json.loads(V18_PRESCREEN.read_text())["basis"]
    return {m: b["per_mode"][m]["a_star"] for m in b["proposed_basis"]}


def v18_phi(mode: str, a: float, phase):
    """phase (fractions of h per axis): the lattice origin shifted by phase*h, i.e. the body at the opposite sub-cell offset.  Phase 0 = gated bytes."""
    import mode01_modes as M
    import mode01_v18_prescreen as P18
    import v18_plate as V
    s, p = G["v18"]
    if not any(phase):
        phi = P18.state_phi(s, p, mode, a)
        return phi, s.origin_m, M.phi_fortran_sha(phi)
    t = shifted(s, [f * s.spacing_m for f in phase])
    t = M.with_phi(t, V.plate_phi(t, p).astype("<f4"))
    return (t.phi if mode == "parent" else V.mode_phi(t, p, mode, a)), t.origin_m, None


def combo_phi(coeffs: dict, noise_seed):
    """parent + sum_m c_m (harness bytes of m at A*_m - parent): the linear phi-space combination a basis optimiser builds (harness state model),
    optionally with U(-h/16, h/16) noise on the active nodes (a non-exact SDF)."""
    import mode01_modes as M
    import mode01_v18_prescreen as P18
    s, p = G["v18"]
    if "delta" not in G:
        G["delta"] = {m: P18.state_phi(s, p, m, a).astype(np.float64) - s.phi.astype(np.float64) for m, a in basis().items()}
    phi = s.phi.astype(np.float64) + sum(c * G["delta"][m] for m, c in coeffs.items())
    if noise_seed is not None:
        phi += np.where(M.active_mask(s), np.random.default_rng([SEED, noise_seed]).uniform(-H / 16, H / 16, phi.shape), 0.0)
    return phi.astype("<f4")


def work(task: tuple) -> dict:
    kind = task[0]
    row = {"task": list(task)}
    try:
        if kind == "v18":
            _, mode, a, phase = task
            phi, origin, sha = v18_phi(mode, a, phase)
            p = G["v18"][1]
            row.update(mode=mode, amplitude=a, phase=list(phase), phi_fortran_sha256=sha, min_thickness_m=min_thickness_m(p, mode, a),
                       **measure(phi, H, origin, p, with_r2=mode == "parent" or not any(phase)))  # R2 (8 x R0): D1 and phase 0 only (compute deviation)
        elif kind == "combo":
            _, i, coeffs, noise = task
            s, p = G["v18"]
            row.update(combo=i, coeffs=dict(coeffs), noisy=noise is not None, **measure(combo_phi(dict(coeffs), noise), H, s.origin_m, p, with_r2=False))
        elif kind == "roundtip":
            import v18_tip_probe as TP
            s, p0 = G["v18"]
            dx, dz, da, dt = task[1]
            p = {**p0, "xc": p0["xc"] + dx, "zc": p0["zc"] + dz, "alpha": p0["alpha"] + math.radians(da), "t": p0["t"] * (1 + dt)}
            row.update(draw=task[2], **measure(np.asarray(TP.round_tip_phi(s, p), "<f4"), H))
        elif kind in ("opt01", "regen6p25"):
            import mode01_modes as M
            import mode01_prescreen as P
            _, mode, a = task
            s = M.load_parent() if kind == "opt01" else P.regen_parent(M.load_parent())
            phi = s.phi.copy() if mode == "parent" else M.mode_phi(s, mode, a)
            row.update(mode=mode, amplitude=a, phi_fortran_sha256=M.phi_fortran_sha(phi), **measure(phi, H))
        elif kind == "reinit04":
            import geom02_canonical as canon
            import reinit04_v17 as R
            from cfd_sdf.design.sdf_state import SDFDesignState
            name, npz, _ = next(x for x in R.STATES if x[0] == task[1])
            st = R.reinitialize_sdf(SDFDesignState.load(canon.INPUTS / f"{npz}.npz"), profile="canonical", fail_closed=False).state
            row.update(state=name, state_sha256=st.state_sha256, **measure(st.phi, H))
        elif kind in ("syn", "aslab"):
            _, name, i = task
            sh = SHAPES[name] if kind == "syn" else ASLABS[name]
            rot, c = draw(np.random.default_rng([SEED, i, zlib(name)])) if kind == "syn" else (np.eye(3), np.array([(SYN_N - 1) / 2] * 2 + [(SYN_N - 1) / 2 + i / ASLAB_PHASES]))
            phi = synthetic_phi(sh["inside"], rot, c)
            row.update(shape=name, draw=i, represented=represented(sh, phi, rot, c), **measure(phi, H))
            if kind == "syn" and sh["cls"] == "thin":
                row["r1_phi_x2"] = r1(2 * phi, H)  # K6: R1 reads phi units; R0, R2-R4 only use the sign of trilinear phi
    except Exception as e:  # noqa: BLE001 - a state that cannot be built or measured is a result and makes the run invalid
        row["error"] = f"{type(e).__name__}: {e}"
    return row


# ---------------------------------------------------------------- synthetic shapes (lengths in cells h; local frame centred at 0)
def zlib(name: str) -> int:
    return int(hashlib.sha256(name.encode()).hexdigest()[:8], 16)


def _slab(w, half=4):
    return lambda x, y, z: (abs(x) <= half) & (abs(y) <= half) & (abs(z) <= w / 2)


def _fin(w, ln):
    c = ln / 2  # cube 6 + plate of length ln along x, total extent centred
    plate = lambda x, y, z: (x > 3 - c) & (x <= 3 + c) & (abs(y) <= 3) & (abs(z) <= w / 2)  # noqa: E731
    return (lambda x, y, z: ((x >= -3 - c) & (x <= 3 - c) & (abs(y) <= 3) & (abs(z) <= 3)) | plate(x, y, z)), plate


def _neck(d, gap):
    e = 2.5 + gap / 2  # ball centres; the neck is `gap` long between the balls
    cyl = lambda x, y, z: (abs(x) <= e) & (y ** 2 + z ** 2 <= d * d / 4)  # noqa: E731
    return (lambda x, y, z: ((x - e) ** 2 + y ** 2 + z ** 2 <= 6.25) | ((x + e) ** 2 + y ** 2 + z ** 2 <= 6.25) | cyl(x, y, z)), \
        (lambda x, y, z: cyl(x, y, z) & (abs(x) < gap / 2))


def _wedge(theta):
    tn = math.tan(math.radians(theta) / 2)
    return lambda x, y, z: (x >= -4) & (x <= 4) & (abs(y) <= 3) & (abs(z) <= np.minimum((4 - x) * tn, 2.5))


def _slot(g):
    slot = lambda x, y, z: (abs(x) < g / 2) & (abs(y) <= 4) & (z > -0.5) & (z <= 3.5)  # noqa: E731  depth 4 from the top, floor 3
    return (lambda x, y, z: (abs(x) <= 4) & (abs(y) <= 4) & (abs(z) <= 3.5) & ~slot(x, y, z)), slot


def _stadium(t):
    half = (12 - t) / 2
    return lambda x, y, z: (abs(y) <= 3) & (np.maximum(abs(x) - half, 0) ** 2 + z ** 2 <= t * t / 4)


def _ball(r):
    return lambda x, y, z: x ** 2 + y ** 2 + z ** 2 <= r * r


def _shape(family, width, inside, cls, part=None, side="solid"):
    """part: the thin feature itself (default: the whole body); a draw counts only if the lattice holds it (one node of the right sign inside it)."""
    return {"family": family, "width": width, "inside": inside, "cls": cls, "part": part or inside, "side": side}


def _band(w):
    return "thin" if w <= 1 else ("thick" if w >= 2.5 else "transition")


SHAPES = {
    **{f"slab_w{w}": _shape("slab", w, _slab(w), _band(w)) for w in (0.5, 0.75, 1, 1.25, 1.5, 1.75, 2, 2.5, 3)},
    **{f"fin_w{w}_l{ln}": _shape("fin", w, *_fin(w, ln)[:1], "thin" if ln >= 2 else "short", _fin(w, ln)[1]) for w in (0.5, 1) for ln in (0.5, 1, 1.5, 2, 4)},
    "fin_w3_l4": _shape("fin", 3, _fin(3, 4)[0], "thick", _fin(3, 4)[1]),
    **{f"neck_d{d}_l4": _shape("neck", d, _neck(d, 4)[0], _band(d), _neck(d, 4)[1]) for d in (0.5, 1, 1.5, 2.5)},
    **{f"neck_d1_l{g}": _shape("neck", 1, _neck(1, g)[0], "short", _neck(1, g)[1]) for g in (1, 2)},
    **{f"wedge_{t}deg": _shape("wedge", None, _wedge(t), "wedge") for t in (20, 40, 60, 90)},
    **{f"slot_g{g}": _shape("slot", g, _slot(g)[0], _band(g), _slot(g)[1], "void") for g in (0.5, 1, 1.5, 3)},
    **{f"stadium_t{t}": _shape("stadium", t, _stadium(t), "thick" if t >= 3 else "transition") for t in (2, 3, 4.6)},
    **{f"ball_r{r}": _shape("ball", 2 * r, _ball(r), "thick" if r >= 2 else "transition") for r in (1, 1.5, 2, 3)},
}
ASLABS = {f"aslab_w{w}": _shape("aligned_slab", w, _slab(w, half=100), "k5") for w in (1.0, 1.125, 1.25, 1.375, 1.5, 1.625, 1.75, 1.875, 2.0, 2.25, 2.5)}


def rotation(rng) -> np.ndarray:
    q, r = np.linalg.qr(rng.standard_normal((3, 3)))
    q = q * np.sign(np.diag(r))
    return q if np.linalg.det(q) > 0 else -q


def draw(rng, n=SYN_N) -> tuple[np.ndarray, np.ndarray]:
    """A uniform random rotation and a uniform sub-cell placement of the shape centre (node-index units)."""
    return rotation(rng), (n - 1) / 2 + rng.uniform(-0.5, 0.5, 3)


def _local(points: np.ndarray, rot: np.ndarray, c: np.ndarray) -> np.ndarray:
    return (points - c) @ rot  # rot columns = local axes in the lattice frame


def synthetic_phi(inside, rot, c, n=SYN_N, k=SYN_K, h=H) -> np.ndarray:
    """Near-exact SDF (error <= h/2k) of the shape rotated by `rot` and centred at `c`: signed EDT of the inside predicate on a k-fold refinement."""
    ax = np.arange((n - 1) * k + 1) / k
    q = _local(np.stack(np.meshgrid(ax, ax, ax, indexing="ij"), axis=-1), rot, c)
    ins = inside(q[..., 0], q[..., 1], q[..., 2])
    f = np.where(ins, -(ndimage.distance_transform_edt(ins) - 0.5), ndimage.distance_transform_edt(~ins) - 0.5) / k
    return (f[::k, ::k, ::k] * h).astype("<f4")


def represented(sh: dict, phi: np.ndarray, rot, c) -> bool:
    q = _local(np.stack(np.indices(phi.shape), axis=-1).astype(np.float64), rot, c)
    part = sh["part"](q[..., 0], q[..., 1], q[..., 2])
    return bool((part & ((phi < 0) if sh["side"] == "solid" else (phi > 0))).any())


# ---------------------------------------------------------------- tasks
V18_PARENT_PHASES = [(i / 8, l / 4, j / 8) for i in range(8) for l in range(4) for j in range(8)]
V18_MODE_PHASES = [(i / 4, 0.0, j / 4) for i in range(4) for j in range(4)]


def combos() -> list[tuple]:
    rng, names = np.random.default_rng([SEED, 1]), list(basis())
    out = []
    for i in range(N_COMBOS + N_NOISY):
        ms = rng.choice(names, size=int(rng.integers(2, 4)), replace=False)
        out.append(("combo", i, tuple((str(m), float(rng.uniform(-1, 1))) for m in ms), i if i >= N_COMBOS else None))
    return out


def tasks() -> list[tuple]:
    import mode01_prescreen as P
    import mode01_v18_prescreen as P18
    import v18_tip_probe as TP
    t = [("v18", "parent", 0.0, ph) for ph in V18_PARENT_PHASES]
    t += [("v18", m, a, ph) for m, a in P18.tasks() if m != "parent" for ph in V18_MODE_PHASES]
    t += combos()
    rng = np.random.default_rng(TP.SEED)  # the S0 probe's own draws
    t += [("roundtip", (rng.uniform(-0.04, 0.04), rng.uniform(-0.04, 0.04), rng.uniform(-5, 5), rng.uniform(-0.08, 0.08)), i) for i in range(TP.N)]
    t += [(fam, m, a) for fam in ("opt01", "regen6p25") for m, a in P.tasks(fam)]
    t += [("reinit04", "baseline"), ("reinit04", "lowdim03_parent")]
    t += [("syn", name, d) for name in SHAPES for d in range(SYN_DRAWS)]
    t += [("aslab", name, i) for name in ASLABS for i in range(ASLAB_PHASES)]
    return t


# ---------------------------------------------------------------- checks, criteria, tables
def passes(row, rule) -> bool:
    return row[rule]["status"] == "pass"


def ev(rows, rule) -> list:
    return [r for r in rows if r[rule]["status"] != "not_evaluated"]


def records() -> dict:
    out = {"v18": {(r["mode"], r["amplitude"]): r for r in json.loads(V18_PRESCREEN.read_text())["states"]}}
    for fam, f in (("opt01", "prescreen.json"), ("regen6p25", "prescreen_regen6p25.json")):
        out[fam] = {(r["mode"], r["amplitude"]): r for r in json.loads((MODE01 / f).read_text())["states"]}
    out["reinit04"] = json.loads((ROOT / "docs/evidence/reinit04_v17_2026_10_15/result.json").read_text())["states"]
    return out


def checks(rows: list[dict], rec: dict) -> dict:
    """Consistency against the committed records; any mismatch makes the run invalid."""
    out = {"errors": [r for r in rows if "error" in r]}
    zero = [r for r in rows if r["task"][0] == "v18" and not any(r["phase"])]
    out["v18_phase0"] = {"n": len(zero), "sha_mismatch": [(r["mode"], r["amplitude"]) for r in zero if r["phi_fortran_sha256"] != rec["v18"][(r["mode"], r["amplitude"])]["phi_fortran_sha256"]],
                         "r0_status_mismatch": [(r["mode"], r["amplitude"]) for r in zero if r["r0"]["status"] != rec["v18"][(r["mode"], r["amplitude"])]["gate_status"]["min_feature_width"]]}
    tp = json.loads((ROOT / "docs/evidence/v18_genesis_2026_10_19/tip_probe.json").read_text())["variants"]["rev1_round_tip_0.434375"]["rows"]
    out["roundtip"] = {"r0_width_mismatch": [r["draw"] for r in rows if r["task"][0] == "roundtip" and abs(r["r0"]["solid"] - tp[r["draw"]]["min_feature_width_m"]) > 1e-12]}
    for fam in ("opt01", "regen6p25"):
        mine = [r for r in rows if r["task"][0] == fam]
        out[fam] = {"n": len(mine), "sha_mismatch": [(r["mode"], r["amplitude"]) for r in mine if r["phi_fortran_sha256"] != rec[fam][(r["mode"], r["amplitude"])]["phi_fortran_sha256"]],
                    "r0_status_mismatch": [(r["mode"], r["amplitude"]) for r in mine if r["r0"]["status"] != rec[fam][(r["mode"], r["amplitude"])]["gate_status"]["min_feature_width"]]}
    out["reinit04"] = {r["state"]: {"state_sha_match": r["state_sha256"] == rec["reinit04"][r["state"]]["output"]["state_sha256"],
                                    "r0_status_match": r["r0"]["status"] == rec["reinit04"][r["state"]]["geom02"]["output_status"]["min_feature_width"]}
                       for r in rows if r["task"][0] == "reinit04"}
    out["valid"] = (not out["errors"] and not out["v18_phase0"]["sha_mismatch"] and not out["v18_phase0"]["r0_status_mismatch"] and not out["roundtip"]["r0_width_mismatch"]
                    and all(not out[f]["sha_mismatch"] and not out[f]["r0_status_mismatch"] for f in ("opt01", "regen6p25"))
                    and len(out["reinit04"]) == 2 and all(all(v.values()) for v in out["reinit04"].values()))
    return out


def v18_other_gate_failures(rec: dict, mode: str, a: float) -> list[str]:
    return [g for g in rec["v18"][(mode, a)]["failed_geom02"] if g != "min_feature_width"]


def hist_label(fam: str, r: dict, rec: dict) -> str:
    """Expected label from the documented mechanism (MODE-01 2026-10-16 README, REINIT-04 result), assigned before the run."""
    if fam == "reinit04":
        return "broken_export (designated gates: export, volume)"
    failed = rec[fam][(r["mode"], r["amplitude"])]["failed_geom02"]
    if fam == "opt01" and r["mode"] == "surge" and abs(r["amplitude"]) == 25:
        return "rim_mismatch (real defect, expected fail; one lattice-congruent pair)"
    if "near_zero_gradient_band" in failed:
        return "tie_plateau (designated gate: near_zero_gradient_band)"
    if r["mode"] == "thickness":
        return "thinned_slab (near the limit, no expectation)"
    return "other"


def w50(frac: dict):
    """Width (cells) where the fail fraction first drops to 0.5 or below, linearly interpolated; None if it never does."""
    ws = sorted(frac)
    if frac[ws[0]] <= 0.5:
        return ws[0]
    for a, b in zip(ws, ws[1:]):
        if frac[a] > 0.5 >= frac[b]:
            return a + (frac[a] - 0.5) / (frac[a] - frac[b]) * (b - a)
    return None


def criteria(rows: list[dict], rec: dict) -> dict:
    k1 = [r for r in rows if r["task"][0] in ("combo", "roundtip") or (r["task"][0] == "v18" and not v18_other_gate_failures(rec, r["mode"], r["amplitude"]))]
    syn = [r for r in rows if r["task"][0] == "syn"]
    thin = [r for r in syn if SHAPES[r["shape"]]["cls"] == "thin" and r["represented"]]
    thick = [r for r in syn if SHAPES[r["shape"]]["cls"] == "thick"]
    short = [r for r in syn if SHAPES[r["shape"]]["cls"] == "short" and r["represented"]]
    aslab = [r for r in rows if r["task"][0] == "aslab"]
    hist = [r for r in rows if r["task"][0] in ("opt01", "regen6p25", "reinit04") and (r["task"][0] == "reinit04" or rec[r["task"][0]][(r["mode"], r["amplitude"])]["gate_status"]["min_feature_width"] != "pass")]
    out = {"n": {"K1": len(k1), "K2_thin_represented": len(thin), "K2_thin_not_represented": sum(SHAPES[r["shape"]]["cls"] == "thin" and not r["represented"] for r in syn),
                 "K3_thick": len(thick), "short_represented": len(short), "historical_failures": len(hist)}}
    for rule in RULES:
        frac = {ASLABS[n]["width"]: sum(not passes(r, rule) for r in aslab if r["shape"] == n) / ASLAB_PHASES for n in ASLABS}
        hrows = []
        for r in hist:
            fam = r["task"][0]
            other = (["export_surface_integrity", "volume_semantics"] if fam == "reinit04"
                     else [g for g in rec[fam][(r["mode"], r["amplitude"])]["failed_geom02"] if g != "min_feature_width"])
            hrows.append({"family": fam, "state": r.get("mode", r.get("state")), "amplitude": r.get("amplitude"), "label": hist_label(fam, r, rec),
                          "passes": passes(r, rule), "bundle_still_fails_via": other})
        out[rule] = {
            "K1_not_pass": sum(not passes(r, rule) for r in ev(k1, rule)), "K1_evaluated": len(ev(k1, rule)),
            "K1_by_kind": {k: sum(not passes(r, rule) for r in ev(k1, rule) if r["task"][0] == k) for k in ("v18", "combo", "roundtip")},
            "K2_thin_passed": sum(passes(r, rule) for r in thin),
            "K3_thick_not_passed": sum(not passes(r, rule) for r in thick),
            "K4_rim_mismatch_passed": [h["amplitude"] for h in hrows if h["label"].startswith("rim_mismatch") and h["passes"]],
            "K4_historical_still_failing": sum(not h["passes"] for h in hrows),
            "K4_passed_with_no_other_failing_gate": [h for h in hrows if h["passes"] and not h["bundle_still_fails_via"]],
            "historical": hrows,
            "aligned_slab_fail_fraction": frac, "aligned_slab_w50_cells": w50(frac),
            "short_features_not_passed": sum(not passes(r, rule) for r in short),
        }
    r1x2 = [r for r in thin if "r1_phi_x2" in r]
    out["r1"]["K6_thin_passed_with_phi_x2"] = sum(r["r1_phi_x2"]["status"] == "pass" for r in r1x2)
    for rule in RULES:
        c = out[rule]
        c["K5_not_relaxation"] = c["aligned_slab_w50_cells"] is not None and out["r0"]["aligned_slab_w50_cells"] is not None and c["aligned_slab_w50_cells"] >= out["r0"]["aligned_slab_w50_cells"]
        c["K6_phi_scale_invariant"] = rule != "r1" or c["K6_thin_passed_with_phi_x2"] == 0  # R0, R2-R4 use only the sign of trilinear phi
        c["meets_K1_K6"] = (c["K1_not_pass"] == 0 and c["K2_thin_passed"] == 0 and c["K3_thick_not_passed"] == 0 and not c["K4_rim_mismatch_passed"]
                            and not c["K4_passed_with_no_other_failing_gate"] and c["K5_not_relaxation"] and c["K6_phi_scale_invariant"])
    return out


def f3(x):
    return "-" if x is None else ("inf" if x == math.inf else f"{x * 1000:.1f}")


def _counts(g, rules=RULES) -> str:
    """Not-pass counts per rule; 'k of n' when the rule was evaluated on only n of the rows (R2 outside D1 and phase 0)."""
    return " | ".join(f"{sum(not passes(r, x) for r in ev(g, x))}" + ("" if len(ev(g, x)) == len(g) else f" of {len(ev(g, x))}") for x in rules)


def tables(rows: list[dict], crit: dict, rec: dict) -> dict[str, str]:
    md = {}
    v18 = [r for r in rows if r["task"][0] == "v18"]
    lines = []
    for key in dict.fromkeys((r["mode"], r["amplitude"]) for r in v18):
        g = [r for r in v18 if (r["mode"], r["amplitude"]) == key]
        loc = {}
        for r in g:
            for x in r.get("r0_location", []):
                loc[x] = loc.get(x, 0) + 1
        bad = [r for r in g if not passes(r, "r0")]
        lines.append(f"| {key[0]} | {key[1]:g} | {', '.join(v18_other_gate_failures(rec, *key)) or '-'} | {g[0]['min_thickness_m'] * 1000:.1f} | {len(g)} | {_counts(g)}"
                     f" | {', '.join(sorted({f3(r['r0']['solid']) for r in g}))} | {', '.join(f'{k} {v}' for k, v in sorted(loc.items())) or '-'}"
                     f" | {f3(max((r['r4']['solid'] for r in bad), default=None))} | {f3(min(r['r1']['solid'] for r in g))} | {f3(max(r['r3']['solid'] for r in g))} |")
    md["v18_phase_sweep_table.md"] = ("Counts are (state, phase) pairs that do not pass, out of `phases`. Phase 0 is the gated harness bytes. `other gates` = non-width gates the recorded phase-0 bundle fails (such states are outside K1).\n\n"
                                      "| mode | a | other gates (phase 0) | min thickness mm | phases | R0 | R1 | R2 | R3 | R4 | R0 solid values mm | R0 failure location (phases) | R4 defect of R0 failures, max mm | R1 min mm | R3 max defect mm |\n"
                                      "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|\n" + "\n".join(lines) + "\n")
    cmb = [r for r in rows if r["task"][0] == "combo"]
    rt = [r for r in rows if r["task"][0] == "roundtip"]
    md["v18_combos_table.md"] = ("| set | n | R0 | R1 | R2 | R3 | R4 | R3 max defect mm |\n|---|---|---|---|---|---|---|---|\n"
                                 + "\n".join(f"| {name} | {len(g)} | {_counts(g)} | {f3(max((r['r3']['solid'] for r in g), default=None))} |"
                                             for name, g in (("2-3 basis modes, c ~ U(-1, 1) x A*", [r for r in cmb if not r["noisy"]]),
                                                             ("same with U(-h/16, h/16) phi noise", [r for r in cmb if r["noisy"]]),
                                                             ("rev. 1 round tips, 40 S0 placements", rt))) + "\n")
    syn = [r for r in rows if r["task"][0] == "syn"]
    lines = []
    for n, sh in SHAPES.items():
        g = [r for r in syn if r["shape"] == n]
        gr = [r for r in g if r["represented"]]
        lines.append(f"| {n} | {sh['width'] if sh['width'] is not None else '-'} | {sh['cls']} | {len(gr)}/{len(g)} | {_counts(gr)}"
                     f" | {', '.join(sorted({f3(r['r0']['solid']) for r in gr}))} | {f3(min((r['r1']['solid'] for r in gr if r['r1']['solid'] is not None), default=None))}"
                     f" | {f3(max((r['r3']['solid'] for r in gr if r['r3']['solid'] is not None), default=None))} | {f3(max((r['r3']['void'] or 0 for r in gr), default=None))} |")
    md["synthetic_table.md"] = (f"Counts are draws that do not pass, among the draws whose lattice holds the feature (`held`), {SYN_DRAWS} draws of random rotation and sub-cell translation each.\n\n"
                                "| shape | true width (h) | class | held | R0 | R1 | R2 | R3 | R4 | R0 solid values mm | R1 min solid mm | R3 max solid defect mm | R3 max void defect mm |\n"
                                "|---|---|---|---|---|---|---|---|---|---|---|---|---|\n" + "\n".join(lines) + "\n\n"
                                f"Axis-aligned slabs spanning the lattice, {ASLAB_PHASES} sub-cell phases (K5): fail fraction\n\n| w (h) | " + " | ".join(RULES) + " |\n|---|" + "---|" * len(RULES) + "\n"
                                + "\n".join(f"| {w} | " + " | ".join(f"{crit[x]['aligned_slab_fail_fraction'][w]:.3f}" for x in RULES) + " |" for w in sorted(crit["r0"]["aligned_slab_fail_fraction"]))
                                + "\n| 50 % width | " + " | ".join(str(None if crit[x]["aligned_slab_w50_cells"] is None else round(crit[x]["aligned_slab_w50_cells"], 3)) for x in RULES) + " |\n")
    hist = [r for r in rows if r["task"][0] in ("opt01", "regen6p25", "reinit04")]
    lines = []
    for r in hist:
        fam = r["task"][0]
        recorded = "fail" if fam == "reinit04" else rec[fam][(r["mode"], r["amplitude"])]["gate_status"]["min_feature_width"]
        label = hist_label(fam, r, rec) if recorded != "pass" else "-"
        lines.append(f"| {fam} | {r.get('mode', r.get('state'))} | {r.get('amplitude', '')} | {recorded} | {label} | " + " | ".join(r[x]["status"] for x in RULES)
                     + f" | {f3(r['r0']['solid'])} | {f3(r['r1']['solid'])} | {r['r2']['n_pass']}/8 | {f3(r['r3']['solid'])} / {f3(r['r3']['void'])} | {f3(r['r4']['solid'])} / {f3(r['r4']['void'])} |")
    md["historical_table.md"] = ("| family | state | a | recorded width | label (pre-assigned) | R0 | R1 | R2 | R3 | R4 | R0 solid mm | R1 solid mm | R2 phases passing | R3 defect solid / void mm | R4 defect solid / void mm |\n"
                                 "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|\n" + "\n".join(lines) + "\n")
    lines = [f"| {x} | {c['K1_not_pass']}/{c['K1_evaluated']} | {c['K2_thin_passed']}/{crit['n']['K2_thin_represented']} | {c['K3_thick_not_passed']}/{crit['n']['K3_thick']} | "
             f"{len(c['K4_rim_mismatch_passed'])} | {c['K4_historical_still_failing']}/{crit['n']['historical_failures']} | {len(c['K4_passed_with_no_other_failing_gate'])} | "
             f"{None if c['aligned_slab_w50_cells'] is None else round(c['aligned_slab_w50_cells'], 3)} | {c['K5_not_relaxation']} | {c['K6_phi_scale_invariant']} | "
             f"{c['short_features_not_passed']}/{crit['n']['short_represented']} | {c['meets_K1_K6']} |" for x, c in ((x, crit[x]) for x in RULES)]
    md["criteria_table.md"] = ("| rule | K1 v18 + combos + round tips not passing | K2 thin passed | K3 thick not passed | K4 rim-mismatch passed | K4 historical width failures still failing | historical passed with no other failing gate | aligned-slab 50 % width (h) | K5 | K6 | short features (l <= 1.5h) not passing | meets K1-K6 |\n"
                               "|---|---|---|---|---|---|---|---|---|---|---|---|\n" + "\n".join(lines) + "\n")
    return md


def jsonable(x):
    if isinstance(x, float) and math.isinf(x):
        return "inf"
    if isinstance(x, dict):
        return {k: jsonable(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [jsonable(v) for v in x]
    if isinstance(x, (np.floating, np.integer, np.bool_)):
        return x.item()
    return x


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=5)
    ap.add_argument("--limit", type=int, default=0, help="smoke: every Nth task only, nothing written")
    ap.add_argument("--cache", type=Path, default=ROOT / "work/width_rule_2026_10_20/rows.jsonl", help="append-only row cache; a restart skips cached tasks")
    args = ap.parse_args()
    todo = tasks()
    if args.limit:
        todo = todo[::args.limit]
    key = lambda t: json.dumps(list(t))  # noqa: E731
    done = {}
    if not args.limit and args.cache.exists():
        for line in args.cache.read_text().splitlines():
            r = json.loads(line)
            done[json.dumps(r["task"])] = r
    left = [t for t in todo if key(t) not in done]
    print(f"{len(todo)} tasks, {len(todo) - len(left)} cached", flush=True)
    args.cache.parent.mkdir(parents=True, exist_ok=True)
    with Pool(args.workers, initializer=_init) as pool, open(args.cache, "a") as cache:
        for i, r in enumerate(pool.imap_unordered(work, left)):
            done[json.dumps(r["task"])] = r
            if not args.limit:
                cache.write(json.dumps(r) + "\n")
                cache.flush()
            if i % 50 == 0 or "error" in r:
                print(i, len(left), r["task"][:3], r.get("error", ""), flush=True)
    rows = [done[key(t)] for t in todo]
    if args.limit:
        print(json.dumps(jsonable([{k: v for k, v in r.items() if k in ("task", "error", *RULES)} for r in rows[:6]]), indent=1)[:6000])
        return
    rec = records()
    meta = {"kind": "width_rule_study", "evidence_tier": "EXPLORATORY_COMMITTED", "plan": "docs/width_rule_plan_2026_10_20.md (rev. 2)", "solver_started": False,
            "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), "h_m": H,
            "parameters": {"limit_cells": LIMIT_CELLS, "guard_cells": GUARD_CELLS, "r2_shifts_cells": R2_SHIFTS,
                           "r2_evaluated_on": "D1 (parent, 256 phases), phase 0 of every MODE-01 v18 state, round tips, synthetic, historical; not on D2 phases != 0 or D3 (compute deviation, plan §9)",
                           "opening": {"k": OPEN_K, "radius_cells": OPEN_RADIUS_CELLS, "tau_cells": OPEN_TAU_CELLS, "unmeasured_band_cells": GUARD_CELLS, "crop_pad_cells": OPEN_PAD},
                           "synthetic": {"seed": SEED, "lattice_nodes": SYN_N, "refinement": SYN_K, "draws": SYN_DRAWS, "aligned_slab_phases": ASLAB_PHASES},
                           "combos": {"n": N_COMBOS, "noisy": N_NOISY, "basis_a_star": basis(), "noise": "U(-h/16, h/16) on active nodes"}},
            "phases": {"v18_parent": V18_PARENT_PHASES, "v18_modes": V18_MODE_PHASES, "unit": "fraction of h by which the lattice origin is shifted (x, y, z)"},
            "versions": {m.__name__: m.__version__ for m in (np, __import__("scipy"))}, "flags_changed": False, "shape_update_allowed": False}
    chk, crit = checks(rows, rec), criteria(rows, rec)
    OUT.mkdir(parents=True, exist_ok=True)
    groups = {"v18_phase_sweep.json": ("v18", "combo", "roundtip"), "synthetic.json": ("syn", "aslab"), "historical.json": ("opt01", "regen6p25", "reinit04")}
    for name, kinds in groups.items():
        (OUT / name).write_text(json.dumps(jsonable({"meta": meta, "rows": [r for r in rows if r["task"][0] in kinds]}), indent=1, sort_keys=True) + "\n")
    (OUT / "summary.json").write_text(json.dumps(jsonable({"meta": meta, "checks": chk, "criteria": crit}), indent=1, sort_keys=True) + "\n")
    for name, text in tables(rows, crit, rec).items():
        (OUT / name).write_text(text)
    print("checks valid:", chk["valid"])
    print((OUT / "criteria_table.md").read_text())


if __name__ == "__main__":
    main()
