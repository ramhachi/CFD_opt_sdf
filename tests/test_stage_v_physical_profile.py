from __future__ import annotations

import json
from pathlib import Path

from cfd_sdf.stage_v_physical_profile import (
    evaluate_boundary_metrics,
    evaluate_solver_residual_gate,
    read_boundary_field,
)


def _field(kind: str, patches: dict[str, str]) -> str:
    entries = []
    for name, body in patches.items():
        entries.append(f"    {name}\n    {{\n{body}\n    }}")
    return (
        "FoamFile\n{\n    object test;\n}\n"
        "boundaryField\n{\n"
        + "\n".join(entries)
        + "\n}\n"
    )


def _write_case(tmp_path: Path, *, ground: str = "(1 0 0)") -> Path:
    case = tmp_path / "case"
    time = case / "181"
    time.mkdir(parents=True)
    patches = {
        "inlet": "        type freestream;\n        value uniform -1;",
        "outlet": "        type freestream;\n        value uniform 1;",
        "sideMin": "        type freestream;\n        value uniform 0;",
        "sideMax": "        type freestream;\n        value uniform 0;",
        "top": "        type freestream;\n        value uniform 0;",
        "bottom": "        type wall;\n        value uniform 0;",
        "design_candidate": "        type wall;\n        value uniform 0;",
    }
    (time / "phi").write_text(_field("scalar", patches), encoding="utf-8")
    velocity_patches = {
        "inlet": f"        type freestreamVelocity;\n        value uniform (1 0 0);",
        "outlet": "        type freestreamVelocity;",
        "sideMin": "        type freestreamVelocity;",
        "sideMax": "        type freestreamVelocity;",
        "top": "        type freestreamVelocity;",
        "bottom": f"        type translatingWallVelocity;\n        value uniform {ground};",
        "design_candidate": "        type noSlip;",
    }
    (time / "U").write_text(_field("vector", velocity_patches), encoding="utf-8")
    pressure_patches = {
        "inlet": "        type freestreamPressure;\n        value uniform 0;",
        "outlet": "        type freestreamPressure;\n        value uniform 0;",
        "sideMin": "        type freestreamPressure;\n        value uniform 0;",
        "sideMax": "        type freestreamPressure;\n        value uniform 0;",
        "top": "        type freestreamPressure;\n        value uniform 0;",
        "bottom": "        type zeroGradient;",
        "design_candidate": "        type zeroGradient;",
    }
    (time / "p").write_text(_field("scalar", pressure_patches), encoding="utf-8")
    return case


def test_boundary_reader_accepts_multiline_patch_names_and_uniform_values(tmp_path: Path) -> None:
    case = _write_case(tmp_path)
    fields = read_boundary_field(case / "181" / "phi", kind="scalar")
    assert set(fields) == {"inlet", "outlet", "sideMin", "sideMax", "top", "bottom", "design_candidate"}
    assert fields["inlet"]["values"] == [-1.0]
    assert fields["outlet"]["values"] == [1.0]


def test_boundary_metrics_pass_on_closed_uniform_reference(tmp_path: Path) -> None:
    result = evaluate_boundary_metrics(_write_case(tmp_path))
    assert result["qualified"] is True
    assert result["gates"]["global_mass_conservation"]["status"] == "pass"
    assert result["gates"]["moving_ground_velocity_and_zero_normal_flux"]["status"] == "pass"
    assert result["gates"]["outer_patch_backflow_and_pressure_disturbance"]["status"] == "pass"


def test_boundary_metrics_fail_closed_for_wrong_ground_velocity(tmp_path: Path) -> None:
    result = evaluate_boundary_metrics(_write_case(tmp_path, ground="(0 0 0)"))
    assert result["qualified"] is False
    assert result["gates"]["moving_ground_velocity_and_zero_normal_flux"]["status"] == "fail"


def test_solver_residual_gate_requires_explicit_termination_and_thresholds() -> None:
    parsed = {
        "solver": {
            "final_residuals": {"p": 1.0e-6, "Ux": 1.0e-7, "Uy": 1.0e-7, "Uz": 1.0e-7},
            "residual_control_converged_at_iteration": 181,
            "end_marker": True,
        }
    }
    assert evaluate_solver_residual_gate(parsed)["qualified"] is True
    parsed["solver"]["final_residuals"]["p"] = 2.0e-5
    assert evaluate_solver_residual_gate(parsed)["qualified"] is False
