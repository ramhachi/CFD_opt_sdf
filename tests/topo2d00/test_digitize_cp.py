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
        # Different actual sampling grids make even the zero-Cp lower surfaces
        # independent-content synthetic readings, rather than renamed copies.
        xs = [(i / 10) ** (1 if who == "a" else 2) for i in range(11)]
        for element, pressure in (("main", main), ("flap", flap)):
            write_csv(tmp_path / f"{element}_{who}_upper.csv", [(x, pressure) for x in xs])
            write_csv(tmp_path / f"{element}_{who}_lower.csv", [(x, 0) for x in reversed(xs)])
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
    xs = [0, 0.01, 0.04, 0.1, 0.2, 0.4, 0.55, 0.73, 0.9, 1]
    upper = write_csv(tmp_path / "upper.csv", [(x, 1 + 2 * x) for x in xs])
    lower = write_csv(tmp_path / "lower.csv", [(1 - i / 9, -1) for i in range(10)])
    assert D.integrate_cp(upper, lower, abscissa_chord_m=0.38,
                          reference_chord_m=0.2234, x_extent=[0, 1]) == pytest.approx(3 * 0.38 / 0.2234)
    # Suction below an inverted wing produces positive downforce.
    assert D.integrate_cp(lower, upper, abscissa_chord_m=0.38,
                          reference_chord_m=0.2234, x_extent=[0, 1]) < 0


def test_constant_pressure_closes_and_translation_does_not_change_force(tmp_path):
    upper = write_csv(tmp_path / "up.csv", [(-3 + (i / 9) ** 2, 4) for i in range(10)])
    lower = write_csv(tmp_path / "lo.csv", [(-3 + i / 10, 4) for i in range(11)])
    assert D.integrate_cp(upper, lower, abscissa_chord_m=0.2234,
                          reference_chord_m=0.2234, x_extent=[-3, -2]) == pytest.approx(0, abs=1e-14)


def test_two_digitizations_sum_conservative_sensitivities_without_cancellation(tmp_path):
    manifest = cp_manifest(tmp_path)
    result = run_manifest(tmp_path, manifest)
    ref = result["references"][0]
    assert result["normalization"]["reference_chord_m"] == 0.2234
    assert result["observable"] == ref["observable"] == "pressure_cl"
    assert ref["h_over_c1"] == pytest.approx(0.1 / 0.2234)
    assert ref["h_over_c"] == pytest.approx(0.1 / 0.380)
    assert ref["Cl"] == pytest.approx(2.1 + 0.4)
    assert ref["digitization_sensitivity_abs"] == pytest.approx(0.2 + 0.2)
    assert ref["paired_total_difference_abs"] == pytest.approx(0)
    assert ref["uncertainty"]["total_reference_abs"] is None
    assert ref["uncertainty"]["covers_total_reference"] is False
    assert result["qualification_decided"] is False
    assert result["manifest"]["sha256"] == hashlib.sha256((tmp_path / "input.json").read_bytes()).hexdigest()
    for element in ref["elements"]:
        for surface in ("upper", "lower"):
            assert element["digitizations"][0][surface]["sha256"] != element["digitizations"][1][surface]["sha256"]
        for inputs in element["digitizations"]:
            for surface in ("upper", "lower"):
                inp = inputs[surface]
                assert inp["sha256"] == hashlib.sha256((tmp_path / inp["path"]).read_bytes()).hexdigest()
                assert inp["points"] >= 10


def test_distinct_sampling_contents_may_give_equal_integrals(tmp_path):
    manifest = cp_manifest(tmp_path)
    for element, pressure in (("main", 2.0), ("flap", 1.0)):
        write_csv(tmp_path / f"{element}_b_upper.csv", [((i / 10) ** 2, pressure) for i in range(11)])
    reference = run_manifest(tmp_path, manifest)["references"][0]
    assert reference["Cl"] == pytest.approx(2.5)
    assert reference["digitization_sensitivity_abs"] == pytest.approx(0)


@pytest.mark.parametrize("surface", ["upper", "lower"])
@pytest.mark.parametrize("same_path", [False, True])
def test_copied_reader_csv_is_refused_by_content_sha(tmp_path, surface, same_path):
    manifest = cp_manifest(tmp_path)
    element = manifest["configs"][0]["elements"][0]
    first = element["surfaces"]["a"][surface]
    if same_path:
        element["surfaces"]["b"][surface] = first
    else:
        second = element["surfaces"]["b"][surface]
        (tmp_path / second).write_bytes((tmp_path / first).read_bytes())
        assert first != second
    with pytest.raises(ValueError, match="different.*SHA"):
        run_manifest(tmp_path, manifest)


@pytest.mark.parametrize("element_id,reader", [("main", "a"), ("flap", "b")])
@pytest.mark.parametrize("pressure", [-0.1, 0.0])
def test_nonpositive_individual_element_is_refused_before_averaging(tmp_path, element_id, reader, pressure):
    manifest = cp_manifest(tmp_path)
    # Other elements/readings remain positive, so total/mean checks alone miss
    # this surface-label or reading error.
    write_csv(tmp_path / f"{element_id}_{reader}_upper.csv", [(i / 10, pressure) for i in range(11)])
    with pytest.raises(ValueError, match=f"{element_id}/{reader}.*downforce-positive"):
        run_manifest(tmp_path, manifest)


@pytest.mark.parametrize("reader", ["a", "b"])
@pytest.mark.parametrize("surface", ["upper", "lower"])
@pytest.mark.parametrize("count", [2, 9])
def test_each_physical_surface_requires_ten_points(tmp_path, reader, surface, count):
    manifest = cp_manifest(tmp_path)
    pressure = 2.0 if surface == "upper" else 0.0
    write_csv(tmp_path / f"main_{reader}_{surface}.csv", [(i / (count - 1), pressure) for i in range(count)])
    with pytest.raises(ValueError, match="at least 10 points"):
        run_manifest(tmp_path, manifest)


@pytest.mark.parametrize("reader", ["a", "b"])
def test_swapped_physical_surfaces_are_refused(tmp_path, reader):
    manifest = cp_manifest(tmp_path)
    surfaces = manifest["configs"][0]["elements"][0]["surfaces"][reader]
    surfaces["upper"], surfaces["lower"] = surfaces["lower"], surfaces["upper"]
    with pytest.raises(ValueError, match=f"main/{reader}.*downforce-positive"):
        run_manifest(tmp_path, manifest)


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
    assert increment["from_digitization_sensitivity_abs"] == 0
    assert increment["to_digitization_sensitivity_abs"] == pytest.approx(0.4)
    assert increment["reference_difference_reading_sensitivity_abs"] == pytest.approx(0.4)
    assert increment["threshold_uncertainty_basis"] == "to_reference_digitization_sensitivity_abs"
    assert increment["digitization_exceeds_5_percent"] is True
    assert increment["threshold_fraction"] == 0.05
    assert increment["qualification_decided"] is False


def test_table_15_scalar_does_not_need_fabricated_reader_files(tmp_path):
    manifest = {"kind": "topo2d00_cp_manifest_v1", "reference_chord_m": 0.2234,
                "configs": [table_config()], "increments": []}
    table = run_manifest(tmp_path, manifest)["references"][0]
    assert table["Cl"] == 1.009
    assert table["uncertainty_method"] == "explicit_table_reading_sensitivity"
    assert "digitizations" not in table and "elements" not in table
    assert not list(tmp_path.glob("*.csv"))


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


@pytest.mark.parametrize("mutation,reason", [("duplicate", "abscissa"), ("nonfinite", "nonfinite"),
                                            ("backtracking", "abscissa"), ("short", "at least 10"),
                                            ("extra_column", "exactly two"), ("header", "required CSV header")])
def test_csv_rejects_ambiguous_nonfinite_and_malformed_input(tmp_path, mutation, reason):
    path = tmp_path / "bad.csv"
    rows = [(i / 10, 1.0) for i in range(11)]
    if mutation == "duplicate":
        rows[5] = rows[4]
    elif mutation == "nonfinite":
        rows[5] = (0.5, float("nan"))
    elif mutation == "backtracking":
        rows[5], rows[6] = rows[6], rows[5]
    elif mutation == "short":
        rows = rows[:1]
    write_csv(path, rows, header="x,cp" if mutation == "header" else "x/c,Cp")
    if mutation == "extra_column":
        path.write_text(path.read_text().replace("0.0,1.0\n", "0.0,1.0,extra\n"))
    with pytest.raises(ValueError, match=reason):
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
        write_csv(tmp_path / "main_a_upper.csv", [(0.1 + 0.9 * i / 10, 2) for i in range(11)])
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
    for name, offset in (("a", 0), ("b", 0.2)):
        write_csv(tmp_path / f"{name}.csv", [(0.1, 1 + offset), (0.2, 2 + offset)], header="h/c,Cl")
    manifest["configs"] = [config]
    with pytest.raises(ValueError, match="extrapolat"):
        run_manifest(tmp_path, manifest)
    manifest["configs"] = [table_config()]
    manifest["increments"] = [{"from": "E1_sharp", "to": "missing"}]
    with pytest.raises(ValueError, match="increment"):
        run_manifest(tmp_path, manifest)


def test_five_percent_boundary_zero_increment_and_height_identity(tmp_path):
    first, second = table_config(), table_config()
    first.update(Cl=1.0, reading_sensitivity_abs=0.8)
    second.update(config="E2_sharp", Cl=2.0, reading_sensitivity_abs=0.05)
    manifest = {"kind": "topo2d00_cp_manifest_v1", "reference_chord_m": 0.2234,
                "configs": [first, second], "increments": [{"from": "E1_sharp", "to": "E2_sharp"}]}
    increment = run_manifest(tmp_path, manifest)["increments"][0]
    assert increment["digitization_fraction_of_increment"] == pytest.approx(0.05)
    assert increment["digitization_exceeds_5_percent"] is False  # above 5%, not >= 5%
    assert increment["from_digitization_sensitivity_abs"] == 0.8
    assert increment["reference_difference_reading_sensitivity_abs"] == pytest.approx(0.85)
    second["reading_sensitivity_abs"] = 0.051
    assert run_manifest(tmp_path, manifest)["increments"][0]["digitization_exceeds_5_percent"] is True
    second["Cl"] = 1.0
    increment = run_manifest(tmp_path, manifest)["increments"][0]
    assert increment["zero_increment"] is True
    assert increment["digitization_fraction_of_increment"] is None
    assert increment["digitization_exceeds_5_percent"] is None
    second["height_m"] = 0.08
    with pytest.raises(ValueError, match="same physical height"):
        run_manifest(tmp_path, manifest)


def test_identical_cl_curve_contents_under_different_paths_are_refused(tmp_path):
    manifest = cp_manifest(tmp_path)
    config = table_config()
    config.update(method="cl_curve", height_chord_m=0.2,
                  digitizers=manifest["configs"][0]["digitizers"], independence_note="independent readers",
                  curves={"a": "a.csv", "b": "b.csv"})
    for key in ("Cl", "reading_sensitivity_abs", "reading_sensitivity_note"):
        config.pop(key)
    first = write_csv(tmp_path / "a.csv", [(0.25, 1), (0.75, 3)], header="h/c,Cl")
    (tmp_path / "b.csv").write_bytes(first.read_bytes())
    manifest["configs"] = [config]
    with pytest.raises(ValueError, match="different.*SHA"):
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
