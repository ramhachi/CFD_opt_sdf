"""Cost model for the GEN-01 programme (plan rev 2, 2026-11-01).

Rev 2 models every stage the plan names (round-2 review R-NG7), prices NODE-HOURS, multiplies by operating points
(OPs) and responses, and adds: the per-iterate Carter check, the in-study sigma phases, the epsilon ladder of the
strong-condition test, the second-base-mesh gradient at checkpoints, the other-build and other-code verification
tiers, the control arm, the held-out genericity geometry, meshing, storage/idle and a development factor.
Every number is an assumption the plan states. Anchors:
- simpleFoam ~25 core-s per million cells per SIMPLE iteration (SPUMA, arXiv 2512.22215) = 4.0e4 cell-it/s/core; range 2.5e4-6e4.
- adjoint/primal runtime 1.5-3 (DAFoam 1.7-2.2 at 10.1 M cells, He et al. 2020, explicit Jacobian, structured mesh).
- adjoint memory 113 kB/cell (He 2020 explicit) to 200 kB/cell (DAFoam FAQ 2 GB per 10,000 cells); Jacobian-free unmeasured.
- node: AWS hpc7a.96xlarge, 192 cores, 768 GiB, 7.20 USD/h on-demand (aggregator price; no Spot for hpc7a).
- BMW M4 GT4 (Antonau et al. 2022): ~75 core-h per M cells per iteration.
- strong-scaling floor 2e4 cells/core (DAFoam FAQ 1e4; OHC-1 practical limit ~1e4); efficiency loss is inside RATE.
"""
from __future__ import annotations
import math

NODE_CORES, NODE_GIB, NODE_USD_H = 192, 768, 7.20
RATE = (2.5e4, 6.0e4)
ADJ = (1.5, 3.0)
MEM_ADJ_KB = (113.0, 200.0)
CELLS_PER_CORE = 2.0e4
DEV = 1.5                 # development, debugging, rejected runs
MESH_FRAC = 0.03          # snappyHexMesh with layers, per mesh, as a fraction of one primal; ~1 mesh per 6 primals
STORAGE_IDLE = 0.05       # storage, transfer, idle nodes
EXTRA_PRIMALS = 1.5       # line search / rejected trials per iteration
CARTER = 2                # central FD along g at every accepted iterate
K = 16                    # strong-condition directions
EPS_LADDER = 3            # epsilon values per direction (item 7)
SIGMA_PHASE = 16          # in-study sigma_step/sigma_claim phase per OP (states not reused)
ENSEMBLE = 32             # sigma_claim: 16 remesh realisations of parent + 16 of final, per OP
CHECKPOINTS = 3           # second-base-mesh gradient at checkpoints
URANS_EQ = 20             # one URANS verification ~ 20 primal-equivalents per OP
OTHER_MODEL = 4           # parent + final x 2 models
OTHER_FAMILY = 16         # parent + final x 8 realisations, same build, other mesh family
OTHER_BUILD = 16          # parent + final x 8 realisations, other build
OTHER_CODE = 16           # parent + final x 8 realisations, other code (SU2), priced as primals


def p_core_h(cells, iters, rate):
    return cells * iters / rate / 3600.0


def nodes_for(cells, mem_kb):
    return max(1, math.ceil(cells / CELLS_PER_CORE / NODE_CORES), math.ceil(cells * mem_kb / 2**20 / NODE_GIB))


def node_h(core_h, cells, nodes):
    busy = min(cells / CELLS_PER_CORE, nodes * NODE_CORES)
    return core_h / busy * nodes


def usd(core_h, cells, mem_kb):
    n = nodes_for(cells, mem_kb)
    nh = node_h(core_h, cells, n)
    return nh * NODE_USD_H * DEV * (1 + STORAGE_IDLE), n, nh


def campaign(cells, iters, resp, ops, it, rate, adj):
    """Registered adaptive campaign at one stage: returns core-h."""
    p = p_core_h(cells, iters, rate)
    per_iter = p * (1 + resp * adj + EXTRA_PRIMALS + CARTER)
    per_op = (it * per_iter
              + p * (SIGMA_PHASE + ENSEMBLE + 2 * K * EPS_LADDER + URANS_EQ + OTHER_MODEL + OTHER_FAMILY + OTHER_BUILD + OTHER_CODE)
              + CHECKPOINTS * p * (1 + resp * adj))
    meshes = (it * (1 + EXTRA_PRIMALS) / 6 + ENSEMBLE + OTHER_FAMILY + OTHER_BUILD) * MESH_FRAC * p
    return ops * (per_op + meshes)


def fd_arm(cells, iters, ops, it, rate, k=K):
    p = p_core_h(cells, iters, rate)
    return ops * (it * p * (2 * k + EXTRA_PRIMALS) + p * (SIGMA_PHASE + ENSEMBLE + URANS_EQ + OTHER_MODEL + OTHER_FAMILY))


def main():
    rows = []
    # name, cells, iters, resp, ops, it, memory mode, extra core-h function
    rows.append(("CLOUD-ENV-01 (40 node-h of reruns and image builds)", lambda r, a: (40 * NODE_CORES, NODE_CORES * CELLS_PER_CORE, 7.2)))
    rows.append(("ADJ-00a (3 candidates, case 4 + build equivalence)", lambda r, a: (
        3 * (p_core_h(3e6, 3000, r) * (1 + 2 * a)) + 2 * 9 * p_core_h(3e6, 3000, r), 3e6, MEM_ADJ_KB[1 if a > 2 else 0])))
    rows.append(("ADJ-00b (3 candidates x cases 1,3,4; eps ladder, 2 base meshes)", lambda r, a: (
        3 * (2 * (p_core_h(3e6, 3000, r) * (1 + 2 * a)) + 2 * K * EPS_LADDER * p_core_h(3e6, 3000, r) + 40 * p_core_h(5e4, 5000, r)), 3e6, MEM_ADJ_KB[1 if a > 2 else 0])))
    rows.append(("EVAL-3D-01b (IFW: 3 models x 2 Re x 8 realisations, primal only)", lambda r, a: (48 * p_core_h(3e6, 3000, r), 3e6, 7.2)))
    rows.append(("LOOP-3D-00 (coarse wing, exploratory)", lambda r, a: (campaign(1e6, 2500, 2, 1, 10, r, a), 1e6, MEM_ADJ_KB[1 if a > 2 else 0])))
    rows.append(("LOOP-CAR-00 (coarse half car 5e6, primal + adjoint + shares)", lambda r, a: (p_core_h(5e6, 3000, r) * (3 + 2 * a), 5e6, MEM_ADJ_KB[1 if a > 2 else 0])))
    rows.append(("WING-3D-01 (rear wing, 2 OPs)", lambda r, a: (campaign(3e6, 3000, 3, 2, 30, r, a), 3e6, MEM_ADJ_KB[1 if a > 2 else 0])))
    rows.append(("WING-3D-01 control arm (LB K=16 FD, 2 OPs)", lambda r, a: (fd_arm(3e6, 3000, 2, 30, r), 3e6, 7.2)))
    rows.append(("WING-3D-01 installed check (half car x 16)", lambda r, a: (16 * p_core_h(2.5e7, 4000, r), 2.5e7, 7.2)))
    rows.append(("GENERICITY (held-out geometry 1e6, 5 iterations)", lambda r, a: (campaign(1e6, 2500, 2, 1, 5, r, a), 1e6, MEM_ADJ_KB[1 if a > 2 else 0])))
    rows.append(("WW-00a/b (parent scan 6 h/c x (steady + LTS + URANS), adjoint probe)", lambda r, a: (p_core_h(8e6, 3000, r) * (6 * (2 + URANS_EQ) + 3 * (1 + 2 * a)), 8e6, MEM_ADJ_KB[1 if a > 2 else 0])))
    rows.append(("WW-01 (front wing + wheel, 2 OPs)", lambda r, a: (campaign(8e6, 3000, 3, 2, 30, r, a), 8e6, MEM_ADJ_KB[1 if a > 2 else 0])))
    rows.append(("CAR-01 (half car, 3 OPs, + DDES pair)", lambda r, a: (campaign(2.5e7, 4000, 4, 3, 30, r, a) + 2 * 50 * p_core_h(2.5e7, 4000, r), 2.5e7, MEM_ADJ_KB[1 if a > 2 else 0])))

    print(f"{'stage':68s} {'nodes':>5s} {'node-h lo':>9s} {'node-h hi':>9s} {'USD lo':>8s} {'USD hi':>8s}")
    tot_lo = tot_hi = 0.0
    for name, f in rows:
        ch_lo, cells, mem_lo = f(RATE[1], ADJ[0])
        ch_hi, _, mem_hi = f(RATE[0], ADJ[1])
        u_lo, n_lo, nh_lo = usd(ch_lo, cells, mem_lo)
        u_hi, n_hi, nh_hi = usd(ch_hi, cells, mem_hi)
        tot_lo += u_lo
        tot_hi += u_hi
        print(f"{name:68s} {n_lo:2d}/{n_hi:<2d} {nh_lo:9.0f} {nh_hi:9.0f} {u_lo:8.0f} {u_hi:8.0f}")
    print(f"{'TOTAL compute (x1.5 dev, +5 % storage/idle)':68s} {'':5s} {'':9s} {'':9s} {tot_lo:8.0f} {tot_hi:8.0f}")
    print(f"{'TOTAL + 20 % reserve':68s} {'':5s} {'':9s} {'':9s} {tot_lo*1.2:8.0f} {tot_hi*1.2:8.0f}")
    wo_car_lo = tot_lo - usd(rows[-1][1](RATE[1], ADJ[0])[0], 2.5e7, MEM_ADJ_KB[0])[0]
    wo_car_hi = tot_hi - usd(rows[-1][1](RATE[0], ADJ[1])[0], 2.5e7, MEM_ADJ_KB[1])[0]
    print(f"{'TOTAL without CAR-01':68s} {'':5s} {'':9s} {'':9s} {wo_car_lo:8.0f} {wo_car_hi:8.0f}")
    print()
    print("Per-step noise floor anchor (T2-0c fine30, h/c 0.224, morph sigma_eff 0.00043 Cl = 0.033 %): paired 0.047 %, n=16 upper bound 0.067 %;")
    print("  k = 8 on sigma_step = 0.37-0.54 % of the objective per accepted step (best case); at h/c 0.134 (sigma_eff 0.0021, Cl 1.40) 1.7-2.4 %.")
    print("Claim margin anchor (paired 16-vs-16 remesh ensembles, one-sided 95 %): 1.645*sqrt(2/16)*sigma_claim = 0.58 sigma_claim = 0.12-0.52 % of Cl for sigma_claim 0.2-0.9 %.")
    print(f"BMW anchor: 2.5e7 cells x 30 it x 75 core-h/Mcell = {2.5e7/1e6*75*30:,.0f} core-h = {2.5e7/1e6*75*30/NODE_CORES*NODE_USD_H:,.0f} USD on whole nodes (one OP, no verification, no dev factor)")
    print(f"Local Mac (8 cores): half-car primal {p_core_h(2.5e7, 4000, 4e4)/8/24:.1f} days; rear-wing primal {p_core_h(3e6, 3000, 4e4)/8:.1f} h (and 172 GiB primal memory for the half car)")


if __name__ == "__main__":
    main()
