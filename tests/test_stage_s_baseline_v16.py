"""Contract test for the registered Stage S baseline (no solver run)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from cfd_sdf import campaign_assertions as ca  # noqa: E402

ARTIFACT = ROOT / "docs/evidence/stage_s_baseline_v16_2026_09.json"


def _artifact() -> dict:
    return json.loads(ARTIFACT.read_text())


def test_baseline_binds_the_selected_handoff_and_clearance():
    artifact = _artifact()
    assert artifact["kind"] == "stage_s_baseline_v16"
    assert artifact["gate"]["ready_for_stage_s"] is True
    assert artifact["handoff"]["selected_threshold"] == 0.5
    assert artifact["handoff"]["selection_rule"]["require_ready_for_stage_s"] is True
    assert artifact["clearance"]["qualified"] is True
    assert artifact["clearance"]["profile_id"] == "stage_v_clearance_v1"
    assert artifact["fields"]["geometry_basis"] == "rho_projection"
    assert artifact["fields"]["solver_audit_field"] == "beta_solver"


def test_baseline_file_hashes_reverify():
    artifact = _artifact()
    for name, record in artifact["fields"]["bundle"].items():
        assert ca.sha256_file(ROOT / record["path"]) == record["sha256"], name
    manifest = ROOT / artifact["handoff"]["manifest"]["path"]
    assert ca.sha256_file(manifest) == artifact["handoff"]["manifest"]["sha256"]
    for key, record in artifact["handoff"]["artifacts"].items():
        assert ca.sha256_file(ROOT / record["path"]) == record["sha256"], key
    pq41 = ROOT / artifact["handoff"]["pq4_1_artifact"]["path"]
    assert ca.sha256_file(pq41) == artifact["handoff"]["pq4_1_artifact"]["sha256"]
    assert ca.sha256_file(pq41) == artifact["gate"]["pq4_1_artifact_sha256"]
    assert (
        artifact["handoff"]["artifacts"]["surface_stl"]["sha256"]
        == artifact["clearance"]["surface_stl_sha256"]
    )


def test_baseline_candidate_matches_the_v16_outcome():
    artifact = _artifact()
    outcome = json.loads(
        (ROOT / artifact["candidate"]["campaign_outcome"]["path"]).read_text()
    )
    assert ca.sha256_file(ROOT / artifact["candidate"]["campaign_outcome"]["path"]) == (
        artifact["candidate"]["campaign_outcome"]["sha256"]
    )
    assert artifact["candidate"]["rho_sha256"] == outcome["checkpoint"]["rho_sha256"]
    assert artifact["candidate"]["checkpoint_index"] == outcome["checkpoint"]["index"]
    assert artifact["candidate"]["projected_volume"] <= artifact["candidate"]["v_max_projected"]
    assert artifact["work_f_profiles"]["mesh_and_solver"]["profile_id"] == "stage_v_qualification_v1"
    assert artifact["work_f_profiles"]["surface_fd"]["profile_id"] == "fd_gradient_v1"


V2_ARTIFACT = ROOT / "docs/evidence/stage_s_baseline_v16_v2_2026_09.json"


def test_baseline_v2_supersedes_v1_and_binds_the_repaired_judgment():
    artifact = json.loads(V2_ARTIFACT.read_text())
    assert artifact["kind"] == "stage_s_baseline_v16_v2"
    assert artifact["gate"]["ready_for_stage_s"] is True
    assert artifact["handoff"]["selected_threshold"] == 0.5
    assert artifact["clearance"]["qualified"] is True
    assert artifact["fields"]["geometry_basis"] == "rho_projection"
    assert artifact["supersedes"]["sha256"] == ca.sha256_file(
        ROOT / artifact["supersedes"]["path"]
    )
    for name, record in artifact["fields"]["bundle"].items():
        assert ca.sha256_file(ROOT / record["path"]) == record["sha256"], name
    manifest = ROOT / artifact["handoff"]["manifest"]["path"]
    assert ca.sha256_file(manifest) == artifact["handoff"]["manifest"]["sha256"]
    for key, record in artifact["handoff"]["artifacts"].items():
        assert ca.sha256_file(ROOT / record["path"]) == record["sha256"], key
    pq41 = ROOT / artifact["handoff"]["pq4_1_artifact"]["path"]
    assert ca.sha256_file(pq41) == artifact["handoff"]["pq4_1_artifact"]["sha256"]
    assert ca.sha256_file(pq41) == artifact["gate"]["pq4_1_artifact_sha256"]
    assert artifact["work_f_profiles"]["surface_fd"]["profile_id"] == "fd_gradient_v1"
    assert artifact["work_f_profiles"]["mesh_and_solver"]["profile_id"] == "stage_v_qualification_v1"
