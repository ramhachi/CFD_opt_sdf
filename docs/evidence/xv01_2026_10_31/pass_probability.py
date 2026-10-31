#!/usr/bin/env python3
"""XV-01 (#65) planning only: expected pass probability of the registered XV rules for the frozen SCREEN-01 finalist, before any case is funded.

Reads visible records only (SCREEN-01 handoff and rs.json, FID-01 analysis.json); no OpenFOAM force of the finalist exists.  Writes
pass_probability.json beside this file.  Two parts:
  s57   the SCREEN §5.7 projection turned into a probability for the V1 gain floor (Gaussian; central and pessimistic, as §5.7 defines them);
  comp  a component model: the finalist's WaterLily response split by the SCREEN response surface into pitch / camber / reflex / rest, each part
        carried to OpenFOAM V1/V2/V3 with the retention vector of a FID design of that family (bootstrap over designs, multiplicative noise),
        then every registered XV rule applied (registration §6).  Assumptions are the module constants; none is a measured XV quantity.
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
F_PARENT = {"V1": 0.2017, "V2": 0.2062, "V3": 0.2124}          # FID-01 OpenFOAM parent downforce (N), visible; x_OF uses max(J48, F)
TAU, EXT = 0.08, 0.10                                           # design-to-design retention spread; extra camber-extension factor (planning)
SE_PLAN = {("V1", "downforce"): 2.5e-4, ("V1", "drag"): 1.0e-4,   # planning SEs (FID V1 own-pair SEs; V2/V3: floor / sqrt(4))
           ("V2", "downforce"): 1.0e-4, ("V2", "drag"): 0.7e-4, ("V3", "downforce"): 1.0e-4, ("V3", "drag"): 0.7e-4}
V1_PAIR_SD = 1.0e-3                                             # FID camber designs' V1 pair-mean SD (7.5e-4 .. 1.3e-3): V1 on the 4 common pairs
FAMILIES = {"pitch": ["v18__pitch_p0.7", "v18__pitch_m0.7"], "camber": ["v18__camber_m11.3", "v18__camber_m19.7"],
            "reflex": ["v18__reflex_m29.3"]}
LEVELS, RESP = ("V1", "V2", "V3"), ("downforce", "drag")


def contributions(h, rs):
    """WaterLily parts of the finalist's confirmation difference (N): surface terms by mode, the cross terms, and the rest (measured - fit)."""
    p, c, r = h["u"]
    x = np.array([p, c, r, p * p, c * c, r * r, p * c, p * r, c * r])
    out = {}
    for resp in RESP:
        t = np.array(rs["comparable"]["fit"][resp]["coef"]) * x
        parts = {"pitch": t[0] + t[3], "camber": t[1] + t[4], "reflex": t[2] + t[5], "cross": t[6] + t[7] + t[8]}
        parts["rest"] = h["confirmation"]["f32"]["delta_bar"][resp] - sum(parts.values())
        out[resp] = parts
    return out


def retention_table(a):
    """family -> list of {(level, resp): OF / WL} for whole FID designs (keeps each design's cross-level pattern); 'rest' and 'cross' use the
    tier-A through-origin slope per level and response."""
    wl, of = a["wl_flow32"], a["of"]
    ratio = lambda n, lev, resp: of[lev][n][resp]["delta_bar_n"] / wl[n][resp]["delta_bar_n"]  # noqa: E731
    tab = {f: [{(lev, resp): ratio(n, lev, resp) for lev in LEVELS for resp in RESP} for n in ns] for f, ns in FAMILIES.items()}
    slope = {}
    for lev in LEVELS:
        for resp in RESP:
            w = np.array([wl[n][resp]["delta_bar_n"] for n in a["tiers"]["A"]])
            o = np.array([of[lev][n][resp]["delta_bar_n"] for n in a["tiers"]["A"]])
            slope[(lev, resp)] = float(w @ o / (w @ w))
    tab["cross"] = tab["rest"] = [slope]
    return tab


def simulate(parts, tab, h, rng, wl_shift=0.0):
    """Replicates of the OpenFOAM differences Delta[level][resp] (N) and the WaterLily confirmation value used by G4."""
    f32 = h["confirmation"]["f32"]
    d = {lev: {resp: np.zeros(N) for resp in RESP} for lev in LEVELS}
    wl = {resp: f32["delta_bar"][resp] + rng.normal(0, f32["se_eff"][resp], N) for resp in RESP}
    ext = np.exp(rng.normal(0, EXT, N))
    for fam, members in tab.items():
        pick = rng.integers(0, len(members), N)
        for resp in RESP:
            base = parts[resp][fam] + (wl[resp] - f32["delta_bar"][resp] + (wl_shift if resp == "downforce" else 0.0) if fam == "rest" else 0.0)
            for lev in LEVELS:
                r = np.array([m[(lev, resp)] for m in members])[pick] * np.exp(rng.normal(0, TAU, N)) * (ext if fam == "camber" else 1.0)
                d[lev][resp] += base * r
    for lev in LEVELS:
        for resp in RESP:
            d[lev][resp] += rng.normal(0, SE_PLAN[(lev, resp)], N)
    return d, wl


def rules(d, wl, h):
    """The registered XV rules (§6.3-6.6) on planning SEs: per rule a PASS / FAIL mask (else UNRESOLVED)."""
    t15, t3 = stats.t.ppf(0.95, 15), stats.t.ppf(0.95, 3)
    tl = {"V1": t15, "V2": t3, "V3": t3}
    se = lambda lev, resp: SE_PLAN[(lev, resp)]  # noqa: E731
    out = {}
    for lev in LEVELS:
        x, s, D = G_OF * max(J48, F_PARENT[lev]), se(lev, "downforce"), d[lev]["downforce"]
        out[f"GAIN_{lev}"] = (D >= x) & (D > 3 * s), D + tl[lev] * s < x
        Dr, sr = d[lev]["drag"], se(lev, "drag")
        out[f"DRAG_{lev}"] = Dr + tl[lev] * sr <= 0, Dr - tl[lev] * sr > 0
    v1, v2, s1, s2 = d["V1"]["downforce"], d["V2"]["downforce"], se("V1", "downforce"), se("V2", "downforce")
    m, R, sR = (v1 + v2) / 2, np.abs(v1 - v2), math.hypot(s1, s2)
    out["G3_V1V2"] = R <= 0.5 * np.abs(m), R - 2 * sR > 0.5 * np.abs(m)
    w, sw = wl["downforce"], h["confirmation"]["f32"]["se_eff"]["downforce"]
    rho = v1 / w
    out["G4_V1"] = (rho >= 0.5) & (rho <= 2.0), (v1 + t3 * s1 < 0.5 * (w - t3 * sw)) | (v1 - t3 * s1 > 2 * (w + t3 * sw))
    v3, s13 = d["V3"]["downforce"], math.hypot(se("V3", "downforce"), V1_PAIR_SD / 2)   # margins on the 4 common pairs (dof 3)
    lo, hi = v3 - 0.6 * v1, 1.67 * v1 - v3
    out["V3_BAND"] = (lo >= 0) & (hi >= 0), (lo + t3 * s13 < 0) | (hi + t3 * s13 < 0)
    return out


def summarise(out):
    keys = list(out)
    allpass = np.logical_and.reduce([out[k][0] for k in keys])
    anyfail = np.logical_or.reduce([out[k][1] for k in keys])
    gain_drag = [k for k in keys if k.startswith(("GAIN", "DRAG"))]
    return {"rules": {k: {"pass": float(out[k][0].mean()), "fail": float(out[k][1].mean())} for k in keys},
            "XV01_PASS": float(allpass.mean()), "XV01_FAIL": float(anyfail.mean()), "XV01_UNRESOLVED": float((~allpass & ~anyfail).mean()),
            "XV_OF_GAIN_CONFIRMED": float(np.logical_and.reduce([out[k][0] for k in gain_drag]).mean())}


def s57(h):
    """§5.7 numbers as a probability that the V1 gain clears x_OF: mean = retention (Delta - b_K), SD = sigma_disc (+ WL and V1 SE)."""
    sb, f32 = h["selection_bias_inputs"], h["confirmation"]["f32"]
    out = {}
    for case, ret, b, sd in (("central", "central", "central", "central"), ("pessimistic", "pessimistic", "upper", "upper")):
        r = sb["retention"][ret]
        mean = r * (f32["delta_bar"]["downforce"] - h["selection_bias"]["b_K"][b])
        sdev = math.sqrt(sb["sigma_disc"][sd] ** 2 + (r * f32["se_eff"]["downforce"]) ** 2 + SE_PLAN[("V1", "downforce")] ** 2)
        out[case] = {"expected_V1_gain_n": mean, "expected_V1_gain_pct_J48": 100 * mean / J48, "sd_n": sdev,
                     **{f"p_clear_x_{k}": float(stats.norm.sf((x - mean) / sdev)) for k, x in
                        (("J48", G_OF * J48), ("F_parent_V1", G_OF * F_PARENT["V1"]))}}
    return out


def main():
    h = json.loads((SCR / "xv_handoff.json").read_text())
    rs = json.loads((SCR / "rs.json").read_text())
    parts, tab = contributions(h, rs), retention_table(json.loads(FID.read_text()))
    res = {"kind": "xv01_pass_probability_planning", "seed": SEED, "replicates": N, "evidence_class": "planning projection, no outcome effect",
           "x_of_n": {lev: G_OF * max(J48, F_PARENT[lev]) for lev in LEVELS}, "s57": s57(h),
           "components_n": parts, "retention_sources": {f: FAMILIES.get(f, "tier-A through-origin slope") for f in tab},
           "assumptions": {"tau": TAU, "camber_extension_sd": EXT, "se_plan": {f"{a}/{b}": v for (a, b), v in SE_PLAN.items()},
                           "v1_pair_sd": V1_PAIR_SD, "f_parent_of": F_PARENT}}
    for name, shift in (("comp", 0.0), ("comp_minus_bK_central", -h["selection_bias"]["b_K"]["central"]),
                        ("comp_minus_bK_upper", -h["selection_bias"]["b_K"]["upper"])):
        d, wl = simulate(parts, tab, h, np.random.default_rng(SEED), shift)
        res[name] = summarise(rules(d, wl, h)) | {"median_n": {lev: {r: float(np.median(d[lev][r])) for r in RESP} for lev in LEVELS}}
    (Path(__file__).with_suffix(".json")).write_text(json.dumps(res, indent=1, sort_keys=True) + "\n")
    print(json.dumps({k: res[k] for k in ("s57",)}, indent=1))
    for k in ("comp", "comp_minus_bK_central", "comp_minus_bK_upper"):
        print(k, {x: round(res[k][x], 3) for x in ("XV01_PASS", "XV01_FAIL", "XV01_UNRESOLVED", "XV_OF_GAIN_CONFIRMED")})
        print("   ", {r: (round(v["pass"], 3), round(v["fail"], 3)) for r, v in res[k]["rules"].items()})
        print("   ", res[k]["median_n"])


if __name__ == "__main__":
    main()
