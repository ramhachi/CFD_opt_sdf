"""Contract tests for the Stage S Work F0 registration (no OpenFOAM runs)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from cfd_sdf import campaign_assertions as ca  # noqa: E402
from cfd_sdf.problem_spec import load_problem_spec  # noqa: E402

MANIFEST = ROOT / "docs/evidence/stage_s_work_f_manifest_2026_09.json"
PREFLIGHT = ROOT / "docs/evidence/stage_s_work_f_v1_preflight_2026_09.json"
MESH = ROOT / "docs/evidence/stage_s_work_f_v1_mesh_2026_09.json"
BASELINE = ROOT / "docs/evidence/stage_s_baseline_v16_v2_2026_09.json"
SPEC = ROOT / "work/stage_sv_laminar/project_matched_re_laminar.yaml"


def _manifest() -> dict:
    return json.loads(MANIFEST.read_text())


def test_manifest_and_sidecar_are_consistent():
    manifest = _manifest()
    assert manifest["kind"] == "stage_s_work_f_manifest_v1"
    assert manifest["immutable"] is True
    assert manifest["status"] == "registered_preflight_pending"
    sidecar = MANIFEST.with_suffix(".json.sha256").read_text().strip()
    assert sidecar == ca.sha256_file(MANIFEST)


def test_registration_binds_the_baseline_and_response_identities():
    manifest = _manifest()
    baseline = json.loads(BASELINE.read_text())
    assert manifest["baseline"]["sha256"] == ca.sha256_file(BASELINE)
    assert baseline["gate"]["ready_for_stage_s"] is True
    spec = load_problem_spec(SPEC)
    responses = {response.id: response for response in spec.responses}
    assert manifest["response_identities"]["drag"]["direction"] == list(responses["drag"].direction)
    assert manifest["response_identities"]["downforce"]["direction"] == list(
        responses["downforce"].direction
    )
    assert manifest["response_identities"]["downforce"]["objective_sign"] == -1
    assert manifest["expected_case"]["force_reference"]["lift_dir"] == [0.0, 0.0, 1.0]
    assert manifest["level"] == {"name": "V1", "voxel_size_m": 0.05}
    assert ca.sha256_file(ROOT / manifest["preflight"]["script_path"]) == manifest["preflight"]["script_sha256"]


def test_preflight_artifact_passed_and_matches_the_manifest():
    preflight = json.loads(PREFLIGHT.read_text())
    assert preflight["manifest"]["sha256"] == ca.sha256_file(MANIFEST)
    assert preflight["baseline"]["sha256"] == ca.sha256_file(BASELINE)
    assert preflight["case"]["pass"] is True
    assert preflight["case"]["failed_checks"] == []
    assert preflight["clearance"]["qualified"] is True
    assert preflight["summary"]["preflight_pass"] is True
    assert preflight["summary"]["mesh_allowed"] is True
    assert preflight["summary"]["solver_started"] is False
    case_dir = ROOT / preflight["case"]["case_dir"]
    assert ca.sha256_file(case_dir / "case_metadata.json") == preflight["case"]["metadata_sha256"]


def test_mesh_evidence_passed_without_starting_the_solver():
    evidence = json.loads(MESH.read_text())
    assert evidence["manifest"]["sha256"] == ca.sha256_file(MANIFEST)
    assert evidence["preflight"]["sha256"] == ca.sha256_file(PREFLIGHT)
    assert evidence["openfoam_run"]["returncode"] == 0
    assert evidence["openfoam_run"]["timed_out"] is False
    assert evidence["check_mesh"]["qualified"] is True
    assert evidence["check_mesh"]["profile_id"] == "stage_v_qualification_v1"
    assert evidence["check_mesh"]["failed_check_lines"] == [
        "Concave cells (using face planes) found, number of cells: 2441"
    ]
    assert evidence["check_mesh"]["concave_cell_fraction"] <= 0.08
    assert evidence["summary"]["solver_allowed"] is True
    assert evidence["summary"]["solver_started"] is False
