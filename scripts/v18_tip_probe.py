#!/usr/bin/env python3
"""S0 disclosure probe for the v18 tip choice (EXPLORATORY_COMMITTED, solver-free): crossing-slope failures and the GEOM-02 min_feature_width estimate
(min_feature_width_m on the cell occupancy, solid AABB + 1 cell, limit 0.0375 - guard 0.00625 m) over seeded random rigid placements of the plate, for the
rev. 1 round tips (rectangle ⊕ ball, y_tip 0.434375) and the rev. 2 flat tips (y_tip 0.4375).  Writes docs/evidence/v18_genesis_2026_10_19/tip_probe.json.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]
import mode01_prescreen as P  # noqa: E402
import v18_plate as V  # noqa: E402
from cfd_sdf.design.geometry_gates import cell_occupancy, min_feature_width_m  # noqa: E402

SEED, N, WIDTH_FAIL_BELOW_M = 20261019, 40, 0.0375 - 0.025 / 4


def round_tip_phi(s, p, y_tip=0.434375):
    X, Y, Z = V.axes(s)
    u = (X - p["xc"]) * math.cos(p["alpha"]) + (Z - p["zc"]) * math.sin(p["alpha"])
    w = -(X - p["xc"]) * math.sin(p["alpha"]) + (Z - p["zc"]) * math.cos(p["alpha"])
    return np.sqrt(np.maximum(np.abs(u) - p["L"] / 2, 0) ** 2 + np.maximum(np.abs(Y) - (y_tip - p["t"] / 2), 0) ** 2 + w ** 2) - p["t"] / 2


def width(s, phi):
    occ = cell_occupancy(M_with(s, phi))
    idx = np.argwhere(occ)
    return min_feature_width_m(occ[tuple(slice(max(a - 1, 0), b + 2) for a, b in zip(idx.min(0), idx.max(0)))], s.spacing_m)


def M_with(s, phi):
    return V.M.with_phi(s, np.asarray(phi, "<f4"))


def main() -> None:
    s, p0 = V.build_parent()
    rng = np.random.default_rng(SEED)
    draws = [(rng.uniform(-0.04, 0.04), rng.uniform(-0.04, 0.04), rng.uniform(-5, 5), rng.uniform(-0.08, 0.08)) for _ in range(N)]
    out = {"seed": SEED, "n": N, "draw": "dx, dz ~ U(-40, 40) mm, dalpha ~ U(-5, 5) deg, t (1 + U(-0.08, 0.08)); whole lattice, analytic phi (no mask)",
           "width_fail_below_m": WIDTH_FAIL_BELOW_M, "variants": {}}
    for name, fn in (("rev1_round_tip_0.434375", round_tip_phi), ("rev2_flat_tip_0.4375", V.plate_phi)):
        rows = []
        for dx, dz, da, dt in draws:
            p = {**p0, "xc": p0["xc"] + dx, "zc": p0["zc"] + dz, "alpha": p0["alpha"] + math.radians(da), "t": p0["t"] * (1 + dt)}
            phi = np.asarray(fn(s, p), "<f4")
            rows.append({"crossing_slope_fail_nodes": P.crossing_slope_failures(phi), "min_feature_width_m": width(s, phi)})
        out["variants"][name] = {"states_crossing_fail": sum(r["crossing_slope_fail_nodes"] > 0 for r in rows),
                                 "states_width_fail": sum(r["min_feature_width_m"] < WIDTH_FAIL_BELOW_M for r in rows), "rows": rows}
        print(name, out["variants"][name]["states_crossing_fail"], out["variants"][name]["states_width_fail"], flush=True)
    path = ROOT / "docs/evidence/v18_genesis_2026_10_19/tip_probe.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=1, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
