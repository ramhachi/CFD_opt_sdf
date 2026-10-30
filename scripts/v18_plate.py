#!/usr/bin/env python3
"""v18 analytic plate (#60, B1 2026-10-19): exact SDF of a stadium cross-section (thickness t, round leading/trailing edges) extruded over |y| <= y_tip
with flat tips, on the v17 lattice, and its analytic modes.
EXPLORATORY_COMMITTED, solver-free, deterministic (float64 arithmetic, float32 '<f4' result).  Plan: docs/v18_mode01_plan_2026_10_19.md.

d2 = sqrt(max(|u| - L/2, 0)^2 + w^2) - t/2,  dy = |y| - y_tip,  phi = min(max(d2, dy), 0) + sqrt(max(d2, 0)^2 + max(dy, 0)^2)   (exact extrusion SDF),
u = (x - xc) cos(alpha) + (z - zc) sin(alpha),  w = -(x - xc) sin(alpha) + (z - zc) cos(alpha) + camber (s^2 - 1/3) + reflex (s^3 - 3 s / 5),
s = clip(2u/L, -1, 1).  xc, zc and alpha may vary with eta = clip(y / y_tip, -1, 1) (twist, dihedral, sweep).
A mode recomputes phi with perturbed parameters on the ACTIVE nodes only; every other node keeps the parent bytes (as mode01_modes.mode_phi).
"""
from __future__ import annotations

import hashlib
import json
import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]
import mode01_modes as M  # noqa: E402
from cfd_sdf.design.sdf_state import SDFDesignState  # noqa: E402

V17_BASELINE = ROOT / "docs/evidence/p22_v17_volume_semantics_bridge_2026_10_11/inputs/v17_baseline.npz"  # = geom02_canonical.INPUTS
V17_BASELINE_NPZ_SHA = "7a972b330c11d6580c49de4cba9b5f4a0b2cb664dda67e4f7053c280655feb31"                  # geom02_canonical.BASELINE_NPZ_SHA
BBOX = {"x": (-0.6, 0.55), "z": (-0.25, 0.25)}   # v17 baseline solid-cell box: keeps LE/TE x, top and ride height (z_min = -0.25 m)
Y_TIP = 0.45 - 0.025 / 2                         # 0.4375 m: flat tip on the cell-centre plane, the only flat-face offset with crossing slope >= 0.5 on both sides
                                                 # (j = 15 inside the design mask at -12.5 mm, j = 14 outside at +12.5 mm; plan rev. 2 §3.3)
T_ROUND_M = 1e-4                                 # thickness rounded to 0.1 mm after the smoothed-volume bisection
UNITS = {
    "heave": "mm; zc + a, + = up", "surge": "mm; xc + a, + = downstream (control)", "pitch": "deg; alpha + a about (xc, zc), + = nose down (higher incidence)",
    "camber": "mm; w -> w + a (s^2 - 1/3): + = mid-chord up, edges down (a = mid-minus-edge deflection)",
    "reflex": "mm; w -> w + a (s^3 - 3s/5): + = trailing edge down, leading edge up",
    "thick_chord": "e; t (1 + e) with L re-solved for equal section area L t + pi t^2 / 4 (exact volume, flat tips), centre, alpha, y_tip kept; + = thicker and shorter",
    "twist": "deg; alpha(y) = alpha + a (eta^2 - 1/3), + = tips nose down relative to mid-span", "twist_anti": "deg; alpha(y) = alpha + a eta (control: mirror-odd)",
    "dihedral": "mm; zc(y) = zc + a (eta^2 - 1/3), + = tips up", "sweep": "mm; xc(y) = xc + a (eta^2 - 1/3), + = tips downstream",
    "thickness_D0": "mm; phi - a (mode01_modes thickness; NOT volume neutral, reference)",
    "offset_s400": "mm; phi - a g taper, g = exp(-((x-xc)^2 + y^2) / (2 sigma^2)), sigma 0.4 m, both surfaces, + = outward (support axis; not neutral)",
    "offset_s125": "mm; as offset_s400 with sigma 0.125 m", "offset_s050": "mm; as offset_s400 with sigma 0.05 m",
    "corrugation": "mm; phi - a cos(2 pi u / 0.1) cos(2 pi y / 0.1) taper (wavelength 4h over the whole band: wide extent, low smoothness; mean ~0)",
}
SIGMA_M = {"offset_s400": 0.4, "offset_s125": 0.125, "offset_s050": 0.05}
CORRUGATION_WAVELENGTH_M = 0.1


def fit(t: float) -> dict:
    """Plate parameters for thickness t that fill the v17 bounding box (stadium extent = L cos(alpha) + t in x, L sin(alpha) + t in z)."""
    (x0, x1), (z0, z1) = BBOX["x"], BBOX["z"]
    lc, ls = x1 - x0 - t, z1 - z0 - t
    return {"xc": (x0 + x1) / 2, "zc": (z0 + z1) / 2, "alpha": math.atan2(ls, lc), "L": math.hypot(lc, ls), "t": t, "y_tip": Y_TIP, "camber": 0.0, "reflex": 0.0}


def volume(L: float, t: float, y_tip: float = Y_TIP) -> float:
    """Exact volume: stadium section area (L t + pi t^2 / 4) x span 2 y_tip (flat tips)."""
    return (L * t + math.pi * t * t / 4) * 2 * y_tip


def axes(s: SDFDesignState):
    return np.meshgrid(*[o + np.arange(n) * s.spacing_m for o, n in zip(s.origin_m, s.shape)], indexing="ij")


def plate_phi(s: SDFDesignState, p: dict, twist=None, dihedral=None, sweep=None) -> np.ndarray:
    """float64 phi on the whole lattice; twist/dihedral/sweep are callables eta -> d_alpha (rad) / d_zc (m) / d_xc (m)."""
    X, Y, Z = axes(s)
    eta = np.clip(Y / p["y_tip"], -1.0, 1.0)
    alpha = p["alpha"] + (twist(eta) if twist else 0.0)
    xc, zc = p["xc"] + (sweep(eta) if sweep else 0.0), p["zc"] + (dihedral(eta) if dihedral else 0.0)
    ca, sa = np.cos(alpha), np.sin(alpha)
    u = (X - xc) * ca + (Z - zc) * sa
    w = -(X - xc) * sa + (Z - zc) * ca
    sc = np.clip(2 * u / p["L"], -1.0, 1.0)
    w = w + p["camber"] * (sc ** 2 - 1 / 3) + p["reflex"] * (sc ** 3 - 0.6 * sc)
    d2 = np.sqrt(np.maximum(np.abs(u) - p["L"] / 2, 0) ** 2 + w ** 2) - p["t"] / 2
    dy = np.abs(Y) - p["y_tip"]
    return np.minimum(np.maximum(d2, dy), 0) + np.sqrt(np.maximum(d2, 0) ** 2 + np.maximum(dy, 0) ** 2)


def raw_mode(s: SDFDesignState, p: dict, mode: str, a: float) -> np.ndarray:
    m, q = a / 1000.0, dict(p)
    bow = lambda e: m * (e ** 2 - 1 / 3)  # noqa: E731
    if mode == "heave":
        q["zc"] += m
    elif mode == "surge":
        q["xc"] += m
    elif mode == "pitch":
        q["alpha"] += math.radians(a)
    elif mode in ("camber", "reflex"):
        q[mode] += m
    elif mode == "thick_chord":
        t2 = p["t"] * (1 + a)
        q["t"], q["L"] = t2, (p["L"] * p["t"] + math.pi * p["t"] ** 2 / 4 - math.pi * t2 * t2 / 4) / t2
    elif mode == "twist":
        return plate_phi(s, q, twist=lambda e: math.radians(a) * (e ** 2 - 1 / 3))
    elif mode == "twist_anti":
        return plate_phi(s, q, twist=lambda e: math.radians(a) * e)
    elif mode == "dihedral":
        return plate_phi(s, q, dihedral=bow)
    elif mode == "sweep":
        return plate_phi(s, q, sweep=bow)
    elif mode == "thickness_D0":
        return M.raw_mode(s, "thickness", a)
    elif mode in SIGMA_M or mode == "corrugation":
        X, Y, Z = axes(s)
        phi = s.phi.astype(np.float64)
        if mode == "corrugation":
            u = (X - p["xc"]) * math.cos(p["alpha"]) + (Z - p["zc"]) * math.sin(p["alpha"])
            g = np.cos(2 * math.pi * u / CORRUGATION_WAVELENGTH_M) * np.cos(2 * math.pi * Y / CORRUGATION_WAVELENGTH_M)
        else:
            g = np.exp(-((X - p["xc"]) ** 2 + Y ** 2) / (2 * SIGMA_M[mode] ** 2))
        return phi - m * g * M._taper(phi)
    else:
        raise ValueError(f"unknown mode {mode}")
    return plate_phi(s, q)


def mode_phi(s: SDFDesignState, p: dict, mode: str, a: float) -> np.ndarray:
    if a == 0:
        return s.phi.copy()
    return np.where(M.active_mask(s), raw_mode(s, p, mode, a), s.phi.astype(np.float64)).astype("<f4")


def harness_direction(s: SDFDesignState, phi_analytic: np.ndarray) -> tuple[np.ndarray, float]:
    """Max-normalised float32 direction and step (mm) of the harness state model parent + step * direction (zero outside the active set)."""
    d = np.where(M.active_mask(s), phi_analytic.astype(np.float64) - s.phi.astype(np.float64), 0.0)
    peak = float(np.abs(d).max())
    return (d / peak).astype("<f4"), peak * 1000.0


def harness_state(s: SDFDesignState, phi_analytic: np.ndarray) -> SDFDesignState:
    """The bytes the campaign harness builds: construct_state(parent, direction, step_mm, +1) with harness_direction (these are the gated bytes)."""
    from cfd_sdf.fd08_v2_campaign import construct_state
    return construct_state(s, *harness_direction(s, phi_analytic), 1)[0]


def spec_sha(p: dict) -> str:
    return hashlib.sha256(json.dumps(p, sort_keys=True).encode()).hexdigest()


def build_parent(t: float | None = None) -> tuple[SDFDesignState, dict]:
    """v18 parent on the v17 lattice with the v17 baseline masks/policies.  t=None: bisection so the smoothed volume equals the v17 baseline's, rounded to 0.1 mm."""
    import build_lowdim01_inputs as lowdim  # heavy, only needed here
    base = SDFDesignState.load(V17_BASELINE)

    def state(tt):
        p = fit(tt)
        phi = plate_phi(base, p).astype("<f4")
        return SDFDesignState.create(phi=phi, origin_m=base.origin_m, spacing_m=base.spacing_m, design_mask=base.design_mask, fixed_solid_mask=base.fixed_solid_mask,
                                     forbidden_mask=base.forbidden_mask, root_mask=base.root_mask, narrow_band_width_m=base.narrow_band_width_m, generation=0,
                                     source_sha256=spec_sha(p), topology_policy_id=base.topology_policy_id, reinitialization_policy_id=base.reinitialization_policy_id), p

    if t is None:
        v0 = lowdim.geometry(base)["smoothed_volume_m3"]
        lo, hi = 0.10, 0.13
        for _ in range(40):  # ponytail: plain bisection on a monotone volume, 40 halvings of 30 mm is far below the 0.1 mm rounding
            mid = 0.5 * (lo + hi)
            lo, hi = (mid, hi) if lowdim.geometry(state(mid)[0])["smoothed_volume_m3"] < v0 else (lo, mid)
        t = round(0.5 * (lo + hi) / T_ROUND_M) * T_ROUND_M
    return state(t)
