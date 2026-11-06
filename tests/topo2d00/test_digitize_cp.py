"""Synthetic reference estimates; no published figure is digitized in tests."""
import copy
import hashlib
import json

import pytest

from scripts.topo2d00 import digitize_cp as D


def write_csv(path, rows, header="x/c,Cp"):
    path.write_text(header + "\n" + "\n".join(f"{x},{y}" for x, y in rows) + "\n")
    return path


def cp_manifest(tmp_path):
    for who, main, flap in (("a", 2.0, 1.0), ("b", 2.2, 0.6)):
        for element, pressure in (("main", main), ("flap", flap)):
            write_csv(tmp_path / f"{element}_{who}_upper.csv", [(0, pressure), (0.2, pressure), (1, pressure)])
            write_csv(tmp_path / f"{element}_{who}_lower.csv", [(1, 0), (0.4, 0), (0, 0)])
    source = {"citation": "synthetic test", "location": "synthetic panel",
              "observable": "centre_section_pressure_integrated", "transition": "unknown"}
    config = {"config": "E2_sharp", "method": "cp", "height_m": 0.1,
              "source": source, "height_mapping_note": "synthetic physical height",
              "abscissa_direction": "global_streamwise", "independence_note": "independent synthetic readers",
              "digitizers": [{"id": "a", "operator": "reader A", "tool": "tool"},
                             {"id": "b", "operator": "reader B", "tool": "tool"}],
              "elements": [{"id": name, "abscissa_chord_m": chord, "x_extent": [0, 1],
                            "coverage_note": "complete projected contour; vertical closing caps",
                            "surfaces": {who: {side: f"{name}_{who}_{side}.csv" for side in ("upper", "lower")}
                                         for who in ("a", "b")}}
                           for name, chord in (("main", 0.2234), ("flap", 0.1117))]}
    return {"kind": "topo2d00_cp_manifest_v1", "reference_chord_m": 0.2234,
            "configs": [config], "increments": []}


def run_manifest(tmp_path, manifest):
    path = tmp_path / "input.json"
    path.write_text(json.dumps(manifest))
    return D.build_reference(path)


def test_trapezoids_use_physical_upper_lower_and_global_x(tmp_path):
    upper = write_csv(tmp_path / "upper.csv", [(0, 1), (0.1, 1.2), (1, 3)])
    lower = write_csv(tmp_path / "lower.csv", [(1, -1), (0.3, -1), (0, -1)])
    assert D.integrate_cp(upper, lower, abscissa_chord_m=0.38,
                          reference_chord_m=0.2234, x_extent=[0, 1]) == pytest.approx(3 * 0.38 / 0.2234)
    # Suction below an inverted wing produces positive downforce.
    assert D.integrate_cp(lower, upper, abscissa_chord_m=0.38,
                          reference_chord_m=0.2234, x_extent=[0, 1]) < 0


def test_constant_pressure_closes_and_translation_does_not_change_force(tmp_path):
    upper = write_csv(tmp_path / "up.csv", [(-3, 4), (-2.3, 4), (-2, 4)])
    lower = write_csv(tmp_path / "lo.csv", [(-3, 4), (-2, 4)])
    assert D.integrate_cp(upper, lower, abscissa_chord_m=0.2234,
                          reference_chord_m=0.2234, x_extent=[-3, -2]) == pytest.approx(0, abs=1e-14)


def test_two_digitizations_sum_conservative_sensitivities_without_cancellation(tmp_path):
    manifest = cp_manifest(tmp_path)
    result = run_manifest(tmp_path, manifest)
    ref = result["references"][0]
    assert result["normalization"]["reference_chord_m"] == 0.2234
    assert ref["Cl"] == pytest.approx(2.1 + 0.4)
    assert ref["digitization_sensitivity_abs"] == pytest.approx(0.2 + 0.2)
    assert ref["paired_total_difference_abs"] == pytest.approx(0)
    assert ref["uncertainty"]["total_reference_abs"] is None
    assert ref["uncertainty"]["covers_total_reference"] is False
    assert result["qualification_decided"] is False
    assert result["manifest"]["sha256"] == hashlib.sha256((tmp_path / "input.json").read_bytes()).hexdigest()
    for element in ref["elements"]:
        for inputs in element["digitizations"]:
            for surface in ("upper", "lower"):
                inp = inputs[surface]
                assert inp["sha256"] == hashlib.sha256((tmp_path / inp["path"]).read_bytes()).hexdigest()


def table_config():
    return {"config": "E1_sharp", "method": "tabulated_cl", "height_m": 0.1,
            "source": {"citation": "Zerihan (2001), university thesis",
                       "location": "Table 15, printed p179 / PDF p197; audited EVAL-VALID-01",
                       "observable": "centre_section_pressure_integrated", "transition": "unknown"},
            "height_mapping_note": "h/c1=0.448 is the published rounded ratio for the h=100 mm comparison",
            "coefficient_chord_m": 0.2234, "coefficient_sign": "downforce=-Fz",
            "Cl": 1.009, "reading_sensitivity_abs": 0.0,
            "reading_sensitivity_note": "Exact transcription of printed digits; total error remains unknown"}


def test_table_15_is_scalar_provenance_and_fixed_five_percent_is_descriptive(tmp_path):
    manifest = cp_manifest(tmp_path)
    manifest["configs"].insert(0, table_config())
    manifest["increments"] = [{"from": "E1_sharp", "to": "E2_sharp"}]
    result = run_manifest(tmp_path, manifest)
    table = result["references"][0]
    increment = result["increments"][0]
    assert table["Cl"] == 1.009
    assert table["method"] == "tabulated_cl"
    assert "elements" not in table
    assert "Table 15" in table["source"]["location"]
    assert table["uncertainty"]["total_reference_abs"] is None
    assert increment["delta_Cl"] == pytest.approx(2.5 - 1.009)
    assert increment["digitization_sensitivity_abs"] == pytest.approx(0.4)
    assert increment["digitization_exceeds_5_percent"] is True
    assert increment["threshold_fraction"] == 0.05
    assert increment["qualification_decided"] is False


def test_tabulated_coefficient_and_two_cl_curves_use_common_chord(tmp_path):
    manifest = cp_manifest(tmp_path)
    config = table_config()
    config.update(method="cl_curve", coefficient_chord_m=0.38, height_chord_m=0.2,
                  digitizers=manifest["configs"][0]["digitizers"], independence_note="separate curve readings",
                  curves={"a": "a.csv", "b": "b.csv"})
    for key in ("Cl", "reading_sensitivity_abs", "reading_sensitivity_note"):
        config.pop(key)
    write_csv(tmp_path / "a.csv", [(0.25, 1), (0.75, 3)], header="h/c,Cl")
    write_csv(tmp_path / "b.csv", [(0.75, 3.2), (0.25, 1.2)], header="h/c,Cl")
    manifest["configs"] = [config]
    result = run_manifest(tmp_path, manifest)["references"][0]
    assert result["Cl"] == pytest.approx(2.1 * 0.38 / 0.2234)
    assert result["digitization_sensitivity_abs"] == pytest.approx(0.2 * 0.38 / 0.2234)
    config = table_config()
    config["coefficient_chord_m"] = 0.38
    manifest["configs"] = [config]
    assert run_manifest(tmp_path, manifest)["references"][0]["Cl"] == pytest.approx(1.009 * 0.38 / 0.2234)


@pytest.mark.parametrize("content", ["x/c,Cp\n0,0\n0,1\n", "x/c,Cp\n0,nan\n1,1\n",
                                     "x/c,Cp\n0,0\n1,1\n0.5,1\n", "x/c,Cp\n0,0\n",
                                     "x/c,Cp\n0,0,extra\n1,1\n", "x,cp\n0,0\n1,1\n"])
def test_csv_rejects_ambiguous_nonfinite_and_malformed_input(tmp_path, content):
    path = tmp_path / "bad.csv"
    path.write_text(content)
    with pytest.raises(ValueError):
        D.read_csv(path)


@pytest.mark.parametrize("mutation", ["inclined_local", "missing_surface", "partial_coverage", "unknown_method",
                                      "one_digitizer", "same_reader_tool", "bad_chord", "balance", "missing_csv",
                                      "missing_extent", "unknown_kind", "duplicate_config", "duplicate_increment"])
def test_manifest_fails_closed(tmp_path, mutation):
    manifest = cp_manifest(tmp_path)
    config = manifest["configs"][0]
    element = config["elements"][0]
    if mutation == "inclined_local":
        config["abscissa_direction"] = "local_chord"
    elif mutation == "missing_surface":
        element["surfaces"]["a"].pop("lower")
    elif mutation == "partial_coverage":
        write_csv(tmp_path / "main_a_upper.csv", [(0.1, 2), (1, 2)])
    elif mutation == "unknown_method":
        config["method"] = "balance"
    elif mutation == "one_digitizer":
        config["digitizers"].pop()
    elif mutation == "same_reader_tool":
        config["digitizers"][1].update(operator="reader A", tool="tool")
    elif mutation == "bad_chord":
        element["abscissa_chord_m"] = -0.38
    elif mutation == "balance":
        config["source"]["observable"] = "balance_CL"
    elif mutation == "missing_csv":
        (tmp_path / "main_a_upper.csv").unlink()
    elif mutation == "missing_extent":
        element.pop("x_extent")
    elif mutation == "unknown_kind":
        manifest["kind"] = "other"
    elif mutation == "duplicate_config":
        manifest["configs"].append(copy.deepcopy(config))
    elif mutation == "duplicate_increment":
        manifest["configs"].insert(0, table_config())
        manifest["increments"] = [{"from": "E1_sharp", "to": "E2_sharp"}] * 2
    with pytest.raises((ValueError, FileNotFoundError)):
        run_manifest(tmp_path, manifest)


def test_curve_extrapolation_and_unknown_increment_are_rejected(tmp_path):
    manifest = cp_manifest(tmp_path)
    config = table_config()
    config.update(method="cl_curve", coefficient_chord_m=0.2234, height_chord_m=0.2234,
                  digitizers=manifest["configs"][0]["digitizers"], independence_note="independent readers",
                  curves={"a": "a.csv", "b": "b.csv"})
    for key in ("Cl", "reading_sensitivity_abs", "reading_sensitivity_note"):
        config.pop(key)
    for name in ("a", "b"):
        write_csv(tmp_path / f"{name}.csv", [(0.1, 1), (0.2, 2)], header="h/c,Cl")
    manifest["configs"] = [config]
    with pytest.raises(ValueError, match="extrapolat"):
        run_manifest(tmp_path, manifest)
    manifest["configs"] = [table_config()]
    manifest["increments"] = [{"from": "E1_sharp", "to": "missing"}]
    with pytest.raises(ValueError, match="increment"):
        run_manifest(tmp_path, manifest)


def test_five_percent_boundary_zero_increment_and_height_identity(tmp_path):
    first, second = table_config(), table_config()
    first.update(Cl=1.0, reading_sensitivity_abs=0.025)
    second.update(config="E2_sharp", Cl=2.0, reading_sensitivity_abs=0.025)
    manifest = {"kind": "topo2d00_cp_manifest_v1", "reference_chord_m": 0.2234,
                "configs": [first, second], "increments": [{"from": "E1_sharp", "to": "E2_sharp"}]}
    increment = run_manifest(tmp_path, manifest)["increments"][0]
    assert increment["digitization_fraction_of_increment"] == pytest.approx(0.05)
    assert increment["digitization_exceeds_5_percent"] is False  # above 5%, not >= 5%
    second["reading_sensitivity_abs"] = 0.026
    assert run_manifest(tmp_path, manifest)["increments"][0]["digitization_exceeds_5_percent"] is True
    second["Cl"] = 1.0
    increment = run_manifest(tmp_path, manifest)["increments"][0]
    assert increment["zero_increment"] is True
    assert increment["digitization_fraction_of_increment"] is None
    assert increment["digitization_exceeds_5_percent"] is None
    second["height_m"] = 0.08
    with pytest.raises(ValueError, match="same physical height"):
        run_manifest(tmp_path, manifest)


def test_cli_writes_json_and_refuses_to_overwrite_input_or_result(tmp_path):
    run_manifest(tmp_path, cp_manifest(tmp_path))
    out = tmp_path / "reference.json"
    assert D.main([str(tmp_path / "input.json"), "--out", str(out)]) == 0
    assert json.loads(out.read_text())["references"][0]["Cl"] == pytest.approx(2.5)
    with pytest.raises((FileExistsError, SystemExit)):
        D.main([str(tmp_path / "input.json"), "--out", str(out)])


def test_relative_manifest_records_canonical_path_and_original_bytes(tmp_path, monkeypatch):
    manifest = cp_manifest(tmp_path)
    path = tmp_path / "input.json"
    payload = (json.dumps(manifest, indent=3) + "\n").encode("utf-8")
    path.write_bytes(payload)
    monkeypatch.chdir(tmp_path)
    result = D.build_reference("input.json")
    assert result["manifest"]["path"] == str(path.resolve())
    assert result["manifest"]["sha256"] == hashlib.sha256(payload).hexdigest()
    assert path.read_bytes() == payload
    assert result["references"][0]["Cl"] == pytest.approx(2.5)
