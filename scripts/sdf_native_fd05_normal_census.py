"""FD-05 (#37) solver-free diagnostic: does the body normal jump under a tiny perturbation?

Re-evaluates the WaterLily `measure()` body quantities (trilinear phi value and
normalized analytic trilinear gradient, as in `WaterLilyBody.jl` /
`GridSDFBody.jl`) at the flow_24 cell centres and face centres near the zero
level, for the canonical v17 phi and each registered FD-05 perturbation.  A
smooth response needs max|n(eps) - n(0)| -> 0 linearly in eps; an
eps-independent normal change marks a non-differentiable body representation.

Diagnostic only: numpy float64 re-implementation, candidate body only (moving
ground excluded), WaterLily sample offsets approximated as cell centre +/- h/2.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

SHAPE = (121, 65, 49)
SDF_ORIGIN = np.array([-1.0, -0.8, -0.6])
SDF_H = 0.025
FLOW_ORIGIN = np.array([-2.5, -1.2, -0.9])
FLOW_H = 0.8 / 24
FLOW_DIMS = (150, 72, 54)
BAND_SOLVER = 2.0  # BDIM kernel support is |d| <= 1 solver cell; keep a margin
EPS_TAGS = {0.0005: "0p0005", 0.001: "0p0010", 0.0025: "0p0025", 0.005: "0p0050", 0.01: "0p0100"}
DIRECTIONS = ("D0_interface_offset", "D1_filtered_seed11", "D2_filtered_seed2026")


def sample_points() -> np.ndarray:
    """Cell centres plus the three face-centre families of the flow_24 grid (world m)."""
    idx = np.stack(np.meshgrid(*[np.arange(n) + 0.5 for n in FLOW_DIMS], indexing="ij"), -1).reshape(-1, 3)
    sets = [idx] + [idx - 0.5 * np.eye(3)[a] for a in range(3)]
    return FLOW_ORIGIN + FLOW_H * np.concatenate(sets)


def trilinear(phi: np.ndarray, x: np.ndarray):
    """Value and analytic gradient of the trilinear interpolant (points inside the box)."""
    s = (x - SDF_ORIGIN) / SDF_H
    i = np.minimum(np.floor(s).astype(int), np.array(SHAPE) - 2)
    t = s - i
    v = {(a, b, c): phi[i[:, 0] + a, i[:, 1] + b, i[:, 2] + c] for a in (0, 1) for b in (0, 1) for c in (0, 1)}
    w = lambda k, tk: tk if k else 1 - tk  # noqa: E731
    val = sum(w(a, t[:, 0]) * w(b, t[:, 1]) * w(c, t[:, 2]) * v[a, b, c] for (a, b, c) in v)
    dw = lambda k: 1.0 if k else -1.0  # noqa: E731
    gx = sum(dw(a) * w(b, t[:, 1]) * w(c, t[:, 2]) * v[a, b, c] for (a, b, c) in v)
    gy = sum(w(a, t[:, 0]) * dw(b) * w(c, t[:, 2]) * v[a, b, c] for (a, b, c) in v)
    gz = sum(w(a, t[:, 0]) * w(b, t[:, 1]) * dw(c) * v[a, b, c] for (a, b, c) in v)
    return val, np.stack([gx, gy, gz], -1) / SDF_H


def normals(g: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    mag = np.linalg.norm(g, axis=1)
    n = np.zeros_like(g)
    ok = mag > 0
    n[ok] = g[ok] / mag[ok, None]
    return n, mag


def load(path: Path) -> np.ndarray:
    return np.fromfile(path, "<f4").reshape(SHAPE, order="F").astype(np.float64)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", type=Path, required=True, help="FD-05 dataset directory")
    ap.add_argument("--output", type=Path)
    args = ap.parse_args()

    base = load(args.dataset / "canonical_v17_phi_f4_fortran.raw")
    x = sample_points()
    inside = np.all((x >= SDF_ORIGIN) & (x <= SDF_ORIGIN + SDF_H * (np.array(SHAPE) - 1)), axis=1)
    x = x[inside]
    d0, g0 = trilinear(base, x)
    band = np.abs(d0) / FLOW_H <= BAND_SOLVER
    x, d0, g0 = x[band], d0[band], g0[band]
    n0, mag0 = normals(g0)
    result = {
        "kind": "sdf_native_fd05_normal_census",
        "evidence_class": "diagnostic_only_solver_free",
        "band_solver_cells": BAND_SOLVER,
        "band_sample_count": int(len(x)),
        "baseline_grad_magnitude_quantiles": {q: float(np.quantile(mag0, q)) for q in (0.0, 0.001, 0.01, 0.05, 0.5)},
        "baseline_samples_grad_below_0p25": int(np.count_nonzero(mag0 < 0.25)),
        "baseline_samples_grad_below_1e-3": int(np.count_nonzero(mag0 < 1e-3)),
        "cases": {},
    }
    print(f"band samples {len(x)}; |grad| quantiles {result['baseline_grad_magnitude_quantiles']}")
    for direction in DIRECTIONS:
        for eps, tag in EPS_TAGS.items():
            for sign in ("plus", "minus"):
                phi = load(args.dataset / "perturbations" / f"{direction}__eps_{tag}m__{sign}.phi-f4-fortran.raw")
                d, g = trilinear(phi, x)
                n, mag = normals(g)
                dn = np.linalg.norm(n - n0, axis=1)
                big = dn > 0.1
                case = {
                    "max_normal_change": float(dn.max()),
                    "max_normal_change_per_eps_m": float(dn.max() / eps),
                    "samples_normal_change_gt_0p1": int(np.count_nonzero(big)),
                    "max_abs_d_change_m": float(np.abs(d - d0).max()),
                    "baseline_grad_magnitude_at_jumps_max": float(mag0[big].max()) if big.any() else None,
                    "jump_sample_abs_d_solver_max": float((np.abs(d0[big]) / FLOW_H).max()) if big.any() else None,
                }
                result["cases"][f"{direction}__{tag}__{sign}"] = case
                print(direction[:2], tag, sign, json.dumps(case))
    if args.output:
        args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
