from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner
import yaml

from cfd_sdf.cli import app
from cfd_sdf.problem_spec import load_problem_spec, problem_spec_sha256


runner = CliRunner()
EXAMPLE = Path("examples/generic_problem_v2/project.yaml")


def test_validate_problem_spec_stdout_is_json() -> None:
    result = runner.invoke(app, ["validate-problem-spec", str(EXAMPLE)])

    assert result.exit_code == 0, result.output
    summary = json.loads(result.output)
    assert summary["kind"] == "problem_spec_validation"
    assert summary["execution_ready"] is True


def test_validate_problem_spec_writes_report_snapshot_and_matching_hash(tmp_path: Path) -> None:
    output_dir = tmp_path / "validation"

    result = runner.invoke(
        app,
        ["validate-problem-spec", str(EXAMPLE), "--output-dir", str(output_dir)],
    )

    assert result.exit_code == 0, result.output
    validation_path = output_dir / "problem_spec_validation.json"
    snapshot_path = output_dir / "problem_spec_snapshot.json"
    assert validation_path.exists()
    assert snapshot_path.exists()
    report = json.loads(validation_path.read_text(encoding="utf-8"))
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    spec = load_problem_spec(EXAMPLE)
    assert report["kind"] == "problem_spec_validation"
    assert report["execution_ready"] is True
    assert report["flow_case_ids"] == ["straight", "yawed"]
    assert report["problem_spec_sha256"] == problem_spec_sha256(spec)
    assert snapshot["problem_spec_sha256"] == report["problem_spec_sha256"]
    assert str(snapshot_path) in result.output
    assert str(validation_path) in result.output


def test_require_execution_ready_exits_after_writing_incomplete_report(tmp_path: Path) -> None:
    data = yaml.safe_load(EXAMPLE.read_text(encoding="utf-8"))
    data["geometry_regions"] = [
        region for region in data["geometry_regions"] if region["role"] != "design_domain"
    ]
    source = tmp_path / "incomplete.yaml"
    source.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    output_dir = tmp_path / "incomplete_report"

    result = runner.invoke(
        app,
        [
            "validate-problem-spec",
            str(source),
            "--output-dir",
            str(output_dir),
            "--require-execution-ready",
        ],
    )

    assert result.exit_code == 1
    report = json.loads((output_dir / "problem_spec_validation.json").read_text(encoding="utf-8"))
    assert report["execution_ready"] is False
    assert (output_dir / "problem_spec_snapshot.json").exists()


def test_cli_help_describes_generic_scope_and_front_wing_benchmark() -> None:
    result = runner.invoke(app, ["--help"])
    init_result = runner.invoke(app, ["init", "--help"])

    assert result.exit_code == 0
    assert init_result.exit_code == 0
    normalized = " ".join(result.output.lower().split())
    normalized_init = " ".join(init_result.output.lower().split())
    assert "generic topology and sdf tools" in normalized
    assert "front-wing sdf benchmark demo" in normalized_init


def test_generic_v2_example_is_ready_and_covers_all_response_kinds() -> None:
    spec = load_problem_spec(EXAMPLE)

    assert spec.migration.execution_ready is True
    assert [case.id for case in spec.flow_cases] == ["straight", "yawed"]
    assert {response.kind for response in spec.responses} == {
        "force",
        "moment",
        "pressure_loss",
        "flow_rate",
        "plugin",
    }
    assert len(spec.objectives[0].terms) == 2
