from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "docs/evidence/stage_v_v16_physical_profile_contract_manifest_v2_2026_09.json"
RUN_MANIFEST = ROOT / "docs/evidence/stage_v_v16_physical_profile_run_manifest_v2_2026_09.json"
LINEAGE = ROOT / "docs/evidence/stage_v_v16_physical_profile_candidate_lineage_v2_2026_09.json"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_v2_physical_profile_contract_is_immutable_and_self_contained() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    run_manifest = json.loads(RUN_MANIFEST.read_text(encoding="utf-8"))
    lineage = json.loads(LINEAGE.read_text(encoding="utf-8"))

    assert manifest["status"] == "registered_not_run"
    assert run_manifest["status"] == "registered_not_run"
    assert run_manifest["execution"] == {
        "mesh_generation_started": False,
        "new_run_count": 0,
        "optimization_campaign_started": False,
        "solver_started": False,
    }
    assert lineage["reconstruction"]["solver_invoked"] is False
    assert manifest["physical_profile"]["boundary_implementation"]["moving_wall"] == (
        "translatingWallVelocity"
    )
    assert manifest["physical_profile"]["outer_boundary_semantics"] == {
        "freestream_pressure_pa": 0.0,
        "freestream_velocity_mps": [1.0, 0.0, 0.0],
    }
    assert manifest["metric"]["physical_profile_qualification"]["required_before_domain_convergence"] is True
    assert manifest["metric"]["same_profile_domain_convergence"]["bounds"] == {
        "downforce_absolute": 0.005,
        "drag_relative": 0.02,
    }
    assert "downforce_absolute" not in manifest["metric"]

    for record in run_manifest["artifacts"].values():
        path = ROOT / record["path"]
        assert path.is_file(), record["path"]
        assert _sha256(path) == record["sha256"], record["path"]

    assert run_manifest["candidate_lineage"] == manifest["candidate_lineage"]
