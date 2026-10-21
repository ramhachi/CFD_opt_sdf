#!/usr/bin/env python3
"""FID-01 (#62, M3a) designs on the v18 analytic plate: the registered candidate slots, their phi, and the solver-free admissibility prescreen.

A design is a dict {mode: amplitude}.  Analytic modes (heave, pitch, camber, reflex, twist, sweep; units as v18_plate.UNITS) are applied JOINTLY to the
plate parameters, so a combination is again an exact plate SDF (v18_plate.plate_phi); a single analytic mode reproduces v18_plate.raw_mode bit for bit.
One-sided Gaussian normal offsets of mode01_modes applied to the v18 parent (bump_lower, bump_upper: sigma 0.125 m, narrow; bump_lower_s300: sigma
0.3 m, mid support) are the support designs.  As everywhere else only ACTIVE nodes change, and the gated bytes are the harness state model
(v18_plate.harness_state).  Registration: docs/fid01_registration_2026_10_21.md.

    python scripts/fid01/fid01_designs.py prescreen [--workers N]   # every candidate through the MODE-01 v18 gate stack -> designs.json rows
    python scripts/fid01/fid01_designs.py select [--workers N]      # per slot, gate-clean candidates in order through the X1 STL export gate -> designs
"""
from __future__ import annotations

import argparse
import json
import math
import multiprocessing as mp
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]
import mode01_modes as M  # noqa: E402
import v18_plate as V  # noqa: E402

OUT = ROOT / "docs/evidence/fid01_2026_10_21"
STL = ROOT / "work/fid01_of/stl"
CACHE = ROOT / "work/fid01_prescreen"
ANALYTIC = ("heave", "pitch", "camber", "reflex", "twist", "sweep")
BUMPS = ("bump_lower", "bump_upper", "bump_small", "bump_lower_s300")
SIGMA_MID_M = 0.3   # bump_lower_s300: one-sided Gaussian normal offset on the ground-facing surface, sigma 0.3 m (mid support)

# slot -> (stratum, family, candidates in order; the first that passes every gate is the design).  Registration §3.
P_, M_ = 1, -1
SLOTS = {
    "W1": ("wide", "rigid", [{"heave": -31.1}]),
    "W1b": ("wide", "rigid", [{"heave": -13.7}]),
    "W2": ("wide", "rigid", [{"heave": 31.1}, {"heave": 13.7}]),
    "W3": ("wide", "rigid", [{"pitch": -0.7}]),
    "W8": ("wide", "rigid", [{"pitch": 0.7}]),
    "W4": ("wide", "section", [{"camber": -19.7}]),
    "W4b": ("wide", "section", [{"camber": -11.3}]),
    "W5": ("wide", "section", [{"camber": 19.7}, {"camber": 11.3}]),
    "W6": ("wide", "section", [{"reflex": -29.3}, {"reflex": -19.7}]),
    "W7": ("wide", "span", [{"twist": 2.3}, {"twist": 1.1}]),
    "C1": ("wide", "combination", [{"camber": c, "reflex": r} for c in (-19.7, -11.3) for r in (-29.3, -19.7, -11.3)]),
    "C2": ("wide", "combination", [{"heave": h, "pitch": t} for h in (-31.1, -13.7) for t in (1.3, 0.7)]),
    "C3": ("wide", "combination", [{"heave": h, "camber": c, "twist": t} for h in (-31.1, -13.7) for c in (-19.7, -11.3) for t in (2.3, 1.1)]),
    "C4": ("wide", "combination", [{"pitch": t, "reflex": r, "sweep": 11.3} for t in (-1.3, -0.7) for r in (29.3, 19.7, 11.3)]),
    "C5": ("wide", "combination", [{"camber": c, "twist": -1.1, **sw} for c in (19.7, 11.3) for sw in ({"sweep": -11.3}, {})]),
    "N1": ("narrow", "local", [{"bump_lower": a} for a in (20.0, 15.0, 10.0)]),
    "N2": ("narrow", "local", [{"bump_upper": a} for a in (20.0, 15.0, 10.0)]),
    "M1": ("mid", "local", [{"bump_lower_s300": a} for a in (15.0, 10.0)]),
}


def name(spec: dict) -> str:
    return "v18__" + "_".join(f"{m}_{'p' if a > 0 else 'm'}{abs(a):g}" for m, a in spec.items())


def raw_design(s, p: dict, spec: dict) -> np.ndarray:
    """float64 phi on the whole lattice (before the active-set mask)."""
    if len(spec) == 1 and next(iter(spec)) in BUMPS:
        (m, a), = spec.items()
        return M._bump(s, a, -1.0, SIGMA_MID_M) if m == "bump_lower_s300" else M.raw_mode(s, m, a)
    if not spec or not set(spec) <= set(ANALYTIC):
        raise ValueError(f"not a registered design: {spec}")
    q = dict(p)
    for m, a in spec.items():
        if m == "heave":
            q["zc"] += a / 1000.0
        elif m == "pitch":
            q["alpha"] += math.radians(a)
        elif m in ("camber", "reflex"):
            q[m] += a / 1000.0
    twist = (lambda e: math.radians(spec["twist"]) * (e ** 2 - 1 / 3)) if "twist" in spec else None
    sweep = (lambda e: spec["sweep"] / 1000.0 * (e ** 2 - 1 / 3)) if "sweep" in spec else None
    return V.plate_phi(s, q, twist=twist, sweep=sweep)


def design_phi(s, p: dict, spec: dict) -> np.ndarray:
    """The analytic design on the active nodes, parent bytes elsewhere (as v18_plate.mode_phi)."""
    return np.where(M.active_mask(s), raw_design(s, p, spec), s.phi.astype(np.float64)).astype("<f4")


def gated_phi(s, p: dict, spec: dict) -> np.ndarray:
    """The bytes the harness builds and the gates see: construct_state(parent, d / max|d|, 1000 max|d| mm, +1)."""
    return V.harness_state(s, design_phi(s, p, spec)).phi


def work(task) -> dict:
    import mode01_prescreen as P
    import sdf_native_genesis_v18_2026_10 as gen
    import width_rule_study as W
    slot, i, spec = task
    s, p = P.G["parent"], P.G["params"]
    row = {"slot": slot, "index": i, "spec": spec, "name": name(spec)}
    try:
        analytic = design_phi(s, p, spec)
        phi = V.harness_state(s, analytic).phi
        ev = P.evaluate(M.with_phi(s, phi))
        ev["all_pass"] = bool(ev["all_pass"] and not ev["unmeasured_geom02"])   # unmeasured blocks like fail (as the MODE-01 v18 prescreen)
        row.update(phi_fortran_sha256=M.phi_fortran_sha(phi), harness_step_mm=V.harness_direction(s, analytic)[1], support=M.support_fraction(s, phi),
                   min_zero_level_z_m=gen.min_zero_z(s, phi), r3_descriptive=W.r3(phi, s.spacing_m)["status"], **ev)
    except Exception as e:  # noqa: BLE001 - a design that cannot be built is a result
        row["error"] = f"{type(e).__name__}: {e}"
    return row


def _init() -> None:
    import mode01_v18_prescreen as P18
    P18._init()


def prescreen(workers: int) -> dict:
    """Every candidate through the gate stack; per-candidate rows are cached under work/fid01_prescreen/ (deterministic, keyed by name) so an edited
    slot list re-uses the rows of unchanged candidates."""
    tasks = [(slot, i, spec) for slot, (_, _, cands) in SLOTS.items() for i, spec in enumerate(cands)]
    CACHE.mkdir(parents=True, exist_ok=True)
    done = {}
    if (OUT / "designs.json").exists():   # rows of an earlier prescreen run (same code, deterministic) seed the cache
        for r in json.loads((OUT / "designs.json").read_text())["rows"]:
            r = {k: v for k, v in r.items() if k not in ("slot", "index")}
            done[r["name"]] = r
            (CACHE / f"{r['name']}.json").write_text(json.dumps(r, sort_keys=True))
    for f in CACHE.glob("*.json"):
        r = json.loads(f.read_text())
        done[r["name"]] = r
    todo = [t for t in tasks if name(t[2]) not in done]
    with mp.get_context("spawn").Pool(workers, initializer=_init) as pool:
        for r in pool.imap_unordered(work, todo):
            (CACHE / f"{r['name']}.json").write_text(json.dumps(r, sort_keys=True))
            done[r["name"]] = r
            print(r["name"], r.get("all_pass", r.get("error")), flush=True)
    rows = [{**done[name(spec)], "slot": slot, "index": i} for slot, i, spec in tasks]
    if any("error" in r for r in rows):
        raise SystemExit(f"design build errors: {[(r['name'], r['error']) for r in rows if 'error' in r]}")
    chosen = {}
    for slot, (stratum, family, _) in SLOTS.items():
        clean = [r for r in rows if r["slot"] == slot and r["all_pass"]]
        chosen[slot] = None if not clean else {"name": clean[0]["name"], "spec": clean[0]["spec"], "stratum": stratum, "family": family, "index": clean[0]["index"]}
    rec = {"kind": "fid01_design_prescreen", "evidence_tier": "solver-free admissibility (registration §3)", "rule": "per slot, the first candidate in the "
           "registered order whose harness bytes pass every MODE-01 v18 gate (13 GEOM-02 v2 gates incl. R0 min_feature_width, P22-v2, smoothed-volume band, "
           "clearance); R3 descriptive only", "slots": {k: {"stratum": v[0], "family": v[1], "candidates": v[2]} for k, v in SLOTS.items()},
           "designs": chosen, "rows": rows, "solver_started": False}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "designs.json").write_text(json.dumps(rec, indent=1, sort_keys=True) + "\n")
    return rec


def _x1(task):
    """STL export (r = 8, the registered profile) and the X1 practical gate (double and float32) of one candidate; the STL is kept for the OpenFOAM inputs."""
    import mode01_v18_prescreen as P18
    import unc01_u3_prepare as U
    name_, spec = task
    s, p = P18.load_parent()
    blob, rec = U.export(M.with_phi(s, gated_phi(s, p, spec)), json.loads(U.PROFILE.read_text()))
    if rec["pass"]:
        STL.mkdir(parents=True, exist_ok=True)
        (STL / f"{name_}.stl").write_bytes(blob)
    return name_, {k: rec[k] for k in ("pass", "stl_sha256", "triangles", "removed_components")}


def select(workers: int) -> dict:
    """Registration §3.2: the design of a slot is its first candidate (registered order) that passes the gate stack AND the X1 export gate.
    X1 is evaluated in rounds over the next gate-clean candidate of every unresolved slot."""
    import multiprocessing as mp
    rec = json.loads((OUT / "designs.json").read_text())
    rows = {r["name"]: r for r in rec["rows"]}
    clean = {slot: [n for n in (name(c) for c in cands) if rows[n]["all_pass"]] for slot, (_, _, cands) in SLOTS.items()}
    x1, chosen, pos = rec.get("x1", {}), {}, {slot: 0 for slot in SLOTS}
    with mp.get_context("spawn").Pool(workers) as pool:
        while True:
            todo = {slot: clean[slot][pos[slot]] for slot in SLOTS if slot not in chosen and pos[slot] < len(clean[slot])}
            if not todo:
                break
            for n, r in pool.map(_x1, [(n, rows[n]["spec"]) for n in todo.values() if n not in x1]):
                x1[n] = r
            for slot, n in todo.items():
                if x1[n]["pass"]:
                    chosen[slot] = n
                else:
                    pos[slot] += 1
    rec["x1"] = x1
    rec["designs"] = {slot: None if slot not in chosen else {"name": chosen[slot], "spec": rows[chosen[slot]]["spec"], "stratum": st, "family": fam,
                                                              "index": rows[chosen[slot]]["index"], "support": rows[chosen[slot]]["support"]["fraction"]}
                      for slot, (st, fam, _) in SLOTS.items()}
    rec["rule"] = ("per slot, the first candidate in the registered order whose harness bytes pass every MODE-01 v18 gate (13 GEOM-02 v2 gates incl. R0 "
                   "min_feature_width, P22-v2, smoothed-volume band, clearance) and whose r = 8 STL passes the X1 practical gate (double and float32); "
                   "R3 descriptive only")
    (OUT / "designs.json").write_text(json.dumps(rec, indent=1, sort_keys=True) + "\n")
    return rec


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["prescreen", "select"])
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args()
    rec = prescreen(a.workers) if a.cmd == "prescreen" else select(a.workers)
    for slot, d in rec["designs"].items():
        print(slot, d and d["name"], [(r["name"], r["all_pass"], r["failed_geom02"], round(r["support"]["fraction"], 3)) for r in rec["rows"] if r["slot"] == slot])


if __name__ == "__main__":
    main()
