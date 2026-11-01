"""GEN-01 rev 3.1 cost model: WaterLily (GPU, fixed grid) as the main line, OpenFOAM primal (no adjoint) as the verifier.

Budgets are GPU-hours (and rental USD / purchase JPY), plus verifier machine-days. Anchors from this repository (Kaggle T4,
WaterLily 1.8.0): flow_32 1.38 M cells, 13,549 steps, 342 s and flow_48 4.67 M cells, 27,372 steps, 2,267 s -> 5.5e7 cell-steps/s
(~18 ns per cell-step). Published: H100 1.57 ns/cell-step (arXiv 2407.16032); WaterLily is memory-bandwidth bound, so GPU speed is
scaled by bandwidth (research E; to be measured on a rented card before any purchase): T4 1x, Kaggle T4x2 (both GPUs) 2x,
RTX 5070 Ti / 5080 ~3x, RTX 4090 ~3.5x, RTX 5090 ~6x, A100 ~7x. Memory ~128-134 B/cell.
Prices (2026-11-01, research E and review W-S6; approximate): rental 5090 0.35-1.19 USD/h, 4090 0.3-0.9, A100 1.2-1.8;
purchase 5090 > 1.0 M JPY (Sept 2026, scarce), 5080 ~240 k JPY, 5070 Ti ~180 k JPY; electricity ~17 k JPY/month at 24/7 (unverified).
OpenFOAM verifier: FID-01 V3 1.46 M cells, simpleFoam 27,793 s for 4,548 iterations on the Mac (4 cpus) -> ~6e4 cell-it/s/core;
memory ~1.5 kB/cell. Unsteady laminar (pimpleFoam) same-Re check: ~800 core-h per run (review W-S8 estimate).
"""
from __future__ import annotations

T4_RATE = 5.5e7
GPU = {"T4 (Kaggle, 1 GPU)": 1.0, "T4x2 (Kaggle, both)": 2.0, "RTX 5070Ti/5080": 3.0, "RTX 5090": 6.0}
RENT_USD_H = {"RTX 4090": (0.30, 0.90), "RTX 5090": (0.35, 1.19), "A100 80GB": (1.2, 1.8)}
BYTES_PER_CELL = 134
CFL = 0.5

CASES = {
    # (nx, ny, nz) at the stated h; chord in cells; convective window and burn-in in c/U units
    "TOPO-2D-00: 2D section, 1-3 elements, Re_c 3e3 (h c/120)": dict(n=(1200, 600, 1), c_cells=120, window=200, burn=60),
    "front wing + ground, h 5 mm (Re_c ~3e3)": dict(n=(300, 200, 120), c_cells=60, window=150, burn=50),
    "front wing + ground, h 3.3 mm (R3 confirmation, same Re)": dict(n=(450, 300, 180), c_cells=90, window=150, burn=50),
    "front wing + ground, h 2.5 mm (Re_c ~1e4 probe)": dict(n=(600, 400, 240), c_cells=120, window=200, burn=60),
    "sidepod + wheel, h 10 mm (Re_L ~3e3)": dict(n=(300, 160, 160), c_cells=50, window=150, burn=50),
    "coarse half car context, h 25 mm": dict(n=(200, 96, 72), c_cells=12, window=120, burn=80),
}
BUDGETS = {
    "SCREEN-type: 8-mode RS 90 + events 6x21 + fixed-count arm 90 + verification 32": 90 + 126 + 90 + 32,
    "reduced-basis sep-CMA-ES/DE, K=15, 30xD = 450 + events 126 + fixed-count 90 + verification 32": 450 + 126 + 90 + 32,
    "reduced-basis FD trust region, K=15, 30 iterations (945) + events + arms": 945 + 126 + 90 + 32,
}
PROGRAMME_5090_HOURS = (500, 650)   # review W-S6 estimate: STAGE-0, MW-01 with fixed-count arm, h 2.5 mm probes, GRAD-00, SP-01


def run(case):
    nx, ny, nz = case["n"]
    cells = nx * ny * nz
    steps = (case["window"] + case["burn"]) * case["c_cells"] / CFL
    return cells, steps, cells * steps, cells * BYTES_PER_CELL / 1e9


def main():
    print(f"{'case':62s} {'cells':>8s} {'steps':>7s} {'GB':>5s} | " + " | ".join(f"{g:>19s}" for g in GPU))
    per = {}
    for name, case in CASES.items():
        cells, steps, cs, gb = run(case)
        per[name] = {g: cs / (T4_RATE * f) / 3600 for g, f in GPU.items()}
        print(f"{name:62s} {cells:8.1e} {steps:7.0f} {gb:5.1f} | " + " | ".join(f"{per[name][g]:14.2f} h/ev" for g in GPU))
    print()
    fw = "front wing + ground, h 5 mm (Re_c ~3e3)"
    print("MW-01 on the h 5 mm front wing: GPU-hours and calendar per budget line")
    print(f"  {'budget line':92s} {'evals':>5s} | {'T4x2 quota-h (weeks @30h)':>26s} | {'5090 hours (days 24/7)':>22s} | {'5090 rental USD':>15s}")
    for bname, n in BUDGETS.items():
        h_t4x2 = per[fw]["T4x2 (Kaggle, both)"] * n
        h_5090 = per[fw]["RTX 5090"] * n
        rent = (h_5090 * RENT_USD_H["RTX 5090"][0], h_5090 * RENT_USD_H["RTX 5090"][1])
        print(f"  {bname:92s} {n:5d} | {h_t4x2:12.0f} h ({h_t4x2/30:4.1f} wk) | {h_5090:9.0f} h ({h_5090/24:4.1f} d) | {rent[0]:5.0f}..{rent[1]:<5.0f}")
    print()
    lo, hi = PROGRAMME_5090_HOURS
    print(f"Programme total (review W-S6 estimate): {lo}-{hi} RTX-5090-hours = rental {lo*RENT_USD_H['RTX 5090'][0]:.0f}..{hi*RENT_USD_H['RTX 5090'][1]:.0f} USD; "
          f"on T4x2 {lo*3:.0f}-{hi*3:.0f} quota-hours = {lo*3/30:.0f}-{hi*3/30:.0f} weeks; on a 5080 {lo*2:.0f}-{hi*2:.0f} h = {lo*2/24:.0f}-{hi*2/24:.0f} days 24/7")
    print("Purchase (JPY, 2026-09/10): 5090 > 1,000k (scarce) | 5080 ~240k | 5070 Ti ~180k | plus host PC with 128 GB RAM; electricity ~17k/month at 24/7.")
    print()
    for cells, iters, label in ((3e6, 3000, "wing RANS primal, 3 M cells"), (8e6, 3000, "wing + wheel RANS, 8 M cells")):
        core_h = cells * iters / 4e4 / 3600
        print(f"OpenFOAM verifier ({label}): {core_h:5.0f} core-h = {core_h/10:5.1f} h on the Mac (10 cores) / {core_h/64:4.1f} h on 64 cores; 16 pairs = {32*core_h/10/24:4.1f} Mac-days")
    print(f"Same-Re unsteady laminar check (pimpleFoam, ~800 core-h per run): 4 pairs = {8*800/10/24:4.1f} Mac-days / {8*800/64/24:4.1f} days on 64 cores")


if __name__ == "__main__":
    main()
