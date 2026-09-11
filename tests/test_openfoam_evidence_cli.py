from __future__ import annotations

import hashlib
import json
from pathlib import Path

from typer.testing import CliRunner

from cfd_sdf.cli import app


runner = CliRunner()


def test_extract_cli_writes_deterministic_incomplete_bundle_and_returns_zero(
    tmp_path: Path,
) -> None:
    bundle = _write_bundle(tmp_path / "bundle")
    first = tmp_path / "first_evidence.json"
    second = tmp_path / "second_evidence.json"

    first_result = runner.invoke(
        app,
        ["extract-openfoam-convergence-evidence", str(bundle), str(first)],
    )
    second_result = runner.invoke(
        app,
        ["extract-openfoam-convergence-evidence", str(bundle), str(second)],
    )

    assert first_result.exit_code == 0, first_result.output
    assert second_result.exit_code == 0, second_result.output
    first_provenance = first.with_name(f"{first.name}.provenance.json")
    second_provenance = second.with_name(f"{second.name}.provenance.json")
    summary = json.loads(first_result.output)
    assert summary == {
        "kind": "openfoam_convergence_evidence_extraction",
        "status": "incomplete",
        "complete": False,
        "problem_id": "g2_cli_test",
        "flow_cases": {"straight": "incomplete", "yawed": "incomplete"},
        "artifact_json": str(first.resolve()),
        "provenance_json": str(first_provenance.resolve()),
    }
    evidence = json.loads(first.read_text(encoding="utf-8"))
    assert list(evidence) == ["flow_cases"]
    assert list(evidence["flow_cases"]) == ["straight", "yawed"]
    assert all(
        item["status"] == "incomplete"
        and "missing_solver_log" in item["incomplete_reasons"]
        for item in evidence["flow_cases"].values()
    )
    provenance = json.loads(first_provenance.read_text(encoding="utf-8"))
    assert provenance == {
        "schema_version": 1,
        "kind": "openfoam_convergence_evidence_provenance",
        "problem_id": "g2_cli_test",
        "problem_spec_sha256": "a" * 64,
        "execution_ready": True,
        "bundle_metadata_sha256": hashlib.sha256(
            (bundle / "openfoam_case_bundle.json").read_bytes()
        ).hexdigest(),
        "evidence_sha256": hashlib.sha256(first.read_bytes()).hexdigest(),
        "flow_case_ids": ["straight", "yawed"],
    }
    assert first.read_bytes() == second.read_bytes()
    assert first_provenance.read_bytes() == second_provenance.read_bytes()


def test_extract_cli_rejects_case_directory_traversal_without_writing_output(
    tmp_path: Path,
) -> None:
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    (bundle / "openfoam_case_bundle.json").write_text(
        json.dumps(
            {
                "kind": "openfoam_case_bundle",
                "problem_id": "g2_cli_test",
                "problem_spec_sha256": "a" * 64,
                "execution_ready": True,
                "compile_ready": True,
                "status": "compiled",
                "flow_cases": {
                    "straight": {"case_dir": "../outside", "status": "compiled"}
                },
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "evidence.json"

    result = runner.invoke(
        app,
        ["extract-openfoam-convergence-evidence", str(bundle), str(output)],
    )

    assert result.exit_code != 0
    assert "Unsafe case directory name" in result.output
    assert not output.exists()


def test_extract_cli_never_replaces_bundle_metadata(tmp_path: Path) -> None:
    bundle = _write_bundle(tmp_path / "bundle")
    metadata = bundle / "openfoam_case_bundle.json"
    before = metadata.read_bytes()

    result = runner.invoke(
        app,
        ["extract-openfoam-convergence-evidence", str(bundle), str(metadata)],
    )

    assert result.exit_code != 0
    assert "must not replace openfoam_case_bundle.json" in result.output
    assert metadata.read_bytes() == before


def test_extract_cli_never_replaces_compiled_case_artifacts(tmp_path: Path) -> None:
    bundle = _write_bundle(tmp_path / "bundle")
    case = bundle / "flow_straight"
    for name in (
        "generated_openfoam_responses.json",
        "generated_openfoam_physics.json",
        "openfoam_case_compilation.json",
    ):
        artifact = case / name
        before = artifact.read_bytes()

        result = runner.invoke(
            app,
            ["extract-openfoam-convergence-evidence", str(bundle), str(artifact)],
        )

        assert result.exit_code != 0
        assert "must not be placed inside compiled flow-case" in result.output
        assert "directory 'straight'" in result.output
        assert artifact.read_bytes() == before
        assert not artifact.with_name(f"{artifact.name}.provenance.json").exists()


def test_extract_cli_never_replaces_compiled_manifest(tmp_path: Path) -> None:
    bundle = _write_bundle(tmp_path / "bundle")
    manifest = bundle / "openfoam_solver_case_manifest.json"
    before = manifest.read_bytes()

    result = runner.invoke(
        app,
        ["extract-openfoam-convergence-evidence", str(bundle), str(manifest)],
    )

    assert result.exit_code != 0
    assert "must not replace compiled OpenFOAM manifest" in result.output
    assert manifest.read_bytes() == before


def _write_bundle(root: Path) -> Path:
    root.mkdir(parents=True)
    flow_cases = {
        "yawed": {"case_dir": "flow_yawed", "status": "compiled"},
        "straight": {"case_dir": "flow_straight", "status": "compiled"},
    }
    for flow_case_id, metadata in flow_cases.items():
        _write_flow_case(root / metadata["case_dir"], response_id=f"force_{flow_case_id}")
    (root / "openfoam_case_bundle.json").write_text(
        json.dumps(
            {
                "kind": "openfoam_case_bundle",
                "problem_id": "g2_cli_test",
                "problem_spec_sha256": "a" * 64,
                "execution_ready": True,
                "compile_ready": True,
                "status": "compiled",
                "manifest_path": "openfoam_solver_case_manifest.json",
                "flow_cases": flow_cases,
            }
        ),
        encoding="utf-8",
    )
    (root / "openfoam_solver_case_manifest.json").write_text(
        json.dumps({"kind": "openfoam_solver_case_manifest"}), encoding="utf-8"
    )
    return root


def _write_flow_case(case: Path, *, response_id: str) -> None:
    (case / "system").mkdir(parents=True)
    (case / "system" / "controlDict").write_text(
        "application adjointOptimisationFoam;\n", encoding="utf-8"
    )
    (case / "generated_openfoam_responses.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "kind": "generated_openfoam_responses",
                "response_mappings": [
                    {
                        "response_id": response_id,
                        "objective_name": response_id,
                        "adjoint_solver_id": f"resp_{response_id}",
                        "adjoint_velocity_field": f"Uaresp_{response_id}",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (case / "generated_openfoam_physics.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "kind": "generated_openfoam_physics",
                "generated": {"turbulence": {"model": "k_omega_sst"}},
            }
        ),
        encoding="utf-8",
    )
    (case / "openfoam_case_compilation.json").write_text(
        json.dumps({"kind": "openfoam_case_compilation"}), encoding="utf-8"
    )
