"""Contract tests for the Work F D4.2 geometry-Jacobian audit (solver-free)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from cfd_sdf import campaign_assertions as ca  # noqa: E402
from cfd_sdf.stage_s_geometry_jacobian import (  # noqa: E402
    GEOMETRY_QUANTITIES,
    GeometryJacobianError,
    centered_difference,
    evaluate_quantity_gate,
    face_geometry,
    parse_dump,
    plateau_status,
    quantity_diagnostics,
)

MANIFEST = ROOT / "docs/evidence/stage_s_work_f_geometry_jacobian_manifest_2026_09.json"
AUDIT = ROOT / "docs/evidence/stage_s_work_f_geometry_jacobian_audit_2026_09.json"
PRESERVED = ROOT / "docs/evidence/stage_s_work_f_geometry_jacobian_audit_all_epsilon_2026_09.json"
D4_MANIFEST = ROOT / "docs/evidence/stage_s_work_f_component_diagnosis_manifest_2026_09.json"
UTILITY = ROOT / "openfoam_utils/geometryDerivativeDump"


def test_face_geometry_matches_openfoam_formulas():
    points = np.asarray(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [1.0, 1.0, 0.0],
            [0.0, 1.0, 0.0],
        ]
    )
    quad = face_geometry(points, [[0, 1, 2, 3]])
    assert np.allclose(quad.centres[0], [0.5, 0.5, 0.0])
    assert np.allclose(quad.areas[0], [0.0, 0.0, 1.0])
    assert np.allclose(quad.normals[0], [0.0, 0.0, 1.0])
    triangle = face_geometry(points, [[0, 1, 2]])
    assert np.allclose(triangle.centres[0], [2.0 / 3.0, 1.0 / 3.0, 0.0])
    assert np.allclose(triangle.areas[0], [0.0, 0.0, 0.5])


def test_centered_difference_and_guards():
    plus = np.asarray([[2.0, 0.0, 0.0]])
    minus = np.asarray([[0.0, 0.0, 0.0]])
    assert np.allclose(centered_difference(plus, minus, 1.0), [[1.0, 0.0, 0.0]])
    with pytest.raises(GeometryJacobianError, match="epsilon must be positive"):
        centered_difference(plus, minus, 0.0)


def test_parse_dump_roundtrip():
    text = "\n".join(
        [
            "#geometryDerivativeDump v1",
            "#design_patch design_candidate",
            "#n_design_faces 2",
            "#direction alpha",
            "#face_table_begin alpha",
            "0 1 2 3 4 5 6 7 8 9",
            "1 1 2 3 4 5 6 7 8 9",
            "#face_table_end alpha",
            "#patch_inside_counts_begin",
            "inlet 0",
            "#patch_inside_counts_end",
            "#end",
        ]
    )
    parsed = parse_dump(text)
    assert parsed["n_faces"] == 2
    assert parsed["inside_counts"] == {"inlet": 0}
    assert parsed["directions"]["alpha"]["Cf"].shape == (2, 3)
    broken = text.replace("1 1 2 3 4 5 6 7 8 9", "7 1 2 3 4 5 6 7 8 9")
    with pytest.raises(GeometryJacobianError, match="not consecutive"):
        parse_dump(broken)


def test_quantity_diagnostics_and_gates():
    analytic = np.asarray([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]])
    fd = analytic + 1e-9
    diagnostics = quantity_diagnostics(analytic, fd)
    gates = evaluate_quantity_gate(
        diagnostics, relative=1e-6, absolute=1e-9, l2_tolerance=1e-6, cosine_min=0.999999
    )
    assert all(gates.values())
    assert diagnostics["l2_ratio"] == pytest.approx(1.0, abs=1e-8)
    poor = quantity_diagnostics(analytic, -analytic)
    gates = evaluate_quantity_gate(
        poor, relative=1e-6, absolute=1e-9, l2_tolerance=1e-6, cosine_min=0.999999
    )
    assert not gates["max_error"]
    assert not gates["cosine"]
    assert gates["l2_ratio"]
    status = plateau_status([1.0, 1.0001, 0.99995, 1.00002])
    assert status["plateau"] is True
    assert status["max_deviation"] == pytest.approx(1.5e-4, rel=1e-6)
    assert plateau_status([1.0])["plateau"] is False


def test_registered_geometry_jacobian_manifest():
    manifest = json.loads(MANIFEST.read_text())
    assert manifest["kind"] == "stage_s_work_f_geometry_jacobian_manifest"
    assert manifest["registered_before_computation"] is True
    assert ca.sha256_file(D4_MANIFEST) == manifest["component_diagnosis_manifest"]["sha256"]
    assert ca.sha256_file(UTILITY / "geometryDerivativeDump.C") == manifest["utility"]["source_sha256"]
    assert manifest["scope"]["comparison_epsilon_m"] == pytest.approx(1e-3)
    assert sorted(manifest["scope"]["epsilons_m"]) == [1e-4, 2.5e-4, 5e-4, 1e-3]
    assert manifest["base_case"]["dynamicMeshDict_reconstructs_from_catalog_basis"] is True
    assert len(manifest["perturbation_sides"]["sides"]) == 32
    assert all(record["pass"] for record in manifest["perturbation_sides"]["sides"].values())
    assert set(manifest["gate_tolerances"]) == set(GEOMETRY_QUANTITIES)


def test_registered_geometry_jacobian_audit_pass():
    manifest = json.loads(MANIFEST.read_text())
    audit = json.loads(AUDIT.read_text())
    assert audit["manifest"]["sha256"] == ca.sha256_file(MANIFEST)
    correction = audit["comparison_correction"]
    assert ca.sha256_file(PRESERVED) == correction["as_run_artifact"]["sha256"]
    assert correction["registered_comparison_epsilon_m"] == pytest.approx(
        manifest["scope"]["comparison_epsilon_m"]
    )
    assert audit["utility"]["read_only"] is True
    assert audit["summary"]["geometry_jacobian_pass"] is True
    assert audit["summary"]["derivative_qualified"] is False
    assert audit["summary"]["shape_update_allowed"] is False
    assert audit["checks"]["topology_faces_and_boundary_identical"] is True
    assert audit["checks"]["non_design_patch_inside_counts_zero"] is True
    assert audit["checks"]["outside_patch_movement_zero"] is True
    assert audit["checks"]["roundoff_scaling_consistent"] is True
    assert len(audit["comparisons"]) == 16
    for entry in audit["comparisons"].values():
        tight = any(
            quantity["tight_gate_at_comparison_epsilon"]
            for quantity in entry["quantities"].values()
        )
        if tight:
            assert entry["epsilon_m"] == pytest.approx(manifest["scope"]["comparison_epsilon_m"])
            for quantity in GEOMETRY_QUANTITIES:
                assert entry["quantities"][quantity]["pass"] is True
                assert all(entry["quantities"][quantity]["gates"].values())
        else:
            for quantity in GEOMETRY_QUANTITIES:
                assert entry["quantities"][quantity]["pass"] == (
                    entry["quantities"][quantity]["gates"]["l2_ratio"]
                )
    for direction in audit["plateau"]:
        for quantity in GEOMETRY_QUANTITIES:
            assert audit["plateau"][direction][quantity]["pass"] is True
    roundoff = audit["checks"]["roundoff_characterization"]
    for direction, quantities in roundoff.items():
        for quantity, record in quantities.items():
            scaled = record["max_abs_error_times_two_epsilon"]
            assert record["scaled_spread"] <= 0.5
            assert max(scaled) / max(min(scaled), 1e-30) <= 2.0
