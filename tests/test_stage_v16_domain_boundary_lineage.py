"""Evidence tests for the corrected v16 factor-run lineage."""

from __future__ import annotations

import json
from pathlib import Path

from cfd_sdf import campaign_assertions as ca

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "docs/evidence/stage_v_v16_domain_boundary_lineage_audit_2026_09.json"


def test_corrected_factor_screen_uses_distinct_canonical_histories():
    audit = json.loads(AUDIT.read_text(encoding="utf-8"))
    assert audit["status"] == "pass"
    assert audit["checks"] == {
        "boundary_change_matches_registered_top_outlet_factor": True,
        "preliminary_reused_postprocessing_case_not_used": True,
        "qualification_reads_canonical_coefficient_dat": True,
        "treatment_histories_distinct_from_baseline": True,
    }
    baseline_hash = audit["baseline"]["history"]["sha256"]
    for treatment in audit["treatments"].values():
        assert treatment["history"]["source"].endswith("postProcessing/forceCoeffs/0/coefficient.dat")
        assert treatment["history"]["sha256"] != baseline_hash
        assert treatment["history"]["numbered_sibling_files"] == []


def test_lineage_audit_sidecar_matches():
    assert ca.sha256_file(AUDIT) == AUDIT.with_suffix(".json.sha256").read_text(encoding="utf-8").strip()
