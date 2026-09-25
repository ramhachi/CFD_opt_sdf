"""Contract tests for the v16 same-candidate Stage V factor screen."""

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

MANIFEST = ROOT / "docs/evidence/stage_v_v16_domain_boundary_contract_manifest_v2_2026_09.json"
AUDIT = ROOT / "docs/evidence/stage_s_v16_contract_audit_manifest_2026_09.json"
BASE_SPEC = ROOT / "work/stage_sv_laminar/project_matched_re_laminar.yaml"
EXT_SPEC = ROOT / "work/stage_v_v16_domain_boundary_v2_2026_09/specs/project_matched_re_laminar_domain_extended_0p8_v2.yaml"


def _module():
    spec = importlib.util.spec_from_file_location("v16_factor", ROOT / "scripts/run_stage_v16_domain_boundary_contract_2026_09.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_registered_contract_is_immutable_and_solver_free():
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert manifest["kind"] == "stage_v_v16_domain_boundary_contract_manifest"
    assert manifest["immutable"] is True
    assert manifest["registered_before_computation"] is True
    assert manifest["status"] == "registered_not_run"
    assert manifest["execution"] == {
        "mesh_generation_started": False,
        "new_run_count": 0,
        "optimization_campaign_started": False,
        "solver_started": False,
    }
    assert ca.sha256_file(MANIFEST) == MANIFEST.with_suffix(".json.sha256").read_text().strip()
    assert manifest["parent_contract_audit"]["sha256"] == ca.sha256_file(AUDIT)


def test_contract_binds_the_v16_candidate_and_two_one_factor_treatments():
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert manifest["candidate"]["stl"]["sha256"] == "5e6d210794b55a11f3dc76b8be37eeb39d27579b341212939a1c2a63d2fb8d11"
    treatments = {item["name"]: item for item in manifest["treatments"]}
    assert set(treatments) == {"far_field_domain_extension_0p8", "top_pressure_outlet"}
    assert treatments["far_field_domain_extension_0p8"]["far_field_faces"] == ["inlet", "outlet", "sideMin", "sideMax", "top"]
    assert treatments["far_field_domain_extension_0p8"]["ground_face"] == "bottom"
    assert treatments["top_pressure_outlet"]["boundary_contract"]["top"] == "patch / U zeroGradient / p fixedValue uniform 0"
    assert manifest["budget"] == {"max_new_runs": 2, "mesh_levels": ["V1"], "v2_runs": 0, "v3_runs": 0}


def test_extended_spec_changes_only_domain_and_problem_id():
    module = _module()
    import yaml

    base = yaml.safe_load(BASE_SPEC.read_text(encoding="utf-8"))
    extended = yaml.safe_load(EXT_SPEC.read_text(encoding="utf-8"))
    diff = sorted(key for key in set(base) | set(extended) if base.get(key) != extended.get(key))
    assert diff == ["grid", "problem_id"]
    assert extended["grid"]["domain_bounds_m"]["lower"] == pytest.approx([-1.8, -1.6, -0.6])
    assert extended["grid"]["domain_bounds_m"]["upper"] == pytest.approx([2.8, 1.6, 1.4])
    assert module.EXTENSION_M == 0.8
    assert module.EXT_SPEC == EXT_SPEC


def test_copied_treatment_case_drops_old_postprocessing():
    module = _module()
    import tempfile

    with tempfile.TemporaryDirectory() as temporary:
        case_dir = Path(temporary)
        (case_dir / "0").mkdir()
        (case_dir / "constant").mkdir()
        (case_dir / "system").mkdir()
        stale = case_dir / "postProcessing/forceCoeffs/0"
        stale.mkdir(parents=True)
        (stale / "coefficient.dat").write_text("stale\n", encoding="utf-8")
        module._clean_case_outputs(case_dir)
        assert not (case_dir / "postProcessing").exists()
        assert (case_dir / "0").is_dir()
        assert (case_dir / "constant").is_dir()
        assert (case_dir / "system").is_dir()


def test_registered_artifacts_are_current():
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    for key, ref in manifest["artifacts"].items():
        assert ca.sha256_file(ROOT / ref["path"]) == ref["sha256"], key
