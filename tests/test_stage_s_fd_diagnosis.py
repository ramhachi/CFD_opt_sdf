"""Contract tests for the Work F FD diagnosis D1/D2 audits (solver-free)."""

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
from cfd_sdf.stage_s_realized_direction import (  # noqa: E402
    RealizedDirectionError,
    active_mask_from_ids,
    audit_case,
    audit_pair,
    direction_comparison,
    direction_to_cp_space,
    read_control_points_csv,
    read_control_points_file,
)

D1_MANIFEST = ROOT / "docs/evidence/stage_s_work_f_realized_direction_audit_manifest_2026_09.json"
D1_ARTIFACT = ROOT / "docs/evidence/stage_s_work_f_realized_direction_audit_2026_09.json"
D2_MANIFEST = ROOT / "docs/evidence/stage_s_work_f_sensitivity_semantics_audit_manifest_2026_09.json"
D2_ARTIFACT = ROOT / "docs/evidence/stage_s_work_f_sensitivity_semantics_audit_2026_09.json"
QUALIFICATION = ROOT / "docs/evidence/stage_s_work_f_adjoint_qualification_2026_09.json"
BASE_CATALOG = (
    ROOT / "work/stage_s_work_f_v1/adjoint/base/optimisation/controlPoints/boxcpsBsplines0.csv"
)


def _ids() -> tuple[int, ...]:
    qualification = json.loads(QUALIFICATION.read_text())
    return tuple(int(value) for value in qualification["derivative_contract"]["active_var_ids"])


def _write_cp_file(tmp_path: Path, values: np.ndarray, name: str = "boxcpsBsplines") -> Path:
    rows = "\n".join(f"({x:.10g} {y:.10g} {z:.10g})" for x, y, z in values)
    text = (
        "FoamFile\n{\n    version 2.0;\n    format ascii;\n    class cartesian;\n}\n\n"
        f"controlPoints nonuniform List<vector>\n{len(values)}\n(\n{rows}\n)\n"
    )
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def test_control_point_parsers_and_count_validation(tmp_path: Path):
    values = np.zeros((4, 3), dtype=np.float64)
    values[1] = (1e-4, -2.5e-4, 0.0)
    path = _write_cp_file(tmp_path, values)
    parsed = read_control_points_file(path)
    assert np.allclose(parsed, values)
    base = read_control_points_csv(BASE_CATALOG)
    assert base.shape == (512, 3)
    bad = tmp_path / "bad"
    bad.write_text("controlPoints nonuniform List<vector>\n9\n(\n(0 0 0)\n)\n", encoding="utf-8")
    with pytest.raises(RealizedDirectionError, match="count mismatch"):
        read_control_points_file(bad)


def test_case_audit_detects_clipping_and_accepts_exact_application():
    ids = _ids()
    mask = active_mask_from_ids(ids)
    base = read_control_points_csv(BASE_CATALOG)
    direction_cp = direction_to_cp_space(np.ones(len(ids)), ids) * 1e-4
    exact = base + direction_cp
    ok = audit_case(base=base, realized=exact, prescribed=direction_cp, active_mask=mask)
    assert ok["realized_equals_prescribed"] is True
    assert ok["boundary_fixed"] is True
    assert ok["inactive_zero"] is True
    clipped = exact.copy()
    boundary = np.argwhere(~mask)[0]
    clipped[tuple(boundary)] += 1e-6
    bad = audit_case(base=base, realized=clipped, prescribed=direction_cp, active_mask=mask)
    assert bad["boundary_fixed"] is False
    assert bad["realized_equals_prescribed"] is False


def test_pair_audit_odd_even_and_direction_comparison():
    ids = _ids()
    mask = active_mask_from_ids(ids)
    base = read_control_points_csv(BASE_CATALOG)
    direction_cp = direction_to_cp_space(np.ones(len(ids)), ids)
    epsilon = 5e-4
    plus = base + epsilon * direction_cp
    minus = base - epsilon * direction_cp
    pair = audit_pair(base=base, realized_plus=plus, realized_minus=minus, epsilon=epsilon)
    assert np.allclose(pair.delta_odd, direction_cp)
    assert np.allclose(pair.delta_even, 0.0)
    comparison = direction_comparison(
        direction_cp=direction_cp, delta_odd=pair.delta_odd, active_mask=mask
    )
    assert comparison["cosine_ok"] is True
    assert comparison["difference_ok"] is True
    asymmetric = plus + 2.0 * epsilon * 1e-4 * direction_cp
    skewed = audit_pair(base=base, realized_plus=asymmetric, realized_minus=minus, epsilon=epsilon)
    assert np.max(np.abs(skewed.delta_even[mask])) > 0.0


def test_registered_d1_audit_reverifies():
    manifest = json.loads(D1_MANIFEST.read_text())
    artifact = json.loads(D1_ARTIFACT.read_text())
    assert artifact["manifest"]["sha256"] == ca.sha256_file(D1_MANIFEST)
    for name, record in manifest["inputs"].items():
        assert ca.sha256_file(ROOT / record["path"]) == record["sha256"], name
    assert artifact["summary"]["realized_direction_audit_pass"] is True
    assert artifact["summary"]["n_side_failures"] == 0
    assert artifact["summary"]["n_pair_failures"] == 0
    assert artifact["summary"]["original_verdict_unchanged"] is True
    assert artifact["summary"]["solver_started"] is False
    for pair in artifact["pairs"].values():
        assert pair["pass"] is True
        assert pair["movement_difference_m"] <= 1e-6
        assert pair["odd_symmetry_abs_error_m"] <= 1e-6
        assert pair["even_component_abs_m"] <= 1e-6
        assert pair["comparison"]["cosine_similarity"] >= 0.999999
    for response in ("drag", "downforce"):
        pair = artifact["pairs"]["downforce_gradient_aligned__eps0.001"]
        analytic = pair["analytic"][response]
        assert abs(analytic["d_analytic_prescribed"] - analytic["d_analytic_realized"]) <= (
            1e-5 * max(abs(analytic["d_analytic_prescribed"]), 1.0)
        )


def test_registered_d2_audit_reverifies():
    manifest = json.loads(D2_MANIFEST.read_text())
    artifact = json.loads(D2_ARTIFACT.read_text())
    assert artifact["manifest"]["sha256"] == ca.sha256_file(D2_MANIFEST)
    for name, record in manifest["inputs"].items():
        assert ca.sha256_file(ROOT / record["path"]) == record["sha256"], name
    assert artifact["summary"]["semantics_audit_pass"] is True
    assert artifact["summary"]["response_identity_pass"] is True
    assert artifact["summary"]["independent_recomputation_pass"] is True
    assert artifact["summary"]["original_verdict_unchanged"] is True
    for row in artifact["independent_recomputation"].values():
        assert row["relative_difference"] <= 1e-9


D3_MANIFEST = ROOT / "docs/evidence/stage_s_work_f_discretization_diagnostic_manifest_2026_09.json"
D3_PREFLIGHT = ROOT / "docs/evidence/stage_s_work_f_discretization_diagnostic_preflight_2026_09.json"
D3_EVIDENCE = ROOT / "docs/evidence/stage_s_work_f_discretization_diagnostic_2026_09.json"


def test_registered_d3_diagnostic_reverifies():
    manifest = json.loads(D3_MANIFEST.read_text())
    preflight = json.loads(D3_PREFLIGHT.read_text())
    evidence = json.loads(D3_EVIDENCE.read_text())
    assert evidence["manifest"]["sha256"] == ca.sha256_file(D3_MANIFEST)
    assert evidence["preflight"]["sha256"] == ca.sha256_file(D3_PREFLIGHT)
    assert preflight["summary"]["diagnostic_allowed"] is True
    assert preflight["scheme"]["only_div_phi_U_changed"] is True
    assert manifest["epsilon_m"] == 5e-4
    assert list(manifest["directions"]) == [
        "downforce_gradient_aligned",
        "random_seed_11",
        "random_seed_2026",
    ]
    assert evidence["base_primal"]["qualified"] is True
    assert evidence["base_primal"]["returncode"] == 0
    assert evidence["adjoint"]["converged"] is True
    for side in evidence["sides"].values():
        assert side["pass"] is True
        assert side["geometry_pass"] is True
        assert side["immobility_pass"] is True
        assert side["check_mesh_qualified"] is True
    for record in evidence["diagnostic"].values():
        assert record["status"] == "ok"
        assert record["ratio_upwind"] == pytest.approx(
            record["fd_upwind"] / record["analytic_upwind"], rel=1e-9
        )
        assert record["ratio_linearUpwind"] == pytest.approx(
            record["fd_linearUpwind"] / record["analytic_linearUpwind"], rel=1e-9
        )
    assert evidence["interpretation"]["n_improved_across_the_gate"] == 2
    assert evidence["interpretation"]["n_worsened_controls"] == 1
    assert evidence["interpretation"]["supports_discretization_cause"] is False
    assert evidence["summary"]["derivative_qualified"] is False
    assert evidence["summary"]["shape_update_allowed"] is False
    assert evidence["summary"]["original_verdict_unchanged"] is True
