"""Back-of-envelope cost model for an adjoint-RANS whole-vehicle optimisation campaign (GEN-01 plan, 2026-11-01).

Every number is an assumption the plan states; change the dicts and rerun. Sources of the anchors:
- simpleFoam throughput: SPUMA (arXiv 2512.22215) CPU table gives ~25 core-s per million cells per SIMPLE iteration
  on Sapphire Rapids (= 4.0e4 cell-iterations/s/core); the range below brackets older hardware and poorer scaling.
- adjoint/primal runtime: DAFoam 1.7-2.2 at 10.1 M cells (He et al. 2020); continuous adjoint ~1-1.5; SU2 anecdotal ~2-3.
- memory: DAFoam explicit-Jacobian adjoint 1146 GB vs 73 GB primal at 10.1 M cells (He et al. 2020) = 113 kB/cell vs 7.2 kB/cell;
  the newer Jacobian-free mode is NOT in that paper and must be measured in ADJ-00. SU2 ~10x primal (forum, anecdotal).
- BMW M4 GT4 (Antonau et al. 2022): 114.7 M cells, 14 iterations, 120,960 CPU h -> ~75 core-h per M cells per iteration.
- cloud: AWS hpc7a.96xlarge 192 cores, 768 GiB, ~7.2 USD/h on-demand (0.038 USD/core-h); Azure HBv4 spot ~1.33 USD/h for 176 cores.
"""
from __future__ import annotations

CASES = {
    # name: (cells, steady iterations to the force plateau, responses with an adjoint)
    "2D section (LOOP-2D-01, xfine30)": (5.0e4, 5000, 2),
    "front wing + endplates (WING-3D-01)": (3.0e6, 3000, 2),
    "wing + wheel + ground (WW-01)": (8.0e6, 3000, 2),
    "half car, wall functions (CAR-01)": (2.5e7, 4000, 3),
    "half car, resolved layers": (6.0e7, 5000, 3),
}
RATE_LOW, RATE_HIGH = 2.5e4, 6.0e4           # cell-iterations / s / core (anchor 4.0e4)
ADJ_LOW, ADJ_HIGH = 1.5, 3.0                 # one adjoint solve vs one primal
ITERS_PER_OPT = 30                           # optimiser iterations per campaign (BMW 14, He et al. 21)
EXTRA_PRIMALS = 1.5                          # line search / rejected steps per iteration
PRICE = 0.038                                # USD per core-h on-demand (hpc7a); spot ~0.4x
CELLS_PER_CORE = 5.0e4                       # strong-scaling floor used for wall-clock
NODE_CORES, NODE_GIB = 192, 768
MEM_PRIMAL_KB, MEM_ADJ_EXPLICIT_KB, MEM_SU2_FACTOR = 7.2, 113.0, 10.0


def core_h(cells, iters, rate):
    return cells * iters / rate / 3600.0


def main():
    hdr = f"{'case':40s} {'cells':>8s} {'primal core-h':>16s} {'gradient core-h':>17s} {'campaign core-h':>18s} {'nodes(192c)':>11s} {'wall days':>11s} {'USD on-demand':>14s}"
    print(hdr)
    for name, (cells, iters, n_resp) in CASES.items():
        p_lo, p_hi = core_h(cells, iters, RATE_HIGH), core_h(cells, iters, RATE_LOW)
        g_lo, g_hi = p_lo * (1 + n_resp * ADJ_LOW), p_hi * (1 + n_resp * ADJ_HIGH)
        c_lo, c_hi = ITERS_PER_OPT * (g_lo + EXTRA_PRIMALS * p_lo), ITERS_PER_OPT * (g_hi + EXTRA_PRIMALS * p_hi)
        cores = min(4 * NODE_CORES, max(4, cells / CELLS_PER_CORE))
        nodes = max(1, round(cores / NODE_CORES))
        wall = (c_lo / cores / 24, c_hi / cores / 24)
        print(f"{name:40s} {cells:8.1e} {p_lo:7.0f}..{p_hi:<8.0f} {g_lo:7.0f}..{g_hi:<9.0f} {c_lo:8.0f}..{c_hi:<9.0f} {nodes:11d} {wall[0]:4.1f}..{wall[1]:<6.1f} {c_lo*PRICE:6.0f}..{c_hi*PRICE:<7.0f}")
    print()
    print("Memory (GiB) per case: primal / DAFoam explicit-Jacobian adjoint / SU2 (~10x primal); nodes of 768 GiB for the explicit adjoint")
    for name, (cells, _, _) in CASES.items():
        p = cells * MEM_PRIMAL_KB / 2**20
        a = cells * MEM_ADJ_EXPLICIT_KB / 2**20
        s = p * MEM_SU2_FACTOR
        print(f"  {name:40s} {p:8.1f} {a:9.1f} {s:8.1f}   nodes {max(1, -(-a // NODE_GIB)):.0f}")
    print()
    bmw = 114.7e6 / 1e6 * 75 * 30
    print(f"BMW anchor (75 core-h per M cells per iteration): half car 2.5e7 cells x 30 iterations = {2.5e7/1e6*75*30:,.0f} core-h = {2.5e7/1e6*75*30*PRICE:,.0f} USD; full BMW mesh 30 it = {bmw:,.0f} core-h")
    print(f"Local Mac (8 cores): half-car primal 2.5e7 x 4000 at 4e4 = {core_h(2.5e7, 4000, 4e4)/8/24:.1f} days wall; front wing 3e6 x 3000 = {core_h(3e6, 3000, 4e4)/8:.1f} h wall")
    for n in (3, 10, 30, 100, 1000, 10000):
        print(f"quadratic RS with n={n:6d} variables needs {(n + 1) * (n + 2) // 2:10d} primals; reduced-basis centred FD needs 2K; adjoint needs 1 + n_resp x (1.5..3)")


if __name__ == "__main__":
    main()
