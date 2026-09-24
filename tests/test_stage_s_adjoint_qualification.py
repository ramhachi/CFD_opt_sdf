"""Contract tests for the Work F base-adjoint qualification (Slice A)."""

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
from cfd_sdf.stage_s_adjoint_qualification import (  # noqa: E402
    DERIVATIVE_HEADER_COLUMNS,
    AdjointQualificationError,
    active_var_ids,
    build_direction_artifact,
    materialize_direction,
    parse_derivative_file,
    qualification_checks,
    random_direction,
    response_derivative_vector,
    var_id_to_ijk_component,
)

ARTIFACT = ROOT / "docs/evidence/stage_s_work_f_adjoint_qualification_2026_09.json"
RUN_EVIDENCE = ROOT / "docs/evidence/stage_s_work_f_adjoint_run_2026_09.json"


def _derivative_text(var_ids, totals) -> str:
    header = " ".join(DERIVATIVE_HEADER_COLUMNS)
    rows = [
        f"{var_id} {total:.10g} 0 0 0 0 0 0 0 0 0"
        for var_id, total in zip(var_ids, totals, strict=True)
    ]
    return "\n".join([header, *rows]) + "\n"


def _write_derivative(tmp_path: Path, name: str, var_ids, totals) -> Path:
    path = tmp_path / name
    path.write_text(_derivative_text(var_ids, totals), encoding="utf-8")
    return path


def _active() -> tuple[int, ...]:
    return active_var_ids()


def test_active_var_ids_are_the_interior_components_only():
    ids = _active()
    assert len(ids) == 216 * 3
    for var_id in ids:
        i, j, k, component = var_id_to_ijk_component(var_id)
        assert 1 <= i <= 6 and 1 <= j <= 6 and 1 <= k <= 6
        assert 0 <= component <= 2
    # a boundary control point's component is not active
    boundary = (0 * 64 + 0 * 8 + 0) * 3
    assert boundary not in ids


def test_var_id_mapping_round_trips():
    for var_id in _active():
        i, j, k, component = var_id_to_ijk_component(var_id)
        assert var_id == (k * 64 + j * 8 + i) * 3 + component
    with pytest.raises(AdjointQualificationError, match="outside"):
        var_id_to_ijk_component(8 * 8 * 8 * 3)


def test_parse_rejects_wrong_solver_and_bad_header(tmp_path: Path):
    ids = _active()
    path = _write_derivative(tmp_path, "volumetricBSplinesadjDragESI100", ids, [1.0] * len(ids))
    with pytest.raises(AdjointQualificationError, match="expected solver"):
        parse_derivative_file(path, expected_solver="adjDownforce")
    bad = tmp_path / "volumetricBSplinesadjDragESI100"
    bad.write_text("wrong header\n1 2 3\n", encoding="utf-8")
    with pytest.raises(AdjointQualificationError, match="header"):
        parse_derivative_file(bad, expected_solver="adjDrag")


def test_parse_rejects_non_finite_totals(tmp_path: Path):
    ids = _active()
    values = [1.0] * len(ids)
    values[3] = float("nan")
    path = _write_derivative(tmp_path, "volumetricBSplinesadjDragESI100", ids, values)
    with pytest.raises(AdjointQualificationError, match="non-finite"):
        parse_derivative_file(path, expected_solver="adjDrag")


def test_qualification_checks_reject_duplicates_and_set_mismatch(tmp_path: Path):
    ids = _active()
    drag = parse_derivative_file(
        _write_derivative(
            tmp_path,
            "volumetricBSplinesadjDragESI100",
            [*ids[:-1], ids[-1]],
            [1.0] * len(ids),
        ),
        expected_solver="adjDrag",
    )
    downforce = parse_derivative_file(
        _write_derivative(
            tmp_path,
            "volumetricBSplinesadjDownforceESI100",
            ids,
            [0.5] * len(ids),
        ),
        expected_solver="adjDownforce",
    )
    assert all(qualification_checks(drag=drag, downforce=downforce, active_ids=ids).values())
    short = parse_derivative_file(
        _write_derivative(
            tmp_path,
            "volumetricBSplinesadjDragESI101",
            ids[:-1],
            [1.0] * (len(ids) - 1),
        ),
        expected_solver="adjDrag",
    )
    checks = qualification_checks(drag=short, downforce=downforce, active_ids=ids)
    assert checks["drag_matches_active_set"] is False
    assert checks["expected_active_count"] is False


def test_response_derivative_vector_applies_the_registered_sign(tmp_path: Path):
    ids = _active()
    derivative = parse_derivative_file(
        _write_derivative(
            tmp_path,
            "volumetricBSplinesadjDownforceESI100",
            ids,
            [1.0 + index / 1000.0 for index in range(len(ids))],
        ),
        expected_solver="adjDownforce",
    )
    plus = response_derivative_vector(derivative, active_ids=ids, objective_sign=1.0)
    minus = response_derivative_vector(derivative, active_ids=ids, objective_sign=-1.0)
    assert np.allclose(plus, -minus)
    assert plus[0] == pytest.approx(1.0)


def test_materialize_and_random_directions_are_deterministic():
    ids = _active()
    first = materialize_direction(random_direction(ids, seed=11), kind="random", seed=11)
    second = materialize_direction(random_direction(ids, seed=11), kind="random", seed=11)
    other = materialize_direction(random_direction(ids, seed=2026), kind="random", seed=2026)
    assert first["sha256"] == second["sha256"]
    assert first["sha256"] != other["sha256"]
    assert first["unit_inf_norm"] == pytest.approx(1.0)
    assert first["kind"] == "random" and first["seed"] == 11


def test_build_direction_artifact_refuses_a_swapped_response(tmp_path: Path):
    ids = _active()
    drag = parse_derivative_file(
        _write_derivative(tmp_path, "volumetricBSplinesadjDragESI100", ids, [1.0] * len(ids)),
        expected_solver="adjDrag",
    )
    downforce = parse_derivative_file(
        _write_derivative(
            tmp_path, "volumetricBSplinesadjDownforceESI100", ids, [0.5] * len(ids)
        ),
        expected_solver="adjDownforce",
    )
    with pytest.raises(AdjointQualificationError, match="expected solver"):
        parse_derivative_file(Path(drag.path), expected_solver="adjDownforce")
    artifact = build_direction_artifact(
        drag=drag,
        downforce=downforce,
        active_ids=ids,
        random_seeds=(11, 2026),
        objective_signs={"drag": 1.0, "downforce": 1.0},
    )
    assert set(artifact["directions"]) == {
        "drag_gradient_aligned",
        "downforce_gradient_aligned",
        "random_seed_11",
        "random_seed_2026",
    }
    for record in artifact["directions"].values():
        assert record["unit_inf_norm"] == pytest.approx(1.0)


def test_registered_qualification_reverifies():
    artifact = json.loads(ARTIFACT.read_text())
    run = json.loads(RUN_EVIDENCE.read_text())
    assert artifact["run_evidence"]["sha256"] == ca.sha256_file(RUN_EVIDENCE)
    assert artifact["summary"]["perturbation_allowed"] is True
    assert artifact["summary"]["shape_update_allowed"] is False
    assert all(artifact["base_gates"].values())
    assert all(artifact["residual_checks"].values())
    assert artifact["derivative_contract"]["active_var_count"] == 648
    for response, record in artifact["derivative_contract"]["files"].items():
        path = ROOT / record["path"]
        assert ca.sha256_file(path) == record["sha256"]
        assert record["rows"] == 648
    for name, record in artifact["directions"].items():
        values = np.asarray(record["values"], dtype=np.float64)
        import hashlib

        assert hashlib.sha256(np.ascontiguousarray(values, dtype=np.float64).tobytes()).hexdigest() == (
            artifact["direction_hashes"][name]
        )
        assert np.max(np.abs(values)) == pytest.approx(1.0)
    log = ROOT / artifact["log"]["path"]
    assert ca.sha256_file(log) == run["log"]["sha256"]
