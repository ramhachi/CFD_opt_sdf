"""Deterministic synthetic case records; no OpenFOAM or gmsh invocation."""
from __future__ import annotations

import hashlib
import copy
import importlib.util
import json
import shutil
import sys
import time
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/topo2d00"))
import collect_rans as C


def case_fixture(tmp_path, *, config="E2_sharp", realisation=0, signal=None,
                 status="COMPLETED", mode="production", n_layers=4):
    key = dict(config=config, model="sa-wf", family="fine30", realisation=realisation)
    folder = tmp_path / C.run_id(key)
    folder.mkdir()
    t = np.arange(1, 5001, dtype=float)
    cl = signal(t) if signal else np.full(t.shape, 2.0)
    files, force_files = {}, {}
    denominator = .5*C.NORMALIZATION["rho_kg_m3"]*C.NORMALIZATION["U_inf_m_s"]**2*C.NORMALIZATION["reference_area_m2"]
    n = int(config[1])
    parts = (("airfoil", 1.0),) if n == 1 else (("airfoil", .7), ("airfoil_2", .3))
    for obj, scale in (("total", 1.0), *parts):
        p = folder / f"coefficients/{obj}/0/coefficient.dat"
        p.parent.mkdir(parents=True)
        p.write_text("# Time Cd Cl\n" + "".join(f"{a:g} {0.1*scale:.12g} {b*scale:.12g}\n" for a, b in zip(t, cl)))
        files[obj] = [{"path": str(p.relative_to(folder)), "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}]
        force = p.with_name("force.dat")
        force.write_text("# Time total_x total_y total_z pressure_x pressure_y pressure_z viscous_x viscous_y viscous_z\n" + "".join(
            f"{a:g} {denominator*.1*scale:.12g} {-denominator*b*scale:.12g} 0 "
            f"{denominator*.08*scale:.12g} {-denominator*b*scale*.95:.12g} 0 "
            f"{denominator*.02*scale:.12g} {-denominator*b*scale*.05:.12g} 0\n" for a,b in zip(t,cl)))
        force_files[obj] = [{"path": str(force.relative_to(folder)), "sha256": C.sha256(force)}]
    mesh = folder / "mesh.msh"
    mesh.write_text(f"test mesh fixture {config} realisation {realisation}\n")
    record = {
        "schema_version": "topo2d00-case-v1", "id": C.run_id(key), **key,
        "mode": mode, "status": status, "mesh_msh_sha256": C.sha256(mesh),
        "n_layers": n_layers,
        "mesh_file": "mesh.msh", "geometry_sha256": "a" * 64,
        "normalization": C.NORMALIZATION,
        "convergence_policy": C.CONVERGENCE,
        "force_convention": C.FORCE_CONVENTION,
        "elements": [{"name": "main" if i == 0 else "flap", "patch": patch} for i, (patch, _) in enumerate(parts)],
        "coefficient_files": files, "force_files": force_files, "stages": [], "solver": {"nan_in_log": False},
        "check_mesh": {"mesh_ok": True, "failed_check_counts": []},
    }
    p = folder / "case_result.json"
    p.write_text(json.dumps(record))
    return p, key


def test_complete_case_coefficients_closure_and_schema(tmp_path):
    path, key = case_fixture(tmp_path)
    got = C.collect([path], expected=[key])
    assert got["schema_version"] == "topo2d00-rans-v1"
    assert got["complete"] and got["missing_runs"] == []
    row = got["results"][0]
    assert row["config"] == "E2_sharp" and row["realisation"] == 0
    assert row["convergence"]["state"] == "settled"
    assert row["convergence"]["raw_class"] == "VALID"
    assert row["pressure_convergence"]["state"] == "settled"
    assert row["coefficients"]["total"] == pytest.approx({"Cl": 2.0, "Cd": 0.1})
    assert row["observable"] == "pressure_cl"
    assert row["n_layers"] == 4
    assert row["pressure_coefficients"]["total"] == pytest.approx({"Cl": 1.9, "Cd": .08})
    assert row["viscous_coefficients"]["total"] == pytest.approx({"Cl": .1, "Cd": .02})
    assert sum(e["Cl"] for e in row["coefficients"]["elements"]) == pytest.approx(2.0)
    assert row["usable"]
    schema = json.loads(C.SCHEMA.read_text())
    assert schema["properties"]["schema_version"]["const"] == got["schema_version"]
    assert got["normalization"]["reference_area_m2"] == schema["$defs"]["normalization"]["properties"]["reference_area_m2"]["const"]
    assert set(schema["required"]) == set(got)
    assert schema["additionalProperties"] is False
    assert set(schema["$defs"]["result"]["required"]) == set(row)
    json.dumps(got, allow_nan=False)


def test_missing_is_explicit_not_a_zero_coefficient(tmp_path):
    path, key = case_fixture(tmp_path)
    missing = {**key, "realisation": 1}
    got = C.collect([path], expected=[key, missing])
    assert not got["complete"]
    assert got["missing_runs"] == [missing]
    assert len(got["results"]) == 1


def test_missing_cli_writes_diagnostic_and_returns_failure(tmp_path):
    path, key = case_fixture(tmp_path)
    plan = tmp_path / "plan.json"
    plan.write_text(json.dumps({"runs": [key, {**key, "realisation": 1}]}))
    out = tmp_path / "rans_results.json"
    assert C.main([str(path), "--plan", str(plan), "--measurements-only", "--out", str(out)]) == 2
    assert out.is_file() and not json.loads(out.read_text())["complete"]


@pytest.mark.parametrize("signal,state,raw", [
    (lambda t: 2 + .08*np.sin(2*np.pi*t/20), "not_settled", "UNSTEADY"),
    (lambda t: 2 + .08*np.sin(2*np.pi*t/40), "not_settled", "SOLVER_FAIL"),
    (lambda t: 2 + t*.0001, "not_settled", "SOLVER_FAIL"),
    (lambda t: np.full(t.shape, np.nan), "diverged", "SOLVER_FAIL"),
    (lambda t: np.full(t.shape, 101.), "diverged", "SOLVER_FAIL"),
])
def test_iteration_classification_reuses_t20c(tmp_path, signal, state, raw):
    p, key = case_fixture(tmp_path, signal=signal)
    row = C.collect([p], expected=[key])["results"][0]
    assert row["convergence"]["state"] == state
    assert row["convergence"]["raw_class"] == raw
    assert row["convergence"]["coordinate"] == "SIMPLE iteration (not physical time)"
    assert "frequency_unit" not in row["convergence"]["statistics"]
    assert not row["usable"]
    json.dumps(row, allow_nan=False)


@pytest.mark.parametrize("signal", [
    lambda t: 2 + .006*(-1.)**t,
    lambda t: 2 + .008*np.sin(2*np.pi*t/7),
    lambda t: 2 + np.random.default_rng(37).normal(0, .004, len(t)),
])
def test_review_low_amplitude_periodic_and_noise_histories_are_settled(tmp_path, signal):
    p, key = case_fixture(tmp_path, signal=signal)
    row = C.collect([p], expected=[key])["results"][0]
    assert row["convergence"]["state"] == "settled"
    assert row["convergence"]["raw_class"] == "VALID"
    assert row["convergence"]["statistics"]["Cl"]["tail_rel_std"] <= .00301
    assert row["usable"]


def test_manifest_and_collector_share_registered_policy():
    import t2d_foam_case as F
    assert C.CONVERGENCE is F.CONVERGENCE
    assert C.CONVERGENCE["unsteady_raw_tail_relative_std"] == .005
    assert "T2-0c" in C.CONVERGENCE["rule_source"]


def test_family_layer_count_is_fixed_across_configs_and_models(tmp_path):
    p, a = case_fixture(tmp_path, config="E1_sharp", n_layers=4)
    q, b = case_fixture(tmp_path, config="E2_sharp", n_layers=3)
    with pytest.raises(ValueError, match="n_layers.*fine30"):
        C.collect([p, q], expected=[a, b])


def test_missing_layer_count_on_meshed_case_fails_closed(tmp_path):
    p, key = case_fixture(tmp_path)
    record = json.loads(p.read_text())
    record.pop("n_layers")
    p.write_text(json.dumps(record))
    with pytest.raises(ValueError, match="n_layers"):
        C.collect([p], expected=[key])


def test_duplicate_key_and_unknown_run_fail_closed(tmp_path):
    p, key = case_fixture(tmp_path)
    other = tmp_path / "duplicate"
    other.mkdir()
    q = other / "case_result.json"
    q.write_bytes(p.read_bytes())
    with pytest.raises(ValueError, match="duplicate"):
        C.collect([p, q], expected=[key])
    with pytest.raises(ValueError, match="unexpected"):
        C.collect([p], expected=[{**key, "realisation": 1}])


@pytest.mark.parametrize("kind", ["history", "mesh", "missing", "normalization", "status", "closure", "path", "smoke"])
def test_bad_completed_inputs_fail_closed(tmp_path, kind):
    p, key = case_fixture(tmp_path)
    r = json.loads(p.read_text())
    if kind in ("history", "missing", "closure"):
        h = p.parent / r["coefficient_files"]["airfoil"][0]["path"]
        if kind == "history":
            h.write_text(h.read_text().replace("1 0.07 1.4", "1 0.07 1.5"))
        elif kind == "missing":
            h.unlink()
        else:
            h.write_text(h.read_text().replace(" 1.4\n", " 1.5\n"))
            r["coefficient_files"]["airfoil"][0]["sha256"] = C.sha256(h)
    elif kind == "mesh":
        (p.parent / "mesh.msh").write_text("changed")
    elif kind == "normalization":
        r["normalization"] = {**r["normalization"], "reference_chord_m": .38}
    elif kind == "status":
        r["status"] = "MAGIC_STATUS"
    elif kind == "path":
        r["coefficient_files"]["total"][0]["path"] = "../outside.dat"
    else:
        r["mode"] = "smoke"
    p.write_text(json.dumps(r))
    with pytest.raises((ValueError, FileNotFoundError)):
        C.collect([p], expected=[key])


def test_failed_and_lost_runs_have_no_usable_values(tmp_path):
    p, key = case_fixture(tmp_path, status="GENERATOR_FAILED")
    r = json.loads(p.read_text())
    for name in ("mesh_file", "mesh_msh_sha256", "coefficient_files"):
        r.pop(name)
    p.write_text(json.dumps(r))
    row = C.collect([p], expected=[key])["results"][0]
    assert row["convergence"]["state"] == "unavailable"
    assert row["coefficients"]["total"] is None
    assert row["mesh_msh_sha256"] is None and not row["usable"]


def test_config_element_count_must_match(tmp_path):
    p, key = case_fixture(tmp_path)
    r = json.loads(p.read_text())
    r["elements"].pop()
    p.write_text(json.dumps(r))
    with pytest.raises(ValueError, match="element"):
        C.collect([p], expected=[key])


@pytest.mark.parametrize("status,solver,state", [
    ("simpleFoam_FAILED", {}, "not_settled"),
    ("simpleFoam_FAILED", {"sigfpe": True}, "diverged"),
    ("simpleFoam_TIMEOUT", {}, "unavailable"),
    ("simpleFoam_TIMEOUT", {"nan_in_log": True}, "diverged"),
    ("simpleFoam_TIMEOUT", {"sigfpe": True}, "diverged"),
    ("simpleFoam_TIMEOUT", {"foam_fatal": True}, "diverged"),
])
@pytest.mark.parametrize("rows", [None, 0, 1])
def test_failed_solver_can_have_no_or_truncated_history(tmp_path, status, solver, state, rows):
    p, key = case_fixture(tmp_path, status=status)
    r = json.loads(p.read_text())
    r["solver"] = solver
    if rows is None:
        r.pop("coefficient_files")
        r.pop("force_files")
    else:
        for entries in r["coefficient_files"].values():
            h = p.parent / entries[0]["path"]
            h.write_text("# Time Cd Cl\n" + ("1 .1 2\n" if rows else ""))
            entries[0]["sha256"] = C.sha256(h)
    p.write_text(json.dumps(r))
    row = C.collect([p], expected=[key])["results"][0]
    assert row["convergence"]["state"] == state
    assert row["coefficients"]["total"] is None and not row["usable"]


@pytest.mark.parametrize("config,usable", [("E2_sharp", False), ("E1", True)])
def test_selected_observable_controls_validity_when_pressure_and_viscous_cancel(tmp_path, config, usable):
    p, key = case_fixture(tmp_path, config=config)
    r = json.loads(p.read_text())
    q = .5*30**2*.0004468
    for name, entries in r["force_files"].items():
        f = p.parent / entries[0]["path"]
        text = f.read_text().splitlines()
        a = np.loadtxt(text[1:], ndmin=2)
        scale = 1. if config == "E1" else {"total": 1., "airfoil": .7, "airfoil_2": .3}[name]
        a[:, 5] -= q*scale*a[:, 0]*.0001
        a[:, 8] = a[:, 2] - a[:, 5]
        f.write_text(text[0]+"\n"+"\n".join(" ".join(f"{v:.12g}" for v in row) for row in a)+"\n")
        entries[0]["sha256"] = C.sha256(f)
    p.write_text(json.dumps(r))
    row = C.collect([p], expected=[key])["results"][0]
    assert row["convergence"]["state"] == "settled"
    assert row["pressure_convergence"]["state"] == "not_settled"
    assert row["usable"] is usable
    if usable:
        out = C.to_wp4(C.collect([p], expected=[key]), reference_fixture(tmp_path), geometry_sha256=geometry_identity_fixture())
        force = out["cells"][0]["realisations"][0]["forces"][config]
        assert force["observable"] == "total_cl" and force["downforce"] == pytest.approx(2.)


def test_plan_binds_geometry_identity_in_addition_to_run_key(tmp_path):
    p, key = case_fixture(tmp_path)
    with pytest.raises(ValueError, match="geometry_sha256 differs"):
        C.collect([p], expected=[{**key, "geometry_sha256": "b"*64}])


def reference_fixture(tmp_path):
    from scripts.topo2d00 import digitize_cp as CP
    folder = tmp_path / "reference"
    folder.mkdir()
    for name, cp in (("main", 1.9), ("flap", .05*.2234/.1657)):
        for reader in ("a", "b"):
            for side, value in (("upper", cp), ("lower", 0.)):
                # Independent grids, identical known integrals, SHA-distinct content.
                points = np.linspace(0, 1, 10 if reader == "a" else 11)
                (folder / f"{name}_{reader}_{side}.csv").write_text("x/c,Cp\n" + "".join(f"{x:.12g},{value:.12g}\n" for x in points))
    source = {"citation": "synthetic reference", "url": "https://example.invalid/synthetic-reference", "location": "test panels", "observable": "centre_section_pressure_integrated", "transition": "synthetic"}
    single = {"config": "E1_sharp", "method": "tabulated_cl", "height_m": .1, "height_mapping_note": "synthetic same physical height", "source": source,
              "Cl": 1., "coefficient_chord_m": .2234, "coefficient_sign": "downforce=-Fz", "reading_sensitivity_abs": 0., "reading_sensitivity_note": "synthetic exact input"}
    double = {"config": "E2_sharp", "method": "cp", "height_m": .1, "height_mapping_note": "synthetic same physical height", "source": source,
              "abscissa_direction": "global_streamwise", "independence_note": "two independent synthetic operators",
              "digitizers": [{"id": "a", "operator": "A", "tool": "test"}, {"id": "b", "operator": "B", "tool": "test"}],
              "elements": [{"id": name, "abscissa_chord_m": chord, "x_extent": [0, 1], "coverage_note": "complete synthetic contour",
                            "surfaces": {reader: {side: f"{name}_{reader}_{side}.csv" for side in ("upper", "lower")} for reader in ("a", "b")}}
                           for name, chord in (("main", .2234), ("flap", .1657))]}
    manifest = {"kind": "topo2d00_cp_manifest_v1", "reference_chord_m": .2234, "configs": [single, double], "increments": [{"from": "E1_sharp", "to": "E2_sharp"}]}
    p = folder / "manifest.json"
    p.write_text(json.dumps(manifest))
    return CP.build_reference(p)


def geometry_identity_fixture():
    return {config: "a"*64 for config in C.CONFIGS}


def test_wp4_export_uses_pressure_for_tr_and_total_for_thick(tmp_path):
    paths, expected = [], []
    for i in range(8):
        for config, cl in (("E1_sharp", 1.), ("E2_sharp", 2.)):
            p, key = case_fixture(tmp_path, config=config, realisation=i, signal=lambda t, cl=cl: np.full(t.shape, cl))
            paths.append(p)
            expected.append(key)
    p, key = case_fixture(tmp_path, config="E1")
    paths.append(p)
    expected.append(key)
    detailed = C.collect(paths, expected=expected)
    reference = reference_fixture(tmp_path)
    out = C.to_wp4(detailed, reference, geometry_sha256=geometry_identity_fixture())
    assert out["schema"] == "topo2d00-rans-results-v1"
    assert out["reference"]["delta_cl"] == pytest.approx(.95)
    assert out["reference"]["digitizing_uncertainty"] == 0
    cell = out["cells"][0]
    assert len(cell["realisations"]) == 8
    first = cell["realisations"][0]
    assert first["forces"]["E1_sharp"]["downforce"] == pytest.approx(.95)
    assert first["forces"]["E2_sharp"]["downforce"] == pytest.approx(1.9)
    assert first["forces"]["E1"]["downforce"] == pytest.approx(2.)
    assert first["status"]["E2"] == "INCOMPLETE" and first["forces"]["E2"] is None
    assert first["mesh_sha256"]["E2"] is None
    assert first["diagnostics"]["E1_sharp"]["observable"] == "pressure_cl"
    assert first["forces"]["E1_sharp"]["observable"] == "pressure_cl"
    assert first["forces"]["E1"]["observable"] == "total_cl"
    assert out["reference"]["observable"] == "pressure_cl"
    assert out["provenance"]["component_by_config"]["E1_sharp"] == "pressure_cl"
    assert out["coefficient_reference"]["h_over_c1"] == pytest.approx(.1/.2234)
    assert out["coefficient_reference"]["h_over_c"] == pytest.approx(.1/.380)
    assert cell["cell_summary"]["E1_sharp"]["status"] == "COMPLETE"
    assert out["provenance"]["reference_estimate"]["references"][0]["uncertainty"]["covers_total_reference"] is False
    assert out["provenance"]["geometry_sha256"] == geometry_identity_fixture()
    records = out["reference"]["source"]["digitization_records"]
    assert len(records) >= 8 and len({r["path"] for r in records}) == len(records)
    assert out["reference"]["source"]["url"] == "https://example.invalid/synthetic-reference"
    for record in records:
        assert set(record) == {"path", "sha256", "method"}
        assert Path(record["path"]).is_absolute() and "#" not in record["path"]
        assert C.sha256(Path(record["path"])) == record["sha256"]
        assert record["method"]
    assert "freeze_sha256" not in out["provenance"]
    schema = json.loads(C.SHARED_SCHEMA.read_text())
    assert set(schema["required"]) <= set(out)
    # Exercise the real consumer when WP4 is integrated or its sibling worktree
    # is available. This is read-only and never evaluates scientific run data.
    candidates = [ROOT / "scripts/topo2d00/analyze.py", ROOT.parent / "CFD2026_09-wp-04-topo2d-waterlily/scripts/topo2d00/analyze.py"]
    consumer = next((x for x in candidates if x.is_file()), None)
    if consumer:
        spec = importlib.util.spec_from_file_location("wp4_consumer_under_test", consumer)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.validate_input({"schema": "topo2d00-input-v1", "identity_valid": True, "cap_hit": False, "controls": {}, "waterlily": [], "rans": out})
        assert module.tr00(out)["cells"]["sa-wf/fine30"]["label"] == "TR00_PASS_RATIO"


def test_duplicate_meshes_keep_point_estimates_and_block_ratio_intervals(tmp_path):
    paths, expected = [], []
    for i in range(8):
        p, key = case_fixture(tmp_path, realisation=i)
        (p.parent / "mesh.msh").write_text("same deterministic mesh\n")
        record = json.loads(p.read_text())
        record["mesh_msh_sha256"] = C.sha256(p.parent / "mesh.msh")
        p.write_text(json.dumps(record))
        paths.append(p)
        expected.append(key)
    measurements = C.collect(paths, expected=expected)
    out = C.to_wp4(measurements, reference_fixture(tmp_path), geometry_sha256=geometry_identity_fixture())
    cell = out["cells"][0]
    summary = cell["cell_summary"]["E2_sharp"]
    assert summary["status"] == "DEGENERATE_REALISATIONS"
    assert summary["distinct_meshes"] == 1
    assert summary["point_estimate"]["downforce"] == pytest.approx(1.9)
    assert summary["ci90"] is None
    assert summary["ratio_test_status"] == "INCOMPLETE"
    assert all(r["status"]["E2_sharp"] == "INCOMPLETE" for r in cell["realisations"])
    assert all(r["forces"]["E2_sharp"]["downforce"] == pytest.approx(1.9) for r in cell["realisations"])


def test_thickening_alone_keeps_pressure_and_total_observables_separate(tmp_path):
    sharp, a = case_fixture(tmp_path, config="E1_sharp", signal=lambda t: np.full(t.shape, 2.))
    thick, b = case_fixture(tmp_path, config="E1", signal=lambda t: np.full(t.shape, 3.))
    measurements = C.collect([sharp, thick], expected=[a, b])
    out = C.to_wp4(measurements, reference_fixture(tmp_path), geometry_sha256=geometry_identity_fixture())
    descriptors = {d["observable"]: d for d in out["cells"][0]["thickening_alone"] if d["to"] == "E1"}
    assert descriptors["pressure_cl"]["point_estimate"]["downforce"] == pytest.approx(.95)
    assert descriptors["total_cl"]["point_estimate"]["downforce"] == pytest.approx(1.)
    assert all(d["from"] == "E1_sharp" and d["paired_realisations"] == 1 and d["ci90"] is None for d in descriptors.values())


def test_shared_export_refuses_wrong_observable_and_layer_mismatch(tmp_path):
    p, key = case_fixture(tmp_path)
    measurements = C.collect([p], expected=[key])
    measurements["results"][0]["observable"] = "total_cl"
    with pytest.raises(ValueError, match="observable"):
        C.to_wp4(measurements, reference_fixture(tmp_path), geometry_sha256=geometry_identity_fixture())


@pytest.mark.parametrize("mutation", ["normalization", "sign", "observable", "height", "zero", "wrong_increment", "sensitivity", "duplicate_config"])
def test_wp4_reference_export_fails_closed(tmp_path, mutation):
    p, key = case_fixture(tmp_path)
    measurements = C.collect([p], expected=[key])
    reference = reference_fixture(tmp_path)
    if mutation == "normalization":
        reference["normalization"]["reference_chord_m"] = .38
    elif mutation == "sign":
        reference["normalization"]["sign"] = "lift=+Fz"
    elif mutation == "observable":
        reference["normalization"]["observable"] = "balance_CL"
    elif mutation == "height":
        reference["references"][0]["height_m"] = .08
    elif mutation == "zero":
        reference["increments"][0]["delta_Cl"] = 0
    elif mutation == "wrong_increment":
        reference["increments"][0]["from"] = "E1"
    elif mutation == "sensitivity":
        reference["increments"][0]["digitization_sensitivity_abs"] = -.1
    else:
        reference["references"].append(copy.deepcopy(reference["references"][0]))
    with pytest.raises(ValueError):
        C.to_wp4(measurements, reference, geometry_sha256=geometry_identity_fixture())


def test_cli_combines_tr_and_main_plans_for_actual_wp4_export(tmp_path):
    sharp, a = case_fixture(tmp_path)
    thick, b = case_fixture(tmp_path, config="E1")
    plans = []
    for i, key in enumerate((a, b)):
        path = tmp_path / f"plan{i}.json"
        path.write_text(json.dumps({"runs": [{**key, "geometry_sha256": "a"*64}]}))
        plans.append(path)
    reference = tmp_path / "reference.json"
    reference.write_text(json.dumps(reference_fixture(tmp_path)))
    out = tmp_path / "rans_results.json"
    geometry_plan = tmp_path / "geometry_plan.json"
    geometry_plan.write_text(json.dumps({"geometry_input_sha256": geometry_identity_fixture(), "runs": []}))
    assert C.main([str(sharp), str(thick), "--plan", str(plans[0]), "--plan", str(plans[1]), "--geometry-plan", str(geometry_plan),
                   "--reference", str(reference), "--out", str(out)]) == 0
    result = json.loads(out.read_text())
    assert result["schema"] == "topo2d00-rans-results-v1"
    assert result["provenance"]["measurements"]["expected_runs"] == 2
    assert len(result["cells"][0]["realisations"]) == 8


@pytest.mark.parametrize("bad", ["url_missing", "url_invalid", "csv_changed", "csv_missing", "reused_csv", "copied_csv", "geometry_missing", "geometry_conflict"])
def test_formal_export_requires_real_reference_artifacts_and_all_geometry(tmp_path, bad):
    p, key = case_fixture(tmp_path)
    measurements = C.collect([p], expected=[key])
    reference = reference_fixture(tmp_path)
    geometry = geometry_identity_fixture()
    if bad == "url_missing":
        reference["references"][0]["source"].pop("url")
    elif bad == "url_invalid":
        reference["references"][0]["source"]["url"] = "unknown"
    elif bad in ("csv_changed", "csv_missing"):
        csv = tmp_path / "reference/main_a_upper.csv"
        csv.write_text("changed") if bad == "csv_changed" else csv.unlink()
    elif bad == "reused_csv":
        ds = reference["references"][1]["elements"][0]["digitizations"]
        ds[1]["upper"] = dict(ds[0]["upper"])
    elif bad == "copied_csv":
        ds = reference["references"][1]["elements"][0]["digitizations"]
        destination = tmp_path / "reference" / ds[1]["upper"]["path"]
        source = tmp_path / "reference" / ds[0]["upper"]["path"]
        destination.write_bytes(source.read_bytes())
        ds[1]["upper"]["sha256"] = C.sha256(destination)
    elif bad == "geometry_missing":
        geometry = None
    else:
        geometry["E2_sharp"] = "b"*64
    with pytest.raises((ValueError, FileNotFoundError)):
        C.to_wp4(measurements, reference, geometry_sha256=geometry)


def test_curve_artifacts_and_relative_paths_are_resolved_from_cp_manifest(tmp_path, monkeypatch):
    from scripts.topo2d00 import digitize_cp as CP
    reference_fixture(tmp_path)
    manifest_path = tmp_path / "reference/manifest.json"
    manifest = json.loads(manifest_path.read_text())
    single = manifest["configs"][0]
    for key in ("Cl", "reading_sensitivity_abs", "reading_sensitivity_note"):
        single.pop(key)
    single.update(method="cl_curve", height_chord_m=.2234,
                  digitizers=manifest["configs"][1]["digitizers"], independence_note="independent synthetic curve readings",
                  curves={reader: f"single_{reader}.csv" for reader in ("a", "b")})
    for reader in ("a", "b"):
        points = np.linspace(.25, .75, 10 if reader == "a" else 11)
        (manifest_path.parent / f"single_{reader}.csv").write_text("h/c,Cl\n" + "".join(f"{x:.12g},1\n" for x in points))
    manifest_path.write_text(json.dumps(manifest))
    reference = CP.build_reference(manifest_path)
    p, key = case_fixture(tmp_path)
    measurements = C.collect([p], expected=[key])
    elsewhere = tmp_path / "other_cwd"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    out = C.to_wp4(measurements, reference, geometry_sha256=geometry_identity_fixture())
    records = out["reference"]["source"]["digitization_records"]
    assert {Path(r["path"]).name for r in records if "cl_curve" in r["method"]} == {"single_a.csv", "single_b.csv"}
    assert all(Path(r["path"]).is_absolute() for r in records)


def test_geometry_plans_supply_unrun_main_geometry_and_source_identity(tmp_path):
    p, key = case_fixture(tmp_path)
    measurements = C.collect([p], expected=[key])
    reference = reference_fixture(tmp_path)
    plans = [{"geometry_input_sha256": {c: "a"*64 for c in ("E1_sharp", "E2_sharp")},
              "source_commit": "c"*40, "source_dirty": True, "bundle_sha256": "d"*64, "input_sha256": {"scripts/topo2d00/collect_rans.py": "e"*64}},
             {"geometry_input_sha256": {c: "a"*64 for c in ("E1", "E2", "E3", "E3_sharp")}, "ready_for_execution": False}]
    out = C.to_wp4(measurements, reference, plans=plans)
    assert out["provenance"]["geometry_sha256"] == geometry_identity_fixture()
    assert out["provenance"]["study_geometry_sha256"]["E3_sharp"] == "a"*64
    assert out["provenance"]["source_commit"] == "c"*40
    assert out["provenance"]["source_identity"][0]["source_dirty"] is True
    assert out["cells"][0]["realisations"][0]["status"]["E3"] == "INCOMPLETE"
    assert "freeze_sha256" not in out["provenance"]


def test_actual_kernel_runtime_records_are_preserved_when_available(tmp_path):
    p, key = case_fixture(tmp_path)
    output = tmp_path / "kernel_output"
    kept = output / "cases" / p.parent.name
    kept.parent.mkdir(parents=True)
    shutil.move(str(p.parent), kept)
    environment = output / "environment.json"
    install = output / "install.json"
    environment.write_text(json.dumps({"python": "synthetic runtime", "source_commit": "f"*40,
                                       "source_dirty": True, "source_archive_sha256": "a"*64}))
    install.write_text(json.dumps({"foamVersion": "OpenFOAM-v2512", "gmsh": "4.15.2", "scope": "synthetic fixture"}))
    measurements = C.collect([kept / p.name], expected=[key])
    out = C.to_wp4(measurements, reference_fixture(tmp_path), geometry_sha256=geometry_identity_fixture())
    assert out["provenance"]["source_commit"] == "f"*40
    records = out["provenance"]["runtime_records"]
    assert {Path(r["path"]).name for r in records} == {"environment.json", "install.json"}
    assert all(C.sha256(Path(r["path"])) == r["sha256"] for r in records)
    assert "freeze_sha256" not in out["provenance"]


def _synthetic_driver(tmp_path, monkeypatch, *, nonfinite=False, proxy_failure=False, generator_failure=False, mesh_failure=False):
    """Exercise generation/mesh/continuation plumbing without external processes."""
    import run_rans as R
    output = tmp_path / "output"
    (output / "work").mkdir(parents=True)
    helper, calls = R.inherited_runner(), []
    spec = {**C.expected_runs()[0], "mode": "production", "iters": 5000, "cont_iters": 15000,
            "case_cap_s": 9000, "geometry_file": "geometry/E1_sharp.json", "geometry_sha256": "a"*64,
            "elements": [{"name": "main", "patch": "airfoil"}]}

    def generate(command, **kwargs):
        case = Path(command[command.index("--out")+1])
        (case / "system").mkdir(parents=True)
        (case / "system/controlDict").write_text("startFrom startTime;\nendTime 5000;\n")
        (case / "mesh.msh").write_text("synthetic mesh")
        (case / "case_manifest.json").write_text(json.dumps({
            "geometry_sha256": spec["geometry_sha256"], "n_layers": 4, "convergence": C.CONVERGENCE,
            "mesh_quality_failures": ["skew_boundary (UNVERIFIED)"] if proxy_failure else []}))
        return type("Result", (), {"returncode": 1 if generator_failure else 0, "stdout": "generated", "stderr": ""})()

    def timed(name, command, case, timeout):
        calls.append(name)
        if name == "gmshToFoam":
            (case / "constant/polyMesh").mkdir(parents=True)
            (case / "constant/polyMesh/boundary").write_text("\n".join(f"{p} {{ type patch; }}" for p in ("airfoil", "front", "back", "ground")))
        elif name == "checkMesh":
            (case / "log.checkMesh").write_text("Failed 1 mesh checks.\n" if mesh_failure else "cells: 2000\nMesh OK.\n")
        else:
            assert name == "simpleFoam", "settled or nonfinite initial history must not continue"
            q = .5*30**2*.0004468
            cl = float("nan") if nonfinite else 2.
            for coeff_name, force_name in (("forceCoeffs", "forces"), ("forceCoeffs_airfoil", "forces_airfoil")):
                cf = case / "postProcessing" / coeff_name / "0"
                ff = case / "postProcessing" / force_name / "0"
                cf.mkdir(parents=True)
                ff.mkdir(parents=True)
                (cf / "coefficient.dat").write_text("# Time Cd Cl\n" + "".join(f"{i} .1 {cl}\n" for i in range(1, 5001)))
                (ff / "force.dat").write_text("# Time total_x total_y total_z pressure_x pressure_y pressure_z viscous_x viscous_y viscous_z\n" + "".join(
                    f"{i} {q*.1} {-q*cl} 0 {q*.08} {-q*cl*.95} 0 {q*.02} {-q*cl*.05} 0\n" for i in range(1, 5001)))
            (case / "log.simpleFoam").write_text("Time = 5000\n")
        return {"stage": name, "returncode": 0, "timed_out": False, "wall_s": .1}

    monkeypatch.setattr(R.subprocess, "run", generate)
    monkeypatch.setattr(helper, "timed_run", timed)
    result = R.run_case(spec, ROOT, output, time.monotonic()+10000, helper)
    path = output / "cases" / R._spec_id(spec) / "case_result.json"
    return result, C.collect([path], expected=[spec]), calls


def test_nonfinite_initial_history_is_diverged_without_continuation(tmp_path, monkeypatch):
    result, measurements, calls = _synthetic_driver(tmp_path, monkeypatch, nonfinite=True)
    assert result["status"] == "SOLVER_DIVERGED"
    assert not result["force_values_finite"]
    assert calls == ["gmshToFoam", "checkMesh", "simpleFoam"]
    assert measurements["results"][0]["convergence"]["state"] == "diverged"
    assert measurements["results"][0]["convergence"]["raw_class"] == "SOLVER_FAIL"


@pytest.mark.parametrize("status", ["COMPLETED", "simpleFoam_TIMEOUT", "SOLVER_TIMEOUT_PARTIAL"])
def test_nonfinite_row_remains_a_result_even_with_a_short_or_timed_out_history(tmp_path, status):
    p, key = case_fixture(tmp_path, status=status)
    record = json.loads(p.read_text())
    for entries in record["coefficient_files"].values():
        path = p.parent / entries[0]["path"]
        path.write_text("# Time Cd Cl\n1 .1 nan\n")
        entries[0]["sha256"] = C.sha256(path)
    p.write_text(json.dumps(record))
    row = C.collect([p], expected=[key])["results"][0]
    assert row["status"] == "SOLVER_DIVERGED"
    assert row["convergence"]["state"] == "diverged"
    assert row["convergence"]["raw_class"] == "SOLVER_FAIL"
    assert row["coefficients"]["total"] is None


def test_quality_proxy_is_informational_when_checkmesh_accepts(tmp_path, monkeypatch):
    result, measurements, calls = _synthetic_driver(tmp_path, monkeypatch, proxy_failure=True)
    assert result["status"] == "COMPLETED"
    assert result["mesh_proxy_failures"]
    assert measurements["results"][0]["usable"]
    assert calls == ["gmshToFoam", "checkMesh", "simpleFoam"]


@pytest.mark.parametrize("failure", ["generator_failure", "mesh_failure"])
def test_generator_and_mesh_failures_remain_mesh_failed(tmp_path, monkeypatch, failure):
    result, measurements, calls = _synthetic_driver(tmp_path, monkeypatch, **{failure: True})
    assert result["status"] == "MESH_FAILED"
    assert measurements["results"][0]["status"] == "MESH_FAILED"
    assert measurements["results"][0]["convergence"]["raw_class"] == "MESH_FAILED"
    assert "simpleFoam" not in calls
    out = C.to_wp4(measurements, reference_fixture(tmp_path), geometry_sha256=geometry_identity_fixture())
    assert out["cells"][0]["realisations"][0]["status"]["E1_sharp"] == "MESH_FAILED"
