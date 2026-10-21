#!/usr/bin/env python3
"""FID-01 (#62, M3a) operating characteristics of the registered rules (§6.10): synthetic studies through the frozen analyzer (`analyze_fid01.evaluate`,
`extension_eval`), including the §6.8 extension.  Solver-free; the noise model and its sources are in the registration; the output is a planning
statement about the rules, not evidence about the physics.

    python scripts/fid01/fid01_oc.py [--reps 200] --out docs/evidence/fid01_2026_10_21/oc.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts"), str(ROOT / "scripts/fid01")]
import analyze_fid01 as F  # noqa: E402

# planning mix of |Delta_WL| (N): tier A, tier B and two support designs; signs alternate; families cycle (assumption, not data)
MIX = [1.5e-2, 1.3e-2, 1.2e-2, 1.0e-2, 1.0e-2, 8e-3, 7e-3, 6e-3, 6e-3, 4e-3, 3e-3, 2.2e-3]
FAMS = ["combination", "section", "rigid", "section", "combination", "rigid", "combination", "section", "rigid", "span", "rigid", "span"]
SIGNS = [1, -1, 1, -1, 1, -1, 1, 1, -1, 1, -1, 1]
TAGS = {"V1": [f"{i}{m}" for i in range(49, 65) for m in "pm"], "V2": ["49p", "49m", "50p", "50m"], "V3": ["49p"]}
EXT = {"V1": [f"{i}{m}" for i in range(65, 73) for m in "pm"], "V2": ["51p", "51m", "52p", "52m"], "V3": ["49m"]}


def wl_sigma(d):
    """M2 descriptive fit of sigma_d(Delta) on flow_32 (analysis.md): 9.7e-5 N at 1e-3 N, slope 0.48 in log-log."""
    return 9.7e-5 * (abs(d) / 1e-3) ** 0.48


def study(rng, rho, tau, sigma0, v23_factor, mirror_corr=0.0):
    designs = {f"d{i}": ("wide", FAMS[i], SIGNS[i] * MIX[i]) for i in range(len(MIX))}
    srec = {F.PARENT: {"slot": None}, F.ROLL: {"slot": None}}
    srec.update({n: {"slot": f"S{n}", "stratum": st, "family": fam, "spec": {}} for n, (st, fam, _) in designs.items()})
    true_rho = {n: {L: rho[L] + tau * z for L in rho} for n, z in zip(designs, rng.standard_normal(len(designs)))}
    forces = {F.PARENT: {f"k{k}": {"downforce": 0.26 + 1.3e-3 * rng.standard_normal(), "drag": 0.27} for k in (7, 8, 9, 10)}}
    for n, (_, _, d) in designs.items():
        forces[n] = {t: {"downforce": f["downforce"] + d + wl_sigma(d) * rng.standard_normal(), "drag": f["drag"] + 0.3 * abs(d) + wl_sigma(d) * rng.standard_normal()}
                     for t, f in forces[F.PARENT].items()}
    forces[F.ROLL] = {t: {"downforce": f["downforce"] - 1.648e-3 + 2.09e-4 * rng.standard_normal(), "drag": f["drag"]} for t, f in forces[F.PARENT].items()}
    wl = F.wl_diffs(forces)

    def shifts(tags, L, vals):
        s = sigma0 * (1.0 if L == "V1" else v23_factor)
        for i in sorted({t[:-1] for t in tags}):
            ms = [m for m in "pm" if f"{i}{m}" in tags]
            p0 = 0.2 + 1e-3 * rng.standard_normal()
            for m in ms:
                vals[(F.PARENT, f"{i}{m}")] = {"downforce": p0, "drag": 0.34}
            for n, (_, _, d) in designs.items():
                a, b = rng.standard_normal(2)
                e = {"p": s * a, "m": s * (mirror_corr * a + np.sqrt(1 - mirror_corr ** 2) * b)}
                for m in ms:
                    vals[(n, f"{i}{m}")] = {"downforce": p0 + true_rho[n][L] * d + e[m], "drag": 0.34 + 0.75 * 0.3 * abs(d) + e[m]}
            if L == "V1":
                for m in ms:
                    vals[(F.ROLL, f"{i}{m}")] = {"downforce": p0 - 6.61e-4 + 2.3e-4 * rng.standard_normal(), "drag": 0.34}
        return vals
    vals = {L: shifts(TAGS[L], L, {}) for L in TAGS}
    export = {f"{n}|r8": {"pass": True, "stl_volume_vs_parent": 0.0, "sdf_smoothed_volume_vs_parent": 0.0} for n in designs}
    out, _ = F.evaluate(srec, wl, vals, export)
    final = out["outcome"]
    if final == "EXTENSION_REQUIRED":
        ext_vals = {L: dict(v) for L, v in vals.items()}
        for L in out["extension_plan"]:
            shifts(EXT[L], L, ext_vals[L])
        final = F.extension_eval(json.loads(json.dumps(F.A.clean(out))), srec, wl, ext_vals, export)["outcome"]
    return out["outcome"], final


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reps", type=int, default=200)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    good = {"V1": 0.67, "V2": 0.75, "V3": 0.80}
    scenarios = [(f"rho {r['V1']}/{r['V2']}/{r['V3']} tau {tau} sigma0 {s0:g} V2/V3 noise x{f:g} mirror corr {mc:g}", r, tau, s0, f, mc)
                 for r in (good, {"V1": 0.67, "V2": 0.67, "V3": 0.67}) for tau in (0.0, 0.08, 0.15) for s0 in (4e-4, 7e-4, 1.2e-3) for f, mc in ((0.7, 0.0), (1.0, -0.5))]
    scenarios += [(f"BAD rho {v} everywhere tau 0.08 sigma0 {s0:g}", {"V1": v, "V2": v, "V3": v}, 0.08, s0, 1.0, 0.0) for v in (0.45, 0.3) for s0 in (4e-4, 1.2e-3)]
    scenarios += [(f"BAD mesh: V3 at 0.35 of WL, V1 0.67 sigma0 {s0:g}", {"V1": 0.67, "V2": 0.6, "V3": 0.35}, 0.08, s0, 1.0, 0.0) for s0 in (4e-4, 1.2e-3)]
    rng = np.random.default_rng(20261021)
    res = {}
    for name, rho, tau, s0, f, mc in scenarios:
        cnt, first = {}, {}
        for _ in range(a.reps):
            o1, o2 = study(rng, rho, tau, s0, f, mc)
            cnt[o2] = cnt.get(o2, 0) + 1
            first[o1] = first.get(o1, 0) + 1
        res[name] = {"final": {k: v / a.reps for k, v in sorted(cnt.items())}, "main_analysis": {k: v / a.reps for k, v in sorted(first.items())}}
        print(name, res[name]["final"], flush=True)
    rec = {"kind": "fid01_operating_characteristics", "reps": a.reps, "seed": 20261021, "analyzer_sha256": F.SC.sha256_path(F.__file__),
           "mix_abs_delta_n": MIX, "wl_sigma_model": "9.7e-5 (|Delta|/1e-3)^0.48 N (M2 fit)", "of_noise": "per-shift SD sigma0 on V1; V2/V3 sigma0 x factor; mirror correlation as listed",
           "scenarios": res}
    a.out.write_text(json.dumps(rec, indent=1, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
