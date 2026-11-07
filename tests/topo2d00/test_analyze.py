"""Synthetic numerical/contract tests; no solver or physical qualification."""
import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest
from scipy.stats import t

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


A = load(ROOT / "scripts/topo2d00/analyze.py", "topo_analyze")
S = load(HERE / "synthetic.py", "topo_synthetic")


def test_paired_statistics_and_bounded_retention():
    result = A.analyze_input(S.input_table())
    assert result["label"] == "CONCORDANT"
    stat = result["waterlily"]["1000"]["12"]["downforce"]
    assert stat["mean"] == pytest.approx(1)
    assert stat["sigma"] == max(stat["sigma_a"], stat["sigma_b"])
    assert stat["se"] == pytest.approx(stat["sigma"] / 4)
    assert not any("upper" in key for key in stat)
    assert stat["ci90"][0] < 1 < stat["ci90"][1]
    assert len(result["tr00"]["qualified_cells"]) == 4
    ratio = result["agreement"]["1000"]["cells"]["SA-WF/fine30"]["RETENTION_12"]
    assert ratio["fieller"]["kind"] == "bounded"
    assert ratio["relative_w"] == pytest.approx(1 / 1.2)
    assert result["controls"]["determinism"] == {"judged": True, "pass": True}


@pytest.mark.parametrize("target", ["waterlily", "readout", "main", "sharp", "reference"])
def test_observable_mismatch_is_refused_before_any_difference(target):
    data = S.input_table()
    if target == "waterlily":
        data["waterlily"][0]["observable"] = "pressure_cl"
    elif target == "readout":
        data["waterlily"][0]["readouts"]["cur"]["observable"] = "pressure_cl"
    elif target == "reference":
        data["rans"]["reference"]["observable"] = "total_cl"
    else:
        config = "E1" if target == "main" else "E1_sharp"
        data["rans"]["cells"][0]["realisations"][0]["forces"][config]["observable"] = "pressure_cl" if target == "main" else "total_cl"
    with pytest.raises(ValueError, match="observable"):
        A.analyze_input(data)


@pytest.mark.parametrize("arm,expected", [("E3", "INCOMPLETE"), ("E1_sharp", "TR_UNQUALIFIED")])
def test_duplicate_meshes_are_not_independent_realisations(arm, expected):
    data = S.input_table()
    for cell in data["rans"]["cells"]:
        for row in cell["realisations"]:
            row["mesh_sha256"][arm] = "b" * 64
    result = A.analyze_input(data)
    assert result["label"] == expected
    for cell in result["rans_diagnostics"].values():
        assert cell[arm]["status"] == "DEGENERATE_REALISATIONS"
        assert cell[arm]["distinct_meshes"] == 1
        assert cell[arm]["point_estimate"] is not None
        assert cell[arm]["ci90"] is None
    if arm.endswith("_sharp"):
        for cell in result["tr00"]["cells"].values():
            assert cell["label"] == "INCOMPLETE"
            assert cell["reason"] == "DEGENERATE_REALISATIONS"
            assert cell["delta"] is cell["ratio_ci90"] is None
            assert cell["point_estimate"] is not None


def test_height_normalizations_and_thickening_observable_limit_are_explicit():
    data = S.input_table()
    result = A.analyze_input(data)
    assert result["height"]["h_over_c1"] == pytest.approx(100 / 223.4)
    assert result["height"]["h_over_c"] == pytest.approx(100 / 380)
    record = result["thickening_alone"]["SA-WF/fine30"]["E2"]
    assert record["from"] == "E2_sharp" and record["to"] == "E2"
    assert all(r["status"] == "UNAVAILABLE" and r["point_estimate"] is None and r["paired_realisations"] == 0 for r in record["observables"].values())
    assert any("geometry and grid" in text for text in result["limitations"])
    data["rans"]["coefficient_reference"]["h_over_c"] = 100 / 223.4
    with pytest.raises(ValueError, match="h_over_c"):
        A.analyze_input(data)
    data = S.input_table()
    data["waterlily"][0]["h_over_c1"] = 100 / 380
    with pytest.raises(ValueError, match="h_over_c1"):
        A.analyze_input(data)


def test_rans_mesh_failure_remains_distinct_from_numerical():
    data = S.input_table()
    row = data["rans"]["cells"][0]["realisations"][0]
    row["status"]["E3"] = "MESH_FAILED"
    row["forces"]["E3"] = row["mesh_sha256"]["E3"] = None
    result = A.analyze_input(data)
    assert result["label"] == "NUMERICAL"
    assert result["rans_diagnostics"]["SA-WF/fine30"]["E3"]["status"] == "MESH_FAILED"


def test_thickening_recomputed_from_raw_same_observable_auxiliary_coefficients():
    payload = S.add_auxiliary_coefficients(S.input_table())
    # Precomputed collector summaries are untrusted, including plausible-looking values.
    payload["rans"]["cells"][0]["thickening_alone"] = [{"point_estimate": {"downforce": 999}}]
    analyzed = A.analyze_input(payload)
    checker = load(ROOT / "scripts/topo2d00/check.py", "topo_auxiliary_checker")
    assert checker.compare(analyzed, checker.check(payload)) == []
    assert analyzed["label"] == "CONCORDANT"
    for config in ("E1", "E2"):
        observed = analyzed["thickening_alone"]["SA-WF/fine30"][config]["observables"]
        for name, downforce, drag in (("pressure_cl", 3, .2), ("total_cl", 7, .4)):
            stat = observed[name]
            assert stat["status"] == "DESCRIPTIVE" and stat["paired_realisations"] == 8
            assert stat["point_estimate"] == pytest.approx({"downforce": downforce, "drag": drag})
            assert stat["ci90"]["downforce"] == pytest.approx([downforce, downforce])
    assert analyzed["thickening_alone"]["SA-WF/fine30"]["E3"]["status"] == "UNAVAILABLE_SHARP_ARM"


@pytest.mark.parametrize("failure", ["duplicate", "unusable", "status", "pressure_unsettled", "total_unsettled", "nonfinite", "missing"])
def test_thickening_auxiliary_failures_withhold_ci_and_do_not_change_label(failure):
    payload = S.add_auxiliary_coefficients(S.input_table())
    cell = payload["rans"]["cells"][0]
    raw = cell["realisations"][0]["diagnostics"]["E2_sharp"]
    if failure == "duplicate":
        for row in cell["realisations"]:
            row["mesh_sha256"]["E2_sharp"] = "b" * 64
            row["diagnostics"]["E2_sharp"]["mesh_msh_sha256"] = "b" * 64
    elif failure == "unusable":
        raw["usable"] = False
    elif failure == "status":
        raw["status"] = "SOLVER_DIVERGED"
    elif failure == "pressure_unsettled":
        raw["pressure_convergence"]["state"] = "not_settled"
    elif failure == "total_unsettled":
        raw["convergence"]["state"] = "not_settled"
    elif failure == "nonfinite":
        raw["pressure_coefficients"]["total"]["Cl"] = float("nan")
    else:
        raw.pop("pressure_coefficients")
    result = A.analyze_input(payload)
    checker = load(ROOT / "scripts/topo2d00/check.py", "topo_auxiliary_failure_checker")
    assert checker.compare(result, checker.check(payload)) == []
    assert result["label"] == "CONCORDANT"  # Other registered cells still qualify.
    stats = result["thickening_alone"]["SA-WF/fine30"]["E2"]["observables"]
    limited = ("total_cl",) if failure == "total_unsettled" else ("pressure_cl",) if failure in ("pressure_unsettled", "nonfinite", "missing") else ("pressure_cl", "total_cl")
    for name in limited:
        assert stats[name]["status"] == "POINT_ONLY" and stats[name]["ci90"] is None
        assert stats[name]["paired_realisations"] == (8 if failure == "duplicate" else 7)


def test_thickening_auxiliary_config_and_mesh_identity_are_bound():
    checker = load(ROOT / "scripts/topo2d00/check.py", "topo_auxiliary_identity_checker")
    payload = S.add_auxiliary_coefficients(S.input_table())
    payload["rans"]["cells"][0]["realisations"][0]["diagnostics"]["E1"]["mesh_msh_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="auxiliary RANS"):
        A.analyze_input(payload)
    with pytest.raises(ValueError, match="auxiliary RANS"):
        checker.check(payload)


@pytest.mark.parametrize("zero_side", ["waterlily", "rans", "both"])
def test_zero_baseline_only_undefines_descriptive_retention(zero_side):
    payload = S.input_table()
    if zero_side in ("waterlily", "both"):
        for config, downforce in (("E1", 0.0), ("E2", 1.0), ("E3", 2.0)):
            S.set_force(payload, config, downforce)
    if zero_side in ("rans", "both"):
        for cell in payload["rans"]["cells"]:
            for row in cell["realisations"]:
                for config, downforce in (("E1", 0.0), ("E2", 1.0), ("E3", 2.0)):
                    row["forces"][config]["downforce"] = downforce
    result = A.analyze_input(payload)
    assert result["label"] == "CONCORDANT"
    for reynolds in ("1000", "3000"):
        for cell in result["agreement"][reynolds]["cells"].values():
            retention = cell["RETENTION_12"]
            assert retention["fieller"] == {"kind": "undefined_zero_baseline", "intervals": []}
            for side, key in (("waterlily", "w"), ("rans", "r")):
                if zero_side in (side, "both"):
                    assert retention["relative_" + key] is None
                    assert retention["variance_" + key] is None
                else:
                    assert np.isfinite(retention["relative_" + key])
                    assert np.isfinite(retention["variance_" + key])
    json.dumps(result, allow_nan=False)


@pytest.mark.parametrize("label", ["INVALID", "TR_UNQUALIFIED", "NUMERICAL", "INCOMPLETE", "RESOLUTION_LIMITED", "UNRESOLVED", "DISCORDANT", "CONCORDANT_PARTIAL", "CONCORDANT"])
def test_all_reachable_labels(label):
    payload = S.input_table()
    if label == "INVALID":
        payload["identity_valid"] = False
    elif label == "TR_UNQUALIFIED":
        for cell in payload["rans"]["cells"]:
            for row in cell["realisations"]:
                row["forces"]["E2_sharp"]["downforce"] = 0
    elif label == "NUMERICAL":
        payload["waterlily"][0]["finite"] = False
        payload["waterlily"][0]["readouts"] = {key: None for key in ("cur", "nds", "cv")}
    elif label == "INCOMPLETE":
        payload["cap_hit"] = True
    elif label == "RESOLUTION_LIMITED":
        for row in payload["waterlily"]:
            if row["grid"] == "confirmation" and row["configuration"] == "E2":
                S.set_readout(row, "downforce", 0.5)
    elif label == "UNRESOLVED":
        S.set_force(payload, "E2", 1.2, re=1000)
        S.set_force(payload, "E1", 1.2, re=1000)
    elif label == "DISCORDANT":
        S.set_force(payload, "E2", 0.2)
    elif label == "CONCORDANT_PARTIAL":
        S.set_force(payload, "E2", 0.2, re=1000)
    assert A.analyze_input(payload)["label"] == label


@pytest.mark.parametrize("discordant_re", [1000, 3000])
def test_amendment5_partial_is_reachable_in_opus_counterexample_c(discordant_re):
    payload = S.input_table()
    S.set_force(payload, "E2", 0.2, re=discordant_re)
    result = A.analyze_input(payload)
    assert result["label"] == "CONCORDANT_PARTIAL"
    assert result["agreement"][str(discordant_re)]["state"] == "DISCORDANT"
    assert result["agreement"][str(4000 - discordant_re)]["state"] == "CONCORDANT"
    assert not result["agreement"][str(discordant_re)]["SIGN_AGREE_12"]
    checker = load(ROOT / "scripts/topo2d00/check.py", "topo_partial_checker")
    assert checker.compare(result, checker.check(payload)) == []
    assert not any("unreachable" in text for text in result["limitations"])


def test_unresolved_re_precedes_partial_concordance():
    payload = S.input_table()
    S.set_force(payload, "E2", 1.2, re=1000)
    S.set_force(payload, "E1", 1.2, re=1000)
    result = A.analyze_input(payload)
    assert result["label"] == "UNRESOLVED"
    assert result["agreement"]["1000"]["state"] == "UNRESOLVED"
    assert result["agreement"]["3000"]["state"] == "CONCORDANT"


def test_only_registered_12_23_intervals_are_required_by_amendment5():
    payload = S.input_table()
    for config, value in (("E1", 1.), ("E2", 3.), ("E3", 1.00001)):
        S.set_force(payload, config, value)
        for cell in payload["rans"]["cells"]:
            for row in cell["realisations"]:
                row["forces"][config]["downforce"] = value
    result = A.analyze_input(payload)
    assert result["label"] == "CONCORDANT"
    for re in ("1000", "3000"):
        # E1->E3 sorted-rank interval is unresolved in W; Amendment 5's
        # required list is fixed to 12/23. Keep this diagnostic visible.
        assert result["agreement"][re]["state"] == "CONCORDANT"
        assert not result["agreement"][re]["RANK_AGREE"]
    checker = load(ROOT / "scripts/topo2d00/check.py", "topo_fixed_required_intervals")
    assert checker.compare(result, checker.check(payload)) == []


def test_tr00_sign_only_threshold_and_ratio_failure():
    payload = S.input_table()
    payload["rans"]["reference"]["digitizing_uncertainty"] = 0.051
    result = A.analyze_input(payload)
    assert {v["label"] for v in result["tr00"]["cells"].values()} == {"TR00_PASS_SIGN"}
    payload["rans"]["reference"]["digitizing_uncertainty"] = 0.05
    payload["rans"]["reference"]["delta_cl"] = 0.1
    payload["rans"]["reference"]["digitizing_uncertainty"] = 0.005
    assert A.analyze_input(payload)["label"] == "TR_UNQUALIFIED"


def test_fieller_all_topologies_and_variance_refusal():
    assert A.fieller(1, 2, 0.01, 0.01)["kind"] == "bounded"
    assert A.fieller(1, 0, 0.01, 0.1)["kind"] == "disjoint"
    assert A.fieller(0, 0, 1, 1)["kind"] == "all_real"
    assert A.fieller(1, 0, 0.01, 0)["kind"] == "empty"
    assert A.fieller(1, 1, 0.01, 1 / t.ppf(0.95, 7) ** 2)["kind"] == "half_line"
    with pytest.raises(ValueError, match="variance"):
        A.fieller(1, 1, -1, 1)
    with pytest.raises(ValueError, match="variance"):
        A.fieller(1, 1, 1e-20, 1e-20, 1e-12)
    assert A.fieller(1e12, 1, 0, 0)["kind"] == "bounded"
    original = A.fieller(1, 0.2, 0.05, 0.03)
    scaled = A.fieller(1e-9, 0.2e-9, 0.05e-18, 0.03e-18)
    assert original["kind"] == scaled["kind"]
    for left, right in zip(original["intervals"], scaled["intervals"]):
        for a, b in zip(left, right):
            assert a == b if a is None else a == pytest.approx(b)


@pytest.mark.parametrize("variance_num,variance_den,covariance", [
    (1e-12, 1e-12, 2e-12), (0.0, 0.0, 1e-8),
    (1e-160, 1e-160, 2e-160), (0.0, 0.0, 1e-170),
])
def test_fieller_rejects_non_psd_covariance_independently_of_units(variance_num, variance_den, covariance):
    with pytest.raises(ValueError, match="variance/covariance"):
        A.fieller(1.0, 2.0, variance_num, variance_den, covariance)


@pytest.mark.parametrize("scale", [1.0, 1e-12, 1e-160, 1e-320])
@pytest.mark.parametrize("direction", [-1, 1])
def test_fieller_accepts_valid_covariance_boundary_across_units(scale, direction):
    result = A.fieller(1.0, 2.0, scale, scale, direction * scale)
    assert result["kind"] in {"bounded", "disjoint", "all_real", "empty", "half_line"}


def test_sigma_b_point_estimate_is_in_sd_units_and_t90_uses_p_minus_one():
    payload = S.input_table()
    base = [r for r in payload["waterlily"] if r["role"] == "primary" and r["reynolds"] == 1000 and r["configuration"] == "E1"]
    candidate = [r for r in payload["waterlily"] if r["role"] == "primary" and r["reynolds"] == 1000 and r["configuration"] == "E2"]
    stat = A.wstat(base, candidate)
    assert stat["sigma_a"] < 1e-15
    assert stat["sigma_b"] == pytest.approx(0.001 * np.sqrt(2 / 3))
    assert stat["sigma"] == stat["sigma_b"]
    assert stat["se"] == pytest.approx(stat["sigma"] / 4)
    assert stat["ci90"] == pytest.approx(1 + np.array([-1, 1]) * t.ppf(.95, 15) * stat["se"])
    assert not any("upper" in key for key in stat)


def test_domain_p2_detects_shift_above_three_point_pooled_standard_errors():
    payload = S.input_table()
    for row in list(payload["waterlily"]):
        if row["role"] == "primary" and row["reynolds"] == 3000 and row["configuration"] in ("E1", "E2") and row["phase"] in ("0", "1"):
            if row["configuration"] == "E2":
                jitter = -.1 if row["phase"] == "0" else .1
                S.set_readout(row, "downforce", row["readouts"]["cur"]["downforce"] + jitter)
            duplicate = json.loads(json.dumps(row))
            duplicate["role"] = "domain"
            if duplicate["configuration"] == "E2":
                S.set_readout(duplicate, "downforce", duplicate["readouts"]["cur"]["downforce"] + .5)
            payload["waterlily"].append(duplicate)
    result = A.analyze_input(payload)
    assert result["controls"]["domain"]["status"] == "DOMAIN_SENSITIVE"
    assert result["controls"]["domain"]["z"] == pytest.approx(.5 / np.sqrt(.02))
    checker = load(ROOT / "scripts/topo2d00/check.py", "topo_domain_checker")
    assert checker.compare(result, checker.check(payload)) == []


def test_controls_are_measured_or_explicitly_not_judged():
    payload = S.input_table()
    result = A.analyze_input(payload)
    assert result["controls"]["domain"] == {"status": "NOT_JUDGED", "z": None}
    assert result["controls"]["readout"]["1000"]["nds"] is None
    for row in list(payload["waterlily"]):
        if row["role"] == "primary" and row["reynolds"] == 3000 and row["configuration"] in ("E1", "E2") and row["phase"] in ("0", "1"):
            duplicate = json.loads(json.dumps(row))
            duplicate["role"] = "domain"
            if duplicate["configuration"] == "E2":
                S.set_readout(duplicate, "downforce", duplicate["readouts"]["cur"]["downforce"] + 0.5)
            payload["waterlily"].append(duplicate)
    assert A.analyze_input(payload)["controls"]["domain"]["status"] == "DOMAIN_SENSITIVE"
    repeated = next(r for r in payload["waterlily"] if r["role"] == "determinism")
    S.set_readout(repeated, "downforce", repeated["readouts"]["cur"]["downforce"] + 0.01)
    result = A.analyze_input(payload)
    assert result["controls"]["determinism"] == {"judged": True, "pass": False}
    assert result["label"] == "CONCORDANT"  # no invented control-to-label policy


def test_worst_cell_is_not_averaged_and_drag_sign_is_report_only():
    payload = S.input_table()
    for row in payload["rans"]["cells"][0]["realisations"]:
        row["forces"]["E3"]["downforce"] = 1.5
    result = A.analyze_input(payload)
    assert result["label"] == "DISCORDANT"
    assert not result["agreement"]["1000"]["RANK_AGREE"]
    payload = S.input_table()
    for row in payload["waterlily"]:
        if row["configuration"] == "E2":
            S.set_readout(row, "drag", 0.01)
    result = A.analyze_input(payload)
    assert not result["agreement"]["1000"]["DRAG_SIGN_AGREE_12"]
    assert result["label"] == "CONCORDANT"


@pytest.mark.parametrize("sign_only", [False, True])
def test_unresolved_drag_is_reported_without_adding_an_acceptance_gate(sign_only):
    payload = S.input_table()
    if sign_only:
        payload["rans"]["reference"]["digitizing_uncertainty"] = 0.051
    for row in payload["waterlily"]:
        S.set_readout(row, "drag", 0.0)
    for cell in payload["rans"]["cells"]:
        for row in cell["realisations"]:
            for config in ("E1", "E2", "E3"):
                row["forces"][config]["drag"] = 0.0
    result = A.analyze_input(payload)
    assert result["label"] == "CONCORDANT"
    for re in ("1000", "3000"):
        assert result["waterlily"][re]["12"]["drag"]["ci90"][0] < 0 < result["waterlily"][re]["12"]["drag"]["ci90"][1]
        assert not result["agreement"][re]["DRAG_SIGN_AGREE_12"]
        assert result["agreement"][re]["SIGN_AGREE_12"]
        assert result["agreement"][re]["RANK_AGREE"]


def test_study_numeric_precedes_cap_and_preserves_cell_outcomes():
    payload = S.input_table()
    payload["cap_hit"] = True
    payload["waterlily"][0]["finite"] = False
    assert A.analyze_input(payload)["label"] == "NUMERICAL"
    payload = S.input_table()
    row = payload["rans"]["cells"][0]["realisations"][0]
    row["status"]["E3"] = "INCOMPLETE"
    row["forces"]["E3"] = None
    row["mesh_sha256"]["E3"] = None
    assert A.analyze_input(payload)["label"] == "INCOMPLETE"
    row["status"]["E3"] = "NUMERICAL"
    assert A.analyze_input(payload)["label"] == "NUMERICAL"


@pytest.mark.parametrize("states,expected", [
    (("SETTLED", "NUMERICAL"), "NUMERICAL"),
    (("SETTLED", "MESH_FAILED"), "MESH_FAILED"),
    (("SETTLED", "INCOMPLETE"), "INCOMPLETE"),
    (("NUMERICAL", "MESH_FAILED"), "MESH_FAILED"),
    (("NUMERICAL", "INCOMPLETE"), "INCOMPLETE"),
    (("MESH_FAILED", "INCOMPLETE"), "INCOMPLETE"),
])
@pytest.mark.parametrize("arm", ["E3", "E1_sharp"])
def test_amendment3_cell_severity_is_independent_of_realisation_order(states, expected, arm):
    payload = S.input_table()
    for cell in payload["rans"]["cells"]:
        for row, state in zip(cell["realisations"], states):
            row["status"][arm] = state
            if state != "SETTLED":
                row["forces"][arm] = row["mesh_sha256"][arm] = None
    result = A.analyze_input(payload)
    for diagnostic in result["rans_diagnostics"].values():
        assert diagnostic[arm]["status"] == expected
    if arm.endswith("_sharp"):
        # The study's TR gate still precedes its scientific outcome labels.
        assert result["label"] == "TR_UNQUALIFIED"
        assert all(cell["label"] == expected for cell in result["tr00"]["cells"].values())
    else:
        assert result["label"] == ("NUMERICAL" if expected in ("NUMERICAL", "MESH_FAILED") else "INCOMPLETE")
    for cell in payload["rans"]["cells"]:
        cell["realisations"].reverse()
    reversed_result = A.analyze_input(payload)
    assert reversed_result["label"] == result["label"]
    for name in result["rans_diagnostics"]:
        assert reversed_result["rans_diagnostics"][name][arm]["status"] == expected
        assert reversed_result["tr00"]["cells"][name]["label"] == result["tr00"]["cells"][name]["label"]


@pytest.mark.parametrize("incomplete_source", ["cap", "waterlily", "rans"])
def test_study_numeric_precedes_independent_required_incomplete_state(incomplete_source):
    payload = S.input_table()
    failure = payload["waterlily"][0]
    failure.update(finite=False, ok=False, complete=False,
                   readouts={name: None for name in ("cur", "nds", "cv")})
    # A nonfinite run is NUMERICAL even though no complete window was recorded.
    assert A.analyze_input(payload)["label"] == "NUMERICAL"
    if incomplete_source == "cap":
        payload["cap_hit"] = True
    elif incomplete_source == "waterlily":
        payload["waterlily"][1].update(complete=False, ok=False)
    else:
        row = payload["rans"]["cells"][0]["realisations"][0]
        row["status"]["E2"] = "INCOMPLETE"
        row["forces"]["E2"] = row["mesh_sha256"]["E2"] = None
    assert A.analyze_input(payload)["label"] == "NUMERICAL"


@pytest.mark.parametrize("arm", ["E3", "E1_sharp"])
@pytest.mark.parametrize("failure", ["NUMERICAL", "MESH_FAILED"])
def test_degenerate_realisations_remain_incomplete_with_retained_failure_diagnostics(arm, failure):
    payload = S.input_table()
    for cell in payload["rans"]["cells"]:
        for row in cell["realisations"]:
            row["mesh_sha256"][arm] = "b" * 64
        # An unsuccessful run may legitimately retain finite diagnostic forces
        # and its mesh SHA. Those do not restore eight distinct realisations.
        cell["realisations"][0]["status"][arm] = failure
    result = A.analyze_input(payload)
    assert result["label"] == ("TR_UNQUALIFIED" if arm.endswith("_sharp") else "INCOMPLETE")
    for diagnostic in result["rans_diagnostics"].values():
        assert diagnostic[arm]["status"] == "DEGENERATE_REALISATIONS"
        assert diagnostic[arm]["distinct_meshes"] == 1
        assert diagnostic[arm]["point_estimate"] is not None and diagnostic[arm]["ci90"] is None
    if arm.endswith("_sharp"):
        assert all(cell["label"] == "INCOMPLETE" for cell in result["tr00"]["cells"].values())


def test_smoke_formal_input_is_rejected_without_trusting_success_flags(tmp_path):
    from cfd_harness import campaign_schema as sc
    freeze = tmp_path / "freeze.json"
    freeze.write_text(json.dumps({"schema": "topo2d00-analysis-freeze-v1", "source_commit": "a" * 40,
                                "cap_hit": False, "primary_readout": "cur", "height_mm": 100,
                                "sources": {"README.md": "a" * 64}, "inputs": {}}))
    Path(str(freeze) + ".sha256").write_text(A.sha256(freeze))
    table = tmp_path / "table.json"
    table.write_text(json.dumps({"kind": sc.TABLE_KIND, "harness_version": sc.HARNESS_VERSION,
                                "smoke": True, "integrity": {"pass": True, "failures": []}}))
    with pytest.raises(ValueError, match="smoke or unverified"):
        A.load_formal_inputs([table], tmp_path / "rans.json", freeze)


def test_missing_phase_duplicate_unknown_and_nonfinite_fail_closed():
    payload = S.input_table()
    payload["waterlily"].pop(0)
    with pytest.raises(ValueError, match="phase|16"):
        A.analyze_input(payload)
    payload = S.input_table()
    payload["waterlily"].append(payload["waterlily"][0])
    with pytest.raises(ValueError, match="duplicate"):
        A.analyze_input(payload)
    payload = S.input_table()
    payload["waterlily"][0]["role"] = "unknown"
    with pytest.raises(ValueError, match="role"):
        A.analyze_input(payload)
    payload = S.input_table()
    payload["waterlily"][0]["readouts"]["cur"]["downforce"] = float("nan")
    with pytest.raises(ValueError, match="finite"):
        A.analyze_input(payload)


def test_write_once_checks_both_targets_before_mutation(tmp_path):
    result = A.analyze_input(S.input_table())
    A.write_analysis(tmp_path, {"input": S.input_table(), "result": result, "provenance": {"synthetic": True}})
    with pytest.raises(FileExistsError):
        A.write_analysis(tmp_path, {})
    assert json.loads((tmp_path / "analysis.json").read_text())["result"]["label"] == "CONCORDANT"
    other = tmp_path / "other"
    other.mkdir()
    (other / "analysis.md").write_text("existing")
    with pytest.raises(FileExistsError):
        A.write_analysis(other, {})
    assert not (other / "analysis.json").exists()


def test_registered_outputs_are_exclusive_and_hash_all_three_artifacts(tmp_path):
    record = {"input": S.input_table(), "result": A.analyze_input(S.input_table()), "provenance": {"synthetic": True}}
    A.write_analysis(tmp_path, record)
    assert json.loads((tmp_path / "tr00.json").read_text()) == record["result"]["tr00"]
    lines = (tmp_path / "SHA256SUMS").read_text().splitlines()
    assert {line.split("  ", 1)[1] for line in lines} == {"analysis.json", "analysis.md", "tr00.json"}
    for line in lines:
        digest, name = line.split("  ", 1)
        assert digest == A.sha256(tmp_path / name)
    for name in ("analysis.json", "analysis.md", "tr00.json", "SHA256SUMS"):
        target = tmp_path / name
        isolated = tmp_path / ("existing_" + name.replace(".", "_"))
        isolated.mkdir()
        (isolated / name).write_bytes(target.read_bytes())
        before = {p.name: p.read_bytes() for p in isolated.iterdir()}
        with pytest.raises(FileExistsError):
            A.write_analysis(isolated, record)
        assert {p.name: p.read_bytes() for p in isolated.iterdir()} == before


def test_rans_schema_rejects_ambiguous_units_and_wrong_count():
    payload = S.input_table()
    payload["rans"]["coefficient_reference"]["chord_mm"] = 380
    with pytest.raises(ValueError, match="223.4"):
        A.analyze_input(payload)
    payload = S.input_table()
    payload["rans"]["cells"][0]["realisations"].pop()
    with pytest.raises(ValueError, match="8"):
        A.analyze_input(payload)


@pytest.fixture
def formal_boundary(tmp_path, monkeypatch):
    """Mock the external harness boundary, not the numerical analyzer.

    These are source/manifest contract fixtures; they are never CFD evidence.
    The verifier's raw result and the supplied success table are independent.
    """
    from copy import deepcopy
    from cfd_harness import campaign_schema as sc, scene_campaign
    commit = "b" * 40
    source_names = ("scripts/topo2d00/analyze.py", "scripts/topo2d00/check.py",
                    "scripts/waterlily_topo2d_job.jl", "src/cfd_gen/topo2d/geometry.py")
    sources = {}
    for name in source_names:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("synthetic source identity: " + name)
        sources[name] = A.sha256(path)
    monkeypatch.setattr(A, "REPO", tmp_path)

    def source_read(command, **kwargs):
        assert command[:2] == ["git", "show"]
        assert command[2].startswith(commit + ":")
        return (tmp_path / command[2].split(":", 1)[1]).read_bytes()
    monkeypatch.setattr(A.subprocess, "check_output", source_read)
    geometry = {}
    for name in A.RCONFIGS:
        path = tmp_path / (name + ".json")
        path.write_text(json.dumps({"schema": "topo2d-scene-v1", "synthetic_geometry": name,
                                    "sources": [{"verification": "VERIFIED_SYNTHETIC"}]}))
        geometry[name] = A.sha256(path)
    payload = S.input_table()
    payload["rans"]["provenance"] = {
        "geometry_sha256": geometry.copy(),
        "component_by_config": {c: "pressure_only" if c.endswith("_sharp") else "pressure_plus_viscous" for c in A.RCONFIGS}}
    bundle = S.write_reference_bundle(tmp_path)
    digitization_records = bundle["artifacts"]
    payload["rans"]["provenance"]["reference_estimate"] = {
        "kind": "topo2d00_pressure_reference_v1", "observable": "pressure_cl",
        "manifest": {key: bundle["manifest"][key] for key in ("path", "sha256")}}
    payload["rans"]["reference"]["source"] = {
        "observable": "centre-section pressure-integrated Cl", "title": "Synthetic test only",
        "url": "https://example.invalid/synthetic", "pages": "Table15 and Cp figures",
        "method": "Synthetic E1 Table15 extraction and E2 Cp integration; no measured data",
        "digitization_records": digitization_records}
    rows = {}
    for i, row in enumerate(payload["waterlily"]):
        topo_keys = ("configuration", "height_mm", "reynolds", "grid", "phase", "role")
        row["scene_sha256"] = geometry[row["configuration"]] if row["grid"] == "main" else "c" * 64
        rows[str(i)] = {"topo2d": {key: row[key] for key in topo_keys},
                        **{key: row[key] for key in ("ok", "finite", "complete", "scene_sha256", "readouts", "observable")}}
    table_value = {"kind": sc.TABLE_KIND, "harness_version": sc.HARNESS_VERSION,
                   "smoke": False, "integrity": {"pass": True, "failures": []},
                   "force_unit": "N/m", "source_commit": commit, "state_forces_n": {"kernel": rows}}
    table_path, rans_path, freeze_path = [tmp_path / name for name in ("table.json", "rans.json", "study_freeze.json")]
    table_path.write_text(json.dumps(table_value))
    rans_path.write_text(json.dumps(payload["rans"]))
    for name in ("campaign.json", "harness_freeze.json"):
        (tmp_path / name).write_text("{}")
    freeze = {"schema": "topo2d00-analysis-freeze-v1", "source_commit": commit,
              "cap_hit": False, "primary_readout": "cur", "height_mm": 100,
              "sources": sources, "geometry_sha256": geometry,
              "inputs": {name: A.sha256(tmp_path / name) for name in
                         ("table.json", "rans.json", "campaign.json", "harness_freeze.json") + tuple(c + ".json" for c in A.RCONFIGS)},
              "harness": [{"table": "table.json", "campaign": "campaign.json",
                           "freeze": "harness_freeze.json", "outputs": ["raw_output"]}]}
    freeze["inputs"].update({r["path"]: r["sha256"] for r in digitization_records})
    calls = []
    actual = deepcopy(table_value)

    def verify(campaign, outputs, harness_freeze, **kwargs):
        calls.append((campaign, outputs, harness_freeze, kwargs))
        assert campaign == str(tmp_path / "campaign.json")
        assert outputs == [str(tmp_path / "raw_output")]
        assert harness_freeze == str(tmp_path / "harness_freeze.json")
        assert kwargs == {"smoke": False, "repo": tmp_path, "source_commit": commit}
        return actual
    real_verifier = scene_campaign.verify
    monkeypatch.setattr(scene_campaign, "verify", verify)

    def save_freeze():
        freeze_path.write_text(json.dumps(freeze))
        Path(str(freeze_path) + ".sha256").write_text(A.sha256(freeze_path))
    save_freeze()
    return {"root": tmp_path, "table": table_path, "rans": rans_path, "freeze": freeze_path,
            "spec": freeze, "save": save_freeze, "actual": actual, "calls": calls, "real_verifier": real_verifier}


def test_formal_loader_reverifies_raw_table_and_all_source_geometry_inputs(formal_boundary):
    f = formal_boundary
    data, provenance = A.load_formal_inputs([f["table"]], f["rans"], f["freeze"])
    assert data["identity_valid"] and len(f["calls"]) == 1
    assert A.analyze_input(data)["label"] == "CONCORDANT"
    assert all(r["observable"] == "total_cl" and r["h_over_c1"] == pytest.approx(r["height_mm"] / 223.4) and r["h_over_c"] == pytest.approx(r["height_mm"] / 380) for r in data["waterlily"])
    assert len(provenance["input_sha256"]) == 18
    # Confirmation geometry differs, and is bound by its own harness scene.
    assert {r["scene_sha256"] for r in data["waterlily"] if r["grid"] == "confirmation"} == {"c" * 64}
    # A success-flagged table cannot replace different raw verified coefficients.
    row = next(iter(f["actual"]["state_forces_n"]["kernel"].values()))
    S.set_readout(row, "drag", row["readouts"]["cur"]["drag"] + 0.1)
    data, provenance = A.load_formal_inputs([f["table"]], f["rans"], f["freeze"])
    assert A.analyze_input(data)["label"] == "INVALID"
    assert any("reverified force table differs" in e for e in provenance["identity_errors"])


def refresh_reference_fixture(f, *paths):
    """Model an authorized fixture freeze update, never mutate real evidence."""
    rans = A.load_json(f["rans"])
    for path in paths:
        path = Path(path).resolve()
        digest = A.sha256(path)
        f["spec"]["inputs"][str(path)] = digest
        for entry in rans["reference"]["source"]["digitization_records"]:
            if Path(entry["path"]).resolve() == path:
                entry["sha256"] = digest
        descriptor = rans["provenance"]["reference_estimate"]["manifest"]
        if Path(descriptor["path"]).resolve() == path:
            descriptor["sha256"] = digest
    f["rans"].write_text(json.dumps(rans))
    f["spec"]["inputs"]["rans.json"] = A.sha256(f["rans"])
    f["save"]()


def test_formal_reference_recomputed_from_frozen_manifest_and_raw_csvs(formal_boundary):
    f = formal_boundary
    data, provenance = A.load_formal_inputs([f["table"]], f["rans"], f["freeze"])
    assert data["reference_inputs"]["manifest"].endswith("digitization_manifest.json")
    assert len(data["reference_inputs"]["sha256"]) == 9
    result = A.analyze_input(data)
    assert result["tr00"]["reference"] == pytest.approx({"delta_cl": 1., "digitizing_uncertainty": .01})
    checker = load(ROOT / "scripts/topo2d00/check.py", "topo_reference_checker")
    assert checker.compare(result, checker.check(data)) == []
    path = f["root"] / "digitization_e0_A_upper.csv"
    path.write_text(path.read_text().replace("0.7985", "0.9985"))
    # A saved normalized record cannot conceal raw-record mutation from either implementation.
    for implementation in (A.analyze_input, checker.check):
        with pytest.raises(ValueError, match="reference.*SHA|SHA.*reference"):
            implementation(data)


def test_formal_provenance_cannot_be_downgraded_to_scalar_only_api(formal_boundary):
    f = formal_boundary
    data, _ = A.load_formal_inputs([f["table"]], f["rans"], f["freeze"])
    del data["reference_inputs"]
    checker = load(ROOT / "scripts/topo2d00/check.py", "topo_reference_no_downgrade")
    for implementation in (A.analyze_input, checker.check):
        with pytest.raises(ValueError, match="reference inputs"):
            implementation(data)


@pytest.mark.parametrize("tamper", [None, "tr00", "checksum", "missing"])
def test_checker_cli_checks_registered_standalone_outputs(tmp_path, monkeypatch, capsys, tamper):
    data = S.input_table()
    A.write_analysis(tmp_path, {"input": data, "result": A.analyze_input(data)})
    if tamper == "tr00":
        record = A.load_json(tmp_path / "tr00.json")
        record["reference"]["delta_cl"] += 1
        (tmp_path / "tr00.json").write_text(json.dumps(record))
    elif tamper == "checksum":
        (tmp_path / "SHA256SUMS").write_text("false checksum\n")
    elif tamper == "missing":
        (tmp_path / "analysis.md").unlink()
    checker = load(ROOT / "scripts/topo2d00/check.py", "topo_registered_cli")
    monkeypatch.setattr(checker, "__name__", "__main__")
    monkeypatch.setattr(checker, "__file__", str(ROOT / "scripts/topo2d00/check.py"))
    monkeypatch.setattr(A.sys, "argv", ["check.py", str(tmp_path / "analysis.json")])
    with pytest.raises(SystemExit) as exited:
        checker.main()
    assert exited.value.code == int(tamper is not None)
    result = json.loads(capsys.readouterr().out)
    assert result["pass"] is (tamper is None)
    assert bool(result["discrepancies"]) is (tamper is not None)


@pytest.mark.parametrize("summary_field", ["delta_cl", "digitizing_uncertainty"])
def test_reference_summary_cannot_override_raw_arithmetic(formal_boundary, summary_field):
    f = formal_boundary
    rans = A.load_json(f["rans"])
    rans["reference"][summary_field] += .5
    f["rans"].write_text(json.dumps(rans))
    f["spec"]["inputs"]["rans.json"] = A.sha256(f["rans"])
    f["save"]()
    with pytest.raises(ValueError, match="recomputed reference"):
        A.load_formal_inputs([f["table"]], f["rans"], f["freeze"])


@pytest.mark.parametrize("surface", ["upper", "lower"])
def test_reference_rejects_equal_numeric_contents_despite_distinct_bytes(formal_boundary, surface):
    f = formal_boundary
    source = f["root"] / f"digitization_e0_A_{surface}.csv"
    other = f["root"] / f"digitization_e0_B_{surface}.csv"
    rows = source.read_text().splitlines()[1:]
    # Reversed direction, different float spelling, BOM and CRLF are the same reading.
    other.write_bytes(("\ufeffx/c,Cp\r\n" + "\r\n".join(
        ",".join(f"{float(v):.17e}" for v in row.split(",")) for row in reversed(rows)) + "\r\n").encode())
    assert source.read_bytes() != other.read_bytes()
    refresh_reference_fixture(f, other)
    with pytest.raises(ValueError, match="normalized numeric"):
        A.load_formal_inputs([f["table"]], f["rans"], f["freeze"])


@pytest.mark.parametrize("problem", ["under_sampled", "swapped", "unbound", "missing_manifest"])
def test_reference_raw_failures_are_refused_before_output(formal_boundary, problem):
    f = formal_boundary
    if problem == "missing_manifest":
        rans = A.load_json(f["rans"])
        rans["provenance"].pop("reference_estimate")
        f["rans"].write_text(json.dumps(rans))
        f["spec"]["inputs"]["rans.json"] = A.sha256(f["rans"])
        f["save"]()
    else:
        path = f["root"] / "digitization_e0_A_upper.csv"
        if problem == "under_sampled":
            path.write_text("\n".join(path.read_text().splitlines()[:6]) + "\n")
            refresh_reference_fixture(f, path)
        elif problem == "swapped":
            lower = f["root"] / "digitization_e0_A_lower.csv"
            upper_bytes, lower_bytes = path.read_bytes(), lower.read_bytes()
            path.write_bytes(lower_bytes)
            lower.write_bytes(upper_bytes)
            refresh_reference_fixture(f, path, lower)
        else:
            f["spec"]["inputs"].pop(str(path.resolve()))
            f["save"]()
    with pytest.raises(ValueError):
        A.run_analysis([f["table"]], f["rans"], f["freeze"], f["root"] / "analysis")
    assert not (f["root"] / "analysis").exists()


def test_formal_loader_rejects_changed_source_and_rans_geometry(formal_boundary):
    f = formal_boundary
    path = f["root"] / "scripts/waterlily_topo2d_job.jl"
    path.write_text(path.read_text() + " changed after freeze")
    rans = json.loads(f["rans"].read_text())
    rans["provenance"]["geometry_sha256"]["E1"] = "d" * 64
    f["rans"].write_text(json.dumps(rans))
    f["spec"]["inputs"]["rans.json"] = A.sha256(f["rans"])
    f["save"]()
    data, provenance = A.load_formal_inputs([f["table"]], f["rans"], f["freeze"])
    assert A.analyze_input(data)["label"] == "INVALID"
    assert any("source mismatch" in e for e in provenance["identity_errors"])
    assert any("RANS geometry identity" in e for e in provenance["identity_errors"])


@pytest.mark.parametrize("config", ["E1", "E2", "E3", "E1_sharp", "E2_sharp"])
@pytest.mark.parametrize("state", ["UNVERIFIED_OCR", "UNKNOWN"])
def test_analysis_freeze_rejects_unverified_sources_on_every_geometry_arm(formal_boundary, config, state):
    f = formal_boundary
    path = f["root"] / (config + ".json")
    scene = A.load_json(path)
    scene["sources"][0]["verification"] = state
    path.write_text(json.dumps(scene))
    digest = A.sha256(path)
    rans = A.load_json(f["rans"])
    rans["provenance"]["geometry_sha256"][config] = digest
    f["rans"].write_text(json.dumps(rans))
    f["spec"]["geometry_sha256"][config] = digest
    f["spec"]["inputs"].update({config + ".json": digest, "rans.json": A.sha256(f["rans"])})
    f["save"]()
    with pytest.raises(ValueError, match="UNVERIFIED_OCR|verification"):
        A.load_formal_inputs([f["table"]], f["rans"], f["freeze"])


def test_json_duplicate_identity_is_rejected(tmp_path):
    path = tmp_path / "duplicate.json"
    path.write_text('{"schema":"first","schema":"second"}')
    with pytest.raises(ValueError, match="duplicate JSON key"):
        A.load_json(path)


def test_formal_tr00_requires_two_distinct_frozen_digitizations(formal_boundary):
    f = formal_boundary
    rans = json.loads(f["rans"].read_text())
    records = rans["reference"]["source"]["digitization_records"]
    records[1] = records[0].copy()
    f["rans"].write_text(json.dumps(rans))
    f["spec"]["inputs"]["rans.json"] = A.sha256(f["rans"])
    f["save"]()
    with pytest.raises(ValueError, match="distinct artifacts"):
        A.load_formal_inputs([f["table"]], f["rans"], f["freeze"])
    records[:] = records[:1]
    f["rans"].write_text(json.dumps(rans))
    f["spec"]["inputs"]["rans.json"] = A.sha256(f["rans"])
    f["save"]()
    with pytest.raises(ValueError, match="two independent"):
        A.load_formal_inputs([f["table"]], f["rans"], f["freeze"])


def test_distinct_digitization_paths_cannot_hide_identical_content(formal_boundary):
    f = formal_boundary
    rans = json.loads(f["rans"].read_text())
    records = rans["reference"]["source"]["digitization_records"]
    a, b = [f["root"] / f"digitization_e0_{reader}_upper.csv" for reader in ("A", "B")]
    b.write_bytes(a.read_bytes())
    refresh_reference_fixture(f, b)
    with pytest.raises(ValueError, match="normalized numeric contents"):
        A.load_formal_inputs([f["table"]], f["rans"], f["freeze"])


def test_formal_analysis_refuses_wrong_rans_observable(formal_boundary):
    f = formal_boundary
    rans = json.loads(f["rans"].read_text())
    rans["cells"][0]["realisations"][0]["forces"]["E2"]["observable"] = "pressure_cl"
    f["rans"].write_text(json.dumps(rans))
    f["spec"]["inputs"]["rans.json"] = A.sha256(f["rans"])
    f["save"]()
    with pytest.raises(ValueError, match="observable"):
        A.run_analysis([f["table"]], f["rans"], f["freeze"], f["root"] / "analysis")
    assert not (f["root"] / "analysis").exists()


def test_formal_analysis_refuses_wrong_verified_waterlily_observable(formal_boundary):
    f = formal_boundary
    claimed = json.loads(f["table"].read_text())
    next(iter(claimed["state_forces_n"]["kernel"].values()))["observable"] = "pressure_cl"
    f["actual"].clear()
    f["actual"].update(claimed)
    f["table"].write_text(json.dumps(claimed))
    f["spec"]["inputs"]["table.json"] = A.sha256(f["table"])
    f["save"]()
    with pytest.raises(ValueError, match="observable"):
        A.run_analysis([f["table"]], f["rans"], f["freeze"], f["root"] / "analysis")
    assert not (f["root"] / "analysis").exists()


def test_formal_legacy_component_map_cannot_contradict_force_observables(formal_boundary):
    f = formal_boundary
    rans = json.loads(f["rans"].read_text())
    rans["provenance"]["component_by_config"]["E1_sharp"] = "pressure_plus_viscous"
    f["rans"].write_text(json.dumps(rans))
    f["spec"]["inputs"]["rans.json"] = A.sha256(f["rans"])
    f["save"]()
    with pytest.raises(ValueError, match="component_by_config"):
        A.load_formal_inputs([f["table"]], f["rans"], f["freeze"])


def test_formal_current_wp5_component_map_uses_observable_names(formal_boundary):
    f = formal_boundary
    rans = json.loads(f["rans"].read_text())
    rans["provenance"]["component_by_config"] = {c: "pressure_cl" if c.endswith("_sharp") else "total_cl" for c in A.RCONFIGS}
    f["rans"].write_text(json.dumps(rans))
    f["spec"]["inputs"]["rans.json"] = A.sha256(f["rans"])
    f["save"]()
    data, _ = A.load_formal_inputs([f["table"]], f["rans"], f["freeze"])
    assert A.analyze_input(data)["label"] == "CONCORDANT"


def test_readout_whole_mean_must_match_equal_duration_batch_means():
    payload = S.input_table()
    payload["waterlily"][0]["readouts"]["cur"]["downforce"] += 0.01
    with pytest.raises(ValueError, match="batch mean"):
        A.analyze_input(payload)
    payload = S.input_table()
    payload["waterlily"][0]["readouts"]["cur"]["downforce"] += 0.5e-9
    A.analyze_input(payload)  # permit declared floating-point reduction tolerance


@pytest.mark.parametrize("status", ["complete", "finite", "ok"])
def test_identical_but_failed_determinism_repeat_cannot_pass(status):
    payload = S.input_table()
    repeated = next(r for r in payload["waterlily"] if r["role"] == "determinism")
    repeated[status] = False
    result = A.analyze_input(payload)
    if status == "finite":
        assert result["label"] == "NUMERICAL"
        assert result["controls"]["determinism"]["pass"] is not True
    else:
        assert result["controls"]["determinism"] == {"judged": True, "pass": False}


@pytest.mark.parametrize("role", ["secondary", "domain"])
def test_actual_nonfinite_control_is_numerical_before_phase_cardinality(role):
    payload = S.input_table()
    row = payload["waterlily"][0]
    row["role"] = role  # missing primary phase is immaterial after actual failure
    row["finite"] = row["ok"] = row["complete"] = False
    row["readouts"] = {name: None for name in ("cur", "nds", "cv")}
    assert A.analyze_input(payload)["label"] == "NUMERICAL"


def test_formal_failure_transport_uses_reverified_rows_not_claimed_flags(formal_boundary):
    """Boundary contract test; actual cryptographic admission is harness-owned."""
    from copy import deepcopy
    f = formal_boundary
    claimed = json.loads(f["table"].read_text())
    rows = claimed["state_forces_n"]["kernel"]
    failure = f["root"] / "numerical_failure.json"
    failure.write_text(json.dumps({"synthetic_failure_identity": "contract mock only"}))
    digest = A.sha256(failure)
    for index, status in (("0", "NUMERICAL"), ("1", "SKIPPED_NUMERICAL")):
        row = rows[index]
        row.update(status=status, ok=False, complete=False,
                   finite=False if status == "NUMERICAL" else None,
                   readouts={name: None for name in ("cur", "nds", "cv")})
        row["failure_sha256" if status == "NUMERICAL" else "prior_failure_sha256"] = digest
    f["table"].write_text(json.dumps(claimed))
    f["spec"]["inputs"]["table.json"] = A.sha256(f["table"])
    f["spec"]["inputs"]["numerical_failure.json"] = digest
    f["save"]()
    # Supplied failure flags contradict the verifier's independently returned table.
    data, provenance = A.load_formal_inputs([f["table"]], f["rans"], f["freeze"])
    assert A.analyze_input(data)["label"] == "INVALID"
    assert any("reverified force table differs" in e for e in provenance["identity_errors"])
    # The external admission boundary now returns the authenticated-failure shape.
    f["actual"].clear()
    f["actual"].update(deepcopy(claimed))
    data, provenance = A.load_formal_inputs([f["table"]], f["rans"], f["freeze"])
    assert A.analyze_input(data)["label"] == "NUMERICAL"
    assert len(provenance["skipped_numerical"]) == 1
    assert provenance["skipped_numerical"][0]["prior_failure_sha256"] == digest
    assert provenance["skipped_numerical"][0]["topo2d"] == rows["1"]["topo2d"]
    assert provenance["numerical_failures"][0]["failure_sha256"] == digest
    assert len(data["waterlily"]) == len(rows) - 1


def bind_actual_raw_harness_study(f, monkeypatch, writer):
    """Bind actual raw verifier fixtures to synthetic study/source attestations."""
    from cfd_harness import campaign_schema as sc, scene_campaign
    repo = f["root"] / "raw_repo"
    campaign_path, output, harness_freeze = writer(repo, smoke=False)
    monkeypatch.setattr(A, "REPO", repo)
    monkeypatch.setattr(scene_campaign, "verify", f["real_verifier"])
    monkeypatch.setattr(scene_campaign, "formal_context", lambda *args: [0.5, 4.5])
    # External PDF/source-verification admission is synthetic in this raw
    # receipt fixture, just like the qualification gate and git attestations.
    # Real scene geometry gates, manifests and receipt linkage still run.
    monkeypatch.setattr(scene_campaign, "require_verified_geometry", lambda scene: None)
    for name in f["spec"]["sources"]:
        path = repo / name
        if not path.is_file():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("synthetic unexecuted source attestation: " + name)
    monkeypatch.setattr(A.subprocess, "check_output", lambda command, **kwargs: (repo / command[2].split(":", 1)[1]).read_bytes())
    table = scene_campaign.verify(campaign_path, [output], harness_freeze, repo=repo, source_commit="a" * 40)
    f["table"].write_text(json.dumps(table))
    campaign = sc.jload(campaign_path)
    geometry_paths = {state["topo2d"]["configuration"]: repo / state["scene_path"] for state in campaign["states"].values()}
    for config in A.RCONFIGS:
        if config not in geometry_paths:
            path = repo / (config + ".json")
            path.write_text(json.dumps({"schema": "topo2d-scene-v1", "synthetic_unrun_geometry": config,
                                        "sources": [{"verification": "VERIFIED_SYNTHETIC"}]}))
            geometry_paths[config] = path
    geometry = {config: A.sha256(path) for config, path in geometry_paths.items()}
    rans = json.loads(f["rans"].read_text())
    rans["provenance"]["geometry_sha256"] = geometry
    for digitization in rans["reference"]["source"]["digitization_records"]:
        digitization["path"] = str(f["root"] / digitization["path"])
    f["rans"].write_text(json.dumps(rans))
    spec = f["spec"]
    spec["inputs"] = {str(f["root"] / name): digest for name, digest in spec["inputs"].items()}
    for path in (f["table"], f["rans"], campaign_path, harness_freeze, *geometry_paths.values()):
        spec["inputs"][str(path)] = A.sha256(path)
    spec.update(source_commit="a" * 40, geometry_sha256=geometry,
                sources={name: A.sha256(repo / name) for name in spec["sources"]},
                harness=[{"table": str(f["table"]), "campaign": str(campaign_path), "freeze": str(harness_freeze), "outputs": [str(output)]}])
    f["save"]()
    return campaign_path, output, harness_freeze


def test_actual_harness_failure_proof_reaches_numerical_and_forgery_is_invalid(formal_boundary, monkeypatch):
    """Actual raw admission; external qualification/commit attestations are synthetic.

    No solver or GPU is invoked. Only formal_context and git-source extraction
    are mocked. The real scene verifier checks scene/source/runtime hashes,
    manifest, numerical receipt, skip linkage and the unaffected force CSV.
    """
    from cfd_harness import campaign_schema as sc
    f = formal_boundary
    helper = load(HERE / "test_campaign.py", "topo_numerical_receipt_fixture")
    _, output, _ = bind_actual_raw_harness_study(f, monkeypatch, helper.write_synthetic_numerical_kernel)
    data, provenance = A.load_formal_inputs([f["table"]], f["rans"], f["freeze"])
    assert data["identity_valid"] and A.analyze_input(data)["label"] == "NUMERICAL"
    assert len(data["waterlily"]) == 2
    assert len(provenance["numerical_failures"]) == len(provenance["skipped_numerical"]) == 1
    # Even refreshed file/index/manifest hashes cannot authenticate a different scene.
    index_path = output / sc.INDEX_NAME_DEFAULT
    index = sc.jload(index_path)
    failure_path = output / "states" / index["states"][0]["name"] / "numerical_failure.json"
    failure = sc.jload(failure_path)
    failure["scene_sha256"] = "0" * 64
    failure_path.write_text(json.dumps(failure))
    digest = A.sha256(failure_path)
    index["states"][0]["failure_sha256"] = index["states"][2]["prior_failure_sha256"] = digest
    index_path.write_text(json.dumps(index))
    (output / sc.MANIFEST_NAME).write_text(json.dumps(sc.build_manifest(output)))
    data, provenance = A.load_formal_inputs([f["table"]], f["rans"], f["freeze"])
    assert A.analyze_input(data)["label"] == "INVALID"
    assert any("raw harness verification failed" in e for e in provenance["identity_errors"])


def test_cap_markers_are_unmeasured_and_only_reverified_cap_is_used(formal_boundary):
    """Normalization boundary only; raw receipt validation has a real-verifier test."""
    from copy import deepcopy
    f = formal_boundary
    claimed = json.loads(f["table"].read_text())
    record = {"schema": "topo2d-cap-receipt-v1", "reason": "STATE_TIMEOUT"}
    path = f["root"] / "cap_receipt.json"
    path.write_text(json.dumps(record))
    digest = A.sha256(path)
    claimed.update(cap_hit=True, cap_receipts={"kernel": {"sha256": digest, "record": record}})
    rows = claimed["state_forces_n"]["kernel"]
    for key, status in (("0", "INCOMPLETE_TIMEOUT"), ("1", "UNRUN_CAP")):
        rows[key] = {"topo2d": rows[key]["topo2d"], "scene_sha256": rows[key]["scene_sha256"],
                     "status": status, "cap_receipt_sha256": digest}
    f["table"].write_text(json.dumps(claimed))
    f["spec"]["inputs"].update({"table.json": A.sha256(f["table"]), "cap_receipt.json": digest})
    f["save"]()
    data, _ = A.load_formal_inputs([f["table"]], f["rans"], f["freeze"])
    assert A.analyze_input(data)["label"] == "INVALID"  # declared flags alone cannot pass
    f["actual"].clear()
    f["actual"].update(deepcopy(claimed))
    data, provenance = A.load_formal_inputs([f["table"]], f["rans"], f["freeze"])
    assert data["cap_hit"] and A.analyze_input(data)["label"] == "INCOMPLETE"
    assert len(data["waterlily"]) == len(rows) - 2
    assert {r["status"] for r in provenance["unmeasured_cap"]} == {"INCOMPLETE_TIMEOUT", "UNRUN_CAP"}
    assert provenance["cap_receipts"][0]["sha256"] == digest


@pytest.mark.parametrize("reason", ["STATE_TIMEOUT", "SOLVER_WALL_CAP", "WALL_TIME_OVERRUN"])
def test_actual_harness_cap_proof_reaches_incomplete_and_forgery_is_invalid(formal_boundary, monkeypatch, reason):
    """Actual cap verifier, with synthetic external qualification/source context."""
    from cfd_harness import campaign_schema as sc
    f = formal_boundary
    helper = load(HERE / "test_campaign.py", "topo_cap_receipt_fixture")
    writer = lambda folder, smoke: helper.write_synthetic_incomplete_kernel(folder, smoke=smoke, reason=reason)
    _, output, _ = bind_actual_raw_harness_study(f, monkeypatch, writer)
    data, provenance = A.load_formal_inputs([f["table"]], f["rans"], f["freeze"])
    assert data["identity_valid"] and data["cap_hit"]
    assert A.analyze_input(data)["label"] == "INCOMPLETE"
    assert data["waterlily"] and all(r["complete"] and r["finite"] and r["ok"] for r in data["waterlily"])
    assert provenance["cap_receipts"][0]["record"]["reason"] == reason
    if reason == "WALL_TIME_OVERRUN":
        assert provenance["unmeasured_cap"] == []  # final measured state itself exceeded the cap
    else:
        assert provenance["unmeasured_cap"]
    assert all("readouts" not in r and "finite" not in r for r in provenance["unmeasured_cap"])
    # An unknown process failure cannot become a budget result by rehashing it.
    path = output / "cap_receipt.json"
    record = sc.jload(path)
    old_digest = A.sha256(path)
    record["reason"] = "UNKNOWN_PROCESS_ERROR"
    path.write_text(json.dumps(record))
    new_digest = A.sha256(path)

    def replace_digest(value):
        if isinstance(value, dict):
            return {k: replace_digest(v) for k, v in value.items()}
        if isinstance(value, list):
            return [replace_digest(v) for v in value]
        return new_digest if value == old_digest else value
    index_path = output / sc.INDEX_NAME_DEFAULT
    index_path.write_text(json.dumps(replace_digest(sc.jload(index_path))))
    (output / sc.MANIFEST_NAME).write_text(json.dumps(sc.build_manifest(output)))
    data, provenance = A.load_formal_inputs([f["table"]], f["rans"], f["freeze"])
    assert A.analyze_input(data)["label"] == "INVALID"
    assert any("raw harness verification failed" in e for e in provenance["identity_errors"])
