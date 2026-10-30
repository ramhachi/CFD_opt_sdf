#!/usr/bin/env python3
"""SCREEN-01 (#64, M3b-1) revision 1: the finite admissible pools on the v18 plate, the response-surface design, and the gated refinement step
`propose()` (surface -> constrained argmax -> local cloud -> gate every point -> proposals).  Solver-free geometry; no force is read here.
Registration: docs/screen01_registration_2026_10_30.md (rev. 1, §3, §5.3).  Reuses scripts/fid01/fid01_designs.py unchanged (joint analytic
builder, gate stack `work`, X1 export `_x1`).

Space (rev. 1): the fixed subset (pitch, camber, reflex), heave = 0, box u in [-1, 1] x [-1.5, 1] x [-1, 1], amplitude = u * A*.
Admissible = 13 GEOM-02 v2 gates (incl. R0) + P22-v2 + volume band + clearance (fid01_designs.work, unmeasured = fail) AND the r = 8 X1 export
gate (double + float32) AND the STL chain check |dV_STL/V - dV_SDF,smoothed/V| <= 0.01 against the parent STL.

Pools (scrambled Sobol, scipy qmc, u = lo + (hi - lo) x, amplitudes rounded to 1e-3):
  axial    the 6 states {m: +-A*_m} of the subset
  ref      the FID C1 downforce reference (camber -11.3, reflex -11.3; infeasible under drag non-increase, chain check only)
  manual   the drag-neutral hand-design ladder (camber -A* with a pitch or reflex trim sized from the visible linear ratios), first admissible = M
  rs       the design pool: 64 points (seed 20261030), extended by 64 while fewer than 12 admissible, at most 256
  rand3    the random-direction control: seed 20261033, consumed in sequence order until 19 admissible members or 512 points

    python scripts/screen01/screen01_pool.py gen
    python scripts/screen01/screen01_pool.py p0 --pools axial ref manual rs [rand3] --workers 4   # gate + X1 + chain check with the extension rules
    python scripts/screen01/screen01_pool.py design                                              # D-optimal 9 + 6 axial, no-intercept rank/cond
    python scripts/screen01/screen01_pool.py selfcheck                                           # propose() on a synthetic surface

Caches: work/screen01_pool_prescreen/rows/<name>.json, x1/<name>.json, stl/<name>.stl.  A cached gate row or X1 record is reused only when its `fingerprint`
equals `fingerprint()` (the SHA-256 over DEPENDENCIES: every repository module the gate stack imports and every data file it reads; source review 2026-10-31, Q1/B5),
an STL is read only when its SHA-256 equals the record's `stl_sha256`, and a row carrying `error` is never cached (Q7).  The 2026-10-30 caches carry no such key and
are not reused: the P0 re-validation before freeze 1 recomputes every member (registration §2 P0, §3.4).
Outputs: docs/evidence/screen01_2026_10_30/pool_prescreen_rev1/{pools.json,rows.jsonl,summary.json,design_check.json}.
"""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
import multiprocessing as mp
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts"), str(ROOT / "scripts/fid01")]
import fid01_designs as D  # noqa: E402

OUT = ROOT / "docs/evidence/screen01_2026_10_30/pool_prescreen_rev1"
WORK = ROOT / "work/screen01_pool_prescreen"
STL = WORK / "stl"
D.STL = STL   # module level: spawn workers re-import this module
# every repository file the admissibility decision depends on: the gate-stack import closure of fid01_designs.work / _x1 (observed on 2026-10-31, asserted by
# `selfcheck`) and the data files the stack reads; freeze 1 binds every one of them (REUSED of screen01_freeze.py must contain this list)
DEPENDENCIES = sorted(set(D.DEPENDENCIES) | {
    "scripts/fid01/fid01_designs.py", "scripts/fid01/fid01_build.py", "scripts/analyze_lowdim02a.py", "scripts/build_grid01_inputs.py", "scripts/build_lowdim01_inputs.py",
    "scripts/build_lowdim04a_inputs.py", "scripts/fd08_v2_campaign_io.py", "scripts/geom02_gradient_floor_diagnostic.py", "scripts/lowdim01_states.py", "scripts/lowdim04a_states.py",
    "scripts/prepare_kaggle_xfid_gridphase_x3.py", "scripts/register_geom02_profile.py", "scripts/register_opt01_v1.py", "scripts/step01_states.py", "scripts/unc01_build.py",
    "scripts/xfid45_round3_export.py", "scripts/xfid45_surface_round2_candidates.py",
    "src/cfd_sdf/__init__.py", "src/cfd_sdf/analytic_candidate_shapes.py", "src/cfd_sdf/config.py", "src/cfd_sdf/design/__init__.py", "src/cfd_sdf/design/genesis.py",
    "src/cfd_sdf/design/geometry_gates.py", "src/cfd_sdf/design/geometry_gates_v2.py", "src/cfd_sdf/design/sdf_state.py", "src/cfd_sdf/design/topology_policy.py",
    "src/cfd_sdf/design/topology_policy_research.py", "src/cfd_sdf/design/volume_semantics.py", "src/cfd_sdf/design/volume_semantics_v2.py", "src/cfd_sdf/design_state.py",
    "src/cfd_sdf/extraction_qualification.py", "src/cfd_sdf/fixed_grid_contract.py", "src/cfd_sdf/gradients/__init__.py", "src/cfd_sdf/gradients/base.py",
    "src/cfd_sdf/gradients/directional_comparison.py", "src/cfd_sdf/gradients/directional_fd.py", "src/cfd_sdf/grid.py", "src/cfd_sdf/grid01_contract.py",
    "src/cfd_sdf/lowdim02a_contract.py", "src/cfd_sdf/lowdim03_contract.py", "src/cfd_sdf/oracles/__init__.py", "src/cfd_sdf/oracles/base.py", "src/cfd_sdf/problem_spec.py",
    "src/cfd_sdf/runtime/__init__.py", "src/cfd_sdf/runtime/fingerprint.py", "src/cfd_sdf/sdf.py", "src/cfd_sdf/shape_feature_metrics.py",
    "docs/evidence/v18_genesis_2026_10_19/v18_parent.npz", "docs/evidence/v18_genesis_2026_10_19/v18_parent.phi_f4_fortran.raw", "docs/evidence/v18_genesis_2026_10_19/genesis.json",
    "docs/evidence/geom02_v17_gates_2026_10_14/geom02_resolved_research_policy.json", "docs/evidence/p22_v17_volume_semantics_bridge_2026_10_11/inputs/v17_baseline.npz",
    "docs/evidence/opt01a_stage_a_2026_10_15/inputs/opt01_v1_parent.npz"})


def fingerprint() -> str:
    """SHA-256 over DEPENDENCIES (path + file hash); the key of every cached gate row, X1 record and parent record."""
    h = hashlib.sha256()
    for rel in DEPENDENCIES:
        h.update(rel.encode() + hashlib.sha256((ROOT / rel).read_bytes()).digest())
    return h.hexdigest()


SUBSET = ("pitch", "camber", "reflex")
A_STAR = {"pitch": 3.1, "camber": 19.7, "reflex": 29.3}                        # MODE-01 v18 A* (deg, mm, mm)
BOX = {"pitch": (-1.0, 1.0), "camber": (-1.5, 1.0), "reflex": (-1.0, 1.0)}    # rev. 1: camber extended to -29.55 mm (every point gated)
N_RS0, N_RS_STEP, N_RS_MAX, MIN_ADM_RS = 64, 64, 256, 12
K_RAND, N_RAND_MAX, RAND_CHUNK = 19, 512, 16
SEED_RS, SEED_RAND, SEED_CLOUD = 20261030, 20261033, 20261032
CHAIN_TOL = 0.01
# visible flow_32 values used by the hand-design recipe (FID-01 analysis.json; M2): camber -19.7 drag +1.998e-3 N; pitch -0.7 drag -6.383e-3 N; reflex +29.3 drag -9.74e-3 N
VIS = {"camber_m19.7_drag": 1.998e-3, "pitch_m0.7_drag": 6.383e-3, "reflex_p29.3_drag": 9.74e-3}
# refinement defaults (registration §5.3)
M_D = 1.5e-3                       # registered response-surface drag target margin (N); registration §5.2 / §5.10
TARGETS = (1.0, 1.5, 2.0)          # multiples of m_D for the predicted-drag target of each proposal family
N_CLOUD, R_CLOUD, N_GRID = 256, 0.25, 81
GATE_CAP, N_PER_TARGET, N_PROP, GATE_ROUND = 36, 2, 4, 4


# ---- geometry helpers --------------------------------------------------------------------------------------------------------------------------
def u_to_spec(u) -> dict:
    return dict(sorted((m, round(float(x * A_STAR[m]), 3)) for m, x in zip(SUBSET, u) if round(float(x * A_STAR[m]), 3) != 0.0))   # sorted keys = the §3.2 state names


def spec_to_u(spec) -> list:
    return [spec.get(m, 0.0) / A_STAR[m] for m in SUBSET]


def x_to_u(x):
    lo = np.array([BOX[m][0] for m in SUBSET]); hi = np.array([BOX[m][1] for m in SUBSET])
    return lo + (hi - lo) * np.asarray(x, float)


def sobol_u(n, seed):
    from scipy.stats import qmc
    return x_to_u(qmc.Sobol(d=3, scramble=True, seed=seed).random(n))


def manual_ladder(m_d=M_D) -> list:
    """Drag-neutral hand design: camber -A* with a trim sized so that the visible linear ratios predict drag = -m_d; then a fixed fallback ladder."""
    tp = -round(0.7 * (VIS["camber_m19.7_drag"] + m_d) / VIS["pitch_m0.7_drag"], 2)
    tr = round(29.3 * (VIS["camber_m19.7_drag"] + m_d) / VIS["reflex_p29.3_drag"], 1)
    return [{"camber": -19.7, "pitch": tp}, {"camber": -19.7, "reflex": tr}, {"camber": -19.7, "pitch": round(0.75 * tp, 2)},
            {"camber": -19.7, "pitch": round(1.25 * tp, 2)}, {"camber": -19.7, "pitch": round(tp / 2, 2), "reflex": round(tr / 2, 1)}]


def gen() -> dict:
    pools = {"axial": [{m: s * A_STAR[m]} for m in SUBSET for s in (1, -1)], "ref": [{"camber": -11.3, "reflex": -11.3}],
             "manual": [], "rs": [u_to_spec(u) for u in sobol_u(N_RS_MAX, SEED_RS)], "rand3": [u_to_spec(u) for u in sobol_u(N_RAND_MAX, SEED_RAND)]}
    for md in (1.0e-3, 1.5e-3):            # both candidate margins gated at P0; the registration fixes one
        for s in manual_ladder(md):
            if s not in pools["manual"]:
                pools["manual"].append(s)
    rec = {"kind": "screen01_candidate_pools_rev1", "subset": SUBSET, "a_star": A_STAR, "box_u": BOX, "seeds": {"rs": SEED_RS, "rand3": SEED_RAND, "cloud": SEED_CLOUD},
           "rules": {"rs": f"first {N_RS0}, +{N_RS_STEP} while admissible < {MIN_ADM_RS}, max {N_RS_MAX}", "rand3": f"sequence order until {K_RAND} admissible or {N_RAND_MAX}",
                     "manual": "first admissible ladder entry (ladders for m_D 1.0e-3 then 1.5e-3)"},
           "generator": "scipy.stats.qmc.Sobol(d=3, scramble=True, seed).random(n); u = lo + (hi - lo) x; amplitude = u A*, round 3", "scipy": __import__("scipy").__version__,
           "pools": pools}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "pools.json").write_text(json.dumps(rec, indent=1, sort_keys=True) + "\n")
    return rec


# ---- admissibility pipeline (gate stack -> X1 -> chain check), cached per state name under fingerprint() -------------------------------------------
def _work(task):
    t0 = time.time()
    row = D.work(task)
    row["eval_wall_s"] = round(time.time() - t0, 1)
    return row


def _load_cache(dirname, fp) -> dict:
    """name -> cached record of `dirname` carrying this fingerprint and no `error`; everything else is ignored (recomputed)."""
    d = WORK / dirname
    d.mkdir(parents=True, exist_ok=True)
    out = {}
    for f in d.glob("*.json"):
        r = json.loads(f.read_text())
        if r.get("fingerprint") == fp and "error" not in r:
            out[r["name"]] = r
    return out


def gate_rows(specs: list, workers: int, log) -> dict:
    """name -> gate row for every spec; cached under fingerprint(); a row with `error` (the gate stack raised) is returned but never cached."""
    fp = fingerprint()
    cache = _load_cache("rows", fp)
    todo = [("p0", i, s) for i, s in enumerate(specs) if D.name(s) not in cache]
    if todo:
        with mp.get_context("spawn").Pool(min(workers, len(todo)), initializer=D._init) as pool:
            for r in pool.imap_unordered(_work, todo):
                r["fingerprint"] = fp
                if "error" not in r:
                    (WORK / "rows" / f"{r['name']}.json").write_text(json.dumps(r, sort_keys=True))
                cache[r["name"]] = r
                log(f"gate {r['name']} {r.get('all_pass', r.get('error'))} {r.get('failed_geom02')} {r.get('eval_wall_s')} s")
    return {D.name(s): cache[D.name(s)] for s in specs}


def stl_volume_file(name, stl_sha256) -> float | None:
    """Volume of the kept STL, read only when its bytes hash to the record's stl_sha256."""
    import fid01_build as FB
    f = STL / f"{name}.stl"
    if not f.exists():
        return None
    blob = f.read_bytes()
    return FB.stl_volume(blob) if hashlib.sha256(blob).hexdigest() == stl_sha256 else None


def _x1(task):
    n, rec = D._x1(task)
    rec["stl_volume_m3"] = stl_volume_file(n, rec["stl_sha256"]) if rec["pass"] else None
    return n, rec


def parent_x1() -> dict:
    """The parent's X1 record (STL SHA-256, volume), cached under fingerprint(); recomputed when the key or the STL bytes do not match."""
    fp, f = fingerprint(), WORK / "x1" / "v18__parent.json"
    if f.exists():
        rec = json.loads(f.read_text())
        if rec.get("fingerprint") == fp and stl_volume_file("v18__parent", rec["stl_sha256"]) == rec["stl_volume_m3"] and rec["stl_volume_m3"]:
            return rec
    import mode01_v18_prescreen as P18
    import unc01_u3_prepare as U
    s, _ = P18.load_parent()
    blob, rec = U.export(s, json.loads(U.PROFILE.read_text()))
    STL.mkdir(parents=True, exist_ok=True)
    (STL / "v18__parent.stl").write_bytes(blob)
    rec = {"name": "v18__parent", "pass": rec["pass"], "stl_sha256": rec["stl_sha256"], "triangles": rec["triangles"], "stl_volume_m3": stl_volume_file("v18__parent", rec["stl_sha256"]),
           "fingerprint": fp}
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(rec, sort_keys=True))
    return rec


def x1_rows(items: list, workers: int, log) -> dict:
    """(name, spec) -> X1 record with the STL volume; cached under fingerprint(); a passed record whose STL is missing or does not hash is recomputed."""
    fp = fingerprint()
    cache = {n: r for n, r in _load_cache("x1", fp).items() if not r.get("pass") or (r.get("stl_volume_m3") and stl_volume_file(n, r["stl_sha256"]) == r["stl_volume_m3"])}
    todo = [(n, s) for n, s in items if n not in cache]
    if todo:
        with mp.get_context("spawn").Pool(min(workers, len(todo)), initializer=D._init) as pool:
            for n, rec in pool.imap_unordered(_x1, todo):
                rec.update(name=n, fingerprint=fp)
                (WORK / "x1" / f"{n}.json").write_text(json.dumps(rec, sort_keys=True))
                cache[n] = rec
                log(f"x1 {n} {rec['pass']}")
    return {n: cache[n] for n, _ in items}


def chain_ok(row, x1rec, v_parent) -> bool | None:
    if not (row.get("all_pass") and x1rec and x1rec.get("pass") and x1rec.get("stl_volume_m3")):
        return None
    return abs((x1rec["stl_volume_m3"] / v_parent - 1.0) - row["volume_vs_parent"]) <= CHAIN_TOL


def admissible_rows(specs: list, workers: int, log) -> list:
    """Full admissibility for a list of specs: rows with admissible flag, X1 summary and the chain check."""
    rows = gate_rows(specs, workers, log)
    vp = parent_x1()["stl_volume_m3"]
    clean = [(n, r["spec"]) for n, r in rows.items() if r.get("all_pass")]
    x1 = x1_rows(clean, workers, log) if clean else {}
    out = []
    for s in specs:
        n = D.name(s)
        r, xr = rows[n], x1.get(n)
        ch = chain_ok(r, xr, vp)
        out.append({**r, "x1": None if xr is None else {k: xr.get(k) for k in ("pass", "stl_sha256", "triangles", "stl_volume_m3")},
                    "stl_volume_vs_parent": None if not xr or not xr.get("stl_volume_m3") else xr["stl_volume_m3"] / vp - 1.0, "chain_ok": ch,
                    "admissible": bool("error" not in r and r.get("all_pass") and xr and xr.get("pass") and ch)})   # an error row is not admissible and is counted (Q7)
    return out


def p0(pool_names: list, workers: int) -> dict:
    pools = json.loads((OUT / "pools.json").read_text())["pools"]
    logf = (OUT / "p0.log").open("a")
    def log(msg):
        print(msg, flush=True); logf.write(f"{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} {msg}\n"); logf.flush()
    t0 = time.time()
    rows, summ = [], {"kind": "screen01_p0_rev1", "pools": {}, "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    for p in pool_names:
        tp = time.time()
        specs = pools[p]
        if p == "rs":                                   # extension rule
            n = N_RS0
            while True:
                res = admissible_rows(specs[:n], workers, log)
                adm = sum(r["admissible"] for r in res)
                log(f"rs: {n} evaluated, {adm} admissible")
                if adm >= MIN_ADM_RS or n >= N_RS_MAX:
                    break
                n += N_RS_STEP
            extra = {"n_used": n, "extended": n > N_RS0, "min_admissible_rule": MIN_ADM_RS}
        elif p == "rand3":                              # until K_RAND admissible
            n, res = 0, []
            while n < N_RAND_MAX:
                n = min(n + RAND_CHUNK, N_RAND_MAX)
                res = admissible_rows(specs[:n], workers, log)
                adm = [r["name"] for r in res if r["admissible"]]
                log(f"rand3: {n} evaluated, {len(adm)} admissible")
                if len(adm) >= K_RAND:
                    break
            idx = [i for i, r in enumerate(res) if r["admissible"]][:K_RAND]
            adm = [res[i]["name"] for i in idx]
            # n_consumed = sequence points up to and including the K_RAND-th admissible member (registration §3.3); the chunk end is n_evaluated (Q5)
            extra = {"n_consumed": (idx[-1] + 1) if len(idx) >= K_RAND else n, "control_set": adm, "complete": len(adm) >= K_RAND}
        else:
            res = admissible_rows(specs, workers, log)
            extra = {}
            if p == "manual":
                for md in (1.0e-3, 1.5e-3):
                    lad = [D.name(s) for s in manual_ladder(md)]
                    byn = {r["name"]: r for r in res}
                    extra[f"M_for_m_D_{md:g}"] = next((n for n in lad if byn[n]["admissible"]), None)
        for i, r in enumerate(res):
            rows.append({**r, "slot": p, "index": i})
        fails = {}
        for r in res:
            for g in r.get("failed_geom02", []) + r.get("unmeasured_geom02", []):
                fails[g] = fails.get(g, 0) + 1
        summ["pools"][p] = {"n_evaluated": len(res), "gate_clean": sum(bool(r.get("all_pass")) for r in res), "x1_pass": sum(bool(r["x1"] and r["x1"]["pass"]) for r in res),
                            "chain_ok": sum(bool(r["chain_ok"]) for r in res), "admissible": sum(r["admissible"] for r in res), "failed_gate_counts": fails,
                            "error_rows": [r["name"] for r in res if "error" in r],
                            "admissible_names": [r["name"] for r in res if r["admissible"]], "wall_s": round(time.time() - tp, 1),
                            "eval_wall_s_median": float(np.median([r["eval_wall_s"] for r in res if "eval_wall_s" in r])) if res else None, **extra}
        log(f"{p}: {summ['pools'][p]['admissible']}/{len(res)} admissible, {summ['pools'][p]['wall_s']} s")
    summ.update(wall_s=round(time.time() - t0, 1), finished_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), fingerprint=fingerprint(), d_fingerprint=D.fingerprint(),
                dependencies=DEPENDENCIES, workers=workers, parent_stl=parent_x1(), chain_tolerance=CHAIN_TOL, box_u=BOX)
    with (OUT / "rows.jsonl").open("w") as fh:
        for r in rows:
            fh.write(json.dumps(r, sort_keys=True) + "\n")
    (OUT / "summary.json").write_text(json.dumps(summ, indent=1, sort_keys=True) + "\n")
    return summ


# ---- response surface: no-intercept full quadratic in u (9 coefficients) ------------------------------------------------------------------------
def quad9(U):
    u = np.atleast_2d(np.asarray(U, float))
    return np.column_stack([u[:, 0], u[:, 1], u[:, 2], u[:, 0] ** 2, u[:, 1] ** 2, u[:, 2] ** 2, u[:, 0] * u[:, 1], u[:, 0] * u[:, 2], u[:, 1] * u[:, 2]])


def fit9(U, y):
    """OLS without intercept; returns beta (9,), residual SD (dof n - 9), rank and condition number of the design matrix."""
    X = quad9(U)
    beta, *_ = np.linalg.lstsq(X, np.asarray(y, float), rcond=None)
    r = np.asarray(y, float) - X @ beta
    sv = np.linalg.svd(X, compute_uv=False)
    dof = len(y) - 9
    return beta, (float(np.sqrt(r @ r / dof)) if dof > 0 else None), int(np.linalg.matrix_rank(X)), float(sv[0] / sv[-1]) if sv[-1] > 0 else math.inf


def predict9(beta, U):
    return quad9(U) @ np.asarray(beta, float)


AXIAL_U = np.vstack([np.eye(3), -np.eye(3)])


def d_optimal9(cand_u, k, base_u=AXIAL_U, eps=1e-6):
    """Greedy Bayesian D-optimal forward selection on the 9-column no-intercept model: add the candidate maximising logdet(X'X + eps I); ties -> smallest index."""
    chosen, X = [], quad9(base_u)
    for _ in range(min(k, len(cand_u))):
        best = None
        for j in range(len(cand_u)):
            if j in chosen:
                continue
            Xj = np.vstack([X, quad9(cand_u[j:j + 1])])
            ld = np.linalg.slogdet(Xj.T @ Xj + eps * np.eye(9))[1]
            if best is None or ld > best[0] + 1e-12:
                best = (ld, j)
        chosen.append(best[1])
        X = np.vstack([X, quad9(cand_u[best[1]:best[1] + 1])])
    return chosen, X


def grid_u(n=N_GRID):
    axes = [np.linspace(BOX[m][0], BOX[m][1], n) for m in SUBSET]
    return np.stack(np.meshgrid(*axes, indexing="ij"), -1).reshape(-1, 3)


def constrained_argmax(beta_y, beta_z, target, n_grid=N_GRID, grid=None):
    """argmax of predicted downforce over the box grid subject to predicted drag <= -target; None if empty; ties -> first grid point (C order)."""
    G = grid_u(n_grid) if grid is None else grid
    y, z = predict9(beta_y, G), predict9(beta_z, G)
    ok = z <= -target
    if not ok.any():
        return None, None, None
    y = np.where(ok, y, -np.inf)
    j = int(np.argmax(y))
    return G[j], float(y[j]), float(z[j])


def cloud(u_star, radius, n, seed):
    from scipy.stats import qmc
    lo = np.array([BOX[m][0] for m in SUBSET]); hi = np.array([BOX[m][1] for m in SUBSET])
    x = qmc.Sobol(d=3, scramble=True, seed=seed).random(n)
    return np.clip(u_star + radius * (2 * x - 1), lo, hi)


def propose(beta_y, beta_z, is_admissible, exclude=(), m_d=M_D, targets=TARGETS, n_cloud=N_CLOUD, radius=R_CLOUD, seed=SEED_CLOUD, gate_cap=GATE_CAP,
            n_per_target=N_PER_TARGET, n_prop=N_PROP, gate_round=GATE_ROUND, n_grid=N_GRID, grid=None):
    """Registered refinement step (§5.2, §5.11).  Per target tau: u*_tau = constrained argmax of the fitted surface over the box grid with predicted drag
    <= -tau m_d (ties -> first grid point in C order); a target with no feasible grid point or y*_tau <= 0 contributes nothing.  Candidate list = u*_tau
    first, then the Sobol cloud (seed + 0-based target index, max-norm radius, clipped to the box) filtered to predicted drag <= -tau m_d and predicted
    downforce >= 0.9 y*_tau, by predicted downforce descending (stable); distinct names only, already-evaluated names excluded.  The lists are interleaved
    round-robin into one queue; a name an earlier list already queued is skipped (every point is gated once, owned by the target that queued it first).
    Gated (`is_admissible(u) -> bool`, the full P0 admissibility) in rounds of `gate_round`, stopping after the round in which every target with a queued
    point has >= n_per_target admissible points of its own, or `gate_cap` points were gated.  Proposals: per target (target order) its admissible point with
    the largest predicted downforce, then the remaining admissible points by predicted downforce (ties -> gated earlier), up to n_prop.  Deterministic."""
    lists, stars = [], {}
    for i, tau in enumerate(targets):
        us, ys, zs = constrained_argmax(beta_y, beta_z, tau * m_d, n_grid, grid)
        if us is None or ys <= 0:
            stars[tau] = None if us is None else {"u": [float(v) for v in us], "y_pred": ys, "z_pred": zs, "n_candidates": 0, "no_predicted_gain": True}
            lists.append([])
            continue
        C = cloud(us, radius, n_cloud, seed + i)
        y, z = predict9(beta_y, C), predict9(beta_z, C)
        keep = (z <= -tau * m_d) & (y >= 0.9 * ys)
        order = np.argsort(-y[keep], kind="stable")
        pts = [(tuple(us), ys, zs)] + [(tuple(C[keep][j]), float(y[keep][j]), float(z[keep][j])) for j in order]
        seen, uniq = set(exclude), []
        for u, yy, zz in pts:
            n = D.name(u_to_spec(u))
            if n not in seen:
                seen.add(n)
                uniq.append((u, yy, zz, n))
        stars[tau] = {"u": [float(v) for v in us], "y_pred": ys, "z_pred": zs, "n_candidates": 0}
        lists.append(uniq)
    queue, taken = [], set()
    for k in range(max(map(len, lists), default=0)):
        for tau, l in zip(targets, lists):
            if k < len(l) and l[k][3] not in taken:
                taken.add(l[k][3])
                queue.append((tau, l[k]))
                stars[tau]["n_candidates"] += 1
    has = {tau: stars[tau] is not None and stars[tau]["n_candidates"] > 0 for tau in targets}
    gated, adm = [], {tau: [] for tau in targets}
    pos = 0
    while pos < len(queue) and len(gated) < gate_cap:
        batch = queue[pos:pos + min(gate_round, gate_cap - len(gated))]
        pos += len(batch)
        for tau, (u, yy, zz, n) in batch:
            ok = bool(is_admissible(np.asarray(u)))
            if ok:
                adm[tau].append((-yy, len(gated), n, u, zz))      # sort key (-y_pred, gated index): ties -> gated earlier
            gated.append({"name": n, "u": [float(v) for v in u], "target": tau, "y_pred": yy, "z_pred": zz, "admissible": ok})
        if all(len(adm[tau]) >= n_per_target for tau in targets if has[tau]):
            break
    first = [min(adm[tau]) for tau in targets if adm[tau]]
    rest = sorted(t for tau in targets for t in adm[tau] if t not in first)
    props = [{"name": n, "u": [float(v) for v in u], "target": gated[g]["target"], "y_pred": -ny, "z_pred": zz} for ny, g, n, u, zz in (first + rest)[:n_prop]]
    return {"proposals": props, "gated": gated, "argmax": {f"{tau:g}": s for tau, s in stars.items()}, "n_gated": len(gated),
            "params": {"m_d": m_d, "targets": list(targets), "n_cloud": n_cloud, "radius": radius, "seed": seed, "gate_cap": gate_cap, "n_per_target": n_per_target, "n_prop": n_prop,
                       "gate_round": gate_round, "n_grid": n_grid, "box_u": BOX}}


# ---- design check and the self-check ------------------------------------------------------------------------------------------------------------
def design() -> dict:
    rows = [json.loads(l) for l in (OUT / "rows.jsonl").read_text().splitlines()]
    summ = json.loads((OUT / "summary.json").read_text())
    rs = [r for r in rows if r["slot"] == "rs"]
    surv = [r for r in rs if r["admissible"]]
    U = np.array([spec_to_u(r["spec"]) for r in surv]) if surv else np.zeros((0, 3))
    out = {"kind": "screen01_rs_design_check_rev1", "rule": "base = the 6 axial points (+-e_i); 9 admissible rs members added by greedy Bayesian D-optimality on the "
           "9-column no-intercept quadratic (logdet(X'X + 1e-6 I)); admissible = gate stack + X1 + chain check; admissible design iff rank 9 and cond <= 20",
           "n_rs_evaluated": len(rs), "n_admissible": len(surv), "box_u": BOX}
    corners = np.array(list(itertools.product((-1, 1), repeat=3)), float)
    s_ref = np.linalg.svd(quad9(np.vstack([AXIAL_U, corners])), compute_uv=False)
    out["reference_fccd_14x9_cond"] = float(s_ref[0] / s_ref[-1])
    if len(surv):
        idx, X = d_optimal9(U, 9)
        sv = np.linalg.svd(X, compute_uv=False)
        cond = float(sv[0] / sv[-1]) if sv[-1] > 0 else math.inf
        out.update(design_points=[surv[j]["name"] for j in idx], design_u=[U[j].tolist() for j in idx], n_design_nonparent=int(len(X)), rank=int(np.linalg.matrix_rank(X)), cond=cond,
                   singular_values=sv.tolist(), design_admissible=bool(np.linalg.matrix_rank(X) == 9 and cond <= 20),
                   rank_all_admissible_plus_axial=int(np.linalg.matrix_rank(quad9(np.vstack([AXIAL_U, U])))),
                   abs_u_inf_design=[float(np.abs(U[j]).max()) for j in idx], camber_u_design=[float(U[j][1]) for j in idx],
                   n_admissible_in_extension=int((U[:, 1] < -1.0).sum()), n_rs_in_extension=int(sum(spec_to_u(r["spec"])[1] < -1.0 for r in rs)))
    if "rand3" in summ["pools"]:
        names = set(summ["pools"]["rand3"]["control_set"])
        Ur = np.array([spec_to_u(r["spec"]) for r in rows if r["slot"] == "rand3" and r["name"] in names])
        out["rand3"] = {"k": len(Ur), "abs_u_inf": sorted(float(v) for v in np.abs(Ur).max(1)) if len(Ur) else [], "n_in_extension": int((Ur[:, 1] < -1.0).sum()) if len(Ur) else 0,
                        "n_consumed": summ["pools"]["rand3"]["n_consumed"], "complete": summ["pools"]["rand3"]["complete"]}
    (OUT / "design_check.json").write_text(json.dumps(out, indent=1, sort_keys=True) + "\n")
    return out


def selfcheck() -> dict:
    """propose() on a synthetic surface with a Bernoulli admissibility oracle: proposals lie in the box, are predicted feasible with the right margin,
    are admissible, and the step is deterministic."""
    rng = np.random.default_rng(1)
    by = np.array([2.0e-2, -1.2e-2, -1.4e-2, 0.0, 1e-3, 0.0, 0.0, 0.0, 2e-3])   # downforce: pitch +, camber -, reflex -
    bz = np.array([1.4e-2, -0.3e-2, -1.0e-2, 0.0, 0.5e-3, 0.0, 0.0, 0.0, 0.0])  # drag: the same signs, smaller for camber
    oracle = lambda u: rng.random() < 0.42  # noqa: E731
    r1 = propose(by, bz, oracle, n_grid=41)
    rng = np.random.default_rng(1)
    r2 = propose(by, bz, lambda u: rng.random() < 0.42, n_grid=41)
    assert r1["proposals"] and r1 == r2, "propose must be deterministic"
    lo = np.array([BOX[m][0] for m in SUBSET]); hi = np.array([BOX[m][1] for m in SUBSET])
    for p in r1["proposals"]:
        u = np.array(p["u"])
        assert (u >= lo - 1e-12).all() and (u <= hi + 1e-12).all(), "proposal outside the box"
        assert predict9(bz, u)[0] <= -p["target"] * M_D + 1e-12, "proposal not predicted feasible at its target"
        assert any(g["name"] == p["name"] and g["admissible"] for g in r1["gated"]), "proposal not gated admissible"
    assert len(r1["proposals"]) <= N_PROP and r1["n_gated"] <= GATE_CAP
    assert len({p["target"] for p in r1["proposals"][:3]}) == 3, "one proposal per target first"
    names = [g["name"] for g in r1["gated"]]
    assert len(set(names)) == len(names), "a point is gated at most once"
    for tau, a in r1["argmax"].items():   # u*_tau is the first point gated under its own target (§5.11)
        own = [g for g in r1["gated"] if f"{g['target']:g}" == tau]
        assert not a or not own or own[0]["name"] == D.name(u_to_spec(a["u"])), "u* must be gated first"
    r3 = propose(np.array([0, 0, 0, -1e-2, -1e-2, -1e-2, 0, 0, 0]), bz, lambda u: True, n_grid=41)   # downforce < 0 everywhere but the (infeasible) origin
    assert not r3["proposals"] and not r3["gated"] and all(s is None or s.get("no_predicted_gain") for s in r3["argmax"].values()), "no proposals without a predicted gain"
    U = np.vstack([AXIAL_U, sobol_u(12, 5)])
    b, sd, rank, cond = fit9(U, predict9(by, U) + 1e-4 * rng.standard_normal(len(U)))
    assert rank == 9 and np.allclose(b, by, atol=5e-4), "fit9 must recover the surface"
    # the gate stack's import closure is covered by DEPENDENCIES (the cache key and the freeze-1 REUSED list), every dependency exists
    import fid01_build, mode01_prescreen, mode01_v18_prescreen, sdf_native_genesis_v18_2026_10, unc01_u3_prepare, width_rule_study  # noqa: F401
    closure = {str(Path(m.__file__).resolve().relative_to(ROOT)) for m in list(sys.modules.values()) if getattr(m, "__file__", None) and Path(m.__file__).resolve().is_relative_to(ROOT)}
    missing = sorted(f for f in closure if not f.startswith("scripts/screen01/") and f not in DEPENDENCIES)
    assert not missing and all((ROOT / f).is_file() for f in DEPENDENCIES), f"DEPENDENCIES does not cover the gate stack: {missing}"
    return {"ok": True, "fingerprint": fingerprint(), "n_dependencies": len(DEPENDENCIES), "n_proposals": len(r1["proposals"]), "n_gated": r1["n_gated"], "targets": [p["target"] for p in r1["proposals"]], "argmax": r1["argmax"]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["gen", "p0", "design", "selfcheck"])
    ap.add_argument("--pools", nargs="*", default=["axial", "ref", "manual", "rs"])
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args()
    if a.cmd == "gen":
        print({k: len(v) for k, v in gen()["pools"].items()})
    elif a.cmd == "p0":
        s = p0(a.pools, a.workers)
        print(json.dumps({k: {kk: vv for kk, vv in v.items() if kk not in ("admissible_names", "control_set")} for k, v in s["pools"].items()}, indent=1))
    elif a.cmd == "design":
        print(json.dumps({k: v for k, v in design().items() if k not in ("singular_values",)}, indent=1)[:3000])
    else:
        print(json.dumps(selfcheck(), indent=1))


if __name__ == "__main__":
    main()
