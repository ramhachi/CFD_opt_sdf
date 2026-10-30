"""STEP-01 analyzer on synthetic kernel outputs: integrity gates, the registered quantities, one-shot writing."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests")); sys.path.insert(0, str(ROOT / "scripts")); sys.path.insert(0, str(ROOT / "src"))
import analyze_step01 as A  # noqa: E402
import step01_synthetic as SYN  # noqa: E402
import step01_states as S  # noqa: E402


def run(tmp_path, **kw):
    dirs, freeze, inv = SYN.make_all(tmp_path, **kw)
    return A.analyze(dirs, freeze, inventory=inv, formal=SYN.FORMAL), dirs, freeze, inv


def test_linear_responses_are_recorded_with_full_agreement_and_no_nonlinearity(tmp_path):
    r, *_ = run(tmp_path)
    assert r["verdict"] == "STEP01_RECORDED" and r["integrity"]["pass"] is True and len(r["series"]) == 8
    for key, s in r["series"].items():
        assert s["sign_stability"]["constant_over_resolved_steps"] is True and s["sign_stable_through_mm"] == 12.5
        assert s["agreement_radius_mm"]["50pct"] is not None
        assert all(abs(x) < 1e-9 for x in s["eta_even_by_step"] if x == x)
        assert s["secant_drift"]["30pct"]["first_step_outside_mm"] is None
    assert r["selected_delta"] is None and r["grad03_verdict"] is None and r["no_gradient_claim"] is True and set(r["qualification_flags"].values()) == {False}


def test_the_centered_secant_cancels_the_even_part_and_eta_even_reports_it(tmp_path):
    r, *_ = run(tmp_path, curvature=0.5)
    row = r["series"]["D0_interface_offset|downforce"]["rows"][2]
    g = SYN.ghat("D0_interface_offset", "downforce")
    assert row["g_sec_n_per_m"] == pytest.approx(g, rel=1e-6)                      # the quadratic part is even: the centered secant is unchanged
    assert row["eta_even"] == pytest.approx(0.19, abs=0.03) and row["g_sec_over_g_hat"] == pytest.approx(1.0, rel=1e-6) and abs(row["one_sided_secant_plus_n_per_m"] - row["one_sided_secant_minus_n_per_m"]) > 0


def test_a_sign_reversal_marks_the_first_flip_and_ends_the_stable_range(tmp_path):
    r, *_ = run(tmp_path, flip_at=10.0, flip_series="D1_filtered_seed11")
    s = r["series"]["D1_filtered_seed11|downforce"]
    assert s["sign_stability"]["constant_over_resolved_steps"] is False and s["sign_stability"]["first_flip_index"] == 3 and s["sign_stable_through_mm"] == 7.5
    assert s["agreement_radius_mm"]["30pct"] == 7.5
    assert r["series"]["D0_interface_offset|drag"]["sign_stability"]["constant_over_resolved_steps"] is True
    assert r["contract_inputs_for_lowdim"]["all_series_sign_constant_through_12.5mm"] is False


def test_combined_directions_report_additivity_with_the_interpolation_spread(tmp_path):
    r, *_ = run(tmp_path)
    cells = r["combined_directions"]["D1_filtered_seed11+D2_filtered_seed2026"]
    assert set(cells) == {f"{resp}|{sg}" for resp in ("drag", "downforce") for sg in ("plus", "minus")}
    for cell in cells.values():
        assert cell["additivity"]["relative_to_combo"] < 1e-6 and cell["component_step_mm"] == pytest.approx(4.67376863, rel=1e-6)
    r2, *_ = run(tmp_path / "d", combo_defect=0.5)
    c2 = r2["combined_directions"]["D0_interface_offset+P1_upstream_lobe"]["drag|plus"]
    assert c2["additivity"]["relative_to_combo"] > 0.05 and c2["additivity"]["defect_exceeds_interpolation_spread_and_resolution"] is True


@pytest.mark.parametrize("kw", [dict(break_baseline=True), dict(drop="step01__D0_interface_offset__s5mm__plus"), dict(failed="step01__baseline"), dict(gpu="Tesla P100")])
def test_integrity_failures_make_the_run_incomplete_and_report_no_series(tmp_path, kw):
    r, *_ = run(tmp_path, **kw)
    assert r["verdict"] == "STEP01_INCOMPLETE" and r["integrity"]["pass"] is False and "series" not in r


def test_a_summary_that_disagrees_with_the_host_recomputation_or_the_registered_phi_is_refused(tmp_path):
    dirs, freeze, inv = SYN.make_all(tmp_path)
    p = dirs["a"] / "states" / "step01__D0_interface_offset__s5mm__plus" / "flow_24.summary.json"
    d = json.loads(p.read_text()); d["drag_time_weighted_n"] *= 1.0001; p.write_text(json.dumps(d))
    r = A.analyze(dirs, freeze, inventory=inv, formal=SYN.FORMAL)
    assert r["verdict"] == "STEP01_INCOMPLETE" and any("host recomputation" in f or "manifest" in f for f in r["integrity"]["failures"])


def test_frozen_pins_the_source_commit_and_the_analyzer_are_checked(tmp_path):
    dirs, freeze, inv = SYN.make_all(tmp_path)
    assert A.analyze(dirs, {**freeze, "source_commit": "b" * 40}, inventory=inv, formal=SYN.FORMAL)["verdict"] == "STEP01_INCOMPLETE"
    assert A.analyze(dirs, {**freeze, "pins": {"scripts/y.jl": "33" * 32}}, inventory=inv, formal=SYN.FORMAL)["verdict"] == "STEP01_INCOMPLETE"
    assert A.analyze(dirs, {**freeze, "file_hashes": {**freeze["file_hashes"], "analyzer": "0" * 64}}, inventory=inv, formal=SYN.FORMAL)["verdict"] == "STEP01_INCOMPLETE"


def test_the_analyzer_writes_once_and_check_mode_writes_nothing(tmp_path, monkeypatch, capsys):
    dirs, freeze, inv = SYN.make_all(tmp_path)
    fz = tmp_path / "freeze.json"; fz.write_text(json.dumps(freeze))
    original = A.analyze
    monkeypatch.setattr(A, "analyze", lambda d, f: original(d, f, inventory=inv, formal=SYN.FORMAL))
    argv = ["x", "--freeze", str(fz), *sum((["--kernel-dir", f"{k}={v}"] for k, v in dirs.items()), [])]
    monkeypatch.setattr("sys.argv", argv + ["--check"])
    A.main()
    assert json.loads(capsys.readouterr().out)["verdict"] == "STEP01_RECORDED"
    target = tmp_path / "a.json"
    monkeypatch.setattr("sys.argv", argv + ["--write", str(target)])
    A.main()
    assert json.loads(target.read_text())["verdict"] == "STEP01_RECORDED"
    with pytest.raises(SystemExit):
        A.main()


# ---- cases added after the independent review ------------------------------------------------------------------------------------------------------------------
def tamper(tmp_path, edit, **kw):
    dirs, freeze, inv = SYN.make_all(tmp_path, **kw)
    edit(dirs, freeze, inv)
    return A.analyze(dirs, freeze, inventory=inv, formal=SYN.FORMAL)


def test_an_empty_manifest_or_empty_pins_are_refused(tmp_path):
    assert run(tmp_path, empty_manifest=True)[0]["verdict"] == "STEP01_INCOMPLETE"
    assert run(tmp_path / "p", empty_pins=True)[0]["verdict"] == "STEP01_INCOMPLETE"


@pytest.mark.parametrize("name", ["contract", "states_module", "force_io", "formal_criteria", "inventory_canonical_json"])
def test_every_frozen_input_of_the_computation_is_checked(tmp_path, name):
    r = tamper(tmp_path, lambda d, f, i: f["file_hashes"].__setitem__(name, "0" * 64))
    assert r["verdict"] == "STEP01_INCOMPLETE" and any(name.split("_canonical")[0].replace("_", " ") in x.replace("_", " ") or name in x for x in r["integrity"]["failures"])


def test_the_frozen_g_hat_fits_are_compared(tmp_path):
    r = tamper(tmp_path, lambda d, f, i: f["fd08_g_hat_fits"]["D0_interface_offset|drag"].__setitem__("g_n_per_m", 3 * f["fd08_g_hat_fits"]["D0_interface_offset|drag"]["g_n_per_m"]))
    assert r["verdict"] == "STEP01_INCOMPLETE" and any("g-hat" in x for x in r["integrity"]["failures"])


def test_nan_and_malformed_summaries_make_the_run_incomplete_never_a_crash(tmp_path):
    def edit(dirs, freeze, inv):
        p = dirs["b"] / "states" / "step01__baseline" / "flow_24.summary.json"
        d = json.loads(p.read_text()); d["drag_time_weighted_n"] = float("nan"); d.pop("t_end_reached"); p.write_text(json.dumps(d))
        m = json.loads((dirs["b"] / "output_manifest.json").read_text()); m["files"]["states/step01__baseline/flow_24.summary.json"] = A.sha256(p)
        (dirs["b"] / "output_manifest.json").write_text(json.dumps(m))
    r = tamper(tmp_path, edit)
    assert r["verdict"] == "STEP01_INCOMPLETE" and any("summary" in x or "horizon" in x for x in r["integrity"]["failures"])


def test_done_and_error_together_a_missing_gpu_record_or_a_tampered_manifest_are_refused(tmp_path):
    assert tamper(tmp_path, lambda d, f, i: (d["a"] / "ERROR.txt").write_text("x"))["verdict"] == "STEP01_INCOMPLETE"
    assert tamper(tmp_path / "g", lambda d, f, i: (d["b"] / "nvidia_smi.csv").unlink())["verdict"] == "STEP01_INCOMPLETE"
    def edit(d, f, i):
        p = d["c"] / "states" / "step01__baseline" / "flow_24.forces.csv"
        p.write_text(p.read_text() + "\n")
    assert tamper(tmp_path / "m", edit)["verdict"] == "STEP01_INCOMPLETE"


def test_a_baseline_that_differs_in_one_kernel_only_is_refused_and_names_the_kernel(tmp_path):
    r, *_ = run(tmp_path, break_baseline_kernel="b")
    assert r["verdict"] == "STEP01_INCOMPLETE" and any("kernel b" in x for x in r["integrity"]["failures"]) and not any("kernel a" in x for x in r["integrity"]["failures"])


def test_unresolved_steps_do_not_count_as_stable_and_a_g_hat_of_opposite_sign_is_reported(tmp_path):
    r, *_ = run(tmp_path, amplitude=1e-6)                                       # every response change is far below 10 sigma0
    for s in r["series"].values():
        assert s["sign_stable_through_mm"] is None and len(s["sign_stability"]["unresolved_indices"]) == 5 and s["sign_stability"]["constant_over_resolved_steps"] is False
    r2, *_ = run(tmp_path / "o", ghat_scale=-1.0)
    s = r2["series"]["D0_interface_offset|downforce"]
    assert s["sign_stability"]["same_sign_as_g_hat_over_resolved_steps"] is False and s["agreement_radius_mm"]["30pct"] is None and s["agreement_radius_mm"]["50pct"] is None
    assert all(row["g_sec_over_g_hat"] < 0 for row in s["rows"])


def test_a_nonlinear_combined_response_gives_a_resolved_defect_above_the_interpolation_spread(tmp_path):
    r, *_ = run(tmp_path, curvature=0.4, combo_curvature=0.0)                   # single directions curve; the combination is exactly linear: it cannot match the interpolated sum
    cell = r["combined_directions"]["D1_filtered_seed11+D2_filtered_seed2026"]["downforce|plus"]
    assert cell["prediction_spread_n"] > 0 and cell["additivity"]["defect_exceeds_interpolation_spread_and_resolution"] is True
    assert r["contract_inputs_for_lowdim"]["worst_combined_additivity_relative_defect"]["relative_defect"] > 0.01


def test_the_report_carries_provenance_when_written_by_main(tmp_path, monkeypatch):
    dirs, freeze, inv = SYN.make_all(tmp_path)
    fz = tmp_path / "freeze.json"; fz.write_text(json.dumps(freeze))
    original = A.analyze
    monkeypatch.setattr(A, "analyze", lambda d, f: original(d, f, inventory=inv, formal=SYN.FORMAL))
    target = tmp_path / "a.json"
    monkeypatch.setattr("sys.argv", ["x", "--freeze", str(fz), "--write", str(target), *sum((["--kernel-dir", f"{k}={v}"] for k, v in dirs.items()), [])])
    A.main()
    prov = json.loads(target.read_text())["provenance"]
    assert prov["freeze_sha256"] == A.sha256(fz) and prov["analyzer_sha256"] == A.sha256(Path(A.__file__)) and set(prov["kernel_manifest_sha256"]) == {"a", "b", "c"}
