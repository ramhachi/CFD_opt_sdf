#!/usr/bin/env python3
"""MODE-01 on the v18 analytic plate (#60; EXPLORATORY_COMMITTED): the declared modes x amplitudes of docs/v18_mode01_plan_2026_10_19.md §4 against the
unchanged hard gates (scripts/mode01_prescreen.evaluate: 13 GEOM-02 v2 gates with the v18 parent as parent_state, P22-v2 N_phi <= 8272, smoothed volume band
10 % vs the v17 baseline, clearance 0.15 m), then the basis rule of §5 applied once.  Solver-free.

    python scripts/mode01_v18_prescreen.py [--workers 8] [--cache DIR]   # writes docs/evidence/mode01_v18_prescreen_2026_10_19/prescreen.{json,md}
"""
from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]
import mode01_modes as M  # noqa: E402
import mode01_prescreen as P  # noqa: E402
import v18_plate as V  # noqa: E402

OUT = ROOT / "docs/evidence/mode01_v18_prescreen_2026_10_19"
GENESIS = ROOT / "docs/evidence/v18_genesis_2026_10_19"
# incommensurate with h = 25 mm and with each other (plan rev. 2, numerical review finding 2): no two ladder points of a rigid mode share a sub-cell phase
AMPS = {"heave": (7.3, 13.7, 21.3, 31.1), "pitch": (0.7, 1.3, 2.1, 3.1), "camber": (11.3, 19.7, 29.3, 41.1), "reflex": (11.3, 19.7, 29.3, 41.1),
        "thick_chord": (0.025, 0.05, 0.1), "twist": (1.1, 2.3, 3.1, 4.7), "dihedral": (11.3, 19.7, 29.3, 43.1), "sweep": (11.3, 19.7, 29.3, 43.1),
        "surge": (7.3, 13.7, 21.3, 31.1), "twist_anti": (1.1, 2.3, 3.1), "thickness_D0": (1, 2, 3),
        "offset_s400": (2, 5), "offset_s125": (2, 5), "offset_s050": (2, 5), "corrugation": (2, 5)}
CLASS = {**{m: "wide" for m in ("heave", "pitch", "camber", "reflex", "thick_chord", "twist", "dihedral", "sweep")}, "surge": "control", "twist_anti": "control",
         "thickness_D0": "reference", "offset_s400": "support-large", "offset_s125": "support-medium", "offset_s050": "support-small", "corrugation": "rough"}
COLLINEAR_COS = 0.9   # a wide mode whose symmetric phi-difference has |cos| > 0.9 with an earlier member (AMPS order) is not counted as a distinct direction
MIN_DISPLACEMENT_M, MIN_SUPPORT, MIN_WIDE, MAX_BASIS = 0.005, 0.5, 6, 10


def tasks() -> list[tuple[str, float]]:
    return [("parent", 0.0)] + [(m, s * a) for m, amps in AMPS.items() for a in amps for s in (1, -1)]


def load_parent():
    from cfd_sdf.design.sdf_state import SDFDesignState
    g = json.loads((GENESIS / "genesis.json").read_text())
    s = SDFDesignState.load(GENESIS / "v18_parent.npz")
    if M.phi_fortran_sha(s.phi) != g["state"]["phi_fortran_order_sha256"] or s.state_sha256 != g["state"]["state_sha256"]:
        raise SystemExit("v18 parent differs from its genesis record")
    return s, g["parameters"]


def _init() -> None:
    import build_lowdim01_inputs as lowdim
    P._init("opt01")  # registered gate stack: profile (cap 8272), policy, v17 baseline volume base
    s, p = load_parent()
    P.G.update(parent=s, params=p, parent_geom=lowdim.geometry(s))


def state_phi(s, p, mode, a) -> np.ndarray:
    """The gated bytes: the analytic mode rebuilt through the harness state model (v18_plate.harness_state); the parent is its own bytes."""
    return s.phi.copy() if mode == "parent" else V.harness_state(s, V.mode_phi(s, p, mode, a)).phi


def work(task) -> dict:
    import sdf_native_genesis_v18_2026_10 as gen
    mode, a = task
    s, p = P.G["parent"], P.G["params"]
    row = {"mode": mode, "amplitude": a, "class": CLASS.get(mode, "parent")}
    try:
        phi = state_phi(s, p, mode, a)
        analytic = s.phi if mode == "parent" else V.mode_phi(s, p, mode, a)
        ev = P.evaluate(M.with_phi(s, phi))
        ev["all_pass"] = bool(ev["all_pass"] and not ev["unmeasured_geom02"])  # unmeasured blocks like fail (also the gate bundle's own rule)
        row.update(phi_fortran_sha256=M.phi_fortran_sha(phi), harness_step_mm=None if mode == "parent" else V.harness_direction(s, analytic)[1], max_abs_vs_analytic_m=float(np.abs(phi.astype(np.float64) - analytic.astype(np.float64)).max()),
                   support=M.support_fraction(s, phi), min_zero_level_z_m=gen.min_zero_z(s, phi), **ev)
    except Exception as e:  # noqa: BLE001 - a state that cannot be built is a result (and makes the run invalid)
        row["error"] = f"{type(e).__name__}: {e}"
    return row


def gram(s, p, members: dict) -> dict:
    """|cos| between the symmetric phi-differences (phi(+A*) - phi(-A*)) / 2 over the active interface band (|parent phi| <= 2h)."""
    band = M.active_mask(s) & (np.abs(s.phi) <= 2 * s.spacing_m)
    vec = {}
    for m, a in members.items():
        v = (state_phi(s, p, m, a).astype(np.float64) - state_phi(s, p, m, -a).astype(np.float64))[band] / 2
        vec[m] = v / np.linalg.norm(v)
    names = list(vec)
    sv = np.linalg.svd(np.stack([vec[m] for m in names]), compute_uv=False) if names else np.zeros(0)
    return {"abs_cos": {m: {n: float(abs(vec[m] @ vec[n])) for n in vec} for m in vec}, "singular_values": sv.tolist()}


def basis(rows, s, p) -> dict:
    """§5, applied once (plan rev. 2).  A* = largest ladder amplitude with both signs gate-clean; a wide mode also needs max displacement >= 5 mm and
    support >= 0.5 at both signs; controls need only gate-clean pairs; support probes need one gate-clean state (either sign) at some amplitude."""
    if len(rows) != len(tasks()) or any("error" in r for r in rows):
        return {"verdict": "V18_RUN_INVALID", "errors": [(r["mode"], r["amplitude"], r["error"]) for r in rows if "error" in r]}
    by = {(r["mode"], r["amplitude"]): r for r in rows}
    out = {}
    for mode, amps in AMPS.items():
        cls, ok = CLASS[mode], []
        for a in amps:
            pair = [by[(mode, a)], by[(mode, -a)]]
            if cls.startswith("support") or cls in ("reference", "rough"):
                if any(r["all_pass"] for r in pair):
                    ok.append(a)
                continue
            if all(r["all_pass"] for r in pair) and (cls == "control" or (min(r["support"]["max_band_change_m"] for r in pair) >= MIN_DISPLACEMENT_M
                                                                           and min(r["support"]["fraction"] for r in pair) >= MIN_SUPPORT)):
                ok.append(a)
        out[mode] = {"class": cls, "qualifying_amplitudes": ok, "a_star": max(ok) if ok else None, "failed_amplitudes": [a for a in amps if a not in ok],
                     "gate_clean_signs": {f"{a:g}": [sg for sg in (1, -1) if by[(mode, sg * a)]["all_pass"]] for a in amps}}
    wide = [m for m, v in out.items() if v["class"] == "wide" and v["a_star"] is not None]
    gm = gram(s, p, {m: out[m]["a_star"] for m in wide}) if wide else {"abs_cos": {}, "singular_values": []}
    cos = gm["abs_cos"]
    distinct = []
    for m in wide:  # AMPS order
        if all(cos[m][n] <= COLLINEAR_COS for n in distinct):
            distinct.append(m)
    ctrl = [m for m, v in out.items() if v["class"] == "control" and v["a_star"] is not None]
    support = {c: [m for m, v in out.items() if v["class"] == c and v["a_star"] is not None] for c in ("support-large", "support-medium", "support-small")}
    if not by[("parent", 0.0)]["all_pass"]:
        verdict = "V18_PARENT_FAIL"
    elif len(distinct) >= MIN_WIDE and ctrl and support["support-medium"] and support["support-small"]:
        verdict = "V18_BASIS_READY"
    else:
        verdict = "V18_BASIS_INCOMPLETE"
    return {"rule": "docs/v18_mode01_plan_2026_10_19.md §5", "per_mode": out, "wide_qualifying": wide, "wide_distinct": distinct, "collinear_cos_threshold": COLLINEAR_COS,
            "gram_abs_cos": cos, "gram_singular_values": gm["singular_values"], "controls": ctrl, "support_probes": support, "verdict": verdict,
            "proposed_basis": (distinct + ctrl)[:MAX_BASIS] if verdict == "V18_BASIS_READY" else []}


def table(rows) -> str:
    h = ("| mode | a | class | all gates | failed | N_phi (slack) | support | max disp mm | vol vs parent (smoothed / sharp) | eik med / p95 | min z | max abs vs analytic (m) |\n"
         "|---|---|---|---|---|---|---|---|---|---|---|---|\n")
    out = []
    for r in rows:
        if "error" in r:
            out.append(f"| {r['mode']} | {r['amplitude']:g} | {r['class']} | ERROR | {r['error'][:60]} | | | | | | | |")
            continue
        fails = ",".join(r["failed_geom02"] + r["unmeasured_geom02"] + ([] if r["p22"]["pass"] else ["p22"]) + ([] if r["retained"]["volume_band_pass"] else ["vol_band"])
                         + ([] if r["retained"]["clearance_pass"] else ["clearance"])) or "-"
        out.append(f"| {r['mode']} | {r['amplitude']:g} | {r['class']} | {'PASS' if r['all_pass'] else 'FAIL'} | {fails} | {r['p22']['n_phi']} ({r['p22']['slack']:+d}) | "
                   f"{r['support']['fraction']:.3f} | {1000 * r['support']['max_band_change_m']:.1f} | {100 * r['volume_vs_parent']:+.2f}% / {100 * r['sharp_volume_vs_parent']:+.2f}% | "
                   f"{r['eikonal_median']:.3f} / {r['eikonal_p95']:.3f} | {r['min_zero_level_z_m']:+.4f} | {r['max_abs_vs_analytic_m']:.1e} |")
    return h + "\n".join(out) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--cache", type=Path, help="per-state json cache (resume)")
    args = ap.parse_args()
    todo, done = tasks(), {}
    if args.cache:
        args.cache.mkdir(parents=True, exist_ok=True)
        done = {t: json.loads(f.read_text()) for t in todo if (f := args.cache / f"{t[0]}_{t[1]:+g}.json").exists()}
    with mp.get_context("spawn").Pool(args.workers, initializer=_init) as pool:
        for r in pool.imap_unordered(work, [t for t in todo if t not in done]):
            done[(r["mode"], r["amplitude"])] = r
            if args.cache:
                (args.cache / f"{r['mode']}_{r['amplitude']:+g}.json").write_text(json.dumps(r, sort_keys=True))
            print(r["mode"], r["amplitude"], r.get("all_pass", r.get("error")), flush=True)
    rows = [done[t] for t in todo]
    g = json.loads((GENESIS / "genesis.json").read_text())
    meta = {"kind": "mode01_v18_prescreen", "evidence_tier": "EXPLORATORY_COMMITTED", "plan": "docs/v18_mode01_plan_2026_10_19.md", "parent": g["state"], "parameters": g["parameters"],
            "units": V.UNITS, "amplitudes": AMPS, "classes": CLASS, "n_max": P.N_MAX, "volume_band_base": "v17 baseline smoothed volume (unchanged)",
            "support_definition": "fraction of active interface-band nodes (|parent phi| <= 2h) with |dphi| > 10 % of the band maximum (MODE-01)",
            "basis_thresholds": {"min_max_displacement_m": MIN_DISPLACEMENT_M, "min_support": MIN_SUPPORT, "min_wide_members": MIN_WIDE, "max_basis": MAX_BASIS}, "solver_started": False}
    OUT.mkdir(parents=True, exist_ok=True)
    s, p = load_parent()
    result = {"meta": meta, "states": rows, "basis": basis(rows, s, p)}
    (OUT / "prescreen.json").write_text(json.dumps(result, sort_keys=True, indent=1) + "\n")
    (OUT / "prescreen_table.md").write_text(table(rows))
    print(table(rows))
    print(json.dumps(result["basis"], indent=1))


if __name__ == "__main__":
    main()
