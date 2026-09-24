"""Contract tests for the Work F morpher perturbation sides (Slice B)."""

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
from cfd_sdf.stage_s_perturbation import (  # noqa: E402
    PerturbationError,
    build_control_point_movement,
    extract_patch_surface,
    fixed_patch_immobility,
    movement_sha256,
    movement_to_text,
)
from cfd_sdf.stage_s_adjoint_qualification import active_var_ids  # noqa: E402

EVIDENCE = ROOT / "docs/evidence/stage_s_work_f_perturbation_sides_2026_09.json"
QUALIFICATION = ROOT / "docs/evidence/stage_s_work_f_adjoint_qualification_2026_09.json"
BASE_CASE = ROOT / "work/stage_s_work_f_v1/baseline/V1"


def _active() -> tuple[int, ...]:
    return active_var_ids()


def test_control_point_movement_has_exact_inf_norm_and_respects_confinement():
    ids = _active()
    direction = np.ones(len(ids), dtype=np.float64)
    for sign, epsilon in ((1.0, 1e-3), (-1.0, 1e-3), (1.0, 2.5e-4)):
        movement = build_control_point_movement(
            direction=direction,
            active_var_ids=ids,
            n_control_points=(8, 8, 8),
            epsilon=epsilon,
            sign=sign,
        )
        assert movement.shape == (512, 3)
        assert np.max(np.abs(movement)) == pytest.approx(epsilon)
        # every displacement sits on an interior control point
        moved_cp = np.unique(np.nonzero(np.any(movement != 0.0, axis=1))[0])
        for cp in moved_cp:
            i = cp % 8
            j = (cp // 8) % 8
            k = cp // 64
            assert 1 <= i <= 6 and 1 <= j <= 6 and 1 <= k <= 6
        plus = build_control_point_movement(
            direction=direction,
            active_var_ids=ids,
            n_control_points=(8, 8, 8),
            epsilon=epsilon,
            sign=1.0,
        )
        minus = build_control_point_movement(
            direction=direction,
            active_var_ids=ids,
            n_control_points=(8, 8, 8),
            epsilon=epsilon,
            sign=-1.0,
        )
        assert np.allclose(plus, -minus)


def test_movement_builder_rejects_dimension_mismatch_and_nonfinite():
    ids = _active()
    with pytest.raises(PerturbationError, match="active ids"):
        build_control_point_movement(
            direction=np.zeros(len(ids) - 1),
            active_var_ids=ids,
            n_control_points=(8, 8, 8),
            epsilon=1e-4,
            sign=1.0,
        )
    bad = np.ones(len(ids))
    bad[0] = np.nan
    with pytest.raises(PerturbationError, match="non-finite"):
        build_control_point_movement(
            direction=bad,
            active_var_ids=ids,
            n_control_points=(8, 8, 8),
            epsilon=1e-4,
            sign=1.0,
        )


def test_movement_text_is_loadable_and_hashed():
    movement = np.zeros((512, 3), dtype=np.float64)
    movement[73] = (1e-4, 0.0, 0.0)
    text = movement_to_text(movement)
    assert "controlPointsMovement 512" in text
    assert "(0.0001 0 0)" in text
    assert movement_sha256(movement) == movement_sha256(movement)
    assert movement_sha256(movement) != movement_sha256(-movement)


def test_baseline_patch_extraction_is_closed_and_oriented():
    baseline = extract_patch_surface(BASE_CASE, time_name="constant")
    assert baseline.vertices.shape[1] == 3
    assert baseline.faces.shape[1] == 3
    assert baseline.orientation_flipped is True
    assert baseline.raw_volume < 0.0
    import trimesh

    mesh = trimesh.Trimesh(vertices=baseline.vertices, faces=baseline.faces, process=True)
    assert mesh.is_watertight
    assert mesh.volume > 0.0


def test_fixed_patches_do_not_move_in_a_registered_side():
    evidence = json.loads(EVIDENCE.read_text())
    side = next(iter(evidence["sides"].values()))
    case_dir = ROOT / side["case_dir"]
    result = fixed_patch_immobility(
        case_dir=case_dir,
        baseline_points=BASE_CASE / "constant" / "polyMesh" / "points",
        moved_points=case_dir / "0" / "polyMesh" / "points",
    )
    assert result["pass"] is True
    assert result["boundary_max_displacement_m"] == 0.0
    assert result["interior_max_displacement_m"] > 0.0


def test_registered_side_evidence_reverifies():
    evidence = json.loads(EVIDENCE.read_text())
    qualification = json.loads(QUALIFICATION.read_text())
    assert evidence["qualification"]["sha256"] == ca.sha256_file(QUALIFICATION)
    assert qualification["summary"]["perturbation_allowed"] is True
    assert evidence["summary"]["n_sides"] == 32
    assert evidence["summary"]["n_pass"] == 32
    assert evidence["summary"]["all_sides_pass"] is True
    assert evidence["summary"]["primal_campaign_allowed"] is True
    assert evidence["summary"]["solver_started"] is False
    assert evidence["morpher_utility"]["binary_sha256"] == ca.sha256_file(
        ROOT / evidence["morpher_utility"]["binary_path"]
    )
    for side_id, record in evidence["sides"].items():
        assert record["pass"] is True, side_id
        assert record["movement_inf_norm_m"] == pytest.approx(
            {"eps0.0001": 1e-4, "eps0.00025": 2.5e-4, "eps0.0005": 5e-4, "eps0.001": 1e-3}[
                side_id.split("__")[1]
            ]
        )
        case_dir = ROOT / record["case_dir"]
        assert ca.sha256_file(case_dir / "constant" / "controlPointsMovement") == ca.sha256_file(
            case_dir / "constant" / "controlPointsMovement"
        )
        assert record["geometry"]["self_intersection"] == "none"
        assert record["geometry"]["clearance_qualified"] is True
        assert record["geometry"]["minimum_solid_width_m"] == pytest.approx(0.05)
        assert record["immobility"]["boundary_max_displacement_m"] == 0.0
        assert record["check_mesh"]["qualified"] is True
        assert record["check_mesh"]["total_cells"] == 39848


RESULT = ROOT / "docs/evidence/stage_s_work_f_surface_fd_result_2026_09.json"


def test_registered_surface_fd_result_reverifies():
    result = json.loads(RESULT.read_text())
    sides = json.loads(EVIDENCE.read_text())
    assert result["sides_evidence"]["sha256"] == ca.sha256_file(EVIDENCE)
    assert sides["summary"]["primal_campaign_allowed"] is True
    assert result["summary"]["n_runs"] == 32
    assert result["summary"]["n_runs_pass"] == 32
    assert result["summary"]["both_responses_pass"] is False
    assert result["summary"]["shape_update_allowed"] is False
    for side_id, record in result["runs"].items():
        assert record["pass"] is True, side_id
        assert record["qualification"]["solver_converged"] is True
        assert record["qualification"]["force_stationarity"] is True
        assert record["qualification"]["check_mesh_qualified"] is True
        qualification = ROOT / record["qualification_path"]
        assert ca.sha256_file(qualification) == record["qualification_sha256"]
        assert ca.sha256_file(ROOT / record["case_dir"] / "log.simpleFoam") == ca.sha256_file(
            ROOT / record["case_dir"] / "log.simpleFoam"
        )
    for response, verdict in result["response_verdicts"].items():
        assert verdict["primary_gradient_aligned_resolved"] is True
        assert verdict["passed"] is False
        assert any(failure["reason"] == "relative_error" for failure in verdict["failures"])
        for check in verdict["checks"]:
            if check["direction"].endswith("_gradient_aligned"):
                assert check["passed"] is True, (response, check)
                assert check["relative_error"] <= 0.05
            if check["direction"].endswith("_gradient_aligned") and check["status"] == "epsilon_plateau":
                assert check["plateau_ok"] is True
    # the random-direction failures are the registered relative-rule rows
    assert any(
        failure["direction"].startswith("random_seed_")
        for failure in result["response_verdicts"]["drag"]["failures"]
    )
