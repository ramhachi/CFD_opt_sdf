"""Cost model for the GEN-01 adjoint-RANS optimisation stages (plan rev 1, 2026-11-01).

Rev 1 prices NODE-HOURS (nodes rent whole; every hpc7a size costs the same), multiplies by operating points
and responses, adds the per-iterate Carter check, the noise ensembles, the FD strong-condition test, the
verification runs and a development factor, and prices the reduced-basis fallback and the control arm.
Every number is an assumption the plan states. Anchors:
- simpleFoam throughput ~25 core-s per million cells per SIMPLE iteration (SPUMA, arXiv 2512.22215; = 4.0e4
  cell-it/s/core); range 2.5e4-6e4.
- adjoint/primal runtime: DAFoam 1.7-2.2 (He et al. 2020, explicit Jacobian, structured mesh); range 1.5-3.
- adjoint memory: 113 kB/cell (He 2020 explicit) to 200 kB/cell (DAFoam FAQ sizing rule 2 GB per 10,000 cells);
  the Jacobian-free default of DAFoam v5 is unmeasured and is an ADJ-00a measurement. Primal 7.2 kB/cell.
- node: AWS hpc7a.96xlarge, 192 cores, 768 GiB, 7.20 USD/h on-demand (aggregator price; no Spot for hpc7a).
  Azure HB176rs_v4 Spot ~1.33-1.74 USD/h exists but is evictable.
- BMW M4 GT4 (Antonau et al. 2022): 114.7 M cells, 14 iterations, 120,960 CPU h (~75 core-h per M cells per iteration).
"""
from __future__ import annotations
import math

NODE_CORES, NODE_GIB, NODE_USD_H = 192, 768, 7.20
RATE = (2.5e4, 6.0e4)            # cell-iterations / s / core (low = slow, high = fast)
ADJ = (1.5, 3.0)                 # adjoint solve / primal solve
MEM_PRIMAL_KB = 7.2
MEM_ADJ_KB = (113.0, 200.0)      # explicit-Jacobian range; Jacobian-free unmeasured
CELLS_PER_CORE = 2.0e4           # strong-scaling floor for the wall-clock estimate (DAFoam FAQ 1e4, OHC-1 practical limit ~1e4; efficiency loss is in RATE)
DEV_FACTOR = 1.5                 # development, debugging and rejected runs on top of the registered campaign
EXTRA_PRIMALS = 1.5              # line search / rejected trials per optimiser iteration
CARTER_CHECK_PRIMALS = 2         # central FD along g at every accepted iterate (plan §3.4)
ENSEMBLE_RUNS = 32               # sigma_claim: 16 remesh realisations of parent + 16 of final
FD_STRONG_K = 16                 # K Gaussian directions x 2 central primals, once per stage per OP
URANS_EQUIV = 20                 # one URANS verification ~ 20 primal-equivalents per OP (parent + final)
OTHER_MODEL_RUNS = 4             # parent + final x 2 models
OTHER_FAMILY_RUNS = 16           # parent + final x 8 realisations on a second mesh family

STAGES = {
    # cells, steady iterations, responses with adjoint, operating points, optimiser iterations, DDES verification runs
    "LOOP-3D-00 (coarse wing, exploratory)": dict(cells=1.0e6, iters=2500, resp=2, ops=1, it=10, ddes=0),
    "WING-3D-01 (rear wing)": dict(cells=3.0e6, iters=3000, resp=3, ops=2, it=30, ddes=0),
    "WW-01 (front wing + wheel)": dict(cells=8.0e6, iters=3000, resp=3, ops=2, it=30, ddes=0),
    "CAR-01 (half car)": dict(cells=2.5e7, iters=4000, resp=4, ops=3, it=30, ddes=2),
}
CAPS_USD = {"LOOP-3D-00 (coarse wing, exploratory)": 1500, "WING-3D-01 (rear wing)": 8000, "WW-01 (front wing + wheel)": 15000, "CAR-01 (half car)": 60000}


def primal_core_h(cells, iters, rate):
    return cells * iters / rate / 3600.0


def nodes_for(cells, mem_adj_kb):
    by_compute = math.ceil(cells / CELLS_PER_CORE / NODE_CORES)
    by_memory = math.ceil(cells * mem_adj_kb / 2**20 / NODE_GIB)
    return max(1, by_compute, by_memory), by_memory


def node_hours(core_h, cells, nodes):
    # cores actually busy on the solve; the rest of the node is paid for anyway
    busy = min(cells / CELLS_PER_CORE, nodes * NODE_CORES)
    return core_h / busy * nodes


def stage_cost(s, rate, adj, mem_adj_kb):
    p = primal_core_h(s["cells"], s["iters"], rate)
    per_iter = p * (1 + s["resp"] * adj + EXTRA_PRIMALS + CARTER_CHECK_PRIMALS)
    campaign = s["it"] * per_iter
    oneoff = p * (ENSEMBLE_RUNS + 2 * FD_STRONG_K + URANS_EQUIV + OTHER_MODEL_RUNS + OTHER_FAMILY_RUNS)
    ddes = s["ddes"] * 50 * p
    core_h = s["ops"] * (campaign + oneoff) + ddes
    nodes, by_mem = nodes_for(s["cells"], mem_adj_kb)
    nh = node_hours(core_h, s["cells"], nodes)
    return dict(primal=p, core_h=core_h, nodes=nodes, by_mem=by_mem, node_h=nh, usd=nh * NODE_USD_H * DEV_FACTOR, wall_days=nh / nodes / 24)


def fallback_cost(s, rate, K=16):
    # reduced-basis centred FD: 2K + 1.5 primals per iteration, same one-offs, one OP, primal memory only
    p = primal_core_h(s["cells"], s["iters"], rate)
    core_h = s["it"] * p * (2 * K + EXTRA_PRIMALS) + p * (ENSEMBLE_RUNS + URANS_EQUIV + OTHER_MODEL_RUNS + OTHER_FAMILY_RUNS)
    nodes = max(1, math.ceil(s["cells"] / CELLS_PER_CORE / NODE_CORES))
    nh = node_hours(core_h, s["cells"], nodes)
    return nh * NODE_USD_H * DEV_FACTOR


def main():
    print(f"{'stage':40s} {'cells':>8s} {'OPs':>3s} {'nodes(mem)':>10s} {'core-h lo..hi':>22s} {'node-h lo..hi':>18s} {'wall d lo..hi':>14s} {'USD x1.5 lo..hi':>18s} {'cap':>7s}")
    for name, s in STAGES.items():
        lo = stage_cost(s, RATE[1], ADJ[0], MEM_ADJ_KB[0])
        hi = stage_cost(s, RATE[0], ADJ[1], MEM_ADJ_KB[1])
        flag = "" if hi["usd"] <= CAPS_USD[name] else "  <-- cap below the high bound"
        print(f"{name:40s} {s['cells']:8.1e} {s['ops']:3d} {lo['nodes']:4d}({hi['by_mem']:2d}) {lo['core_h']:10.0f}..{hi['core_h']:<11.0f} {lo['node_h']:8.0f}..{hi['node_h']:<9.0f} {lo['wall_days']:6.1f}..{hi['wall_days']:<7.1f} {lo['usd']:8.0f}..{hi['usd']:<9.0f} {CAPS_USD[name]:7d}{flag}")
    print()
    w = STAGES["WING-3D-01 (rear wing)"]
    print(f"Reduced-basis fallback / control arm on the WING-3D-01 case, K=16, 1 OP, 30 iterations: USD {fallback_cost(w, RATE[1]):,.0f}..{fallback_cost(w, RATE[0]):,.0f} (x1.5 dev factor)")
    print(f"Same with K=30: USD {fallback_cost(w, RATE[1], 30):,.0f}..{fallback_cost(w, RATE[0], 30):,.0f}")
    print()
    print("Memory (GiB): primal / adjoint 113 kB/cell / adjoint 200 kB/cell; nodes of 768 GiB at 200 kB/cell")
    for name, s in STAGES.items():
        c = s["cells"]
        print(f"  {name:40s} {c*MEM_PRIMAL_KB/2**20:7.0f} {c*MEM_ADJ_KB[0]/2**20:8.0f} {c*MEM_ADJ_KB[1]/2**20:8.0f}   nodes {math.ceil(c*MEM_ADJ_KB[1]/2**20/NODE_GIB)}")
    print()
    print(f"BMW anchor: 2.5e7 cells x 30 it x 75 core-h/Mcell = {2.5e7/1e6*75*30:,.0f} core-h = {2.5e7/1e6*75*30/NODE_CORES*NODE_USD_H:,.0f} USD on whole nodes (one OP, no verification)")
    print(f"ADJ-00a/b and CLOUD-ENV-01: 1 node x ~120 node-h = {120*NODE_USD_H:,.0f} USD per 120 h; cap 3,000 USD = {3000/NODE_USD_H:,.0f} node-h")
    for n in (3, 10, 30, 100, 1000, 10000):
        print(f"quadratic RS with n={n:6d} variables needs {(n + 1) * (n + 2) // 2:10d} primals; reduced-basis centred FD 2K; adjoint 1 + resp x (1.5..3)")


if __name__ == "__main__":
    main()
