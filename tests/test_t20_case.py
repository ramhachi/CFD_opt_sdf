"""T2-0a case generator: mesh and dictionary checks that need no OpenFOAM (gmsh only). OpenFOAM-side behaviour is NOT tested here."""
import json
import math
import re
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("gmsh")
from scripts import t20_case as T  # noqa: E402  (sets OMP_NUM_THREADS=1 before gmsh loads: the BL mesher is nondeterministic with threads)
from scripts import t20_foam as F  # noqa: E402
import gmsh  # noqa: E402

HC = (0.671, 0.224, 0.134, 0.09)
MODELS = ("sa-wf", "sst-wf", "sst-lm")


def mesh_for(model):
    return "wr2" if T.MODELS[model]["wall"] == "wr" else "med30"


@pytest.fixture(scope="module")
def cases(tmp_path_factory):
    root = tmp_path_factory.mktemp("t20")
    return {(h, m): (root / f"{m}_{h}", T.write_case(root / f"{m}_{h}", h, m, mesh_for(m))) for h in HC for m in MODELS}


def test_coordinate_table_and_physical_units():
    rows = np.loadtxt(T.COORDS)
    assert rows.shape == (44, 4) and tuple(rows[0]) == (0, 0, 0, 0) and tuple(rows[-1]) == (1, 0.0603, 1, 0.0603)
    assert rows[:, 1].min() == -0.0771 and rows[np.argmin(rows[:, 1]), 0] == 0.1996
    assert T.U_INF * T.CHORD / T.NU == pytest.approx(4.6e5)


@pytest.mark.parametrize("h", HC)
@pytest.mark.parametrize("delta", [0.0, 2.0])
def test_ride_height_is_the_lowest_suction_point_exactly(h, delta):
    Q, i_low, i_le = T.airfoil_points(h, delta)
    assert Q[i_low, 1] == pytest.approx(h * T.CHORD, abs=1e-12)
    assert Q[:i_le + 1, 1].min() == Q[i_low, 1] and Q[:, 1].min() >= Q[i_low, 1] - 1e-6   # also nothing below it on the pressure side
    assert Q[-1, 1] > Q[i_le, 1]                                                          # TE above LE: positive incidence as listed
    if delta:
        assert (Q[-1, 1] - Q[i_le, 1]) > (T.airfoil_points(h)[0][-1, 1] - T.airfoil_points(h)[0][i_le, 1])


@pytest.mark.parametrize("h", HC)
@pytest.mark.parametrize("model", MODELS)
def test_mesh_counts_first_cell_gap_and_ride_height(cases, h, model):
    _, man = cases[(h, model)]
    s, spec = man["mesh_stats"], man["mesh_spec"]
    assert s["cells_3d"] == s["cells_2d"] == s["tri_cells"] + s["quad_cells"]
    lo, hi = (70_000, 160_000) if mesh_for(model) == "wr2" else (8_000, 40_000)
    assert lo < s["cells_3d"] < hi
    fa = s["first_cell_airfoil_m"]
    assert fa["median"] == pytest.approx(spec["y1"], rel=0.01) and fa["p05"] > 0.95 * spec["y1"] and fa["p95"] < 1.10 * spec["y1"]
    assert s["first_cell_ground_m"]["median"] == pytest.approx(spec["y1"], rel=0.01)
    assert s["gap_cells_at_lowest_point"] >= 15
    assert man["h_m"] == pytest.approx(h * T.CHORD, abs=1e-12)
    assert abs(s["airfoil_node_min_y_m"] - man["h_m"]) < 1e-6                        # no mesh node on the airfoil lower than the ride height
    assert s["n_layers"] <= s["n_layers_spec"] and s["bl_thickness_m"] <= 0.4 * man["h_m"] + 1e-12


def test_wall_resolved_first_cell_y_plus_estimate():
    # flat-plate estimate (Cf = 0.006 is generous for Re_c 4.6e5): y+ = y1 u_tau / nu with u_tau = U sqrt(Cf/2); wrc is the coarse smoke mesh (y+ ~ 2)
    assert T.MESHES["wr2"]["y1"] * T.U_INF * math.sqrt(0.003) / T.NU < 1.2
    assert T.MESHES["wrc"]["y1"] * T.U_INF * math.sqrt(0.003) / T.NU < 2.5


def test_dictionaries_are_deterministic_and_the_mesh_is_stable_within_a_percent(tmp_path, cases):
    # gmsh's boundary-layer path is not bit-reproducible (documented in t20_case.py): everything except mesh.msh and the mesh part of the manifest must be.
    T.write_case(tmp_path / "again", 0.134, "sa-wf", "med30")
    first, man = cases[(0.134, "sa-wf")]
    again = json.loads((tmp_path / "again/case_manifest.json").read_text())
    names = sorted(str(p.relative_to(first)) for p in first.rglob("*") if p.is_file())
    assert names == sorted(str(p.relative_to(tmp_path / "again")) for p in (tmp_path / "again").rglob("*") if p.is_file())
    assert all((first / n).read_bytes() == (tmp_path / "again" / n).read_bytes() for n in names if n not in ("mesh.msh", "case_manifest.json"))
    drop = lambda d: {k: v for k, v in d.items() if k not in ("mesh_stats", "mesh_msh_sha256", "mesh_quality_failures")}
    assert drop(man) == drop(again)
    assert abs(again["mesh_stats"]["cells_3d"] / man["mesh_stats"]["cells_3d"] - 1) < 0.01
    assert again["mesh_stats"]["ride_height_m"] == man["mesh_stats"]["ride_height_m"]
    a1, a2 = T.airfoil_points(0.134), T.airfoil_points(0.134)       # the geometry itself is exactly reproducible
    assert a1[0].tobytes() == a2[0].tobytes()


COMMON = ["0/U", "0/p", "0/nut", "constant/transportProperties", "constant/momentumTransport", "constant/turbulenceProperties",
          "system/controlDict", "system/fvSchemes", "system/fvSolution", "mesh.msh", "case_manifest.json"]
EXTRA = {"sa-wf": ["0/nuTilda"], "sst-wf": ["0/k", "0/omega"], "sst-lm": ["0/k", "0/omega", "0/ReThetat", "0/gammaInt"]}


@pytest.mark.parametrize("model", MODELS)
def test_foam_files_present_and_parseable_as_text(cases, model):
    d, man = cases[(0.224, model)]
    for rel in COMMON + EXTRA[model]:
        text = (d / rel).read_text()
        assert text.count("{") == text.count("}") and text.count("(") == text.count(")"), rel
        if rel.startswith(("0/", "system/", "constant/")):
            assert text.startswith("FoamFile")
    assert not (d / "0/nuTilda").exists() or model == "sa-wf"
    turb = (d / "constant/momentumTransport").read_text()
    assert f"model {'kOmegaSST' if model == 'sst-lm' else T.MODELS[model]['foam']};" in turb   # LM: stage 1 is kOmegaSST, the LM dictionaries wait in stage2/
    assert turb.replace("momentumTransport", "turbulenceProperties") == (d / "constant/turbulenceProperties").read_text()
    ctrl = (d / "system/controlDict").read_text()
    assert "liftDir (0 -1 0);" in ctrl and "dragDir (1 0 0);" in ctrl and f"magUInf {T.U_INF};" in ctrl and f"lRef {T.CHORD};" in ctrl
    assert float(re.search(r"Aref ([\d.e-]+);", ctrl).group(1)) == pytest.approx(T.CHORD * T.Z)
    assert re.search(r"nu \[0 2 -1 0 0 0 0\] ([\d.e-]+);", (d / "constant/transportProperties").read_text()).group(1) == str(T.NU)
    u = (d / "0/U").read_text()
    assert re.search(r"ground\s*\{\s*type fixedValue;\s*value uniform \(30.0 0 0\);", u) and "airfoil" in u and "type slip;" in u
    for patch in ("inlet", "outlet", "top", "ground", "airfoil", "front", "back"):
        assert patch in u
    if model == "sst-lm":
        assert float(re.search(r"internalField uniform ([\d.]+);", (d / "0/ReThetat").read_text()).group(1)) == pytest.approx(F.retheta_t(0.3), rel=1e-9)
        assert F.retheta_t(0.3) == pytest.approx(999.1, abs=0.1) and "nutLowReWallFunction" in (d / "0/nut").read_text()
    else:
        assert "WallFunction" in (d / "0/nut").read_text() and "nutLowRe" not in (d / "0/nut").read_text()
    msh = (d / "mesh.msh").read_text()
    assert msh.startswith("$MeshFormat\n2.2 ")
    for name in ("inlet", "outlet", "top", "ground", "airfoil", "front", "back", "fluid"):
        assert f'"{name}"' in msh
    assert man["coords_sha256"] == T.sha256(T.COORDS) and man["gmsh_version"] == gmsh.__version__
    json.loads((d / "case_manifest.json").read_text())


def test_model_and_mesh_wall_treatment_must_match(tmp_path):
    with pytest.raises(ValueError):
        T.write_case(tmp_path / "x", 0.224, "sst-lm", "med30")
    with pytest.raises(ValueError):
        T.write_case(tmp_path / "y", 0.224, "sa-wf", "wr2")


def test_fix_boundary_sets_empty_and_wall_types():
    text = "7\n(\n" + "".join(f"    {n}\n    {{\n        type patch;\n        nFaces 3;\n    }}\n" for n in ("inlet", "front", "back", "airfoil", "ground")) + ")\n"
    out = F.fix_boundary(text)
    for n, t in (("inlet", "patch"), ("front", "empty"), ("back", "empty"), ("airfoil", "wall"), ("ground", "wall")):
        assert re.search(rf"{n}\s*\{{\s*type {t};", out)
    with pytest.raises(ValueError):
        F.fix_boundary("inlet { type patch; }")


FACES = {5: [(0, 1, 2, 3), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)],
         6: [(0, 1, 2), (3, 4, 5), (0, 1, 4, 3), (1, 2, 5, 4), (2, 0, 3, 5)]}


@pytest.mark.parametrize("model", ["sa-wf", "sst-lm"])
def test_msh_is_a_closed_one_cell_thick_mesh_whose_boundary_is_exactly_the_physical_faces(cases, model):
    """What gmshToFoam needs: every cell face is shared by two cells or is a tagged boundary face (this is a proxy; gmshToFoam itself was not run)."""
    text = (cases[(0.09, model)][0] / "mesh.msh").read_text().split("\n")
    i = text.index("$Elements")
    rows = [list(map(int, r.split())) for r in text[i + 2:i + 2 + int(text[i + 1])]]
    use, tagged, nz = {}, {}, {}
    for r in rows:
        et, nodes = r[1], r[5:]
        if et in FACES:
            for f in FACES[et]:
                key = frozenset(nodes[j] for j in f)
                use[key] = use.get(key, 0) + 1
        else:
            tagged[frozenset(nodes)] = r[3]
    assert max(use.values()) == 2 and {k for k, v in use.items() if v == 1} == set(tagged)
    assert {v for v in tagged.values()} == {1, 2, 3, 4, 5, 6, 7}
    nodes_z = {int(r.split()[0]): float(r.split()[3]) for r in text[text.index("$Nodes") + 2:text.index("$EndNodes")]}
    assert set(nodes_z.values()) == {0.0, T.Z}


# ---- mesh quality: the local proxy of checkMesh, every mesh spec at every registered ride height -------------------------------------------------------

ALL_HC = (0.671, 0.448, 0.224, 0.134, 0.09)
_MESHES = {}


def stats_for(spec, h, tmp_path_factory):
    if (spec, h) not in _MESHES:
        _MESHES[spec, h] = T.build_mesh(h, T.MESHES[spec], tmp_path_factory.mktemp("q") / "m.msh")
    return _MESHES[spec, h]


@pytest.mark.parametrize("h", ALL_HC)
@pytest.mark.parametrize("spec", sorted(T.MESHES))
def test_every_mesh_spec_at_every_height_passes_the_local_checkmesh_proxy(tmp_path_factory, spec, h):
    """What attempt 2 failed on Kaggle (1024 unused points, 89.9 degree faces, skewness, determinant, weights, volume ratios) can no longer happen locally."""
    s = stats_for(spec, h, tmp_path_factory)
    q = s["quality"]
    assert T.quality_failures(q, s["gmsh_min_sicn_tri"]) == [], q
    assert q["unused_nodes"] == 0 and q["nonorth_gt70_faces"] == 0 and q["skew_gt4_faces"] == 0
    assert q["weight_lt0.05_faces"] == q["vol_ratio_lt0.01_faces"] == q["det_lt1e-3_cells"] == 0
    assert q["cells"] == s["cells_2d"]
    assert s["gap_cells_at_lowest_point"] >= 15                                   # also at h/c 0.09 for every spec
    assert abs(s["airfoil_node_min_y_m"] - s["ride_height_m"]) < 1e-6 and s["ride_height_m"] == pytest.approx(h * T.CHORD, abs=1e-12)
    wall = T.MESHES[spec]["wall"]
    assert q["aspect_ratio_max"] < (14 if wall == "wf" else 100)                  # wall-resolved: the cell-determinant limit (interior aspect ratio ~89) is the binding one


def test_wall_resolved_first_layer_and_end_columns_respect_the_determinant_limit(tmp_path_factory):
    # checkMesh's cell determinant: interior cell 8 (dy/dx)^2 >= 1e-3 -> aspect ratio < ~89; a wall cell 20 (dy/dx)^2 -> < ~141; end-column cell 1.27 (dy/dx)^2 -> < ~35
    for name, spec in T.MESHES.items():
        if spec["wall"] == "wr":
            assert spec["ds"] / spec["y1"] <= 85 and T.END_AR <= 30 and spec["last"] == 0.3
            s = stats_for(name, 0.09, tmp_path_factory)
            assert s["first_cell_ground_m"]["median"] == pytest.approx(spec["y1"], rel=1e-6)   # the explicit ground block has the exact first layer
            assert stats_for(name, 0.448, tmp_path_factory)["bl_thickness_m"] / spec["y1"] <= 100   # sharp-TE fan: best face weight ~ 1/(1 + sqrt(1.5 R/y1))


def test_mesh_quality_reproduces_openfoam_definitions_on_a_hand_checkable_grid(tmp_path):
    def msh(xs, ys):
        nx, ny = len(xs), len(ys)
        node = lambda i, j: j * nx + i + 1
        lines = ["$MeshFormat", "2.2 0 8", "$EndMeshFormat", "$PhysicalNames", "2", '2 6 "front"', '3 10 "fluid"', "$EndPhysicalNames", "$Nodes", str(2 * nx * ny)]
        lines += [f"{node(i, j) + k * nx * ny} {xs[i]} {ys[j]} {0.1 * k}" for k in (0, 1) for j in range(ny) for i in range(nx)] + ["$EndNodes", "$Elements"]
        els = []
        for j in range(ny - 1):
            for i in range(nx - 1):
                q = [node(i, j), node(i + 1, j), node(i + 1, j + 1), node(i, j + 1)]
                els += [f"3 2 6 6 {' '.join(map(str, q))}", f"5 2 10 10 {' '.join(str(n) for n in q + [n + nx * ny for n in q])}"]
        lines += [str(len(els))] + [f"{k} {e}" for k, e in enumerate(els, 1)] + ["$EndElements", ""]
        out = tmp_path / "g.msh"
        out.write_text("\n".join(lines))
        return T.mesh_quality(out)
    q = msh([0, 1, 2, 3], [0, 1, 2, 3])                       # unit square 3 x 3
    assert q["unused_nodes"] == 0 and q["cells"] == 9 and q["nonorth_max"] == pytest.approx(0) and q["skew_max"] == pytest.approx(0) and q["aspect_ratio_max"] == pytest.approx(1)
    assert q["weight_min"] == pytest.approx(0.5) and q["vol_ratio_min"] == pytest.approx(1) and q["det_min"] == pytest.approx(1 / 8)   # corner cell: 2 internal faces, det 1 / 8
    q = msh([0, 1, 4, 5], [0, 1, 2, 3])                       # middle column 3 wide: weight 1/4 (centres 0.5 and 2.5 around the face x = 1), volume ratio 1/3
    assert q["weight_min"] == pytest.approx(0.25) and q["vol_ratio_min"] == pytest.approx(1 / 3)
    thin = msh([0, 1, 2, 3], [0, 0.01, 0.02, 0.03])           # aspect ratio 100: the centre cell has det 8 (dy/dx)^2 = 8e-4, the 3-internal-face edge cell 2 (dy/avg)^2 (dx/avg)^2 / 8 = 1.24e-4 (the minimum), both < 1e-3
    assert thin["aspect_ratio_max"] == pytest.approx(100) and thin["det_min"] == pytest.approx(1.2406e-4, rel=1e-3) and "det_lt1e-3_cells" in T.quality_failures(thin)
    assert T.quality_failures(q) == [] and T.quality_failures({**q, "unused_nodes": 1}) == ["unused_nodes"]


def test_write_msh_drops_nodes_that_no_cell_uses(tmp_path):
    # the 1024 `unused points` of the Kaggle attempt were geometry points / spline control points saved as nodes
    s = T.build_mesh(0.448, T.MESHES["coa30"], tmp_path / "m.msh")
    assert s["quality"]["unused_nodes"] == 0
    lines = (tmp_path / "m.msh").read_text().split("\n")
    assert int(lines[lines.index("$Nodes") + 1]) == len(set(n for l in lines[lines.index("$Elements") + 2:] if len(l.split()) > 5 and l.split()[1] in ("5", "6") for n in l.split()[5:]))


def test_manifest_records_the_mesh_quality_metrics(cases):
    _, man = cases[(0.09, "sst-lm")]
    q = man["mesh_stats"]["quality"]
    assert man["mesh_quality_failures"] == [] and q["unused_nodes"] == 0 and {"nonorth_max", "skew_max", "weight_min", "vol_ratio_min", "det_min", "aspect_ratio_max", "worst_xy_m"} <= set(q)
    assert man["mesh_stats"]["gmsh_min_sicn_tri"] > T.LIMITS["min_sicn"]


def test_lm_case_is_a_two_stage_continuation_with_low_relaxation(cases):
    d, man = cases[(0.224, "sst-lm")]
    n1, n2 = man["iterations_stage1_sst"], man["iterations_stage2_lm"]
    assert (n1, n2) == (2000, 8000) and man["iterations"] == 10000
    root_ctrl, root_sol, root_tr = (d / "system/controlDict").read_text(), (d / "system/fvSolution").read_text(), (d / "constant/momentumTransport").read_text()
    assert "model kOmegaSST;" in root_tr and f"endTime {n1};" in root_ctrl and "startFrom startTime;" in root_ctrl and "consistent yes;" in root_sol
    two = d / "stage2"
    assert "model kOmegaSSTLM;" in (two / "constant/momentumTransport").read_text()
    ctrl, sol, sch = (two / "system/controlDict").read_text(), (two / "system/fvSolution").read_text(), (two / "system/fvSchemes").read_text()
    assert "startFrom latestTime;" in ctrl and f"endTime {n1 + n2};" in ctrl
    assert "consistent no;" in sol and "fields { p 0.2; }" in sol and "U 0.5;" in sol and '"(k|omega|ReThetat|gammaInt)" 0.3;' in sol
    for f in ("k", "omega", "ReThetat", "gammaInt"):
        assert f"bounded Gauss upwind" in sch and f"div(phi,{f}) bounded Gauss upwind;" in sch
    assert "UMax 60.0;" in (two / "system/fvOptions").read_text()
    assert not (d / "system/fvOptions").exists()                                  # the limiter only arrives with stage 2
    assert (d / "0/gammaInt").read_text().count("uniform 1;") >= 1 and (d / "0/ReThetat").is_file()
    assert not (cases[(0.224, "sa-wf")][0] / "stage2").exists()
    smoke = T.write_case(d.parent / "smoke_lm", 0.448, "sst-lm", "wrc", iters=200)
    assert (smoke["iterations_stage1_sst"], smoke["iterations_stage2_lm"]) == (100, 100) and smoke["mesh_quality_failures"] == []
