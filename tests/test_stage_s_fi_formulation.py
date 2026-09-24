"""Contract tests for the Work F A0/A1 FI formulation diagnostic."""

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

MANIFEST = ROOT / "docs/evidence/stage_s_work_f_fi_formulation_diagnostic_manifest_2026_09.json"
EVIDENCE = ROOT / "docs/evidence/stage_s_work_f_fi_formulation_diagnostic_2026_09.json"
COMPONENT_AUDIT = ROOT / "docs/evidence/stage_s_work_f_derivative_component_audit_2026_09.json"
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


def test_registered_fi_manifest_contract():
    manifest = json.loads(MANIFEST.read_text())
    assert manifest["kind"] == "stage_s_work_f_fi_formulation_diagnostic_manifest"
    assert manifest["registered_before_computation"] is True
    assert manifest["treatment"]["baseline"] == "sensitivityType surface;"
    assert manifest["treatment"]["treatment"] == "sensitivityType shapeFI;"
    assert manifest["budget"]["fixed_base_primal_lineage_runs"] == 1
    assert manifest["budget"]["adjoint_runs"] == 2
    assert manifest["budget"]["new_perturbation_primals"] == 0
    assert manifest["fixed_contract"]["active_var_count"] == 648
    assert len(manifest["fixed_contract"]["active_var_ids"]) == 648
    assert manifest["fixed_contract"]["parameterization"]["shapeType"] == "volumetricBSplines"
    assert sorted(manifest["fixed_contract"]["epsilon_ladder_m"]) == [1e-4, 2.5e-4, 5e-4, 1e-3]
    assert len(manifest["openfoam_source_files"]["sha256"]) == 12
    assert manifest["original_lineage"]["sensitivity_type"] == "surface"
    assert len(manifest["original_lineage"]["field_hashes"]) == 3
    assert len(manifest["baseline_row_classification"]) == 32
    for record in manifest["inputs"].values():
        assert ca.sha256_file(ROOT / record["path"]) == record["sha256"]
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


def test_registered_fi_discriminant_is_mixed_fail():
    evidence = json.loads(EVIDENCE.read_text())
    assert evidence["manifest"]["sha256"] == ca.sha256_file(MANIFEST)
    assert evidence["scheme_edit"]["isolated"] is True
    assert evidence["convergence"]["sensitivity_selected"] == "shapeFI"
    assert evidence["convergence"]["adjDownforce"] is True
    assert evidence["convergence"]["adjDrag"] is True
    assert evidence["lineage"]["all_field_hashes_match"] is True
    assert evidence["lineage"]["primal_converged"] is True
    for entry in evidence["schema"].values():
        assert entry == {"rows": 648, "unique": True, "matches_active_set": True, "finite": True}
    judgment = evidence["judgment"]
    assert judgment["sign_agreement_all"] is True
    assert judgment["plateau_all"] is True
    assert judgment["no_near_zero_artifacts"] is True
    assert judgment["lineage_unchanged"] is True
    assert judgment["schema_unchanged"] is True
    assert judgment["original_failing_rows_all_within"] is False
    assert judgment["original_passing_rows_none_worsened"] is False
    assert judgment["candidate_formulation_supported"] is False
    assert evidence["summary"]["derivative_qualified"] is False
    assert evidence["summary"]["shape_update_allowed"] is False
    assert evidence["summary"]["next"].startswith("register the 0-run architecture memo")
    assert len(evidence["rows"]) == 32
    component_rows = {
        f"{row['row_id']}": row for row in json.loads(COMPONENT_AUDIT.read_text())["rows"]
    }
    for key, row in evidence["rows"].items():
        components = row["components"]
        assert components["dxdbSurf"] == pytest.approx(0.0, abs=1e-15)
        assert components["dndb"] == pytest.approx(0.0, abs=1e-15)
        audit_key = f"upwind__{key}"
        if audit_key in component_rows and row["epsilon_m"] == 5e-4:
            assert components["dSdb"] == pytest.approx(
                component_rows[audit_key]["d_dSdb"], rel=1e-9, abs=1e-12
            )
    seed_2026 = evidence["rows"]["drag__random_seed_2026__0.0005"]
    assert seed_2026["baseline_analytic"] == pytest.approx(-0.1342488944, abs=1e-9)
    assert seed_2026["fi_analytic"] == pytest.approx(-0.12401002, abs=2e-4)
    assert seed_2026["fi_within_gate"] is False
    gradient = evidence["rows"]["downforce__downforce_gradient_aligned__0.0005"]
    assert gradient["baseline_within_gate"] is True
    assert gradient["fi_within_gate"] is False
    assert gradient["fi_ratio"] == pytest.approx(1.1333, abs=1e-3)
