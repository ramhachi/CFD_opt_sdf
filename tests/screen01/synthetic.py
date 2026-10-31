"""SCREEN-01 (#64): synthetic harness-like forces and normalised inputs T for every branch of the registered rules (registration §5.1-§5.9).

`make(stage, ...)` builds a consistent study (roles, G1 / G2 / F runs, the gating record of the refinement) from a quadratic truth: downforce
`quad9(u) @ BY`, drag `quad9(u) @ BZ` (a feasible optimum near u = (0.3, -1.5, 1), drag-neutral combinations gain downforce, single downforce modes cost drag).
Edits are hooks `edits[point](T, al)` called after the runs of that point exist: "g1" (before the refinement gates), "g2", "f" (confirmation); `al` names the
roles (parent, repeat, nc, manual, ref, axial[], design[], random[], proposals[], finalist, rbest).  Helpers: set_delta, set_run, drop, lose.
`BRANCHES[name] = (stage, kwargs)` is the registry shared by the analyzer tests and the cross-check tests; `branch(name)` is cached.
"""
from __future__ import annotations

import copy
import math
import sys
import types
import zlib
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts"), str(ROOT / "scripts/fid01"), str(ROOT / "scripts/screen01")]
import analyze_screen01 as S  # noqa: E402
import screen01_pool as P  # noqa: E402

PARENT, REPEAT, ROLL = "v18__parent", "v18__parent__repeat", "v18__roll_p25"
F0 = {"downforce": 0.2658, "drag": 0.2800}
PSHIFT = {"11": 0.0, "12": 2e-3, "13": -1e-3, "14": 1.5e-3, "15": -2e-3, "16": 0.5e-3}
BY = [1.0e-2, -1.2e-2, -3.0e-3, -1.0e-3, 1.0e-3, 0.0, 0.0, 0.0, 2.0e-3]    # [p, c, r, p^2, c^2, r^2, pc, pr, cr]
BZ = [7.0e-3, -2.0e-3, -1.0e-2, 0.0, 5.0e-4, 0.0, 0.0, 0.0, 0.0]
KERNEL_OF = {"g1": {"11": "g1k11", "12": "g1k12"}, "g2": {"11": "g2", "12": "g2"}, "f32": {"11": "f32a", "13": "f32a", "14": "f32a", "15": "f32b", "16": "f32b"},
             "f48": {"13": "f48k13", "14": "f48k14"}}
RATIO48 = 0.98


def sname(u) -> str:
    return P.D.name(P.u_to_spec(u))


def surface(coef, u) -> float:
    return float(P.quad9(u)[0] @ np.asarray(coef))


def _design_u():
    pool = P.sobol_u(64, 20261030)
    adm = np.random.default_rng(7).random(64) < 0.55
    idx, X = P.d_optimal9(pool[adm], 9)
    assert np.linalg.matrix_rank(X) == 9 and np.linalg.svd(X, compute_uv=False)[0] / np.linalg.svd(X, compute_uv=False)[-1] <= 20
    return pool[adm][idx]


AXIAL_U = [("pitch", 1, [1, 0, 0]), ("pitch", -1, [-1, 0, 0]), ("camber", 1, [0, 1, 0]), ("camber", -1, [0, -1, 0]), ("reflex", 1, [0, 0, 1]), ("reflex", -1, [0, 0, -1])]
DESIGN_U = _design_u()
RANDOM_U = P.sobol_u(19, 20261033)
MANUAL_U = [-0.38 / 3.1, -1.0, 0.0]
REF_U = [0.0, -11.3 / 19.7, -11.3 / 29.3]


def base_roles(n_random=19, manual=True) -> dict:
    r = {PARENT: {"role": "parent", "order": 0, "u": None}, REPEAT: {"role": "parent_repeat", "order": 0, "u": None}, ROLL: {"role": "nc", "order": 0, "u": None}}
    for i, (_, _, u) in enumerate(AXIAL_U):
        r[sname(u)] = {"role": "axial", "order": i, "u": [float(x) for x in u]}
    for i, u in enumerate(DESIGN_U):
        r[sname(u)] = {"role": "design", "order": i, "u": [float(x) for x in u]}
    for i, u in enumerate(RANDOM_U[:n_random]):
        r[sname(u)] = {"role": "random", "order": i, "u": [float(x) for x in u]}
    r[sname(REF_U)] = {"role": "ref", "order": 0, "u": REF_U}
    if manual:
        r[sname(MANUAL_U)] = {"role": "manual", "order": 0, "u": MANUAL_U}
    return r


def aliases(roles, proposals=(), finalist=None, rbest=None):
    nm = lambda role: S.names(roles, role)   # noqa: E731
    return types.SimpleNamespace(parent=PARENT, repeat=REPEAT, nc=ROLL, manual=(nm("manual") or [None])[0], ref=nm("ref")[0], axial=nm("axial"), design=nm("design"),
                                 random=nm("random"), proposals=list(proposals), finalist=finalist, rbest=rbest)


# ---- run generation and edit helpers ----------------------------------------------------------------------------------------------------------------
def level(g, ph):
    return F0["downforce"] + PSHIFT[ph] + (0.02 if g == "f48" else 0.0), F0["drag"] + 0.5 * PSHIFT[ph] + (0.02 if g == "f48" else 0.0)


def noise_of(seed, tag, sd) -> float:
    return float(np.random.default_rng(zlib.crc32(f"{seed}|{tag}".encode())).normal(0.0, sd)) if sd else 0.0


def truth_delta(T, s, g, by, bz):
    r = T["roles"][s]
    if r["role"] == "nc":
        return S.NC_REF, -2e-4
    if r["u"] is None:
        return 0.0, 0.0
    k = RATIO48 if g == "f48" else 1.0
    return k * surface(by, r["u"]), surface(bz, r["u"])


def fill(T, g, spec, by, bz, noise, seed):
    """spec = {state: [phases]}; every run = parent level + truth difference + seeded placement noise (the repeat copies the parent run)."""
    for s, phs in spec.items():
        for ph in phs:
            if s == REPEAT:
                T["runs"][g].setdefault(s, {})[ph] = dict(T["runs"][g][PARENT][ph])
                continue
            d = truth_delta(T, s, g, by, bz)
            lv = level(g, ph)
            T["runs"][g].setdefault(s, {})[ph] = {r: lv[i] + (d[i] if s != PARENT else 0.0) + noise_of(seed, f"{g}|{s}|{ph}|{r}", noise[i]) for i, r in enumerate(S.RESP)} | {"ok": True}


def parent_run(T, g, ph):
    return T["runs"][g][PARENT][ph]


def set_delta(T, g, s, ph, ddf=None, ddr=None):
    """Make the run of state s at phase ph (or every phase) differ from the same-group parent run by ddf / ddr (None keeps that component)."""
    for p in ([ph] if ph else list(T["runs"][g][s])):
        pr, r = parent_run(T, g, p), T["runs"][g][s][p]
        if ddf is not None:
            r["downforce"] = pr["downforce"] + ddf
        if ddr is not None:
            r["drag"] = pr["drag"] + ddr


def set_run(T, g, s, ph, **kw):
    T["runs"][g][s][ph].update(kw)


def drop(T, g, s, ph=None):
    for p in ([ph] if ph else list(T["runs"][g].get(s, {}))):
        T["runs"][g][s].pop(p, None)


def _remove(T, kernel):
    for g, m in KERNEL_OF.items():
        for ph, k in m.items():
            if k == kernel and g in T["runs"]:
                for s in T["runs"][g]:
                    T["runs"][g][s].pop(ph, None)


def lose(T, kernel):
    """The kernel is declared lost: its runs are not in the tables."""
    _remove(T, kernel)
    T["lost_kernels"] = sorted({*T["lost_kernels"], kernel})


def skip(T, kernels, reason):
    """The kernels were never pushed (--not-pushed KERNEL=REASON, registration §5.11.19): no runs, not lost."""
    for k in kernels:
        _remove(T, k)
    T["not_pushed"] = {**T["not_pushed"], **{k: reason for k in kernels}}


CONF = ("f32a", "f32b", "f48k13", "f48k14")


def no_f_groups(T):
    for g in ("f32", "f48"):
        T["runs"].pop(g, None)


_GATE = {}


def default_oracle(u) -> bool:
    return sum(sname(u).encode()) % 7 < 4


def retarget(roles, role, order, u) -> None:
    """Move the state of (role, order) to the point u (its name follows the §3.2 identity of u)."""
    old = next(n for n, r in roles.items() if r["role"] == role and r["order"] == order)
    roles[sname(u)] = {**roles.pop(old), "u": [float(x) for x in u]}


def make(stage="main", *, by=BY, bz=BZ, noise=(0.0, 0.0), n_random=19, manual=True, oracle=None, edits=None, seed=0, n_grid=None, roles_edit=None) -> dict:
    """roles_edit(roles, n_grid) may move registered states (retarget) before any force is generated."""
    n_grid, edits, oracle = n_grid or S.GRID_N, edits or {}, oracle or default_oracle
    roles = base_roles(n_random, manual)
    if roles_edit:
        roles_edit(roles, n_grid)
    T = {"schema": "screen01-T-v1", "stage": "rs", "roles": roles, "runs": {"g1": {}}, "lost_kernels": [], "not_pushed": {}, "gating": []}
    g1 = {s: ["11", "12"] for s in roles if roles[s]["role"] not in ("parent_repeat",)}
    fill(T, "g1", {**g1, REPEAT: ["11"]}, by, bz, noise, seed)
    edits.get("g1", lambda T, al: None)(T, aliases(roles))
    key = (n_grid, repr(sorted((s, sorted((p, tuple(sorted(r.items()))) for p, r in ph.items())) for s, ph in T["runs"]["g1"].items())), tuple(T["lost_kernels"]), id(oracle))
    if key not in _GATE:
        _GATE[key] = (oracle, S.rs_gate(T, oracle, n_grid)["gating"])      # the oracle is kept so that its id is not reused
    T["gating"] = copy.deepcopy(_GATE[key][1])
    if stage == "rs":
        return T
    props = S.compute(T)["proposal_states"]
    for p in props:
        T["roles"][p["name"]] = {"role": "proposal", "order": p["rank"], "u": p["u"]}
    T["stage"] = "finalist"
    pn = [p["name"] for p in props]
    if pn:
        T["runs"]["g2"] = {}
        fill(T, "g2", {s: ["11", "12"] for s in [PARENT, *pn]}, by, bz, noise, seed)
    edits.get("g2", lambda T, al: None)(T, aliases(T["roles"], pn))
    fin = S.compute(T)
    al = aliases(T["roles"], pn, fin["finalist"], fin["r_best"])
    if stage == "finalist":
        return T
    T["stage"] = "main"
    if fin["finalist"] is not None:
        sts = [fin["finalist"], *([fin["r_best"]] if fin["r_best"] else []), *([al.manual] if al.manual else []), ROLL]
        T["runs"]["f32"], T["runs"]["f48"] = {}, {}
        fill(T, "f32", {PARENT: ["11", "13", "14", "15", "16"], REPEAT: ["13"], **{s: ["13", "14", "15", "16"] for s in sts}}, by, bz, noise, seed)
        fill(T, "f48", {s: ["13", "14"] for s in [PARENT, fin["finalist"], *([fin["r_best"]] if fin["r_best"] else [])]}, by, bz, noise, seed)
    edits.get("f", lambda T, al: None)(T, al)
    return T


# ---- the branch registry ----------------------------------------------------------------------------------------------------------------------------
def e(**hooks):
    return hooks


def _weak(k):
    return [c * k for c in BY]


def _positive_drag(T, al):
    for s in al.axial + al.design + al.random:
        for g in ("g1",):
            for ph in T["runs"][g][s]:
                set_delta(T, g, s, ph, ddr=abs(T["runs"][g][s][ph]["drag"] - parent_run(T, g, ph)["drag"]) + 1e-3)


def _positive_drag_g2(T, al):
    for s in al.proposals:
        for ph in T["runs"]["g2"][s]:
            set_delta(T, "g2", s, ph, ddr=1e-3)


def _lose_both_g1_nc_ok(T, al):
    for ph in ("11", "12"):
        drop(T, "g1", al.parent, ph)


def _lose_points(k, how="ok"):
    """DATA_LOSS of the first k axial/design points at both phases: ok = false, or a null force."""
    def f(T, al):
        for s in (al.axial + al.design)[:k]:
            for ph in ("11", "12"):
                set_run(T, "g1", s, ph, **({"ok": False} if how == "ok" else {"downforce": None}))
    return f


def _misfit(T, al):
    for i, s in enumerate(al.design[:4]):
        for ph in ("11", "12"):
            set_delta(T, "g1", s, ph, ddf=T["runs"]["g1"][s][ph]["downforce"] - parent_run(T, "g1", ph)["downforce"] + (0.01 if i % 2 else -0.01))


def _tie(a, b):
    def f(T, al):
        x, y = getattr(al, a[0])[a[1]], getattr(al, b[0])[b[1]]
        for s in (x, y):
            for ph in ("11", "12"):
                set_delta(T, "g1", s, ph, ddf=0.05, ddr=-1e-3)
    return f


def _f(df32=None, dr32=None, df48=None, dr48=None, who="finalist"):
    """Set the confirmation differences of a role: scalars or per-phase lists (flow_32 phases 13-16, flow_48 phases 13-14)."""
    def f(T, al):
        s = getattr(al, who)
        for g, df, dr in (("f32", df32, dr32), ("f48", df48, dr48)):
            if s not in T["runs"].get(g, {}):
                continue
            phs = list(T["runs"][g][s])
            for i, ph in enumerate(phs):
                pick = lambda v: None if v is None else (v[i] if isinstance(v, (list, tuple)) else v)   # noqa: E731
                set_delta(T, g, s, ph, pick(df), pick(dr))
    return f


def _chain(*fs):
    def f(T, al):
        for x in fs:
            x(T, al)
    return f


def _nc_f(d):
    return lambda T, al: [set_delta(T, "f32", al.nc, ph, d) for ph in list(T["runs"]["f32"][al.nc])]


def _repeat(g, d):
    return lambda T, al: set_delta(T, g, al.repeat, None, d, d)


def _drift(d):
    def f(T, al):
        T["runs"]["f32"][al.parent]["11"].update({k: T["runs"]["g1"][al.parent]["11"][k] + d for k in S.RESP})
    return f


def _g2_df(df):
    """The first proposal gets the exploration downforce difference df with a feasible drag (the others are made worthless)."""
    def f(T, al):
        for i, s in enumerate(al.proposals):
            Y_ = df if i == 0 else -0.001
            set_delta(T, "g2", s, None, ddf=Y_, ddr=-1e-3)
    return f


def _best_design(df):
    def f(T, al):
        set_delta(T, "g1", al.design[4], None, ddf=df, ddr=-1e-3)
    return f


def _xv_edge(which, eps):
    """Confirmation downforce difference exactly at the XV margin boundary I_s of the central / pessimistic projection at K = 19 (plus eps relative)."""
    emax = S.e_max_normals(19)
    i = (S.XV_FLOOR / S.RETENTION[which] + emax * S.SIGMA_DISC["central" if which == "central" else "upper"] / S.J_B48) + eps

    def f(T, al):
        set_delta(T, "f32", al.finalist, None, ddf=i * S.J_B48, ddr=-1e-3)
        set_delta(T, "f48", al.finalist, None, ddf=i * S.J_B48)
    return f


# ---- truths and edits of the reconciliation branches (registration §5.2, §5.11) ---------------------------------------------------------------------
BY_NO_GAIN_T2 = [1e-2, -2e-3, -1.6e-2, 0, 0, 0, 0, 0, 0]     # target 2 needs reflex >= 0.909, which costs more downforce than pitch and camber give: y*_2 < 0
BZ_NO_GAIN_T2 = [0, 0, -3.3e-3, 0, 0, 0, 0, 0, 0]
BY_ALL_NEG, BZ_ALL_NEG = [0, 0, 0, -1e-2, -1e-2, -1e-2, 0, 0, 0], [0, 0, -1e-2, 0, 0, 0, 0, 0, 0]   # downforce below the parent everywhere: y*_tau < 0 for every target
BY_TIE, BZ_TIE = [1e-2, -1.2e-2, 0, -1e-3, 1e-3, 0, 0, 0, 0], [7e-3, -2e-3, 0, 0, 5e-4, 0, 0, 0, 0]  # no reflex dependence
UC, K_BOWL = np.array([0.5, -0.5, 0.5]), 4e-3                 # downforce peak and drag minimum at the grid point UC; drag(UC) = -3.001e-3 N: feasible at tau = 2 only inside a ball of radius 0.016
K_Z = (3e-3 + 1e-6) / 0.75
BY_BOWL, BZ_BOWL = list(2 * K_BOWL * UC) + [-K_BOWL] * 3 + [0, 0, 0], list(-2 * K_Z * UC) + [K_Z] * 3 + [0, 0, 0]
KEEP_9_FIT_UNDEFINED = (0, 1, 2, 3, 4, 5, 6, 7, 8)             # 6 axial + design 0-2: rank 9, cond 8.7, n = 9 (residual SD undefined)
KEEP_9_NOT_FIT_COND = (0, 1, 2, 3, 4, 5, 6, 7, 11)             # 6 axial + design 0, 1, 5: rank 9, cond 139.7 > 20 (RS_NOT_FIT with rank 9)


def search_states(roles=None):
    return [n for n, r in sorted((roles or base_roles()).items(), key=lambda kv: (kv[1]["role"], kv[1]["order"])) if r["role"] in ("axial", "design")]


def check_keep_sets():
    """The two subsets above are what the comments say (computed, not trusted)."""
    U = np.vstack([a[2] for a in AXIAL_U] + list(DESIGN_U))
    for keep, ok in ((KEEP_9_FIT_UNDEFINED, lambda r, c: r == 9 and c <= 20), (KEEP_9_NOT_FIT_COND, lambda r, c: r == 9 and 50 < c < 1e6)):
        X = P.quad9(U[list(keep)])
        sv = np.linalg.svd(X, compute_uv=False)
        assert ok(np.linalg.matrix_rank(X), sv[0] / sv[-1]), keep


def _keep_only(keep):
    """DATA_LOSS (ok = false) of both exploration phases of every axial / design state outside the kept indices (0-5 axial, 6-14 design)."""
    def f(T, al):
        for i, s in enumerate(al.axial + al.design):
            if i not in keep:
                for ph in ("11", "12"):
                    set_run(T, "g1", s, ph, ok=False)
    return f


def _design_at_ustar1(by=BY, bz=BZ, order=3):
    """A registered design point placed at u*_1 of the (noise-free) surface: its §3.2 name is then excluded from every candidate list."""
    def f(roles, n_grid):
        us = P.constrained_argmax(by, bz, P.M_D, n_grid, S.get_grid(n_grid))[0]
        retarget(roles, "design", order, us)
    return f


def _random_at_cloud(by=BY, bz=BZ):
    """A random-control state placed at the best cloud point of target 0 (the second point of its list)."""
    def f(roles, n_grid):
        res = P.propose(by, bz, lambda u: True, n_grid=n_grid, grid=S.get_grid(n_grid))
        retarget(roles, "random", 0, res["gated"][3]["u"])
    return f


def _line_design(roles, n_grid):
    for i, t in enumerate((-0.8, -0.6, -0.4, -0.2, 0.2, 0.4, 0.6, 0.8, 0.9)):
        retarget(roles, "design", i, [t, 0.0, 0.0])


def _lose_one_phase(k, ph="11"):
    def f(T, al):
        for s in (al.axial + al.design)[:k]:
            set_run(T, "g1", s, ph, ok=False)
    return f


def _nc_g1(d):
    return lambda T, al: [set_delta(T, "g1", al.nc, ph, d) for ph in ("11", "12")]


def _parent_lost_at_12(T, al):
    """The parent run at phase 12 is not ok; a non-finite design run and a not-ok NC run at phase 12 then have no valid parent run: they enter no estimator and are not listed."""
    set_run(T, "g1", al.parent, "12", ok=False)
    set_run(T, "g1", al.design[0], "12", downforce=None)
    set_run(T, "g1", al.nc, "12", ok=False)


_DUP = dict(by=_weak(0.1), edits=e(g1=_best_design(0.012), g2=_g2_df(0.001)))      # u*_1 = u*_1.5 (a slack drag margin): one point under two targets

BRANCHES = {
    # ---- stage rs ----
    "rs_base": ("rs", {}),
    "rs_noisy": ("rs", dict(noise=(1.5e-4, 3e-4), seed=3)),
    "rs_lost_point": ("rs", dict(edits=e(g1=_lose_points(1)))),
    "rs_lost_both_phases_two_points": ("rs", dict(edits=e(g1=_lose_points(2, "null")))),
    "rs_not_fit": ("rs", dict(edits=e(g1=_lose_points(8)))),
    "rs_one_kernel_lost": ("rs", dict(edits=e(g1=lambda T, al: lose(T, "g1k12")))),
    "rs_both_kernels_lost": ("rs", dict(edits=e(g1=lambda T, al: (lose(T, "g1k11"), lose(T, "g1k12"))))),
    "rs_fit_poor": ("rs", dict(edits=e(g1=_misfit))),
    "rs_no_feasible_target": ("rs", dict(bz=[0, 0, 0, 1e-2, 1e-2, 1e-2, 0, 0, 0])),
    "fin_no_proposals": ("finalist", dict(bz=[0, 0, 0, 1e-2, 1e-2, 1e-2, 0, 0, 0])),
    "rs_weak": ("rs", dict(by=_weak(0.1))),
    # ---- stage finalist ----
    "fin_base": ("finalist", {}),
    "fin_noisy": ("finalist", dict(noise=(1.5e-4, 3e-4), seed=3)),
    "fin_tie_axial_design": ("finalist", dict(edits=e(g1=_tie(("axial", 0), ("design", 0))))),
    "fin_tie_design_design": ("finalist", dict(edits=e(g1=_tie(("design", 5), ("design", 2))))),
    "fin_no_feasible": ("finalist", dict(edits=e(g1=_positive_drag, g2=_positive_drag_g2))),
    "fin_gain_below_min_at_selection": ("finalist", dict(by=_weak(0.1))),
    "fin_g2_lost": ("finalist", dict(edits=e(g2=lambda T, al: lose(T, "g2")))),
    "fin_g2_lost_weak": ("finalist", dict(by=_weak(0.1), edits=e(g2=lambda T, al: lose(T, "g2")))),
    "fin_one_proposal_phase_lost": ("finalist", dict(edits=e(g2=lambda T, al: drop(T, "g2", al.proposals[0], "12")))),
    "fin_g1_state_phase_lost": ("finalist", dict(edits=e(g1=lambda T, al: drop(T, "g1", al.axial[0], "12")))),
    "fin_g1_kernel_lost": ("finalist", dict(edits=e(g1=lambda T, al: lose(T, "g1k12")))),
    "fin_random_none_feasible": ("finalist", dict(edits=e(g1=lambda T, al: [set_delta(T, "g1", s, None, ddr=1e-3) for s in al.random]))),
    "fin_random_lost": ("finalist", dict(edits=e(g1=lambda T, al: [drop(T, "g1", s, "12") for s in al.random]))),
    "fin_k_mismatch": ("finalist", dict(n_random=18)),
    "fin_pool_limited": ("finalist", dict(edits=e(g1=lambda T, al: [set_delta(T, "g1", s, None, ddr=1e-3) for s in al.axial + al.design if T["runs"]["g1"][s]["11"]["drag"] - parent_run(T, "g1", "11")["drag"] <= 0
                                                                      and T["runs"]["g1"][s]["11"]["downforce"] - parent_run(T, "g1", "11")["downforce"] >= S.X_STAR],
                                     g2=lambda T, al: [set_delta(T, "g2", s, None, ddf=1e-3) for s in al.proposals]))),
    # ---- stage main ----
    "main_gain": ("main", {}),
    "main_gain_noisy": ("main", dict(noise=(1.5e-4, 3e-4), seed=3)),
    "main_gain_f48_one_kernel": ("main", dict(edits=e(f=lambda T, al: lose(T, "f48k14")))),
    "main_gain_drift": ("main", dict(edits=e(f=_drift(8e-4)))),
    "main_gain_no_manual": ("main", dict(manual=False)),
    "main_incomplete_no_parent_g1": ("main", dict(edits=e(g1=_lose_both_g1_nc_ok))),
    "main_incomplete_no_nc_g1": ("main", dict(edits=e(g1=lambda T, al: drop(T, "g1", al.nc)))),
    "main_invalid_nc_g1": ("main", dict(edits=e(g1=lambda T, al: [set_delta(T, "g1", al.nc, ph, 5e-3) for ph in ("11", "12")]))),
    "main_invalid_nondeterminism_g1": ("main", dict(edits=e(g1=lambda T, al: set_delta(T, "g1", al.repeat, "11", 5e-4, 0.0)))),
    "main_no_gain_no_feasible": ("main", dict(edits=e(g1=_positive_drag, g2=_positive_drag_g2))),
    "main_no_gain_futility_gain": ("main", dict(by=_weak(0.1))),
    "main_incomplete_g1_kernel": ("main", dict(by=_weak(0.1), edits=e(g1=lambda T, al: lose(T, "g1k12")))),
    "main_incomplete_refine": ("main", dict(by=_weak(0.1), edits=e(g1=_lose_points(8)))),
    "main_incomplete_g2": ("main", dict(by=_weak(0.1), edits=e(g2=lambda T, al: lose(T, "g2")))),
    "main_continue_g2_lost": ("main", dict(edits=e(g2=lambda T, al: lose(T, "g2")))),
    "main_incomplete_f32_kernel": ("main", dict(edits=e(f=lambda T, al: lose(T, "f32b")))),
    "main_incomplete_f48_both": ("main", dict(edits=e(f=lambda T, al: (lose(T, "f48k13"), lose(T, "f48k14"))))),
    "main_incomplete_nc_f": ("main", dict(edits=e(f=lambda T, al: drop(T, "f32", al.nc)))),
    "main_incomplete_f_not_run": ("main", dict(edits=e(f=lambda T, al: (skip(T, CONF, "BUDGET"), no_f_groups(T))))),
    "main_invalid_nc_f": ("main", dict(edits=e(f=_nc_f(4e-3)))),
    "main_invalid_nondeterminism_f32a": ("main", dict(edits=e(f=_repeat("f32", 4e-4)))),
    "main_no_gain_below_min": ("main", dict(edits=e(f=_f(df32=[0.005] * 4, df48=0.005)))),
    "main_no_gain_drag": ("main", dict(edits=e(f=_f(dr32=[2e-3] * 4)))),
    "main_no_gain_drag_unresolved": ("main", dict(edits=e(f=_f(dr32=[1e-3, -1e-3, 3e-3, -1e-3])))),
    "main_no_gain_sign_split": ("main", dict(edits=e(f=_f(df48=[-1e-3, -2e-3])))),
    "main_no_gain_all_three": ("main", dict(edits=e(f=_f(df32=[0.004] * 4, dr32=[2e-3] * 4, df48=-1e-3)))),
    "main_inconclusive_g": ("main", dict(edits=e(f=_f(df32=[0.0195, -0.0045, 0.0195, -0.0045], dr32=[-3e-3] * 4)))),
    "main_inconclusive_r3": ("main", dict(edits=e(f=_f(df48=[3e-4, 3e-4])))),
    "main_gain_drag_unresolved": ("main", dict(edits=e(f=_f(dr32=[-1e-3, 1e-3, -2e-3, 1e-3])))),
    "main_random_beats_opt": ("main", dict(edits=e(f=_f(df32=0.05, df48=0.05, dr32=-2e-3, dr48=-2e-3, who="rbest")))),
    "main_random_fails_g": ("main", dict(edits=e(f=_f(df32=0.002, who="rbest")))),
    "main_random_no_feasible": ("main", dict(edits=e(g1=lambda T, al: [set_delta(T, "g1", s, None, ddr=1e-3) for s in al.random]))),
    "main_manual_beats_opt": ("main", dict(edits=e(f=_f(df32=0.05, who="manual")))),
    # ---- edges, single phases, partial losses (cross-check coverage) ----
    "fin_futility_edge_kept": ("finalist", dict(by=_weak(0.1), edits=e(g2=_g2_df(S.X_STAR - 3 * S.FLOOR["downforce"] / math.sqrt(2) + 1e-6)))),
    "fin_futility_edge_dropped": ("finalist", dict(by=_weak(0.1), edits=e(g2=_g2_df(S.X_STAR - 3 * S.FLOOR["downforce"] / math.sqrt(2) - 1e-6)))),
    "fin_proposal_single_phase": ("finalist", dict(edits=e(g2=lambda T, al: [drop(T, "g2", al.proposals[0], "11"), set_run(T, "g2", al.proposals[1], "12", ok=False)]))),
    "fin_random_tie": ("finalist", dict(edits=e(g1=lambda T, al: [set_delta(T, "g1", al.random[i], None, ddf=0.06, ddr=-1e-3) for i in (3, 1)]))),
    "fin_implausible_candidate": ("finalist", dict(edits=e(g1=lambda T, al: set_delta(T, "g1", al.axial[2], None, ddf=0.09)))),
    "fin_both_g1_kernels_lost": ("finalist", dict(edits=e(g1=lambda T, al: (lose(T, "g1k11"), lose(T, "g1k12"))))),
    "main_both_g1_kernels_lost": ("main", dict(edits=e(g1=lambda T, al: (lose(T, "g1k11"), lose(T, "g1k12"))))),
    "main_nondeterminism_drag_only_g1": ("main", dict(edits=e(g1=lambda T, al: set_delta(T, "g1", al.repeat, "11", 0.0, 3e-4)))),
    "main_nondeterminism_drag_only_f32a": ("main", dict(edits=e(f=lambda T, al: set_delta(T, "f32", al.repeat, "13", 0.0, 3e-4)))),
    "main_drift_drag_only": ("main", dict(edits=e(f=lambda T, al: T["runs"]["f32"][al.parent]["11"].update(drag=T["runs"]["g1"][al.parent]["11"]["drag"] + 5e-4)))),
    "main_repeat_missing": ("main", dict(edits=e(g1=lambda T, al: drop(T, "g1", al.repeat)))),
    "main_nc_g1_one_phase": ("main", dict(edits=e(g1=lambda T, al: drop(T, "g1", al.nc, "12")))),
    "main_nc_f_one_phase": ("main", dict(edits=e(f=lambda T, al: [drop(T, "f32", al.nc, p) for p in ("14", "15", "16")]))),
    "main_f32_three_phases": ("main", dict(edits=e(f=lambda T, al: drop(T, "f32", al.finalist, "16")))),
    "main_f32_both_kernels_lost": ("main", dict(edits=e(f=lambda T, al: (lose(T, "f32a"), lose(T, "f32b"))))),
    "main_budget_f32b_not_run": ("main", dict(edits=e(f=lambda T, al: skip(T, ["f32b"], "BUDGET")))),
    "main_budget_and_lost": ("main", dict(edits=e(f=lambda T, al: (skip(T, ["f32b"], "BUDGET"), lose(T, "f48k13"))))),
    "main_f48_one_phase_lost_data": ("main", dict(edits=e(f=lambda T, al: set_run(T, "f48", al.finalist, "14", ok=False)))),
    "main_rbest_single_phase": ("main", dict(edits=e(f=lambda T, al: [drop(T, "f32", al.rbest, p) for p in ("14", "15", "16")]))),
    "main_manual_missing_in_f": ("main", dict(edits=e(f=lambda T, al: drop(T, "f32", al.manual)))),
    "main_xv_central_edge_above": ("main", dict(edits=e(f=_xv_edge("central", +1e-6)))),
    "main_xv_central_edge_below": ("main", dict(edits=e(f=_xv_edge("central", -1e-6)))),
    "main_xv_pessimistic_edge_above": ("main", dict(edits=e(f=_xv_edge("pessimistic", +1e-6)))),
    "main_xv_pessimistic_edge_below": ("main", dict(edits=e(f=_xv_edge("pessimistic", -1e-6)))),
    "main_g_resolved_edge": ("main", dict(noise=(1.5e-4, 3e-4), seed=5, edits=e(f=_f(df32=[S.X_STAR + 9e-4, S.X_STAR + 11e-4, S.X_STAR + 9e-4, S.X_STAR + 11e-4])))),
    "main_d_zero_drag": ("main", dict(edits=e(f=_f(dr32=0.0)))),
    "main_r3_ratio_out_of_band": ("main", dict(edits=e(f=_f(df48=0.014)))),
    "main_r3_e2_exceeded_only": ("main", dict(edits=e(f=_f(df48=0.0175, dr48=2e-3)))),
    "main_duplicate_target_point": ("main", _DUP),   # u*_1 = u*_1.5: one point under two targets

    # ---- reconciliation branches (registration §5.2, §5.11; docs/evidence/screen01_2026_10_30/crosscheck_reconciliation.md §3.3) ----
    "rs_duplicate_target_point": ("rs", _DUP),
    "fin_duplicate_target_point": ("finalist", _DUP),
    "rs_target_no_predicted_gain": ("rs", dict(by=BY_NO_GAIN_T2, bz=BZ_NO_GAIN_T2)),
    "fin_target_no_predicted_gain": ("finalist", dict(by=BY_NO_GAIN_T2, bz=BZ_NO_GAIN_T2)),
    "rs_all_targets_no_predicted_gain": ("rs", dict(by=BY_ALL_NEG, bz=BZ_ALL_NEG)),
    "fin_all_targets_no_predicted_gain": ("finalist", dict(by=BY_ALL_NEG, bz=BZ_ALL_NEG)),
    "main_all_targets_no_predicted_gain": ("main", dict(by=BY_ALL_NEG, bz=BZ_ALL_NEG)),
    "rs_argmax_tie": ("rs", dict(by=BY_TIE, bz=BZ_TIE)),
    "rs_cloud_point_already_evaluated": ("rs", dict(roles_edit=_design_at_ustar1())),
    "rs_cloud_point_as_random_state": ("rs", dict(roles_edit=_random_at_cloud())),
    "rs_target_list_absorbed": ("rs", dict(by=BY_BOWL, bz=BZ_BOWL)),
    "fin_target_list_absorbed": ("finalist", dict(by=BY_BOWL, bz=BZ_BOWL)),
    "rs_fit_undefined": ("rs", dict(edits=e(g1=_keep_only(KEEP_9_FIT_UNDEFINED)))),
    "rs_not_fit_cond": ("rs", dict(edits=e(g1=_keep_only(KEEP_9_NOT_FIT_COND)))),
    "main_repeat_implausible_g1": ("main", dict(edits=e(g1=lambda T, al: set_run(T, "g1", al.repeat, "11", downforce=T["runs"]["g1"][al.parent]["11"]["downforce"] * 1.3)))),
    "main_repeat_nonfinite_g1": ("main", dict(edits=e(g1=lambda T, al: set_run(T, "g1", al.repeat, "11", downforce=None)))),
    "main_repeat_not_ok_f32a": ("main", dict(edits=e(f=lambda T, al: set_run(T, "f32", al.repeat, "13", ok=False)))),
    "main_repeat_missing_f32a": ("main", dict(edits=e(f=lambda T, al: drop(T, "f32", al.repeat)))),
    "main_incomplete_g1_kernel_and_refine": ("main", dict(by=_weak(0.1), edits=e(g1=lambda T, al: (lose(T, "g1k12"), _lose_one_phase(8)(T, al))))),
    "main_incomplete_g1_phase_and_g2": ("main", dict(by=_weak(0.1), edits=e(g1=lambda T, al: set_run(T, "g1", al.axial[0], "12", ok=False),
                                                                      g2=lambda T, al: set_run(T, "g2", al.proposals[0], "12", ok=False)))),
    "main_incomplete_refine_degenerate_design": ("main", dict(by=_weak(0.1), roles_edit=_line_design)),
    "main_r3_one_f48_phase_paired": ("main", dict(edits=e(f=lambda T, al: (lose(T, "f48k14"), _f(df32=[0.020, 0.030, 0.020, 0.030], dr32=[1e-3, -4e-3, -4e-3, -4e-3], df48=[0.0195], dr48=[1e-3])(T, al))))),
    "main_budget_f48_not_run": ("main", dict(edits=e(f=lambda T, al: (skip(T, ["f48k13", "f48k14"], "BUDGET"), T["runs"].pop("f48"))))),
    # ---- source review (adoption.md §3.1; registration §5.11.1, .18, .19) ----
    "rs_nc_g1_not_consistent": ("rs", dict(edits=e(g1=_nc_g1(5e-3)))),
    "rs_repeat_nondeterministic": ("rs", dict(edits=e(g1=lambda T, al: set_delta(T, "g1", al.repeat, "11", 5e-4, 0.0)))),
    "fin_g1k11_lost": ("finalist", dict(edits=e(g1=lambda T, al: lose(T, "g1k11")))),
    "fin_invalid_g1_g2_not_pushed": ("finalist", dict(edits=e(g1=_nc_g1(5e-3), g2=lambda T, al: (skip(T, ["g2"], "INVALID_G1"), T["runs"].pop("g2"))))),
    "main_invalid_g1_without_F": ("main", dict(edits=e(g1=_nc_g1(5e-3), g2=lambda T, al: (skip(T, ["g2"], "INVALID_G1"), T["runs"].pop("g2")),
                                                  f=lambda T, al: (skip(T, CONF, "INVALID_G1"), no_f_groups(T))))),
    "main_budget_with_full_data": ("main", dict(edits=e(f=lambda T, al: skip(T, ["f48k14"], "BUDGET")))),
    "main_two_causes_step2": ("main", dict(edits=e(g1=lambda T, al: (_nc_g1(5e-3)(T, al), set_delta(T, "g1", al.repeat, "11", 5e-4, 0.0))))),
    "main_two_causes_step5": ("main", dict(edits=e(f=lambda T, al: (_nc_f(4e-3)(T, al), _repeat("f32", 4e-4)(T, al))))),
    "main_two_causes_step7": ("main", dict(edits=e(f=_f(df32=[0.0195, -0.0045, 0.0195, -0.0045], dr32=[-3e-3] * 4, df48=[3e-4, 3e-4])))),
    "main_axial_finalist": ("main", dict(edits=e(g1=lambda T, al: set_delta(T, "g1", al.axial[0], None, ddf=0.05, ddr=-1e-3), f=_f(df32=0.02, dr32=-2e-3, df48=0.02, dr48=-2e-3)))),
    "main_design_finalist": ("main", dict(edits=e(g1=lambda T, al: set_delta(T, "g1", al.design[4], None, ddf=0.05, ddr=-1e-3), f=_f(df32=0.02, dr32=-2e-3, df48=0.02, dr48=-2e-3)))),
    "rs_parent_lost_phase_unpaired_runs_not_listed": ("rs", dict(edits=e(g1=_parent_lost_at_12))),
}


_CACHE = {}


def branch(name) -> dict:
    key = (name, S.GRID_N)
    if key not in _CACHE:
        stage, kw = BRANCHES[name]
        _CACHE[key] = make(stage, **kw)
    return copy.deepcopy(_CACHE[key])


# ---- a whole study on disk: a tmp "repository" with freeze records, campaigns, verified tables, kernel files (analyzer pipeline tests) ----------------------------------
import argparse  # noqa: E402
import hashlib  # noqa: E402
import importlib.metadata  # noqa: E402
import json  # noqa: E402
import platform  # noqa: E402
import shutil  # noqa: E402
import types as _types  # noqa: E402

SC = S.SC
TOOLS = {"campaign_schema.py": "a" * 64, "harness.py": "b" * 64}
FINGERPRINT = "f" * 64
UNC_STATES_REL = "docs/evidence/unc01_2026_10_20/states.json"       # a second states.json in freeze 1 (the real REUSED list holds it)
PROFILE_REL = "docs/evidence/opt01_v1_2026_10_15/geom02_gate_profile_v2.json"
CIDS = {"g1": "screen01", "g2": "screen01_g2", "f32": "screen01_f", "f48": "screen01_f48"}


def sha_text(text) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def write_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, sort_keys=True, indent=1) + "\n")


def build_campaign(root, cid, T, group, kernel_root, extra=None):
    """A minimal campaign JSON under root/docs/harness, one verified table per kernel and the kernel files of the runs of one group of T (the table carries the freeze hashes)."""
    km, out_prefix = KERNEL_OF[group], f"{cid}_"
    c = {"campaign_id": cid, "out_prefix": out_prefix, "kernels": {}, **(extra or {})}
    tables = {}
    for k in sorted(set(km.values())):
        runs, forces = [], {}
        for s, by in T["runs"].get(group, {}).items():
            for ph, r in by.items():
                if km.get(ph) != k:
                    continue
                name = f"{s}__k{ph}"
                runs.append({"state": s, "name": name, "env": {}})
                d = kernel_root / f"{out_prefix}{k}" / "states" / name
                d.mkdir(parents=True, exist_ok=True)
                (d / "flow_32.summary.json").write_text(json.dumps({"name": name, "k": k}))
                (d / "flow_32.forces.csv").write_text(f"{name},{r['downforce']}\n")
                forces[name] = {"downforce_n": r["downforce"] if r["ok"] else None, "drag_n": r["drag"] if r["ok"] else None, "forces_csv_sha256": SC.sha256_path(d / "flow_32.forces.csv"),
                                "summary_sha256": SC.sha256_path(d / "flow_32.summary.json"), "solver_process_wall_seconds": 400.0, "julia_summary_wall_seconds": 390.0}
        if runs:
            c["kernels"][k] = {"case": {"case_id": "flow_32"}, "runs": runs}
            tables[k] = forces
    path = root / "docs" / "harness" / f"{cid}_campaign.json"
    write_json(path, c)
    entry = {"campaign_sha256": SC.sha256_path(path), "prerun_freeze_sha256": sha_text(cid + "prerun"), "smoke_verified_sha256": sha_text(cid + "smoke")}
    files = []
    for k, forces in tables.items():
        t = {"kind": SC.TABLE_KIND, "harness_version": SC.HARNESS_VERSION, "smoke": False, "integrity": {"pass": True, "failures": []}, "campaign_id": cid,
             "campaign_sha256": entry["campaign_sha256"], "freeze_sha256": entry["prerun_freeze_sha256"], "harness_tool_sha256": TOOLS, "state_forces_n": {k: forces}}
        tp = root.parent / "tables" / f"{cid}_{k}.json"
        write_json(tp, t)
        files.append(tp)
    return path, files, entry


class Disk:
    """T of a branch as files: freeze records 1, 2, 2.1, 3 (written as the study proceeds), campaigns, per-kernel tables, kernel files, states.json, the frozen sources (copies) and a
    stub P0 rows record, all under a tmp "repository" that replaces S.ROOT.  `stage_rs`, `stage_finalist`, `stage_main` run the analyzer steps and write their outputs once;
    `args` is the CLI namespace.  Kernels of T["lost_kernels"] get a classification record, kernels of T["not_pushed"] a budget record or the frozen rs.json / finalist.json."""
    def __init__(self, tmp_path, monkeypatch, name="main_gain", checker=None, T=None):
        self.T, self.tmp = T or branch(name), tmp_path
        self.root, self.kr = tmp_path / "repo", tmp_path / "kernels"
        self.ev = self.root / S.EV_REL
        self.ev.mkdir(parents=True)
        for attr, val in (("ROOT", self.root), ("EV", self.ev), ("CHECKER", checker or _types.SimpleNamespace(check=lambda t: S.compute(t), compare=lambda a, b, stage: [k for k in a if S.canon(a[k]) != S.canon(b.get(k))]))):
            monkeypatch.setattr(S, attr, val)
        monkeypatch.setattr(SC, "validate_campaign", lambda c: None)
        monkeypatch.setattr(P, "fingerprint", lambda: FINGERPRINT)
        fin = S.compute(self.T) if self.T["stage"] == "rs" else S.compute({**self.T, "stage": "finalist"})
        fin = {"finalist": None, "r_best": None, "g1_controls": fin["g1_controls"]} if self.T["stage"] == "rs" else fin
        self.inv = fin["g1_controls"]["invalid_at_step_2"]
        self.has_props = any(r["role"] == "proposal" for r in self.T["roles"].values())
        self.pushed = bool(fin["finalist"]) and not self.inv and self.T["stage"] == "main"
        self.finalist, self.r_best = fin["finalist"], fin["r_best"]
        self.states = self.ev / "states.json"
        write_json(self.states, {"schema": "screen01-states-v1", "parent": PARENT, "states": {n: {"role": r["role"], "order": r["order"], "u": r["u"], "spec": None if r["u"] is None else P.u_to_spec(r["u"])}
                                                                                          for n, r in self.T["roles"].items() if r["role"] != "proposal"}})
        files = {}
        for rel in S.FROZEN_FILES:
            dst = self.root / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            if rel == S.ROWS_REL:
                dst.write_text("".join(json.dumps({"name": n, "slot": r["role"], "admissible": True, "phi_fortran_sha256": sha_text(n)}) + "\n" for n, r in self.T["roles"].items() if r["role"] in ("axial", "design")))
            else:
                shutil.copy(ROOT / rel, dst)
            files[rel] = SC.sha256_path(dst)
        files[S.rel(self.states)] = SC.sha256_path(self.states)
        for rel in (UNC_STATES_REL, PROFILE_REL, S.POLICY_REL):
            files[rel] = SC.sha256_path(ROOT / rel) if (ROOT / rel).exists() else sha_text(rel)
        try:
            from screen01_freeze import REUSED
            assert UNC_STATES_REL in REUSED, "the real REUSED list no longer binds the UNC-01 states.json"
        except ImportError:
            pass
        self.write("freeze1", {"kind": "freeze1", "file_sha256": files, "environment": {"python": platform.python_version(), **{m: importlib.metadata.version(m) for m in ("numpy", "scipy", "scikit-image")}},
                               "harness_tool_sha256": TOOLS, "p0": {"fingerprint": FINGERPRINT}})
        self.camp, self.tabs, self.entry = {}, {}, {}
        extra32 = {"states": {PARENT: {"kind": "parent", **self.ident("p")}, **({self.finalist: {"kind": "candidate", "direction": "d1", "step_mm": 1.0, "sign": 1, **self.ident("f")}} if self.finalist else {})},
                   "directions": {"d1": {"path": "d1.raw", "sha256_fortran_raw": "a" * 64}}, "domain": {"flow_origin_m": [0, 0, 0], "physical_box_max_m": [1, 1, 1]}, "baseline": {"path": "b.raw", "sha256_fortran_raw": "b" * 64}}
        for g in ("g1", "g2", "f32", "f48"):
            if g in ("g2",) and not (self.has_props and not self.inv) or g in ("f32", "f48") and not self.pushed:
                continue
            self.camp[g], self.tabs[g], self.entry[g] = build_campaign(self.root, CIDS[g], self.T, g, self.kr, extra32 if g == "f32" else None)
        self.write("freeze2", {"kind": "freeze2", "file_sha256": {S.rel(self.ev / "freeze1.json"): SC.sha256_path(self.ev / "freeze1.json"), S.rel(self.camp["g1"]): SC.sha256_path(self.camp["g1"])},
                               "campaign": self.entry["g1"]})
        self.args = argparse.Namespace(states=self.states, g1=None, g2=None, f32=None, f48=None, rs=self.ev / "rs.json", finalist=self.ev / "finalist.json", kernel_root=self.kr, lost=[],
                                       lost_declarations={}, not_pushed={}, not_pushed_records={}, workers=4, out=None)

    @staticmethod
    def ident(tag):
        return {k: (sha_text(f"{tag}{k}") if k.endswith("sha256") else 0.1) for k in SC.STATE_IDENTITY_KEYS}

    def write(self, name, rec):
        write_json(self.ev / f"{name}.json", rec)

    def freeze(self, name):
        return json.loads((self.ev / f"{name}.json").read_text())

    def group(self, g):
        return [self.camp[g], *self.tabs[g]] if g in self.camp else None

    def declare(self, stage):
        """lost / not-pushed declarations of the kernels of the stage, each with its record."""
        ks = {k for g in S.STAGE_GROUPS[stage] for k in S.KERNELS[g]}
        lost = {}
        for k in sorted(set(self.T["lost_kernels"]) & ks):
            r = self.ev.parent / f"lost_{k}.json"
            write_json(r, {"kind": "screen01_infra_classification", "kernel": k, "attempt": 2, "classification": "NOT_INFRASTRUCTURE", "signature": None, "evidence_sha256": {},
                           "verify_failed": False, "table_sha256": SC.sha256_path(self.root / S.INFRA_REL)})
            lost.update(S.parse_lost([f"{k}=NOT_INFRASTRUCTURE:{r}"]))
        np_ = {}
        for k, reason in self.T.get("not_pushed", {}).items():
            if k not in ks:
                continue
            rec = None
            if reason == "BUDGET":
                rec = self.ev.parent / f"budget_{k}.json"
                write_json(rec, {"kind": "screen01_budget_decision", "decision": "stop", "pending_estimate_s": {k: [5000]}, "T_s": 90000, "cap_s": 86400, "rule": "registration §4.3"})
            np_[k] = {"reason": reason, "record": rec}
        self.args.lost, self.args.lost_declarations, self.args.not_pushed = sorted(lost), lost, np_

    def oracle(self, T, workers):
        rows = {}

        def ask(u):
            n = sname(u)
            rows[n] = {"name": n, "admissible": bool(default_oracle(u)), "gate_values": {"min_feature_width": 1.0}, "phi_fortran_sha256": sha_text(n)}
            return rows[n]["admissible"]
        return ask, rows

    def stage_rs(self, oracle=None):
        self.declare("rs")
        self.args.g1 = self.group("g1")
        rec = S.run_rs(self.args, oracle or self.oracle)
        S.write_once(self.args.rs, S.dumps(rec))
        inv = rec["comparable"]["g1_controls"]["invalid_at_step_2"]
        extra = {"g2": self.entry["g2"]} if "g2" in self.entry else {"g2": "none (invalid_at_step_2)" if inv else "none (no proposal)"}
        self.write("freeze2_1", {"kind": "freeze2_1", "file_sha256": {S.rel(self.ev / "freeze2.json"): SC.sha256_path(self.ev / "freeze2.json"), S.rel(self.args.rs): SC.sha256_path(self.args.rs),
                                                                       **({S.rel(self.camp["g2"]): SC.sha256_path(self.camp["g2"])} if "g2" in self.camp else {})},
                                 "rs_json_sha256": SC.sha256_path(self.args.rs), **extra})
        return rec

    def stage_finalist(self):
        self.declare("finalist")
        self.args.g2 = self.group("g2")
        rec = S.run_finalist(self.args)
        S.write_once(self.args.finalist, S.dumps(rec))
        f3 = {"kind": "freeze3", "file_sha256": {S.rel(self.ev / "freeze2_1.json"): SC.sha256_path(self.ev / "freeze2_1.json")}, "finalist_json_sha256": SC.sha256_path(self.args.finalist),
              "finalist": rec["finalist"], "r_best": rec["r_best"], "pushed": rec["pushed"]}
        if rec["pushed"] and "f32" in self.entry:
            f3["campaigns"] = {CIDS[g]: self.entry[g] for g in ("f32", "f48")}
            f3["file_sha256"].update({S.rel(self.camp[g]): SC.sha256_path(self.camp[g]) for g in ("f32", "f48")})
        self.write("freeze3", f3)
        return rec

    def stage_main(self, out=None):
        self.declare("main")
        self.args.g2 = self.group("g2")
        self.args.f32, self.args.f48 = self.group("f32"), self.group("f48")
        self.args.out = out or self.ev / "analysis.json"
        return S.run_main(self.args)

    def run_all(self):
        self.stage_rs()
        self.stage_finalist()
        return self.stage_main()
