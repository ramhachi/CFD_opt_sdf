"""T2-0c (#57): builder, case lists, the morph (identity, geometry, fixed nodes, initial fields), and every verdict branch, the power requirement,
UNSTEADY, the next-action rows and the labels of the registered analyzer on synthetic outputs (no OpenFOAM, no network)."""
import gzip
import json
import math
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest

from scripts import analyze_t20c as A
from scripts import build_t20c_kernel as BK
from scripts import t20_case, t20c_case as M

REAL = Path(BK.ROOT)
TEMPLATE = REAL / "infra/kaggle/kernel_t20c_cpu/runner.py"


def runner_ns():
    src = TEMPLATE.read_text()
    ns = {"__name__": "t20c_runner_test"}
    exec(compile(src.replace("PINS = PIN_PINS", "PINS = {}").split('\nif __name__ == "__main__":')[0], "runner", "exec"), ns)
    return ns


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t", *args], check=True, capture_output=True, text=True).stdout.strip()


# ---- kernel template and builder ---------------------------------------------------

def test_builder_renders_each_mode_with_pins(tmp_path, monkeypatch):
    ns = runner_ns()
    for rel in (*BK.FILES, *ns["LOCKS"].values(), "infra/kaggle/kernel_t20c_cpu/runner.py", "infra/kaggle/kernel_t20c_cpu/kernel-metadata.json"):
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REAL / rel, tmp_path / rel)
    git(tmp_path, "init", "-q")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-qm", "x")
    for mod in (BK, BK.A):
        monkeypatch.setattr(mod, "ROOT", tmp_path)
    monkeypatch.setattr(BK, "TEMPLATE_DIR", tmp_path / "infra/kaggle/kernel_t20c_cpu")
    commit = git(tmp_path, "rev-parse", "HEAD")
    for mode, slug in BK.MODES.items():
        out = tmp_path / f"out_{mode}"
        BK.main(["--source-commit", commit, "--mode", mode, "--out", str(out)])
        text = (out / "runner.py").read_text()
        assert f"MODE = {mode!r}" in text and f"SOURCE_COMMIT = {commit!r}" in text and "scripts/t20c_case.py" in text
        meta = json.loads((out / "kernel-metadata.json").read_text())
        assert meta["title"] == slug == meta["id"].split("/")[1] and not meta["enable_gpu"] and meta["is_private"]
    (tmp_path / "scripts/t20c_case.py").write_text("# edited after the commit\n")
    with pytest.raises(ValueError, match="committed source differs"):
        BK.render(commit, "morph")


def test_registered_case_lists_and_ids_match_the_analyzer():
    ns = runner_ns()
    R, Mc, S = ns["R_CASES"], ns["M_CASES"], ns["S_CASES"]
    assert (len(R), len(Mc), len(S)) == (82, 93, 96)
    for cases in (R, Mc, S):
        ids = [ns["case_id"](*c) for c in cases]
        assert len(set(ids)) == len(ids) and cases[0][2] == min({c[2] for c in cases}, key=ns["MESH_ORDER"].get)   # most expensive mesh first
    assert {c[2] for c in R if c[4] != 0} == set(A.LEVELS) and {c[2] for c in R} == {"coa30", *A.LEVELS}
    assert len([c for c in Mc if c[5] == "B2"]) == 24 and len([c for c in Mc if c[5] == "lin"]) == 6 and len([c for c in Mc if c[0] == "base"]) == 9
    assert len([c for c in S if c[0] == "remesh"]) == 18 and len([c for c in S if c[0] == "morph"]) == 72
    assert len(ns["BASES"]["morph"]) == 15 and set(ns["BASES"]["shape"]) <= set(ns["BASES"]["smoke"])
    cid = ns["case_id"]
    assert cid("remesh", 0.134, "fine30", "incidence", -0.25, "") == A.rid(0.134, "fine30", -0.25) == "sa-wf_h0.134_fine30_da-0.25"
    assert cid("base", 0.09, "xfine30", "incidence", 0.0, "") == A.rid(0.09, "xfine30")
    assert cid("morph", 0.224, "fine30", "incidence", 1.0, "B2") == A.mid(0.224, "fine30", 1.0, "B2") == "sa-wf_h0.224_fine30_morphB2-da+1"
    assert cid("morph", 0.224, "fine30", "incidence", -1.0, "lin") == A.mid(0.224, "fine30", -1.0, "lin")
    assert cid("morph", 0.09, "med30", "camber", -0.25, "") == A.sid(0.09, "med30", "camber", -0.25) == "sa-wf_h0.09_med30_morph-camber-0.25mm"
    assert cid("remesh", 0.09, "fine30", "heave", 0.5, "") == A.sid(0.09, "fine30", "heave", 0.5, False)
    assert ns["ITERS"] == 5000 and ns["CONT_ITERS"] == 15000 and ns["CASE_CAP_S"] == 2.5 * 3600


def test_smoke_filter_and_set_iters(tmp_path):
    ns = runner_ns()
    ns["MODE"] = "smoke"
    kept = ns["_keep_text"]("Time = 5\nCl    : 1.2\n        Total    : (1 2 3)\nSolving for Ux, Initial residual = 1e-3\n")
    assert kept == "Time = 5\nSolving for Ux, Initial residual = 1e-3"
    (tmp_path / "system").mkdir()
    (tmp_path / "system/controlDict").write_text("startFrom startTime;\nendTime 5000;\nwriteInterval 5000;\n")
    ns["_set_iters"](tmp_path, 100)
    assert (tmp_path / "system/controlDict").read_text() == "startFrom startTime;\nendTime 100;\nwriteInterval 100;\n"


# ---- the morph ------------------------------------------------------------------------

@pytest.fixture(scope="module")
def base(tmp_path_factory):
    d = tmp_path_factory.mktemp("t20c") / "base"
    M.remesh_case(d, 0.224, "coa30", iters=5000)
    return d


def test_xfine30_level_and_layers():
    assert M.MESHES["xfine30"] == M.XFINE30 == dict(wall="wf", ds=1e-3, y1=0.6e-3, g=1.2, te=2, fan=4, last=0.65) and "xfine30" not in t20_case.MESHES
    for h in (0.671, 0.224, 0.09):
        n_spec, n, total = t20_case.layers(1e-3, 0.6e-3, 1.2, h * t20_case.CHORD, 0.65)
        assert n_spec == n == 2 and total == pytest.approx(1.32e-3)


def test_zero_morph_is_byte_identical_and_initial_fields_are_the_generators(base, tmp_path):
    man = M.morph_case(base, tmp_path / "z", "incidence", 0.0)
    assert (tmp_path / "z/mesh.msh").read_bytes() == (base / "mesh.msh").read_bytes() and man["morph"]["inverted_cells"] == 0
    for f in (base / "0").iterdir():
        text = (tmp_path / "z/0" / f.name).read_text()
        assert text == f.read_text() and "internalField uniform" in text
    assert not (tmp_path / "z/constant/polyMesh").exists()


def test_incidence_morph_reaches_the_generator_geometry(base, tmp_path):
    man = M.morph_case(base, tmp_path / "p1", "incidence", 1.0)
    m = man["morph"]
    assert m["contour_err_m"] < 1e-12 and m["inverted_cells"] == 0 and m["fixed_nodes_moved"] == 0 and m["airfoil_min_weight"] == 1.0
    assert man["delta_alpha_deg"] == 1.0 and man["mesh_quality_failures"] == []
    lines = (tmp_path / "p1/mesh.msh").read_text().split("\n")
    old = (base / "mesh.msh").read_text().split("\n")
    i, n = lines.index("$Nodes") + 2, int(lines[lines.index("$Nodes") + 1])
    assert lines[:i] == old[:i] and lines[i + n:] == old[i + n:]          # only node coordinates change
    g = M._groups(lines)
    xy = np.array([l.split()[1:3] for l in lines[i:i + n]], float)
    foil = sorted({k for c in g["airfoil"] for k in c})
    q1, i_low, _ = t20_case.airfoil_points(0.224, 1.0)
    assert xy[foil, 1].min() == pytest.approx(q1[i_low, 1], abs=2e-5)      # ride height kept at the new lowest point
    # a base at +0.5 deg morphed to +1 deg: the same target contour from another mesh realisation
    b2 = tmp_path / "b2"
    M.remesh_case(b2, 0.224, "coa30", 0.5, iters=5000)
    m2 = M.morph_case(b2, tmp_path / "p2", "incidence", 1.0)["morph"]
    assert m2["contour_err_m"] < 1e-12 and m2["base_delta_alpha_deg"] == 0.5
    with pytest.raises(ValueError, match="0-deg base"):
        M.displacement(0.224, "camber", 0.5, base_da=0.5)


def test_shape_modes_signs_ride_height_and_remeshed_contour(base, tmp_path):
    q0, _, i_le = t20_case.airfoil_points(0.224)
    for mode in ("camber", "flap"):
        D, s, moved = M.shape_contour(q0, i_le, 0.224, mode, 0.5)
        assert moved[:i_le + 1, 1].min() == pytest.approx(0.224 * t20_case.CHORD, abs=1e-15)
        te_rel = (moved[0, 1] - moved[i_le, 1]) - (q0[0, 1] - q0[i_le, 1])
        mid = np.argmin(np.abs(q0[:i_le + 1, 0] - 0.5 * t20_case.CHORD))
        if mode == "flap":
            assert te_rel == pytest.approx(0.5e-3, rel=0.02)                  # TE away from the ground
        else:
            assert moved[mid, 1] - q0[mid, 1] < s                              # mid-chord toward the ground relative to the shift
    man = M.morph_case(base, tmp_path / "hv", "heave", 0.5)
    assert man["h_m"] == pytest.approx(0.224 * t20_case.CHORD + 0.5e-3) and man["morph"]["inverted_cells"] == 0
    rem = M.remesh_case(tmp_path / "rc", 0.224, "coa30", iters=5000, shape="camber", shape_amp=0.5)
    assert rem["shape"]["mode"] == "camber" and rem["h_m"] == pytest.approx(0.224 * t20_case.CHORD, abs=1e-12)
    assert t20_case.airfoil_points(0.224)[0][5, 1] == q0[5, 1] and "xfine30" not in t20_case.MESHES   # the patches are undone
    with pytest.raises(ValueError, match="unmorphed"):
        M.morph_case(tmp_path / "rc", tmp_path / "x", "incidence", 1.0)


def test_morph_assertion_failure_exits_nonzero(base, tmp_path, monkeypatch):
    monkeypatch.setattr(M, "blend", lambda xy, Q0, b, kind="smoothstep": np.zeros(len(xy)))   # the airfoil would not move
    with pytest.raises(RuntimeError, match="airfoil_min_weight"):
        M.morph_case(base, tmp_path / "bad", "incidence", 1.0)


# ---- analyzer: synthetic outputs --------------------------------------------------------

EXP = {float(h): p["Cl"] for h, p in json.loads(A.B.EXP.read_text())["points"].items()}
NOISE = {-1.0: 0.0004, -0.5: -0.0006, -0.25: 0.0003, 0.0: 0.0, 0.25: -0.0002, 0.5: 0.0005, 1.0: -0.0003}
SLOPE = {0.224: 0.13, 0.134: 0.068, 0.09: 0.06}
LEVEL = {"coa30": 1.03, "med30": 1.04, "fine30": 1.01, "xfine30": 1.005}
K_SHAPE = {"camber": 0.05, "flap": 0.04, "heave": -0.02}   # per mm


def rec(i, cl, status="COMPLETED", plateau=True, tail_std=1e-4, mesh_sha="m", **extra):
    return {"id": i, "status": status, "check_mesh": {"mesh_ok": True, "failed_check_counts": [], "max_non_orthogonality": "40"},
            "stages": [{"stage": "simpleFoam", "wall_s": 300.0}], "pre_solver_wall_s": 30.0, "total_wall_s": 330.0, "mesh_cells_3d": 15000, "n_layers": 4,
            "mesh_msh_sha256": mesh_sha, "yplus": {"airfoil": {"average": 30.0}},
            "forces": {"Cl": {"tail_mean": cl, "tail_std": tail_std, "tail_rel_std": tail_std / abs(cl), "tail_min": cl, "tail_max": cl},
                       "Cd": {"tail_mean": 0.03}, "cl_plateau": plateau, "cl_block_rel_std": 1e-6, "iterations_to_plateau": 150, "history_rows": 5000}, **extra}


def world(slope=None, remesh_slope=None, b2_slope=None, morph_noise=0.0, level=None, peak_boost=0.0, shape=None):
    """Kernels R/M/S with Cl = EXP * level + slope * alpha (+ remeshing noise on R scans, + optional morph noise)."""
    slope = slope or (lambda m, h: SLOPE[h])
    remesh_slope = remesh_slope or slope
    b2_slope = b2_slope or slope
    level = level or LEVEL
    k = {"R": {}, "M": {}, "S": {}}
    c0 = lambda m, h: EXP[h] * level[m] + (peak_boost if h == 0.134 else 0.0)
    for m in level:
        for h in A.HEIGHTS:
            k["R"][A.rid(h, m)] = rec(A.rid(h, m), c0(m, h), mesh_sha=f"{m}{h}")
    for m in A.LEVELS:
        for h in A.H:
            for a in A.A7:
                if a:
                    k["R"][A.rid(h, m, a)] = rec(A.rid(h, m, a), c0(m, h) + remesh_slope(m, h) * a + NOISE[a])
                    k["M"][A.mid(h, m, a)] = rec(A.mid(h, m, a), c0(m, h) + slope(m, h) * a + morph_noise * NOISE[a] / 0.0006)
            k["M"][A.rid(h, m)] = rec(A.rid(h, m), c0(m, h), mesh_sha=f"{m}{h}")
    for m in ("med30", "fine30"):
        for h in A.H:
            for a in A.B2_TARGETS:
                k["M"][A.mid(h, m, a, "B2")] = rec(A.mid(h, m, a, "B2"), c0(m, h) + b2_slope(m, h) * a)
            k["S"][A.rid(h, m)] = rec(A.rid(h, m), c0(m, h), mesh_sha=f"{m}{h}")
            for mode in A.SHAPES:
                for a in (-0.5, -0.25, 0.25, 0.5):
                    k["S"][A.sid(h, m, mode, a)] = rec(A.sid(h, m, mode, a), c0(m, h) + (shape or K_SHAPE)[mode] * a)
    for h in A.H:
        for a in (-1.0, 1.0):
            k["M"][A.mid(h, "fine30", a, "lin")] = rec(A.mid(h, "fine30", a, "lin"), c0("fine30", h) + 1.01 * SLOPE[h] * a)
        for mode in A.SHAPES:
            for a in (-0.5, 0.5):
                k["S"][A.sid(h, "fine30", mode, a, False)] = rec(A.sid(h, "fine30", mode, a, False), c0("fine30", h) + K_SHAPE[mode] * a + NOISE[a])
    return k


def run(k):
    D = A.Data(k)
    g = A.evaluate(D, A.atoms_spec())
    v = A.verdict(g)
    return v, A.next_action(g, v), g


def test_compare_power_requirement_and_floor():
    c = A.compare(0.10, 0.11, 1e-4, 1e-4)
    assert c["pass"] and not c["unresolved"] and c["allowed"] == pytest.approx(0.0275)
    noisy = A.compare(0.10, 0.10, 0.004, 0.004)                          # 3 rss = 0.017 > 0.5 * 0.25 * 0.10
    assert noisy["unresolved"] and not noisy["pass"]
    assert A.compare(0.10, 0.10, 0.004, 0.004, power=False)["pass"]
    assert A.compare(0.02, 0.029, 0.0, 0.0)["pass"] and not A.compare(0.02, 0.029, 0.0, 0.0, floor=0.0)["pass"]   # the 0.01 per deg floor
    assert not A.compare(float("nan"), 0.1, 0.0, 0.0)["pass"]


def test_all_pass_gives_go_and_row_3():
    v, act, g = run(world())
    assert v == A.V_GO and act["row"] == 3 and len(g) == 14 and all(x["value"] for x in g.values())
    s = A.Data(world()).sigma("R", "fine30", 0.134)
    assert s["iter"] == 1e-4 and s["eff"] == max(s["fit_cubic"], 1e-4) and s["fit_quadratic"] > 0


def test_unsteady_case_at_009_gives_attached_with_unsteady_route():
    k = world()
    r = k["M"][A.mid(0.09, "xfine30", 1.0)]
    r["forces"]["Cl"]["tail_rel_std"] = 0.0188
    assert A.classify(r) == "UNSTEADY"
    v, act, g = run(k)
    assert v == A.V_ATT and act["row"] == 4 and act["row_for_0.09"] == 5
    assert g[("G3bm", 0.09)]["value"] is False and g[("G7m_xfine30", 0.09)]["value"] is False and g[("G3bm", 0.134)]["value"]


def test_g3bm_failure_attached_heights_gives_no_go_row_9():
    v, act, _ = run(world(slope=lambda m, h: SLOPE[h] * (1.5 if (m == "xfine30" and h == 0.134) else 1.0),
                          remesh_slope=lambda m, h: SLOPE[h] * (1.5 if (m == "xfine30" and h == 0.134) else 1.0)))
    assert v == A.V_NO and act["row"] == 9


def test_g7m_and_g8m_failures_route_in_order():
    v, act, g = run(world(remesh_slope=lambda m, h: SLOPE[h] * (1.6 if m == "fine30" else 1.0)))
    assert v == A.V_NO and act["row"] == 6 and not g[("G7m_fine30", 0.224)]["value"]
    v, act, g = run(world(b2_slope=lambda m, h: SLOPE[h] * (1.5 if h == 0.224 else 1.0)))
    assert v == A.V_NO and act["row"] == 7 and not g[("G8m", 0.224)]["value"]
    v, act, g = run(world(b2_slope=lambda m, h: SLOPE[h] * (1.5 if h == 0.09 else 1.0)))
    assert v == A.V_ATT and act["row_for_0.09"] == 7


def test_morph_noise_fails_g6m_through_the_power_requirement():
    k = world(morph_noise=0.006)
    v, act, g = run(k)
    assert v == A.V_NO and not g[("G6m", 0.134)]["value"]
    assert g[("G6m", 0.134)]["detail"]["consistency"]["unresolved"] or not g[("G6m", 0.134)]["detail"]["resolved"]
    assert act["row"] == 8 and set(act["failing"].values()) == {8}   # freeze-2 interpretation: failures only through noise are row 8


def test_sign_check_and_mechanical_and_solver_failures():
    v, _, g = run(world(slope=lambda m, h: -SLOPE[h] if h == 0.224 else SLOPE[h], remesh_slope=lambda m, h: -SLOPE[h] if h == 0.224 else SLOPE[h],
                        b2_slope=lambda m, h: -SLOPE[h] if h == 0.224 else SLOPE[h]))
    assert v == A.V_NO and g[("G3bm", 0.224)]["detail"]["sign_ok"] is False
    k = world()
    k["M"][A.mid(0.134, "fine30", 0.5)]["status"] = "TOPOLOGY_CHANGED"
    v, act, _ = run(k)
    assert v == A.V_NO and act["row"] == 1
    k = world()
    k["R"][A.rid(0.224, "fine30", -1.0)]["forces"]["cl_plateau"] = False
    v, act, _ = run(k)
    assert v == A.V_NO and act["row"] == 5


def test_failed_input_dominates_a_lost_input_in_the_same_gate():
    k = world()
    k["M"][A.mid(0.224, "fine30", 0.25)]["status"] = "NOT_RUN_TIME_BUDGET"
    k["M"][A.mid(0.224, "fine30", 1.0, "B2")]["forces"]["Cl"]["tail_rel_std"] = 0.02
    v, act, g = run(k)
    assert g[("G8m", 0.224)]["value"] is False and v == A.V_NO and act["row"] == 5


def test_single_component_failures_and_power_by_gate():
    k = world()
    for a in (-0.25, 0.25):   # B' disagrees only at s = 0.25
        r = k["M"][A.mid(0.134, "fine30", a, "B2")]
        r["forces"]["Cl"]["tail_mean"] += 0.5 * SLOPE[0.134] * a
    v, act, g = run(k)
    d = g[("G8m", 0.134)]["detail"]
    assert d["1.0"]["pass"] and not d["0.25"]["pass"] and not d["0.25"]["unresolved"] and v == A.V_NO and act["row"] == 7
    k = world()
    for a in A.A7:   # a noisy xfine30 morph scan: G3bm UNRESOLVED (power), G7m(xfine30) has no power requirement
        if a:
            k["M"][A.mid(0.134, "xfine30", a)]["forces"]["Cl"]["tail_std"] = 0.006
    v, act, g = run(k)
    assert g[("G3bm", 0.134)]["detail"]["xfine30"]["unresolved"] and g[("G7m_xfine30", 0.134)]["value"] is True
    assert g[("G7m_xfine30", 0.134)]["detail"]["unresolved"] is False and v == A.V_NO and act["row"] == 8
    v, act, g = run(world(slope=lambda m, h: 0.001 if h == 0.134 else SLOPE[h], remesh_slope=lambda m, h: 0.001 if h == 0.134 else SLOPE[h],
                          b2_slope=lambda m, h: 0.001 if h == 0.134 else SLOPE[h]))
    assert g[("G6m", 0.134)]["detail"]["resolved"] is False and act["row"] == 8


def test_unsteady_boundary_and_mechanical_statuses():
    r = rec("x", 1.0, tail_std=0.005)
    assert A.classify(r) == "VALID"
    r["forces"]["Cl"]["tail_rel_std"] = 0.0051
    assert A.classify(r) == "UNSTEADY"
    for st in ("TOPOLOGY_CHANGED", "BASE_TOPOLOGY_MISSING", "GENERATOR_FAILED", "checkMesh_FAILED"):
        assert A.classify({**rec("x", 1.0), "status": st}) == "MECHANICAL_FAIL"
    assert A.classify({**rec("x", 1.0), "status": "RUNNER_EXCEPTION"}) == "INFRA_LOSS"
    k = world()
    k["S"][A.sid(0.134, "fine30", "flap", 0.5)]["status"] = "TOPOLOGY_CHANGED"
    D = A.Data(k)
    spec = A.atoms_spec()
    g = A.evaluate(D, spec)
    act = A.next_action(g, A.verdict(g), ["S:" + A.sid(0.134, "fine30", "flap", 0.5)])
    assert act["row"] == 3 and act["mechanical_fail_outside_gate_inputs"] == ["S:" + A.sid(0.134, "fine30", "flap", 0.5)]


def test_smoke_mesh_pass_has_one_case_per_id():
    ns = runner_ns()
    unique = {}
    for sp in ns["make_specs"](ns["M_CASES"] + ns["S_CASES"] + ns["R_CASES"], solve=False):
        unique.setdefault(sp["id"], sp)
    assert len(unique) == 256 and sum(s["method"] == "base" for s in unique.values()) == 9


def test_infrastructure_loss_enumeration():
    k = world()
    k["M"][A.mid(0.09, "fine30", 1.0, "B2")]["status"] = "NOT_RUN_TIME_BUDGET"
    v, act, g = run(k)
    assert g[("G8m", 0.09)]["value"] is None and v == A.V_INC and act["row"] == 2
    k["M"][A.mid(0.09, "xfine30", 1.0)]["forces"]["cl_plateau"] = False      # a failure at 0.09 makes the open gate irrelevant
    v, _, _ = run(k)
    assert v == A.V_ATT
    k = world()
    del k["M"][A.mid(0.134, "fine30", 0.25)]
    v, _, _ = run(k)
    assert v == A.V_INC


def test_series_peak_and_g2_labels():
    D = A.Data(world())
    s = A.series_labels(D, EXP)
    assert s["PEAK"] == "PEAK_AT_FINER_LEVELS" or s["PEAK"] == "PEAK_INDETERMINATE_NOISE"
    lv = {"coa30": 1.03, "med30": 1.04, "fine30": 1.01, "xfine30": 1.005}
    s = A.series_labels(A.Data(world(peak_boost=0.05)), EXP)
    assert s["PEAK"] == "PEAK_AT_FINER_LEVELS" and s["G2_by_level"]["xfine30"]["peak_h"] == 0.134
    s = A.series_labels(A.Data(world(peak_boost=-0.08)), EXP)
    assert s["PEAK"] == "PEAK_NOT_AT_FINER_LEVELS"
    cl = s["Cl"][0.671]
    assert cl["e2"] == pytest.approx(EXP[0.671] * (lv["fine30"] - lv["med30"])) and cl["label"] in ("MONOTONE", "NOT_RESOLVED")
    assert isinstance(s["G2_by_level"]["fine30"]["mean_abs_e_plus_0p15deg"], float) and "mean_abs_e_plus_0p15deg" not in s["G2_by_level"]["coa30"]


def test_shape_labels():
    D = A.Data(world())
    sh = A.shape_labels(D)
    assert sh["label"] == "SHAPE_RESOLVED_CONSISTENT", sh["holds"]
    row = sh["camber:0.134"]
    assert row["fine30"]["d_per_mm"][0.5] == pytest.approx(0.05) and row["fine30"]["expected_sign_ok"] and row["fine30"]["resolved"]
    sh = A.shape_labels(A.Data(world(shape={"camber": 0.0001, "flap": 0.04, "heave": -0.02})))
    assert sh["label"] == "SHAPE_NOT_RESOLVED"


def test_replication_label_against_t20b_layout(tmp_path):
    k = world()
    d = tmp_path / "t20b/cases/sa-wf_h0.224_med30_da0"
    d.mkdir(parents=True)
    old = k["R"][A.rid(0.224, "med30")]
    (d / "case_result.json").write_text(json.dumps(old))
    (d / "case_manifest.json.gz").write_bytes(gzip.compress(json.dumps({"mesh_msh_sha256": old["mesh_msh_sha256"]}).encode()))
    rep = A.replication_labels(A.Data(k), tmp_path / "t20b", {})
    assert rep["vs_T20B"]["label"] == "REPLICATED_BITWISE" and rep["cross_kernel"]["label"] == "CROSS_KERNEL_IDENTICAL"
    k["R"][A.rid(0.224, "med30")]["forces"]["Cl"]["tail_mean"] *= 1 + 1e-6
    assert A.replication_labels(A.Data(k), tmp_path / "t20b", {})["vs_T20B"]["label"] == "NOT_BITWISE"


def test_main_writes_once(tmp_path):
    k = world()
    for name, key in (("remesh", "R"), ("morph", "M"), ("shape", "S")):
        for i, r in k[key].items():
            p = tmp_path / name / "cases" / i
            p.mkdir(parents=True)
            (p / "case_result.json").write_text(json.dumps(r))
    out = tmp_path / "out"
    args = ["--remesh", str(tmp_path / "remesh"), "--morph", str(tmp_path / "morph"), "--shape", str(tmp_path / "shape"), "--t20b", str(tmp_path / "none"), "--out", str(out)]
    A.main(args)
    v = json.loads((out / "verdict.json").read_text())
    lab = v["labels"]
    assert v["verdict"] == A.V_GO and v["thresholds_set_after_t20b_visible"] and lab["MED30"]["full"] is True and v["next_action"]["row"] == 3
    assert all(lab["SURVIVES_2SIGMA"].values()) and lab["G6M_009"]["pass"] and all(isinstance(b, dict) for b in lab["BLEND"].values())
    assert all(x["pass"] for x in lab["remeshed_rules"].values() if isinstance(x, dict) and "pass" in x) and len(lab["noise"]["per_pair_ratio_R_over_M"]) == 9
    assert any(p.endswith("analyze_t20b.py") for p in v["input_sha256"])
    assert "T2-0c registered verdict" in (out / "analysis.md").read_text() and v["labels"]["noise"]["pooled_noise_reduction_R_over_M"] > 1
    with pytest.raises(SystemExit):
        A.main(args)
