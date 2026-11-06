"""GEN-01 cost model under the realistic constraint set by the user on 2026-11-01: ONE machine with 128 GB RAM
(no cloud by default, no DAFoam). The budget is machine time, not dollars.

Toolchain assumed: OpenFOAM primal + ESI continuous adjoint (adjointOptimisationFoam), which holds roughly one extra
set of fields per adjoint response (memory ~2-3x the primal), instead of a discrete adjoint that stores a Jacobian
(DAFoam explicit 113-200 kB/cell: ~0.6-1.1 M cells in 128 GB, so excluded here). Memory anchors are assumptions
to be measured in ADJ-00 (the FID-01 V3 case_result records RSS per stage; see the plan).
Throughput anchor: ~25 core-s per million cells per SIMPLE iteration (4e4 cell-it/s/core); range 2.5e4-6e4.
"""
from __future__ import annotations

RAM_GIB = 128
PRIMAL_KB = 2.0           # simpleFoam + SA/SST, per cell, during the solve (assumption; OpenFOAM rule of thumb 1-2 kB/cell)
SNAPPY_KB = 4.0           # snappyHexMesh peak per final cell (assumption; meshing is the memory peak, done once per remesh)
ADJ_FACTOR_MEM = 2.5      # continuous adjoint fields + sensitivities, relative to the primal
ADJ_FACTOR_TIME = (1.0, 2.0)
RATE = (2.5e4, 6.0e4)
EXTRA_PRIMALS = 1.5
CARTER = 2
CORES = (32, 64)

STAGES = {
    # cells, iters, responses, OPs, optimiser iterations, lean verification primal-equivalents per OP
    "LOOP-3D-00 (coarse wing)": (1.0e6, 2500, 2, 1, 10, 40),
    "WING-3D-01 rear wing": (3.0e6, 3000, 2, 2, 30, 100),
    "WING-3D-01b topology epochs (+6 events)": (3.0e6, 3000, 2, 2, 30, 100 + 6 * (5 + 16)),
    "WW-01 front wing + tyre": (8.0e6, 3000, 2, 2, 30, 100),
    "CAR-01 installed component campaigns (3 x 10 M cells)": (1.0e7, 3500, 2, 1, 20, 80),
    "CAR-01 whole half car 25 M (one OP)": (2.5e7, 4000, 3, 1, 20, 80),
}


def fits(cells):
    peak = max(cells * SNAPPY_KB, cells * PRIMAL_KB * ADJ_FACTOR_MEM) / 2**20
    return peak, peak <= RAM_GIB


def primal_h(cells, iters, rate, cores):
    return cells * iters / rate / 3600.0 / cores


def main():
    print(f"RAM {RAM_GIB} GiB; peak memory = max(snappy {SNAPPY_KB} kB/cell, adjoint {PRIMAL_KB}x{ADJ_FACTOR_MEM} kB/cell)")
    print(f"{'stage':54s} {'cells':>8s} {'peak GiB':>8s} {'fits':>4s} | {'primal h (32c)':>14s} {'days/OP (32c)':>13s} {'days total (32c)':>16s} | {'days total (64c)':>16s}")
    tot = {c: [0.0, 0.0] for c in CORES}
    for name, (cells, iters, resp, ops, it, verif) in STAGES.items():
        peak, ok = fits(cells)
        out = []
        for cores in CORES:
            lo_hi = []
            for rate, adj in ((RATE[1], ADJ_FACTOR_TIME[0]), (RATE[0], ADJ_FACTOR_TIME[1])):
                p = primal_h(cells, iters, rate, cores)
                per_iter = p * (1 + resp * adj + EXTRA_PRIMALS + CARTER)
                days_op = (it * per_iter + verif * p) / 24
                lo_hi.append(days_op)
            out.append(lo_hi)
            if ok:
                tot[cores][0] += ops * lo_hi[0]
                tot[cores][1] += ops * lo_hi[1]
        p32 = (primal_h(cells, iters, RATE[1], 32), primal_h(cells, iters, RATE[0], 32))
        print(f"{name:54s} {cells:8.1e} {peak:8.0f} {'yes' if ok else 'NO':>4s} | {p32[0]:5.1f}..{p32[1]:<7.1f} {out[0][0]:5.0f}..{out[0][1]:<6.0f} {ops*out[0][0]:6.0f}..{ops*out[0][1]:<8.0f} | {ops*out[1][0]:6.0f}..{ops*out[1][1]:<8.0f}")
    for cores in CORES:
        print(f"TOTAL machine-days on {cores} cores for every stage that fits (serial): {tot[cores][0]:.0f}..{tot[cores][1]:.0f}  (= {tot[cores][0]/30:.1f}..{tot[cores][1]/30:.1f} months)")
    print()
    print("Kaggle CPU offload (free): 5 sessions x 4 cores x 12 h/day = 240 core-h/day; a 3 M-cell primal is ~16-40 core-h,")
    print("  so the verification ensembles of the wing stages (<= ~3 M cells, ~30 GB RAM per session) can run there at ~6-15 primals/day.")
    print("Hardware: a 64-core / 128-256 GB workstation is roughly 1.5-3 M JPY one-time; the Mac (Rosetta) is 3-5x slower per core.")
    print("Control arm (LB K=16 FD, 30 it, 1 OP, 3 M cells) on 32 cores: "
          f"{30*33*primal_h(3e6,3000,RATE[1],32)/24:.0f}..{30*33*primal_h(3e6,3000,RATE[0],32)/24:.0f} days -> not affordable on one machine; K=8, 15 it: "
          f"{15*17*primal_h(3e6,3000,RATE[1],32)/24:.0f}..{15*17*primal_h(3e6,3000,RATE[0],32)/24:.0f} days")


if __name__ == "__main__":
    main()
