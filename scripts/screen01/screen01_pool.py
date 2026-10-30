#!/usr/bin/env python3
"""SCREEN-01 (#64, M3b-1): finite R0-clean candidate pools on the v18 plate — generation, solver-free gate prescreen, X1 export gate and the
response-surface design check.  Pre-registration geometry work (EXPLORATORY until the registration freezes it); no solver, no force.
Registration draft: docs/screen01_registration_2026_10_30.md (§3).  Reuses scripts/fid01/fid01_designs.py (joint analytic builder, gate stack
`work`, X1 export `_x1`) unchanged.

Pools (deterministic):
  axial                 the 10 stage-1 states {mode: +-A*} (heave fixed at 0)
  manual                the manual control: camber -11.3, reflex -11.3 (FID-01 C1)
  rs_<m1>_<m2>_<m3>     one per 3-mode subset of (pitch, camber, reflex, twist, sweep): N_RS scrambled Sobol points in [-1, 1]^3
                        (scipy qmc.Sobol, seed SEED_RS + subset index), amplitude = u * A*, rounded to 1e-3 (mm or deg)
  rand5                 the random-direction control pool: N_RAND scrambled Sobol points in [-1, 1]^5 (seed SEED_RAND), same gates

    python scripts/screen01/screen01_pool.py gen
    python scripts/screen01/screen01_pool.py prescreen --pools axial manual rs_pitch_camber_reflex rand5 --limit 48 --workers 4
    python scripts/screen01/screen01_pool.py x1 --pools ... --workers 4
    python scripts/screen01/screen01_pool.py design
    python scripts/screen01/screen01_pool.py all --pools ... --limit 48 --workers 4   (gen, prescreen, x1, design)

Cached rows: work/screen01_pool_prescreen/rows/<name>.json (keyed by the fid01_designs code fingerprint + this file's hash).
Outputs: docs/evidence/screen01_2026_10_30/pool_prescreen/{pools.json,rows.jsonl,prescreen_summary.json,x1.json,design_check.json}.
"""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import multiprocessing as mp
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts"), str(ROOT / "scripts/fid01")]
import fid01_designs as D  # noqa: E402

OUT = ROOT / "docs/evidence/screen01_2026_10_30/pool_prescreen"
WORK = ROOT / "work/screen01_pool_prescreen"
STL = WORK / "stl"
D.STL = STL   # X1 blobs of this study go here (module level: spawn workers re-import this module)

MODES = ("pitch", "camber", "reflex", "twist", "sweep")          # heave fixed at 0 (registration §3.1)
A_STAR = {"pitch": 3.1, "camber": 19.7, "reflex": 29.3, "twist": 1.1, "sweep": 11.3}   # MODE-01 v18 A* (both signs gate-clean), deg / mm
N_RS, N_RAND = 64, 256
SEED_RS, SEED_RAND = 20261030, 20261031
N_BASE_DESIGN = 7          # parent + 6 axial points of the subset (stage 1, same phases)
N_RS_POINTS = 9            # pool points added D-optimally -> 16 design points for the 10 full-quadratic coefficients
MANUAL = {"camber": -11.3, "reflex": -11.3}


def subsets():
    return list(itertools.combinations(MODES, 3))


def pool_name(sub):
    return "rs_" + "_".join(sub)


def spec_of(sub, u):
    return {m: round(float(x * A_STAR[m]), 3) for m, x in zip(sub, u) if round(float(x * A_STAR[m]), 3) != 0.0}


def gen() -> dict:
    from scipy.stats import qmc
    pools = {"axial": [{m: s * A_STAR[m]} for m in MODES for s in (1, -1)], "manual": [dict(MANUAL)]}
    for i, sub in enumerate(subsets()):
        u = 2 * qmc.Sobol(d=3, scramble=True, seed=SEED_RS + i).random_base2(int(np.log2(N_RS))) - 1
        pools[pool_name(sub)] = [spec_of(sub, row) for row in u]
    u = 2 * qmc.Sobol(d=5, scramble=True, seed=SEED_RAND).random_base2(int(np.log2(N_RAND))) - 1
    pools["rand5"] = [spec_of(MODES, row) for row in u]
    rec = {"kind": "screen01_candidate_pools", "modes": MODES, "a_star": A_STAR, "n_rs": N_RS, "n_rand": N_RAND, "seed_rs": SEED_RS, "seed_rand": SEED_RAND,
           "generator": "scipy.stats.qmc.Sobol(scramble=True, seed).random_base2; u in [-1, 1]; amplitude = u * A*, round 3", "scipy": __import__("scipy").__version__,
           "pools": pools}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "pools.json").write_text(json.dumps(rec, indent=1, sort_keys=True) + "\n")
    return rec


def fingerprint() -> str:
    return hashlib.sha256((D.fingerprint() + hashlib.sha256(Path(__file__).read_bytes()).hexdigest()).encode()).hexdigest()


def _work(task):
    t0 = time.time()
    row = D.work(task)
    row["eval_wall_s"] = round(time.time() - t0, 1)
    return row


def tasks_of(pools, names, limit):
    out = []
    for p in names:
        specs = pools["pools"][p]
        if p == "rand5" and limit:
            specs = specs[:limit]
        out += [(p, i, s) for i, s in enumerate(specs)]
    return out


def prescreen(names, limit, workers) -> dict:
    pools = json.loads((OUT / "pools.json").read_text())
    tasks = tasks_of(pools, names, limit)
    rows_dir, fp = WORK / "rows", fingerprint()
    rows_dir.mkdir(parents=True, exist_ok=True)
    done = {}
    for f in rows_dir.glob("*.json"):
        r = json.loads(f.read_text())
        if r.get("code_fingerprint") == fp:
            done[r["name"]] = r
    todo = [t for t in tasks if D.name(t[2]) not in done]
    t0 = time.time()
    with mp.get_context("spawn").Pool(workers, initializer=D._init) as pool:
        for r in pool.imap_unordered(_work, todo):
            r["code_fingerprint"] = fp
            (rows_dir / f"{r['name']}.json").write_text(json.dumps(r, sort_keys=True))
            done[r["name"]] = r
            print(r["slot"], r["name"], r.get("all_pass", r.get("error")), r.get("failed_geom02"), r.get("eval_wall_s"), flush=True)
    wall = time.time() - t0
    rows = [{**done[D.name(s)], "slot": p, "index": i} for p, i, s in tasks]
    with (OUT / "rows.jsonl").open("w") as fh:
        for r in rows:
            fh.write(json.dumps(r, sort_keys=True) + "\n")
    summ = {"kind": "screen01_pool_prescreen", "evidence_tier": "EXPLORATORY (pre-registration geometry only; no solver)", "code_fingerprint": fp,
            "gate_stack": "fid01_designs.work: 13 GEOM-02 v2 gates incl. R0 min_feature_width (v18 parent as parent_state), P22-v2 N_phi <= 8272, "
                          "smoothed-volume band 10 % vs the v17 baseline, clearance >= 0.15 m; unmeasured counts as fail; R3 descriptive",
            "pools_evaluated": names, "rand5_limit": limit, "workers": workers, "evaluated_now": len(todo), "wall_s_this_run": round(wall, 1), "per_pool": {}}
    for p in names:
        rs = [r for r in rows if r["slot"] == p]
        fails = {}
        for r in rs:
            for g in r.get("failed_geom02", []) + r.get("unmeasured_geom02", []):
                fails[g] = fails.get(g, 0) + 1
            if "error" in r:
                fails["ERROR"] = fails.get("ERROR", 0) + 1
        summ["per_pool"][p] = {"n": len(rs), "gate_clean": sum(bool(r.get("all_pass")) for r in rs), "failed_gate_counts": fails,
                               "r3_descriptive_pass": sum(r.get("r3_descriptive") == "pass" for r in rs),
                               "eval_wall_s_median": float(np.median([r["eval_wall_s"] for r in rs if "eval_wall_s" in r])) if rs else None,
                               "gate_clean_names": [r["name"] for r in rs if r.get("all_pass")]}
    (OUT / "prescreen_summary.json").write_text(json.dumps(summ, indent=1, sort_keys=True) + "\n")
    return summ


def _x1(task):
    return D._x1(task)


def x1(names, workers) -> dict:
    rows = [json.loads(l) for l in (OUT / "rows.jsonl").read_text().splitlines()]
    clean = [(r["name"], r["spec"]) for r in rows if r["slot"] in names and r.get("all_pass")]
    prev = json.loads((OUT / "x1.json").read_text())["x1"] if (OUT / "x1.json").exists() else {}
    todo = [t for t in clean if t[0] not in prev]
    t0 = time.time()
    with mp.get_context("spawn").Pool(workers) as pool:
        for n, rec in pool.imap_unordered(_x1, todo):
            prev[n] = rec
            print("x1", n, rec["pass"], flush=True)
    out = {"kind": "screen01_pool_x1", "gate": "unc01_u3_prepare.export (geom02_canonical r = 8, X1 practical gate double + float32 STL)", "wall_s_this_run": round(time.time() - t0, 1),
           "n_gate_clean": len(clean), "n_pass": sum(prev[n]["pass"] for n, _ in clean), "x1": prev}
    (OUT / "x1.json").write_text(json.dumps(out, indent=1, sort_keys=True) + "\n")
    return out


# ---- response-surface design check (solver-free) -------------------------------------------------------------------------------------------------
def quad_cols(U):
    u = np.asarray(U, float)
    cols = [np.ones(len(u))] + [u[:, i] for i in range(3)] + [u[:, i] ** 2 for i in range(3)] + [u[:, i] * u[:, j] for i in range(3) for j in range(i + 1, 3)]
    return np.column_stack(cols)


def d_optimal(base, cand, k, eps=1e-6):
    """Greedy Bayesian D-optimal forward selection: add the candidate maximising logdet(X'X + eps I); ties -> smallest index.  Returns chosen indices."""
    chosen, X = [], quad_cols(base)
    for _ in range(min(k, len(cand))):
        best = None
        for j in range(len(cand)):
            if j in chosen:
                continue
            Xj = np.vstack([X, quad_cols(cand[j:j + 1])])
            ld = np.linalg.slogdet(Xj.T @ Xj + eps * np.eye(10))[1]
            if best is None or ld > best[0] + 1e-12:
                best = (ld, j)
        chosen.append(best[1])
        X = np.vstack([X, quad_cols(cand[best[1]:best[1] + 1])])
    return chosen, X


def design() -> dict:
    from scipy.spatial import ConvexHull, Delaunay
    rows = {r["name"]: r for r in (json.loads(l) for l in (OUT / "rows.jsonl").read_text().splitlines())}
    x1r = json.loads((OUT / "x1.json").read_text())["x1"] if (OUT / "x1.json").exists() else {}
    pools = json.loads((OUT / "pools.json").read_text())["pools"]
    out = {"kind": "screen01_rs_design_check", "rule": f"base = parent + 6 axial (+-1 e_i); {N_RS_POINTS} pool survivors added by greedy Bayesian D-optimality "
           "(logdet(X'X + 1e-6 I)) on the full-quadratic columns [1, u, u^2, u_i u_j]; survivors = gate-clean AND X1-pass; trust region = convex hull of the design points",
           "subsets": {}}
    corners = np.array(list(itertools.product((-1, 1), repeat=3)), float)
    grid3 = np.array(list(itertools.product((-1, 0, 1), repeat=3)), float)
    for sub in subsets():
        p = pool_name(sub)
        if not any(r["slot"] == p for r in rows.values()):
            continue
        names = [D.name(s) for s in pools[p]]
        surv = [(n, s) for n, s in zip(names, pools[p]) if rows.get(n, {}).get("all_pass") and x1r.get(n, {}).get("pass")]
        U = np.array([[s.get(m, 0.0) / A_STAR[m] for m in sub] for _, s in surv]) if surv else np.zeros((0, 3))
        base = np.vstack([np.zeros((1, 3)), np.eye(3), -np.eye(3)])
        rec = {"n_pool": len(names), "n_gate_clean": sum(bool(rows.get(n, {}).get("all_pass")) for n in names), "n_survivors": len(surv),
               "n_gate_clean_x1_unknown": sum(bool(rows.get(n, {}).get("all_pass")) and n not in x1r for n in names)}
        if len(surv):
            allX = quad_cols(np.vstack([base, U]))
            rec["rank_all_survivors_plus_base"] = int(np.linalg.matrix_rank(allX))
            idx, X = d_optimal(base, U, N_RS_POINTS)
            sv = np.linalg.svd(X, compute_uv=False)
            rec.update(design_points=[surv[j][0] for j in idx], design_u=[U[j].tolist() for j in idx], rank=int(np.linalg.matrix_rank(X)), n_design=int(len(X)),
                       cond=float(sv[0] / sv[-1]) if sv[-1] > 0 else None, singular_values=sv.tolist(), logdet_xtx=float(np.linalg.slogdet(X.T @ X)[1]) if sv[-1] > 0 else None)
            pts = np.vstack([base, U[idx]])
            try:
                hull = Delaunay(pts)
                inside = lambda Q: int((hull.find_simplex(Q) >= 0).sum())  # noqa: E731
                rec["trust_region"] = {"survivors_inside_hull": inside(U), "corners_inside_hull": inside(corners), "grid27_inside_hull": inside(grid3),
                                       "hull_volume_fraction_of_box": float(ConvexHull(pts).volume / 8.0)}
            except Exception as e:  # noqa: BLE001 - a degenerate hull is a result
                rec["trust_region"] = {"error": f"{type(e).__name__}: {e}"}
            ccd = np.vstack([np.zeros((1, 3)), np.eye(3), -np.eye(3), corners])   # reference: face-centred central composite design, 15 points
            s2 = np.linalg.svd(quad_cols(ccd), compute_uv=False)
            rec["reference_fccd15_cond"] = float(s2[0] / s2[-1])
        out["subsets"][p] = rec
    if any(r["slot"] == "rand5" for r in rows.values()):
        names = [D.name(s) for s in pools["rand5"]]
        ev = [n for n in names if n in rows]
        surv = [n for n in ev if rows[n].get("all_pass") and x1r.get(n, {}).get("pass")]
        out["rand5"] = {"n_evaluated": len(ev), "n_gate_clean": sum(bool(rows[n].get("all_pass")) for n in ev), "n_survivors": len(surv),
                        "first_22_survivors_reached_at_sequence_index": (ev.index(surv[21]) + 1) if len(surv) >= 22 else None,
                        "projected_sequence_length_for_22": (round(22 * len(ev) / len(surv)) if surv else None), "survivors_in_order": surv}
    (OUT / "design_check.json").write_text(json.dumps(out, indent=1, sort_keys=True) + "\n")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["gen", "prescreen", "x1", "design", "all"])
    ap.add_argument("--pools", nargs="*", default=["axial", "manual", "rs_pitch_camber_reflex", "rand5"])
    ap.add_argument("--limit", type=int, default=48, help="rand5: evaluate only the first N sequence points (0 = all)")
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args()
    if a.cmd in ("gen", "all"):
        print("pools", {k: len(v) for k, v in gen()["pools"].items()})
    if a.cmd in ("prescreen", "all"):
        print(json.dumps({k: {kk: vv for kk, vv in v.items() if kk != "gate_clean_names"} for k, v in prescreen(a.pools, a.limit, a.workers)["per_pool"].items()}, indent=1))
    if a.cmd in ("x1", "all"):
        r = x1(a.pools, a.workers)
        print("x1", r["n_pass"], "/", r["n_gate_clean"])
    if a.cmd in ("design", "all"):
        print(json.dumps(design(), indent=1)[:4000])


if __name__ == "__main__":
    main()
