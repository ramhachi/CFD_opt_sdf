"""Contract and evidence checks for the v16 outer-condition ladder."""

from __future__ import annotations

import json
from pathlib import Path

from cfd_sdf import campaign_assertions as ca

ROOT = Path(__file__).resolve().parents[1]
CONTINUATION_MANIFEST = ROOT / "docs/evidence/stage_v_v16_domain_continuation_3p2_run_manifest_2026_09.json"
CONTINUATION_EVIDENCE = ROOT / "docs/evidence/stage_v_v16_domain_continuation_3p2_2026_09.json"
FARFIELD_MANIFEST = ROOT / "docs/evidence/stage_v_v16_far_field_contract_run_manifest_v2_2026_09.json"
FARFIELD_EVIDENCE = ROOT / "docs/evidence/stage_v_v16_far_field_contract_v2_2026_09.json"
FARFIELD_AUDIT = ROOT / "docs/evidence/stage_v_v16_far_field_contract_audit_2026_09.json"


def test_final_domain_continuation_is_registered_and_no_go():
    manifest = json.loads(CONTINUATION_MANIFEST.read_text(encoding="utf-8"))
    evidence = json.loads(CONTINUATION_EVIDENCE.read_text(encoding="utf-8"))
    assert manifest["registered_before_computation"] is True
    assert manifest["status"] == "registered_not_run"
    assert manifest["treatment"]["extended_spec"]["extension_m"] == 3.2
    assert evidence["summary"] == {
        "adjacent_transition_within_bound": False,
        "qualified": True,
        "stage_s_s2_allowed": False,
    }
    assert ca.sha256_file(CONTINUATION_MANIFEST) == CONTINUATION_MANIFEST.with_suffix(".json.sha256").read_text().strip()
    assert ca.sha256_file(CONTINUATION_EVIDENCE) == CONTINUATION_EVIDENCE.with_suffix(".json.sha256").read_text().strip()


def test_mixed_far_field_contract_is_same_mesh_and_audited():
    manifest = json.loads(FARFIELD_MANIFEST.read_text(encoding="utf-8"))
    evidence = json.loads(FARFIELD_EVIDENCE.read_text(encoding="utf-8"))
    audit = json.loads(FARFIELD_AUDIT.read_text(encoding="utf-8"))
    assert manifest["registered_before_computation"] is True
    assert manifest["status"] == "registered_not_run"
    assert set(manifest["treatment"]["outer_patches"]) == {"inlet", "outlet", "sideMin", "sideMax", "top"}
    boundary_contract = manifest["treatment"]["boundary_contract"]
    assert all(boundary_contract[patch]["mesh"] == "patch" for patch in manifest["treatment"]["outer_patches"])
    assert boundary_contract["bottom"]["mesh"] == "wall"
    assert boundary_contract["design_candidate"]["mesh"] == "wall"
    assert evidence["summary"] == {
        "qualified": True,
        "stage_s_s2_allowed": False,
        "within_registered_band": False,
    }
    assert audit["status"] == "pass"
    assert audit["checks"] == {
        "fresh_canonical_force_histories": True,
        "no_solver_started_during_registration": True,
        "only_registered_boundary_types_changed": True,
        "same_candidate": True,
        "same_domain_and_mesh": True,
    }
    assert audit["boundary_identity"]["treatment_U"]["top"] == "freestreamVelocity"
    assert audit["boundary_identity"]["treatment_p"]["top"] == "freestreamPressure"
    assert ca.sha256_file(FARFIELD_AUDIT) == FARFIELD_AUDIT.with_suffix(".json.sha256").read_text().strip()
