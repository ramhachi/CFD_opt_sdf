#!/usr/bin/env python3
"""G2-DIAG5 host analyzer: integrity of the CPU matrix, then the pre-registered classification (run once).

Question: where does the D0 corner tangent get its one-step gain, does the AD tangent agree with a finite-amplitude response of the implemented map, and is the gain
a property of the map or of the derivative convention at the nonsmooth limiter?  Each state (S900, S1000) is classified; the final label needs both states to agree.

  R1_SELECTOR_CONVENTION  the AD/FD mismatch grows with the branch-flip rate, a generalised (tie-averaged) derivative closes it and reproduces the finite growth,
                          and the finite-amplitude growth is clearly smaller than the AD growth  -> the instability is sensitive to the derivative convention at the selector
  R2_LINEARISATION_DEFECT AD and FD disagree at an amplitude (>= 1e-5) where the corner box has (almost) no branch flips (testable only if such an amplitude exists)
  R3_FINITE_INSTABILITY   AD agrees with FD at every registered amplitude and the finite perturbation grows at the AD rate -> a genuine finite-perturbation instability
                          of the implemented map over the tested neighbourhood
  R4_INCONCLUSIVE         otherwise (the registered meaning: the current long-window forward-AD qualification programme is a bounded No-Go; no gradient claim)

Nothing here computes a gradient, a bridge value or a delta; no GRAD-03 verdict; the six flags stay false.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATES = ("S900", "S1000")
EPS_E3 = (1e-6, 1e-5, 1e-4, 1e-3, 1e-2)
EPS_E5 = ("1e-5", "1e-4", "1e-3", "1e-2")
EPS_E5_VARIANT_B = ("1e-4", "1e-3")      # eps with the controls B (p unperturbed) and C (solenoidal velocity direction)
K_STEPS = 40
LAMBDAS = ("quick", "tie1e-5", "tie1e-4", "linear")
FLAGS = ("fd_oracle", "field_gradient", "reverse", "optimizer", "topology", "shape_update_allowed")
# ---- registered thresholds (fixed in the pre-run freeze) ---------------------------------------------------------------------------------------------------
AGREE_REL = 0.10             # JVP agrees with the finite difference: relative L2 error in the corner box
AGREE_COS = 0.99
AGREE_RATIO = (0.95, 1.05)
SMOOTH_FLIP_RATE = 0.01      # the branch-flip rate (corner box, either conv_diff call) below which the map is treated as smooth at that eps
SMOOTH_MIN_EPS = 1e-5        # smaller eps are dominated by Float32 round-off of the difference quotient
SMOOTH_MAX_EPS = 1e-3        # larger eps carry finite-amplitude nonlinearity of the map itself
FLIP_RANK_CORRELATION = 0.8  # R1: Spearman correlation between the flip rate and the baseline mismatch over eps <= RANK_EPS_MAX
RANK_EPS_MAX = 1e-3
RANK_MIN_POINTS = 4
LINEAR_AMPLITUDE = 0.1       # the finite-amplitude growth is read while eps * max|D_k| (corner box) <= this
RATE_MIN_POINTS = 5
FD_LOWER_FACTOR = 0.5        # R1: finite growth rate <= this fraction of the AD rate at eps = 1e-3
FD_MATCH = (0.7, 1.3)        # R3: finite growth rate / AD rate
SURROGATE_RATE_TOL = 0.3     # R1: |rate(AD with the surrogate) - rate(FD)| <= max(this * |rate(FD)|, SURROGATE_RATE_FLOOR)
SURROGATE_RATE_FLOOR = 0.02  # decade per step
SURROGATE_MISMATCH_REDUCTION = 0.5
SURROGATE_GAIN_TOL = 0.2
ULP_SENSITIVE = 0.05         # reported only: median pattern change of the corner tangent under +-1 ulp noise on the primal
ENSEMBLE_N = 16
AD_RATE_MIN = 0.02           # decade/step: the AD tangent must GROW at least this fast for the growth comparison (a decaying or flat AD tangent never makes R1 or R3)
E0_DT_REL = 1e-4
E0_PRIMAL_U_REL = 1e-5
E0_PRIMAL_P_REL = 1e-3
E3_ROWS = len(EPS_E3) * len(LAMBDAS) * 2      # eps x derivative variant x region


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def read_csv(path: Path):
    with Path(path).open(newline="") as handle:
        return list(csv.DictReader(handle))


def jload(path: Path):
    return json.loads(Path(path).read_text())


def fnum(x) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return float("nan")


def tag(state: str, group: str) -> str:
    return f"{state}_{group.replace(':', '_')}"


def expected_groups() -> list[tuple[str, str]]:
    groups = ["E1", "E2", "E3", "E3C", "E5AD", *(f"E5FD:{e}" for e in EPS_E5), "E6"]
    return [("R1188", "E0"), *((s, g) for s in STATES for g in groups)]


def fit(xs, ys):
    n = len(xs)
    if n < RATE_MIN_POINTS:
        return float("nan"), float("nan")
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    if sxx == 0:
        return float("nan"), float("nan")
    return sxy / sxx, (sxy * sxy / (sxx * syy) if syy > 0 else 1.0)


def rate(rows, kmax=None):
    """Growth rate (decade per step) of the corner-box L2 norm of the tangent / difference quotient, steps 0..kmax."""
    pts = [(int(r["step"]), fnum(r["l2_box"])) for r in rows if (kmax is None or int(r["step"]) <= kmax)]
    pts = [(k, math.log10(v)) for k, v in pts if math.isfinite(v) and v > 0]
    slope, r2 = fit([p[0] for p in pts], [p[1] for p in pts])
    return {"rate": slope, "r2": r2, "points": len(pts), "kmax": kmax}


def linear_range(fd_rows, eps):
    """Last step k such that eps * bmax_j <= LINEAR_AMPLITUDE for all j <= k (the finite perturbation is still small)."""
    last = 0
    for r in sorted(fd_rows, key=lambda r: int(r["step"])):
        if eps * fnum(r["bmax"]) > LINEAR_AMPLITUDE or not math.isfinite(fnum(r["bmax"])):
            break
        last = int(r["step"])
    return last


def ranks(v):
    order = sorted(range(len(v)), key=lambda i: v[i]); r = [0.0] * len(v); i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and v[order[j + 1]] == v[order[i]]:
            j += 1
        for k in range(i, j + 1):
            r[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return r


def spearman(x, y):
    if len(x) < RANK_MIN_POINTS or len(x) != len(y) or not all(math.isfinite(t) for t in (*x, *y)):
        return float("nan")
    rx, ry = ranks(x), ranks(y)
    mx, my = sum(rx) / len(rx), sum(ry) / len(ry)
    sxx = sum((a - mx) ** 2 for a in rx); syy = sum((b - my) ** 2 for b in ry)
    return sum((a - mx) * (b - my) for a, b in zip(rx, ry)) / math.sqrt(sxx * syy) if sxx > 0 and syy > 0 else float("nan")


def e3_state(rows) -> dict:
    """Per eps and derivative variant: agreement in the corner box, the flip statistics and the localisation of the mismatch."""
    out: dict = {}
    for r in rows:
        if r["region"] != "box":
            continue
        e, lam = float(r["eps"]), r["lambda"]
        flip = max(fnum(r["flip_rate_box_predict"]), fnum(r["flip_rate_box_correct"]))
        rel, cos, ratio = fnum(r["rel"]), fnum(r["cos"]), fnum(r["ratio"])
        enrich = [fnum(r["mismatch_share_in_flip_cells_d1"]) / max(fnum(r["flip_cell_fraction_d1"]), 1e-12)]      # descriptive only: saturates when the flip cells cover the box
        agree = rel <= AGREE_REL and cos >= AGREE_COS and AGREE_RATIO[0] <= ratio <= AGREE_RATIO[1]
        out.setdefault(e, {})[lam] = {"rel": rel, "cos": cos, "ratio": ratio, "flip_rate": flip, "agree": agree, "enrichment_d1": enrich[0], "mismatch_share_d1": fnum(r["mismatch_share_in_flip_cells_d1"]),
                                      "gain_jvp": fnum(r["gain_jvp_box_max"]), "gain_fd": fnum(r["gain_fd_box_max"])}
    return out


def classify_state(e3: dict, fd: dict, ad: dict, e6: dict | None, e3c: dict | None = None) -> dict:
    ind: dict = {}
    if e3c:     # the control with the solenoidal velocity direction: reported, never a classification input
        ind["solenoidal_control_agree_by_eps"] = {str(e): v["quick"]["agree"] for e, v in sorted(e3c.items()) if "quick" in v}
    base = {e: v["quick"] for e, v in e3.items() if "quick" in v}
    ind["agree_by_eps"] = {str(e): v["agree"] for e, v in sorted(base.items())}
    ind["flip_rate_by_eps"] = {str(e): v["flip_rate"] for e, v in sorted(base.items())}
    smooth = [e for e, v in base.items() if SMOOTH_MIN_EPS <= e <= SMOOTH_MAX_EPS and v["flip_rate"] < SMOOTH_FLIP_RATE]
    ind["smooth_eps"] = sorted(smooth)
    ind["r2_testable"] = bool(smooth)
    ind["smooth_regime_mismatch"] = any(not base[e]["agree"] for e in smooth)
    ind["enrichment_d1_descriptive"] = {str(e): v["enrichment_d1"] for e, v in sorted(base.items())}
    rk = [e for e in sorted(base) if e <= RANK_EPS_MAX]
    ind["flip_mismatch_rank_correlation"] = spearman([base[e]["flip_rate"] for e in rk], [base[e]["rel"] for e in rk])
    ind["mismatch_grows_with_flips"] = math.isfinite(ind["flip_mismatch_rank_correlation"]) and ind["flip_mismatch_rank_correlation"] >= FLIP_RANK_CORRELATION
    mid = [1e-5, 1e-4, 1e-3]
    ind["agrees_at_every_mid_eps"] = all(e in base and base[e]["agree"] for e in mid)
    ind["baseline_disagrees_at_1e-3"] = 1e-3 in base and not base[1e-3]["agree"]
    # the surrogate derivative at eps = 1e-3
    best = None
    for lam in ("tie1e-5", "tie1e-4"):
        v, b = e3.get(1e-3, {}).get(lam), e3.get(1e-3, {}).get("quick")
        if not v or not b or not b["rel"] > 0:
            continue
        reduction = 1 - v["rel"] / b["rel"]
        gain_ok = abs(v["gain_jvp"] - v["gain_fd"]) / max(abs(v["gain_fd"]), 1e-300) <= SURROGATE_GAIN_TOL
        cand = {"lambda": lam, "mismatch_reduction": reduction, "gain_close_to_fd": gain_ok, "agrees_with_fd": v["agree"], "ok": reduction >= SURROGATE_MISMATCH_REDUCTION and gain_ok and v["agree"]}
        if best is None or (cand["ok"], reduction) > (best["ok"], best["mismatch_reduction"]):
            best = cand
    ind["surrogate_one_step"] = best
    # multi-step growth
    growth: dict = {}
    for e in EPS_E5:
        rows = fd.get(("A", e))
        if rows is None:
            growth[e] = None
            continue
        kv = linear_range(rows, float(e))
        fdr, adr = rate(rows, kv), rate(ad["quick"], kv)
        entry = {"kmax": kv, "rate_fd": fdr["rate"], "rate_ad": adr["rate"], "points": fdr["points"]}
        entry["ratio_fd_over_ad"] = fdr["rate"] / adr["rate"] if math.isfinite(adr["rate"]) and adr["rate"] >= AD_RATE_MIN and math.isfinite(fdr["rate"]) else None
        for lam in ("tie1e-5", "tie1e-4", "linear"):
            entry["rate_ad_" + lam] = rate(ad[lam], kv)["rate"]
        rb, rc = fd.get(("B", e)), fd.get(("C", e))
        entry["rate_fd_variant_B_p_unperturbed"] = rate(rb, kv)["rate"] if rb else None
        entry["rate_fd_variant_C_solenoidal"] = rate(rc, kv)["rate"] if rc else None
        entry["rate_ad_variant_C_solenoidal"] = rate(ad["quick_C"], kv)["rate"] if "quick_C" in ad else None
        growth[e] = entry
    ind["growth"] = growth
    g3 = growth.get("1e-3")
    ind["fd_growth_clearly_lower"] = bool(g3 and g3["ratio_fd_over_ad"] is not None and g3["ratio_fd_over_ad"] <= FD_LOWER_FACTOR)
    ind["fd_growth_matches_ad"] = all(growth.get(e) and growth[e]["ratio_fd_over_ad"] is not None and FD_MATCH[0] <= growth[e]["ratio_fd_over_ad"] <= FD_MATCH[1] for e in ("1e-4", "1e-3"))
    sur = False
    if g3 and best:
        a, b = g3["rate_ad_" + best["lambda"]], g3["rate_fd"]
        sur = math.isfinite(a) and math.isfinite(b) and abs(a - b) <= max(SURROGATE_RATE_TOL * abs(b), SURROGATE_RATE_FLOOR)
    ind["surrogate_reproduces_finite_growth"] = sur
    if e6:        # reported, never a classification input
        ind["ulp_sensitive_reported"] = statistics.median(e6["pattern_changes"]) >= ULP_SENSITIVE if e6["pattern_changes"] else None
        ind["ulp_ad_vs_fd_change_median"] = [statistics.median(e6["pattern_changes"]) if e6["pattern_changes"] else None, statistics.median(e6["fd_changes"]) if e6["fd_changes"] else None]
    if ind["smooth_regime_mismatch"]:
        label = "R2_LINEARISATION_DEFECT"
    elif ind["agrees_at_every_mid_eps"] and ind["fd_growth_matches_ad"]:
        label = "R3_FINITE_INSTABILITY"
    elif ind["baseline_disagrees_at_1e-3"] and ind["mismatch_grows_with_flips"] and (ind["surrogate_one_step"] or {}).get("ok") and ind["fd_growth_clearly_lower"] and ind["surrogate_reproduces_finite_growth"]:
        label = "R1_SELECTOR_CONVENTION"
    else:
        label = "R4_INCONCLUSIVE"
    ind["label"] = label
    return ind


def verify_integrity(out: Path, freeze: dict | None = None) -> dict:
    failures: list[str] = []
    drv = jload(out / "driver_index.json") if (out / "driver_index.json").is_file() else {}
    if not drv:
        failures.append("driver_index.json missing")
    done, error = (out / "DONE").is_file(), (out / "ERROR.txt").is_file()
    if done == error:
        failures.append(f"exactly one of DONE/ERROR.txt must exist (done={done}, error={error})")
    if drv.get("status") != "COMPLETE":
        failures.append(f"driver status is {drv.get('status')!r}")
    if freeze is not None:
        if drv.get("source_commit") != freeze["source_commit"]:
            failures.append("driver source_commit differs from the freeze")
        if drv.get("pins") != freeze["pins"]:
            failures.append("driver pins differ from the freeze")
        if sha256(Path(__file__)) != freeze.get("file_hashes", {}).get("analyzer"):
            failures.append("the analyzer differs from (or is missing in) the frozen analyzer")
    for state, group in expected_groups():
        d = out / tag(state, group)
        if not (d / "status.json").is_file() or not (d / "result.json").is_file():
            failures.append(f"missing output: {state} {group}")
            continue
        st = jload(d / "status.json")
        if st.get("status") != "COMPLETE" or st.get("dryrun") is not False or st.get("k_steps") != K_STEPS or st.get("threads") != 1:
            failures.append(f"status of {state} {group}: {st.get('status')!r} dryrun={st.get('dryrun')!r} k={st.get('k_steps')!r} threads={st.get('threads')!r}")
        if st.get("qualification_flags") != {k: False for k in FLAGS}:
            failures.append(f"qualification flags are not all false: {state} {group}")
        if freeze is not None:
            for key in ("waterlily_flow_jl_sha256", "waterlily_multilevelpoisson_jl_sha256", "waterlily_poisson_jl_sha256"):
                if st.get(key) != freeze["runtime_source_hashes"][key]:
                    failures.append(f"runtime source hash differs from the freeze: {key} {state} {group}")
    return {"pass": not failures, "failures": failures}


def primal_bits_ok(result: dict) -> bool:
    """Every registered eps x derivative variant has a primal checksum and all variants of an eps equal the baseline's.  The keys are parsed (Julia prints 1.0e-6 where Python prints 1e-06)."""
    got: dict = {}
    for key, value in result.items():
        m = re.fullmatch(r"primal_bits_(.+)_(quick|tie1e-5|tie1e-4|linear)", key)
        if m:
            got.setdefault(float(m.group(1)), {})[m.group(2)] = value
    if sorted(got) != sorted(EPS_E3):
        return False
    return all(set(v) == set(LAMBDAS) and all(x is not None and x == v["quick"] for x in v.values()) for v in got.values())


def e3_rows_complete(rows) -> bool:
    """eps x variant x region rows, each exactly once, with finite agreement metrics and flip rates."""
    seen: dict = {}
    for r in rows:
        key = (float(r["eps"]), r["lambda"], r["region"])
        seen[key] = seen.get(key, 0) + 1
        if not all(math.isfinite(fnum(r[c])) for c in ("rel", "cos", "ratio", "flip_rate_box_predict", "flip_rate_box_correct", "gain_jvp_box_max", "gain_fd_box_max")):
            return False
    want = {(e, lam, reg) for e in EPS_E3 for lam in LAMBDAS for reg in ("box", "interior")}
    return set(seen) == want and all(v == 1 for v in seen.values()) and len(rows) == E3_ROWS


def gates(out: Path) -> dict:
    """Mechanical gates that must hold before the classification is trusted."""
    g: dict = {}
    e0 = jload(out / tag("R1188", "E0") / "result.json")
    dt = e0["dt_output"]; dti = e0["dt_input"]
    g["e0_dt_input_tangent_rel"] = abs(dti["cfl_tangent"] - dti["stored_tangent_scaled"]) / max(abs(dti["stored_tangent_scaled"]), 1e-300)
    g["e0_dt_output_tangent_rel"] = abs(dt["cpu_tangent"] - dt["stored_tangent_scaled"]) / max(abs(dt["stored_tangent_scaled"]), 1e-300)
    g["e0_primal_u_rel"] = e0["primal_u"]["rel"]; g["e0_primal_p_rel"] = e0["primal_p"]["rel"]
    g["e0_pass"] = g["e0_dt_input_tangent_rel"] <= E0_DT_REL and g["e0_dt_output_tangent_rel"] <= E0_DT_REL and g["e0_primal_u_rel"] <= E0_PRIMAL_U_REL and g["e0_primal_p_rel"] <= E0_PRIMAL_P_REL
    g["e0_ghost_closure"] = e0["ghost_closure"]
    DT_VALUE_REL, DT_TANGENT_REL = 1e-6, 1e-4
    for s in STATES:
        ok = True
        for state, group in expected_groups():
            if state != s:
                continue
            dc = jload(out / tag(state, group) / "result.json").get("dt_closure")
            ok &= bool(dc) and abs(dc["cfl_value"] - dc["stored_value"]) <= DT_VALUE_REL * abs(dc["stored_value"]) and \
                abs(dc["cfl_tangent"] - dc["stored_tangent"]) <= DT_TANGENT_REL * abs(dc["stored_tangent"])
        g[f"{s}_dt_closure_complete"] = ok
        e5 = jload(out / tag(s, "E5AD") / "result.json")
        g[f"{s}_instrumented_step_bit_identical"] = e5["instrumented_step_bit_identical_to_sim_step"] is True
        rows = read_csv(out / tag(s, "E5AD") / "e5ad_rows.csv")
        by = {}
        for r in rows:
            by.setdefault(r["variant"], {})[int(r["step"])] = (r["u_xor"], r["u_sum"])
        g[f"{s}_variants_share_the_primal"] = all(by.get(v) == by.get("AD/quick") and len(by.get(v, {})) == K_STEPS + 1 for v in ("AD/quick", "AD/tie1e-5", "AD/tie1e-4", "AD/linear", "ADC/quick"))
        for grp, fname in (("E3", "e3_rows.csv"), ("E3C", "e3c_rows.csv")):
            res = jload(out / tag(s, grp) / "result.json")
            g[f"{s}_{grp.lower()}_variants_share_the_primal"] = primal_bits_ok(res)
            g[f"{s}_{grp.lower()}_rows_complete"] = e3_rows_complete(read_csv(out / tag(s, grp) / fname))
        e6 = jload(out / tag(s, "E6") / "result.json")
        g[f"{s}_e6_complete"] = all(len(e6.get(k, [])) == ENSEMBLE_N and all(isinstance(v, (int, float)) and math.isfinite(v) for v in e6[k]) for k in ("gains", "pattern_changes", "fd_changes"))
        for e in EPS_E5:
            fdr = read_csv(out / tag(s, f"E5FD:{e}") / "e5fd_rows.csv")
            variants = {r["variant"] for r in fdr}
            want = {"FD/A"} | ({"FD/B", "FD/C"} if e in EPS_E5_VARIANT_B else set())
            g[f"{s}_e5fd_{e}_complete"] = variants == want and all(sum(1 for r in fdr if r["variant"] == v) == K_STEPS + 1 for v in want)
    g["pass"] = g["e0_pass"] and all(v for k, v in g.items() if k.endswith(("bit_identical", "share_the_primal", "_complete", "_rows_complete")))
    return g


def load_state(out: Path, state: str):
    e3 = e3_state(read_csv(out / tag(state, "E3") / "e3_rows.csv"))
    ad: dict = {}
    for r in read_csv(out / tag(state, "E5AD") / "e5ad_rows.csv"):
        kind, lam = r["variant"].split("/")
        ad.setdefault(lam if kind == "AD" else lam + "_C", []).append(r)
    fd: dict = {}
    for e in EPS_E5:
        for r in read_csv(out / tag(state, f"E5FD:{e}") / "e5fd_rows.csv"):
            fd.setdefault((r["variant"].split("/")[1], e), []).append(r)
    e6 = jload(out / tag(state, "E6") / "result.json")
    e3c = e3_state(read_csv(out / tag(state, "E3C") / "e3c_rows.csv"))
    return e3, fd, ad, e6, e3c


def descriptive(out: Path, state: str) -> dict:
    """E1 / E2 / E6 summaries (no classification input except the E6 ulp indicator)."""
    d: dict = {}
    stages = read_csv(out / tag(state, "E1") / "e1_stages.csv")
    full = [r for r in stages if r["variant"] == "full/quick"]
    ref = next(fnum(r["l2_box"]) for r in full if r["stage"] == "input" and r["field"] == "u")
    d["stage_l2_box_over_input"] = [{"stage": r["stage"], "field": r["field"], "ratio": fnum(r["l2_box"]) / ref if ref else None, "max_box": fnum(r["max_box"])} for r in full if r["stage"] != "input"]
    terms = read_csv(out / tag(state, "E1") / "e1_terms.csv")
    top: dict = {}
    for r in terms:
        if r["variant"] != "full/quick" or r["role"] in ("closure",) or r["region"] == "bdim":
            continue
        top.setdefault(r["call"], []).append((fnum(r["l2_box"]), r["i"], r["j"], r["role"], r["region"]))
    d["conv_diff_terms_top5_l2_box"] = {k: sorted(v, reverse=True)[:5] for k, v in top.items()}
    d["conv_diff_closure_rel"] = {r["call"]: fnum(r["max_all_or_closure"]) for r in terms if r["variant"] == "full/quick" and r["role"] == "closure"}
    d["bdim_terms_l2_box"] = {f"{r['call']}/{r['role']}": fnum(r["l2_box"]) for r in terms if r["variant"] == "full/quick" and r["region"] == "bdim"}
    e2 = jload(out / tag(state, "E2") / "result.json")
    d["e2_box_predict"] = e2["predict_conv"]["box"]
    e6 = jload(out / tag(state, "E6") / "result.json")
    d["e6"] = {"gain_baseline": e6["gain_baseline"], "gain_range": [min(e6["gains"]), max(e6["gains"])] if e6["gains"] else None,
               "pattern_change_median": statistics.median(e6["pattern_changes"]) if e6["pattern_changes"] else None,
               "fd_change_median": statistics.median(e6["fd_changes"]) if e6["fd_changes"] else None}
    return d


def analyze(out: Path) -> dict:
    report: dict = {"kind": "grad03_g2_diag5_analysis", "no_bridge_value": True, "selected_delta": None, "grad03_verdict": None, "qualification_flags": {k: False for k in FLAGS}}
    report["gates"] = gates(out)
    states = {}
    for s in STATES:
        e3, fd, ad, e6, e3c = load_state(out, s)
        states[s] = classify_state(e3, fd, ad, e6, e3c)
        states[s]["descriptive"] = descriptive(out, s)
    report["states"] = states
    labels = {s: states[s]["label"] for s in STATES}
    report["labels"] = labels
    report["verdict"] = "DIAG5_INCOMPLETE" if not report["gates"]["pass"] else (labels[STATES[0]] if len(set(labels.values())) == 1 else "R4_INCONCLUSIVE")
    report["interpretation"] = INTERPRETATION.get(report["verdict"], "the mechanical gates failed: nothing is concluded")
    return report


INTERPRETATION = {
    "R1_SELECTOR_CONVENTION": ("The corner tangent gain of the AD linearisation is sensitive to the derivative convention at the nonsmooth QUICK/median limiter: the AD/finite-difference mismatch "
                               "grows with the branch-flip rate and a generalised (tie-averaged) derivative removes it and reproduces the finite-amplitude growth. This is a statement about a "
                               "derivative convention (the surrogate is not the derivative of the implemented map), not an AD bug and not a gradient qualification; continuing full-field AD "
                               "would need a new gradient contract with its own pre-registered qualification."),
    "R2_LINEARISATION_DEFECT": "AD and the finite difference disagree at an amplitude where the corner box has almost no branch flips: a linearisation defect is a candidate explanation (term-level localisation in E1; not established).",
    "R3_FINITE_INSTABILITY": ("The observed unstable tangent mode is a genuine finite-perturbation instability of the implemented discrete map over the tested neighbourhood; "
                              "the current long-window forward-AD qualification programme is a bounded No-Go."),
    "R4_INCONCLUSIVE": ("The predefined diagnostic budget did not identify a qualified derivative interpretation; the current long-horizon AD path is terminated without a gradient correctness claim "
                        "(bounded No-Go for this programme, not a statement about full-field AD in general)."),
    "DIAG5_INCOMPLETE": "the mechanical gates failed: nothing is concluded"}


def clean(x):
    """Strict JSON: non-finite floats become null, tuples lists."""
    if isinstance(x, float):
        return x if math.isfinite(x) else None
    if isinstance(x, dict):
        return {str(k): clean(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [clean(v) for v in x]
    return x


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out-dir", required=True, type=Path)
    p.add_argument("--freeze", required=True, type=Path)
    p.add_argument("--write", type=Path)
    p.add_argument("--check", action="store_true", help="print the integrity and the gates only; writes nothing and classifies nothing")
    args = p.parse_args()
    try:
        integrity = verify_integrity(args.out_dir, jload(args.freeze))
    except Exception as err:  # noqa: BLE001
        integrity = {"pass": False, "failures": [f"integrity check error: {type(err).__name__}: {err}"]}
    if args.check:
        try:
            g = gates(args.out_dir)
        except Exception as err:  # noqa: BLE001
            g = {"pass": False, "error": f"{type(err).__name__}: {err}"}
        print(json.dumps(clean({"integrity": integrity, "gates": g}), indent=2, sort_keys=True))
        return
    if args.write is None:
        sys.exit("--write is required unless --check")
    if args.write.exists():
        sys.exit("refusing to overwrite an existing analysis (the diagnostic analyzer runs once)")
    report: dict = {"integrity": integrity}
    if not integrity["pass"]:
        report["verdict"] = "DIAG5_INCOMPLETE"      # nothing is classified when the integrity check failed
    else:
        try:
            report |= analyze(args.out_dir)
        except Exception as err:  # noqa: BLE001
            report |= {"verdict": "DIAG5_INCOMPLETE", "note": f"analysis error: {type(err).__name__}: {err}"}
    data = json.dumps(clean(report), indent=2, sort_keys=True, default=str, allow_nan=False) + "\n"
    with args.write.open("x") as handle:
        handle.write(data)
    print(report.get("verdict"), "integrity_pass=", integrity["pass"], hashlib.sha256(data.encode()).hexdigest())
    if not integrity["pass"] or "analysis error" in report.get("note", ""):
        sys.exit(3)


if __name__ == "__main__":
    main()
