"""Centered slopes and the registered plateau rule from sdf_native_fd06_frozen_flow_response.jl output, in N."""
import sys
import numpy as np

N_PER_SOLVER = 1.0 / 900.0
EPS = {"0p0005": 0.0005, "0p0010": 0.001, "0p0025": 0.0025, "0p0050": 0.005, "0p0100": 0.01}


def main(path):
    rows = [l.strip().split(",") for l in open(path)][1:]
    data = {}
    for t, d, e, s, tau, pfx, pfy, pfz, vfx, vfy, vfz in rows:
        data[(float(t), d, e, s, float(tau))] = dict(
            drag=(float(pfx) + float(vfx)) * N_PER_SOLVER, down=-(float(pfz) + float(vfz)) * N_PER_SOLVER,
            pdrag=float(pfx) * N_PER_SOLVER, vdrag=float(vfx) * N_PER_SOLVER)
    for t in sorted({k[0] for k in data}):
        for tau in sorted({k[4] for k in data}):
            print(f"== snapshot tU/L {t:.2f}  tau {tau}")
            for d in ("D0_interface_offset", "D1_filtered_seed11", "D2_filtered_seed2026"):
                for r in ("drag", "down", "pdrag", "vdrag"):
                    D = np.array([(data[(t, d, e, "plus", tau)][r] - data[(t, d, e, "minus", tau)][r]) / (2 * EPS[e])
                                  for e in EPS])
                    ref = np.median(D[:3]); dev = np.abs(D[:3] - ref) / max(abs(ref), 1e-8 / 0.0005)
                    print(f"  {d[:2]} {r:5s} slope[N/m] " + " ".join(f"{x:+.4f}" for x in D)
                          + f" | dev3 {100*dev.max():5.2f}%")


main(sys.argv[1])
