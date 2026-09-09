import json

from typer.testing import CliRunner

from cfd_sdf.cli import app


def test_cpu_benchmark_writes_bounded_evidence(tmp_path):
    output = tmp_path / "benchmark.json"
    result = CliRunner().invoke(
        app, ["research", "lbm-benchmark", "--output", str(output)]
    )
    assert result.exit_code == 0, result.output
    report = json.loads(output.read_text())
    assert report["status"] == "pass"
    assert report["capabilities"]["adjoint"] is False
    assert report["capabilities"]["target_aerodynamics"] is False
    assert report["timing"]["cpu_reference_seconds"] > 0


def test_benchmark_rejects_unsupported_backend_without_output(tmp_path):
    output = tmp_path / "bad.json"
    result = CliRunner().invoke(
        app, ["research", "lbm-benchmark", "--backend", "cuda", "--output", str(output)]
    )
    assert result.exit_code != 0
    assert not output.exists()


def test_benchmark_rejects_vacuous_zero_step_run():
    result = CliRunner().invoke(app, ["research", "lbm-benchmark", "--steps", "0"])
    assert result.exit_code != 0


def test_preflight_failure_writes_report_and_fails_command(tmp_path):
    from pathlib import Path

    project = Path(__file__).resolve().parents[1] / "examples/generic_problem_v2/project.yaml"
    output = tmp_path / "preflight.json"
    result = CliRunner().invoke(
        app, ["research", "preflight", str(project), "--output", str(output)]
    )
    assert result.exit_code == 1, result.output
    assert json.loads(output.read_text())["status"] == "fail"


def test_doctor_preserves_unknown_capabilities_in_json(monkeypatch, tmp_path):
    from cfd_sdf import runtime_diagnostics

    report = {"kind": "runtime_diagnostics", "gpu": {"available": None}}
    monkeypatch.setattr(runtime_diagnostics, "collect_runtime_diagnostics", lambda: report)
    output = tmp_path / "runtime.json"
    result = CliRunner().invoke(app, ["research", "doctor", "--output", str(output)])
    assert result.exit_code == 0, result.output
    assert json.loads(output.read_text()) == report


def test_benchmark_rejects_vanished_analytical_signal():
    result = CliRunner().invoke(
        app, ["research", "lbm-benchmark", "--nx", "4", "--ny", "4", "--steps", "20000"]
    )
    assert result.exit_code != 0
    assert "below FP64 resolution" in result.output
