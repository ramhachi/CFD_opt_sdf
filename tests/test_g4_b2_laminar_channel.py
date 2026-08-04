from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from cfd_sdf.cli import app
from cfd_sdf.g4_b2_laminar_channel import (
    G4_B2_CHANNEL_COMPILATION_FILENAME,
    compile_g4_b2_channel_benchmark,
    evaluate_g4_b2_channel_qualification,
    run_g4_b2_channel_cases,
    write_g4_b2_channel_qualification,
)


SPEC = Path("examples/g4_b2_laminar/channel.yaml")
runner = CliRunner()


def _compiled(tmp_path: Path) -> tuple[Path, dict]:
    result = compile_g4_b2_channel_benchmark(spec_path=SPEC, output_dir=tmp_path / "channel")
    payload = json.loads(result.index_path.read_text(encoding="utf-8"))
    return result.root, payload


def _evidence(compilation: dict, *, fine_multiplier: float = 1.0) -> dict:
    analytic = compilation["analytic_solution"]
    gradient = analytic["negative_dp_dx_pa_per_m"]
    bulk = analytic["bulk_velocity_mps"]
    height = analytic["half_height_m"]
    # h^2 errors are deliberately nonzero so all three principal metrics have
    # the recorded, observable p=2 Richardson series.
    errors = {"coarse": 0.08, "medium": 0.02, "fine": 0.005 * fine_multiplier}
    cases = {}
    for case in compilation["cases"]:
        grid_id = case["grid_id"]
        ny = case["cells"][1]
        error = errors[grid_id]
        ys = [-height + (index + 0.5) * (2.0 * height / ny) for index in range(ny)]
        us = [1.5 * bulk * (1.0 - (y / height) ** 2) * (1.0 + error) for y in ys]
        x0, x1 = 0.03, 0.05
        p0 = 1.0
        p1 = p0 - gradient * (1.0 + error) * (x1 - x0)
        cases[grid_id] = {
            "case_sha256": case["case_sha256"],
            "runtime": {
                "status": "completed",
                "container_image": "opencfd/openfoam-default:2512@sha256:" + "a" * 64,
                "command": ["bash", "-lc", "./Allrun"],
                "final_time_s": 2000.0,
                "solver_log_sha256": "b" * 64,
                "fatal_log_clear": True,
                "primal_final_residual": 1.0e-9,
                "normalized_mass_imbalance": 1.0e-12,
                "stationarity": {"status": "passed", "window": 20},
            },
            "profile": {"sampling": "developed_plane_cell_centres", "y_m": ys, "u_x_mps": us},
            "bulk_velocity_mps": bulk * (1.0 + error),
            "pressure_gradient": {
                "sampling": "developed_area_weighted_cross_sections",
                "x0_m": x0, "x1_m": x1, "mean_p0_pa": p0, "mean_p1_pa": p1,
            },
        }
    return {"compilation_sha256": compilation["compilation_sha256"], "cases": cases}


def test_three_grid_compilation_binds_identical_physics_and_exact_channel_contract(tmp_path: Path) -> None:
    root, compilation = _compiled(tmp_path)

    assert compilation["status"] == "compiled_not_runtime_qualified"
    assert compilation["physics"]["openfoam_version"] == "v2512"
    assert compilation["analytic_solution"]["reynolds_number"] == pytest.approx(20.0)
    assert [case["cells"] for case in compilation["cases"]] == [[60, 20, 1], [120, 40, 1], [240, 80, 1]]
    assert all(case["one_z_cell"] for case in compilation["cases"])
    assert all(case["physics_sha256"] == compilation["cases"][0]["physics_sha256"] for case in compilation["cases"])
    assert all(case["boundary_conditions_sha256"] == compilation["cases"][0]["boundary_conditions_sha256"] for case in compilation["cases"])
    medium_u = (root / "medium" / "0" / "U").read_text(encoding="utf-8")
    assert "List<vector>\n        40" in medium_u
    assert "type noSlip" in medium_u
    assert "frontAndBack { type empty; }" in medium_u
    assert (root / "fine" / "Allrun").read_text(encoding="utf-8").startswith("#!/usr/bin/env bash\nset -eu\n")
    expected_divergence_scheme = "div((nuEff*dev2(T(grad(U))))) Gauss linear;"
    assert all(
        expected_divergence_scheme in (root / case["grid_id"] / "system" / "fvSchemes").read_text(encoding="utf-8")
        for case in compilation["cases"]
    )


def test_compilation_replay_is_deterministic_and_outputs_are_immutable(tmp_path: Path) -> None:
    first, _ = _compiled(tmp_path / "one")
    second, _ = _compiled(tmp_path / "two")

    assert (first / G4_B2_CHANNEL_COMPILATION_FILENAME).read_bytes() == (second / G4_B2_CHANNEL_COMPILATION_FILENAME).read_bytes()
    try:
        compile_g4_b2_channel_benchmark(spec_path=SPEC, output_dir=first)
    except FileExistsError:
        pass
    else:
        raise AssertionError("immutable compilation unexpectedly overwrote output")


def test_channel_qualification_passes_only_complete_bound_three_grid_evidence(tmp_path: Path) -> None:
    root, compilation = _compiled(tmp_path)
    result = evaluate_g4_b2_channel_qualification(compilation_dir=root, evidence=_evidence(compilation))

    assert result["status"] == "passed"
    assert result["qualified"] is True
    for metric in result["metrics"].values():
        assert metric["status"] == "pass"
        assert metric["observed_order"] == pytest.approx(2.0)
        assert metric["same_signed_three_grid_differences"] is True

    output = write_g4_b2_channel_qualification(result, tmp_path / "qualification.json")
    assert hashlib.sha256(output.read_bytes()).hexdigest()
    assert json.loads(output.read_text(encoding="utf-8"))["qualified"] is True


def test_missing_or_unbound_runtime_evidence_is_inconclusive_not_a_qualification(tmp_path: Path) -> None:
    root, compilation = _compiled(tmp_path)
    evidence = _evidence(compilation)
    del evidence["cases"]["fine"]["runtime"]["stationarity"]

    result = evaluate_g4_b2_channel_qualification(compilation_dir=root, evidence=evidence)

    assert result["status"] == "inconclusive"
    assert result["qualified"] is False
    assert "fine:runtime_evidence_has_unsupported_key_set" in result["reasons"]


def test_shared_runner_copies_cases_and_dry_run_is_contract_only_not_qualified(tmp_path: Path) -> None:
    root, compilation = _compiled(tmp_path)
    original = (root / "coarse" / "Allrun").read_bytes()
    artifact = run_g4_b2_channel_cases(
        compilation_dir=root, output_dir=tmp_path / "runtime", backend="docker", execute=False
    )
    payload = json.loads(artifact.read_text(encoding="utf-8"))

    assert payload["status"] == "contract_only_not_executed"
    assert payload["qualified"] is False
    assert all(case["status"] == "contract_only_not_executed" for case in payload["cases"])
    assert (root / "coarse" / "Allrun").read_bytes() == original
    assert (artifact.parent / "cases" / "fine" / "openfoam_run_summary.json").is_file()
    for case in payload["cases"]:
        run = case["run"]
        assert run["published_case_relpath"] == f"cases/{case['grid_id']}"
        for key in ("stdout_relpath", "stderr_relpath", "summary_relpath"):
            assert run[key].startswith(f"cases/{case['grid_id']}/")
            assert not Path(run[key]).is_absolute()
            assert ".tmp-" not in run[key]
        # The staging argv is retained as execution provenance, while the
        # replay argv and all public evidence locators name the published tree.
        assert ".tmp-" in json.dumps(run["command_executed"])
        assert run["command_executed_sha256"]
        assert ".tmp-" not in json.dumps(run["replay_command"])
        summary = json.loads((artifact.parent / run["summary_relpath"]).read_text(encoding="utf-8"))
        assert summary["published_case_relpath"] == run["published_case_relpath"]
        assert ".tmp-" not in summary["stdout_relpath"]


def test_nonmonotone_three_grid_metric_fails_with_formula_inputs_retained(tmp_path: Path) -> None:
    root, compilation = _compiled(tmp_path)
    result = evaluate_g4_b2_channel_qualification(
        compilation_dir=root, evidence=_evidence(compilation, fine_multiplier=10.0)
    )

    assert result["status"] == "failed"
    velocity = result["metrics"]["velocity_l2_relative"]
    assert velocity["status"] == "fail"
    assert velocity["phi_1_fine"] == pytest.approx(0.05)
    assert velocity["reasons"]


def test_cli_compiles_contract_without_claiming_runtime_qualification(tmp_path: Path) -> None:
    output = tmp_path / "cli"
    result = runner.invoke(app, ["compile-g4-b2-channel", str(output), "--spec", str(SPEC)])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["status"] == "compiled_not_runtime_qualified"
    assert (output / G4_B2_CHANNEL_COMPILATION_FILENAME).is_file()
