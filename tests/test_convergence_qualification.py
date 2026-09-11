from __future__ import annotations

from dataclasses import replace
import hashlib
import json
from pathlib import Path

from typer.testing import CliRunner

from cfd_sdf.cli import app
from cfd_sdf.convergence_qualification import (
    evaluate_openfoam_convergence_bundle,
    write_openfoam_convergence_qualification,
)
from cfd_sdf.problem_spec import load_problem_spec, problem_spec_sha256
from cfd_sdf.solver_case_manifest import build_openfoam_solver_case_manifest


EXAMPLE = Path("examples/g2_openfoam_compile/project.yaml")
runner = CliRunner()


def _manifest():
    return build_openfoam_solver_case_manifest(
        load_problem_spec(EXAMPLE), available_patch_ids=None
    )


def _flow_evidence(response_id: str) -> dict:
    values = [1.0 + index * 1.0e-5 for index in range(20)]
    return {
        "solver_log": "Starting solver\nEnd\n",
        "primal_residual_history": [
            {"field": "Ux", "final_residual": 5.0e-7},
            {"field": "p", "final_residual": 8.0e-7},
        ],
        "normalized_mass_imbalance_history": [2.0e-4, 5.0e-5],
        "response_history": {response_id: values},
        "adjoint_residual_history": {
            response_id: [
                {"field": "Ua", "final_residual": 7.0e-7},
                {"field": "pa", "final_residual": 6.0e-7},
            ]
        },
    }


def _all_evidence() -> dict:
    return {
        "straight": _flow_evidence("rotated_force"),
        "yawed": _flow_evidence("yaw_side_force"),
    }


def test_multipoint_numeric_evidence_passes_per_flow_and_aggregate() -> None:
    result = evaluate_openfoam_convergence_bundle(_manifest(), _all_evidence())

    assert result["status"] == "pass"
    assert result["qualified"] is True
    assert result["execution_ready"] is True
    assert {key: value["status"] for key, value in result["flow_cases"].items()} == {
        "straight": "pass",
        "yawed": "pass",
    }
    straight = result["flow_cases"]["straight"]
    assert straight["gates"]["primal_final_residual"]["observed_max"] == 8.0e-7
    assert straight["gates"]["response_stationarity"]["window"] == 20


def test_threshold_failure_fails_only_affected_flow_and_bundle() -> None:
    evidence = _all_evidence()
    evidence["yawed"]["normalized_mass_imbalance_history"][-1] = 2.0e-4

    result = evaluate_openfoam_convergence_bundle(_manifest(), evidence)

    assert result["status"] == "fail"
    assert result["qualified"] is False
    assert result["flow_cases"]["straight"]["status"] == "pass"
    yawed = result["flow_cases"]["yawed"]
    assert yawed["status"] == "fail"
    assert "gate_failed:normalized_mass_imbalance" in yawed["reasons"]


def test_missing_flow_is_not_evaluated_and_never_qualified() -> None:
    result = evaluate_openfoam_convergence_bundle(
        _manifest(), {"straight": _flow_evidence("rotated_force")}
    )

    assert result["status"] == "not_evaluated"
    assert result["qualified"] is False
    assert result["flow_cases"]["yawed"]["status"] == "not_evaluated"


def test_non_compile_ready_manifest_cannot_qualify() -> None:
    manifest = replace(
        _manifest(), compile_ready=False, unsupported=("injected_unsupported",)
    )

    result = evaluate_openfoam_convergence_bundle(manifest, _all_evidence())

    assert result["status"] == "fail"
    assert result["qualified"] is False
    assert result["manifest_unsupported"] == ["injected_unsupported"]


def test_converged_text_without_numeric_histories_cannot_pass() -> None:
    evidence = _all_evidence()
    evidence["straight"] = {"solver_log": "solution converged\nEnd\n"}

    result = evaluate_openfoam_convergence_bundle(_manifest(), evidence)

    straight = result["flow_cases"]["straight"]
    assert straight["status"] == "fail"
    assert straight["gates"]["solver_completion"]["status"] == "pass"
    assert straight["gates"]["primal_final_residual"]["status"] == "fail"
    assert straight["gates"]["response_stationarity"]["status"] == "fail"


def test_explicitly_incomplete_extractor_evidence_cannot_qualify() -> None:
    for extractor_metadata in (
        {
            "kind": "openfoam_flow_case_convergence_evidence",
            "complete": False,
        },
        {
            "kind": "openfoam_flow_case_convergence_evidence",
            "status": "incomplete",
        },
    ):
        evidence = _all_evidence()
        evidence["straight"].update(extractor_metadata)

        result = evaluate_openfoam_convergence_bundle(_manifest(), evidence)

        straight = result["flow_cases"]["straight"]
        extraction = straight["gates"]["evidence_extraction"]
        assert result["qualified"] is False
        assert straight["status"] == "fail"
        assert extraction["status"] == "fail"
        assert extraction["reason"] == "extractor_evidence_incomplete"
        assert "gate_failed:evidence_extraction" in straight["reasons"]


def test_fatal_log_pattern_fails_even_with_end_and_good_histories() -> None:
    evidence = _all_evidence()
    evidence["straight"]["solver_log"] = (
        "inconsistent patch and patchField types for patch lower\nEnd\n"
    )

    result = evaluate_openfoam_convergence_bundle(_manifest(), evidence)

    completion = result["flow_cases"]["straight"]["gates"]["solver_completion"]
    assert completion["status"] == "fail"
    assert completion["reason"] == "fatal_solver_log_pattern"


def test_trap_fpe_startup_banner_is_not_a_fatal_solver_failure() -> None:
    evidence = _all_evidence()
    evidence["straight"]["solver_log"] = (
        "trapFpe: Floating point exception trapping enabled (FOAM_SIGFPE).\nEnd\n"
    )

    result = evaluate_openfoam_convergence_bundle(_manifest(), evidence)

    completion = result["flow_cases"]["straight"]["gates"]["solver_completion"]
    assert completion == {"status": "pass", "end_marker": True, "fatal_patterns": []}


def test_actual_floating_point_exception_remains_fatal() -> None:
    evidence = _all_evidence()
    evidence["straight"]["solver_log"] = "Floating point exception (core dumped)\nEnd\n"

    result = evaluate_openfoam_convergence_bundle(_manifest(), evidence)

    completion = result["flow_cases"]["straight"]["gates"]["solver_completion"]
    assert completion["status"] == "fail"
    assert completion["reason"] == "fatal_solver_log_pattern"
    assert completion["fatal_patterns"] == ["Floating point exception"]


def test_insufficient_response_window_and_missing_adjoint_are_fail_closed() -> None:
    evidence = _all_evidence()
    evidence["straight"]["response_history"]["rotated_force"] = [1.0] * 19
    evidence["straight"]["adjoint_residual_history"] = {}

    result = evaluate_openfoam_convergence_bundle(_manifest(), evidence)

    gates = result["flow_cases"]["straight"]["gates"]
    response = gates["response_stationarity"]["responses"]["rotated_force"]
    adjoint = gates["adjoint_final_residual"]["responses"]["rotated_force"]
    assert response["reason"] == "insufficient_stationarity_window"
    assert adjoint["status"] == "fail"


def test_writer_is_deterministic(tmp_path: Path) -> None:
    result = evaluate_openfoam_convergence_bundle(_manifest(), _all_evidence())
    first = write_openfoam_convergence_qualification(result, tmp_path / "first.json")
    second = write_openfoam_convergence_qualification(result, tmp_path / "second.json")

    assert first.read_bytes() == second.read_bytes()
    assert json.loads(first.read_text(encoding="utf-8"))["qualified"] is True


def test_cli_writes_pass_artifact_and_returns_zero(tmp_path: Path) -> None:
    evidence_path = tmp_path / "evidence.json"
    output = tmp_path / "qualification.json"
    evidence_path.write_text(
        json.dumps({"flow_cases": _all_evidence()}), encoding="utf-8"
    )

    result = runner.invoke(
        app,
        [
            "qualify-openfoam-convergence",
            str(EXAMPLE),
            str(evidence_path),
            str(output),
        ],
    )

    assert result.exit_code == 0, result.output
    summary = json.loads(result.output)
    assert summary["qualified"] is True
    assert output.is_file()


def test_cli_requires_matching_provenance_for_extractor_shaped_evidence(
    tmp_path: Path,
) -> None:
    evidence = _all_evidence()
    for item in evidence.values():
        item.update(
            {
                "kind": "openfoam_flow_case_convergence_evidence",
                "status": "complete",
                "complete": True,
            }
        )
    evidence_path = tmp_path / "evidence.json"
    output = tmp_path / "qualification.json"
    evidence_path.write_text(
        json.dumps({"flow_cases": evidence}), encoding="utf-8"
    )

    missing = runner.invoke(
        app,
        [
            "qualify-openfoam-convergence",
            str(EXAMPLE),
            str(evidence_path),
            str(output),
        ],
    )
    assert missing.exit_code != 0
    assert "requires an adjacent provenance" in missing.output
    assert "sidecar" in missing.output
    assert not output.exists()

    sidecar = evidence_path.with_name(f"{evidence_path.name}.provenance.json")
    provenance = {
        "schema_version": 1,
        "kind": "openfoam_convergence_evidence_provenance",
        "problem_id": "wrong_problem",
        "problem_spec_sha256": "a" * 64,
        "execution_ready": True,
        "bundle_metadata_sha256": "b" * 64,
        "evidence_sha256": hashlib.sha256(evidence_path.read_bytes()).hexdigest(),
        "flow_case_ids": ["straight", "yawed"],
    }
    sidecar.write_text(json.dumps(provenance), encoding="utf-8")

    mismatch = runner.invoke(
        app,
        [
            "qualify-openfoam-convergence",
            str(EXAMPLE),
            str(evidence_path),
            str(output),
        ],
    )
    assert mismatch.exit_code != 0
    assert "problem_id does not match" in mismatch.output
    assert not output.exists()

    spec = load_problem_spec(EXAMPLE)
    provenance["problem_id"] = spec.problem_id
    provenance["problem_spec_sha256"] = problem_spec_sha256(spec)
    sidecar.write_text(json.dumps(provenance), encoding="utf-8")

    qualified = runner.invoke(
        app,
        [
            "qualify-openfoam-convergence",
            str(EXAMPLE),
            str(evidence_path),
            str(output),
        ],
    )
    assert qualified.exit_code == 0, qualified.output
    assert json.loads(qualified.output)["qualified"] is True


def test_cli_writes_fail_artifact_and_returns_one(tmp_path: Path) -> None:
    evidence = _all_evidence()
    evidence["yawed"]["primal_residual_history"][0]["final_residual"] = 2.0e-6
    evidence_path = tmp_path / "evidence.json"
    output = tmp_path / "qualification.json"
    evidence_path.write_text(
        json.dumps({"flow_cases": evidence}), encoding="utf-8"
    )

    result = runner.invoke(
        app,
        [
            "qualify-openfoam-convergence",
            str(EXAMPLE),
            str(evidence_path),
            str(output),
        ],
    )

    assert result.exit_code == 1
    assert json.loads(output.read_text(encoding="utf-8"))["status"] == "fail"
