"""Contract tests for the Work F base adjoint case (no OpenFOAM solve)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from cfd_sdf import campaign_assertions as ca  # noqa: E402
from cfd_sdf.stage_s_adjoint_case import (  # noqa: E402
    ADJOINT_SOLVER_NAMES,
    AdjointObjective,
    AdjointPatchRoles,
    build_adjoint_field_files,
    build_adjoint_fv_schemes,
    build_adjoint_fv_solution,
    build_adjoint_ras_properties,
    build_dynamic_mesh_dict,
    build_optimisation_dict,
    render_adjoint_case,
    verify_adjoint_case,
)

PREFLIGHT = ROOT / "docs/evidence/stage_s_work_f_adjoint_preflight_2026_09.json"
ADJOINT_CASE = ROOT / "work/stage_s_work_f_v1/adjoint/base"


def _objectives() -> tuple[AdjointObjective, ...]:
    return (
        AdjointObjective(
            response="downforce",
            solver_name=ADJOINT_SOLVER_NAMES["downforce"],
            direction=(0.0, 0.0, -1.0),
            patches=("design_candidate",),
            area_m2=0.64,
            rho_inf=1.0,
            u_inf=1.0,
        ),
        AdjointObjective(
            response="drag",
            solver_name=ADJOINT_SOLVER_NAMES["drag"],
            direction=(1.0, 0.0, 0.0),
            patches=("design_candidate",),
            area_m2=0.64,
            rho_inf=1.0,
            u_inf=1.0,
        ),
    )


def _patch_roles() -> AdjointPatchRoles:
    return AdjointPatchRoles(
        inflow=("inlet",),
        outflow=("outlet",),
        symmetry=("sideMin", "sideMax", "top"),
        walls=("bottom",),
        design="design_candidate",
    )


def _source_case(tmp_path: Path) -> Path:
    case = tmp_path / "source_case"
    (case / "system").mkdir(parents=True)
    (case / "constant").mkdir(parents=True)
    (case / "0").mkdir(parents=True)
    (case / "case_metadata.json").write_text(json.dumps({"problem_id": "test"}), encoding="utf-8")
    (case / "system" / "fvSchemes").write_text(
        "divSchemes\n{\n    default none;\n    div(phi,U) bounded Gauss upwind;\n}\n",
        encoding="utf-8",
    )
    (case / "system" / "fvSolution").write_text(
        "solvers\n{\n    p { solver GAMG; }\n}\n"
        "relaxationFactors\n{\n    fields { p 0.2; }\n    equations { U 0.5; }\n}\n",
        encoding="utf-8",
    )
    return case


def test_optimisation_dict_declares_both_registered_solvers():
    text = build_optimisation_dict(
        objectives=_objectives(),
        primal_iterations=3000,
        primal_residual=1e-6,
        adjoint_iterations=3000,
        adjoint_residual=1e-6,
    )
    assert "optimisationManager singleRun;" in text
    assert "adjDownforce" in text and "adjDrag" in text
    assert "direction  (0. 0. -1.);" in text
    assert "direction  (1. 0. 0.);" in text
    assert "shapeType       volumetricBSplines;" in text
    assert "sensitivityType surface;" in text
    assert "includeSurfaceArea true;" in text
    assert "Aref       0.64;" in text
    assert text.count("solver                 adjointSimple;") == 2


def test_dynamic_mesh_dict_declares_the_bspline_morpher():
    text = build_dynamic_mesh_dict(
        box_min=(-0.6, -0.45, -0.25),
        box_max=(0.55, 0.45, 0.25),
        n_cps=(8, 8, 8),
        degree=(3, 3, 3),
    )
    assert "solver volumetricBSplinesMotionSolver;" in text
    assert "controlPointsDefinition axisAligned;" in text
    assert "confineBoundaryControlPoints true;" in text
    assert "lowerCpBounds (-0.6 -0.45 -0.25);" in text
    assert "nCPsU   8;" in text


def test_adjoint_fields_use_the_registered_patch_mapping():
    files = build_adjoint_field_files(_patch_roles())
    assert set(files) == {"0/pa", "0/Ua"}
    pa, ua = files["0/pa"], files["0/Ua"]
    assert "adjointFarFieldPressure;" in pa and "inlet" in pa
    assert "adjointInletVelocity;" in ua
    assert "adjointOutletVelocity;" in ua
    assert "adjointWallVelocity;" in ua
    assert "symmetryPlane;" in pa and "symmetryPlane;" in ua
    assert "internalField   uniform 0;" in pa
    assert "internalField   uniform ( 0 0 0 );" in ua


def test_adjoint_ras_properties_declare_the_laminar_adjoint_model():
    text = build_adjoint_ras_properties()
    assert "adjointRASModel   adjointLaminar;" in text
    assert "adjointTurbulence on;" in text


def test_adjoint_fv_schemes_adds_the_suffixed_convection_entries():
    source = "divSchemes\n{\n    default none;\n    div(phi,U) bounded Gauss upwind;\n}\n"
    updated = build_adjoint_fv_schemes(source, ("adjDownforce", "adjDrag"))
    assert "div(-phi,UaadjDownforce) bounded Gauss upwind;" in updated
    assert "div(-phi,UaadjDrag) bounded Gauss upwind;" in updated
    assert "div(phi,U) bounded Gauss upwind;" in updated
    assert "default Gauss linear;" in updated
    assert "default none;" not in updated
    with pytest.raises(ValueError, match="divSchemes"):
        build_adjoint_fv_schemes("ddtSchemes { default steadyState; }", ("adjDrag",))


def test_adjoint_fv_solution_adds_regex_solver_and_relaxation_entries():
    source = (
        "solvers\n{\n    p { solver GAMG; }\n}\n"
        "relaxationFactors\n{\n    fields { p 0.2; }\n    equations { U 0.5; }\n}\n"
    )
    updated = build_adjoint_fv_solution(source)
    assert '"(U|Ua).*"' in updated
    assert '"(p|pa).*"' in updated
    assert '"(m|ma).*"' in updated
    assert '"(d|da).*"' in updated
    assert '"pa.*" 0.3;' in updated
    assert '"Ua.*" 0.7;' in updated
    with pytest.raises(ValueError, match="solvers block"):
        build_adjoint_fv_solution("SIMPLE { nNonOrthogonalCorrectors 0; }")


def test_render_refuses_overwrite_and_verify_passes(tmp_path: Path):
    source = _source_case(tmp_path)
    target = tmp_path / "adjoint"
    render_adjoint_case(
        source_case=source,
        target_case=target,
        objectives=_objectives(),
        patch_roles=_patch_roles(),
        box_min=(-0.6, -0.45, -0.25),
        box_max=(0.55, 0.45, 0.25),
        n_cps=(8, 8, 8),
        degree=(3, 3, 3),
        primal_iterations=3000,
        primal_residual=1e-6,
        adjoint_iterations=3000,
        adjoint_residual=1e-6,
    )
    verdict = verify_adjoint_case(target, objectives=_objectives(), patch_roles=_patch_roles())
    assert verdict["pass"] is True, verdict["failed_checks"]
    with pytest.raises(FileExistsError, match="already exists"):
        render_adjoint_case(
            source_case=source,
            target_case=target,
            objectives=_objectives(),
            patch_roles=_patch_roles(),
            box_min=(-0.6, -0.45, -0.25),
            box_max=(0.55, 0.45, 0.25),
            n_cps=(8, 8, 8),
            degree=(3, 3, 3),
            primal_iterations=3000,
            primal_residual=1e-6,
            adjoint_iterations=3000,
            adjoint_residual=1e-6,
        )


def test_verify_fails_closed_for_a_wrong_direction(tmp_path: Path):
    source = _source_case(tmp_path)
    target = tmp_path / "adjoint"
    render_adjoint_case(
        source_case=source,
        target_case=target,
        objectives=_objectives(),
        patch_roles=_patch_roles(),
        box_min=(-0.6, -0.45, -0.25),
        box_max=(0.55, 0.45, 0.25),
        n_cps=(8, 8, 8),
        degree=(3, 3, 3),
        primal_iterations=3000,
        primal_residual=1e-6,
        adjoint_iterations=3000,
        adjoint_residual=1e-6,
    )
    wrong = (
        AdjointObjective(
            response="downforce",
            solver_name=ADJOINT_SOLVER_NAMES["downforce"],
            direction=(0.0, 0.0, 1.0),
            patches=("design_candidate",),
            area_m2=0.64,
            rho_inf=1.0,
            u_inf=1.0,
        ),
        _objectives()[1],
    )
    verdict = verify_adjoint_case(target, objectives=wrong, patch_roles=_patch_roles())
    assert verdict["pass"] is False
    assert "downforce_direction" in verdict["failed_checks"]


def test_registered_adjoint_preflight_reverifies():
    artifact = json.loads(PREFLIGHT.read_text())
    assert artifact["kind"] == "stage_s_work_f_adjoint_preflight"
    assert artifact["summary"]["preflight_pass"] is True
    assert artifact["summary"]["adjoint_allowed"] is True
    assert artifact["summary"]["solver_started"] is False
    assert artifact["structural_checks"]["pass"] is True
    assert artifact["openfoam_dictionary_check"]["pass"] is True
    case_dir = ROOT / artifact["adjoint_case"]["path"]
    assert ca.sha256_file(case_dir / "system" / "optimisationDict") == artifact[
        "adjoint_case"
    ]["optimisation_dict_sha256"]
    assert ca.sha256_file(case_dir / "constant" / "dynamicMeshDict") == artifact[
        "adjoint_case"
    ]["dynamic_mesh_dict_sha256"]
    assert case_dir == ADJOINT_CASE


RUN = ROOT / "docs/evidence/stage_s_work_f_adjoint_run_2026_09.json"


def test_registered_adjoint_run_reverifies():
    evidence = json.loads(RUN.read_text())
    assert evidence["summary"]["adjoint_converged"] is True
    assert evidence["summary"]["analytic_derivatives_ready"] is True
    assert evidence["summary"]["perturbation_allowed"] is False
    assert evidence["summary"]["shape_update_allowed"] is False
    assert evidence["openfoam_run"]["returncode"] == 0
    assert evidence["openfoam_run"]["timed_out"] is False
    assert set(evidence["analytic"]["found_solvers"]) == {"adjDownforce", "adjDrag"}
    case_dir = ROOT / evidence["case_dir"]
    for name, sha in evidence["analytic"]["design_variable_derivative_files"].items():
        assert ca.sha256_file(case_dir / "optimisation" / "derivatives" / name) == sha
    for relative, sha in evidence["analytic"]["face_sens_normal_files"].items():
        assert ca.sha256_file(case_dir / relative) == sha
    control_points = ROOT / evidence["analytic"]["control_points_csv"]["path"]
    assert ca.sha256_file(control_points) == evidence["analytic"]["control_points_csv"]["sha256"]
    log = ROOT / evidence["log"]["path"]
    assert ca.sha256_file(log) == evidence["log"]["sha256"]
    assert evidence["log"]["converged_markers"] >= 3
