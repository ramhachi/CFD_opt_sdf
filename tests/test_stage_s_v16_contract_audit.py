"""Contract tests for the solver-free v16 Stage S lineage audit."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from cfd_sdf import campaign_assertions as ca  # noqa: E402
from scripts import stage_s_v16_contract_audit_2026_09 as audit  # noqa: E402


MANIFEST = ROOT / "docs/evidence/stage_s_v16_contract_audit_manifest_2026_09.json"


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


def test_every_recorded_artifact_hash_is_current() -> None:
    manifest = _manifest()
    for key, ref in manifest["artifacts"].items():
        assert ca.sha256_file(ROOT / ref["path"]) == ref["sha256"], key


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
