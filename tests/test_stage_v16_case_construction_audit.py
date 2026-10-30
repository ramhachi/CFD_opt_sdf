"""Solver-free construction and boundary-flux audit evidence checks."""

from __future__ import annotations

import json
from pathlib import Path

from cfd_sdf import campaign_assertions as ca

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "docs/evidence/stage_v_v16_case_construction_audit_2026_09.json"


def test_construction_audit_fails_closed_on_stale_extension_identity():
    evidence = json.loads(AUDIT.read_text(encoding="utf-8"))
    assert evidence["status"] == "fail"
    assert evidence["no_solver_started"] is True
    assert len(evidence["findings"]) == 2
    assert all("does not encode the registered +3.2 m case" in finding for finding in evidence["findings"])


def test_construction_audit_separates_provenance_blocker_from_physical_checks():
    evidence = json.loads(AUDIT.read_text(encoding="utf-8"))
    for label in ("baseline", "mixed_far_field"):
        record = evidence[label]
        assert record["checks"]["boundary"]["matches"] is True
        assert all(record["checks"]["operating_point"].values())
        assert all(record["checks"]["force_patch_and_reference"].values())
        assert record["checks"]["ground_and_domain"]["location_inside_domain"] is True
        assert record["checks"]["boundary_flux"]["checks"]["global_closure"] is True
        assert record["checks"]["boundary_flux"]["checks"]["ground_zero"] is True
        assert record["checks"]["boundary_flux"]["checks"]["candidate_zero"] is True
    assert evidence["baseline"]["checks"]["boundary_flux"]["checks"]["symmetry_zero"] is True
    assert evidence["mixed_far_field"]["checks"]["boundary_flux"]["checks"]["freestream_outer_recorded"] is True


def test_construction_audit_sidecar_matches():
    assert ca.sha256_file(AUDIT) == AUDIT.with_suffix(".json.sha256").read_text(encoding="utf-8").strip()
