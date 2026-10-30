"""SCREEN-01 (#64) independent second implementation of the decision tables (registration rev. 1 s5, with the s5.2 rewrite and s5.11; interface: scripts/screen01/INTERFACE.md).

check(T) -> the stage's comparable keys; compare(a, b, stage) -> discrepancy paths. numpy/scipy/stdlib only; no code shared with the analyzer.
Shapes follow INTERFACE.md. Choices the interface leaves open: fit {downforce:{coef}, drag:{coef}, rank, cond, residual_sd:{downforce,drag}}; targets keys "1", "1.5", "2" (%g);
gated [[0-based owning target index, [u x3 rounded 6]]]; candidates {name: {delta_bar, P, se_eff, feasible}}; determinism {g1k11|f32a: {max_abs_diff, nondeterminism, judged}}.
`data_loss` entries are `state@kernel-table-key@phase` (g1, g2, f32, f48) of the runs PRESENT in T["runs"] (s5.11.1: uniform for every role; a run without a valid parent run at its phase is unpaired and not listed).
An extra key `gating_mismatch` (list of paths) is present only when T["gating"] disagrees with the regenerated gating (u, target_index, y_pred, z_pred by position, length, duplicate names, roles.proposals); compare() reports it.
Readings where the text is still open (see the module's comments): the Delta_bar_DF,48 of the R3 ratio/E2 labels stays the Phi_48 mean (s5.11.11 redefines only the flow_32 side); an `ok = false` repeat is NOT_JUDGED even if its force is
non-finite; a run whose own result is invalid but whose parent run at that phase is invalid too is not listed; DATA_G2 is not raised by a declared-lost g2 kernel beyond the proposals lacking phases.
"""
from __future__ import annotations

import math
from functools import lru_cache

import numpy as np
from scipy import integrate, stats
from scipy.stats import qmc

# ---- registration s6 constants (hard-coded on purpose) --------------------------------------------------------------------------------------------
X_STAR = 7.184166586553256e-3              # g_min J_b,48
J48 = 0.26577921974115387
TWO_SD_J = 1.8071267650359157e-3           # 2 S_d J_b,48
FLOOR = {"downforce": 2.0904201605451784e-4, "drag": 1.36408347135453e-4}
NC_REF, NC_SE = -1.6476407624087992e-3, 8.534104568937632e-5
M_D, TARGETS = 1.5e-3, (1.0, 1.5, 2.0)
SIGMA_DISC = (5.61e-4, 1.4474126675928642e-3)   # primary / upper
RETENTION = (0.655, 0.57)                       # central / pessimistic
XV_FLOOR = 0.012674959854238867
BOUND = 0.25
A_STAR = (3.1, 19.7, 29.3)                      # deg, mm, mm (pitch, camber, reflex)
LO, HI = np.array([-1.0, -1.5, -1.0]), np.array([1.0, 1.0, 1.0])
N_GRID, N_CLOUD, R_CLOUD, SEED_CLOUD = 81, 256, 0.25, 20261032
GATE_CAP, GATE_ROUND, N_PER_TARGET, N_PROP = 36, 4, 2, 4
RESP = ("downforce", "drag")
FREEZE1 = ("axial", "design", "manual", "ref", "random")
PHASES = {"g1": (11, 12), "g2": (11, 12), "f32": (13, 14, 15, 16), "f48": (13, 14)}
KERNELS = {"f32a": ("f32", (13, 14)), "f32b": ("f32", (15, 16)), "f48k13": ("f48", (13,)), "f48k14": ("f48", (14,))}


# ---- helpers -------------------------------------------------------------------------------------------------------------------------------------
def _fin(x):
    return x is not None and not isinstance(x, bool) and math.isfinite(x)


def _valid(r):
    return bool(r.get("ok")) and _fin(r.get("downforce")) and _fin(r.get("drag"))


def _t(dof):  # t_{0.95,dof}: the 0.95 quantile (one-sided), literal reading of the subscript
    return float(stats.t.ppf(0.95, dof))


def _quad(U):  # columns [p, c, r, p^2, c^2, r^2, pc, pr, cr]
    p, c, r = np.atleast_2d(U).T
    return np.column_stack([p, c, r, p * p, c * c, r * r, p * c, p * r, c * r])


@lru_cache(maxsize=1)
def _grid():  # 81 points per axis over the box, C order (pitch slowest)
    P, C, R = np.meshgrid(*[np.linspace(lo, hi, N_GRID) for lo, hi in zip(LO, HI)], indexing="ij")
    U = np.column_stack([P.ravel(), C.ravel(), R.ravel()])
    return U, _quad(U)


def _key(u):  # evaluated-name identity: amplitudes rounded to 1e-3 (the 'u_to_spec' rounding of the name); + 0.0 folds -0.0
    return tuple(round(float(x * a), 3) + 0.0 for x, a in zip(u, A_STAR))


def _emax(K):  # E[max of K standard normals], numerical
    if K < 1:
        return None
    if K == 1:
        return 0.0
    f = lambda x: K * x * stats.norm.pdf(x) * stats.norm.cdf(x) ** (K - 1)
    return float(integrate.quad(f, -12, 12, epsabs=1e-13, epsrel=1e-13, limit=500)[0])


# ---- data: runs -> data loss -> paired differences ---------------------------------------------------------------------------------------------------
class _D:
    def __init__(s, T):
        s.T, s.roles = T, T["roles"]
        s.tab = {k: {st: {int(p): r for p, r in ph.items()} for st, ph in (T.get("runs", {}).get(k) or {}).items()} for k in PHASES}
        s.parent = next((n for n, r in s.roles.items() if r["role"] == "parent"), None)
        s.lost = set()
        for stage, tab in s.tab.items():
            par = tab.get(s.parent, {})
            for n, ph in tab.items():
                for k, r in ph.items():
                    if n == s.parent:
                        bad = not _valid(r)
                    else:  # s5.11.1: uniform for every role (the repeat included); a run with no valid parent run at its phase enters no estimator and is not listed
                        p = par.get(k)
                        if p is None or not _valid(p):
                            continue
                        bad = not _valid(r) or any(abs(r[x] - p[x]) > BOUND * abs(p[x]) for x in RESP)
                    if bad:
                        s.lost.add((stage, n, k))

    def data_loss(s):
        return sorted(f"{n}@{st}@{k}" for st, n, k in s.lost)

    def names(s, *roles):
        return sorted((n for n, r in s.roles.items() if r["role"] in roles), key=lambda n: (roles.index(s.roles[n]["role"]), s.roles[n]["order"]))

    def one(s, role):
        x = s.names(role)
        return x[0] if x else None

    def d(s, stage, n, phases=None):  # {phase: (d_downforce, d_drag)} against the parent of the same stage and phase, after data loss
        tab, out = s.tab[stage], {}
        for k in phases or PHASES[stage]:
            r, p = tab.get(n, {}).get(k), tab.get(s.parent, {}).get(k)
            if r is None or p is None or (stage, n, k) in s.lost or (stage, s.parent, k) in s.lost:
                continue
            out[k] = tuple(r[x] - p[x] for x in RESP)
        return out

    def est(s, stage, n, phases=None):
        d = s.d(stage, n, phases)
        P = len(d)
        if not P:
            return None
        e = {"P": P, "delta_bar": {}, "sigma_d": {}, "se_eff": {}}
        for i, x in enumerate(RESP):
            c = [v[i] for v in d.values()]
            sd = float(np.std(c, ddof=1)) if P > 1 else None
            e["delta_bar"][x], e["sigma_d"][x] = math.fsum(c) / P, sd
            e["se_eff"][x] = max(sd or 0.0, FLOOR[x]) / math.sqrt(P)  # P = 1 -> the floor
        return e


# ---- s5.2 response surface ----------------------------------------------------------------------------------------------------------------------------
def _cmax(yg, zg, tau):  # first grid index (C order) of the largest y among z <= -tau m_D; None if no grid point is feasible (tie choice: first in C order)
    ok = np.flatnonzero(zg <= -tau * M_D)
    return int(ok[np.argmax(yg[ok])]) if ok.size else None


def _surface(D):
    pts = [(D.roles[n]["u"], D.est("g1", n)) for n in D.names("axial", "design")]
    pts = [(u, e) for u, e in pts if e]
    n = len(pts)
    X = _quad(np.array([u for u, _ in pts], float)) if n else np.zeros((0, 9))
    rank = int(np.linalg.matrix_rank(X)) if n else 0
    sv = np.linalg.svd(X, compute_uv=False) if n else np.zeros(1)
    cond = float(sv[0] / sv[-1]) if rank == 9 else None  # 2-norm condition number of the n x 9 design matrix; undefined (None) when rank < 9
    S = {"rank": rank, "cond": cond, "not_fit": rank < 9 or cond > 20, "beta": {x: None for x in RESP}, "sd": {x: None for x in RESP}, "poor": None}
    if not S["not_fit"]:  # on RS_NOT_FIT the coefficients and residual SDs stay null (cond is reported when rank = 9)
        for x in RESP:
            y = np.array([e["delta_bar"][x] for _, e in pts])
            S["beta"][x] = b = np.linalg.lstsq(X, y, rcond=None)[0]
            if n > 9:  # residual SD: sqrt(RSS / (n - 9)); null if n <= 9
                S["sd"][x] = float(math.sqrt(float(np.sum((y - X @ b) ** 2)) / (n - 9)))
        if n > 9:  # RS_FIT_POOR: either response's residual SD > 3 x the RMS of that response's per-point SE_eff; undefined (null) otherwise
            rms = {x: math.sqrt(math.fsum(e["se_eff"][x] ** 2 for _, e in pts) / n) for x in RESP}
            S["poor"] = any(S["sd"][x] > 3 * rms[x] for x in RESP)
    S["tg"] = {}
    if not S["not_fit"]:
        U, XG = _grid()
        yg, zg = XG @ S["beta"]["downforce"], XG @ S["beta"]["drag"]
        for ti, tau in enumerate(TARGETS):
            i = _cmax(yg, zg, tau)
            S["tg"][ti] = None if i is None else (U[i], float(yg[i]), float(zg[i]))
    return S


def _lists(D, S):  # per-target candidate lists: u*_tau then the Sobol cloud (filtered, y descending), already-evaluated names excluded
    ev = {_key(r["u"]) for r in D.roles.values() if r["role"] in FREEZE1 and r.get("u") is not None}  # axial, design, M, ref, R
    out = []
    for ti, tau in enumerate(TARGETS):
        if S["tg"].get(ti) is None or S["tg"][ti][1] <= 0:  # no feasible grid point, or no predicted gain (y* <= 0): the target contributes nothing (still reported)
            out.append([])
            continue
        us, ys, _ = S["tg"][ti]
        # cloud = clip(u* + R (2x - 1), lo, hi) for the unit-cube Sobol point x (s5.2); the target index is 0-based
        cu = np.clip(us + R_CLOUD * (2 * qmc.Sobol(d=3, scramble=True, seed=SEED_CLOUD + ti).random(N_CLOUD) - 1), LO, HI)
        Xc = _quad(cu)
        yc, zc = Xc @ S["beta"]["downforce"], Xc @ S["beta"]["drag"]
        keep = (zc <= -tau * M_D) & (yc >= 0.9 * ys)
        seen, L = set(ev), []
        for u in [us] + list(cu[keep][np.argsort(-yc[keep], kind="stable")]):
            if _key(u) not in seen:
                seen.add(_key(u))
                L.append(u)
        out.append(L)
    return out


def _select(items):  # items: [(target_index, y_pred, admissible)] in gated order -> proposal indices (s5.2)
    adm = [i for i, it in enumerate(items) if it[2]]
    first = [max((i for i in adm if items[i][0] == t), key=lambda i: (items[i][1], -i)) for t in sorted({items[i][0] for i in adm})]
    rest = sorted((i for i in adm if i not in first), key=lambda i: (-items[i][1], i))
    return (first + rest)[:N_PROP]


def _gate(T, D, S):  # regenerate the gated order; admissibility from T["gating"] by position
    G, mism, gated, items = T.get("gating") or [], [], [], []
    lists = _lists(D, S) if not S["not_fit"] else [[], [], []]
    order, taken = [], set()  # round-robin; a point already taken by an earlier-popped list is skipped (dedupe by name key)
    for j in range(max(map(len, lists), default=0)):
        for ti, L in enumerate(lists):
            if j < len(L) and _key(L[j]) not in taken:
                taken.add(_key(L[j]))
                order.append((ti, L[j]))
    has, cnt, pos = [any(ti == t for ti, _ in order) for t in range(len(TARGETS))], [0] * len(TARGETS), 0  # targets with >= 1 queued point AFTER the cross-list dedup
    while pos < len(order) and len(gated) < GATE_CAP:
        for ti, u in order[pos:pos + GATE_ROUND]:
            i = len(gated)
            if i >= len(G):
                mism.append(f"gating[{i}]")
                return gated, items, mism
            g = G[i]
            q = _quad(u)[0]
            yv, zv = float(q @ S["beta"]["downforce"]), float(q @ S["beta"]["drag"])
            if [round(float(x), 6) for x in g["u"]] != [round(float(x), 6) for x in u]:
                mism.append(f"gating[{i}].u")
            if g.get("target_index") != ti:
                mism.append(f"gating[{i}].target_index")
            for k, v in (("y_pred", yv), ("z_pred", zv)):  # loose (1e-6 N): the record may carry u rounded to 6 decimals; a wrong surface differs by >> 1e-6
                if not (_fin(g.get(k)) and abs(g[k] - v) <= 1e-6):
                    mism.append(f"gating[{i}].{k}")
            gated.append([ti, [round(float(x), 6) for x in u]])
            items.append((ti, yv, bool(g["admissible"])))
            cnt[ti] += bool(g["admissible"])
        pos += GATE_ROUND
        if all(cnt[t] >= N_PER_TARGET for t in range(len(TARGETS)) if has[t]):
            break
    if len(G) > len(gated):
        mism.append(f"gating[{len(gated)}]")
    names = [g.get("name") for g in G]
    mism += [f"gating[{i}].name" for i, n in enumerate(names) if n in names[:i]]  # INTERFACE: every name appears at most once
    return gated, items, mism


def _rs(T, D, S):
    b, tg = S["beta"], S["tg"]
    t1 = tg.get(0)
    out = {
        "data_loss": D.data_loss(),
        "fit": {"downforce": {"coef": None if b["downforce"] is None else [float(v) for v in b["downforce"]]},
                "drag": {"coef": None if b["drag"] is None else [float(v) for v in b["drag"]]},
                "rank": S["rank"], "cond": S["cond"], "residual_sd": dict(S["sd"])},
        "rs_fit_poor": S["poor"], "rs_not_fit": bool(S["not_fit"]),
        "u_star_1": None if t1 is None else [float(v) for v in t1[0]], "y_star_1": None if t1 is None else t1[1],
        "pool_limited_pre": t1 is not None and t1[1] >= X_STAR,
        "targets": {f"{tau:g}": ({"u_star": None, "y_pred": None, "z_pred": None} if tg.get(ti) is None else
                                       {"u_star": [float(v) for v in tg[ti][0]], "y_pred": tg[ti][1], "z_pred": tg[ti][2]})
                    for ti, tau in enumerate(TARGETS)},
    }
    gated, items, mism = _gate(T, D, S)
    out["gated"], out["stop_after"], out["proposals"] = gated, len(gated), _select(items)
    if mism:
        out["gating_mismatch"] = mism
    return out


# ---- s5.4 finalist, R-best, search_complete -------------------------------------------------------------------------------------------------------------------
def _pick(D, names, stage_of):  # largest exploration downforce difference among the drag-feasible; exact ties -> first in registered order
    best = None
    for n in names:
        e = D.est(stage_of(n), n)
        if e and e["delta_bar"]["drag"] <= 0 and (best is None or e["delta_bar"]["downforce"] > best[1]["delta_bar"]["downforce"]):
            best = (n, e)
    return best


def _finalist(T, D, S):
    stage_of = lambda n: "g2" if D.roles[n]["role"] == "proposal" else "g1"
    names = D.names("axial", "design", "proposal")
    cands = {}
    for n in names:
        e = D.est(stage_of(n), n)
        cands[n] = {"delta_bar": dict(e["delta_bar"]) if e else {"downforce": None, "drag": None}, "P": e["P"] if e else 0,
                    "se_eff": dict(e["se_eff"]) if e else {"downforce": None, "drag": None}, "feasible": bool(e and e["delta_bar"]["drag"] <= 0)}
    best = _pick(D, names, stage_of)
    fut = None
    if best is None:
        fut = "NO_FEASIBLE_CANDIDATE"
    elif best[1]["delta_bar"]["downforce"] < X_STAR - 3 * best[1]["se_eff"]["downforce"]:
        fut = "GAIN_BELOW_MIN_AT_SELECTION"
    # search_complete: every G1 search state (parent, axial, design) has both phases (R, M, ref, NC losses do not count: s5.9 'no effect on the outcome'),
    # rs fit, every proposal has both phases
    g1_ok = D.parent is not None and all(len(D.d("g1", n)) == 2 for n in D.names("parent", "axial", "design"))
    fit_ok = not S["not_fit"]
    g2_ok = all(len(D.d("g2", n)) == 2 for n in D.names("proposal"))
    rb = _pick(D, D.names("random"), lambda n: "g1")
    G = T.get("gating") or []
    prop = [G[i]["name"] for i in _select([(g["target_index"], g["y_pred"], bool(g["admissible"])) for g in G])]
    out = {"data_loss": D.data_loss(), "candidates": cands, "finalist": None if fut else best[0], "futility": fut,
           "search_complete": bool(g1_ok and fit_ok and g2_ok),
           "pool_limited": bool(S["tg"].get(0) is not None and S["tg"][0][1] >= X_STAR and not any(
               c["feasible"] and c["delta_bar"]["downforce"] >= X_STAR for c in cands.values())),
           "r_best": rb[0] if rb else None, "K_opt": len(names), "K_rand": len(D.names("random")), "proposals_from_gating": prop}
    if D.names("proposal") != prop:
        out["gating_mismatch"] = ["roles.proposals"]
    return out, {"g1_ok": g1_ok, "fit_ok": fit_ok, "g2_ok": g2_ok}


# ---- s5.5 / s5.6 / s5.7 / s5.8 ----------------------------------------------------------------------------------------------------------------------
def _G(e):
    d, se, t = e["delta_bar"]["downforce"], e["se_eff"]["downforce"], _t(e["P"] - 1)
    return {"decision": "FAIL" if d < X_STAR else "PASS" if d > 3 * se else "UNRESOLVED", "GAIN_RESOLVED_ABOVE_MIN": bool(d - t * se >= X_STAR)}


def _Dr(e):
    d, se, t = e["delta_bar"]["drag"], e["se_eff"]["drag"], _t(e["P"] - 1)
    if d <= 0:
        return {"decision": "PASS", "label": "PASS_RESOLVED" if d + t * se <= 0 else "PASS_UNRESOLVED"}
    return {"decision": "VIOLATION", "label": "VIOLATION_UNRESOLVED" if d <= t * se else "VIOLATION_RESOLVED"}


def _R3(D, s):
    e = D.est("f48", s)
    if not e:
        return None
    d, se = e["delta_bar"]["downforce"], e["se_eff"]["downforce"]
    common = sorted(set(D.d("f48", s)) & set(D.d("f32", s, (13, 14))))  # Delta_bar_32(k13, k14): the f32 mean over the phases common to Phi_48 and the finalist's f32 phases in {13, 14}
    b = D.est("f32", s, phases=common) if common else None  # Delta_bar_48 itself stays the mean over Phi_48 (s5.11.11 redefines only the flow_32 side)
    d32 = b["delta_bar"]["downforce"] if b else None
    ratio = d / d32 if d32 else None
    return {"label": "R3_CONFIRMED" if d > 3 * se else "R3_SIGN_SPLIT" if d <= 0 else "R3_UNRESOLVED",
            "R3_RATIO_IN_BAND": None if ratio is None else bool(0.8 <= ratio <= 1.25), "G48_ABOVE_MIN": bool(d >= X_STAR), "G48_MARGIN": d - X_STAR,
            "R3_E2_EXCEEDED": None if b is None else bool(abs(d - d32) > TWO_SD_J),
            "R3_DRAG_SAME_SIGN": None if b is None else bool(e["delta_bar"]["drag"] * b["delta_bar"]["drag"] > 0)}  # same strict sign (a zero is not 'same')


def _nc(D, stage):
    n = D.one("nc")
    e = D.est(stage, n) if n else None
    if not e:
        return {"z": None, "label": None}
    z = abs(e["delta_bar"]["downforce"] - NC_REF) / math.sqrt((3e-4 / math.sqrt(e["P"])) ** 2 + NC_SE ** 2)
    return {"z": z, "label": "CONSISTENT" if z <= 3.5 else "NOT_CONSISTENT"}


def _det(D, stage, k):  # raw parent_repeat vs raw parent of the same kernel and phase k (g1k11: 11; f32a: 13); both responses against the downforce floor, strict
    r, p = D.tab[stage].get(D.one("parent_repeat"), {}).get(k), D.tab[stage].get(D.parent, {}).get(k)
    if r is None or not r.get("ok") or p is None or not _valid(p):  # NOT_JUDGED: repeat absent / not ok (or no valid parent run to compare with)
        return {"max_abs_diff": None, "nondeterminism": False, "judged": False}
    if not _valid(r):  # ok but a non-finite force against a finite ok parent: not reproduced
        return {"max_abs_diff": None, "nondeterminism": True, "judged": True}
    m = {x: abs(r[x] - p[x]) for x in RESP}
    return {"max_abs_diff": m, "nondeterminism": bool(max(m.values()) > FLOOR["downforce"]), "judged": True}


def _ctrl(D, f, o, none, lab):  # per-phase e_k = Delta_f,k - Delta_o,k (downforce), t_{0.95,n-1} interval
    if o is None:
        return none
    a, b = D.d("f32", f), D.d("f32", o)
    e = [a[k][0] - b[k][0] for k in sorted(set(a) & set(b))]
    if len(e) < 2:
        return lab[2]
    m, se, t = math.fsum(e) / len(e), float(np.std(e, ddof=1)) / math.sqrt(len(e)), _t(len(e) - 1)
    return lab[0] if m - t * se > 0 else lab[1] if m + t * se < 0 else lab[2]


def _passes(D, s):
    e = D.est("f32", s)
    r = _R3(D, s)
    return bool(e and e["P"] >= 3 and r and _G(e)["decision"] == "PASS" and _Dr(e)["decision"] == "PASS" and r["label"] == "R3_CONFIRMED")


def _main(T, D, fin, ex):
    f, rb, M = fin["finalist"], fin["r_best"], D.one("manual")
    NC = {"g1": _nc(D, "g1"), "f32": _nc(D, "f32")}
    det = {"g1k11": _det(D, "g1", 11), "f32a": _det(D, "f32", 13)}
    a, b = D.tab["f32"].get(D.parent, {}).get(11), D.tab["g1"].get(D.parent, {}).get(11)  # parent replay (f32 phase 11) vs the g1 parent at phase 11, raw forces
    gd = {x: abs(a[x] - b[x]) for x in RESP} if a is not None and b is not None and _valid(a) and _valid(b) else None
    drift = {"max_abs_diff": gd, "drift": bool(gd and max(gd.values()) > FLOOR["downforce"])}  # both responses against the downforce floor
    e32, e48 = (D.est("f32", f), D.est("f48", f)) if f else (None, None)
    full = bool(e32 and e32["P"] >= 3)
    G, Dd, R3 = (_G(e32) if full else None), (_Dr(e32) if full else None), (_R3(D, f) if f else None)
    conf = {"f32": None, "f48": None}
    for k, e in (("f32", e32), ("f48", e48)):
        if e:
            conf[k] = {"delta_bar": e["delta_bar"], "sigma_d": e["sigma_d"], "se_eff": e["se_eff"], "P": e["P"]}
    sb = None
    if full:
        I, E = e32["delta_bar"]["downforce"] / J48, _emax(fin["K_opt"])
        b = [E * s for s in SIGMA_DISC]
        g = [RETENTION[0] * (I - b[0] / J48), RETENTION[1] * (I - b[1] / J48)]
        lab = ["XV_MARGIN_ADEQUATE" if v >= XV_FLOOR else "XV_MARGIN_THIN" for v in g]
        sb = {"b_K": {"central": b[0], "upper": b[1]}, "g_XV_exp": {"central": g[0], "pessimistic": g[1]}, "XV_MARGIN": {"central": lab[0], "pessimistic": lab[1]}}
    ctrl = {"OPT_VS_RANDOM": None, "OPT_VS_MANUAL": None, "RANDOM_FEASIBLE_GAIN": bool(rb and _passes(D, rb)), "K_MISMATCH": fin["K_opt"] != fin["K_rand"]}
    if f:
        ctrl["OPT_VS_RANDOM"] = _ctrl(D, f, rb, "RANDOM_NO_FEASIBLE", ("OPT_BEATS_RANDOM", "RANDOM_BEATS_OPT", "OPT_RANDOM_UNRESOLVED"))
        ctrl["OPT_VS_MANUAL"] = _ctrl(D, f, M, "MANUAL_NONE", ("OPT_BEATS_MANUAL", "MANUAL_BEATS_OPT", "OPT_MANUAL_UNRESOLVED"))
    # ---- s5.8 evaluation order
    # F not completed (budget): a confirmation kernel that is neither declared lost nor has any run row (of any state) at its phases was never run (s5.11.15)
    lost = set(T.get("lost_kernels") or [])
    unrun = [k for k, (st, ph) in KERNELS.items() if k not in lost and not any(x in rows for rows in D.tab[st].values() for x in ph)]
    if not (D.parent and D.d("g1", D.parent) and D.est("g1", D.one("nc") or "")):
        oc, cause = "SCREEN01_INCOMPLETE", ["DATA_G1"]                                                                              # 1
    elif NC["g1"]["label"] == "NOT_CONSISTENT" or det["g1k11"]["nondeterminism"]:
        oc, cause = "SCREEN01_INVALID", (["NC_G1"] if NC["g1"]["label"] == "NOT_CONSISTENT" else []) + (["NONDETERMINISM_G1K11"] if det["g1k11"]["nondeterminism"] else [])  # 2
    elif f is None:                                                                                                                  # 3
        if ex["g1_ok"] and ex["fit_ok"] and ex["g2_ok"]:
            oc, cause = "SCREEN01_NO_GAIN", [fin["futility"]]
        else:
            oc, cause = "SCREEN01_INCOMPLETE", (["DATA_G1"] if lost & {"g1k11", "g1k12"} or not ex["g1_ok"] else []) + (["DATA_REFINE"] if not ex["fit_ok"] else []) \
                + (["DATA_G2"] if ex["fit_ok"] and not ex["g2_ok"] else [])  # all that apply, stage order (s5.11.7)
    elif unrun or not full or not e48 or NC["f32"]["label"] is None:                                                                 # 4
        oc, cause = "SCREEN01_INCOMPLETE", ["BUDGET" if unrun else "DATA_F"]
    elif NC["f32"]["label"] == "NOT_CONSISTENT" or det["f32a"]["nondeterminism"]:                                                    # 5
        oc, cause = "SCREEN01_INVALID", (["NC_F"] if NC["f32"]["label"] == "NOT_CONSISTENT" else []) + (["NONDETERMINISM_F32A"] if det["f32a"]["nondeterminism"] else [])
    else:
        fails = (["GAIN_BELOW_MIN"] if G["decision"] == "FAIL" else []) + (["DRAG_VIOLATION"] if Dd["decision"] == "VIOLATION" else []) \
            + (["GRID_SIGN_SPLIT"] if R3["label"] == "R3_SIGN_SPLIT" else [])
        unres = (["G_UNRESOLVED"] if G["decision"] == "UNRESOLVED" else []) + (["R3_UNRESOLVED"] if R3["label"] == "R3_UNRESOLVED" else [])
        oc, cause = ("SCREEN01_NO_GAIN", fails) if fails else ("SCREEN01_INCONCLUSIVE", unres) if unres else ("SCREEN01_GAIN", [])  # 6, 7, 8
    return {**fin, "outcome": oc, "cause": cause, "G": G, "D": Dd, "R3": R3, "NC": NC, "determinism": det, "generation_drift": drift,
            "controls": ctrl, "selection_bias": sb, "confirmation": conf}


def check(T: dict) -> dict:
    D = _D(T)
    S = _surface(D)
    if T["stage"] == "rs":
        return _rs(T, D, S)
    fin, ex = _finalist(T, D, S)
    return fin if T["stage"] == "finalist" else _main(T, D, fin, ex)


# ---- compare --------------------------------------------------------------------------------------------------------------------------------------
_FIN = {"data_loss": True, "candidates": {"*": {"delta_bar": True, "P": True, "se_eff": True, "feasible": True}}, "finalist": True, "futility": True,
        "search_complete": True, "pool_limited": True, "r_best": True, "K_opt": True, "K_rand": True, "proposals_from_gating": True}
SPECS = {
    "rs": {"data_loss": True, "fit": {"downforce": {"coef": True}, "drag": {"coef": True}, "rank": True, "cond": True, "residual_sd": True},
           "rs_fit_poor": True, "rs_not_fit": True, "u_star_1": True, "y_star_1": True, "pool_limited_pre": True,
           "targets": {"*": {"u_star": True, "y_pred": True, "z_pred": True}}, "gated": True, "stop_after": True, "proposals": True},
    "finalist": _FIN,
    "main": {**_FIN, **{k: True for k in ("outcome", "cause", "G", "D", "R3", "NC", "determinism", "generation_drift", "controls", "selection_bias", "confirmation")}},
}
_MISSING = object()


def _close(a, b):
    if isinstance(a, bool) or isinstance(b, bool) or not isinstance(a, (int, float)) or not isinstance(b, (int, float)):
        return False
    return a == b or (math.isnan(a) and math.isnan(b)) or abs(a - b) <= 1e-9 * max(1.0, abs(a), abs(b))


def _norm(k):  # '1' / '1.0' / 1 -> the same tau key
    try:
        return repr(float(k))
    except (TypeError, ValueError):
        return k


def _cmp(a, b, path, out):
    if a is _MISSING or b is _MISSING:
        if not (a is _MISSING and b is _MISSING):
            out.append(path)
    elif isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b), key=str):
            _cmp(a.get(k, _MISSING), b.get(k, _MISSING), f"{path}.{k}", out)
    elif isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
        if len(a) != len(b):
            out.append(path)
        for i, (x, y) in enumerate(zip(a, b)):
            _cmp(x, y, f"{path}[{i}]", out)
    elif isinstance(a, (bool, str, type(None))) or isinstance(b, (bool, str, type(None))):
        if type(a) is not type(b) or a != b:
            out.append(path)
    elif not _close(a, b):
        out.append(path)


def _walk(a, b, spec, path, out):
    if spec is True or not (isinstance(a, dict) and isinstance(b, dict)):
        return _cmp(a, b, path, out)
    sub_path = lambda x: f"{path}.{x}" if path else str(x)
    for k, sub in spec.items():
        if k == "*":
            na, nb = ({_norm(x): v for x, v in d.items()} for d in (a, b))
            for x in sorted(set(na) | set(nb), key=str):
                _walk(na.get(x, _MISSING), nb.get(x, _MISSING), sub, sub_path(x), out)
        else:
            _walk(a.get(k, _MISSING), b.get(k, _MISSING), sub, sub_path(k), out)


def _py(x):  # numpy scalars / arrays -> python
    if isinstance(x, dict):
        return {k: _py(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_py(v) for v in x]
    return x.tolist() if isinstance(x, (np.generic, np.ndarray)) else x


def compare(a: dict, b: dict, stage: str) -> list[str]:
    out: list[str] = []
    a, b = _py(a), _py(b)
    _walk(a, b, SPECS[stage], "", out)
    out += [m for d in (a, b) for m in d.get("gating_mismatch", [])]
    return list(dict.fromkeys(out))
