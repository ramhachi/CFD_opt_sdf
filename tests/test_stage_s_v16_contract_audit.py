"""Contract tests for the solver-free v16 Stage S lineage audit."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from cfd_sdf import campaign_assertions as ca  # noqa: E402
from scripts import stage_s_v16_contract_audit_2026_09 as audit  # noqa: E402
from conftest import requires_work  # noqa: E402


MANIFEST = ROOT / "docs/evidence/stage_s_v16_contract_audit_manifest_2026_09.json"
CASE_METADATA = ROOT / "work/stage_s_work_f_v1/baseline/V1/case_metadata.json"


def _recorded_source_project_is_another_root() -> bool:
    """The audit compares metadata["source_project"] (an absolute path baked in at run time) with this checkout's root."""
    return CASE_METADATA.is_file() and json.loads(CASE_METADATA.read_text(encoding="utf-8"))["source_project"] != str(audit.ORIGINAL_SPEC)


def _manifest() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def test_manifest_is_immutable_and_sidecar_matches() -> None:
    manifest = _manifest()
    assert manifest["kind"] == "stage_s_v16_contract_audit_manifest"
    assert manifest["immutable"] is True
    assert manifest["status"] == "registered_solver_free_audit"
    assert manifest["registered_before_computation"] is True
    assert ca.sha256_file(MANIFEST) == MANIFEST.with_suffix(".json.sha256").read_text().strip()


def test_candidate_lineage_and_pq2_non_transfer_are_explicit() -> None:
    manifest = _manifest()
    binding = manifest["candidate_binding"]
    assert binding["same_candidate"] is True
    assert binding["candidate_sha256"] == audit.V16_CANDIDATE_SHA
    assert binding["mismatch_with_pq2_candidate"]["same_candidate"] is False
    assert binding["mismatch_with_pq2_candidate"]["pq2_candidate_sha256"] == audit.PQ2_CANDIDATE_SHA
    assert manifest["stage_v_absolute_reference_path"]["transfer_to_v16"].startswith("forbidden")


def test_realized_boundary_and_field_contract_is_complete() -> None:
    manifest = _manifest()
    boundary = manifest["boundary_contract"]
    assert set(boundary["realized_mesh"]) == {
        "inlet", "outlet", "sideMin", "sideMax", "top", "bottom", "design_candidate"
    }
    assert boundary["realized_mesh"]["sideMin"] == "symmetryPlane"
    assert boundary["realized_fields"]["U"]["inlet"] == "fixedValue"
    assert boundary["realized_fields"]["p"]["outlet"] == "fixedValue"
    assert boundary["explicit_problem_spec_six_patch_contract"] is False
    assert boundary["promotion_required_before_reference_campaign"] is True


def test_audit_is_solver_free_and_retains_raw_mesh_semantics() -> None:
    manifest = _manifest()
    execution = manifest["execution"]
    assert execution["solver_started"] is False
    assert execution["mesh_generation_started"] is False
    assert execution["optimization_campaign_started"] is False
    qualification = manifest["mesh_contract"]["qualification"]
    assert qualification["check_mesh_profile_qualified"] is True
    assert qualification["raw_check_mesh_mesh_ok"] is False
    assert "not a clean mesh claim" in qualification["interpretation"]


@requires_work("work/pq4_1_v16_state_v2/sweep/threshold_0.5/iso_surface.stl")
def test_every_recorded_artifact_hash_is_current() -> None:
    manifest = _manifest()
    for key, ref in manifest["artifacts"].items():
        assert ca.sha256_file(ROOT / ref["path"]) == ref["sha256"], key


@requires_work("work/stage_s_work_f_v1/baseline/V1/case_metadata.json")
@pytest.mark.skipif(_recorded_source_project_is_another_root(), reason="case_metadata.json bakes in the absolute source_project path of another checkout root")
def test_build_manifest_refuses_a_pq2_hash_registration_mismatch(monkeypatch) -> None:
    original = audit.PQ2_CANDIDATE_SHA
    monkeypatch.setattr(audit, "PQ2_CANDIDATE_SHA", audit.V16_CANDIDATE_SHA)
    try:
        try:
            audit.build_manifest()
        except ValueError as exc:
            assert "PQ2 registered candidate hash mismatch" in str(exc)
        else:
            raise AssertionError("candidate collision must fail closed")
    finally:
        monkeypatch.setattr(audit, "PQ2_CANDIDATE_SHA", original)
