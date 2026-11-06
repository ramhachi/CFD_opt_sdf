#!/usr/bin/env python3
"""Independent TOPO-2D-00 arithmetic; does not import the analyzer or its helpers.

The input/output contract is wp04_design.md and the registration, rather than
another implementation. This checks the normalized input saved in analysis.json;
it does not replace the analyzer's raw-artifact/freeze verification.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np
from scipy.stats import chi2, t

LIMITATIONS = [
    "No physical, grid-independent, FSAE or 3D qualification is implied.",
    "CONCORDANT_PARTIAL is shadowed by DISCORDANT under global-AND resolved ranking.",
    "RETENTION_12 uses delta-method relative-increment variances followed by Fieller; it is not an exact nested-ratio interval.",
    "The uncertainty model treats placement phases and equal-duration batches as sampling units; iid adequacy requires registration review.",
]
CONFIGS = ("E1", "E2", "E3")
READOUTS = ("cur", "nds", "cv")
RESPONSES = ("downforce", "drag")


def need(condition, message):
    if not condition:
        raise ValueError(message)


def number(x):
    need(not isinstance(x, bool) and isinstance(x, (int, float)) and math.isfinite(x),
         f"expected finite number, got {x!r}")
    return float(x)


def classical(values):
    a = np.asarray([number(x) for x in values], dtype=float)
    need(a.size >= 2, "at least two independent units required")
    n = len(a)
    mean = float(np.sum(a) / n)
    sd = float(np.sqrt(np.sum((a - mean) ** 2) / (n - 1)))
    se = sd / math.sqrt(n)
    half = float(t.ppf(.95, n - 1)) * se
    return dict(n=n, mean=mean, sd=sd, se=se, df=n - 1,
                ci90=[mean - half, mean + half])


def batch_variance(readout, response, phases, upper=False):
    batches = [number(row[response]) for row in readout["batches"]]
    need(len(batches) >= 4, "at least four equal-duration batches required")
    n = len(batches)
    mean, whole = sum(batches) / n, number(readout[response])
    need(abs(mean - whole) <= 1e-9 * max(1, abs(mean), abs(whole)),
         "equal-duration batch means do not reproduce whole-window mean")
    variance = float(np.var(batches, ddof=1)) / n
    if upper:
        # Alpha=.05: half to A, half to B; B uses 2P simultaneous bounds.
        variance *= (n - 1) / float(chi2.ppf(.025 / (2 * phases), n - 1))
    return variance


def paired_w(left, right, response, readout="cur"):
    need(len(left) == len(right) and len(left) >= 2, "paired phase count")
    n = len(left)
    d = np.array([number(b["readouts"][readout][response]) -
                  number(a["readouts"][readout][response]) for a, b in zip(left, right)])
    mean = float(np.mean(d))
    sa = float(np.std(d, ddof=1))
    sb = math.sqrt(sum(batch_variance(row["readouts"][readout], response, n)
                       for row in [*left, *right]) / n)
    sau = sa * math.sqrt((n - 1) / float(chi2.ppf(.025, n - 1)))
    sbu = math.sqrt(sum(batch_variance(row["readouts"][readout], response, n, True)
                        for row in [*left, *right]) / n)
    su = max(sau, sbu)
    se = su / math.sqrt(n)
    hw = float(t.ppf(.95, n - 1)) * se
    return dict(n=n, mean=mean, sigma_a=sa, sigma_b=sb, sigma=max(sa, sb),
                sigma_a_upper=sau, sigma_b_upper=sbu, sigma_upper=su,
                se=se, df=n - 1, ci90=[mean - hw, mean + hw])


def relative_w(left, right, readout="cur"):
    n = len(left)
    a = np.array([number(row["readouts"][readout]["downforce"]) for row in left])
    b = np.array([number(row["readouts"][readout]["downforce"]) for row in right])
    baseline = float(a.mean())
    if baseline == 0:
        return None, None
    r = float((b - a).mean() / baseline)
    influence = ((b - a) - r * a) / baseline
    va = float(np.var(influence, ddof=1)) / n
    va *= (n - 1) / float(chi2.ppf(.025, n - 1))
    vb = sum(batch_variance(y["readouts"][readout], "downforce", n, True)
             + (1 + r) ** 2 * batch_variance(x["readouts"][readout], "downforce", n, True)
             for x, y in zip(left, right)) / (n * n * baseline * baseline)
    return r, max(va, vb)


def relative_r(realizations):
    a = np.array([number(r["forces"]["E1"]["downforce"]) for r in realizations])
    b = np.array([number(r["forces"]["E2"]["downforce"]) for r in realizations])
    if float(a.mean()) == 0:
        return None, None
    r = float((b - a).mean() / a.mean())
    influence = ((b - a) - r * a) / a.mean()
    return r, float(np.var(influence, ddof=1)) / len(a)


def fieller(numerator, denominator, variance_num, variance_den, df, covariance=0.):
    """Solve the confidence-set quadratic, retaining disconnected sets/infinity."""
    u, v, vu, vv, cov = map(number, (numerator, denominator, variance_num,
                                     variance_den, covariance))
    need(vu >= 0 and vv >= 0 and df > 0, "invalid Fieller variance/df")
    if vu == 0 or vv == 0:
        need(cov == 0, "invalid Fieller covariance")
    else:
        # Cauchy-Schwarz on standard deviations avoids squaring tiny/large
        # coefficients, so changing coefficient units cannot weaken admission.
        bound = math.sqrt(vu) * math.sqrt(vv)
        need(abs(cov) <= bound * (1 + 32 * np.finfo(float).eps),
             "invalid Fieller covariance")
    q = float(t.ppf(.95, df)) ** 2
    a, b, c = v * v - q * vv, -2 * u * v + 2 * q * cov, u * u - q * vu
    eps = 32 * np.finfo(float).eps
    if abs(a) <= eps * max(v * v, q * vv, np.finfo(float).tiny):
        if abs(b) <= eps * max(abs(2 * u * v), abs(2 * q * cov), np.finfo(float).tiny):
            return dict(kind="all_real" if c <= 0 else "empty",
                        intervals=[[None, None]] if c <= 0 else [])
        bound = -c / b
        return dict(kind="half_line", intervals=[[None, bound]] if b > 0 else [[bound, None]])
    disc = b * b - 4 * a * c
    if abs(disc) <= eps * max(b * b, abs(4 * a * c), np.finfo(float).tiny):
        disc = 0.
    if disc < 0:
        return dict(kind="all_real" if a < 0 else "empty",
                    intervals=[[None, None]] if a < 0 else [])
    root = math.sqrt(disc)
    # Direct roots suffice here; comparing with the independent implementation
    # catches material cancellation on the registered synthetic/measurement scale.
    low, high = sorted(((-b - root) / (2 * a), (-b + root) / (2 * a)))
    if a > 0:
        return dict(kind="bounded", intervals=[[low, high]])
    if disc == 0:
        return dict(kind="all_real", intervals=[[None, None]])
    return dict(kind="disjoint", intervals=[[None, low], [high, None]])


def resolved(stat):
    lo, hi = stat["ci90"]
    return lo > 0 or hi < 0


def same_sign(a, b):
    return resolved(a) and resolved(b) and (a["mean"] > 0) == (b["mean"] > 0)


def z_test(mean, se):
    return dict(z=abs(mean) / se if se > 0 else (0. if mean == 0 else None),
                **{"pass": abs(mean) > 3 * se})


def initial():
    return dict(schema="topo2d00-analysis-v1", label="INVALID",
        tr00=dict(cells={}, qualified_cells=[]), waterlily={}, rans={}, agreement={},
        resolution=dict(status="NOT_JUDGED", downforce=None),
        controls=dict(determinism=dict(judged=False, **{"pass": None}),
                      domain=dict(status="NOT_JUDGED", z=None), readout={}, manipulation={}),
        limitations=list(LIMITATIONS))


def tr_cells(payload):
    need(payload["schema"] == "topo2d00-rans-results-v1", "RANS schema")
    need(payload["coefficient_reference"]["chord_mm"] == 223.4, "RANS chord convention")
    reference = number(payload["reference"]["delta_cl"])
    uncertainty = number(payload["reference"]["digitizing_uncertainty"])
    need(reference != 0 and uncertainty >= 0, "invalid measured reference increment")
    output, qualified = {}, {}
    for cell in payload["cells"]:
        key = cell["model"] + "/" + cell["family"]
        need(key not in output, "duplicate model/family")
        rows = cell["realisations"]
        need(len({row["id"] for row in rows}) == len(rows), "duplicate realisation")
        statuses = [row["status"][config] for row in rows for config in ("E1_sharp", "E2_sharp")]
        need(set(statuses) <= {"SETTLED", "NUMERICAL", "INCOMPLETE"}, "unknown RANS status")
        block = dict(label="TR00_FAIL", delta=None, ratio_ci90=None)
        if "NUMERICAL" in statuses:
            block["label"] = "NUMERICAL"
        elif len(rows) != 8 or "INCOMPLETE" in statuses:
            block["label"] = "INCOMPLETE"
        else:
            stat = classical([number(row["forces"]["E2_sharp"]["downforce"]) -
                              number(row["forces"]["E1_sharp"]["downforce"]) for row in rows])
            ratio = sorted(x / reference for x in stat["ci90"])
            block.update(delta=stat, ratio_ci90=ratio)
            agrees = resolved(stat) and (stat["mean"] > 0) == (reference > 0)
            if agrees and uncertainty > .05 * abs(reference):
                block["label"] = "TR00_PASS_SIGN"
            elif agrees and .5 <= ratio[0] and ratio[1] <= 2:
                block["label"] = "TR00_PASS_RATIO"
        output[key] = block
        if block["label"].startswith("TR00_PASS_"):
            qualified[key] = rows
    return output, qualified


def select(rows, config, reynolds, role="primary", grid="main"):
    chosen = [row for row in rows if row["configuration"] == config
              and row["reynolds"] == reynolds and row["role"] == role and row["grid"] == grid]
    need(len({str(row["phase"]) for row in chosen}) == len(chosen), "duplicate configuration/phase")
    return {str(row["phase"]): row for row in chosen}


def pair(rows, reynolds, a="E1", b="E2", role="primary", grid="main", phases=None):
    x, y = select(rows, a, reynolds, role, grid), select(rows, b, reynolds, role, grid)
    need(set(x) == set(y), "paired phase identities differ")
    keys = sorted(x) if phases is None else sorted(phases)
    need(set(keys) <= set(x), "requested phases missing")
    return [x[k] for k in keys], [y[k] for k in keys]


def rank_w(rows, reynolds, readout="cur"):
    means = {c: float(np.mean([number(row["readouts"][readout]["downforce"])
                              for row in select(rows, c, reynolds).values()])) for c in CONFIGS}
    order = sorted(CONFIGS, key=means.get)
    return order, all(resolved(paired_w(*pair(rows, reynolds, a, b), "downforce", readout))
                      for a, b in zip(order, order[1:]))


def rank_r(rows):
    means = {c: float(np.mean([number(row["forces"][c]["downforce"]) for row in rows]))
             for c in CONFIGS}
    order = sorted(CONFIGS, key=means.get)
    return order, all(resolved(classical([number(row["forces"][b]["downforce"]) -
                                         number(row["forces"][a]["downforce"]) for row in rows]))
                      for a, b in zip(order, order[1:]))


def check(payload):
    need(payload["schema"] == "topo2d00-input-v1", "normalized input schema")
    need(type(payload["identity_valid"]) is bool and type(payload["cap_hit"]) is bool,
         "identity/cap flags must be explicit booleans")
    result = initial()
    if not payload["identity_valid"]:
        return result
    cells, qualified = tr_cells(payload["rans"])
    result["tr00"] = dict(cells=cells, qualified_cells=sorted(qualified))
    if not qualified:
        result["label"] = "TR_UNQUALIFIED"
        return result
    rows = payload["waterlily"]
    readout = payload["controls"].get("primary_readout", "cur")
    need(readout in READOUTS, "unknown primary readout")
    required = [r for r in rows if r["role"] in ("primary", "confirmation")]
    for row in rows:
        need(all(type(row[k]) is bool for k in ("ok", "finite", "complete")),
             "explicit run flags required")
    states = [r["status"][c] for values in qualified.values() for r in values for c in CONFIGS]
    need(set(states) <= {"SETTLED", "NUMERICAL", "INCOMPLETE"}, "unknown primary R status")
    if (any(not r["finite"] for r in rows)
            or any(r["complete"] and not r["ok"] for r in required)
            or "NUMERICAL" in states):
        result["label"] = "NUMERICAL"
        return result
    if payload["cap_hit"] or any(not r["complete"] for r in required) or "INCOMPLETE" in states:
        result["label"] = "INCOMPLETE"
        return result
    for reynolds in (1000, 3000):
        phase_sets = [set(select(rows, c, reynolds)) for c in CONFIGS]
        need(len(phase_sets[0]) == 16 and all(s == phase_sets[0] for s in phase_sets),
             "exactly 16 common primary phases per Re required")
    confirm = pair(rows, 3000, role="confirmation", grid="confirmation")
    need(len(confirm[0]) == 4, "exactly four confirmation phases required")
    for row in required:
        need(number(row["height_mm"]) == 100, "primary physical height must be 100mm")
        need(isinstance(row["scene_sha256"], str) and len(row["scene_sha256"]) == 64,
             "scene identity missing")
        need(row["readouts"].get(readout) is not None, "primary readout required")
    wranks = {}
    rranks = {}
    for re in (1000, 3000):
        result["waterlily"][str(re)] = {}
        for key, a, b in (("12", "E1", "E2"), ("23", "E2", "E3")):
            p = pair(rows, re, a, b)
            result["waterlily"][str(re)][key] = {q: paired_w(*p, q, readout) for q in RESPONSES}
        wranks[re] = rank_w(rows, re, readout)
    for key, values in sorted(qualified.items()):
        result["rans"][key] = {}
        for transition, a, b in (("12", "E1", "E2"), ("23", "E2", "E3")):
            result["rans"][key][transition] = {
                q: classical([number(row["forces"][b][q]) - number(row["forces"][a][q])
                              for row in values]) for q in RESPONSES}
        rranks[key] = rank_r(values)
    for re in (1000, 3000):
        per_cell = {}
        wstats = result["waterlily"][str(re)]
        u, vu = relative_w(*pair(rows, re), readout)
        for key, values in sorted(qualified.items()):
            rstats = result["rans"][key]
            v, vv = relative_r(values)
            per_cell[key] = {
                "SIGN_AGREE_12": same_sign(wstats["12"]["downforce"], rstats["12"]["downforce"]),
                "RANK_AGREE": wranks[re][1] and rranks[key][1] and wranks[re][0] == rranks[key][0],
                "DRAG_SIGN_AGREE_12": same_sign(wstats["12"]["drag"], rstats["12"]["drag"]),
                "RETENTION_12": dict(relative_w=u, variance_w=vu, relative_r=v, variance_r=vv,
                                     fieller=(dict(kind="undefined_zero_baseline", intervals=[])
                                              if u is None or v is None
                                              else fieller(u, v, vu, vv, 7))),
            }
        result["agreement"][str(re)] = {
            field: all(c[field] for c in per_cell.values())
            for field in ("SIGN_AGREE_12", "RANK_AGREE", "DRAG_SIGN_AGREE_12")}
        result["agreement"][str(re)]["cells"] = per_cell
    phases = [str(r["phase"]) for r in confirm[0]]
    coarse = pair(rows, 3000, phases=phases)
    sm = paired_w(*coarse, "downforce", readout)
    sf = paired_w(*confirm, "downforce", readout)
    dm = [b["readouts"][readout]["downforce"] - a["readouts"][readout]["downforce"]
          for a, b in zip(*coarse)]
    dfine = [b["readouts"][readout]["downforce"] - a["readouts"][readout]["downforce"]
             for a, b in zip(*confirm)]
    covariance = float(np.cov(dfine, dm, ddof=1)[0, 1]) / 4
    ratio = fieller(sf["mean"], sm["mean"], sf["se"] ** 2, sm["se"] ** 2, 3, covariance)
    in_band = ratio["kind"] == "bounded" and .5 <= ratio["intervals"][0][0] and ratio["intervals"][0][1] <= 2
    limited = (sf["mean"] > 0) != (sm["mean"] > 0) or not in_band
    result["resolution"] = dict(status="RESOLUTION_LIMITED" if limited else "PASS",
                                downforce=dict(main=sm, confirmation=sf, ratio=ratio))
    controls = result["controls"]
    repeats = [r for r in rows if r["role"] == "determinism"]
    if repeats:
        passed = True
        for row in repeats:
            original = select(rows, row["configuration"], row["reynolds"])
            need(str(row["phase"]) in original, "determinism primary absent")
            base = original[str(row["phase"])]
            need(("force_csv_sha256" in row) == ("force_csv_sha256" in base), "unpaired determinism CSV identity")
            passed &= (row["readouts"] == base["readouts"] and row["scene_sha256"] == base["scene_sha256"]
                       and row.get("force_csv_sha256") == base.get("force_csv_sha256")
                       and row["ok"] and row["finite"] and row["complete"])
        controls["determinism"] = dict(judged=True, **{"pass": bool(passed)})
    domains = [r for r in rows if r["role"] == "domain" and r["reynolds"] == 3000]
    if domains:
        a, b = select(domains, "E1", 3000, "domain"), select(domains, "E2", 3000, "domain")
        if len(a) >= 2 and set(a) == set(b) and all(r["ok"] and r["finite"] and r["complete"] for r in [*a.values(), *b.values()]):
            dp = pair(domains, 3000, role="domain")
            mp = pair(rows, 3000, phases=set(a))
            ds, ms = paired_w(*dp, "downforce", readout), paired_w(*mp, "downforce", readout)
            error, se = abs(ds["mean"] - ms["mean"]), math.hypot(ds["se"], ms["se"])
            z = error / se if se else (0. if not error else None)
            controls["domain"] = dict(status="DOMAIN_SENSITIVE" if error > 3 * se else "CONSISTENT", z=z)
    for re in (1000, 3000):
        p = pair(rows, re)
        controls["readout"][str(re)] = {}
        for name in READOUTS:
            available = all(r["readouts"].get(name) is not None for r in [*p[0], *p[1]])
            controls["readout"][str(re)][name] = {
                q: float(np.mean([number(b["readouts"][name][q]) - number(a["readouts"][name][q])
                                  for a, b in zip(*p)])) for q in RESPONSES} if available else None
        s = result["waterlily"][str(re)]["12"]["downforce"]
        controls["manipulation"][f"W/{re}"] = z_test(s["mean"], s["se"])
    for key, rstats in result["rans"].items():
        s = rstats["12"]["downforce"]
        controls["manipulation"][f"R/{key}"] = z_test(s["mean"], s["se"])
    if limited:
        result["label"] = "RESOLUTION_LIMITED"
        return result
    all_stats = [result["waterlily"][str(re)][transition][q]
                 for re in (1000, 3000) for transition, q in
                 (("12", "downforce"), ("23", "downforce"))]
    all_stats += [st[transition][q] for st in result["rans"].values()
                  for transition, q in (("12", "downforce"), ("23", "downforce"))]
    if (not all(resolved(s) for s in all_stats) or not all(r[1] for r in wranks.values())
            or not all(r[1] for r in rranks.values())
            or not all(v["pass"] for v in controls["manipulation"].values())):
        result["label"] = "UNRESOLVED"
        return result
    agrees = list(result["agreement"].values())
    if not any(a["SIGN_AGREE_12"] for a in agrees) or not all(a["RANK_AGREE"] for a in agrees):
        result["label"] = "DISCORDANT"
    elif not all(a["SIGN_AGREE_12"] for a in agrees):
        result["label"] = "CONCORDANT_PARTIAL"
    else:
        result["label"] = "CONCORDANT"
    return result


def compare(expected, actual, path="", *, rtol=1e-9):
    """List every differing decision/numerical path; strings/bools/null exact."""
    differences = []
    if isinstance(expected, dict) and isinstance(actual, dict):
        for key in sorted(set(expected) | set(actual)):
            p = f"{path}.{key}" if path else str(key)
            if key not in expected or key not in actual:
                differences.append(p + ": missing key")
            else:
                differences.extend(compare(expected[key], actual[key], p, rtol=rtol))
    elif isinstance(expected, (list, tuple)) and isinstance(actual, (list, tuple)):
        if len(expected) != len(actual):
            differences.append(path + ": length")
        for i, (a, b) in enumerate(zip(expected, actual)):
            differences.extend(compare(a, b, f"{path}[{i}]", rtol=rtol))
    elif isinstance(expected, bool) or isinstance(actual, bool) or expected is None or actual is None:
        if type(expected) is not type(actual) or expected != actual:
            differences.append(f"{path}: {expected!r} != {actual!r}")
    elif isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
        if not (math.isfinite(expected) and math.isfinite(actual)) or abs(expected - actual) > rtol * max(1, abs(expected), abs(actual)):
            differences.append(f"{path}: {expected!r} != {actual!r}")
    elif type(expected) is not type(actual) or expected != actual:
        differences.append(f"{path}: {expected!r} != {actual!r}")
    return differences


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("analysis", type=Path)
    args = parser.parse_args()
    def reject(text):
        raise ValueError(f"nonfinite JSON token {text}")
    def pairs(items):
        out = {}
        for key, value in items:
            need(key not in out, f"duplicate JSON key: {key}")
            out[key] = value
        return out
    record = json.loads(args.analysis.read_text(), parse_constant=reject, object_pairs_hook=pairs)
    differences = compare(record["result"], check(record["input"]))
    print(json.dumps({"pass": not differences, "discrepancies": differences}, indent=2, allow_nan=False))
    raise SystemExit(bool(differences))


if __name__ == "__main__":
    main()
