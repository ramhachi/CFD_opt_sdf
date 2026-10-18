"""T2-0b (#57): builder, case lists, plateau statistic, adjoint projection known answers, rotation convention, and every verdict branch of the
registered analyzer on synthetic outputs (no OpenFOAM, no network)."""
import json
import math
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest

from scripts import analyze_t20b as A
from scripts import build_t20b_kernel as B
from scripts import t20_case, t20_foam, t20b_adjoint as adj

REAL = Path(B.ROOT)
TEMPLATE = REAL / "infra/kaggle/kernel_t20b_cpu/runner.py"


def runner_ns():
    src = TEMPLATE.read_text()
    ns = {"__name__": "t20b_runner_test"}
    exec(compile(src.replace("PINS = PIN_PINS", "PINS = {}").split('\nif __name__ == "__main__":')[0], "runner", "exec"), ns)
    return ns


# ---- kernel template and builder ---------------------------------------------------

def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t", *args], check=True, capture_output=True, text=True).stdout.strip()


def test_builder_renders_each_mode_with_pins(tmp_path, monkeypatch):
    ns = runner_ns()
    files = (*B.FILES, *ns["LOCKS"].values(), "infra/kaggle/kernel_t20b_cpu/runner.py", "infra/kaggle/kernel_t20b_cpu/kernel-metadata.json")
    for rel in files:
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REAL / rel, tmp_path / rel)
    git(tmp_path, "init", "-q")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-qm", "x")
    for mod in (B, B.A):
        monkeypatch.setattr(mod, "ROOT", tmp_path)
    monkeypatch.setattr(B, "TEMPLATE_DIR", tmp_path / "infra/kaggle/kernel_t20b_cpu")
    commit = git(tmp_path, "rev-parse", "HEAD")
    for mode, slug in B.MODES.items():
        out = tmp_path / f"out_{mode}"
        B.main(["--source-commit", commit, "--mode", mode, "--out", str(out)])
        text = (out / "runner.py").read_text()
        assert f"MODE = {mode!r}" in text and f"SOURCE_COMMIT = {commit!r}" in text and "scripts/t20b_adjoint.py" in text
        meta = json.loads((out / "kernel-metadata.json").read_text())
        assert meta["title"] == slug == meta["id"].split("/")[1] and not meta["enable_gpu"] and meta["is_private"]
    (tmp_path / "scripts/t20b_adjoint.py").write_text("# edited after the commit\n")
    with pytest.raises(ValueError, match="committed source differs"):
        B.render(commit, "wf")


def test_registered_case_lists():
    ns = runner_ns()
    wf, lm = ns["WF_CASES"], ns["LM_CASES"]
    assert len(wf) == 60 == len(set(wf))
    sa = [c for c in wf if c[0] == "sa-wf"]
    assert len(sa) == 47 and len([c for c in wf if c[0] == "sst-wf"]) == 13 and {c[2] for c in wf if c[0] == "sst-wf"} == {"med30"}
    for h in A.SCAN:
        assert {c[3] for c in sa if c[1] == h and c[2] == "med30"} == set(A.SCAN_DA)
    assert wf[0][2] == "fine30" and wf[-1][2] == "coa30"   # expected cost order
    assert lm == [("sst-lm", 0.224, "wr2", 0.0), ("sst-lm", 0.134, "wr2", 0.0), ("sst-lm", 0.09, "wr2", 0.0), ("sa-wf", 0.224, "med30", 0.0)]
    assert ns["ADJOINT"]["case"] == lm[-1] and ns["LM_ITERS"] == 14000 and ns["CONT_ITERS"] == 15000
    ids = [A.cid(*c) for c in wf]
    assert len(set(ids)) == 60 and "sa-wf_h0.224_med30_da+0.25" in ids and "sa-wf_h0.224_med30_da0" in ids
    geoms = ns["unique_geometries"](wf + lm)
    assert len(geoms) == 50   # sst-wf and the kernel-L sa-wf case reuse sa-wf geometries; wr2 adds 3


def test_cl_plateau_ignores_period_two_alternation_and_counts_settling():
    ns = runner_ns()
    it = np.arange(1, 5001)
    cl = 1.3 + 0.2 * np.exp(-it / 30.0) + 2e-4 * (-1) ** it
    cd = 0.03 + 7e-5 * (-1) ** it          # raw Cd rel. std ~0.23 %: not a validity input
    rows = [{"Time": float(t), "Cl": float(a), "Cd": float(b)} for t, a, b in zip(it, cl, cd)]
    s = ns["force_summary"](rows)
    assert s["cl_plateau"] and s["tail_rows"] == 1000 and 100 < s["iterations_to_plateau"] < 250
    drift = [{**r, "Cl": r["Cl"] * (1 + 0.05 * r["Time"] / 5000)} for r in rows]
    assert not ns["force_summary"](drift)["cl_plateau"]
    lm = [{"Time": float(t), "Cl": 1.38 + 0.13 * math.sin(2 * math.pi * t / 280), "Cd": 0.06} for t in range(1, 12001)]
    f = ns["force_summary"](lm)
    assert f["Cl"]["half_window_rel_diff"] < 0.01 and f["Cl"]["tail_rel_std"] > 0.05


def test_smoke_filter_drops_force_lines():
    ns = runner_ns()
    ns["MODE"] = "smoke"
    kept = ns["_keep_text"]("Time = 5\nCl    : 1.2\n    Cd = 0.03\nsum of forces:\n        Total    : (1 2 3)\n        Pressure : (1 2 3)\n        Viscous  : (1 2 3)\nSolving for Ux, Initial residual = 1e-3\n")
    assert kept == "Time = 5\nSolving for Ux, Initial residual = 1e-3"


def test_yplus_parser():
    ns = runner_ns()
    y = ns["parse_yplus"]("    patch airfoil y+ : min = 0.5, max = 61.2, average = 33.1\n    patch ground y+ : min = 1, max = 20, average = 9\n")
    assert y == {"airfoil": {"min": 0.5, "max": 61.2, "average": 33.1}, "ground": {"min": 1.0, "max": 20.0, "average": 9.0}}


# ---- geometry and adjoint ---------------------------------------------------------

def test_incidence_rotates_le_toward_ground_and_keeps_ride_height():
    q0, lo0, le0 = t20_case.airfoil_points(0.224)
    q1, lo1, le1 = t20_case.airfoil_points(0.224, 1.0)
    angle = lambda q, le: math.degrees(math.atan2(q[0, 1] - q[le, 1], q[0, 0] - q[le, 0]))   # TE relative to LE
    assert angle(q1, le1) - angle(q0, le0) == pytest.approx(1.0, abs=1e-6)                # TE up = LE toward the ground
    assert q1[:le1 + 1, 1].min() == pytest.approx(0.224 * t20_case.CHORD, abs=1e-12)


def _cps():
    lo, hi = adj.box_bounds(0.05, t20_case.CHORD, t20_case.Z)
    nu, nv, nw = adj.BOX_NCPS
    g = [np.linspace(a, b, n) for a, b, n in zip(lo, hi, (nu, nv, nw))]
    cps = [(g[0][i], g[1][j], g[2][k]) for k in range(nw) for j in range(nv) for i in range(nu)]   # i fastest, as the Stage S CSV
    csv = '"Points : 0", "Points : 1", "Points : 2","i", "j", "k","active : 0", "active : 1", "active : 2"\n' + "".join(f"{x}, {y}, {z}, 0, 0, 0, 0, 0, 0\n" for x, y, z in cps)
    return np.array(cps), csv


def test_projection_reproduces_rigid_motion_of_an_affine_point():
    cps, csv = _cps()
    w = np.random.default_rng(0).random(len(cps))
    w /= w.sum()
    p = w @ cps                                   # a point reproduced by weights summing to 1
    x_low, y_le = 0.045, 0.067
    for comp, expect in ((1, (p[0] - x_low) * math.pi / 180), (0, -(p[1] - y_le) * math.pi / 180)):
        rows = "#varID total\n" + "".join(f"{3 * i + c} {w[i] if c == comp else 0.0}\n" for i in range(len(cps)) for c in range(3))
        r = adj.projected_derivatives(rows, csv, x_low, y_le)
        assert r["rotation_per_deg"] == pytest.approx(expect, rel=1e-12) and r["varids_complete"] and r["n_cps"] == 180
        assert r["x_translation_per_mm"] == pytest.approx(1e-3 if comp == 0 else 0.0, abs=1e-15)
    with pytest.raises(ValueError, match="outside"):
        adj.projected_derivatives("#varID total\n9999 1\n", csv, x_low, y_le)
    partial = adj.projected_derivatives("#varID total\n0 1\n", csv, x_low, y_le)
    assert not partial["varids_complete"]


def test_adjoint_dictionaries_patch_the_t20a_case_text():
    m = t20_case.MODELS["sa-wf"]
    f = t20_foam.system_and_constant(m, t20_case.MESHES["med30"], dict(u=30, nu=t20_case.NU, chord=t20_case.CHORD, z=t20_case.Z, iters=5000))
    sol, sch, cd = adj.fv_solution(f["system/fvSolution"]), adj.fv_schemes(f["system/fvSchemes"]), adj.control_dict(f["system/controlDict"])
    assert '"(pa).*"' in sol and 'equations { "(U|nuTilda)" 0.7; "Ua.*" 0.7; }' in sol and 'fields { p 0.3; "pa.*" 0.3; }' in sol and "consistent no;" in sol and "0.9" not in sol
    assert "default Gauss linear;" in sch and f"div(-phi,Ua{adj.SOLVER}) bounded Gauss upwind;" in sch and "default none;" not in sch
    assert "application adjointOptimisationFoam;" in cd and "startFrom startTime;" in cd and "endTime 100000;" in cd
    d = adj.dynamic_mesh_dict(*adj.box_bounds(0.05, t20_case.CHORD, t20_case.Z))
    assert "confineBoundaryControlPoints false;" in d and "confineWMovement" not in d
    o = adj.optimisation_dict(30.0, 4.468e-4, 300, 5000)
    assert "nIters 300;" in o and "nIters 5000;" in o and "direction (0 -1 0);" in o and "shapeType volumetricBSplines;" in o
    assert set(adj.adjoint_fields()) == {"0/Ua", "0/pa", "constant/adjointRASProperties"}


# ---- analyzer: synthetic outputs ----------------------------------------------------

EXP = {float(h): p["Cl"] for h, p in json.loads(A.EXP.read_text())["points"].items()}
NOISE = {-1.0: 0.0004, -0.5: -0.0006, -0.25: 0.0003, 0.0: 0.0, 0.25: -0.0002, 0.5: 0.0005, 1.0: -0.0003}


def rec(model, h, mesh, da, cl, status="COMPLETED", plateau=True, adjoint=None):
    r = {"id": A.cid(model, h, mesh, da), "model": model, "h_over_c": h, "mesh": mesh, "delta_alpha_deg": da, "status": status,
         "check_mesh": {"mesh_ok": True, "failed_check_counts": []}, "stages": [{"stage": "simpleFoam", "wall_s": 300.0}], "pre_solver_wall_s": 30.0,
         "total_wall_s": 330.0, "mesh_cells_3d": 15000,
         "forces": {"Cl": {"tail_mean": cl, "tail_std": 1e-4, "half_window_rel_diff": 1e-4}, "Cd": {"tail_mean": 0.03}, "cl_plateau": plateau,
                    "cl_block_rel_std": 1e-5, "iterations_to_plateau": 150, "history_rows": 5000}}
    if adjoint:
        r["adjoint"] = adjoint
    return r


def world(fine=1.01, sst_d=0.075, d=0.08, sign=1.0, level=1.02):
    """Cl = level * exp(h) * mesh factor + d * alpha (+ deterministic scan noise on sa-wf med30)."""
    out = {}
    def add(model, h, mesh, da):
        base = EXP[h] * level * (fine if mesh == "fine30" else 1.0)
        slope = (sst_d if model == "sst-wf" else d) * (sign if h == 0.224 else 1.0)
        noise = NOISE[da] if (model, mesh) == ("sa-wf", "med30") and h in A.SCAN else 0.0
        r = rec(model, h, mesh, da, base + slope * da + noise)
        out[r["id"]] = r
    for mesh in ("coa30", "med30", "fine30"):
        for h in A.HEIGHTS:
            add("sa-wf", h, mesh, 0.0)
        for h in A.INC:
            for da in (-1.0, 1.0):
                add("sa-wf", h, mesh, da)
    for h in A.SCAN:
        for da in (-0.5, -0.25, 0.25, 0.5):
            add("sa-wf", h, "med30", da)
    for h in A.HEIGHTS:
        add("sst-wf", h, "med30", 0.0)
    for h in A.INC:
        for da in (-1.0, 1.0):
            add("sst-wf", h, "med30", da)
    return out


def lm_world(adjoint=None):
    out = {A.cid("sst-lm", h, "wr2", 0.0): rec("sst-lm", h, "wr2", 0.0, EXP[h] * 1.02) for h in (0.224, 0.134, 0.09)}
    r = rec("sa-wf", 0.224, "med30", 0.0, EXP[0.224] * 1.02, adjoint=adjoint)
    out[r["id"]] = r
    return out


def write(tmp, name, cases, listed=()):
    d = tmp / name
    for i, r in cases.items():
        (d / "cases" / i).mkdir(parents=True)
        (d / "cases" / i / "case_result.json").write_text(json.dumps(r))
    (d / "result.json").write_text(json.dumps({"cases": list(listed)}))
    return d


def run(tmp, wf, lm, extra_wf=None):
    out = tmp / "analysis"
    dirs = [write(tmp, "wf", wf)] + ([write(tmp, "wf2", extra_wf)] if extra_wf else [])
    A.main(["--wf", *map(str, dirs), "--lm", str(write(tmp, "lm", lm)), "--out", str(out), "--t20a", str(tmp / "none")])
    return json.loads((out / "verdict.json").read_text())


def test_go_full(tmp_path):
    v = run(tmp_path, world(), lm_world())
    assert v["verdict"] == "T20B_GO_2D_SECTION", {k: g for k, g in v["gates"].items() if not g["value"]}
    assert v["thresholds_set_after_exploratory_visible"] and v["labels"]["G2_robustness"] == "ROBUST" and v["labels"]["LM"]["label"] == "LM_DATA_AGREES"
    with pytest.raises(SystemExit, match="written once"):
        A.main(["--wf", str(tmp_path / "wf"), "--lm", str(tmp_path / "lm"), "--out", str(tmp_path / "analysis")])


def test_go_differences_when_only_the_level_moves_with_the_mesh(tmp_path):
    v = run(tmp_path, world(fine=1.08), lm_world())
    assert v["verdict"] == "T20B_GO_2D_SECTION_DIFFERENCES" and v["gates"]["G3a"]["value"] is False
    assert v["labels"]["agreement_mesh_specific"] is True


@pytest.mark.parametrize("kw, gate", [(dict(level=1.07), "G2"), (dict(sign=-1.0), "G3b"), (dict(sst_d=0.03), "G4")])
def test_no_go_branches(tmp_path, kw, gate):
    v = run(tmp_path, world(**kw), lm_world())
    assert v["verdict"] == "T20B_NO_GO" and v["gates"][gate]["value"] is False


def test_solver_fail_fails_its_gates_and_infra_loss_is_enumerated(tmp_path):
    w = world()
    w[A.cid("sa-wf", 0.179, "med30", 0.0)]["forces"]["cl_plateau"] = False          # SOLVER_FAIL in the G2/G2d/G3a/G3c inputs
    v = run(tmp_path / "a", w, lm_world())
    assert v["verdict"] == "T20B_NO_GO" and all(v["gates"][k]["value"] is False for k in ("G2", "G2d", "G3a", "G3c"))
    w = world()
    del w[A.cid("sst-wf", 0.134, "med30", 1.0)]                                       # INFRA_LOSS in a G4 input only
    v = run(tmp_path / "b", w, lm_world())
    assert v["gates"]["G4"]["value"] is None and v["verdict"] == "T20B_INCOMPLETE"
    w = world(level=1.07)
    del w[A.cid("sst-wf", 0.134, "med30", 1.0)]                                       # ... but a failing gate already decides
    assert run(tmp_path / "c", w, lm_world())["verdict"] == "T20B_NO_GO"


def test_resubmission_only_fills_missing_cases(tmp_path):
    w = world()
    lost = A.cid("sst-wf", 0.134, "med30", 1.0)
    second = {lost: w.pop(lost), A.cid("sa-wf", 0.224, "med30", 0.0): rec("sa-wf", 0.224, "med30", 0.0, 9.9)}
    v = run(tmp_path, w, lm_world(), extra_wf=second)
    assert v["verdict"] == "T20B_GO_2D_SECTION" and v["cases_from_resubmission"] == [lost]


def test_mechanical_and_case_classes():
    r = rec("sa-wf", 0.224, "med30", 0.0, 1.3)
    assert A.classify(r) == "VALID" and A.classify(None) == "INFRA_LOSS" and A.classify({"status": "NOT_RUN_TIME_BUDGET"}) == "INFRA_LOSS"
    assert A.classify({**r, "check_mesh": {"mesh_ok": False, "failed_check_counts": [1]}}) == "MECHANICAL_FAIL"
    assert A.classify({**r, "status": "GENERATOR_FAILED"}) == "MECHANICAL_FAIL" and A.classify({**r, "status": "simpleFoam_FAILED"}) == "SOLVER_FAIL"


def test_adjoint_labels(tmp_path):
    w = world()
    good = {"status": "ADJ_RUNS", "projection": {"rotation_per_deg": 0.085, "x_translation_per_mm": 1e-4, "y_translation_per_mm": -0.004},
            "primal": {"last_initial_residuals": {"p": 1e-6, "Ux": 2e-6, "Uy": 2e-6, "nuTilda": 3e-6}}, "stage": {"wall_s": 400}}
    assert A.adj_label(w, lm_world(good))["label"] == "ADJ_CONSISTENT"
    far = {**good, "projection": {**good["projection"], "rotation_per_deg": 0.2}}
    lab = A.adj_label(w, lm_world(far))
    assert lab["label"] == "ADJ_RUNS" and not lab["ADJ_PRIMAL_UNCONVERGED"]
    leak = {**good, "projection": {**good["projection"], "x_translation_per_mm": 0.05}, "primal": {"last_initial_residuals": {"p": 1e-3}}}
    lab = A.adj_label(w, lm_world(leak))
    assert lab["label"] == "ADJ_RUNS" and lab["ADJ_PRIMAL_UNCONVERGED"]
    assert A.adj_label(w, {})["label"] == "ADJ_NOT_RUN"


def test_lm_label_needs_stationary_cycles():
    lm = lm_world()
    assert A.lm_label(lm, EXP)["label"] == "LM_DATA_AGREES"
    lm[A.cid("sst-lm", 0.134, "wr2", 0.0)]["forces"]["Cl"]["half_window_rel_diff"] = 0.02
    assert A.lm_label(lm, EXP)["label"] == "LM_NOT_QUALIFIED"
    del lm[A.cid("sst-lm", 0.09, "wr2", 0.0)]
    assert A.lm_label(lm, EXP)["label"] == "LM_INCOMPLETE"
