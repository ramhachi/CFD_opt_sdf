"""GEN-01 rev 3 cost model: WaterLily (GPU, fixed grid) as the main line, OpenFOAM primal (no adjoint) as the verifier.

Budgets are GPU-hours and verifier machine-days, not dollars. Anchors from this repository (Kaggle T4, WaterLily 1.8.0):
- flow_32: 1.38 M cells, 13,549 steps, 342 s  -> 5.5e7 cell-steps/s;  flow_48: 4.67 M cells, 27,372 steps, 2,267 s -> 5.6e7 cell-steps/s.
- memory 131-135 B/cell (float32).  T4 16 GB -> ~110 M cells; RTX 5090 32 GB -> ~220 M cells; A100 80 GB -> ~550 M cells.
- OpenFOAM verifier: FID-01 V3 1.46 M cells, simpleFoam 27,793 s for 4,548 iterations (Mac, Docker 4 cpus) -> ~6e4 cell-it/s/core;
  memory ~1.5 kB/cell (V3 RSS 2.16 GB) -> 128 GB holds ~50 M cells for a primal.
Assumptions: GPU speed relative to T4: RTX 5090 ~5x, A100 ~6x (to be measured; WaterLily is memory-bandwidth bound).
Time step: dt ~ CFL-limited at moderate Re: steps per convective time (c/U) ~ (c/h) / CFL with CFL ~0.5 (viscous limit no longer binds above Re_L ~ 800).
"""
from __future__ import annotations
import math

T4_RATE = 5.5e7                 # cell-steps per second
GPU = {"Kaggle T4 (30 h/week)": 1.0, "RTX 5090 32 GB (local, 24/7)": 5.0, "A100 80 GB (spot, optional)": 6.0}
BYTES_PER_CELL = 134
CFL = 0.5

# component cases: name, domain cells (nx, ny, nz) at the stated h, chord c in cells, convective window (c/U units), burn-in
CASES = {
    "front wing + ground, h 5 mm (Re_c ~3e3)":  dict(n=(300, 200, 120), c_cells=60,  window=150, burn=50),
    "front wing + ground, h 2.5 mm (Re_c ~1e4)": dict(n=(600, 400, 240), c_cells=120, window=200, burn=60),
    "sidepod + wheel, h 10 mm (Re_L ~3e3)":     dict(n=(300, 160, 160), c_cells=50,  window=150, burn=50),
    "coarse half car context, h 25 mm":         dict(n=(200, 96, 72),   c_cells=12,  window=120, burn=80),
}
# optimiser budgets: evaluations per campaign for 30-40 component variables
BUDGETS = {
    "reduced-basis FD, K=15, 30 iterations (+1.5 trials)": 30 * (2 * 15 + 1.5),
    "CMA-ES, 40 variables, 60 generations x 12": 60 * 12,
    "SCREEN-type response surface on 8 modes (45 coefficients x 2)": 90,
    "topology events: 6 x (5 seeds + 16 paired checks)": 6 * 21,
    "verification: 2 x 16 phase pairs": 32,
}


def run_cost(case):
    nx, ny, nz = case["n"]
    cells = nx * ny * nz
    steps = (case["window"] + case["burn"]) * case["c_cells"] / CFL
    cell_steps = cells * steps
    mem_gb = cells * BYTES_PER_CELL / 1e9
    return cells, steps, cell_steps, mem_gb


def main():
    print(f"{'case':46s} {'cells':>8s} {'steps':>8s} {'GB':>5s} | " + " | ".join(f"{g[:22]:>22s}" for g in GPU))
    per_eval = {}
    for name, case in CASES.items():
        cells, steps, cs, mem = run_cost(case)
        hours = {g: cs / (T4_RATE * f) / 3600 for g, f in GPU.items()}
        per_eval[name] = hours
        print(f"{name:46s} {cells:8.1e} {steps:8.0f} {mem:5.1f} | " + " | ".join(f"{hours[g]:18.2f} h/ev" for g in GPU))
    print()
    print("Campaign GPU-days per budget line, for the two front-wing cases (RTX 5090 local; Kaggle T4 at 30 h/week in weeks):")
    for bname, n_ev in BUDGETS.items():
        row = []
        for cname in list(CASES)[:2]:
            h5090 = per_eval[cname]["RTX 5090 32 GB (local, 24/7)"] * n_ev / 24
            wk_t4 = per_eval[cname]["Kaggle T4 (30 h/week)"] * n_ev / 30
            row.append(f"{h5090:6.1f} d (5090) / {wk_t4:6.1f} wk (T4)")
        print(f"  {bname:62s} {n_ev:5.0f} ev | " + " | ".join(row))
    print()
    # OpenFOAM verifier on a 128 GB / 64-core machine, primal only
    for cells, iters, label in ((3e6, 3000, "wing, SA/SST, 3 M cells"), (8e6, 3000, "wing + wheel, 8 M cells"), (2.5e7, 4000, "half car, 25 M cells")):
        core_h = cells * iters / 4e4 / 3600
        print(f"OpenFOAM primal verifier ({label}): {core_h:6.0f} core-h = {core_h/64:5.1f} h on 64 cores; memory ~{cells*1.5/1e6:5.1f} GB; 32 paired realisations = {32*core_h/64/24:4.1f} machine-days")
    print()
    print("Hardware: RTX 5090 32 GB ~ 0.4-0.6 M JPY; a 64-core/128 GB CPU box ~ 1.5-3 M JPY (verifier); Kaggle GPU is free at ~30 h/week; no cloud CPU, no DAFoam.")


if __name__ == "__main__":
    main()
