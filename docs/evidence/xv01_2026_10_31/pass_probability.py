#!/usr/bin/env python3
"""XV-01 (#65) planning only: expected pass probability of the registered XV rules for the frozen SCREEN-01 finalist, before any case is funded.

Reads visible records only (SCREEN-01 handoff and rs.json, FID-01 analysis.json, M2 analysis.json); no OpenFOAM force of the finalist exists.
Writes pass_probability.json beside this file.  Revision 1 (plan review N1-N3, N7, S3, G11).  Three parts:
  s57        the SCREEN §5.7 projection as probabilities: the V1 gain floor (GAIN_V1) and the G4 retention bound (Delta_V1 >= 0.5 Delta_32);
  scenarios  a component model under structural variants: the finalist's WaterLily response split by the SCREEN response surface into
             pitch / camber / reflex / cross / rest, each part carried to OpenFOAM V1/V2/V3 with the retention vector of a FID design of its
             family (bootstrap), then the registered rules (registration §5) applied;
  ablations  the registered rules against each rejected alternative (decision memo D1-D5), on the reference scenario.
G1, G2, G5, EX and the chain controls (NC, REF, determinism) are not modelled (near-certain passes): every P(PASS) here is an upper bound.
"""
import json
import math
from pathlib import Path

import numpy as np
from scipy import stats

ROOT = Path(__file__).resolve().parents[3]
SCR = ROOT / "docs/evidence/screen01_2026_10_30"
FID = ROOT / "docs/evidence/fid01_2026_10_21/analysis.json"
SEED, N = 20261031, 20000
G_OF, J48 = 0.012674959854238867, 0.26577921974115387
X_OF = G_OF * J48                                               # registration §5.2 (frozen constant)
F_PARENT = {"V1": 0.20186, "V2": 0.2062, "V3": 0.2124}          # FID OpenFOAM parent downforce (N); only for the OpenFOAM-normaliser ablation
FLOOR = {"downforce": 1.984576864434452e-4, "drag": 1.3747177622390572e-4}   # FID V2 pooled pair SD (registration §5.1)
PAIR_SD = {("V1", "downforce"): 1.0e-3, ("V1", "drag"): 5.0e-4,  # planning pair-unit SDs: FID V1 own-pair SDs of camber/reflex designs;
           ("V2", "downforce"): 2.0e-4, ("V2", "drag"): 1.4e-4,  # V2/V3 at the floor scale (V3 x k in the SE-sensitivity scenarios)
           ("V3", "downforce"): 2.0e-4, ("V3", "drag"): 1.4e-4}
NPAIR = {"V1": 16, "V2": 4, "V3": 4}
DELTA_MAT = 5.397769910001766e-4                                # SCREEN drag SE_eff of the finalist: materiality label only (§5.3)
FAMILIES = {"pitch": ["v18__pitch_p0.7", "v18__pitch_m0.7"], "camber": ["v18__camber_m11.3", "v18__camber_m19.7"],
            "reflex": ["v18__reflex_m29.3"]}
LEVELS, RESP = ("V1", "V2", "V3"), ("downforce", "drag")
REF = {"tau": 0.08, "tau_drag": 0.08, "ext_common": 0.10, "ext_level": 0.0, "v3_se": 1.0, "bk": "central", "ret_scale": 1.0,
       "reflex_drag": 1.0, "camber": None, "reflex": None, "trend": False}
SCENARIOS = {
    "reference (b_K central)": {},
    "no selection shift": {"bk": None},
    "b_K upper, family retentions": {"bk": "upper"},
    "s57 pessimistic (retentions x 0.57/0.655, b_K upper)": {"bk": "upper", "ret_scale": 0.57 / 0.655},
    "camber per-level extension noise 0.15": {"ext_level": 0.15},
    "camber per-level extension noise 0.25": {"ext_level": 0.25},
    "camber retention amplitude trend (linear in amplitude to -29.55 mm)": {"trend": True},
    "camber source -19.7 only": {"camber": ["v18__camber_m19.7"]},
    "camber source -11.3 only": {"camber": ["v18__camber_m11.3"]},
    "reflex drag retention x 0.8": {"reflex_drag": 0.8},
    "reflex drag retention x 1.2": {"reflex_drag": 1.2},
    "reflex source C4 (pitch -1.3, reflex +29.3, sweep +11.3)": {"reflex": ["v18__pitch_m1.3_reflex_p29.3_sweep_p11.3"]},
    "drag retention spread tau_drag 0.25": {"tau_drag": 0.25},
    "V3 pair SD x 2": {"v3_se": 2.0},
    "V3 pair SD x 4": {"v3_se": 4.0},
}


def contributions(h, rs):
    """WaterLily parts of the finalist's confirmation difference (N): surface terms by mode, the cross terms, and the rest (measured - fit)."""
    p, c, r = h["u"]
    x = np.array([p, c, r, p * p, c * c, r * r, p * c, p * r, c * r])   # screen01_pool.quad9 order
    out = {}
    for resp in RESP:
        t = np.array(rs["comparable"]["fit"][resp]["coef"]) * x
        parts = {"pitch": t[0] + t[3], "camber": t[1] + t[4], "reflex": t[2] + t[5], "cross": t[6] + t[7] + t[8]}
        parts["rest"] = h["confirmation"]["f32"]["delta_bar"][resp] - sum(parts.values())
        out[resp] = parts
    return out


def ratios(a, names):
    wl, of = a["wl_flow32"], a["of"]
    return [{(lev, resp): of[lev][n][resp]["delta_bar_n"] / wl[n][resp]["delta_bar_n"] for lev in LEVELS for resp in RESP} for n in names]


def retention_table(a, opt):
    """family -> list of {(level, resp): OF / WL} for whole FID designs (each design's cross-level pattern kept); cross and rest use the tier-A
    through-origin slope per level and response."""
    tab = {f: ratios(a, opt.get(f) or ns) for f, ns in FAMILIES.items()}
    if opt["trend"]:   # camber retention extrapolated linearly in amplitude from -11.3 and -19.7 mm to -29.55 mm, clipped to [0.3, 1.5]
        lo, hi = ratios(a, FAMILIES["camber"])
        tab["camber"] = [{k: float(np.clip(hi[k] + (hi[k] - lo[k]) * (29.55 - 19.7) / (19.7 - 11.3), 0.3, 1.5)) for k in lo}]
    slope = {}
    for lev in LEVELS:
        for resp in RESP:
            w = np.array([a["wl_flow32"][n][resp]["delta_bar_n"] for n in a["tiers"]["A"]])
            o = np.array([a["of"][lev][n][resp]["delta_bar_n"] for n in a["tiers"]["A"]])
            slope[(lev, resp)] = float(w @ o / (w @ w))
    tab["cross"] = tab["rest"] = [slope]
    return tab


def simulate(parts, tab, h, opt, rng):
    """Replicates of the OpenFOAM level estimates Delta[level][resp], the V1 mean on the 4 common pairs, and the WaterLily value used by G4."""
    f32 = h["confirmation"]["f32"]
    shift = -h["selection_bias"]["b_K"][opt["bk"]] if opt["bk"] else 0.0
    wl = {resp: f32["delta_bar"][resp] + rng.normal(0, f32["se_eff"][resp], N) for resp in RESP}
    common = np.exp(rng.normal(0, opt["ext_common"], N))
    d = {lev: {resp: np.zeros(N) for resp in RESP} for lev in LEVELS}
    for fam, members in tab.items():
        pick = rng.integers(0, len(members), N)
        for resp in RESP:
            base = parts[resp][fam] + ((wl[resp] - f32["delta_bar"][resp] + (shift if resp == "downforce" else 0.0)) if fam == "rest" else 0.0)
            tau = opt["tau_drag"] if resp == "drag" else opt["tau"]
            for lev in LEVELS:
                r = np.array([m[(lev, resp)] for m in members])[pick] * np.exp(rng.normal(0, tau, N)) * opt["ret_scale"]
                if fam == "camber":
                    r = r * common * np.exp(rng.normal(0, opt["ext_level"], N))
                if fam == "reflex" and resp == "drag":
                    r = r * opt["reflex_drag"]
                d[lev][resp] += base * r
    sd = {k: v * (opt["v3_se"] if k[0] == "V3" else 1.0) for k, v in PAIR_SD.items()}
    est = {lev: {resp: d[lev][resp] + rng.normal(0, sd[(lev, resp)] / math.sqrt(NPAIR[lev]), N) for resp in RESP} for lev in LEVELS}
    v1c = d["V1"]["downforce"] + rng.normal(0, sd[("V1", "downforce")] / 2, N)   # V1 on the 4 common pairs (registration §5.5)
    return est, v1c, wl, sd


def se(sd, lev, resp, pairs=None):
    n = pairs or NPAIR[lev]
    return (sd[(lev, resp)] if lev == "V1" else max(sd[(lev, resp)], FLOOR[resp])) / math.sqrt(n)


def rules(est, v1c, wl, h, sd, alt=None):
    """Rule masks (PASS, FAIL, FAIL-class): FAIL-class False marks a resolved exceedance that the registration classifies UNRESOLVED (§5.5)."""
    tq = lambda n: stats.t.ppf(0.95, n - 1)  # noqa: E731
    npair = dict(NPAIR, **({"V2": 2, "V3": 2} if alt == "A_2pairs" else {}))
    out = {}
    for lev in LEVELS:
        n = npair[lev]
        s, D = se(sd, lev, "downforce", n), est[lev]["downforce"]
        if alt == "copy_residual" and lev == "V3":
            s = 1.4474126675928642e-3
        x = G_OF * F_PARENT[lev] if alt == "of_normaliser" else X_OF
        out[f"GAIN_{lev}"] = ((D >= x) & (D > 3 * s), D + tq(n) * s < x, True)
        Dr, sr = est[lev]["drag"], se(sd, lev, "drag", n)
        if alt == "drag_point_sign":
            out[f"DRAG_{lev}"] = (Dr <= 0, Dr - tq(n) * sr > 0, True)
        elif alt == "drag_v1_only" and lev != "V1":
            continue
        elif alt == "drag_margin":
            out[f"DRAG_{lev}"] = (Dr + tq(n) * sr <= DELTA_MAT, Dr - tq(n) * sr > DELTA_MAT, True)
        else:
            out[f"DRAG_{lev}"] = (Dr + tq(n) * sr <= 0, Dr - tq(n) * sr > 0, True)
    v1, v2 = est["V1"]["downforce"], est["V2"]["downforce"]
    s1, s2 = se(sd, "V1", "downforce"), se(sd, "V2", "downforce", npair["V2"])
    m, R, sR = (v1 + v2) / 2, np.abs(v1 - v2), math.hypot(s1, s2)
    out["G3_V1V2"] = (R <= 0.5 * np.abs(m), R - 2 * sR > 0.5 * np.abs(m), True)
    w, sw, t3 = wl["downforce"], h["confirmation"]["f32"]["se_eff"]["downforce"], tq(4)
    out["G4_V1"] = ((v1 / w >= 0.5) & (v1 / w <= 2.0), (v1 + t3 * s1 < 0.5 * (w - t3 * sw)) | (v1 - t3 * s1 > 2 * (w + t3 * sw)), True)
    n3 = npair["V3"]
    v3, s3, s1p = est["V3"]["downforce"], sd[("V3", "downforce")], sd[("V1", "downforce")]
    se_lo = max(math.hypot(s3, 0.6 * s1p), FLOOR["downforce"]) / math.sqrt(n3)        # pair-level margin SEs (plan review N3)
    se_hi = max(math.hypot(s3, s1p / 0.6), FLOOR["downforce"]) / math.sqrt(n3)
    lo, hi, tb = v3 - 0.6 * v1c, v1c / 0.6 - v3, tq(n3)
    if alt == "v3_whole_interval":
        out["V3_LOW"] = (lo - tb * se_lo >= 0, lo + tb * se_lo < 0, True)
        out["V3_HIGH"] = (hi - tb * se_hi >= 0, hi + tb * se_hi < 0, False)
    else:
        out["V3_LOW"] = (lo >= 0, lo + tb * se_lo < 0, True)
        if alt != "v3_one_sided":
            out["V3_HIGH"] = (hi >= 0, hi + tb * se_hi < 0, False)   # upper side: point-pass required, resolved exceedance UNRESOLVED
    return out


def summarise(out, est, sd):
    allpass = np.logical_and.reduce([v[0] for v in out.values()])
    fail = np.logical_or.reduce([v[1] for v in out.values() if v[2]])
    core = np.logical_and.reduce([v[0] for k, v in out.items() if k.startswith(("GAIN", "DRAG"))])
    tq = lambda n: stats.t.ppf(0.95, n - 1)  # noqa: E731
    drag_below_mat = np.logical_and.reduce([est[lev]["drag"] + tq(NPAIR[lev]) * se(sd, lev, "drag") <= DELTA_MAT for lev in LEVELS])
    return {"rules": {k: {"pass": float(v[0].mean()), "fail": float(v[1].mean())} for k, v in out.items()},
            "XV01_PASS": float(allpass.mean()), "XV01_FAIL": float((~allpass & fail).mean()),
            "XV01_UNRESOLVED": float((~allpass & ~fail).mean()), "XV_OF_CORE": float(core.mean()),
            "drag_not_pass_but_below_materiality": float((~np.logical_and.reduce([out[f"DRAG_{l}"][0] for l in LEVELS if f"DRAG_{l}" in out])
                                                          & drag_below_mat).mean()),
            "median_n": {lev: {r: float(np.median(est[lev][r])) for r in RESP} for lev in LEVELS}}


def s57(h):
    """§5.7 numbers as probabilities: mean = retention (Delta - b_K), SD = sigma_disc (+ WL and V1 SE); thresholds x_OF and the G4 PASS bound."""
    sb, f32 = h["selection_bias_inputs"], h["confirmation"]["f32"]
    g4 = 0.5 * f32["delta_bar"]["downforce"]
    out = {}
    for case, ret, b in (("central", "central", "central"), ("pessimistic", "pessimistic", "upper")):
        r = sb["retention"][ret]
        mean = r * (f32["delta_bar"]["downforce"] - h["selection_bias"]["b_K"][b])
        sdev = math.sqrt(sb["sigma_disc"]["central" if b == "central" else "upper"] ** 2 + (r * f32["se_eff"]["downforce"]) ** 2 + 2.5e-4 ** 2)
        out[case] = {"expected_V1_gain_n": mean, "expected_V1_gain_pct_J48": 100 * mean / J48, "expected_rho": mean / f32["delta_bar"]["downforce"],
                     "sd_n": sdev, "p_gain_v1_clears_x_of": float(stats.norm.sf((X_OF - mean) / sdev)),
                     "p_gain_v1_clears_g_of_F_parent_V1": float(stats.norm.sf((G_OF * F_PARENT["V1"] - mean) / sdev)),
                     "p_g4_pass_bound": float(stats.norm.sf((g4 - mean) / sdev))}
    return out


def run(parts, a, h, opt, alt=None):
    o = dict(REF, **opt)
    est, v1c, wl, sd = simulate(parts, retention_table(a, o), h, o, np.random.default_rng(SEED))
    return summarise(rules(est, v1c, wl, h, sd, alt), est, sd)


def main():
    h = json.loads((SCR / "xv_handoff.json").read_text())
    rs = json.loads((SCR / "rs.json").read_text())
    a = json.loads(FID.read_text())
    parts = contributions(h, rs)
    res = {"kind": "xv01_pass_probability_planning", "revision": 1, "seed": SEED, "replicates": N,
           "evidence_class": "planning projection, no outcome effect; P(PASS) is an upper bound (G1, G2, G5, EX, NC, REF, determinism not modelled)",
           "x_of_n": X_OF, "delta_mat_n": DELTA_MAT, "s57": s57(h), "components_n": parts,
           "assumptions": {"reference": REF, "pair_sd": {f"{a_}/{b}": v for (a_, b), v in PAIR_SD.items()}, "floor": FLOOR, "pairs": NPAIR},
           "scenarios": {k: run(parts, a, h, v) for k, v in SCENARIOS.items()},
           "ablations": {alt: run(parts, a, h, {}, alt) for alt in
                         ("registered", "drag_point_sign", "drag_v1_only", "drag_margin", "v3_one_sided", "v3_whole_interval", "of_normaliser",
                          "A_2pairs", "copy_residual")}}
    res["ablations"]["registered"]["note"] = "the registered rules on the reference scenario (equals scenarios['reference (b_K central)'])"
    Path(__file__).with_suffix(".json").write_text(json.dumps(res, indent=1, sort_keys=True) + "\n")
    print(json.dumps(res["s57"], indent=1))
    for grp in ("scenarios", "ablations"):
        for k, v in res[grp].items():
            print(f"{grp[:4]} {k[:62]:62s} PASS {v['XV01_PASS']:.3f} FAIL {v['XV01_FAIL']:.3f} UNRES {v['XV01_UNRESOLVED']:.3f} "
                  f"CORE {v['XV_OF_CORE']:.3f} drag<mat {v['drag_not_pass_but_below_materiality']:.3f} "
                  f"DRAG_V3 {v['rules'].get('DRAG_V3', {}).get('pass', float('nan')):.2f}/{v['rules'].get('DRAG_V3', {}).get('fail', float('nan')):.2f} "
                  f"V3H {v['rules'].get('V3_HIGH', {}).get('pass', float('nan')):.2f} G4 {v['rules']['G4_V1']['pass']:.2f}/{v['rules']['G4_V1']['fail']:.2f}")


if __name__ == "__main__":
    main()
