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


def lose(T, kernel):
    """The kernel is declared lost: its runs are not in the tables."""
    for g, m in KERNEL_OF.items():
        for ph, k in m.items():
            if k == kernel and g in T["runs"]:
                for s in T["runs"][g]:
                    T["runs"][g][s].pop(ph, None)
    T["lost_kernels"] = sorted({*T["lost_kernels"], kernel})


_GATE = {}


def default_oracle(u) -> bool:
    return sum(sname(u).encode()) % 7 < 4


def make(stage="main", *, by=BY, bz=BZ, noise=(0.0, 0.0), n_random=19, manual=True, oracle=None, edits=None, seed=0, n_grid=None) -> dict:
    n_grid, edits, oracle = n_grid or S.GRID_N, edits or {}, oracle or default_oracle
    roles = base_roles(n_random, manual)
    T = {"schema": "screen01-T-v1", "stage": "rs", "roles": roles, "runs": {"g1": {}}, "lost_kernels": [], "gating": []}
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
    "main_incomplete_f_not_run": ("main", dict(edits=e(f=lambda T, al: (T["runs"].pop("f32"), T["runs"].pop("f48"))))),
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
    "main_budget_f32b_not_run": ("main", dict(edits=e(f=lambda T, al: [drop(T, "f32", s, p) for s in list(T["runs"]["f32"]) for p in ("15", "16")]))),
    "main_budget_and_lost": ("main", dict(edits=e(f=lambda T, al: ([drop(T, "f32", s, p) for s in list(T["runs"]["f32"]) for p in ("15", "16")], lose(T, "f48k13"))))),
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
    "main_duplicate_target_point": ("main", dict(by=_weak(0.1), edits=e(g1=_best_design(0.012), g2=_g2_df(0.001)))),   # u*_1 = u*_1.5: one point under two targets
}


_CACHE = {}


def branch(name) -> dict:
    key = (name, S.GRID_N)
    if key not in _CACHE:
        stage, kw = BRANCHES[name]
        _CACHE[key] = make(stage, **kw)
    return copy.deepcopy(_CACHE[key])
