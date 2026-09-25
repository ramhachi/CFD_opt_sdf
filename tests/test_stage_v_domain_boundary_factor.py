"""Contract tests for the PQ2 Stage V domain/boundary factor campaign."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from cfd_sdf import campaign_assertions as ca  # noqa: E402

PQ2_MANIFEST = ROOT / "docs/evidence/stage_v_domain_boundary_factor_manifest_2026_09.json"
RUN_MANIFEST = ROOT / "docs/evidence/stage_v_domain_boundary_factor_run_manifest_2026_09.json"
EVIDENCE = ROOT / "docs/evidence/stage_v_domain_boundary_factor_2026_09.json"
FIXED_DOMAIN_EVIDENCE = ROOT / "docs/evidence/stage_v_fixed_domain_grid_study_2026_09.json"
BASE_SPEC = ROOT / "work/stage_sv_laminar/project_matched_re_laminar.yaml"
EXT_SPEC = ROOT / "work/stage_v_domain_boundary_factor_2026_09/specs/project_matched_re_laminar_domain_extended_v1.yaml"


def _script_module():
    spec = importlib.util.spec_from_file_location(
        "pq2", ROOT / "scripts/run_stage_v_domain_boundary_factor_2026_09.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_registered_run_manifest_contract():
    pq2 = json.loads(PQ2_MANIFEST.read_text())
    manifest = json.loads(RUN_MANIFEST.read_text())
    assert manifest["kind"] == "stage_v_domain_boundary_factor_run_manifest"
    assert manifest["registered_before_computation"] is True
    assert manifest["pq2_manifest"]["sha256"] == ca.sha256_file(PQ2_MANIFEST)
    assert manifest["fixed_domain_evidence"]["sha256"] == ca.sha256_file(FIXED_DOMAIN_EVIDENCE)
    assert manifest["baseline"]["qualified"] is True
    assert manifest["budget"] == {"max_new_runs": 2, "v3_runs": 0, "note": "V2 level only"}
    treatments = {entry["name"]: entry for entry in manifest["treatments"]}
    assert set(treatments) == {"far_field_domain_extension", "top_pressure_outlet"}
    extension = treatments["far_field_domain_extension"]
    assert extension["far_field_faces"] == ["inlet", "outlet", "sideMin", "sideMax", "top"]
    assert extension["ground_face"] == "bottom"
    assert ca.sha256_file(ROOT / extension["extended_spec"]["path"]) == extension["extended_spec"]["sha256"]
    fixed = json.loads(FIXED_DOMAIN_EVIDENCE.read_text())["fixed_conditions"]
    assert fixed["domain_lower_m"] == [-1.0, -0.8, -0.6]
    assert fixed["domain_upper_m"] == [2.0, 0.8, 0.6]
    assert extension["extended_spec"]["lower_m"] == [-1.8, -1.6, -0.6]
    assert extension["extended_spec"]["upper_m"] == [2.8, 1.6, 1.4]
    top = treatments["top_pressure_outlet"]
    assert top["top_patch"] == {"U": "zeroGradient", "p": "fixedValue uniform 0"}
    for name, record in manifest["candidate"].items():
        if isinstance(record, dict) and "sha256" in record:
            assert ca.sha256_file(ROOT / record["path"]) == record["sha256"]


def test_extended_spec_diff_and_top_block_helper():
    module = _script_module()
    extended = module._extended_spec()
    base = json.loads(json.dumps(__import__("yaml").safe_load(BASE_SPEC.read_text())))
    assert extended["grid"]["domain_bounds_m"]["lower"] == [-1.8, -1.6, -0.6]
    assert extended["grid"]["domain_bounds_m"]["upper"] == [2.8, 1.6, 1.4]
    assert extended["problem_id"] == base["problem_id"] + "_domain_extended_v1"
    diff = sorted(key for key in set(base) | set(extended) if base.get(key) != extended.get(key))
    assert diff == ["grid", "problem_id"]
    boundary_text = (ROOT / "work/stage_v_fixed_domain_2026_09/opt_q100_b0_step0_try0_block/V2/constant/polyMesh/boundary").read_text()
    start, end = module._top_block(boundary_text)
    block = boundary_text.splitlines()[start : end + 1]
    assert block[0].strip() == "top"
    assert any("symmetryPlane" in line for line in block)


def test_extended_domain_reuses_baseline_location_in_mesh():
    pq2 = _script_module()
    assert pq2._location_in_mesh(pq2.BASELINE_CASE) == pytest.approx((-0.7, 0.0, 0.18))


def test_extended_case_bundle_uses_declared_grid_without_sdf_arrays():
    pq2 = _script_module()
    spec = pq2.load_problem_spec(pq2.EXT_SPEC)
    config = pq2.problem_spec_to_project_config(
        spec, candidate_stl=pq2.CANDIDATE, voxel_size_m=pq2.V2_VOXEL_M
    )
    bundle = pq2._declared_domain_bundle(config)
    assert bundle.grid.shape == (185, 129, 81)
    assert bundle.grid.bounds[0].tolist() == pytest.approx([-1.8, -1.6, -0.6])
    assert bundle.grid.bounds[1].tolist() == pytest.approx([2.8, 1.6, 1.4])
    assert bundle.arrays == {}


def test_treatment_cases_match_the_registered_definition():
    manifest = json.loads(RUN_MANIFEST.read_text())
    treatments = {entry["name"]: entry for entry in manifest["treatments"]}
    t2_case = ROOT / treatments["top_pressure_outlet"]["case_dir"]
    qualification = json.loads((t2_case / "stage_v_qualification.json").read_text())
    assert qualification["qualified"] is True
    boundary = (t2_case / "constant/polyMesh/boundary").read_text()
    start, end = _script_module()._top_block(boundary)
    block = "\n".join(boundary.splitlines()[start : end + 1])
    assert "type            patch;" in block
    assert "symmetryPlane" not in block
    assert "top { type zeroGradient; }" in (t2_case / "0/U").read_text()
    assert "top { type fixedValue; value uniform 0; }" in (t2_case / "0/p").read_text()
    t1_case = ROOT / treatments["far_field_domain_extension"]["case_dir"]
    t1 = json.loads((t1_case / "stage_v_qualification.json").read_text())
    assert t1["qualified"] is True
    assert t1["check_mesh"]["total_cells"] > qualification["check_mesh"]["total_cells"]


def test_registered_pq2_evidence_decision():
    manifest = json.loads(RUN_MANIFEST.read_text())
    evidence = json.loads(EVIDENCE.read_text())
    assert evidence["run_manifest"]["sha256"] == ca.sha256_file(RUN_MANIFEST)
    assert evidence["baseline"]["qualified"] is True
    bounds = manifest["metric"]["bounds"]
    assert bounds["downforce_absolute"] == 0.005
    assert bounds["drag_relative"] == 0.02
    assert set(evidence["rows"]) == {"far_field_domain_extension", "top_pressure_outlet"}
    for row in evidence["rows"].values():
        assert row["stationarity_qualified"] is True
        assert row["delta_downforce"] == pytest.approx(
            row["treatment"]["downforce"] - evidence["baseline"]["downforce"]
        )
        assert row["relative_Cd_change"] == pytest.approx(
            (row["treatment"]["Cd"] - evidence["baseline"]["Cd"]) / evidence["baseline"]["Cd"]
        )
        assert row["downforce_beyond_bound"] == (abs(row["delta_downforce"]) > bounds["downforce_absolute"])
        assert row["drag_beyond_bound"] == (abs(row["relative_Cd_change"]) > bounds["drag_relative"])
    registered = evidence["registered_factors_moving_downforce"]
    expected = [
        name
        for name, row in evidence["rows"].items()
        if row["downforce_beyond_bound"] and row["stationarity_qualified"]
    ]
    assert registered == expected
    assert evidence["summary"]["v3_runs"] == 0
    if registered:
        assert evidence["decision"].startswith("register the moving factor")
    else:
        assert "registered bound" in evidence["decision"]
