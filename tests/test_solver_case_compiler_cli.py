from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner
import yaml

from cfd_sdf.cli import app
from cfd_sdf.problem_spec import load_problem_spec
from cfd_sdf.solver_case_compiler import DEFAULT_FIXED_GRID_PATCH_IDS
from cfd_sdf.solver_case_manifest import build_openfoam_solver_case_manifest


runner = CliRunner()
EXAMPLE = Path("examples/g2_openfoam_compile/project.yaml")


def _write_required_initial_fields(template: Path, patch_names: tuple[str, ...]) -> None:
    fields = {
        "alpha": ("volScalarField", "[0 0 0 0 0 0 0]", "0", "zeroGradient"),
        "Ua": ("volVectorField", "[0 1 -1 0 0 0 0]", "(0 0 0)", "symmetryPlane"),
        "pa": ("volScalarField", "[0 2 -2 0 0 0 0]", "0", "symmetryPlane"),
    }
    for name, (field_class, dimensions, internal, patch_type) in fields.items():
        entries = "\n".join(
            f"    {patch}\n    {{\n        type {patch_type};\n    }}"
            for patch in patch_names
        )
        (template / "0.orig" / name).write_text(
            "\n".join(
                (
                    "FoamFile {",
                    f"    class {field_class};",
                    f"    object {name};",
                    "}",
                    f"dimensions {dimensions};",
                    f"internalField uniform {internal};",
                    "boundaryField",
                    "{",
                    entries,
                    "}",
                    "",
                )
            ),
            encoding="utf-8",
        )


def _template(
    tmp_path: Path, *, patch_names: tuple[str, ...] = DEFAULT_FIXED_GRID_PATCH_IDS
) -> Path:
    template = tmp_path / "template"
    for directory in ("0.orig", "constant", "system"):
        (template / directory).mkdir(parents=True)
    (template / "system/optimisationDict").write_text(
        """FoamFile
{
    object optimisationDict;
}
primalSolvers
{
    op1 { type incompressible; }
}
adjointManagers
{
    old { active false; }
}
optimisation
{
    designVariables { type topO; }
    updateMethod { type mma; }
}
""",
        encoding="utf-8",
    )
    (template / "system/fvOptions").write_text(
        """FoamFile
{
    object fvOptions;
}
topologySource
{
    type topOSource;
    names (U Uaas1);
}
""",
        encoding="utf-8",
    )
    (template / "system/controlDict").write_text(
        'application adjointOptimisationFoam;\nlibs ("libcfdSdfPorousObjectives.so");\n',
        encoding="utf-8",
    )
    boundary = "\n".join(
        f"    {name}\n    {{\n        type patch;\n        faces ();\n    }}"
        for name in patch_names
    )
    (template / "system/blockMeshDict").write_text(
        "\n".join(
            (
                "FoamFile { object blockMeshDict; }",
                "scale 1;",
                "vertices",
                "(",
                "    (-1 -0.8 -0.6)",
                "    (2 -0.8 -0.6)",
                "    (2 0.8 -0.6)",
                "    (-1 0.8 -0.6)",
                "    (-1 -0.8 0.6)",
                "    (2 -0.8 0.6)",
                "    (2 0.8 0.6)",
                "    (-1 0.8 0.6)",
                ");",
                "blocks",
                "(",
                "    hex (0 1 2 3 4 5 6 7) (32 16 16) simpleGrading (1 1 1)",
                ");",
                "edges ();",
                "boundary",
                "(",
                boundary,
                ");",
                "",
            )
        ),
        encoding="utf-8",
    )
    _write_required_initial_fields(template, patch_names)
    (template / "Allrun").write_text("#!/bin/sh\nset -e\n", encoding="utf-8")
    (template / "Allclean").write_text("#!/bin/sh\nrm -rf 0\n", encoding="utf-8")
    (template / "lib").mkdir()
    (template / "lib/libcfdSdfPorousObjectives.so").write_bytes(b"cli-test-library")
    (template / "system/sentinel").write_text("preserve", encoding="utf-8")
    return template


def _write_data(tmp_path: Path, data: dict, name: str) -> Path:
    path = tmp_path / name
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return path


def _synthetic_g2_data() -> dict:
    """Return a standalone compiler fixture without production STL coupling."""

    data = yaml.safe_load(EXAMPLE.read_text(encoding="utf-8"))
    data.pop("design_grid", None)
    return data


def test_compile_cli_success_uses_default_patches_and_writes_summary(tmp_path: Path) -> None:
    template = _template(tmp_path)
    output = tmp_path / "bundle"

    result = runner.invoke(
        app,
        [
            "compile-openfoam-problem-cases",
            str(EXAMPLE),
            str(template),
            str(output),
            "--adjoint-iterations",
            "9",
        ],
    )

    assert result.exit_code == 0, result.output
    summary = json.loads(result.output)
    assert summary["kind"] == "openfoam_problem_case_compilation"
    assert summary["compile_ready"] is True
    assert summary["status"] == "compiled"
    assert summary["execution_qualification"] == "not_run"
    assert set(summary["flow_case_dirs"]) == {"straight", "yawed"}
    assert Path(summary["manifest_json"]).is_file()
    assert Path(summary["bundle_metadata_json"]).is_file()
    straight = output / "flow_straight"
    velocity = (straight / "0.orig/U").read_text(encoding="utf-8")
    for patch_id in DEFAULT_FIXED_GRID_PATCH_IDS:
        assert f"    {patch_id}\n" in velocity
    assert "nIters 4000;" in (straight / "system/optimisationDict").read_text(
        encoding="utf-8"
    )


def test_compile_cli_repeated_custom_patch_option(tmp_path: Path) -> None:
    data = _synthetic_g2_data()
    for case in data["flow_cases"]:
        case["boundary_conditions"] = {
            "custom_inlet": "freestream",
            "custom_outlet": "pressure_outlet",
        }
        case["motion_profiles"] = {}
    source = _write_data(tmp_path, data, "custom_patches.yaml")
    template = _template(tmp_path, patch_names=("custom_inlet", "custom_outlet"))
    output = tmp_path / "custom_bundle"

    result = runner.invoke(
        app,
        [
            "compile-openfoam-problem-cases",
            str(source),
            str(template),
            str(output),
            "--patch-id",
            "custom_inlet",
            "--patch-id",
            "custom_outlet",
        ],
    )

    assert result.exit_code == 0, result.output
    text = (output / "flow_straight/0.orig/U").read_text(encoding="utf-8")
    assert "custom_inlet" in text
    assert "custom_outlet" in text
    assert "spanMin" not in text


def test_unsupported_allow_returns_zero_without_cases(tmp_path: Path) -> None:
    data = _synthetic_g2_data()
    data["responses"].append(
        {
            "id": "unsupported_moment",
            "kind": "moment",
            "flow_case_id": "yawed",
            "direction": [0.0, 1.0, 0.0],
        }
    )
    source = _write_data(tmp_path, data, "unsupported_allow.yaml")
    output = tmp_path / "unsupported_allow"

    result = runner.invoke(
        app,
        [
            "compile-openfoam-problem-cases",
            str(source),
            str(_template(tmp_path)),
            str(output),
            "--allow-unsupported",
        ],
    )

    assert result.exit_code == 0, result.output
    summary = json.loads(result.output)
    assert summary["compile_ready"] is False
    assert summary["status"] == "unsupported"
    assert summary["flow_case_dirs"] == {}
    assert any("unsupported_response_kind" in reason for reason in summary["unsupported"])
    assert not list(output.glob("flow_*"))


def test_unsupported_require_returns_one_after_manifest_and_marker(tmp_path: Path) -> None:
    data = _synthetic_g2_data()
    data["grid"]["kind"] = "octree_amr"
    source = _write_data(tmp_path, data, "unsupported_require.yaml")
    output = tmp_path / "unsupported_require"

    result = runner.invoke(
        app,
        [
            "compile-openfoam-problem-cases",
            str(source),
            str(_template(tmp_path)),
            str(output),
        ],
    )

    assert result.exit_code == 1
    summary = json.loads(result.output)
    assert summary["compile_ready"] is False
    assert (output / "openfoam_solver_case_manifest.json").is_file()
    assert (output / "openfoam_case_bundle.json").is_file()


def test_compile_cli_requires_overwrite_for_owned_bundle(tmp_path: Path) -> None:
    template = _template(tmp_path)
    output = tmp_path / "overwrite_bundle"
    args = [
        "compile-openfoam-problem-cases",
        str(EXAMPLE),
        str(template),
        str(output),
    ]
    first = runner.invoke(app, args)
    assert first.exit_code == 0, first.output

    refused = runner.invoke(app, args)
    assert refused.exit_code != 0
    assert "overwrite=True" in refused.output

    replaced = runner.invoke(app, [*args, "--overwrite"])
    assert replaced.exit_code == 0, replaced.output
    assert json.loads(replaced.output)["status"] == "compiled"


def test_g2_example_is_execution_and_compile_ready() -> None:
    spec = load_problem_spec(EXAMPLE)
    manifest = build_openfoam_solver_case_manifest(
        spec, available_patch_ids=DEFAULT_FIXED_GRID_PATCH_IDS
    )

    assert spec.migration.execution_ready is True
    assert manifest.compile_ready is True
    assert manifest.unsupported == ()
    assert [plan.case_directory_name for plan in manifest.flow_cases] == [
        "flow_straight",
        "flow_yawed",
    ]


def test_compile_cli_help_states_compile_only_not_qualified() -> None:
    result = runner.invoke(app, ["compile-openfoam-problem-cases", "--help"])

    assert result.exit_code == 0
    normalized = " ".join(result.output.lower().split())
    assert "compile openfoam cases only" in normalized
    assert "does not execute or qualify the solver" in normalized
