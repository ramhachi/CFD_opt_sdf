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
        return {"observable": "total_cl", "downforce": d, "drag": drag,
                "batches": [{"downforce": d, "drag": drag} for _ in range(8)]}
    rows = []
    for re in (1000, 3000):
        for j in (1, 2, 3):
            for phase in range(16):
                rows.append(dict(configuration=f"E{j}", height_mm=100, reynolds=re,
                    grid="main", phase=str(phase), role="primary", ok=True, finite=True,
                    complete=True, observable="total_cl", scene_sha256=str(j) * 64,
                    readouts=dict(cur=force(j, phase), nds=None, cv=None)))
    for j in (1, 2):
        for phase in range(4):
            rows.append(dict(configuration=f"E{j}", height_mm=100, reynolds=3000,
                grid="confirmation", phase=str(phase), role="confirmation", ok=True, finite=True,
                complete=True, observable="total_cl", scene_sha256=str(j + 3) * 64,
                readouts=dict(cur=force(j, phase), nds=None, cv=None)))
    realizations = []
    for i in range(8):
        names = ("E1", "E2", "E3", "E1_sharp", "E2_sharp")
        realizations.append(dict(id=str(i), mesh_sha256={c: f"{i + 1:064x}" for c in names},
            status={c: "SETTLED" for c in names}, forces={
                c: {"observable": "pressure_cl" if c.endswith("_sharp") else "total_cl", "downforce": int(c[1]) + i * .0001 * int(c[1]),
                    "drag": .1 * int(c[1]) + i * .00001 * int(c[1])} for c in names}))
    return dict(schema="topo2d00-input-v1", identity_valid=True, cap_hit=False, waterlily=rows,
        rans=dict(schema="topo2d00-rans-results-v1", coefficient_reference=dict(chord_mm=223.4, height_mm=100, h_over_c1=100 / 223.4, h_over_c=100 / 380.),
                  reference=dict(delta_cl=1., digitizing_uncertainty=.01, observable="pressure_cl"),
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


@pytest.mark.parametrize("resolved13", [False, True], ids=["review-hprime", "opposite-resolved-13"])
@pytest.mark.parametrize("e2", [-1., 3.], ids=["E2-worst", "E2-best"])
def test_checker_amendment7_orders_only_resolved_required_pairs(resolved13, e2):
    data = planted()
    for row in data["waterlily"]:
        value = {"E1": 1., "E2": e2,
                 "E3": 1.2 if resolved13 else 1.0001 + (int(row["phase"]) - 7.5) * .0001}[row["configuration"]]
        force = row["readouts"]["cur"]
        force["downforce"] = value
        for batch in force["batches"]:
            batch["downforce"] = value
    for i, row in enumerate(data["rans"]["cells"][0]["realisations"]):
        for config, value in (("E1", 1.), ("E2", e2),
                              ("E3", .8 if resolved13 else .9995 + (i - 3.5) * .0044)):
            row["forces"][config]["downforce"] = value
    result = C.check(data)
    assert result["label"] == ("DISCORDANT" if resolved13 else "UNRESOLVED")
    for re in ("1000", "3000"):
        assert result["agreement"][re]["required_pairs"] == ["12", "23", "13"]
        assert result["agreement"][re]["state"] == result["label"]
        assert result["agreement"][re]["SIGN_AGREE_12"]
        assert not result["agreement"][re]["RANK_AGREE"]
        assert C.resolved(result["waterlily"][re]["13"]["downforce"]) is resolved13
    assert C.resolved(result["rans"]["SA/fine30"]["13"]["downforce"]) is resolved13


@pytest.mark.parametrize("problem", ["incomplete", "timeout", "missing_readout", "single_phase", "unpaired", "missing_primary"])
def test_checker_amendment7_unavailable_domain_is_not_judged(problem):
    data = planted()
    domain = []
    for row in data["waterlily"]:
        if row["role"] == "primary" and row["reynolds"] == 3000 and row["configuration"] in ("E1", "E2") and row["phase"] in ("0", "1"):
            value = deepcopy(row)
            value["role"] = "domain"
            domain.append(value)
    if problem == "incomplete":
        domain[0]["complete"] = False
    elif problem == "timeout":
        domain[0].update(complete=False, ok=False, readouts=dict(cur=None, nds=None, cv=None))
    elif problem == "missing_readout":
        domain[0]["readouts"]["cur"] = None
    elif problem == "single_phase":
        domain = [r for r in domain if r["phase"] == "0"]
    elif problem == "unpaired":
        domain.pop()
    else:
        for row in domain:
            row["phase"] = str(int(row["phase"]) + 16)
    data["waterlily"].extend(domain)
    result = C.check(data)
    assert result["label"] == "CONCORDANT"
    assert result["controls"]["domain"] == dict(status="DOMAIN_NOT_JUDGED", z=None)


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


@pytest.mark.parametrize("states,expected", [
    (("SETTLED", "NUMERICAL"), "NUMERICAL"),
    (("SETTLED", "MESH_FAILED"), "MESH_FAILED"),
    (("SETTLED", "INCOMPLETE"), "INCOMPLETE"),
    (("NUMERICAL", "MESH_FAILED"), "MESH_FAILED"),
    (("NUMERICAL", "INCOMPLETE"), "INCOMPLETE"),
    (("MESH_FAILED", "INCOMPLETE"), "INCOMPLETE"),
])
@pytest.mark.parametrize("arm", ["E3", "E1_sharp"])
def test_checker_amendment3_severity_from_raw_realisation_states(states, expected, arm):
    data = planted()
    for row, state in zip(data["rans"]["cells"][0]["realisations"], states):
        row["status"][arm] = state
        if state != "SETTLED":
            row["forces"][arm] = row["mesh_sha256"][arm] = None
    result = C.check(data)
    assert result["rans_diagnostics"]["SA/fine30"][arm]["status"] == expected
    if arm.endswith("_sharp"):
        assert result["label"] == "TR_UNQUALIFIED"
        assert result["tr00"]["cells"]["SA/fine30"]["label"] == expected
    else:
        assert result["label"] == ("NUMERICAL" if expected in ("NUMERICAL", "MESH_FAILED") else "INCOMPLETE")
    data["rans"]["cells"][0]["realisations"].reverse()
    assert C.compare(result, C.check(data)) == []


@pytest.mark.parametrize("incomplete_source", ["cap", "waterlily", "rans"])
def test_checker_study_numeric_precedes_cap_or_required_incomplete(incomplete_source):
    data = planted()
    data["waterlily"][0].update(ok=False, finite=False, complete=False,
                               readouts={name: None for name in ("cur", "nds", "cv")})
    assert C.check(data)["label"] == "NUMERICAL"
    if incomplete_source == "cap":
        data["cap_hit"] = True
    elif incomplete_source == "waterlily":
        data["waterlily"][1].update(ok=False, complete=False)
    else:
        row = data["rans"]["cells"][0]["realisations"][0]
        row["status"]["E2"] = "INCOMPLETE"
        row["forces"]["E2"] = row["mesh_sha256"]["E2"] = None
    assert C.check(data)["label"] == "NUMERICAL"


@pytest.mark.parametrize("arm", ["E3", "E1_sharp"])
@pytest.mark.parametrize("failure", ["NUMERICAL", "MESH_FAILED"])
def test_checker_duplicate_meshes_outrank_retained_failed_run_diagnostics(arm, failure):
    data = planted()
    cell = data["rans"]["cells"][0]
    for row in cell["realisations"]:
        row["mesh_sha256"][arm] = "b" * 64
    cell["realisations"][0]["status"][arm] = failure
    result = C.check(data)
    assert result["label"] == ("TR_UNQUALIFIED" if arm.endswith("_sharp") else "INCOMPLETE")
    diagnostic = result["rans_diagnostics"]["SA/fine30"][arm]
    assert diagnostic["status"] == "DEGENERATE_REALISATIONS"
    assert diagnostic["distinct_meshes"] == 1
    assert diagnostic["point_estimate"] is not None and diagnostic["ci90"] is None
    if arm.endswith("_sharp"):
        assert result["tr00"]["cells"]["SA/fine30"]["label"] == "INCOMPLETE"


@pytest.mark.parametrize("target", ["waterlily", "readout", "main", "sharp", "reference"])
def test_checker_rejects_observable_mismatch_independently(target):
    data = planted()
    if target == "waterlily":
        data["waterlily"][0]["observable"] = "pressure_cl"
    elif target == "readout":
        data["waterlily"][0]["readouts"]["cur"]["observable"] = "pressure_cl"
    elif target == "reference":
        data["rans"]["reference"]["observable"] = "total_cl"
    else:
        force = data["rans"]["cells"][0]["realisations"][0]["forces"]["E1" if target == "main" else "E1_sharp"]
        force["observable"] = "pressure_cl" if target == "main" else "total_cl"
    with pytest.raises(ValueError, match="observable"):
        C.check(data)


@pytest.mark.parametrize("config,expected", [("E3", "INCOMPLETE"), ("E1_sharp", "TR_UNQUALIFIED")])
def test_checker_refuses_duplicate_mesh_intervals(config, expected):
    data = planted()
    for row in data["rans"]["cells"][0]["realisations"]:
        row["mesh_sha256"][config] = "b" * 64
    result = C.check(data)
    assert result["label"] == expected
    diagnostic = result["rans_diagnostics"]["SA/fine30"][config]
    assert diagnostic["status"] == "DEGENERATE_REALISATIONS"
    assert diagnostic["point_estimate"] is not None and diagnostic["ci90"] is None


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


@pytest.mark.parametrize("zero_side", ["waterlily", "rans", "both"])
def test_zero_baseline_does_not_block_reported_only_retention(zero_side):
    data = planted()
    if zero_side in ("waterlily", "both"):
        for row in data["waterlily"]:
            if row["configuration"] == "E1":
                row["readouts"]["cur"]["downforce"] = 0.
                for batch in row["readouts"]["cur"]["batches"]:
                    batch["downforce"] = 0.
    if zero_side in ("rans", "both"):
        for cell in data["rans"]["cells"]:
            for row in cell["realisations"]:
                row["forces"]["E1"]["downforce"] = 0.
    result = C.check(data)
    assert result["label"] == "CONCORDANT"
    retention = result["agreement"]["1000"]["cells"]["SA/fine30"]["RETENTION_12"]
    assert retention["fieller"] == {"kind": "undefined_zero_baseline", "intervals": []}
    assert (retention["relative_w"] is None) == (zero_side in ("waterlily", "both"))
    assert (retention["relative_r"] is None) == (zero_side in ("rans", "both"))
    # Both calculations stay independent; compare only their public output.
    spec = importlib.util.spec_from_file_location(
        "topo_zero_baseline_comparison", ROOT / "scripts/topo2d00/analyze.py")
    analyzer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(analyzer)
    assert C.compare(analyzer.analyze_input(data), result) == []


@pytest.mark.parametrize("case,expected", [
    ("concordant", "CONCORDANT"), ("invalid", "INVALID"),
    ("incomplete", "INCOMPLETE"), ("tr_unqualified", "TR_UNQUALIFIED"),
    ("numerical", "NUMERICAL"), ("resolution", "RESOLUTION_LIMITED"),
    ("control_numerical", "NUMERICAL"), ("numerical_partial", "NUMERICAL"),
    ("unresolved", "UNRESOLVED"), ("discordant", "DISCORDANT"),
    ("partial", "CONCORDANT_PARTIAL"),
    ("sign_only", "CONCORDANT"), ("adopted_nds", "CONCORDANT"),
    ("drag_unresolved_ratio", "CONCORDANT"), ("drag_unresolved_sign", "CONCORDANT"),
    ("degenerate_main", "INCOMPLETE"), ("degenerate_sharp", "TR_UNQUALIFIED"),
    ("mesh_failed", "NUMERICAL"),
    ("numeric_with_cap", "NUMERICAL"),
    ("mixed_main_states", "INCOMPLETE"), ("mixed_sharp_states", "TR_UNQUALIFIED"),
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
    elif case == "partial":
        for row in data["waterlily"]:
            if row["configuration"] == "E2" and row["reynolds"] == 1000:
                row["readouts"]["cur"]["downforce"] -= 3
                for batch in row["readouts"]["cur"]["batches"]:
                    batch["downforce"] -= 3
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
    elif case.startswith("degenerate_"):
        config = "E3" if case == "degenerate_main" else "E1_sharp"
        for row in data["rans"]["cells"][0]["realisations"]:
            row["mesh_sha256"][config] = "b" * 64
    elif case == "mesh_failed":
        row = data["rans"]["cells"][0]["realisations"][0]
        row["status"]["E3"] = "MESH_FAILED"
        row["forces"]["E3"] = row["mesh_sha256"]["E3"] = None
    elif case == "numeric_with_cap":
        data["cap_hit"] = True
        data["waterlily"][0].update(ok=False, finite=False, complete=False,
                                   readouts={name: None for name in ("cur", "nds", "cv")})
    elif case in ("mixed_main_states", "mixed_sharp_states"):
        arm = "E3" if case == "mixed_main_states" else "E1_sharp"
        for row, status in zip(data["rans"]["cells"][0]["realisations"],
                               ("NUMERICAL", "MESH_FAILED", "INCOMPLETE")):
            row["status"][arm] = status
            row["forces"][arm] = row["mesh_sha256"][arm] = None
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
