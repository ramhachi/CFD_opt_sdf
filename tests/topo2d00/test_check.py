"""Planted truth for the independent implementation, without analyzer imports."""
import ast
from copy import deepcopy
import importlib.util
from pathlib import Path

import pytest
from scipy.stats import t

ROOT = Path(__file__).resolve().parents[2]
PATH = ROOT / "scripts/topo2d00/check.py"
SPEC = importlib.util.spec_from_file_location("topo_independent_check", PATH)
C = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(C)


def planted():
    def force(j, phase):
        d = j + (phase - 7) * (.0001 * j)
        drag = .1 * j + (phase - 7) * .00001 * j
        return {"downforce": d, "drag": drag,
                "batches": [{"downforce": d, "drag": drag} for _ in range(8)]}
    rows = []
    for re in (1000, 3000):
        for j in (1, 2, 3):
            for phase in range(16):
                rows.append(dict(configuration=f"E{j}", height_mm=100, reynolds=re,
                    grid="main", phase=str(phase), role="primary", ok=True, finite=True,
                    complete=True, scene_sha256=str(j) * 64,
                    readouts=dict(cur=force(j, phase), nds=None, cv=None)))
    for j in (1, 2):
        for phase in range(4):
            rows.append(dict(configuration=f"E{j}", height_mm=100, reynolds=3000,
                grid="confirmation", phase=str(phase), role="confirmation", ok=True, finite=True,
                complete=True, scene_sha256=str(j + 3) * 64,
                readouts=dict(cur=force(j, phase), nds=None, cv=None)))
    realizations = []
    for i in range(8):
        names = ("E1", "E2", "E3", "E1_sharp", "E2_sharp")
        realizations.append(dict(id=str(i), mesh_sha256={c: "a" * 64 for c in names},
            status={c: "SETTLED" for c in names}, forces={
                c: {"downforce": int(c[1]) + i * .0001 * int(c[1]),
                    "drag": .1 * int(c[1]) + i * .00001 * int(c[1])} for c in names}))
    return dict(schema="topo2d00-input-v1", identity_valid=True, cap_hit=False, waterlily=rows,
        rans=dict(schema="topo2d00-rans-results-v1", coefficient_reference=dict(chord_mm=223.4),
                  reference=dict(delta_cl=1., digitizing_uncertainty=.01),
                  cells=[dict(model="SA", family="fine30", realisations=realizations)]), controls={})


def test_checker_planted_force_table_and_detected_tampering():
    value = C.check(planted())
    assert value["label"] == "CONCORDANT"
    assert value["tr00"]["qualified_cells"] == ["SA/fine30"]
    assert value["waterlily"]["1000"]["12"]["downforce"]["mean"] == pytest.approx(1.00005)
    modified = deepcopy(value)
    modified["waterlily"]["1000"]["12"]["downforce"]["mean"] += .2
    differences = C.compare(value, modified)
    assert len(differences) == 1
    assert differences[0].startswith("waterlily.1000.12.downforce.mean:")


def test_checker_priority_and_missing_input():
    value = planted()
    value["identity_valid"] = False
    value["cap_hit"] = True
    assert C.check(value)["label"] == "INVALID"
    value = planted()
    value["waterlily"][0]["finite"] = False
    assert C.check(value)["label"] == "NUMERICAL"
    value["cap_hit"] = True
    assert C.check(value)["label"] == "NUMERICAL"
    value["waterlily"][0]["finite"] = True
    assert C.check(value)["label"] == "INCOMPLETE"
    value = planted()
    value["waterlily"].pop(0)
    with pytest.raises(ValueError, match="16 common"):
        C.check(value)
    value = planted()
    value["waterlily"][0]["readouts"]["cur"]["downforce"] += .1
    with pytest.raises(ValueError, match="batch means"):
        C.check(value)


def test_independent_checker_has_no_analyzer_import_or_dynamic_source_load():
    tree = ast.parse(PATH.read_text())
    modules = [n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
    modules += [alias.name for n in ast.walk(tree) if isinstance(n, ast.Import) for alias in n.names]
    assert not any(name and ("analyze" in name or "screen01" in name) for name in modules)
    assert "importlib" not in modules


def test_fieller_confidence_sets_include_unbounded_cases():
    bounded = C.fieller(2., 1., .01, .01, 7)
    assert bounded["kind"] == "bounded"
    assert bounded["intervals"][0][0] < 2 < bounded["intervals"][0][1]
    assert C.fieller(0., 0., 1., 1., 7)["kind"] == "all_real"
    disjoint = C.fieller(1., 0., .01, 1., 7)
    assert disjoint["kind"] == "disjoint"
    assert disjoint["intervals"][0][0] is None and disjoint["intervals"][1][1] is None
    assert C.fieller(1., 0., 0., 0., 7) == {"kind": "empty", "intervals": []}
    q = float(t.ppf(.95, 7)) ** 2
    half = C.fieller(2., 1., .01, 1 / q, 7)
    assert half["kind"] == "half_line"
    with pytest.raises(ValueError, match="covariance"):
        C.fieller(1., 1., .01, .01, 7, covariance=1.)


def test_fieller_covariance_validity_is_independent_of_coefficient_units():
    # A covariance larger than sqrt(vu*vv) is impossible at every scale.
    for variance, covariance in ((0., 1e-8), (1e-12, 2e-12),
                                 (1e-160, 2e-160), (0., 1e-170)):
        with pytest.raises(ValueError, match="covariance"):
            C.fieller(1e-5, 1e-5, variance, variance, 7, covariance=covariance)
    assert C.fieller(1e-5, 1e-5, 1e-12, 1e-12, 7,
                     covariance=1e-12)["kind"] == "bounded"


@pytest.mark.parametrize("case,expected", [
    ("concordant", "CONCORDANT"), ("invalid", "INVALID"),
    ("incomplete", "INCOMPLETE"), ("tr_unqualified", "TR_UNQUALIFIED"),
    ("numerical", "NUMERICAL"), ("resolution", "RESOLUTION_LIMITED"),
    ("control_numerical", "NUMERICAL"), ("numerical_partial", "NUMERICAL"),
    ("unresolved", "UNRESOLVED"), ("discordant", "DISCORDANT"),
    ("sign_only", "CONCORDANT"), ("adopted_nds", "CONCORDANT"),
    ("drag_unresolved_ratio", "CONCORDANT"), ("drag_unresolved_sign", "CONCORDANT"),
])
def test_independent_implementations_agree_on_force_tables(case, expected):
    # Importing both at the comparison boundary shares no implementation code.
    # Each implementation was written against the common design independently.
    spec = importlib.util.spec_from_file_location("topo_analyzer_comparison", ROOT / "scripts/topo2d00/analyze.py")
    analyzer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(analyzer)
    data = planted()
    if case == "invalid":
        data["identity_valid"] = False
    elif case == "incomplete":
        data["cap_hit"] = True
    elif case == "tr_unqualified":
        data["rans"]["reference"]["delta_cl"] = -1
    elif case == "numerical":
        data["waterlily"][0]["finite"] = False
    elif case in ("control_numerical", "numerical_partial"):
        failure = deepcopy(data["waterlily"][0])
        failure.update(ok=False, finite=False, complete=False,
                       readouts={"cur": None, "nds": None, "cv": None})
        if case == "control_numerical":
            failure["role"] = "secondary"
            failure["height_mm"] = 80
            data["waterlily"].append(failure)
        else:
            data["waterlily"] = [failure]
    elif case == "resolution":
        for row in data["waterlily"]:
            if row["role"] == "confirmation" and row["configuration"] == "E2":
                row["readouts"]["cur"]["downforce"] *= 2
                for b in row["readouts"]["cur"]["batches"]:
                    b["downforce"] *= 2
    elif case in ("unresolved", "discordant"):
        level = 2. if case == "unresolved" else 1.5
        for row in data["waterlily"]:
            if row["configuration"] == "E3":
                row["readouts"]["cur"]["downforce"] = level
                for b in row["readouts"]["cur"]["batches"]:
                    b["downforce"] = level
    elif case in ("sign_only", "drag_unresolved_sign"):
        data["rans"]["reference"].update(delta_cl=.1, digitizing_uncertainty=.01)
    elif case == "adopted_nds":
        data["controls"]["primary_readout"] = "nds"
        for row in data["waterlily"]:
            row["readouts"]["nds"] = deepcopy(row["readouts"]["cur"])
            # Different from cur: catches implementations that ignore adoption.
            row["readouts"]["nds"]["downforce"] *= 1.1
            for b in row["readouts"]["nds"]["batches"]:
                b["downforce"] *= 1.1
    if case.startswith("drag_unresolved_"):
        for row in data["waterlily"]:
            row["readouts"]["cur"]["drag"] = .1
            for b in row["readouts"]["cur"]["batches"]:
                b["drag"] = .1
        for cell in data["rans"]["cells"]:
            for realization in cell["realisations"]:
                for force in realization["forces"].values():
                    force["drag"] = .1
    independently_computed = C.check(data)
    analyzed = analyzer.analyze_input(data)
    assert independently_computed["label"] == expected
    assert C.compare(analyzed, independently_computed) == []
    if case.startswith("drag_unresolved_"):
        assert independently_computed["agreement"]["1000"]["DRAG_SIGN_AGREE_12"] is False
