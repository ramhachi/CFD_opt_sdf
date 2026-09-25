"""Contract tests for the registered Stage V domain continuation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
import sys

sys.path.insert(0, str(ROOT / "src"))

from cfd_sdf import campaign_assertions as ca  # noqa: E402


MANIFEST = ROOT / "docs/evidence/stage_v_domain_continuation_manifest_2026_09.json"
RUN_MANIFEST = ROOT / "docs/evidence/stage_v_domain_continuation_run_manifest_2026_09.json"
EVIDENCE = ROOT / "docs/evidence/stage_v_domain_continuation_2026_09.json"
BASE_SPEC_GEOMETRY = ROOT / "work/stage_sv_laminar/geometry/design_domain.stl"
STAGED_GEOMETRY = ROOT / "work/stage_v_domain_continuation_2026_09/specs/geometry/design_domain.stl"


def test_continuation_was_registered_before_computation():
    plan = json.loads(MANIFEST.read_text())
    run = json.loads(RUN_MANIFEST.read_text())
    assert plan["registered_before_computation"] is True
    assert plan["kind"] == "stage_v_domain_continuation_manifest"
    assert run["kind"] == "stage_v_domain_continuation_run_manifest"
    assert run["parent_manifest"]["sha256"] == ca.sha256_file(MANIFEST)
    assert run["parent_pq2_evidence"]["sha256"] == ca.sha256_file(
        ROOT / run["parent_pq2_evidence"]["path"]
    )
    assert run["budget"] == {"max_new_runs": 1, "v3_runs": 0}


def test_continuation_definition_is_one_factor_and_aligned():
    plan = json.loads(MANIFEST.read_text())
    treatment = plan["treatment"]
    assert treatment["name"] == "far_field_domain_extension_1p6"
    assert treatment["extended_spec"]["lower_m"] == pytest.approx([-2.6, -2.4, -0.6])
    assert treatment["extended_spec"]["upper_m"] == pytest.approx([3.6, 2.4, 2.2])
    assert treatment["voxel_size_m"] == 0.025
    assert treatment["boundary_contract"]["top"] == "symmetryPlane"
    assert plan["previous_extension"]["name"] == "far_field_domain_extension_0p8"


def test_continuation_judgment_is_fail_closed():
    evidence = json.loads(EVIDENCE.read_text())
    previous = evidence["previous_extension"]
    result = evidence["treatment"]
    delta = evidence["delta_from_previous"]
    assert result["qualified"] is True
    assert result["cells"] > previous["cells"]
    assert delta["downforce"] == pytest.approx(result["downforce"] - previous["downforce"])
    assert delta["relative_Cd_change"] == pytest.approx(
        (result["Cd"] - previous["Cd"]) / previous["Cd"]
    )
    assert delta["downforce_beyond_bound"] is True
    assert delta["drag_beyond_bound"] is True
    assert evidence["summary"]["adjacent_transition_within_bound"] is False
    assert "keep S2 blocked" in evidence["decision"]


def test_staged_geometry_is_byte_identical_to_base():
    assert ca.sha256_file(STAGED_GEOMETRY) == ca.sha256_file(BASE_SPEC_GEOMETRY)
