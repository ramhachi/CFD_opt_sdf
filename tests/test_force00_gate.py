"""Synthetic, falsifiable FORCE-00 gate cases; no solver or GPU is invoked."""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil

import pytest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("force00_gate", ROOT / "scripts/force00_gate.py")


@pytest.fixture
def gate():
    module = importlib.util.module_from_spec(SPEC)
    SPEC.loader.exec_module(module)
    return module


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True) + "\n")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def manifest(repo, directory):
    paths = sorted(p for p in directory.rglob("*") if p.is_file() and p.name != "SHA256SUMS")
    # The repository's registered manifests use repository-relative paths.
    (directory / "SHA256SUMS").write_text("".join(f"{digest(p)}  {p.relative_to(repo)}\n" for p in paths))


@pytest.fixture
def evidence(tmp_path, gate):
    repo = tmp_path / "repo"
    out = repo / "docs/evidence/force00_2026_11"
    out.mkdir(parents=True)
    refs = {}
    for key in gate.EXPECTED_RUNS:
        run, phase, state = key
        grid = "flow_24" if run == "F1" else "flow_32"
        # Nonconstant parent phase values distinguish SD from an accidental mean.
        index = gate.F1_PHASES.index(phase) if run == "F1" else int(phase.removeprefix("k"))
        downforce = 10.0 + index if state == gate.PARENT else 11.0 + index
        legacy_rows = []
        extended_rows = []
        for step, time in enumerate((0.0, 79.0, 90.0, 110.0, 121.0), start=1):
            values = [float(step * 8), time, 2.0, 0.0, -downforce, 2.0, downforce,
                      1.0, 0.0, -downforce, 1.0, 0.0, 0.0]
            fields = [str(v) for v in values]
            legacy_rows.append(",".join(fields))
            extended = fields + [str(v) for v in (2.0, 0.0, -downforce, 2.0, downforce)] * 3
            extended_rows.append(",".join(extended))
        legacy = ",".join(gate.FORCE_COLUMNS) + "\n" + "\n".join(legacy_rows) + "\n"
        extended = ",".join(gate.ALL_COLUMNS) + "\n" + "\n".join(extended_rows) + "\n"
        relative = f"runs/{run}/{state}/{phase}"
        csv = out / (relative + ".csv")
        csv.parent.mkdir(parents=True, exist_ok=True)
        csv.write_text(extended)
        summary = {
            "case_id": grid, "flow_dims": [150, 72, 54] if grid == "flow_24" else [200, 96, 72],
            "flow_spacing_m": 1 / 30 if grid == "flow_24" else 0.025,
            "density_kg_m3": 1.0, "freestream_mps": [1.0, 0.0, 0.0],
            "state_sha256": "a" * 64 if state == gate.PARENT else "b" * 64,
            "phi_fortran_sha256": "c" * 64 if state == gate.PARENT else "d" * 64,
            "canonical_sdf_origin_m": [float(index), 0.0, 0.0],
            "burn_in_t_u_l": 80.0, "t_end_target": 120.0, "sample_every_solver_steps": 8,
            "waterlily_version": "1.8.0", "waterlily_backend": "KernelAbstractions", "gpu_name": "Tesla T4",
            "finite_u": True, "finite_p": True, "finite_forces": True,
            "force_csv_sha256": digest(csv), "steps": 40, "force_samples": 5,
            "t_end_reached": 121.0,
            "force00_cv_box_lower": [7, 7, 7], "force00_cv_box_upper": [40, 40, 40],
        }
        summary_path = out / (relative + ".json")
        write_json(summary_path, summary)
        refs[key] = {"summary": summary, "legacy": legacy.encode(), "grid": grid}
    # The pure gate core accepts an already verified catalog. Its filesystem
    # loader is tested separately against the actual immutable references.
    runs = [{"run": run, "phase_id": phase, "state": state, "grid": refs[key]["grid"],
             "forces_csv": f"runs/{run}/{state}/{phase}.csv", "summary_json": f"runs/{run}/{state}/{phase}.json"}
            for key in gate.EXPECTED_RUNS for run, phase, state in [key]]
    write_json(out / "force00_runs.json", {"schema": "force00_runs_v1", "runs": runs})
    uniform = []
    for grid in ("flow_24", "flow_32"):
        for phase in gate.U1_PHASES:
            uniform.append({"run": "U1", "body": "v18_parent", "grid": grid, "phase_id": phase,
                            "projected_area": 100.0, "cur": [0.1, 0.0, 0.0],
                            "nds": [1e-14, 0.0, 0.0], "cv": [0.0, 0.0, 0.0]})
    for radius in (8, 16, 32):
        for phase in gate.U2_PHASES:
            uniform.append({"run": "U2", "body": "w2a_sphere", "radius_cells": radius, "phase_id": phase,
                            "projected_area": 3.141592653589793 * radius**2, "cur": [0.29, 0.0, 0.0],
                            "nds": [1e-14, 0.0, 0.0], "cv": [0.0, 0.0, 0.0]})
    write_json(out / "uniform_pressure.json", {"schema": "force00_uniform_pressure_v1", "rows": uniform})
    manifest(repo, out)
    return repo, out, refs


def evaluate(gate, evidence, sigma=0.001):
    repo, out, refs = evidence
    return gate.evaluate(out, repo_root=repo, references=refs, sigma_d_n=sigma)


def change_column(gate, evidence, run, column, transform):
    repo, out, _ = evidence
    for item in json.loads((out / "force00_runs.json").read_text())["runs"]:
        if item["run"] != run:
            continue
        csv = out / item["forces_csv"]
        rows = [line.split(",") for line in csv.read_text().splitlines()]
        index = rows[0].index(column)
        for row in rows[1:]:
            row[index] = str(transform(float(row[index]), item))
        csv.write_text("\n".join(",".join(row) for row in rows) + "\n")
        summary = out / item["summary_json"]
        data = json.loads(summary.read_text())
        data["force_csv_sha256"] = digest(csv)
        write_json(summary, data)
    manifest(repo, out)


def test_complete_criteria_and_cv_preferred(gate, evidence):
    result = evaluate(gate, evidence)
    assert result["status"] == "PASS"
    assert result["adopted_readout"] == "R_cv"
    assert result["criteria"]["C1"]["status"] == "PASS"
    assert result["criteria"]["C2"]["R_nds"]["status"] == "PASS"
    assert result["criteria"]["C3"]["R_nds"]["phase_sd_n"] == result["criteria"]["C3"]["R_cur"]["phase_sd_n"]
    assert result["criteria"]["C5"]["R_nds"]["difference_shift_n"] == 0.0


@pytest.mark.parametrize("readout,adopted", [("cv", "R_nds"), ("nds", "R_cv")])
def test_phase_failure_selects_other_readout(gate, evidence, readout, adopted):
    change_column(gate, evidence, "F1", f"{readout}_fz_solver", lambda v, _: v * 1.1)
    change_column(gate, evidence, "F1", f"{readout}_downforce_solver", lambda v, _: v * 1.1)
    result = evaluate(gate, evidence)
    assert result["criteria"]["C3"][f"R_{readout}"]["status"] == "FAIL_PHASE"
    assert result["adopted_readout"] == adopted


def test_c1_compares_bytes_and_stops(gate, evidence):
    # Same float, different bytes: a tolerant numeric comparison must fail here.
    repo, out, _ = evidence
    item = json.loads((out / "force00_runs.json").read_text())["runs"][0]
    csv = out / item["forces_csv"]
    csv.write_text(csv.read_text().replace("8.0,0.0", "8.00,0.0", 1))
    summary = out / item["summary_json"]
    data = json.loads(summary.read_text()); data["force_csv_sha256"] = digest(csv)
    write_json(summary, data); manifest(repo, out)
    result = evaluate(gate, evidence)
    assert result["status"] == "FAIL"
    assert result["criteria"]["C1"]["status"] == "FAIL"
    assert result["adopted_readout"] == "NONE"


def test_c2_recomputes_vector_norm_and_no100x_extra_gate(gate, evidence):
    repo, out, _ = evidence
    path = out / "uniform_pressure.json"
    data = json.loads(path.read_text())
    # Max component is below0.01, vector norm is above0.01.
    data["rows"][0]["nds"] = [0.009, 0.009, 0.0]
    data["max_norm"] = 0.0
    write_json(path, data); manifest(repo, out)
    result = evaluate(gate, evidence)
    assert result["criteria"]["C2"]["R_nds"]["status"] == "FAIL_CLOSURE"
    assert result["adopted_readout"] == "R_cv"
    data["rows"][0]["nds"] = [0.009, 0.0, 0.0]
    write_json(path, data); manifest(repo, out)
    assert evaluate(gate, evidence)["criteria"]["C2"]["R_nds"]["status"] == "PASS"


@pytest.mark.parametrize("offset,expected", [(1.2, "PASS"), (1.6, "PASS"), (2.1, "HOLD"), (-30.0, "FAIL_SIGN")])
def test_c4_sign_and15percent_band(gate, evidence, offset, expected):
    change_column(gate, evidence, "F1", "cv_downforce_solver", lambda v, _: v + offset)
    change_column(gate, evidence, "F1", "cv_fz_solver", lambda v, _: v - offset)
    result = evaluate(gate, evidence)
    row = result["criteria"]["C4"]["R_cv"]
    assert row["status"] == expected
    assert row["within_15_percent"] is (expected == "PASS")
    if offset == 1.6:
        assert row["within_10_percent"] is False
    assert result["criteria"]["C4"]["adoption_relative_band"] == 0.15


def test_c5_descriptive_large_change_does_not_block_adoption(gate, evidence):
    change_column(gate, evidence, "F3", "nds_downforce_solver", lambda v, item: v + (2 if item["state"] != gate.PARENT else 0))
    change_column(gate, evidence, "F3", "nds_fz_solver", lambda v, item: v - (2 if item["state"] != gate.PARENT else 0))
    result = evaluate(gate, evidence)
    assert result["criteria"]["C5"]["R_nds"]["below_sigma_d"] is False
    assert result["readouts"]["R_nds"] == "PASS"
    assert result["adopted_readout"] == "R_cv"


def test_c5_strict_sigma_boundary_and_invalid_sigma(gate, evidence):
    # A zero SD is a valid statistical value; strict '< sigma' is false even
    # for a zero change, and C5 remains descriptive.
    result = evaluate(gate, evidence, sigma=0.0)
    assert result["criteria"]["C5"]["R_nds"]["below_sigma_d"] is False
    assert result["adopted_readout"] == "R_cv"
    for value in (-1.0, float("nan"), float("inf")):
        with pytest.raises(ValueError):
            evaluate(gate, evidence, sigma=value)


def test_incomplete_runs_and_missing_sigma(gate, evidence):
    repo, out, _ = evidence
    assert evaluate(gate, evidence, sigma=None)["status"] == "INCOMPLETE"
    path = out / "force00_runs.json"
    data = json.loads(path.read_text()); data["runs"].pop()
    write_json(path, data); manifest(repo, out)
    result = evaluate(gate, evidence)
    assert result["status"] == "INCOMPLETE"
    assert result["adopted_readout"] == "NONE"
    assert result["missing"]


def test_missing_file_and_uniform_placements_are_incomplete(gate, evidence):
    repo, out, _ = evidence
    path = out / "uniform_pressure.json"
    data = json.loads(path.read_text()); data["rows"].pop()
    write_json(path, data); manifest(repo, out)
    result = evaluate(gate, evidence)
    assert result["status"] == "INCOMPLETE"
    assert result["criteria"]["C2"]["R_nds"]["status"] == "INCOMPLETE"
    path.unlink(); manifest(repo, out)
    assert evaluate(gate, evidence)["status"] == "INCOMPLETE"
    (out / "force00_runs.json").unlink(); manifest(repo, out)
    assert evaluate(gate, evidence)["criteria"]["C1"]["status"] == "INCOMPLETE"


def test_final_solver_step_can_be_sampled_off_cadence(gate, evidence):
    # The registered job samples every8steps OR at the final horizon.
    repo, out, refs = evidence
    item = json.loads((out / "force00_runs.json").read_text())["runs"][0]
    path = out / item["forces_csv"]
    lines = path.read_text().splitlines(); fields = lines[-1].split(",")
    fields[1] = "119.0"; lines[-1] = ",".join(fields)
    fields[0], fields[1] = "41.0", "121.0"; lines.append(",".join(fields))
    path.write_text("\n".join(lines) + "\n")
    summary = out / item["summary_json"]
    data = json.loads(summary.read_text()); data.update(steps=41, force_samples=6, force_csv_sha256=digest(path))
    write_json(summary, data)
    key = (item["run"], item["phase_id"], item["state"])
    legacy = refs[key]["legacy"].splitlines()
    final = legacy[-1].replace(b"40.0,121.0", b"41.0,121.0")
    legacy[-1] = legacy[-1].replace(b"40.0,121.0", b"40.0,119.0")
    refs[key]["legacy"] = b"\n".join([*legacy, final]) + b"\n"
    manifest(repo, out)
    assert evaluate(gate, evidence)["criteria"]["C1"]["status"] == "PASS"
    # An intermediate sample off cadence is never the final-horizon exception.
    lines[2] = lines[2].replace("16.0,79.0", "17.0,79.0", 1)
    path.write_text("\n".join(lines) + "\n"); data["force_csv_sha256"] = digest(path)
    write_json(summary, data); manifest(repo, out)
    with pytest.raises(ValueError, match="cadence"):
        evaluate(gate, evidence)


@pytest.mark.parametrize("defect", ["missing_regular", "missing_first", "steps", "sample_count",
                                  "end_time", "early_endpoint", "steps_type", "count_type"])
def test_f3_history_cadence_and_summary_fail_closed(gate, evidence, defect):
    # F3 has no C1 byte reference: missing samples must fail at the history
    # boundary even when every retained step is divisible by eight.
    repo, out, _ = evidence
    item = next(item for item in json.loads((out / "force00_runs.json").read_text())["runs"]
                if item["run"] == "F3")
    path, summary = out / item["forces_csv"], out / item["summary_json"]
    lines, data = path.read_text().splitlines(), json.loads(summary.read_text())
    if defect in ("missing_regular", "missing_first"):
        del lines[2 if defect == "missing_regular" else 1]
        data["force_samples"] -= 1
    elif defect == "steps":
        data["steps"] = 48
    elif defect == "sample_count":
        data["force_samples"] -= 1
    elif defect == "end_time":
        data["t_end_reached"] = 120.0
    elif defect == "early_endpoint":
        fields = lines[-2].split(","); fields[1] = "120.5"; lines[-2] = ",".join(fields)
    elif defect == "steps_type":
        data["steps"] = 40.0
    else:
        data["force_samples"] = 5.0
    path.write_text("\n".join(lines) + "\n")
    data["force_csv_sha256"] = digest(path)
    write_json(summary, data); manifest(repo, out)
    with pytest.raises(ValueError):
        evaluate(gate, evidence)


def test_none_when_both_readouts_fail(gate, evidence):
    for readout in ("nds", "cv"):
        change_column(gate, evidence, "F1", f"{readout}_downforce_solver", lambda v, _: v * 2)
        change_column(gate, evidence, "F1", f"{readout}_fz_solver", lambda v, _: v * 2)
    result = evaluate(gate, evidence)
    assert result["status"] == "FAIL"
    assert result["adopted_readout"] == "NONE"


def test_hold_blocks_both_without_changing_phase_sd(gate, evidence):
    repo, out, refs = evidence
    # A binary-exact scale avoids an artificial SD ordering from rounding a
    # translated synthetic series; this isolates the C4 HOLD branch.
    for item in json.loads((out / "force00_runs.json").read_text())["runs"]:
        if item["run"] == "F1":
            path = out / item["summary_json"]
            data = json.loads(path.read_text()); data["flow_spacing_m"] = 1 / 32
            write_json(path, data)
            refs[(item["run"], item["phase_id"], item["state"])]["summary"]["flow_spacing_m"] = 1 / 32
    manifest(repo, out)
    for readout in ("nds", "cv"):
        change_column(gate, evidence, "F1", f"{readout}_downforce_solver", lambda v, _: v + 30)
        change_column(gate, evidence, "F1", f"{readout}_fz_solver", lambda v, _: v - 30)
    result = evaluate(gate, evidence)
    assert result["status"] == "HOLD"
    assert result["readouts"] == {"R_nds": "HOLD", "R_cv": "HOLD"}
    assert result["adopted_readout"] == "NONE"


def test_uniform_duplicate_nonfinite_and_sphere_area_rejected(gate, evidence):
    repo, out, _ = evidence
    path = out / "uniform_pressure.json"
    original = json.loads(path.read_text())
    for defect in ("duplicate", "nonfinite", "sphere_area"):
        data = copy.deepcopy(original)
        if defect == "duplicate":
            data["rows"].append(copy.deepcopy(data["rows"][0]))
        elif defect == "nonfinite":
            data["rows"][0]["nds"][0] = float("nan")
        else:
            next(row for row in data["rows"] if row["run"] == "U2")["projected_area"] *= 2
        write_json(path, data); manifest(repo, out)
        with pytest.raises(ValueError):
            evaluate(gate, evidence)


@pytest.mark.parametrize("defect", ["hash", "unknown", "duplicate", "nonfinite", "summary", "cur", "projection", "outside", "box_inset", "box_missing", "box_type"])
def test_fail_closed_invalid_input(gate, evidence, defect):
    repo, out, _ = evidence
    path = out / "force00_runs.json"
    data = json.loads(path.read_text()); item = data["runs"][0]
    if defect == "hash":
        (out / item["forces_csv"]).write_text("tampered")
    elif defect in ("unknown", "duplicate", "outside"):
        if defect == "unknown": item["phase_id"] = "k999"
        if defect == "duplicate": data["runs"].append(copy.deepcopy(item))
        if defect == "outside": item["forces_csv"] = "../../outside.csv"
        write_json(path, data); manifest(repo, out)
    elif defect in ("summary", "box_inset", "box_missing", "box_type"):
        summary = out / item["summary_json"]
        fields = json.loads(summary.read_text())
        if defect == "summary": fields["gpu_name"] = "CPU"
        if defect == "box_inset": fields["force00_cv_box_lower"][0] = 3
        if defect == "box_missing": del fields["force00_cv_box_upper"]
        if defect == "box_type": fields["force00_cv_box_lower"][0] = True
        write_json(summary, fields); manifest(repo, out)
    else:
        column = {"nonfinite": "nds_fx_solver", "cur": "cur_fx_solver", "projection": "cv_drag_solver"}[defect]
        change_column(gate, evidence, "F1", column, lambda v, _: float("nan") if defect == "nonfinite" else v + 1)
    with pytest.raises(ValueError):
        evaluate(gate, evidence)


def test_write_once_refuses_even_before_reading_inputs(gate, evidence):
    repo, out, refs = evidence
    gate.write_gate(out, repo_root=repo, references=refs, sigma_d_n=0.001)
    original = (out / "gate.json").read_bytes()
    (out / "force00_runs.json").unlink()
    with pytest.raises(FileExistsError):
        gate.write_gate(out, repo_root=repo, references=refs, sigma_d_n=0.001)
    assert (out / "gate.json").read_bytes() == original


def test_invalid_derived_value_does_not_create_partial_gate(gate, evidence, monkeypatch):
    _, out, _ = evidence
    monkeypatch.setattr(gate, "evaluate", lambda *args, **kwargs: {"derived_value": float("inf")})
    with pytest.raises(ValueError):
        gate.write_gate(out)
    assert not (out / "gate.json").exists()


@pytest.mark.parametrize("missing_input", ["manifest", "run_catalog", "run_csv"])
def test_cpu_validation_reports_are_not_discovered(gate, evidence, missing_input):
    repo, out, _ = evidence
    reports = repo / "docs/codex/gen01_w1_2026_11_06/reports/wp02_validation"
    # Even a complete, correctly hashed decoy must not fill missing production
    # inputs from a sibling reports directory. The gate reads its root only.
    shutil.copytree(out, reports)
    manifest(repo, reports)
    if missing_input == "manifest":
        (out / "SHA256SUMS").unlink()
    elif missing_input == "run_catalog":
        (out / "force00_runs.json").unlink()
        manifest(repo, out)
    else:
        item = next(item for item in json.loads((out / "force00_runs.json").read_text())["runs"]
                    if item["run"] == "F3")
        (out / item["forces_csv"]).unlink()
        manifest(repo, out)
    result = evaluate(gate, evidence)
    assert result["status"] == "INCOMPLETE"
    assert result["adopted_readout"] == "NONE"
    assert result["missing"]
    assert not (out / "gate.json").exists()


def test_registered_reference_catalog_reads_sha_and_missing_camber_sigma(gate):
    refs, sigma, provenance = gate.registered_references(ROOT)
    assert set(refs) == set(gate.EXPECTED_RUNS)
    assert refs[("F1", "k0", gate.PARENT)]["legacy"].startswith(b"step,t_u_l,")
    assert refs[("F2", "k15", gate.PARENT)]["grid"] == "flow_32"
    assert sigma is None
    assert "camber_m19.7" in provenance["sigma_d_missing"]
    for ref in refs.values():
        if "legacy" not in ref:
            continue
        rows = [dict(zip(gate.FORCE_COLUMNS, map(float, line.decode().split(","))))
                for line in ref["legacy"].splitlines()[1:]]
        summary = ref["summary"]
        assert len(rows) == summary["force_samples"] == (summary["steps"] + 7) // 8
        assert all(row["step"] == min(8 * (index + 1), summary["steps"])
                   for index, row in enumerate(rows))
        assert rows[-1]["t_u_l"] == summary["t_end_reached"] >= 120.0
        assert all(row["t_u_l"] < 120.0 for row in rows[:-1])


def test_production_uniform_provenance_binds_area_sources_and_placements(gate, evidence):
    # Use real registered geometry/phase provenance but synthetic force vectors.
    from force00_uniform_inputs import inputs
    data = inputs()
    refs, _, _ = gate.registered_references(ROOT)
    _, out, _ = evidence
    uniform = json.loads((out / "uniform_pressure.json").read_text())
    uniform.update(waterlily_version="1.8.0", field_type="Float64", source_sha256=dict(data["source_sha256"]),
                   waterlily_source_sha256={name: hashlib.sha256(name.encode()).hexdigest() for name in gate.WATERLILY_SOURCE_FILES})
    for name in gate.UNIFORM_LOCAL_SOURCES:
        uniform["source_sha256"][name] = digest(ROOT / name)
    shifts = {"U1": {r["phase_id"]: r["shift_m"] for r in data["placements"]},
              "U2": {r["phase_id"]: r["shift_m"] for r in data["sphere_placements"]}}
    for row in uniform["rows"]:
        row["shift_m"] = shifts[row["run"]][row["phase_id"]]
        if row["run"] == "U1":
            h = refs[("F1", "k0", gate.PARENT)]["summary"]["flow_spacing_m"] if row["grid"] == "flow_24" else 0.025
            row["projected_area"] = data["planform_area_m2"] / h**2
        else:
            h = 0.5 / row["radius_cells"]
        row["shift_cells"] = [v / h for v in row["shift_m"]]
    gate.validate_uniform_provenance(uniform, ROOT, refs)
    for defect in ("area", "source", "shift", "cells", "type", "waterlily"):
        changed = copy.deepcopy(uniform)
        if defect == "area": changed["rows"][0]["projected_area"] *= 1e12
        if defect == "source": changed["source_sha256"]["julia/CFDSDFWaterLily/src/Forces.jl"] = "0" * 64
        if defect == "shift": changed["rows"][0]["shift_m"][0] += 0.001
        if defect == "cells": changed["rows"][0]["shift_cells"][0] += 0.5
        if defect == "type": changed["field_type"] = "Float32"
        if defect == "waterlily": changed["waterlily_source_sha256"]["Metrics.jl"] = "malformed"
        with pytest.raises(ValueError):
            gate.validate_uniform_provenance(changed, ROOT, refs)


def test_endpoint_clipped_means_reuse_registered_integrator(gate):
    rows = [{key: 0.0 for key in gate.FORCE_COLUMNS} | {"t_u_l": t, "downforce_solver": 3 * t + 2}
            for t in (0.0, 79.0, 100.0, 121.0)]
    assert gate.window_mean(rows, "downforce_solver") == pytest.approx(302.0)
