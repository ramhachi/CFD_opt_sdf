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
    lo, hi = (40_000, 120_000) if mesh_for(model) == "wr2" else (8_000, 40_000)
    assert lo < s["cells_3d"] < hi
    fa = s["first_cell_airfoil_m"]
    assert fa["median"] == pytest.approx(spec["y1"], rel=0.01) and fa["p05"] > 0.95 * spec["y1"] and fa["p95"] < 1.10 * spec["y1"]
    assert s["first_cell_ground_m"]["median"] == pytest.approx(spec["y1"], rel=0.01)
    assert s["gap_cells_at_lowest_point"] >= 15
    assert man["h_m"] == pytest.approx(h * T.CHORD, abs=1e-12)
    assert abs(s["airfoil_node_min_y_m"] - man["h_m"]) < 1e-6                        # no mesh node on the airfoil lower than the ride height
    assert s["n_layers"] <= s["n_layers_spec"] and s["bl_thickness_m"] <= 0.4 * man["h_m"] + 1e-12


def test_wall_resolved_first_cell_y_plus_estimate():
    # flat-plate estimate (Cf = 0.006 is generous for Re_c 4.6e5): y+ = y1 u_tau / nu with u_tau = U sqrt(Cf/2)
    for name in ("wrc", "wr2"):
        assert T.MESHES[name]["y1"] * T.U_INF * math.sqrt(0.003) / T.NU < 1.2


def test_dictionaries_are_deterministic_and_the_mesh_is_stable_within_a_percent(tmp_path, cases):
    # gmsh's boundary-layer path is not bit-reproducible (documented in t20_case.py): everything except mesh.msh and the mesh part of the manifest must be.
    T.write_case(tmp_path / "again", 0.134, "sa-wf", "med30")
    first, man = cases[(0.134, "sa-wf")]
    again = json.loads((tmp_path / "again/case_manifest.json").read_text())
    names = sorted(str(p.relative_to(first)) for p in first.rglob("*") if p.is_file())
    assert names == sorted(str(p.relative_to(tmp_path / "again")) for p in (tmp_path / "again").rglob("*") if p.is_file())
    assert all((first / n).read_bytes() == (tmp_path / "again" / n).read_bytes() for n in names if n not in ("mesh.msh", "case_manifest.json"))
    drop = lambda d: {k: v for k, v in d.items() if k not in ("mesh_stats", "mesh_msh_sha256")}
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
    assert f"model {T.MODELS[model]['foam']};" in turb
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
