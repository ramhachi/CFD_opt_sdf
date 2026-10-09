"""LOWDIM-01 contract and analyzer: the actual primal and the hard gates decide; predictions are reference only; integrity is fail-closed."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests")); sys.path.insert(0, str(ROOT / "scripts")); sys.path.insert(0, str(ROOT / "src"))
import analyze_lowdim01 as A  # noqa: E402
import lowdim01_states as L  # noqa: E402
import lowdim01_synthetic as SYN  # noqa: E402
from cfd_sdf import lowdim01_contract as C  # noqa: E402


# ---- the contract ------------------------------------------------------------------------------------------------------------------------------------------
def test_acceptance_needs_a_resolved_gain_the_drag_constraint_and_every_hard_gate():
    base = (0.33, 0.32)
    assert C.evaluate_candidate(*base, 0.33 + 4e-5, 0.32, True)["accepted"] is True
    assert C.evaluate_candidate(*base, 0.33 + 3e-5, 0.32, True)["accepted"] is False                       # not above 10 sigma0
    assert C.evaluate_candidate(*base, 0.33 + 1e-3, 0.32 + 4e-5, True)["accepted"] is False               # the drag grew by more than the resolution
    assert C.evaluate_candidate(*base, 0.33 + 1e-3, 0.32 + 2e-5, True)["accepted"] is True                # within the allowance
    assert C.evaluate_candidate(*base, 0.33 + 1e-3, 0.32, False)["accepted"] is False                     # a failed hard gate is never overridden by a good response
    with pytest.raises(ValueError):
        C.evaluate_candidate(*base, float("nan"), 0.32, True)
    assert C.MIN_DOWNFORCE_GAIN_N == pytest.approx(3e-5) and C.DRAG_ALLOWANCE_N == pytest.approx(3e-5)


def test_selection_takes_the_largest_actual_gain_then_the_smaller_step_and_none_is_a_no_go():
    ev = {"a": {"accepted": True, "downforce_change_n": 2e-4}, "b": {"accepted": True, "downforce_change_n": 5e-4}, "c": {"accepted": False, "downforce_change_n": 9e-4}}
    assert C.select_trial(ev, {"a": 1.25, "b": 2.5, "c": 5.0}) == {"verdict": "LOWDIM_ACCEPT", "selected": "b"}
    ev["a"]["downforce_change_n"] = 5e-4
    assert C.select_trial(ev, {"a": 1.25, "b": 2.5, "c": 5.0})["selected"] == "a"                          # a tie goes to the smaller step
    assert C.select_trial({"a": {"accepted": False, "downforce_change_n": 1e-3}}, {"a": 1.0}) == {"verdict": "LOWDIM_NO_GO", "selected": None}
    with pytest.raises(ValueError):
        C.select_trial({}, {})                                                                                 # zero evaluations is not a bounded No-Go
    big_first = {"big": {"accepted": True, "downforce_change_n": 4e-4}, "small": {"accepted": True, "downforce_change_n": 4e-4}}
    assert C.select_trial(big_first, {"big": 5.0, "small": 1.25})["selected"] == "small"                      # not the insertion order


def test_the_thresholds_are_strict_exactly_at_the_registered_values():
    assert C.evaluate_candidate(0.0, 0.0, C.MIN_DOWNFORCE_GAIN_N, 0.0, True)["accepted"] is False             # gain == 10 sigma0: not above
    assert C.evaluate_candidate(0.0, 0.0, C.MIN_DOWNFORCE_GAIN_N * 1.0000001, 0.0, True)["accepted"] is True
    assert C.evaluate_candidate(0.0, 0.0, 1e-3, C.DRAG_ALLOWANCE_N, True)["accepted"] is True                  # drag == allowance: accepted
    assert C.evaluate_candidate(0.0, 0.0, 1e-3, C.DRAG_ALLOWANCE_N * 1.0000001, True)["accepted"] is False
    assert C.evaluate_candidate(0.0, 0.0, 1e-3, -1.0, True)["accepted"] is True                                # any drag decrease is fine for the drag constraint


# ---- the analyzer on synthetic outputs -----------------------------------------------------------------------------------------------------------------------
def run(tmp_path, **kw):
    out, freeze, inv = SYN.make_all(tmp_path, **kw)
    return A.analyze(out, freeze, inventory=inv, formal=SYN.FORMAL), out, freeze, inv


def test_an_accepted_trial_is_the_largest_resolved_gain_with_all_gates(tmp_path):
    r, *_ = run(tmp_path, gains={1.25: 3e-4, 2.5: 5e-4, 5.0: -2e-3, 7.5: 2e-3}, gates_fail=(7.5,))
    assert r["verdict"] == "LOWDIM_ACCEPT" and r["selected"] == "lowdim01__prop__s2.5mm" and r["integrity"]["pass"] is True
    c = r["candidates"]
    assert c["lowdim01__prop__s7.5mm"]["accepted"] is False and c["lowdim01__prop__s7.5mm"]["downforce_gain_resolved"] is True            # a good response cannot override a failed gate
    assert c["lowdim01__prop__s5mm"]["accepted"] is False and c["lowdim01__prop__s2.5mm"]["actual_over_predicted_reference_only"] is not None
    assert r["selected_delta"] is None and r["grad03_verdict"] is None and r["not_opt01"] is True and r["reinitialization"] == "none" and set(r["qualification_flags"].values()) == {False}
    assert "reference only" in r["rules"]["authority"] and "full-field gradient" in r["interpretation"]


def test_no_resolved_improvement_is_a_bounded_no_go(tmp_path):
    r, *_ = run(tmp_path, gains={1.25: 2e-5, 2.5: -4e-4, 5.0: -3e-3, 7.5: -9e-3})
    assert r["verdict"] == "LOWDIM_NO_GO" and r["selected"] is None and "bounded No-Go" in r["interpretation"]
    assert all(c["accepted"] is False for c in r["candidates"].values()) and r["candidates"]["lowdim01__prop__s1.25mm"]["downforce_gain_resolved"] is False


def test_a_drag_increase_beyond_the_resolution_rejects_an_otherwise_good_candidate(tmp_path):
    r, *_ = run(tmp_path, gains={1.25: 1e-3}, drags={1.25: 5e-5})
    assert r["candidates"]["lowdim01__prop__s1.25mm"]["drag_constraint_ok"] is False and r["verdict"] == "LOWDIM_NO_GO"


def test_the_prediction_never_enters_the_decision(tmp_path):
    r, *_ = run(tmp_path, gains={1.25: 4e-5})
    assert r["verdict"] == "LOWDIM_ACCEPT" and r["candidates"]["lowdim01__prop__s1.25mm"]["linear_predicted_downforce_change_n_reference_only"] > 5e-4        # far off the prediction, still accepted


@pytest.mark.parametrize("kw", [dict(break_baseline=True), dict(drop="lowdim01__prop__s2.5mm"), dict(failed="lowdim01__baseline"), dict(gpu="Tesla P100"), dict(empty_manifest=True)])
def test_integrity_failures_make_the_run_incomplete_and_decide_nothing(tmp_path, kw):
    r, *_ = run(tmp_path, **kw)
    assert r["verdict"] == "LOWDIM_INCOMPLETE" and r["integrity"]["pass"] is False and "candidates" not in r and "selected" not in r


def tamper(tmp_path, edit):
    out, freeze, inv = SYN.make_all(tmp_path)
    edit(out, freeze, inv)
    return A.analyze(out, freeze, inventory=inv, formal=SYN.FORMAL)


@pytest.mark.parametrize("name", ["contract", "states_module", "step01_states_module", "force_io", "formal_criteria", "analyzer"])
def test_every_frozen_input_is_checked(tmp_path, name):
    r = tamper(tmp_path, lambda o, f, i: f["file_hashes"].__setitem__(name, "0" * 64))
    assert r["verdict"] == "LOWDIM_INCOMPLETE" and any(name.replace("_", " ") in x.replace("_", " ") for x in r["integrity"]["failures"])


def test_the_bound_step01_data_and_the_pins_are_checked(tmp_path):
    assert tamper(tmp_path, lambda o, f, i: f.__setitem__("step01_analysis_sha256", "0" * 64))["verdict"] == "LOWDIM_INCOMPLETE"
    assert tamper(tmp_path / "g", lambda o, f, i: i["coefficient_gradient"]["values"]["D0_interface_offset"].__setitem__("g_sec_n_per_m", 9.9))["verdict"] == "LOWDIM_INCOMPLETE"
    assert tamper(tmp_path / "p", lambda o, f, i: f.__setitem__("pins", {}))["verdict"] == "LOWDIM_INCOMPLETE"
    assert tamper(tmp_path / "s", lambda o, f, i: f.__setitem__("source_commit", "b" * 40))["verdict"] == "LOWDIM_INCOMPLETE"


def test_done_and_error_together_or_a_tampered_csv_are_refused(tmp_path):
    assert tamper(tmp_path, lambda o, f, i: (o / "ERROR.txt").write_text("x"))["verdict"] == "LOWDIM_INCOMPLETE"
    def edit(o, f, i):
        p = o / "states" / "lowdim01__baseline" / "flow_24.forces.csv"; p.write_text(p.read_text() + "\n")
    assert tamper(tmp_path / "m", edit)["verdict"] == "LOWDIM_INCOMPLETE"


def test_the_analyzer_writes_once_check_mode_writes_nothing_and_the_report_has_provenance(tmp_path, monkeypatch, capsys):
    out, freeze, inv = SYN.make_all(tmp_path, gains={1.25: 4e-4})
    fz = tmp_path / "freeze.json"; fz.write_text(json.dumps(freeze))
    original = A.analyze
    monkeypatch.setattr(A, "analyze", lambda d, f: original(d, f, inventory=inv, formal=SYN.FORMAL))
    argv = ["x", "--freeze", str(fz), "--kernel-dir", str(out)]
    monkeypatch.setattr("sys.argv", argv + ["--check"])
    A.main()
    assert json.loads(capsys.readouterr().out)["verdict"] == "LOWDIM_ACCEPT"
    target = tmp_path / "a.json"
    monkeypatch.setattr("sys.argv", argv + ["--write", str(target)])
    A.main()
    rep = json.loads(target.read_text())
    assert rep["verdict"] == "LOWDIM_ACCEPT" and rep["provenance"]["freeze_sha256"] == A.sha256(fz) and rep["provenance"]["source_commit"] == "a" * 40
    with pytest.raises(SystemExit):
        A.main()


# ---- cases added after the independent review -------------------------------------------------------------------------------------------------------------------
def test_equal_gains_choose_the_smaller_step_through_the_analyzer(tmp_path):
    r, *_ = run(tmp_path, gains={1.25: 4e-4, 2.5: 4e-4, 5.0: 4e-4})
    assert r["verdict"] == "LOWDIM_ACCEPT" and r["selected"] == "lowdim01__prop__s1.25mm"


def test_good_responses_with_every_hard_gate_failed_are_a_no_go(tmp_path):
    r, *_ = run(tmp_path, gains={1.25: 4e-4, 2.5: 4e-4, 5.0: 4e-4, 7.5: 4e-4}, gates_fail=(1.25, 2.5, 5.0, 7.5))
    assert r["verdict"] == "LOWDIM_NO_GO" and all(c["downforce_gain_resolved"] and not c["accepted"] for c in r["candidates"].values())


def test_controls_are_reported_but_never_accepted_or_selected(tmp_path):
    r, *_ = run(tmp_path, gains={1.25: -1e-3, 2.5: -1e-3, 5.0: -1e-3, 7.5: -1e-3}, control_gains={1.25: 9e-3, 2.5: 9e-3})
    assert r["verdict"] == "LOWDIM_NO_GO" and r["selected"] is None and set(r["controls"]) == {"lowdim01__ctrl_reverse__s1.25mm", "lowdim01__ctrl_reverse__s2.5mm"}
    assert all(c["never_accepted_or_selected"] is True and "accepted" not in c and c["signed_step_mm"] < 0 for c in r["controls"].values())
    chk = r["proposal_sign_check_descriptive"]["1.25"]
    assert chk["forward_minus_reverse_n"] == pytest.approx(-1e-3 - 9e-3) and chk["odd_part_n"] == pytest.approx(-5e-3) and chk["even_part_n"] == pytest.approx(4e-3)


def test_a_nan_in_a_candidate_force_history_is_an_integrity_failure(tmp_path):
    r, *_ = run(tmp_path, nan_candidate="lowdim01__prop__s2.5mm")
    assert r["verdict"] == "LOWDIM_INCOMPLETE" and "candidates" not in r


def test_the_canonical_inventory_hash_is_checked(tmp_path):
    r = tamper(tmp_path, lambda o, f, i: f["file_hashes"].__setitem__("inventory_canonical_json", "0" * 64))
    assert r["verdict"] == "LOWDIM_INCOMPLETE" and any("inventory" in x for x in r["integrity"]["failures"])


def test_an_inconsistent_registered_gate_record_or_a_missing_reference_makes_the_run_incomplete_with_a_record(tmp_path):
    def edit(o, f, i):
        st = next(r for r in i["states"] if r["name"] == "lowdim01__prop__s1.25mm")
        st["geometry_gates"]["all_hard_gates_pass"] = False                      # contradicts its own gate values
        import hashlib
        f["file_hashes"]["inventory_canonical_json"] = hashlib.sha256((json.dumps(i, sort_keys=True, indent=2) + "\n").encode()).hexdigest()
    r = tamper(tmp_path, edit)
    assert r["verdict"] == "LOWDIM_INCOMPLETE" and any("inconsistent" in x for x in r["integrity"]["failures"])
    def edit2(o, f, i):
        del i["linear_prediction_reference_only"]["lowdim01__prop__s2.5mm"]
        import hashlib
        f["file_hashes"]["inventory_canonical_json"] = hashlib.sha256((json.dumps(i, sort_keys=True, indent=2) + "\n").encode()).hexdigest()
    r2 = tamper(tmp_path / "x", edit2)
    assert r2["verdict"] == "LOWDIM_INCOMPLETE" and any("analysis error" in x for x in r2["integrity"]["failures"])
