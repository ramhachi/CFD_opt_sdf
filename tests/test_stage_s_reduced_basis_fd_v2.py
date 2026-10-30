"""Contract tests for the profile-aware Stage S v2 S0R/S1R slice."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from cfd_sdf import campaign_assertions as ca  # noqa: E402
import register_stage_s_reduced_basis_fd_v2_2026_09 as registration  # noqa: E402


def _manifest() -> dict:
    return json.loads(registration.MANIFEST.read_text(encoding="utf-8"))


def test_v2_contract_binds_profile_domain_and_downforce_objective():
    manifest = _manifest()
    assert manifest["kind"] == "stage_s_reduced_basis_fd_v2_manifest"
    assert manifest["status"] == "registered_preflight_pending"
    assert manifest["immutable"] is True
    assert manifest["stage_v_reference"]["working_domain_bounds_m"] == {
        "lower": [-2.5, -1.2, -0.9],
        "upper": [2.5, 1.2, 0.9],
    }
    assert manifest["stage_v_reference"]["candidate_sha256"] == (
        "5e6d210794b55a11f3dc76b8be37eeb39d27579b341212939a1c2a63d2fb8d11"
    )
    assert manifest["physical_profile"]["sha256"] == (
        "a84670733ad5009ee57e84b9ee40b19da3254aae45846e5fb7a7f3ae8f72ceca"
    )
    objective = manifest["force_normalization_contract"]
    assert objective == {
        "canonical_objective": "J = -CDF",
        "response_id": "downforce",
        "sense": "maximize",
        "drag": "report_only",
        "no_constraints": True,
    }
    assert manifest["stage_s_problem_spec"]["diff_keys"] == ["objectives", "problem_id"]
    assert manifest["stage_s_problem_spec"]["objective_audit"]["stage_v_reference"] == "minimize_drag"
    assert manifest["stage_s_problem_spec"]["objective_audit"]["only_problem_spec_difference"] is True


def test_v2_contract_reuses_exact_sixteen_historical_mode_hashes():
    manifest = _manifest()
    old = json.loads(registration.OLD_S1_EVIDENCE.read_text(encoding="utf-8"))
    modes = manifest["mode_basis"]["modes"]
    assert len(modes) == 16
    assert [m["order"] for m in modes] == list(range(1, 17))
    old_by_name = {m["candidate"]["name"]: m for m in old["modes"]}
    for mode in modes:
        historical = old_by_name[mode["candidate"]["name"]]
        assert mode["normalized_vector_sha256"] == historical["vector_sha256"]
        assert mode["normalization_factor"] == historical["normalization_factor"]
        assert mode["candidate"] == historical["candidate"]
    assert manifest["mode_basis"]["selection_policy"].startswith("reuse_exact_historical")


def test_v2_contract_is_solver_free_and_preflight_script_cannot_launch_solver():
    manifest = _manifest()
    assert manifest["s0r_s1r"]["solver_started"] is False
    assert manifest["s0r_s1r"]["flow_fields_not_evaluated"] is True
    assert manifest["flags"]["solver_campaign_started"] is False
    script = (ROOT / "scripts/stage_s_reduced_basis_fd_v2_preflight_2026_09.py").read_text()
    # The module docstring explains that no flow solver is invoked; the
    # executable body must not mention or invoke one.
    body = script.split('"""', 2)[2]
    assert "simpleFoam" not in body
    assert "adjointOptimisationFoam" not in body
    assert "checkMesh -allGeometry -allTopology" in body
    evidence = json.loads(registration.PREFLIGHT.read_text(encoding="utf-8"))
    assert evidence["commands"] == ["moveControlPoints", "checkMesh -allGeometry -allTopology"]


def test_v2_manifest_sidecar_and_registered_sources_are_immutable():
    manifest = _manifest()
    sidecar = registration.MANIFEST.with_suffix(".json.sha256").read_text().strip()
    assert sidecar == ca.sha256_file(registration.MANIFEST)
    for name, ref in manifest["source_artifacts"].items():
        assert ca.sha256_file(ROOT / ref["path"]) == ref["sha256"], name


def test_immutable_writer_rejects_collision(tmp_path, monkeypatch):
    monkeypatch.setattr(registration, "ROOT", tmp_path)
    path = tmp_path / "immutable.json"
    path.write_text('{"value": 1}\n', encoding="utf-8")
    with pytest.raises(SystemExit, match="immutable artifact"):
        registration._write_immutable(path, {"value": 2})


def test_mode_binding_rejects_changed_historical_vector():
    old_s1 = json.loads(registration.OLD_S1_EVIDENCE.read_text(encoding="utf-8"))
    qualification = json.loads(registration.OLD_QUALIFICATION.read_text(encoding="utf-8"))
    old_s1["modes"][0]["vector_sha256"] = "0" * 64
    with pytest.raises(SystemExit, match="normalized mode hash mismatch"):
        registration._mode_binding(old_s1, qualification)


def test_preflight_evidence_is_solver_free_and_has_no_mode_substitution():
    evidence = json.loads(registration.PREFLIGHT.read_text(encoding="utf-8"))
    manifest = _manifest()
    assert evidence["manifest"]["sha256"] == ca.sha256_file(registration.MANIFEST)
    assert evidence["summary"]["solver_started"] is False
    assert evidence["summary"]["reduced_basis_fd_qualified"] == "pending"
    assert evidence["summary"]["shape_update_allowed"] is False
    assert evidence["s1r"]["basis_policy"].startswith("exact historical")
    assert evidence["s1r"]["modes_requested"] == manifest["mode_basis"]["k_modes"]
    assert evidence["s1r"]["modes_evaluated"] == evidence["summary"]["n_modes_passed"]
