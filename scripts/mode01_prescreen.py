#!/usr/bin/env python3
"""MODE-01 (#60) solver-free prescreen (EXPLORATORY_COMMITTED): every (mode, amplitude) state against the 13 GEOM-02 profile-v2 gates, P22-v2
(N_phi <= 8272), the retained LOWDIM gates (smoothed volume band vs the v17 baseline, clearance 0.15 m), mask preservation, SDF quality and support.
For states over the P22 cap a final scalar offset projection (phi - delta on active nodes, delta by bisection) is PROPOSED and re-gated; nothing is registered.

    python scripts/mode01_prescreen.py [--family opt01|regen6p25] [--workers 8] [--cache DIR]   # writes docs/evidence/mode01_prescreen_2026_10_16/prescreen[_FAMILY].{json,md}

Families: ``opt01`` = the registered OPT-01 v1 parent (P22 cap 8272, volume band vs the v17 baseline).  ``regen6p25`` = a DIAGNOSTIC re-genesis parent phi - 6.25 mm
on every node (moves the zero-level plateau of the parent a half cell off the lattice nodes) with the design mask widened by the two end-plane y layers the offset
turns solid; its own N_phi is the P22 cap and its own volume the band base.  A re-genesis would be a new problem registration (mask, P22 cap, volume base).
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
from cfd_sdf.design.sdf_state import SDFDesignState  # noqa: E402

OUT = ROOT / "docs/evidence/mode01_prescreen_2026_10_16"
AMPS = {"pitch": (0.5, 1, 2, 3), "heave": (5, 10, 20, 30), "surge": (5, 10, 25, 30), "camber": (5, 10, 20, 30), "thickness": (1, 2, 3, 5), "aspect": (0.01, 0.02, 0.04),
        "bump_lower": (2, 5, 10), "bump_upper": (2, 5, 10), "bump_small": (2, 5, 10), "D1_filtered_seed11": (1, 2, 5), "P1_upstream_lobe": (1, 2, 5)}
CLASS = {"pitch": "wide", "heave": "wide", "surge": "control", "camber": "wide", "thickness": "wide", "aspect": "wide", "bump_lower": "medium", "bump_upper": "medium",
         "bump_small": "small", "D1_filtered_seed11": "small-ref", "P1_upstream_lobe": "small-ref"}
AMPS_REGEN = {"pitch": (0.5, 1, 2), "heave": (10, 30), "surge": (10, 30), "camber": (10, 30), "thickness": (2, 5), "aspect": (0.01, 0.02), "bump_lower": (5, 10),
              "bump_upper": (5, 10), "bump_small": (5,), "D1_filtered_seed11": (2,), "P1_upstream_lobe": (2,)}
REGEN_SHIFT_M = -0.00625   # phi + shift on every node: a quarter cell, off the node planes and off the cell centres
N_MAX = 8272
G: dict = {}


def tasks(family: str = "opt01") -> list[tuple[str, float]]:
    return [("parent", 0.0)] + [(m, s * a) for m, amps in (AMPS if family == "opt01" else AMPS_REGEN).items() for a in amps for s in (1, -1)]


def regen_parent(p):
    """Diagnostic re-genesis: phi - 6.25 mm on every node and the design mask widened by the two end-plane y layers (|y| = 0.45), which the offset turns solid."""
    dm = p.design_mask.copy()
    dm[:, [14, 50], :] = p.design_mask[:, [15, 49], :]
    return SDFDesignState.create(phi=(p.phi.astype(np.float64) + REGEN_SHIFT_M).astype("<f4"), origin_m=p.origin_m, spacing_m=p.spacing_m, design_mask=dm, fixed_solid_mask=p.fixed_solid_mask,
                                 forbidden_mask=p.forbidden_mask, root_mask=p.root_mask, narrow_band_width_m=p.narrow_band_width_m, generation=p.generation,
                                 source_sha256=p.source_sha256, topology_policy_id=p.topology_policy_id, reinitialization_policy_id=p.reinitialization_policy_id)


def _init(family: str = "opt01") -> None:
    import evaluate_opt01_v1_states as ev  # heavy gate stack, imported once per worker
    profile = json.loads(ev.reg1.PROFILE.read_text())
    parent = M.load_parent()
    if family == "opt01":
        base_geom, n_max = ev.lowdim.geometry(ev.SDFDesignState.load(ev.canon.INPUTS / "v17_baseline.npz")), N_MAX
    else:
        parent = regen_parent(parent)
        base_geom, n_max = ev.lowdim.geometry(parent), count(parent, parent.phi)
    G.update(ev=ev, parent=parent, profile={**profile, "max_solid_centers": n_max}, n_max=n_max, base_geom=base_geom, parent_geom=ev.lowdim.geometry(parent),
             policy=ev.SDFTopologyPolicyResearchV2.from_dict(json.loads(ev.reg.POLICY.read_text())["policy"]))


def crossing_slope_failures(phi, h=0.025, threshold=0.5) -> int:
    """Cheap numpy replica of the near_zero_gradient_band count: interior sign-change nodes (phi < 0 solid) whose largest opposite-class slope |dphi|/h is < threshold."""
    sol, best, has = phi < 0, np.zeros(phi.shape), np.zeros(phi.shape, bool)
    for ax in range(3):
        for sh in (1, -1):
            opp, sl = np.roll(sol, sh, ax) != sol, np.abs(phi - np.roll(phi, sh, ax)) / h
            best, has = np.where(opp & (sl > best), sl, best), has | opp
    inner = np.zeros(phi.shape, bool)
    inner[1:-1, 1:-1, 1:-1] = True
    return int((has & inner & (best < threshold)).sum())


def count(s, phi) -> int:
    from cfd_sdf.design.volume_semantics import _corner_mean
    return int((_corner_mean(phi) < 0.0).sum())


def project_p22(s, phi, n_max=N_MAX):
    """Largest delta <= 0 (phi - delta = phi + |delta|, a shrink) with N_phi <= n_max on active nodes; 0 if already feasible; None if even -0.2 m fails."""
    act = M.active_mask(s)
    f = lambda d: np.where(act, phi.astype(np.float64) - d, phi.astype(np.float64)).astype("<f4")  # noqa: E731
    if count(s, phi) <= n_max:
        return 0.0, phi
    lo, hi = -0.2, 0.0
    if count(s, f(lo)) > n_max:
        return None, phi
    for _ in range(60):  # ponytail: plain bisection, 60 halvings of 0.2 m is far below float32 resolution
        mid = 0.5 * (lo + hi)
        lo, hi = (mid, hi) if count(s, f(mid)) <= n_max else (lo, mid)
    return lo, f(lo)


def evaluate(state) -> dict:
    ev, p = G["ev"], G["parent"]
    rec = ev.state_record(state, p, G["profile"], G["policy"], ev.canon.export_from_state(state, G["profile"]), G["base_geom"])
    g, pg = ev.lowdim.geometry(state), G["parent_geom"]
    v, n = rec["geom02_v2"]["verdict"], rec["p22_v2"]["sampled_solid_centers"]
    n_max = G["n_max"]
    return {"all_pass": bool(v["pass"] and n <= n_max and rec["retained_lowdim"]["all_pass"]), "crossing_slope_fail_nodes": crossing_slope_failures(state.phi), "geom02_pass": v["pass"], "failed_geom02": v["failed"], "unmeasured_geom02": v["unmeasured"],
            "gate_status": {k: x["status"] for k, x in rec["geom02_v2"]["gates"].items()},
            "p22": {"n_phi": n, "n_max": n_max, "slack": n_max - n, "pass": n <= n_max},
            "retained": {"volume_vs_gate_base": rec["retained_lowdim"]["relative_smoothed_volume_change"], "volume_band_pass": rec["retained_lowdim"]["gates"]["smoothed_volume_band"],
                         "zero_level_margin_m": rec["retained_lowdim"]["zero_level_margin_m"], "clearance_pass": rec["retained_lowdim"]["gates"]["clearance"]},
            "volume_vs_parent": g["smoothed_volume_m3"] / pg["smoothed_volume_m3"] - 1.0, "sharp_volume_vs_parent": g["sharp_volume_m3"] / pg["sharp_volume_m3"] - 1.0,
            "cell_components": g["cell_components"], "eikonal_median": g["eikonal_median_abs_deviation"], "eikonal_p95": g["eikonal_p95_abs_deviation"],
            "eikonal_max": g["eikonal_max_abs_deviation"], "eikonal_band_nodes": g["eikonal_band_node_count"]}


def work(task) -> dict:
    mode, a = task
    s = G["parent"]
    row = {"mode": mode, "amplitude": a, "class": CLASS.get(mode, "parent")}
    try:
        phi = s.phi.copy() if mode == "parent" else M.mode_phi(s, mode, a)
        st = M.with_phi(s, phi)
        row.update(phi_fortran_sha256=M.phi_fortran_sha(phi), support=M.support_fraction(s, phi), **evaluate(st))
        delta, pphi = project_p22(s, phi, G["n_max"])
        proj = {"delta_mm": None if delta is None else delta * 1000.0, "needed": delta != 0.0}
        if delta:  # re-gate the projected state in full
            peak = row["support"]["max_band_change_m"]
            proj.update(phi_fortran_sha256=M.phi_fortran_sha(pphi), d0_share_of_mode_peak=abs(delta) / peak if peak else None, **evaluate(M.with_phi(s, pphi)))
        row["p22_projection"] = proj
    except Exception as e:  # noqa: BLE001 - a state that cannot even be built is a result
        row["error"] = f"{type(e).__name__}: {e}"
    return row


def table(rows) -> str:
    h = "| mode | a | class | all gates | failed | N_phi (slack) | support | volume vs parent | eik med / p95 | delta_mm -> pass |\n|---|---|---|---|---|---|---|---|---|---|\n"
    out = []
    for r in rows:
        if "error" in r:
            out.append(f"| {r['mode']} | {r['amplitude']:g} | {r['class']} | ERROR | {r['error'][:60]} | | | | | |")
            continue
        pr = r["p22_projection"]
        proj = "-" if not pr["needed"] else ("none" if pr["delta_mm"] is None else f"{pr['delta_mm']:.3f} -> {'PASS' if pr.get('all_pass') else 'FAIL'}")
        fails = ",".join(r["failed_geom02"] + r["unmeasured_geom02"] + (["p22"] if not r["p22"]["pass"] else []) + ([] if r["retained"]["volume_band_pass"] else ["vol_band"])
                         + ([] if r["retained"]["clearance_pass"] else ["clearance"])) or "-"
        out.append(f"| {r['mode']} | {r['amplitude']:g} | {r['class']} | {'PASS' if r['all_pass'] else 'FAIL'} | {fails} | {r['p22']['n_phi']} ({r['p22']['slack']:+d}) | "
                   f"{r['support']['fraction']:.3f} | {100 * r['volume_vs_parent']:+.2f}% | {r['eikonal_median']:.3f} / {r['eikonal_p95']:.3f} | {proj} |")
    return h + "\n".join(out) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--family", choices=("opt01", "regen6p25"), default="opt01")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--cache", type=Path, help="per-state json cache (resume)")
    args = ap.parse_args()
    todo, suffix = tasks(args.family), "" if args.family == "opt01" else "_" + args.family
    done = {}
    if args.cache:
        args.cache.mkdir(parents=True, exist_ok=True)
        for t in todo:
            f = args.cache / f"{t[0]}_{t[1]:+g}.json"
            if f.exists():
                done[t] = json.loads(f.read_text())
    with mp.get_context("spawn").Pool(args.workers, initializer=_init, initargs=(args.family,)) as pool:
        for r in pool.imap_unordered(work, [t for t in todo if t not in done]):
            done[(r["mode"], r["amplitude"])] = r  # keys are the task tuples
            if args.cache:
                (args.cache / f"{r['mode']}_{r['amplitude']:+g}.json").write_text(json.dumps(r, sort_keys=True))
            print(r["mode"], r["amplitude"], r.get("all_pass", r.get("error")), flush=True)
    rows = [done[t] for t in todo]
    OUT.mkdir(parents=True, exist_ok=True)
    meta = {"kind": "mode01_prescreen", "evidence_tier": "EXPLORATORY_COMMITTED", "parent": str(M.PARENT.relative_to(ROOT)), "parent_phi_fortran_sha256": M.PARENT_PHI_FORTRAN_SHA,
            "family": args.family, "regen_phi_shift_m": REGEN_SHIFT_M if args.family != "opt01" else None, "n_max_opt01": N_MAX, "units": M.UNITS,
            "amplitudes": AMPS if args.family == "opt01" else AMPS_REGEN, "classes": CLASS, "sigma_m": {"medium": M.SIGMA_M, "small": M.SIGMA_SMALL_M}, "taper_m": M.TAPER_M,
            "support_definition": "fraction of active interface-band nodes (|parent phi| <= 2h) with |dphi| > 10 % of the band maximum",
            "projection": "delta <= 0 largest with N_phi(phi - delta on active nodes) <= the family cap; PROPOSAL only, not registered", "solver_started": False}
    (OUT / f"prescreen{suffix}.json").write_text(json.dumps({"meta": meta, "states": rows}, sort_keys=True, indent=1) + "\n")
    (OUT / f"prescreen_table{suffix}.md").write_text(table(rows))
    print(table(rows))


if __name__ == "__main__":
    main()
