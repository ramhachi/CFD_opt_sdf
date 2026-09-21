"""Tests for the DF0/P18 WP6-2 evidence audit and shape feature metrics."""

from __future__ import annotations

import json

import numpy as np
import pytest

from cfd_sdf.analytic_candidate_shapes import CANONICAL_SHAPE, CANONICAL_SPACING, ShapeDefinition
from cfd_sdf.evidence_audit import (
    ACTION,
    FAIL,
    audit_feature_policy,
    audit_manifest_thresholds,
    audit_ranking_reports,
    audit_verdict_claims,
    build_evidence_audit,
    compute_v1v2_drift,
    extract_declared_widths_m,
)
from cfd_sdf.shape_feature_metrics import (
    measure_shape_definition,
    occupancy_metrics,
    policy_exclusion_report,
)

BANDS = {"downforce_abs": 0.0147, "drag_coefficient_rel": 0.034}


def _report(
    response: str,
    verdict: str,
    *,
    extraction: dict | None = None,
    uncertainty: dict | None = None,
    failed_pairs: list | None = None,
) -> dict:
    return {
        "response_id": response,
        "verdict": verdict,
        "extraction_sensitivity": extraction or {},
        "uncertainty": uncertainty or dict(BANDS),
        "failed_required_pairs": failed_pairs or [],
    }


def _evidence(reports: dict, claims: dict) -> dict:
    return {
        "ranking_reports": reports,
        "verdict_by_response_at_wp6": claims,
        "declared_uncertainty_verbatim": dict(BANDS),
    }


def _feature_table(shapes: dict[str, dict]) -> dict:
    return {"spacing_m": CANONICAL_SPACING, "threshold_m": 0.1, "n_shapes": len(shapes), "shapes": shapes}


def _shape_row(declared: float, measured: float) -> dict:
    return {
        "min_declared_part_dimension_m": declared,
        "min_measured_feature_size_m": measured,
    }


def test_extract_declared_widths_reads_only_minimum_relations():
    purpose = "min solid thickness >= 0.15 m (3 cells at the 0.05 m voxel)"
    definition = "shapes with minimum solid thickness >= 0.10 m"
    assert extract_declared_widths_m(purpose) == [0.15]
    assert extract_declared_widths_m(definition) == [0.1]
    assert extract_declared_widths_m(purpose, definition) == [0.1, 0.15]
    assert extract_declared_widths_m(None) == []


def test_manifest_threshold_conflict_is_blocking():
    conflict = {
        "purpose": ">= 0.15 m",
        "definition": {"reachable_set": ">= 0.10 m"},
    }
    findings = audit_manifest_thresholds(conflict)
    assert [f.finding_id for f in findings] == ["declared_min_width_conflict"]
    assert findings[0].severity == FAIL

    consistent = {
        "purpose": ">= 0.15 m",
        "definition": {"reachable_set": ">= 0.15 m"},
    }
    assert audit_manifest_thresholds(consistent) == []


def test_empty_extraction_sensitivity_blocks_pass_verdicts():
    reports = {
        "reachable_set_8": {
            "reports": {
                "downforce/V1": _report("downforce/V1", "pass"),
            }
        }
    }
    findings = audit_ranking_reports(reports, dict(BANDS))
    ids = [f.finding_id for f in findings]
    assert "extraction_sensitivity_not_measured" in ids
    assert "pass_requires_measured_extraction" in ids
    assert all(f.severity == FAIL for f in findings)

    measured = {
        "reachable_set_8": {
            "reports": {
                "downforce/V1": _report(
                    "downforce/V1", "pass", extraction={"plate": 0.01}
                ),
            }
        }
    }
    assert audit_ranking_reports(measured, dict(BANDS)) == []


def test_report_uncertainty_mismatch_and_failed_pairs_are_blocking():
    reports = {
        "reachable_set_8": {
            "reports": {
                "downforce/V1": _report(
                    "downforce/V1",
                    "pass",
                    extraction={"plate": 0.01},
                    uncertainty={"downforce_abs": 0.5, "drag_coefficient_rel": 0.034},
                    failed_pairs=["a->b"],
                ),
            }
        }
    }
    ids = [f.finding_id for f in audit_ranking_reports(reports, dict(BANDS))]
    assert "report_uncertainty_mismatch" in ids
    assert "failed_required_pairs" in ids


def test_v1v2_drift_flags_band_exceedance_per_candidate():
    v1 = {
        "small_drift": {"downforce": 0.5, "Cd": 1.0},
        "large_drift": {"downforce": 0.5, "Cd": 1.0},
    }
    v2 = {
        "small_drift": {"downforce": 0.51, "Cd": 1.01},
        "large_drift": {"downforce": 0.53, "Cd": 1.05},
    }
    drift = compute_v1v2_drift(v1, v2, BANDS)
    assert drift["candidates_exceeding_downforce_band"] == ["large_drift"]
    assert drift["candidates_exceeding_drag_band"] == ["large_drift"]
    assert drift["common_band_valid_for_all_candidates"] is False
    assert drift["max_downforce_abs_drift"] > BANDS["downforce_abs"]


def test_scoped_pass_claim_is_allowed_while_aggregate_is_unresolved():
    reports = {
        "reachable_set_8": {
            "reports": {"downforce/V1": _report("downforce/V1", "pass")}
        },
        "combined_pool_17_after_policy_exclusion": {
            "reports": {
                "downforce/V1/17pool": _report("downforce/V1/17pool", "unresolved")
            }
        },
    }
    scoped = _evidence(
        reports,
        {"downforce": "pass (reachable set, 8 pre-registered candidates)"},
    )
    assert audit_verdict_claims(scoped["verdict_by_response_at_wp6"], reports) == []

    unscoped = _evidence(reports, {"downforce": "pass"})
    findings = audit_verdict_claims(unscoped["verdict_by_response_at_wp6"], reports)
    assert [f.finding_id for f in findings] == ["unscoped_claim_exceeds_reports"]
    assert findings[0].severity == FAIL


def test_merge_conflicting_scope_claim_fails():
    reports = {
        "reachable_set_8": {
            "reports": {"downforce/V1": _report("downforce/V1", "unresolved")}
        },
    }
    claims = {"downforce": "pass (reachable set)"}
    findings = audit_verdict_claims(claims, reports)
    assert [f.finding_id for f in findings] == ["claim_verdict_exceeds_scope"]


def test_occupancy_metrics_measure_known_slab_and_components():
    solid = np.zeros(CANONICAL_SHAPE, dtype=bool)
    solid[10:30, 10:30, 10:13] = True
    metrics = occupancy_metrics(solid, CANONICAL_SPACING)
    assert metrics["n_components_26"] == 1
    assert metrics["volume_m3"] == 20 * 20 * 3 * CANONICAL_SPACING**3
    assert metrics["max_inscribed_diameter_m"] == pytest.approx(0.15, abs=1e-12)

    two = np.zeros(CANONICAL_SHAPE, dtype=bool)
    two[5:8, 5:8, 5:8] = True
    two[5:8, 5:8, 10:13] = True
    metrics = occupancy_metrics(two, CANONICAL_SPACING)
    assert metrics["n_components_26"] == 2
    assert metrics["max_inscribed_diameter_m"] == pytest.approx(0.15, abs=1e-12)


def test_measure_shape_definition_reports_part_gap_and_overlap():
    part_a = ShapeDefinition("a", 0.20, 0.20, 0.20, 0.0, (0.0, 0.0, 0.0))
    part_b = ShapeDefinition("b", 0.20, 0.20, 0.20, 0.0, (0.0, 0.0, 0.3))
    separated = ShapeDefinition("separated", 0.0, 0.0, 0.0, 0.0, (0.0, 0.0, 0.0), parts=(part_a, part_b))
    entry = measure_shape_definition(separated)
    assert entry["union"]["n_components_26"] == 2
    # gap = nearest center distance minus one voxel: 0.10 - 0.05 (the occupancy
    # of the 0.20 m parts is 5 cells thick, so their faces are 0.05 m apart)
    gap = entry["part_interactions"][0]["min_face_gap_m"]
    assert gap == pytest.approx(0.05, abs=1e-9)

    part_c = ShapeDefinition("c", 0.20, 0.20, 0.20, 0.0, (0.0, 0.0, 0.1))
    overlapped = ShapeDefinition("overlapped", 0.0, 0.0, 0.0, 0.0, (0.0, 0.0, 0.0), parts=(part_a, part_c))
    entry = measure_shape_definition(overlapped)
    interaction = entry["part_interactions"][0]
    assert interaction["overlap_cells"] > 0
    assert interaction["min_face_gap_m"] == 0.0
    assert entry["union"]["n_components_26"] == 1


def test_policy_exclusion_and_classification():
    table = _feature_table(
        {
            "thick": _shape_row(0.15, 0.15),
            "quantized": _shape_row(0.10, 0.1031),
            "thin": _shape_row(0.05, 0.05),
        }
    )
    exclusions = policy_exclusion_report(table, [0.10, 0.15])
    assert exclusions["excluded_shape_ids"]["0.1"] == ["thin"]
    assert exclusions["excluded_shape_ids"]["0.15"] == ["quantized", "thin"]

    findings, _ = audit_feature_policy(table, [0.10, 0.15])
    assert not [f for f in findings if f.severity == FAIL]

    under = _feature_table({"under": _shape_row(0.15, 0.05)})
    findings, _ = audit_feature_policy(under, [0.15])
    assert [f.finding_id for f in findings if f.severity == FAIL] == [
        "declared_vs_measured_feature_mismatch"
    ]


def test_build_evidence_audit_writes_artifact_with_injected_table(tmp_path):
    manifest = {
        "purpose": "min thickness >= 0.15 m",
        "definition": {"reachable_set": "min thickness >= 0.10 m"},
    }
    evidence = _evidence(
        {
            "reachable_set_8": {
                "reports": {"downforce/V1": _report("downforce/V1", "pass")}
            }
        },
        {"downforce": "pass (reachable set)"},
    )
    manifest_path = tmp_path / "manifest.json"
    evidence_path = tmp_path / "evidence.json"
    output_path = tmp_path / "audit.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    evidence_path.write_text(json.dumps(evidence), encoding="utf-8")

    table = _feature_table({"shape_a": _shape_row(0.15, 0.15)})
    result = build_evidence_audit(
        manifest_path=manifest_path,
        reachable_evidence_path=evidence_path,
        output_path=output_path,
        feature_table=table,
    )
    assert result["ok"] is False
    assert output_path.exists()
    written = json.loads(output_path.read_text(encoding="utf-8"))
    blocking = written["conclusions"]["blocking_findings"]
    assert "declared_min_width_conflict" in blocking
    assert "pass_requires_measured_extraction" in blocking
    assert written["scope_repair_manifest"]["claim_status"] == "provisional"
    assert [
        f["finding_id"]
        for f in written["findings"]
        if f["severity"] == ACTION
    ] == ["policy_dependent_scope"]
