from __future__ import annotations

import json
from pathlib import Path

import pytest

from cfd_sdf.convergence_qualification import evaluate_openfoam_convergence_bundle
from cfd_sdf.openfoam_evidence import (
    OPENFOAM_FLOW_CASE_EVIDENCE_SCHEMA_VERSION,
    extract_openfoam_flow_case_evidence,
    write_openfoam_flow_case_evidence,
)
from cfd_sdf.solver_case_manifest import SolverCaseManifest, SolverFlowCasePlan


def test_extracts_complete_evidence_and_is_consumed_by_qualification(
    tmp_path: Path,
) -> None:
    case = _write_case(tmp_path, response_ids=("rotated_force",))
    _write_log(
        case,
        """
Time = 1
DILUPBiCGStab:  Solving for Ux, Initial residual = 1e-4, Final residual = 5e-7, No Iterations 1
DILUPBiCGStab:  Solving for Uy, Initial residual = 1e-4, Final residual = 4e-7, No Iterations 1
DICPCG:  Solving for p, Initial residual = 1e-4, Final residual = 6e-7, No Iterations 2
DICPCG:  Solving for k, Initial residual = 1e-4, Final residual = 3e-7, No Iterations 2
DICPCG:  Solving for omega, Initial residual = 1e-4, Final residual = 2e-7, No Iterations 2
time step continuity errors : sum local = 1e-8, global = -2e-9, cumulative = -3e-9
normalized mass imbalance : -2e-5
rotated_force : 1.0000
Adjoint solver resp_rotated_force
DILUPBiCGStab:  Solving for Uaresp_rotated_forcex, Initial residual = 1e-4, Final residual = 5e-7, No Iterations 1
DICPCG:  Solving for paresp_rotated_force, Initial residual = 1e-4, Final residual = 4e-7, No Iterations 2
Time = 2
DILUPBiCGStab:  Solving for Ux, Initial residual = 1e-4, Final residual = 4e-7, No Iterations 1
DICPCG:  Solving for p, Initial residual = 1e-4, Final residual = 5e-7, No Iterations 2
DICPCG:  Solving for k, Initial residual = 1e-4, Final residual = 2e-7, No Iterations 2
DICPCG:  Solving for omega, Initial residual = 1e-4, Final residual = 2e-7, No Iterations 2
normalised_mass_imbalance = 1e-5
rotated_force : 1.0001
Adjoint solver resp_rotated_force
DILUPBiCGStab:  Solving for Uaresp_rotated_forcey, Initial residual = 1e-4, Final residual = 4e-7, No Iterations 1
DICPCG:  Solving for karesp_rotated_force, Initial residual = 1e-4, Final residual = 4e-7, No Iterations 2
End
""",
    )

    evidence = extract_openfoam_flow_case_evidence(case)

    assert evidence["schema_version"] == OPENFOAM_FLOW_CASE_EVIDENCE_SCHEMA_VERSION
    assert evidence["status"] == "complete"
    assert evidence["complete"] is True
    assert evidence["sources"]["solver_log"]["path"] == "log.adjointOptimisationFoam"
    assert [row["field"] for row in evidence["primal_residual_history"]] == [
        "Ux",
        "Uy",
        "p",
        "k",
        "omega",
        "Ux",
        "p",
        "k",
        "omega",
    ]
    assert evidence["normalized_mass_imbalance_history"] == pytest.approx(
        [2.000020000256988e-05, 1.0000050000476698e-05]
    )
    assert evidence["response_history"] == {"rotated_force": [1.0, 1.0001]}
    assert [row["field"] for row in evidence["adjoint_residual_history"]["rotated_force"]] == [
        "Uaresp_rotated_forcex",
        "paresp_rotated_force",
        "Uaresp_rotated_forcey",
        "karesp_rotated_force",
    ]
    assert evidence["diagnostics"]["continuity_error_history"] == [
        {
            "index": 0,
            "sum_local": 1.0e-8,
            "global": -2.0e-9,
            "cumulative": -3.0e-9,
        }
    ]
    assert evidence["diagnostics"]["adjoint_solver_markers"] == {"rotated_force": 2}

    result = evaluate_openfoam_convergence_bundle(
        _manifest("rotated_force"), {"straight": evidence}
    )
    assert result["qualified"] is True


def test_raw_continuity_error_is_not_invented_as_normalized_mass_imbalance(
    tmp_path: Path,
) -> None:
    case = _write_case(tmp_path, response_ids=("drag",))
    (case / "cfd_sdf_normalized_mass_imbalance.json").unlink()
    _write_log(
        case,
        _minimum_complete_log("drag").replace(
            "normalized mass imbalance : 1e-5\n", ""
        ),
    )

    evidence = extract_openfoam_flow_case_evidence(case)

    assert evidence["normalized_mass_imbalance_history"] == []
    assert evidence["diagnostics"]["continuity_error_history"][0]["global"] == pytest.approx(
        -2.0e-9
    )
    assert "missing_normalized_mass_imbalance_artifact" in evidence[
        "incomplete_reasons"
    ]
    assert evidence["status"] == "incomplete"
    assert evaluate_openfoam_convergence_bundle(
        _manifest("drag"), {"straight": evidence}
    )["qualified"] is False


def test_unscoped_v2512_adjoint_fields_require_and_use_compiler_solver_marker(
    tmp_path: Path,
) -> None:
    case = _write_case(tmp_path, response_ids=("drag",))
    suffix = "resp_drag"
    runtime_log = (
        _minimum_complete_log("drag")
        .replace(f"Ua{suffix}x", "Uax")
        .replace(f"pa{suffix}", "pa")
    )
    _write_log(case, runtime_log)

    evidence = extract_openfoam_flow_case_evidence(case)

    assert evidence["status"] == "complete"
    assert [
        row["field"] for row in evidence["adjoint_residual_history"]["drag"]
    ] == ["Uax", "pa"]
    assert evidence["diagnostics"]["adjoint_solver_markers"] == {"drag": 1}

    unmarked_case = _write_case(tmp_path / "unmarked", response_ids=("drag",))
    _write_log(
        unmarked_case,
        runtime_log.replace("Adjoint solver resp_drag\n", ""),
    )
    unmarked = extract_openfoam_flow_case_evidence(unmarked_case)
    assert unmarked["adjoint_residual_history"]["drag"] == []
    assert "missing_adjoint_residual_history:drag" in unmarked["incomplete_reasons"]


def test_absent_logs_and_data_return_structured_incomplete_evidence(
    tmp_path: Path,
) -> None:
    case = _write_case(tmp_path, response_ids=("drag",))
    (case / "cfd_sdf_normalized_mass_imbalance.json").unlink()

    evidence = extract_openfoam_flow_case_evidence(case)

    assert evidence["solver_log"] is None
    assert evidence["primal_residual_history"] == []
    assert evidence["normalized_mass_imbalance_history"] == []
    assert evidence["response_history"] == {"drag": []}
    assert evidence["adjoint_residual_history"] == {"drag": []}
    assert evidence["sources"]["solver_log"]["status"] == "missing"
    assert set(evidence["incomplete_reasons"]) >= {
        "missing_solver_log",
        "missing_normalized_mass_imbalance_artifact",
        "missing_primal_residual_history",
        "missing_normalized_mass_imbalance_history",
        "missing_response_history:drag",
        "missing_adjoint_residual_history:drag",
    }


def test_missing_or_invalid_compiler_metadata_cannot_establish_response_evidence(
    tmp_path: Path,
) -> None:
    case = _write_case(tmp_path, response_ids=("drag",))
    (case / "generated_openfoam_responses.json").unlink()
    _write_log(case, _minimum_complete_log("drag"))

    missing = extract_openfoam_flow_case_evidence(case)
    assert missing["response_history"] == {}
    assert missing["adjoint_residual_history"] == {}
    assert "missing_response_metadata" in missing["incomplete_reasons"]

    (case / "generated_openfoam_responses.json").write_text("{broken", encoding="utf-8")
    invalid = extract_openfoam_flow_case_evidence(case)
    assert invalid["sources"]["response_metadata"]["status"] == "invalid"
    assert "invalid_response_metadata" in invalid["incomplete_reasons"]


def test_per_response_adjoint_fields_are_separated_and_missing_one_is_incomplete(
    tmp_path: Path,
) -> None:
    case = _write_case(tmp_path, response_ids=("drag", "side_force"))
    _write_log(case, _minimum_complete_log("drag"))

    evidence = extract_openfoam_flow_case_evidence(case)

    assert evidence["response_history"]["drag"] == [1.0, 1.0001]
    assert evidence["response_history"]["side_force"] == []
    assert evidence["adjoint_residual_history"]["drag"]
    assert evidence["adjoint_residual_history"]["side_force"] == []
    assert "missing_response_history:side_force" in evidence["incomplete_reasons"]
    assert "missing_adjoint_residual_history:side_force" in evidence[
        "incomplete_reasons"
    ]


def test_malformed_required_residual_invalidates_its_category_instead_of_using_partial_data(
    tmp_path: Path,
) -> None:
    case = _write_case(tmp_path, response_ids=("drag",))
    log = _minimum_complete_log("drag").replace(
        "Final residual = 5e-7, No Iterations 1",
        "Final residual = nan, No Iterations 1",
        1,
    )
    _write_log(case, log)

    evidence = extract_openfoam_flow_case_evidence(case)

    assert evidence["primal_residual_history"] == []
    assert "invalid_solver_residual_line" in evidence["incomplete_reasons"]
    assert "missing_primal_residual_history" in evidence["incomplete_reasons"]
    assert evaluate_openfoam_convergence_bundle(
        _manifest("drag"), {"straight": evidence}
    )["qualified"] is False


def test_unknown_solver_log_candidates_are_ambiguous_and_fail_closed(tmp_path: Path) -> None:
    case = _write_case(tmp_path, response_ids=("drag",), application="simpleFoam")
    _write_log(case, _minimum_complete_log("drag"), filename="log.simpleFoam")
    _write_log(case, _minimum_complete_log("drag"), filename="log.adjointOptimisationFoam")

    evidence = extract_openfoam_flow_case_evidence(case)

    assert evidence["solver_log"] is None
    assert evidence["sources"]["solver_log"]["status"] == "ambiguous"
    assert "ambiguous_solver_log" in evidence["incomplete_reasons"]


def test_writer_is_deterministic(tmp_path: Path) -> None:
    case = _write_case(tmp_path / "case_source", response_ids=("drag",))
    _write_log(case, _minimum_complete_log("drag"))
    evidence = extract_openfoam_flow_case_evidence(case)

    first = write_openfoam_flow_case_evidence(evidence, tmp_path / "a.json")
    second = write_openfoam_flow_case_evidence(evidence, tmp_path / "b.json")

    assert first.read_bytes() == second.read_bytes()
    assert json.loads(first.read_text(encoding="utf-8"))["complete"] is True


def test_non_directory_input_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="does not exist"):
        extract_openfoam_flow_case_evidence(tmp_path / "not-a-case")


def _write_case(
    root: Path,
    *,
    response_ids: tuple[str, ...],
    application: str = "adjointOptimisationFoam",
) -> Path:
    case = root / "case"
    (case / "system").mkdir(parents=True)
    (case / "system/controlDict").write_text(
        f"application {application};\n", encoding="utf-8"
    )
    mappings = [
        {
            "response_id": response_id,
            "objective_name": response_id,
            "adjoint_solver_id": f"resp_{response_id}",
            "adjoint_velocity_field": f"Uaresp_{response_id}",
        }
        for response_id in response_ids
    ]
    (case / "generated_openfoam_responses.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "kind": "generated_openfoam_responses",
                "response_mappings": mappings,
            }
        ),
        encoding="utf-8",
    )
    (case / "generated_openfoam_physics.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "kind": "generated_openfoam_physics",
                "flow_case_id": "straight",
                "generated": {"turbulence": {"model": "k_omega_sst"}},
                "normalized_mass_imbalance": {
                    "open_patch_ids": ["inlet", "outlet"],
                },
            }
        ),
        encoding="utf-8",
    )
    (case / "cfd_sdf_normalized_mass_imbalance.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "kind": "openfoam_normalized_mass_imbalance",
                "flow_case_id": "straight",
                "open_patch_ids": ["inlet", "outlet"],
                "epsilon": 1e-30,
                "formula": "abs(sum signed flux)/max(sum abs(flux)/2, epsilon)",
                "measurements": [
                    {
                        "time": 1.0,
                        "signed_flux_by_patch": {"inlet": -50.0, "outlet": 49.999},
                        "absolute_flux_by_patch": {"inlet": 50.0, "outlet": 49.999},
                        "net_signed_flux": -0.001,
                        "absolute_flux_sum": 99.999,
                        "throughput": 49.9995,
                        "denominator": 49.9995,
                        "normalized_mass_imbalance": 2.000020000256988e-05,
                    },
                    {
                        "time": 2.0,
                        "signed_flux_by_patch": {"inlet": -50.0, "outlet": 49.9995},
                        "absolute_flux_by_patch": {"inlet": 50.0, "outlet": 49.9995},
                        "net_signed_flux": -0.0005,
                        "absolute_flux_sum": 99.9995,
                        "throughput": 49.99975,
                        "denominator": 49.99975,
                        "normalized_mass_imbalance": 1.0000050000476698e-05,
                    },
                ],
                "sources": {},
            }
        ),
        encoding="utf-8",
    )
    return case


def _write_log(case: Path, text: str, *, filename: str = "log.adjointOptimisationFoam") -> None:
    (case / filename).write_text(text.lstrip(), encoding="utf-8", newline="\n")


def _minimum_complete_log(response_id: str) -> str:
    suffix = f"resp_{response_id}"
    return f"""
Time = 1
DILUPBiCGStab:  Solving for Ux, Initial residual = 1e-4, Final residual = 5e-7, No Iterations 1
DICPCG:  Solving for p, Initial residual = 1e-4, Final residual = 4e-7, No Iterations 2
DICPCG:  Solving for k, Initial residual = 1e-4, Final residual = 3e-7, No Iterations 2
DICPCG:  Solving for omega, Initial residual = 1e-4, Final residual = 2e-7, No Iterations 2
time step continuity errors : sum local = 1e-8, global = -2e-9, cumulative = -3e-9
normalized mass imbalance : 1e-5
{response_id} : 1.0
Adjoint solver {suffix}
DILUPBiCGStab:  Solving for Ua{suffix}x, Initial residual = 1e-4, Final residual = 5e-7, No Iterations 1
DICPCG:  Solving for pa{suffix}, Initial residual = 1e-4, Final residual = 4e-7, No Iterations 2
Time = 2
{response_id} : 1.0001
End
"""


def _manifest(response_id: str) -> SolverCaseManifest:
    plan = SolverFlowCasePlan(
        flow_case_id="straight",
        case_directory_name="flow_straight",
        requested={
            "convergence_criteria": {
                "primal_final_residual_max": 1.0e-6,
                "normalized_mass_imbalance_max": 1.0e-4,
                "response_stationarity_window": 2,
                "response_relative_range_max": 1.0e-3,
                "adjoint_final_residual_max": 1.0e-6,
            }
        },
        generated={},
        supported_response_ids=(response_id,),
        unsupported=(),
    )
    return SolverCaseManifest(
        problem_id="test_problem",
        problem_spec_sha256="0" * 64,
        solver_profile="test",
        flow_cases=(plan,),
        compile_ready=True,
        unsupported=(),
        execution_ready=True,
    )
