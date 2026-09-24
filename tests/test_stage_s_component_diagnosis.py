"""Contract tests for the Work F D4.0/D4.1 component diagnosis (solver-free)."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from cfd_sdf import campaign_assertions as ca  # noqa: E402
from cfd_sdf.stage_s_component_diagnosis import (  # noqa: E402
    CLOSURE_ABSOLUTE_TOLERANCE,
    COMPONENT_COLUMNS,
    DERIVATIVE_HEADER_COLUMNS,
    DERIVATIVE_SUM_FORMULA,
    ComponentDiagnosisError,
    cancellation_index,
    component_closure,
    contract_columns,
    drop_component_hypothesis,
    fitted_scale,
    holdout_seed,
    order_columns,
    parse_derivative_table,
    relative_gate,
    single_scalar_hypothesis,
)

MANIFEST = ROOT / "docs/evidence/stage_s_work_f_component_diagnosis_manifest_2026_09.json"
AUDIT = ROOT / "docs/evidence/stage_s_work_f_derivative_component_audit_2026_09.json"
QUALIFICATION = ROOT / "docs/evidence/stage_s_work_f_adjoint_qualification_2026_09.json"
UPWIND_DERIVATIVES = ROOT / "work/stage_s_work_f_v1/adjoint/base/optimisation/derivatives"
LINEAR_DERIVATIVES = (
    ROOT / "work/stage_s_work_f_v1/discretization_linearUpwind/adjoint/base/optimisation/derivatives"
)


def _write_table(path: Path, rows: list[list[float]]) -> Path:
    lines = [" ".join(DERIVATIVE_HEADER_COLUMNS)]
    for row in rows:
        lines.append(" ".join(f"{value:.10g}" for value in row))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _row(var_id: int, total: float, surf: float, dsdb: float) -> list[float]:
    return [var_id, total, 0.0, surf, dsdb, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]


def test_parse_order_and_contract(tmp_path: Path):
    path = _write_table(
        tmp_path / "volumetricBSplinesadjDragadjDragESI10",
        [_row(7, 3.0, 5.0, -2.0), _row(1, 1.0, 2.0, -1.0)],
    )
    table = parse_derivative_table(path, expected_solver="adjDrag")
    assert table.final_iteration == 10
    assert table.var_ids == (7, 1)
    assert table.column("dxdbSurf").tolist() == [5.0, 2.0]
    ordered = order_columns(table, (1, 7))
    contracted = contract_columns(ordered, np.asarray([2.0, 3.0]))
    assert contracted["total"] == pytest.approx(11.0)
    assert contracted["dxdbSurf"] == pytest.approx(19.0)
    assert component_closure(contracted) == pytest.approx(0.0)


def test_parse_and_order_reject_bad_inputs(tmp_path: Path):
    bad_header = tmp_path / "volumetricBSplinesadjDragadjDragESI10"
    bad_header.write_text("#varID total\n1 2\n", encoding="utf-8")
    with pytest.raises(ComponentDiagnosisError, match="unexpected header"):
        parse_derivative_table(bad_header, expected_solver="adjDrag")
    with pytest.raises(ComponentDiagnosisError, match="final iteration"):
        parse_derivative_table(
            _write_table(tmp_path / "volumetricBSplinesadjDragadjDragESI", [_row(1, 1, 2, -1)]),
            expected_solver="adjDrag",
        )
    table = parse_derivative_table(
        _write_table(tmp_path / "volumetricBSplinesadjDragadjDragESI1", [_row(1, 1, 2, -1)]),
        expected_solver="adjDrag",
    )
    with pytest.raises(ComponentDiagnosisError, match="varID set"):
        order_columns(table, (2,))
    with pytest.raises(ComponentDiagnosisError, match="direction size"):
        contract_columns(order_columns(table, (1,)), np.asarray([1.0, 2.0]))


def test_cancellation_and_gate():
    record = {"total": -0.1342488944, "dxdbVol": 0.0, "dxdbSurf": -0.20195, "dSdb": 0.06770}
    for name in ("dndb", "dxdbDirect", "dVdb"):
        record[name] = 0.0
    assert cancellation_index(record, floor=1e-9) == pytest.approx(
        (0.20195 + 0.06770) / 0.1342488944, rel=1e-6
    )
    ratio, within, sign = relative_gate(-0.13425, -0.19592)
    assert ratio == pytest.approx(1.459, rel=1e-3)
    assert within is False and sign is True
    ratio, within, sign = relative_gate(1.0, -1.0)
    assert within is False and sign is False
    assert relative_gate(0.0, 1.0) == (None, False, False)


def _audit_row(row_id: str, total: float, fd: float, *, within: bool) -> dict:
    record = {
        "row_id": row_id,
        "d_total": total,
        "fd": fd,
        "noise_floor": 1e-3,
        "within_gate": within,
    }
    for name in COMPONENT_COLUMNS:
        record[f"d_{name}"] = 0.0
    return record


def test_drop_component_and_scalar_hypotheses():
    rows = [
        _audit_row("a", 1.0, 1.0, within=True),
        _audit_row("b", 1.5, 1.0, within=False),
    ]
    rows[1]["d_dSdb"] = 0.5
    dropped = drop_component_hypothesis(rows, "dSdb")
    assert dropped["n_passing_after_drop"] == 2
    assert dropped["n_improved_from_baseline"] == 1
    assert dropped["n_worsened_controls"] == 0
    assert dropped["explains_all_directions"] is True
    same = drop_component_hypothesis(rows, "dxdbVol")
    assert same["explains_all_directions"] is False
    assert same["n_passing_after_drop"] == 1
    fit = single_scalar_hypothesis(rows)
    assert fit["explains_all_directions"] is False
    assert fitted_scale(np.asarray([1.0, 2.0]), np.asarray([2.0, 4.0])) == pytest.approx(2.0)


def test_holdout_seed_is_deterministic():
    first = holdout_seed("abc", 1)
    assert first == holdout_seed("abc", 1)
    assert first != holdout_seed("abc", 2)
    assert first != holdout_seed("abd", 1)
    with pytest.raises(ComponentDiagnosisError, match="indices start at 1"):
        holdout_seed("abc", 0)


def test_registered_component_manifest_reverifies():
    manifest = json.loads(MANIFEST.read_text())
    assert manifest["kind"] == "stage_s_work_f_component_diagnosis_manifest"
    assert manifest["registered_before_computation"] is True
    assert manifest["component_formula"]["total"] == DERIVATIVE_SUM_FORMULA
    assert manifest["component_formula"]["components"] == list(COMPONENT_COLUMNS)
    assert manifest["holdout_rule"]["n_random_directions_min"] == 2
    assert [entry["order"] for entry in manifest["ablations"]] == [1, 2]
    assert [entry["option"] for entry in manifest["ablations"]] == [
        "includeSurfaceArea",
        "includeMeshMovement",
    ]
    # machine-generated evidence stays hash-bound; the plan documents are
    # living and may be extended by a later authorized commit (the post-D3
    # plan gained its section 21 in 17cb22c after this manifest was registered)
    living_documents = {"post_d3_plan", "fd_diagnosis_plan"}
    for name, record in manifest["inputs"].items():
        if name in living_documents:
            assert (ROOT / record["path"]).is_file()
            continue
        assert ca.sha256_file(ROOT / record["path"]) == record["sha256"]
    qualification = json.loads(QUALIFICATION.read_text())
    for name, record in manifest["directions"].items():
        values = np.asarray(qualification["directions"][name]["values"], dtype=np.float64)
        array_sha = hashlib.sha256(
            np.ascontiguousarray(values, dtype=np.float64).tobytes()
        ).hexdigest()
        assert array_sha == record["sha256"]
    for scheme, directory in (
        ("upwind", UPWIND_DERIVATIVES),
        ("linearUpwind", LINEAR_DERIVATIVES),
    ):
        for response, record in manifest["derivative_files"][scheme].items():
            assert ca.sha256_file(ROOT / record["path"]) == record["sha256"]
            assert (ROOT / record["path"]).parent == directory
    assert len(manifest["openfoam_source_files"]["sha256"]) == 10


def test_registered_component_audit_reverifies():
    manifest = json.loads(MANIFEST.read_text())
    audit = json.loads(AUDIT.read_text())
    assert audit["manifest"]["sha256"] == ca.sha256_file(MANIFEST)
    checks = audit["checks"]
    assert checks["closure_within_tolerance"] is True
    assert checks["max_abs_closure"] <= CLOSURE_ABSOLUTE_TOLERANCE
    assert checks["upwind_registered_analytic_max_deviation"] == 0.0
    assert checks["linearUpwind_registered_analytic_max_deviation"] == 0.0
    upwind = [row for row in audit["rows"] if row["scheme"] == "upwind"]
    linear = [row for row in audit["rows"] if row["scheme"] == "linearUpwind"]
    assert len(upwind) == 32
    assert len(linear) == 6
    assert sorted({row["epsilon"] for row in upwind}) == [1e-4, 2.5e-4, 5e-4, 1e-3]
    assert {row["epsilon"] for row in linear} == {5e-4}
    for row in audit["rows"]:
        component_sum = sum(row[f"d_{name}"] for name in COMPONENT_COLUMNS)
        assert row["component_sum"] == pytest.approx(component_sum, rel=1e-12, abs=1e-12)
        assert row["closure"] == pytest.approx(row["d_total"] - component_sum, rel=1e-9, abs=1e-12)
        assert abs(row["closure"]) <= CLOSURE_ABSOLUTE_TOLERANCE
        assert row["cancellation_index"] > 0.0
        assert abs(row["fd_residual"] - (row["fd"] - row["d_total"])) <= 1e-12
    summary = audit["summary"]
    assert summary["component_closure_ok"] is True
    assert summary["single_component_drop_explains_upwind"] is False
    assert summary["single_component_drop_explains_linearUpwind"] is False
    assert summary["single_scalar_explains_upwind"] is False
    assert summary["single_scalar_explains_linearUpwind"] is False
    assert summary["derivative_qualified"] is False
    assert summary["shape_update_allowed"] is False
    assert sorted(audit["scheme_component_shift"]) == [
        "downforce__downforce_gradient_aligned__0.0005",
        "downforce__random_seed_11__0.0005",
        "downforce__random_seed_2026__0.0005",
        "drag__downforce_gradient_aligned__0.0005",
        "drag__random_seed_11__0.0005",
        "drag__random_seed_2026__0.0005",
    ]
