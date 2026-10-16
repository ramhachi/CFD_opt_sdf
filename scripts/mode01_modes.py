#!/usr/bin/env python3
"""MODE-01 (#60) mode generators: large-amplitude smooth modes of the OPT-01 v1 parent, phi_new = resample(parent phi) (trilinear), no reinitialisation.
EXPLORATORY_COMMITTED, solver-free.  Pure numpy/scipy; deterministic bytes (no randomness, float64 arithmetic, float32 result).

Frame: +x is the flow, z up (ground at z = -0.9), y spanwise.  The body's nose is the low-x end.  Every transform acts in the x-z plane only, so no
material moves in y.  Each node is resampled at the source point of the material motion and only ACTIVE nodes (design mask minus fixed/forbidden/root)
are replaced; everything else keeps the parent bytes.  Amplitude units / sign conventions are in ``UNITS``.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from scipy.ndimage import map_coordinates

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src")]
from cfd_sdf.design.sdf_state import SDFDesignState  # noqa: E402

PARENT = ROOT / "docs/evidence/opt01a_stage_a_2026_10_15/inputs/opt01_v1_parent.npz"
PARENT_PHI_FORTRAN_SHA = "2f23be7824d31d6c270ada9b3ff2b815601b3435da78e4e7e9089908608bf3d7"
DIRS = ROOT / "docs/evidence/grad03_gpu_dual_spike_2026_10_08/inputs"
SIGMA_M, SIGMA_SMALL_M, TAPER_M = 0.125, 0.05, 0.05   # medium / small bump Gaussian sigma; cosine taper half-width in |phi| (m)
UNITS = {
    "pitch": "deg; + = nose DOWN (low-x end toward the ground, tail up), rotation about the y axis through the solid-node x-z centroid",
    "heave": "mm; + = body moves UP (+z, away from the ground)",
    "surge": "mm; + = body moves DOWNSTREAM (+x); negative control",
    "camber": "mm; z -> z - a*s^2 + c with s=(x-xc)/(L/2), c = a*mean(s^2 over solid nodes); + = nose and tail down relative to mid-chord (a = tip deflection), mean z kept",
    "thickness": "mm; phi - a (D0 style uniform normal offset); + = thicker",
    "aspect": "e (dimensionless); x scaled by (1+e), z by 1/(1+e) about the centroid (volume neutral), + = longer and thinner",
    "bump_lower": "mm; Gaussian normal offset on ground-facing (n_z<0) surface, centre (xc, 0), + = surface moves outward (down)",
    "bump_upper": "mm; same on the upward-facing (n_z>0) surface, + = surface moves outward (up)",
    "bump_small": "mm; as bump_lower with sigma 0.05 m (compact small support; added so the support ladder is ordered by node fraction)",
    "D1_filtered_seed11": "mm; phi + a*d, max-norm-1 direction from grad03 (small support)",
    "P1_upstream_lobe": "mm; phi + a*d, max-norm-1 direction from grad03 (small support)",
}


def load_parent() -> SDFDesignState:
    return SDFDesignState.load(PARENT)


def active_mask(s: SDFDesignState) -> np.ndarray:
    return s.design_mask & ~s.fixed_solid_mask & ~s.forbidden_mask & ~s.root_mask


def _axes(s):
    return np.meshgrid(*[o + np.arange(n) * s.spacing_m for o, n in zip(s.origin_m, s.shape)], indexing="ij")


def _resample(s, src) -> np.ndarray:
    """phi_new(p) = phi(src(p)); trilinear, nearest-edge outside the lattice (positive fluid extension)."""
    idx = np.stack([(c - o) / s.spacing_m for c, o in zip(src(*_axes(s)), s.origin_m)])
    idx = np.where(np.abs(idx - np.round(idx)) < 1e-9, np.round(idx), idx)  # exact lattice hits stay exact (identity, whole-spacing shifts)
    return map_coordinates(s.phi.astype(np.float64), idx, order=1, mode="nearest")


def body_frame(s) -> dict:
    """Centroid, x-length L of the solid, and s^2 mean over solid nodes (all from phi < 0 nodes)."""
    X, _, Z = _axes(s)
    m = s.phi < 0
    x = X[m]
    xc, zc, L = float(x.mean()), float(Z[m].mean()), float(x.max() - x.min() + s.spacing_m)
    return {"xc": xc, "zc": zc, "L": L, "mean_s2": float((((x - xc) / (L / 2)) ** 2).mean())}


def _taper(phi, w=TAPER_M):
    return np.where(np.abs(phi) < w, 0.5 * (1 + np.cos(np.pi * np.abs(phi) / w)), 0.0)


def _bump(s, a, sign, sigma):
    f = body_frame(s)
    X, Y, _ = _axes(s)
    phi = s.phi.astype(np.float64)
    g = np.stack(np.gradient(phi, s.spacing_m))
    nz = g[2] / np.maximum(np.sqrt((g ** 2).sum(0)), 1e-6)
    gauss = np.exp(-((X - f["xc"]) ** 2 + Y ** 2) / (2 * sigma ** 2))
    return phi - a / 1000.0 * gauss * _taper(phi) * np.clip(sign * nz, 0.0, 1.0)


def _dir(name):
    return np.frombuffer((DIRS / f"{name}.dir_f4_fortran.raw").read_bytes(), "<f4").reshape(121, 65, 49, order="F").astype(np.float64)


def raw_mode(s: SDFDesignState, mode: str, a: float) -> np.ndarray:
    f, m = body_frame(s), a / 1000.0
    if mode == "pitch":
        c, sn = np.cos(np.radians(a)), np.sin(np.radians(a))
        return _resample(s, lambda X, Y, Z: (f["xc"] + c * (X - f["xc"]) + sn * (Z - f["zc"]), Y, f["zc"] - sn * (X - f["xc"]) + c * (Z - f["zc"])))
    if mode == "heave":
        return _resample(s, lambda X, Y, Z: (X, Y, Z - m))
    if mode == "surge":
        return _resample(s, lambda X, Y, Z: (X - m, Y, Z))
    if mode == "camber":
        return _resample(s, lambda X, Y, Z: (X, Y, Z + m * (((X - f["xc"]) / (f["L"] / 2)) ** 2 - f["mean_s2"])))
    if mode == "thickness":
        return s.phi.astype(np.float64) - m
    if mode == "aspect":
        return _resample(s, lambda X, Y, Z: (f["xc"] + (X - f["xc"]) / (1 + a), Y, f["zc"] + (Z - f["zc"]) * (1 + a)))
    if mode == "bump_lower":
        return _bump(s, a, -1.0, SIGMA_M)
    if mode == "bump_upper":
        return _bump(s, a, 1.0, SIGMA_M)
    if mode == "bump_small":
        return _bump(s, a, -1.0, SIGMA_SMALL_M)
    if mode in ("D1_filtered_seed11", "P1_upstream_lobe"):
        return s.phi.astype(np.float64) + m * _dir(mode)
    raise ValueError(f"unknown mode {mode}")


def mode_phi(s: SDFDesignState, mode: str, a: float) -> np.ndarray:
    act = active_mask(s)
    return np.where(act, raw_mode(s, mode, a), s.phi.astype(np.float64)).astype("<f4")


def with_phi(s: SDFDesignState, phi: np.ndarray) -> SDFDesignState:
    """Child state: same grid, masks, generation and policies as the parent (construct_state semantics)."""
    return SDFDesignState.create(phi=phi, origin_m=s.origin_m, spacing_m=s.spacing_m, design_mask=s.design_mask, fixed_solid_mask=s.fixed_solid_mask,
                                 forbidden_mask=s.forbidden_mask, root_mask=s.root_mask, narrow_band_width_m=s.narrow_band_width_m, generation=s.generation,
                                 source_sha256=s.source_sha256, topology_policy_id=s.topology_policy_id, reinitialization_policy_id=s.reinitialization_policy_id)


def make_state(s: SDFDesignState, mode: str, a: float) -> SDFDesignState:
    return with_phi(s, mode_phi(s, mode, a))


def support_fraction(s: SDFDesignState, phi_new: np.ndarray) -> dict:
    """Share of interface-band nodes (active, |parent phi| <= 2h) whose |dphi| exceeds 10 % of the band maximum."""
    band = active_mask(s) & (np.abs(s.phi) <= 2 * s.spacing_m)
    d = np.abs(phi_new.astype(np.float64) - s.phi.astype(np.float64))[band]
    mx = float(d.max())
    return {"fraction": float((d > 0.1 * mx).mean()) if mx > 0 else 0.0, "band_nodes": int(band.sum()), "max_band_change_m": mx}


def phi_fortran_sha(phi: np.ndarray) -> str:
    import hashlib
    return hashlib.sha256(np.asarray(phi, "<f4").tobytes(order="F")).hexdigest()
