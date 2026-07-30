from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

import cfd_sdf.cli as cli_module
from cfd_sdf.cli import app
from cfd_sdf.localized_reference_topology import (
    LOCALIZED_REFERENCE_TOPOLOGY_FILENAME,
    LocalizedReferenceTopologyReport,
)


runner = CliRunner()


def test_cli_emits_one_sorted_json_object_for_success_and_uses_default_probes(
    tmp_path: Path, monkeypatch,
) -> None:
    calls: list[tuple[object, dict[str, object]]] = []

    def evaluator(problem, **kwargs):
        calls.append((problem, kwargs))
        return LocalizedReferenceTopologyReport(
            path=Path(kwargs["output_dir"]) / LOCALIZED_REFERENCE_TOPOLOGY_FILENAME,
            status="success",
            reasons=(),
        )

    monkeypatch.setattr(cli_module, "evaluate_localized_reference_topology", evaluator)
    project = tmp_path / "project.yaml"
    bundle = tmp_path / "bundle"
    output = tmp_path / "report"
    result = runner.invoke(
        app,
        ["evaluate-localized-reference-topology", str(project), str(bundle), str(output)],
    )

    assert result.exit_code == 0, result.output
    assert result.output.count("\n") == 1
    assert result.output == json.dumps(
        {
            "kind": "localized_reference_topology_evaluation",
            "reasons": [],
            "report_path": str(output / LOCALIZED_REFERENCE_TOPOLOGY_FILENAME),
            "status": "success",
        },
        sort_keys=True,
        separators=(",", ":"),
    ) + "\n"
    assert calls == [
        (
            project,
            {"reference_bundle_path": bundle, "output_dir": output},
        )
    ]


def test_cli_reports_rejected_outcome_then_exits_one(tmp_path: Path, monkeypatch) -> None:
    output = tmp_path / "report"

    monkeypatch.setattr(
        cli_module,
        "evaluate_localized_reference_topology",
        lambda *_args, **_kwargs: LocalizedReferenceTopologyReport(
            path=output / LOCALIZED_REFERENCE_TOPOLOGY_FILENAME,
            status="rejected",
            reasons=("minimum_solid_width", "erosion_no_effect"),
        ),
    )
    result = runner.invoke(
        app,
        ["evaluate-localized-reference-topology", "project.yaml", "bundle", str(output)],
    )

    assert result.exit_code == 1, result.output
    assert json.loads(result.output) == {
        "kind": "localized_reference_topology_evaluation",
        "reasons": ["minimum_solid_width", "erosion_no_effect"],
        "report_path": str(output / LOCALIZED_REFERENCE_TOPOLOGY_FILENAME),
        "status": "rejected",
    }


def test_cli_expected_error_emits_no_outcome_json_and_no_report(tmp_path: Path, monkeypatch) -> None:
    output = tmp_path / "report"

    def fail(*_args, **_kwargs):
        raise ValueError("verified reference bundle has non-finite rho_projected values")

    monkeypatch.setattr(cli_module, "evaluate_localized_reference_topology", fail)
    result = runner.invoke(
        app,
        ["evaluate-localized-reference-topology", "project.yaml", "bundle", str(output)],
    )

    assert result.exit_code != 0
    assert "non-finite" in result.output
    assert "localized_reference_topology_evaluation" not in result.output
    assert not (output / LOCALIZED_REFERENCE_TOPOLOGY_FILENAME).exists()


def test_cli_help_exposes_exactly_three_arguments_and_no_tuning_controls() -> None:
    result = runner.invoke(app, ["evaluate-localized-reference-topology", "--help"])

    assert result.exit_code == 0, result.output
    normalized = " ".join(result.output.lower().split())
    assert "project_yaml" in normalized
    assert "reference_bundle" in normalized
    assert "output_dir" in normalized
    assert normalized.count("--") == 1  # Typer's mandatory --help only.
    for forbidden in ("threshold", "disk", "memory", "probe", "radius", "beta", "eta"):
        assert forbidden not in normalized
