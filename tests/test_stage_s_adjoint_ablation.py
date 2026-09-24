"""Contract tests for the Work F D4.3 adjoint-option ablation artifacts."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from cfd_sdf import campaign_assertions as ca  # noqa: E402
from cfd_sdf.stage_s_component_diagnosis import relative_gate  # noqa: E402

MANIFEST = ROOT / "docs/evidence/stage_s_work_f_adjoint_option_diagnostic_manifest_2026_09.json"
SURFACE = ROOT / "docs/evidence/stage_s_work_f_adjoint_option_diagnostic_surface_area_2026_09.json"
MESH_MOVEMENT = (
    ROOT / "docs/evidence/stage_s_work_f_adjoint_option_diagnostic_mesh_movement_2026_09.json"
)
RESULT = ROOT / "docs/evidence/stage_s_work_f_surface_fd_result_2026_09.json"
CATALOG = ROOT / "docs/evidence/stage_s_work_f_surface_fd_catalog_2026_09.json"


def _scales() -> dict[str, float]:
    catalog = json.loads(CATALOG.read_text())
    return {
        response: float(
            json.loads((ROOT / record["path"]).read_text())["manifest"]["fixture"]["response_scale"]
        )
        for response, record in catalog["manifests"].items()
    }


def test_manifest_isolation_and_pre_registered_classification():
    manifest = json.loads(MANIFEST.read_text())
    assert manifest["kind"] == "stage_s_work_f_adjoint_option_diagnostic_manifest"
    assert manifest["registered_before_computation"] is True
    assert [factor["order"] for factor in manifest["factors"]] == [1, 2]
    assert [factor["option"] for factor in manifest["factors"]] == [
        "includeSurfaceArea",
        "includeMeshMovement",
    ]
    assert manifest["fixed_settings"]["sensitivityType"] == "surface"
    assert len(manifest["baseline_row_classification"]) == 32
    scales = _scales()
    result = json.loads(RESULT.read_text())
    for response, rows in result["rows"].items():
        floor = 1.0e-3 * abs(scales[response])
        for row in rows:
            key = f"{response}__{row['direction']}__{float(row['epsilon']):g}"
            record = manifest["baseline_row_classification"][key]
            ratio, within, sign = relative_gate(float(row["analytic"]), float(row["fd"]))
            assert record["ratio"] == pytest.approx(ratio)
            assert record["within_gate"] is within
            assert record["sign_agreement"] is sign
            assert record["near_zero"] is (abs(float(row["analytic"])) <= floor)


def test_surface_area_ablation_is_inert_for_derivative_files():
    evidence = json.loads(SURFACE.read_text())
    assert evidence["manifest"]["sha256"] == ca.sha256_file(MANIFEST)
    assert evidence["factor"]["option"] == "includeSurfaceArea"
    assert evidence["scheme_edit"]["isolated"] is True
    assert evidence["convergence"] == {"adjDownforce": True, "adjDrag": True}
    assert evidence["lineage"]["all_field_hashes_match"] is True
    effect = evidence["treatment_effect"]
    assert effect["any_face_sens_normal_changed"] is True
    assert effect["derivative_files_identical_to_baseline"] == {
        "downforce": True,
        "drag": True,
    }
    for record in effect["face_sens_normal_outputs"].values():
        assert record["changed"] is True
    for row in evidence["rows"].values():
        assert row["ablated_analytic"] == pytest.approx(row["baseline_analytic"], rel=1e-15)
        assert row["ablated_within_gate"] is row["baseline_within_gate"]
    judgment = evidence["judgment"]
    assert judgment["lineage_unchanged"] is True
    assert judgment["original_failing_rows_all_within"] is False
    assert judgment["sole_cause_supported"] is False
    assert evidence["summary"]["factor_changes_derivative_files"] is False
    assert evidence["summary"]["derivative_qualified"] is False
    assert evidence["summary"]["shape_update_allowed"] is False


def test_mesh_movement_ablation_changes_but_does_not_explain():
    evidence = json.loads(MESH_MOVEMENT.read_text())
    assert evidence["manifest"]["sha256"] == ca.sha256_file(MANIFEST)
    assert evidence["factor"]["option"] == "includeMeshMovement"
    assert evidence["scheme_edit"]["isolated"] is True
    assert evidence["scheme_edit"]["removed_lines"] == []
    assert evidence["convergence"] == {"adjDownforce": True, "adjDrag": True}
    assert evidence["lineage"]["all_field_hashes_match"] is True
    assert evidence["treatment_effect"]["derivative_files_identical_to_baseline"] == {
        "downforce": False,
        "drag": False,
    }
    changed_components = 0
    for key, row in evidence["rows"].items():
        closure = row["components"]["total"] - sum(
            row["components"][name]
            for name in ("dxdbVol", "dxdbSurf", "dSdb", "dndb", "dxdbDirect", "dVdb")
        )
        assert abs(row["closure"] - closure) <= 1e-9
        if row["ablated_analytic"] != pytest.approx(row["baseline_analytic"], rel=1e-15):
            changed_components += 1
    assert changed_components == 32
    seed_2026 = evidence["rows"]["downforce__random_seed_2026__0.0005"]
    assert seed_2026["components"]["dSdb"] == pytest.approx(
        -0.14158, abs=5e-6
    )
    assert seed_2026["components"]["dxdbSurf"] == pytest.approx(-0.15813, abs=5e-6)
    judgment = evidence["judgment"]
    assert judgment["lineage_unchanged"] is True
    assert judgment["original_failing_rows_all_within"] is False
    assert judgment["original_passing_rows_none_worsened"] is False
    assert judgment["sole_cause_supported"] is False
    assert evidence["summary"]["factor_changes_derivative_files"] is True
    assert evidence["summary"]["next"].startswith("D4.4 fail-closed")
    assert evidence["summary"]["derivative_qualified"] is False
    assert evidence["summary"]["shape_update_allowed"] is False
