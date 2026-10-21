"""T2-0d (#57): stage module, runner lists and the registered analyzer on synthetic fixtures (registration docs/t20d_registration_2026_10_21.md)."""
from __future__ import annotations

import collections
import gzip
import json
import math
import shutil
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import analyze_t20d as A  # noqa: E402
import build_t20d_kernel as K  # noqa: E402
import t20_foam  # noqa: E402
import t20d_case as S  # noqa: E402

TC = 0.2234 / 30.0


# ---- runner lists and ids ------------------------------------------------------------------------

def runner_ns():
    ns = {"__name__": "runner_under_test"}
    text = (ROOT / "infra/kaggle/kernel_t20d_cpu/runner.py").read_text().replace("PIN_PINS", "{}").replace("PIN_ONLY", "None")
    exec(compile(text, "runner.py", "exec"), ns)
    return ns


def test_registered_counts_match_registration_section_5():
    reg = K.registered()
    kinds = collections.Counter(k for m in reg for _, ks in reg[m] for k in ks)
    assert kinds == {"U": 51, "Udt2": 8, "Udt05": 2, "S1": 9, "US1": 2}
    assert sum(len(reg[m]) for m in reg) == 63 and sum(1 for m in reg for _, ks in reg[m] if not ks) == 12
    assert {m: len(reg[m]) for m in reg} == {"xp1": 7, "xp2": 8, "xo1": 6, "xo2": 12, "f1": 19, "f2": 11}
    for m in reg:   # US1 always rides on an S1 of the same geometry; every stage-2 kind is known to the stage module
        for _, ks in reg[m]:
            assert "US1" not in ks or "S1" in ks
            assert set(ks) <= set(S.KINDS)


def test_runner_and_builder_ids_agree_and_sets_close():
    ns = runner_ns()
    for m, items in K.registered().items():
        for c, _ in items:
            assert ns["case_id"](*c) == K._case_id(*c)
    assert len(K.set_closure("xp1", ["sa-wf_h0.134_xfine30_morph-da+1"])) == 7
    assert K.set_closure("xo1", ["sa-wf_h0.09_xfine30_da0"]) == ["sa-wf_h0.09_xfine30_da0"]
    with pytest.raises(ValueError):
        K.set_closure("xo1", ["sa-wf_h0.134_xfine30_da0"])


def test_analyzer_keys_exist_in_the_registered_lists():
    keys = set(A.expected_keys())
    used = [A.g2_key(L, h, a) for L in ("fine30", "xfine30") for h in A.HEIGHTS for a in (0.0,)]
    used += [A.g2_key(L, h, a) for L in ("fine30", "xfine30") for h in A.H3 for a in (-1.0, 1.0)]
    used += [A.scan_key(L, a) for L in ("fine30", "xfine30") for a in A.A7] + [A.scan_key(L, a, "B2") for L in ("fine30", "xfine30") for a in (-1.0, -0.25, 0.25, 1.0)]
    used += [A.shape_key(m, a) for m in ("camber", "flap") for a in (-0.25, 0.25)]
    used += [A.k_u(k, g, x) for k, g in A.Q1_TARGETS.values() for x in ("U", "Udt2", "S0", "S1")]
    used += [A.k_u(k, g, x) for k, g in A.Q1_CONTROLS.values() for x in ("U", "S0", "S1")]
    used += [A.k_u(*A.Q1_TARGETS[n], x) for n in A.US1_AT for x in ("US1", "Udt05")]
    assert set(used) <= keys, sorted(set(used) - keys)


# ---- stage module ------------------------------------------------------------------------------------

def fake_s0(tmp: Path) -> Path:
    s0 = tmp / "s0"
    files = {f"0/{k}": v for k, v in t20_foam.fields({"foam": "SpalartAllmaras", "wall": "wf"}, 30.0, 1.457e-5, 0.003, 0.01).items()}
    files |= t20_foam.system_and_constant({"foam": "SpalartAllmaras", "relax": 0.9}, {}, dict(u=30.0, nu=1.457e-5, chord=0.2234, z=0.002, iters=5000))
    files |= {"constant/polyMesh/points": "pts", "constant/polyMesh/faces": "faces", "5000/U": "U5000", "5000/p": "p5000", "5000/nuTilda": "nt", "5000/nut": "nut",
              "5000/phi": "phi", "5000/yPlus": "yp", "5000/uniform/time": "time", "postProcessing/forceCoeffs/0/coefficient.dat": "#", "mesh.msh": "msh"}
    for rel, text in files.items():
        (s0 / rel).parent.mkdir(parents=True, exist_ok=True)
        (s0 / rel).write_text(text)
    (s0 / "case_manifest.json").write_text(json.dumps({"h_over_c": 0.134}))
    return s0


def test_stage2_urans_copy_and_dictionaries(tmp_path):
    s0 = fake_s0(tmp_path)
    rec = S.stage2_case(s0, tmp_path / "u", "U")
    u = tmp_path / "u"
    assert rec["source_time"] == "5000" and rec["dt_s"] == 1e-5 and rec["end_time_s"] == 0.1192
    assert sorted(p.name for p in (u / "0").iterdir()) == sorted(S.FIELDS)
    assert (u / "0/U").read_text() == "U5000" and (u / "constant/polyMesh/points").read_text() == "pts"
    assert not (u / "postProcessing").exists() and not (u / "0/uniform").exists() and not (u / "5000").exists() and not (u / "mesh.msh").exists()
    cd, sch, sol = ((u / f"system/{n}").read_text() for n in ("controlDict", "fvSchemes", "fvSolution"))
    assert "application pimpleFoam;" in cd and "deltaT 1e-05;" in cd and "endTime 0.1192;" in cd and "writeInterval 11920;" in cd and "forceCoeffs" in cd
    assert "adjustTimeStep no;" in cd and "startTime 0;" in cd
    assert "default backward;" in sch and "bounded" not in sch and "div(phi,U) Gauss linearUpwind grad(U);" in sch
    assert "nOuterCorrectors 2;" in sol and "pFinal" in sol and '".*" 1;' in sol and "SIMPLE" not in sol
    assert json.loads((u / "case_manifest.json").read_text())["stage2"]["kind"] == "U"
    assert S.stage2_case(s0, tmp_path / "u05", "Udt05")["end_time_s"] == 0.0819
    assert "writeInterval 4096;" not in (tmp_path / "u05/system/controlDict").read_text()


def test_stage2_s1_and_us1(tmp_path):
    s0 = fake_s0(tmp_path)
    S.stage2_case(s0, tmp_path / "s1", "S1")
    s1 = tmp_path / "s1"
    assert (s1 / "5000/U").read_text() == "U5000" and not (s1 / "5000/uniform").exists() and not (s1 / "5000/yPlus").exists()
    cd, sol = (s1 / "system/controlDict").read_text(), (s1 / "system/fvSolution").read_text()
    assert "startFrom latestTime;" in cd and "endTime 15000;" in cd and "writeInterval 10000;" in cd   # 10000 S1 iterations from 5000
    assert "consistent no;" in sol and "fields { p 0.3; }" in sol and '"(U|nuTilda)" 0.7;' in sol and "0.9" not in sol
    (s1 / "15000").mkdir()
    for f in S.FIELDS:
        (s1 / "15000" / f).write_text(f"{f}15000")
    rec = S.stage2_case(s1, tmp_path / "us1", "US1")
    assert rec["source_time"] == "15000" and (tmp_path / "us1/0/U").read_text() == "U15000"
    assert "pimpleFoam" in (tmp_path / "us1/system/controlDict").read_text()
    with pytest.raises(ValueError):
        S.stage2_case(s0, tmp_path / "bad", "LM")


# ---- statistics -----------------------------------------------------------------------------------------

def series(fn, dt=1e-5, end=S.END_TIME_S["U"]):
    t = np.arange(1, round(end / dt) + 1) * dt
    return t, fn(t)


def stats(fn, dt=1e-5, end=S.END_TIME_S["U"]):
    t, cl = series(fn, dt, end)
    return A.urans_stats(t, cl, dt, S.T_TR_S, end)


def test_settled_and_settling_runs():
    rng = np.random.default_rng(1)
    s = stats(lambda t: 1.3 + 1e-7 * rng.standard_normal(len(t)))
    assert s["class"] == "VALID_SETTLED" and abs(s["m"] - 1.3) < 1e-6
    s = stats(lambda t: 1.3 + 0.03 * np.exp(-(t - S.T_TR_S) / (0.6 * TC)) * np.sin(2 * np.pi * 1500 * t))   # decays into a steady state: settled on H2
    assert s["class"] == "VALID_SETTLED"


def test_periodic_run_mean_frequency_and_noise():
    s = stats(lambda t: 1.3 + 0.04 * np.sin(2 * np.pi * 1234.5 * t + 0.3))
    assert s["class"] == "VALID_PERIODIC" and not s["low_freq"]
    assert abs(s["f"] / 1234.5 - 1) < 0.01 and abs(s["m"] - 1.3) <= s["se"] + 1e-9
    s4 = stats(lambda t: 1.3 + 0.02 * np.sin(2 * np.pi * (4.3 / 0.0745) * t))
    assert s4["class"] == "VALID_PERIODIC" and s4["low_freq"] and abs(s4["m"] - 1.3) <= s4["se"]
    for k in (1.5, 2.0, 2.5, 2.9):   # below 3 cycles: never valid (TOO_FEW_CYCLES, or NONSTATIONARY when the partial cycle reads as drift)
        cls = stats(lambda t, k=k: 1.3 + 0.02 * np.sin(2 * np.pi * (k / 0.0745) * (t - S.T_TR_S)))["class"]
        assert cls in ("TOO_FEW_CYCLES", "NONSTATIONARY")
    assert stats(lambda t: 1.3 + 0.02 * np.sin(2 * np.pi * (2.5 / 0.0745) * (t - S.T_TR_S)))["class"] == "TOO_FEW_CYCLES"


def test_drift_decay_and_growth_are_nonstationary():
    w = lambda t: (t - S.T_TR_S) / 0.0745
    assert stats(lambda t: 1.3 * (1 + 3e-3 * w(t)) + 0.02 * np.sin(2 * np.pi * 1500 * t))["class"] == "NONSTATIONARY"          # drift 3e-3 with oscillation
    assert stats(lambda t: 1.3 + 0.03 * np.exp(-w(t) * 1.2) * np.sin(2 * np.pi * 1500 * t))["class"] == "NONSTATIONARY"         # decaying amplitude
    assert stats(lambda t: 1.3 + 5e-4 * 1.3 * np.exp(4 * (w(t) - 1)) * np.sin(2 * np.pi * 1500 * t))["class"] == "NONSTATIONARY"  # growing from small
    assert stats(lambda t: 1.3 * (1 + 3e-3 * w(t)))["class"] == "NONSTATIONARY"                                                  # pure drift, small r


def test_steady_stats():
    n = np.arange(5000)
    conv = A.steady_stats(1.3 + 1e-4 * (-1) ** n)
    assert conv["class"] == "CONVERGED" and abs(conv["m"] - 1.3) < 1e-6
    assert A.steady_stats(1.3 + 0.03 * np.sin(2 * np.pi * n / 14))["class"] == "NOT_CONVERGED"


def test_gt_rule():
    a = {"class": "VALID_PERIODIC", "m": 1.30, "se": 1e-4, "r": 0.03, "f": 1500.0, "T_w": 0.0745}
    assert A.gt_rule(a, {**a, "m": 1.302})["pass"]
    assert not A.gt_rule(a, {**a, "m": 1.31})["pass"]
    assert not A.gt_rule(a, {**a, "r": 0.02})["pass"]
    assert not A.gt_rule(a, {**a, "f": 1800.0})["pass"]
    assert A.gt_rule(a, {**a, "f": 1600.0})["pass"]   # within 10 %
    assert not A.gt_rule(a, {**a, "class": "VALID_SETTLED"})["pass"]
    assert A.gt_rule(a, {**a, "m": 1.30 + 0.015, "se": 0.01})["mean_ok"] is False   # the 1e-2 cap (0.013) beats 3 SE


# ---- end-to-end on a synthetic output tree ---------------------------------------------------------------

EXP = {float(h): p["Cl"] for h, p in json.loads((ROOT / "data/t20/zerihan_zhang_cl_genua2009_fig6.json").read_text())["points"].items()}
SLOPE = {0.224: 0.12, 0.134: 0.08, 0.09: 0.06}


def model_cl(c, level_shift=0.0):
    method, h, mesh, mode, amp, variant = c
    base = EXP[h] * (1 + (0.003 if mesh == "fine30" else 0.0) + level_shift)
    if mode == "incidence":
        return base + SLOPE.get(h, 0.12) * amp
    return base + 0.05 * amp


def write_run(d: Path, rec: dict, t=None, cl=None):
    d.mkdir(parents=True, exist_ok=True)
    (d / "case_result.json").write_text(json.dumps(rec))
    if cl is not None:
        with gzip.open(d / "coefficient.dat.gz", "wt") as fh:
            fh.write("# Time Cd Cl\n")
            np.savetxt(fh, np.column_stack([t, np.full_like(t, 0.05), cl]), fmt="%.10g")


PERIODIC = {("xo1", A.gid(0.09, "xfine30", a)) for a in (-1.0, 0.0, 1.0)}


def write_one(out: Path, k: str, c: tuple, kind: str, tw: dict, wall_s=7200.0, s0_wall=1200.0):
    g = K._case_id(*c)
    rid = f"{g}__{kind}"
    if (out / "cases" / rid).exists():
        shutil.rmtree(out / "cases" / rid)
    if tw.get("drop"):
        return
    m = model_cl(c) + tw.get("m_shift", 0.0)
    rec = {"id": rid, "geometry": g, "kind": kind, "status": tw.get("status", "COMPLETED"), "mesh_msh_sha256": f"{k}-{g}", "mesh_cells_3d": 50000,
           "pre_solver_wall_s": 60.0, "s0_wall_s": s0_wall, "solver": {"iterations": 10, "nan_in_log": False}, "source_run": f"{g}__S0"}
    if kind == "S0":
        rec["stages"] = [{"stage": "simpleFoam", "wall_s": s0_wall}]
        if c[0] == "morph":
            rec["morph"] = {"base_mesh_msh_sha256": f"base-{k}"}
        n = np.arange(5000)
        write_run(out / "cases" / rid, rec, n + 1.0, m + 1e-5 * (-1) ** n)
    elif kind == "S1":
        rec["stages"] = [{"stage": "simpleFoam", "wall_s": 2400.0}]
        n = np.arange(10000)
        write_run(out / "cases" / rid, rec, n + 5001.0, m + 1e-6 * (-1) ** n)
    else:
        dt, end = S.DT[kind], S.END_TIME_S[kind]
        rec["stages"] = [{"stage": "pimpleFoam", "wall_s": wall_s}]
        rec["stage2"] = {"kind": kind, "end_time_s": end}
        t = np.arange(1, round(end / dt) + 1) * dt
        if tw.get("cl_fn") is not None:
            cl = tw["cl_fn"](t, m)
        elif (k, g) in PERIODIC:
            cl = m + 0.03 * m * np.sin(2 * np.pi * 1500.0 * t)
        else:
            cl = m + 1e-7 * np.sin(2 * np.pi * 37.0 * t)
        write_run(out / "cases" / rid, rec, t, cl)


def runs():
    reg = K.registered()
    return [(k, c, kind) for k in A.KERNELS for c, kinds in reg[k] for kind in ("S0", *kinds)]


def build_tree(root: Path, wall_s=7200.0, s0_wall=1200.0):
    """All registered runs, COMPLETED, Cl from model_cl; the xfine30 h/c 0.09 runs periodic (St_c ~ 11), the rest settled."""
    for k, c, kind in runs():
        write_one(root / k / "t20d", k, c, kind, {}, wall_s, s0_wall)
    return {k: root / k / "t20d" for k in A.KERNELS}


@pytest.fixture(scope="module")
def tree(tmp_path_factory):
    root = tmp_path_factory.mktemp("t20d_base")
    return root, build_tree(root)


def analyse(dirs, out: Path) -> dict:
    A.main([*sum(([f"--{k}", str(dirs[k])] for k in A.KERNELS), []), "--out", str(out)])
    return json.loads((out / "verdict.json").read_text())


def tweaked(tree, dst: Path, tweak) -> dict:
    """A copy of the nominal tree with the runs `tweak(kernel, run id, geometry, kind)` returns overrides for rewritten ({'status', 'cl_fn', 'drop', 'm_shift'})."""
    shutil.copytree(tree[0], dst)
    for k, c, kind in runs():
        tw = tweak(k, f"{K._case_id(*c)}__{kind}", c, kind)
        if tw:
            write_one(dst / k / "t20d", k, c, kind, tw)
    return {k: dst / k / "t20d" for k in A.KERNELS}


def variant(tree, tmp_path, tweak):
    return analyse(tweaked(tree, tmp_path / "t", tweak), tmp_path / "a")


def test_qualified_unaffordable_on_the_nominal_tree(tree, tmp_path):
    _, dirs = tree
    v = analyse(dirs, tmp_path / "a")
    assert v["DATA"]["outcome"] == "PASS" and v["DIFF"]["outcome"] == "PASS", (v["DATA"]["outcome"], v["DIFF"]["outcome"])
    assert v["cost"]["label"] == "NOT_AFFORDABLE" and v["verdict"] == A.V_QU
    q1 = v["labels"]["Q1"]
    assert q1["per_condition"]["x09 0"]["label"] == "UNSTEADY_IN_URANS" and q1["per_condition"]["x134 0"]["label"] == "STEADY_SOLVER_ARTEFACT"
    assert q1["per_condition"]["x224 0"]["label"] == "CONTROL_OK" and q1["Q1_FORM_09"] == "URANS_REQUIRED" and q1["Q1_FORM_134"] == "STEADY_RELAXED_SUFFICES"
    assert v["labels"]["G2_ACTION"]["label"] == "G2_INDEPENDENT_DATA_NEXT"
    with pytest.raises(SystemExit):   # written once
        analyse(dirs, tmp_path / "a")


def test_affordable_gives_qualified(tree, tmp_path):
    shutil.copytree(tree[0], tmp_path / "t")
    for p in (tmp_path / "t").glob("*/t20d/cases/*/case_result.json"):   # cheaper runs: records only, values unchanged
        r = json.loads(p.read_text())
        r["s0_wall_s"] = 200.0
        r["stages"] = [{**s, "wall_s": 300.0} for s in r["stages"]]
        p.write_text(json.dumps(r))
    v = analyse({k: tmp_path / "t" / k / "t20d" for k in A.KERNELS}, tmp_path / "a")
    assert v["cost"]["label"] == "AFFORDABLE" and v["verdict"] == A.V_Q


def test_nonstationary_g2_input_is_fail_input_not_a_data_failure(tree, tmp_path):
    drift = lambda t, m: m * (1 + 0.01 * t / t[-1])
    v = variant(tree, tmp_path, lambda k, rid, c, kind: {"cl_fn": drift} if (k, rid) == A.g2_key("xfine30", 0.313) else None)
    assert v["DATA"]["G2u"]["xfine30"]["outcome"] == "FAIL_INPUT" and v["DATA"]["outcome"] == "FAIL_INPUT"
    assert v["verdict"] == A.V_NO and v["labels"]["G2_ACTION"]["label"] == "UNDECIDED"


def test_timestep_failure_at_009(tree, tmp_path):
    v = variant(tree, tmp_path, lambda k, rid, c, kind: {"m_shift": 0.02} if (k, rid) == A.k_u("xo1", A.gid(0.09, "xfine30"), "Udt2") else None)
    assert v["DATA"]["GTd"]["xfine30"]["x09 0"]["outcome"] == "FAIL_TIMESTEP" and v["DATA"]["outcome"] == "FAIL_TIMESTEP"
    assert v["DIFF"]["outcome"] == "PASS" and v["verdict"] == A.V_NO
    assert v["labels"]["Q1"]["per_condition"]["x09 0"]["label"] == "INDETERMINATE"


def test_lost_diff_input_is_incomplete(tree, tmp_path):
    v = variant(tree, tmp_path, lambda k, rid, c, kind: {"drop": True} if (k, rid) == A.shape_key("flap", 0.25) else None)
    assert v["DIFF"]["GSu"]["outcome"] == "UNDETERMINED" and v["DATA"]["outcome"] == "PASS" and v["verdict"] == A.V_INC


def test_mechanical_input_is_a_pipeline_defect(tree, tmp_path):
    v = variant(tree, tmp_path, lambda k, rid, c, kind: {"status": "TOPOLOGY_CHANGED"} if (k, rid) == A.scan_key("xfine30", 0.5) else None)
    assert v["DIFF"]["G6u"]["outcome"] == "MECHANICAL" and v["verdict"] == A.V_DEF


def test_base_realisation_and_peak_value_failures(tree, tmp_path):
    b2 = lambda k, rid, c, kind: {"m_shift": 0.4 * SLOPE[0.134] * c[4]} if k == "xp2" and c[5] == "B2" else None
    v = variant(tree, tmp_path / "b", b2)
    assert v["DIFF"]["G8u"]["outcome"] == "FAIL_VALUE" and v["DIFF"]["outcome"] == "FAIL_VALUE" and v["verdict"] == A.V_NO
    peak = lambda k, rid, c, kind: {"m_shift": 0.05} if c[1] == 0.09 and c[4] == 0 and c[2] == "fine30" else None
    v = variant(tree, tmp_path / "p", peak)
    assert v["DATA"]["G2u"]["fine30"]["outcome"] == "FAIL_VALUE" and v["DATA"]["G2u"]["fine30"]["detail"]["tests"]["peak"] == "fail"
    assert v["labels"]["G2_ACTION"]["label"] == "G2_ACTION_STANDS"


def test_start_dependence_and_timeout_classes(tree, tmp_path):
    def tw(k, rid, c, kind):
        if (k, rid) == A.k_u(*A.Q1_TARGETS["x134 0"], "US1"):
            return {"m_shift": 0.02}
        if (k, rid) == A.k_u("xo2", A.gid(0.448, "xfine30")):
            return {"status": "pimpleFoam_TIMEOUT"}
    v = variant(tree, tmp_path, tw)
    assert v["labels"]["Q1"]["per_condition"]["x134 0"]["label"] == "START_DEPENDENT" and v["labels"]["Q1"]["Q1_FORM_134"] == "INDETERMINATE"
    assert v["DATA"]["G2u"]["xfine30"]["outcome"] == "UNDETERMINED" and v["verdict"] == A.V_INC


def test_completeness_prints_no_value(tree, capsys):
    _, dirs = tree
    A.main([*sum(([f"--{k}", str(dirs[k])] for k in A.KERNELS), []), "--completeness"])
    out = json.loads(capsys.readouterr().out)
    assert set(out) == {"counts", "lost"} and out["lost"] == [] and sum(out["counts"].values()) == len(A.expected_keys())


def test_resubmission_replaces_whole_sets_only(tree, tmp_path):
    first = tweaked(tree, tmp_path / "r1", lambda k, rid, c, kind: {"status": "DEADLINE_LIMITED"} if (k, rid) == A.scan_key("xfine30", 1.0) else None)
    second = tweaked(tree, tmp_path / "r2", lambda k, rid, c, kind: {"m_shift": 0.001} if k == "xp1" else None)
    R, prov = A.load({k: [first[k]] + ([second[k]] if k == "xp1" else []) for k in A.KERNELS})
    scan = [A.scan_key("xfine30", a)[1] for a in A.A7]
    assert all(prov[f"xp1:{j}"] == str(second["xp1"]) for j in scan)
    assert prov[f"xp1:{A.gid(0.134, 'xfine30')}__S0"] == str(second["xp1"])
    assert all(v == str(first[k]) for kk, v in prov.items() for k in [kk.split(":")[0]] if k != "xp1")
