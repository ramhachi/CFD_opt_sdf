from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
import yaml

import cfd_sdf.solver_case_compiler as compiler_module
from cfd_sdf.openfoam_blockmesh_grid import read_openfoam_blockmesh_uniform_cartesian_grid
from cfd_sdf.problem_spec import load_problem_spec
from cfd_sdf.solver_case_compiler import compile_openfoam_solver_case_bundle


EXAMPLE = Path("examples/generic_problem_v2/project.yaml")
G2_EXAMPLE = Path("examples/g2_openfoam_compile/project.yaml")
PATCHES = ("inlet", "outlet", "ground")


def _valid_data(*, turbulence: str = "laminar") -> dict:
    data = yaml.safe_load(EXAMPLE.read_text(encoding="utf-8"))
    for case in data["flow_cases"]:
        if turbulence == "laminar":
            case["turbulence"] = {"model": "laminar"}
        else:
            case["turbulence"] = {
                "model": "k_omega_sst",
                "turbulence_intensity": 0.05,
                "turbulence_length_scale_m": 0.2,
            }
    data["flow_cases"][0]["motion_profiles"]["moving_ground"]["boundary_ids"] = ["ground"]
    data["flow_cases"][1]["boundary_conditions"]["ground"] = "stationary_wall"
    data["responses"] = [
        {
            "id": "straight_force",
            "kind": "force",
            "flow_case_id": "straight",
            "direction": [1.0, 0.0, 0.0],
        },
        {
            "id": "yaw_force",
            "kind": "force",
            "flow_case_id": "yawed",
            "direction": [0.0, 1.0, 0.0],
        },
    ]
    data["objectives"] = [
        {
            "id": "multipoint_objective",
            "sense": "minimize",
            "terms": [
                {"coefficient": 0.7, "flow_case_id": "straight", "response_id": "straight_force"},
                {"coefficient": 0.3, "flow_case_id": "yawed", "response_id": "yaw_force"},
            ],
        }
    ]
    data["constraints"] = []
    return data


def _spec(tmp_path: Path, data: dict, name: str = "problem.yaml"):
    path = tmp_path / name
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return load_problem_spec(path)


def _write_required_initial_fields(
    template: Path,
    patch_names: tuple[str, ...],
    *,
    newline: str = "\n",
) -> None:
    field_definitions = {
        "alpha": ("volScalarField", "[0 0 0 0 0 0 0]", "0", "zeroGradient"),
        "Ua": ("volVectorField", "[0 1 -1 0 0 0 0]", "(0 0 0)", "symmetryPlane"),
        "pa": ("volScalarField", "[0 2 -2 0 0 0 0]", "0", "symmetryPlane"),
    }
    for field_name, (field_class, dimensions, internal, patch_type) in field_definitions.items():
        entries = []
        for patch_name in patch_names:
            entries.extend(
                (
                    f"    {patch_name} // retain field comment {{ }}",
                    "    {",
                    f"        type /* preserve comment */ {patch_type};",
                    "    }",
                )
            )
        text = newline.join(
            (
                "FoamFile",
                "{",
                f"    class {field_class};",
                f"    object {field_name};",
                "}",
                f"dimensions {dimensions};",
                f"internalField uniform {internal};",
                "boundaryField",
                "{",
                *entries,
                "}",
                "",
            )
        )
        (template / "0.orig" / field_name).write_bytes(text.encode("utf-8"))


def _write_scalar_initial_field(
    template: Path,
    field_name: str,
    patch_types: dict[str, str],
) -> None:
    entries = []
    for patch_name, patch_type in patch_types.items():
        entries.extend(
            (
                f"    {patch_name}",
                "    {",
                f"        type {patch_type};",
                "    }",
            )
        )
    text = "\n".join(
        (
            "FoamFile { class volScalarField; object " + field_name + "; }",
            "dimensions [0 0 0 0 0 0 0];",
            "internalField uniform 0;",
            "boundaryField",
            "{",
            *entries,
            "}",
            "",
        )
    )
    (template / "0.orig" / field_name).write_text(text, encoding="utf-8")


def _template(tmp_path: Path, *, malformed_fv: bool = False) -> Path:
    template = tmp_path / "template"
    for directory in ("0.orig", "constant", "system", "0", "postProcessing"):
        (template / directory).mkdir(parents=True)
    (template / "0.orig/template_sentinel").write_text("zero", encoding="utf-8")
    (template / "constant/template_sentinel").write_text("constant", encoding="utf-8")
    (template / "system/template_sentinel").write_text("system", encoding="utf-8")
    (template / "0/runtime.txt").write_text("must not copy", encoding="utf-8")
    (template / "postProcessing/result.txt").write_text("must not copy", encoding="utf-8")
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
    fv_text = (
        "FoamFile\n{\n object fvOptions;\n}\n"
        "topologySource\n{\n type topOSource;\n selectionMode all;\n}\n"
        if malformed_fv
        else "FoamFile\n{\n object fvOptions;\n}\n"
        "topologySource\n{\n type topOSource;\n names (U Uaas1);\n}\n"
    )
    (template / "system/fvOptions").write_text(fv_text, encoding="utf-8")
    (template / "system/controlDict").write_text(
        'application adjointOptimisationFoam;\nlibs ("libcfdSdfPorousObjectives.so");\n',
        encoding="utf-8",
    )
    patch_names = ("inlet", "outlet", "ground")
    (template / "system/blockMeshDict").write_bytes(_block_mesh_bytes(patch_names))
    _write_required_initial_fields(template, patch_names)
    (template / "Allrun").write_text("#!/bin/sh\nset -e\n", encoding="utf-8")
    (template / "Allclean").write_text("#!/bin/sh\nrm -rf 0\n", encoding="utf-8")
    (template / "lib").mkdir()
    (template / "lib/libcfdSdfPorousObjectives.so").write_bytes(b"test-library")
    return template


def _set_topo_regularisation(template: Path, *, regularise: str) -> None:
    path = template / "system/optimisationDict"
    source = path.read_text(encoding="utf-8")
    updated = source.replace(
        "designVariables { type topO; }",
        "\n".join(
            (
                "designVariables",
                "{",
                "    type topO;",
                "    regularisation",
                "    {",
                f"        regularise {regularise};",
                "    }",
                "}",
            )
        ),
    )
    assert updated != source
    path.write_text(updated, encoding="utf-8")


def _compile(tmp_path: Path, *, turbulence: str = "laminar", overwrite: bool = False):
    return compile_openfoam_solver_case_bundle(
        _spec(tmp_path, _valid_data(turbulence=turbulence)),
        template_case_dir=_template(tmp_path),
        output_dir=tmp_path / "bundle",
        available_patch_ids=PATCHES,
        adjoint_iterations=7,
        overwrite=overwrite,
    )


def _g2_spec(tmp_path: Path):
    return _spec(
        tmp_path,
        yaml.safe_load(G2_EXAMPLE.read_text(encoding="utf-8")),
        "g2_problem.yaml",
    )


def _block_mesh_bytes(patch_names: tuple[str, ...], *, newline: str = "\n") -> bytes:
    entries = []
    for name in patch_names:
        entries.append(
            newline.join(
                (
                    f"    {name} // comment with braces {{ }}",
                    "    {",
                    "        type /* preserve this comment */ symmetryPlane;",
                    "        faces",
                    "        (",
                    "            (0 1 2 3) // untouched geometry ( ) { }",
                    "        );",
                    "    }",
                )
            )
        )
    return newline.join(
        (
            "FoamFile { object blockMeshDict; }",
            "// fake boundary ( fake { type wall; } )",
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
            *entries,
            ");",
            "mergePatchPairs ();",
            "",
        )
    ).encode("utf-8")


def test_laminar_two_flow_bundle_compiles_exact_owned_files(tmp_path: Path) -> None:
    artifacts = _compile(tmp_path)

    assert artifacts.manifest.compile_ready is True
    assert set(artifacts.case_dirs) == {"straight", "yawed"}
    straight = artifacts.case_dirs["straight"]
    yawed = artifacts.case_dirs["yawed"]
    assert straight.name == "flow_straight"
    assert yawed.name == "flow_yawed"
    assert "internalField   uniform (30 0 0);" in (straight / "0.orig/U").read_text(encoding="utf-8")
    assert "internalField   uniform (29.5 5.2 0);" in (yawed / "0.orig/U").read_text(encoding="utf-8")
    assert "1.4693877551e-05" in (straight / "constant/transportProperties").read_text(
        encoding="utf-8"
    )
    assert "direction (1 0 0);" in (straight / "system/optimisationDict").read_text(
        encoding="utf-8"
    )
    assert "direction (0 1 0);" in (yawed / "system/optimisationDict").read_text(
        encoding="utf-8"
    )
    assert "nIters 7;" in (straight / "system/optimisationDict").read_text(encoding="utf-8")
    straight_optimisation = (straight / "system/optimisationDict").read_text(encoding="utf-8")
    yawed_optimisation = (yawed / "system/optimisationDict").read_text(encoding="utf-8")
    assert "useSolverNameForFields true;" in straight_optimisation
    assert "useSolverNameForFields true;" in yawed_optimisation
    assert "names (U);" in (straight / "system/fvOptions").read_text(
        encoding="utf-8"
    )
    assert "names (U);" in (yawed / "system/fvOptions").read_text(
        encoding="utf-8"
    )
    assert straight_optimisation.count("addFvOptions true;") == 1
    assert yawed_optimisation.count("addFvOptions true;") == 1
    assert (straight / "system/template_sentinel").read_text(encoding="utf-8") == "system"
    assert not (straight / "0").exists()
    assert not (straight / "postProcessing").exists()
    assert (straight / "Allrun").read_bytes() == (tmp_path / "template/Allrun").read_bytes()
    assert (straight / "Allclean").read_bytes() == (tmp_path / "template/Allclean").read_bytes()
    assert (straight / "lib/libcfdSdfPorousObjectives.so").read_bytes() == b"test-library"
    assert '"./lib/libcfdSdfPorousObjectives.so"' in (
        straight / "system/controlDict"
    ).read_text(encoding="utf-8")
    compilation = json.loads((straight / "openfoam_case_compilation.json").read_text(encoding="utf-8"))
    assert compilation["status"] == "compiled"
    assert compilation["execution_qualification"] == "not_run"
    assert compilation["execution_contract"]["qualification"] == "compiled_not_runtime_qualified"
    library = compilation["execution_contract"]["libraries"][0]
    assert library["required"] == "libcfdSdfPorousObjectives.so"
    assert library["staged_path"] == "lib/libcfdSdfPorousObjectives.so"
    assert library["qualification"] == "staged_not_runtime_qualified"
    scripts = {
        script["required"]: script
        for script in compilation["execution_contract"]["scripts"]
    }
    assert scripts["Allrun"]["qualification"] == "staged_fail_fast_not_runtime_qualified"
    assert scripts["Allrun"]["fail_fast"] is True
    assert scripts["Allclean"]["qualification"] == "staged_not_runtime_qualified"
    assert compilation["physics"]["metadata_sha256"] == hashlib.sha256(
        (straight / "generated_openfoam_physics.json").read_bytes()
    ).hexdigest()
    response_metadata = json.loads(
        (straight / "generated_openfoam_responses.json").read_text(encoding="utf-8")
    )
    assert response_metadata["native_source_strategy"]["static_toposource_fields"] == ["U"]
    assert response_metadata["response_mappings"][0]["native_adjoint_source"]["enabled"] is True
    bundle = json.loads(artifacts.bundle_metadata_json.read_text(encoding="utf-8"))
    assert bundle["status"] == "compiled"
    assert bundle["manifest_sha256"] == hashlib.sha256(artifacts.manifest_json.read_bytes()).hexdigest()


def test_topo_regularisation_stages_v2512_b_tilda_solver(tmp_path: Path) -> None:
    template = _template(tmp_path)
    _set_topo_regularisation(template, regularise="true")

    artifacts = compile_openfoam_solver_case_bundle(
        _spec(tmp_path, _valid_data()),
        template_case_dir=template,
        output_dir=tmp_path / "topo_regularised_bundle",
        available_patch_ids=PATCHES,
    )

    straight = artifacts.case_dirs["straight"]
    solution = (straight / "system/fvSolution").read_text(encoding="utf-8")
    assert "    bTilda\n    {" in solution
    assert "        solver          PCG;" in solution
    assert "        preconditioner  DIC;" in solution
    compilation = json.loads(
        (straight / "openfoam_case_compilation.json").read_text(encoding="utf-8")
    )
    assert compilation["physics"]["fv_solution_initialization_solver_fields"] == [
        "bTilda"
    ]
    bundle = json.loads(artifacts.bundle_metadata_json.read_text(encoding="utf-8"))
    assert bundle["fv_solution_initialization_contract"] == {
        "path": "system/optimisationDict",
        "openfoam_version": "v2512",
        "design_variables_type": "topO",
        "regularisation": {"enabled": True, "source": "template"},
        "required_solver_fields": ["bTilda"],
        "validation": "resolved_for_staging",
    }


def test_topo_without_regularisation_does_not_stage_b_tilda_solver(tmp_path: Path) -> None:
    template = _template(tmp_path)
    _set_topo_regularisation(template, regularise="false")

    artifacts = compile_openfoam_solver_case_bundle(
        _spec(tmp_path, _valid_data()),
        template_case_dir=template,
        output_dir=tmp_path / "topo_unregularised_bundle",
        available_patch_ids=PATCHES,
    )

    straight = artifacts.case_dirs["straight"]
    solution = (straight / "system/fvSolution").read_text(encoding="utf-8")
    assert "    bTilda\n    {" not in solution
    compilation = json.loads(
        (straight / "openfoam_case_compilation.json").read_text(encoding="utf-8")
    )
    assert compilation["physics"]["fv_solution_initialization_solver_fields"] == []


def test_sst_bundle_contains_k_omega_nut_fields(tmp_path: Path) -> None:
    artifacts = _compile(tmp_path, turbulence="sst")

    for case_dir in artifacts.case_dirs.values():
        assert (case_dir / "0.orig/k").is_file()
        assert (case_dir / "0.orig/omega").is_file()
        assert (case_dir / "0.orig/nut").is_file()
        assert (case_dir / "0.orig/ka").is_file()
        assert (case_dir / "0.orig/wa").is_file()
        assert (case_dir / "constant/adjointRASProperties").is_file()
        assert (case_dir / "system/fvSchemes").is_file()
        assert (case_dir / "system/fvSolution").is_file()
        assert "kOmegaSST" in (case_dir / "constant/turbulenceProperties").read_text(
            encoding="utf-8"
        )
        physics = json.loads((case_dir / "generated_openfoam_physics.json").read_text(encoding="utf-8"))
        assert physics["generated"]["wall_distance"]["qualification"] == "not_qualified"


def test_g2_rendered_block_mesh_binds_domain_and_preserves_crlf_boundary_content(
    tmp_path: Path,
) -> None:
    template = _template(tmp_path)
    patch_names = ("inlet", "outlet", "spanMin", "spanMax", "lower", "upper")
    source = _block_mesh_bytes(patch_names, newline="\r\n")
    (template / "system/blockMeshDict").write_bytes(source)
    _write_required_initial_fields(template, patch_names, newline="\r\n")
    template_grid = read_openfoam_blockmesh_uniform_cartesian_grid(
        template / "system/blockMeshDict"
    )
    assert template_grid.lower == pytest.approx((-1.0, -0.8, -0.6))

    artifacts = compile_openfoam_solver_case_bundle(
        _g2_spec(tmp_path),
        template_case_dir=template,
        output_dir=tmp_path / "g2_bundle",
        available_patch_ids=patch_names,
    )

    staged = (artifacts.case_dirs["straight"] / "system/blockMeshDict").read_bytes()
    assert b"\r\n" in staged
    assert staged.count(b"\n") == staged.count(b"\r\n")
    assert b"// fake boundary ( fake { type wall; } )" in staged
    assert b"faces\r\n        (\r\n            (0 1 2 3)" in staged
    text = staged.decode("utf-8")
    assert "lower // comment with braces { }\r\n    {\r\n        type /* preserve this comment */ wall;" in text
    assert "upper // comment with braces { }\r\n    {\r\n        type /* preserve this comment */ symmetryPlane;" in text
    alpha = (artifacts.case_dirs["straight"] / "0.orig/alpha").read_bytes()
    ua = (artifacts.case_dirs["straight"] / "0.orig/Ua").read_bytes()
    pa = (artifacts.case_dirs["straight"] / "0.orig/pa").read_bytes()
    assert alpha.count(b"\n") == alpha.count(b"\r\n")
    assert b"lower // retain field comment { }\r\n    {\r\n        type /* preserve comment */ zeroGradient;" in alpha
    assert b"type /* preserve comment */ adjointWallVelocity;" in ua
    assert b"value           uniform (0 0 0);" in ua
    assert b"type /* preserve comment */ zeroGradient;" in pa
    compilation = json.loads(
        (artifacts.case_dirs["straight"] / "openfoam_case_compilation.json").read_text(
            encoding="utf-8"
        )
    )
    mesh = compilation["mesh_boundary_contract"]
    assert mesh["requested_boundary_conditions"]["lower"] == "moving_wall"
    assert mesh["generated_patch_types"]["lower"] == "wall"
    assert mesh["staged_patch_types_after"]["lower"] == "wall"
    assert mesh["validation"] == "pass"
    domain = compilation["mesh_domain_contract"]
    assert domain["binding"] == "bound"
    assert domain["source_cell_shape"] == [32, 16, 16]
    assert domain["rendered_lower_m"] == pytest.approx([-1.0, -1.2, -0.6])
    assert domain["rendered_upper_m"] == pytest.approx([2.0, 1.2, 0.7])
    rendered_grid = read_openfoam_blockmesh_uniform_cartesian_grid(
        artifacts.case_dirs["straight"] / "system/blockMeshDict"
    )
    assert rendered_grid.lower == pytest.approx((-1.0, -1.2, -0.6))
    assert tuple(
        rendered_grid.lower[axis]
        + rendered_grid.spacing[axis] * rendered_grid.cell_shape[axis]
        for axis in range(3)
    ) == pytest.approx((2.0, 1.2, 0.7))
    assert rendered_grid.cell_shape == (32, 16, 16)
    fields = compilation["field_boundary_contract"]
    assert fields["validation"] == "pass"
    assert fields["all_initial_fields"]["alpha"]["patch_types"]["lower"] == "zeroGradient"
    assert fields["all_initial_fields"]["Ua"]["patch_types"]["lower"] == "adjointWallVelocity"


def test_g2_rendered_block_mesh_binds_physical_domain_with_non_unit_scale(
    tmp_path: Path,
) -> None:
    template = _template(tmp_path)
    patch_names = ("inlet", "outlet", "spanMin", "spanMax", "lower", "upper")
    source = _block_mesh_bytes(patch_names).replace(b"scale 1;", b"scale 0.5;")
    (template / "system/blockMeshDict").write_bytes(source)
    _write_required_initial_fields(template, patch_names)

    artifacts = compile_openfoam_solver_case_bundle(
        _g2_spec(tmp_path),
        template_case_dir=template,
        output_dir=tmp_path / "g2_scaled_bundle",
        available_patch_ids=patch_names,
    )

    rendered_path = artifacts.case_dirs["straight"] / "system/blockMeshDict"
    rendered = read_openfoam_blockmesh_uniform_cartesian_grid(rendered_path)
    assert rendered.scale == pytest.approx(0.5)
    assert rendered.lower == pytest.approx((-1.0, -1.2, -0.6))
    assert tuple(
        rendered.lower[axis] + rendered.spacing[axis] * rendered.cell_shape[axis]
        for axis in range(3)
    ) == pytest.approx((2.0, 1.2, 0.7))
    text = rendered_path.read_text(encoding="utf-8")
    assert "    (-2 -2.4 -1.2)" in text
    assert "    (4 2.4 1.4)" in text


def test_compact_retained_field_entry_inserts_value_inside_its_patch(tmp_path: Path) -> None:
    template = _template(tmp_path)
    (template / "0.orig/Ua").write_text(
        "\n".join(
            (
                "FoamFile { class volVectorField; object Ua; }",
                "dimensions [0 1 -1 0 0 0 0];",
                "internalField uniform (0 0 0);",
                "boundaryField",
                "{",
                "    inlet { type symmetryPlane; }",
                "    outlet { type symmetryPlane; }",
                "    ground { type symmetryPlane; }",
                "}",
                "",
            )
        ),
        encoding="utf-8",
    )

    artifacts = compile_openfoam_solver_case_bundle(
        _spec(tmp_path, _valid_data()),
        template_case_dir=template,
        output_dir=tmp_path / "compact_field_bundle",
        available_patch_ids=PATCHES,
    )

    text = (artifacts.case_dirs["straight"] / "0.orig/Ua").read_text(encoding="utf-8")
    assert "ground { type adjointWallVelocity;  value           uniform (0 0 0); }" in text
    assert "value           uniform (0 0 0);ground" not in text


def test_existing_value_comments_are_preserved_while_components_patch(tmp_path: Path) -> None:
    template = _template(tmp_path)
    (template / "0.orig/Ua").write_text(
        "\n".join(
            (
                "FoamFile { class volVectorField; object Ua; }",
                "dimensions [0 1 -1 0 0 0 0];",
                "internalField uniform (0 0 0);",
                "boundaryField",
                "{",
                "    inlet { type symmetryPlane; value /* keep prefix */ uniform (4 /* x */ 5 /* y */ 6 /* z */); }",
                "    outlet { type symmetryPlane; value /* keep prefix */ uniform (4 /* x */ 5 /* y */ 6 /* z */); }",
                "    ground { type symmetryPlane; value /* keep prefix */ uniform (4 /* x */ 5 /* y */ 6 /* z */); }",
                "}",
                "",
            )
        ),
        encoding="utf-8",
    )

    artifacts = compile_openfoam_solver_case_bundle(
        _spec(tmp_path, _valid_data()),
        template_case_dir=template,
        output_dir=tmp_path / "commented_value_bundle",
        available_patch_ids=PATCHES,
    )

    text = (artifacts.case_dirs["straight"] / "0.orig/Ua").read_text(encoding="utf-8")
    assert "/* keep prefix */" in text
    assert "/* x */" in text
    assert "/* y */" in text
    assert "/* z */" in text
    assert "uniform (0 /* x */ 0 /* y */ 0 /* z */);" in text


def test_nested_required_initial_field_is_unsupported_before_staging(tmp_path: Path) -> None:
    template = _template(tmp_path)
    nested = template / "0.orig/nested"
    nested.mkdir()
    (template / "0.orig/alpha").replace(nested / "alpha")

    artifacts = compile_openfoam_solver_case_bundle(
        _spec(tmp_path, _valid_data()),
        template_case_dir=template,
        output_dir=tmp_path / "nested_field_bundle",
        available_patch_ids=PATCHES,
        require_compile_ready=False,
    )

    assert artifacts.manifest.compile_ready is False
    assert "required_initial_field_not_root_level:alpha" in artifacts.manifest.unsupported
    assert artifacts.case_dirs == {}


def test_invalid_root_required_field_cannot_be_replaced_by_nested_field(tmp_path: Path) -> None:
    template = _template(tmp_path)
    nested = template / "0.orig/nested"
    nested.mkdir()
    alpha = template / "0.orig/alpha"
    alpha.replace(nested / "alpha")
    alpha.write_text("template sentinel, not an OpenFOAM field\n", encoding="utf-8")

    artifacts = compile_openfoam_solver_case_bundle(
        _spec(tmp_path, _valid_data()),
        template_case_dir=template,
        output_dir=tmp_path / "invalid_root_field_bundle",
        available_patch_ids=PATCHES,
        require_compile_ready=False,
    )

    assert artifacts.manifest.compile_ready is False
    assert "missing_required_initial_field_boundary:alpha" in artifacts.manifest.unsupported
    assert artifacts.case_dirs == {}


def test_missing_block_mesh_patch_is_unsupported_without_cases(tmp_path: Path) -> None:
    template = _template(tmp_path)
    patch_names = ("inlet", "outlet", "spanMin", "spanMax", "upper")
    (template / "system/blockMeshDict").write_bytes(_block_mesh_bytes(patch_names))

    artifacts = compile_openfoam_solver_case_bundle(
        _g2_spec(tmp_path),
        template_case_dir=template,
        output_dir=tmp_path / "missing_mesh_patch",
        available_patch_ids=("inlet", "outlet", "spanMin", "spanMax", "lower", "upper"),
        require_compile_ready=False,
    )

    assert artifacts.manifest.compile_ready is False
    assert "missing_block_mesh_patch:straight:lower" in artifacts.manifest.unsupported
    assert "missing_block_mesh_patch:yawed:lower" in artifacts.manifest.unsupported
    assert artifacts.case_dirs == {}


def test_missing_retained_field_patch_is_unsupported_without_cases(tmp_path: Path) -> None:
    template = _template(tmp_path)
    patch_names = ("inlet", "outlet", "spanMin", "spanMax", "lower", "upper")
    (template / "system/blockMeshDict").write_bytes(_block_mesh_bytes(patch_names))
    _write_required_initial_fields(template, patch_names)
    alpha = template / "0.orig/alpha"
    alpha.write_text(
        alpha.read_text(encoding="utf-8").replace(
            "    lower // retain field comment { }\n"
            "    {\n"
            "        type /* preserve comment */ zeroGradient;\n"
            "    }\n",
            "",
        ),
        encoding="utf-8",
    )

    artifacts = compile_openfoam_solver_case_bundle(
        _g2_spec(tmp_path),
        template_case_dir=template,
        output_dir=tmp_path / "missing_field_patch",
        available_patch_ids=patch_names,
        require_compile_ready=False,
    )

    assert artifacts.manifest.compile_ready is False
    assert (
        "field_boundary_missing_patch:straight:alpha:lower"
        in artifacts.manifest.unsupported
    )
    assert artifacts.case_dirs == {}


def test_incompatible_unmanaged_retained_field_is_unsupported(tmp_path: Path) -> None:
    template = _template(tmp_path)
    patch_names = ("inlet", "outlet", "spanMin", "spanMax", "lower", "upper")
    (template / "system/blockMeshDict").write_bytes(_block_mesh_bytes(patch_names))
    _write_required_initial_fields(template, patch_names)
    _write_scalar_initial_field(
        template,
        "customDesignState",
        {
            "inlet": "zeroGradient",
            "outlet": "zeroGradient",
            "spanMin": "symmetryPlane",
            "spanMax": "symmetryPlane",
            "lower": "symmetryPlane",
            "upper": "symmetryPlane",
        },
    )

    artifacts = compile_openfoam_solver_case_bundle(
        _g2_spec(tmp_path),
        template_case_dir=template,
        output_dir=tmp_path / "incompatible_field",
        available_patch_ids=patch_names,
        require_compile_ready=False,
    )

    assert artifacts.manifest.compile_ready is False
    assert (
        "field_patch_type_incompatible:straight:customDesignState:lower:symmetryPlane:wall"
        in artifacts.manifest.unsupported
    )
    assert artifacts.case_dirs == {}


def test_duplicate_block_mesh_patch_is_unsupported(tmp_path: Path) -> None:
    template = _template(tmp_path)
    patch_names = ("inlet", "outlet", "spanMin", "spanMax", "lower", "upper", "lower")
    (template / "system/blockMeshDict").write_bytes(_block_mesh_bytes(patch_names))

    artifacts = compile_openfoam_solver_case_bundle(
        _g2_spec(tmp_path),
        template_case_dir=template,
        output_dir=tmp_path / "duplicate_mesh_patch",
        available_patch_ids=("inlet", "outlet", "spanMin", "spanMax", "lower", "upper"),
        require_compile_ready=False,
    )

    assert artifacts.manifest.compile_ready is False
    assert (
        "malformed_block_mesh_boundary:duplicate_patch:lower"
        in artifacts.manifest.unsupported
    )
    assert artifacts.case_dirs == {}


def test_staged_allrun_inserts_crlf_fail_fast_after_shebang(tmp_path: Path) -> None:
    template = _template(tmp_path)
    allrun_source = b"#!/bin/sh\r\nfalse\r\nprintf 'must-not-run\\n'\r\n"
    (template / "Allrun").write_bytes(allrun_source)
    allclean_source = (template / "Allclean").read_bytes()

    artifacts = compile_openfoam_solver_case_bundle(
        _spec(tmp_path, _valid_data()),
        template_case_dir=template,
        output_dir=tmp_path / "fail_fast_bundle",
        available_patch_ids=PATCHES,
    )

    case = artifacts.case_dirs["straight"]
    staged = (case / "Allrun").read_bytes()
    assert staged == b"#!/bin/sh\r\nset -e\r\nfalse\r\nprintf 'must-not-run\\n'\r\n"
    assert (case / "Allclean").read_bytes() == allclean_source
    compilation = json.loads(
        (case / "openfoam_case_compilation.json").read_text(encoding="utf-8")
    )
    scripts = {
        script["required"]: script
        for script in compilation["execution_contract"]["scripts"]
    }
    allrun = scripts["Allrun"]
    assert allrun["fail_fast"] is True
    assert allrun["patch_applied"] is True
    assert allrun["pre_patch_sha256"] != allrun["post_patch_sha256"]
    assert scripts["Allclean"]["pre_patch_sha256"] == scripts["Allclean"]["post_patch_sha256"]


def test_unsupported_bundle_writes_manifest_and_metadata_without_cases(tmp_path: Path) -> None:
    spec = _spec(tmp_path, yaml.safe_load(EXAMPLE.read_text(encoding="utf-8")))
    output = tmp_path / "unsupported"

    artifacts = compile_openfoam_solver_case_bundle(
        spec,
        template_case_dir=tmp_path / "template_not_needed",
        output_dir=output,
        available_patch_ids=PATCHES,
        require_compile_ready=False,
    )

    assert artifacts.manifest_json.is_file()
    assert artifacts.bundle_metadata_json.is_file()
    assert artifacts.case_dirs == {}
    metadata = json.loads(artifacts.bundle_metadata_json.read_text(encoding="utf-8"))
    assert metadata["status"] == "unsupported"
    assert metadata["compile_ready"] is False
    assert not list(output.glob("flow_*"))


def test_require_ready_raises_only_after_unsupported_artifacts_exist(tmp_path: Path) -> None:
    spec = _spec(tmp_path, yaml.safe_load(EXAMPLE.read_text(encoding="utf-8")))
    output = tmp_path / "required"

    with pytest.raises(ValueError, match="not compile-ready"):
        compile_openfoam_solver_case_bundle(
            spec,
            template_case_dir=tmp_path / "template_not_needed",
            output_dir=output,
            available_patch_ids=PATCHES,
            require_compile_ready=True,
        )
    assert (output / "openfoam_solver_case_manifest.json").is_file()
    assert (output / "openfoam_case_bundle.json").is_file()


def test_nonmarker_output_is_rejected_even_with_overwrite(tmp_path: Path) -> None:
    spec = _spec(tmp_path, _valid_data())
    template = _template(tmp_path)
    output = tmp_path / "foreign"
    output.mkdir()
    sentinel = output / "unrelated.txt"
    sentinel.write_text("keep", encoding="utf-8")

    for overwrite in (False, True):
        with pytest.raises(FileExistsError, match="without openfoam_case_bundle.json"):
            compile_openfoam_solver_case_bundle(
                spec,
                template_case_dir=template,
                output_dir=output,
                available_patch_ids=PATCHES,
                overwrite=overwrite,
            )
    assert sentinel.read_text(encoding="utf-8") == "keep"


def test_owned_overwrite_replaces_cases_and_preserves_unrelated_files(tmp_path: Path) -> None:
    first = _compile(tmp_path)
    unrelated = first.output_dir / "notes.txt"
    unrelated_dir = first.output_dir / "user_data"
    unrelated.write_text("keep", encoding="utf-8")
    unrelated_dir.mkdir()
    (unrelated_dir / "keep.txt").write_text("keep", encoding="utf-8")
    old_case_marker = first.case_dirs["straight"] / "old.txt"
    old_case_marker.write_text("remove with owned case", encoding="utf-8")

    second = compile_openfoam_solver_case_bundle(
        _spec(tmp_path, _valid_data(), "problem_repeat.yaml"),
        template_case_dir=tmp_path / "template",
        output_dir=first.output_dir,
        available_patch_ids=PATCHES,
        overwrite=True,
    )

    assert unrelated.read_text(encoding="utf-8") == "keep"
    assert (unrelated_dir / "keep.txt").read_text(encoding="utf-8") == "keep"
    assert not old_case_marker.exists()
    assert second.case_dirs["straight"].is_dir()


def test_missing_template_writes_manifest_then_fails(tmp_path: Path) -> None:
    spec = _spec(tmp_path, _valid_data())
    output = tmp_path / "missing_template_output"

    with pytest.raises(FileNotFoundError, match="missing required paths"):
        compile_openfoam_solver_case_bundle(
            spec,
            template_case_dir=tmp_path / "missing_template",
            output_dir=output,
            available_patch_ids=PATCHES,
        )
    assert (output / "openfoam_solver_case_manifest.json").is_file()
    assert not (output / "openfoam_case_bundle.json").exists()


@pytest.mark.parametrize(
    ("missing", "reason"),
    (
        ("Allrun", "missing_execution_script:Allrun"),
        ("Allclean", "missing_execution_script:Allclean"),
        (
            "lib/libcfdSdfPorousObjectives.so",
            "missing_custom_library:libcfdSdfPorousObjectives.so",
        ),
    ),
)
def test_missing_execution_dependency_is_explicitly_unsupported(
    tmp_path: Path, missing: str, reason: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    template = _template(tmp_path)
    (template / missing).unlink()
    if missing.startswith("lib/"):
        monkeypatch.setattr(compiler_module, "_KNOWN_REPOSITORY_LIBRARIES", {})
    output = tmp_path / "execution_unsupported"

    artifacts = compile_openfoam_solver_case_bundle(
        _spec(tmp_path, _valid_data()),
        template_case_dir=template,
        output_dir=output,
        available_patch_ids=PATCHES,
        require_compile_ready=False,
    )

    assert artifacts.manifest.compile_ready is False
    assert reason in artifacts.manifest.unsupported
    assert artifacts.case_dirs == {}
    bundle = json.loads(artifacts.bundle_metadata_json.read_text(encoding="utf-8"))
    assert bundle["execution_contract"]["qualification"] == "unsupported"
    assert reason in bundle["unsupported"]
    assert not list(output.glob("flow_*"))


def test_runtime_library_is_recorded_but_not_resolved_from_host(tmp_path: Path) -> None:
    template = _template(tmp_path)
    (template / "system/controlDict").write_text(
        'application adjointOptimisationFoam;\n'
        'libs ("libfiniteVolume.so" "libcfdSdfPorousObjectives.so");\n',
        encoding="utf-8",
    )
    artifacts = compile_openfoam_solver_case_bundle(
        _spec(tmp_path, _valid_data()),
        template_case_dir=template,
        output_dir=tmp_path / "runtime_lib_bundle",
        available_patch_ids=PATCHES,
    )

    compilation = json.loads(
        (artifacts.case_dirs["straight"] / "openfoam_case_compilation.json").read_text(
            encoding="utf-8"
        )
    )
    runtime, custom = compilation["execution_contract"]["libraries"]
    assert runtime["required"] == "libfiniteVolume.so"
    assert runtime["resolved_source"] is None
    assert runtime["qualification"] == "solver_runtime_required_not_verified"
    assert custom["qualification"] == "staged_not_runtime_qualified"


def test_required_objective_library_must_be_declared_in_control_dict(
    tmp_path: Path,
) -> None:
    template = _template(tmp_path)
    (template / "system/controlDict").write_text(
        'application adjointOptimisationFoam;\nlibs ("libfiniteVolume.so");\n',
        encoding="utf-8",
    )
    artifacts = compile_openfoam_solver_case_bundle(
        _spec(tmp_path, _valid_data()),
        template_case_dir=template,
        output_dir=tmp_path / "missing_declaration_bundle",
        available_patch_ids=PATCHES,
        require_compile_ready=False,
    )

    assert artifacts.manifest.compile_ready is False
    assert (
        "missing_required_control_dict_library:libcfdSdfPorousObjectives.so"
        in artifacts.manifest.unsupported
    )


def test_template_inside_output_is_rejected(tmp_path: Path) -> None:
    spec = _spec(tmp_path, _valid_data())
    output = tmp_path / "bundle"
    template = output / "template"

    with pytest.raises(ValueError, match="must not equal or be inside output_dir"):
        compile_openfoam_solver_case_bundle(
            spec,
            template_case_dir=template,
            output_dir=output,
            available_patch_ids=PATCHES,
        )


def test_invalid_iterations_fail_before_output_creation(tmp_path: Path) -> None:
    spec = _spec(tmp_path, _valid_data())
    output = tmp_path / "invalid_iterations"

    with pytest.raises(ValueError, match="positive integer"):
        compile_openfoam_solver_case_bundle(
            spec,
            template_case_dir=tmp_path / "template",
            output_dir=output,
            available_patch_ids=PATCHES,
            adjoint_iterations=0,
        )
    assert not output.exists()


def test_physics_staging_is_cleaned_when_response_render_fails(tmp_path: Path) -> None:
    spec = _spec(tmp_path, _valid_data())
    template = _template(tmp_path, malformed_fv=True)
    output = tmp_path / "failed_bundle"

    with pytest.raises(ValueError, match="names statement"):
        compile_openfoam_solver_case_bundle(
            spec,
            template_case_dir=template,
            output_dir=output,
            available_patch_ids=PATCHES,
        )
    assert not list(output.glob(".physics_*"))


def test_second_flow_failure_rolls_back_all_new_cases_and_is_recoverable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = _compile(tmp_path)
    unrelated = first.output_dir / "user_notes.txt"
    unrelated.write_text("preserve", encoding="utf-8")
    spec = _spec(tmp_path, _valid_data(), "failure_problem.yaml")
    real_renderer = compiler_module.render_openfoam_force_response_files

    def fail_second(plan, case_dir, **kwargs):
        if plan.flow_case_id == "yawed":
            raise RuntimeError("injected second-flow response failure")
        return real_renderer(plan, case_dir, **kwargs)

    monkeypatch.setattr(
        compiler_module, "render_openfoam_force_response_files", fail_second
    )
    with pytest.raises(RuntimeError, match="second-flow"):
        compile_openfoam_solver_case_bundle(
            spec,
            template_case_dir=tmp_path / "template",
            output_dir=first.output_dir,
            available_patch_ids=PATCHES,
            overwrite=True,
        )

    assert not list(first.output_dir.glob("flow_*"))
    assert not list(first.output_dir.glob(".case_*"))
    assert not list(first.output_dir.glob(".physics_*"))
    assert unrelated.read_text(encoding="utf-8") == "preserve"
    failed = json.loads(first.bundle_metadata_json.read_text(encoding="utf-8"))
    assert failed["status"] == "failed"
    assert failed["compile_ready"] is True
    assert failed["error_type"] == "RuntimeError"
    assert "second-flow" in failed["error_message"]
    assert failed["flow_cases"]["straight"]["status"] == "rolled_back"

    monkeypatch.setattr(
        compiler_module, "render_openfoam_force_response_files", real_renderer
    )
    recovered = compile_openfoam_solver_case_bundle(
        spec,
        template_case_dir=tmp_path / "template",
        output_dir=first.output_dir,
        available_patch_ids=PATCHES,
        overwrite=True,
    )
    assert set(recovered.case_dirs) == {"straight", "yawed"}
    assert unrelated.read_text(encoding="utf-8") == "preserve"
    assert json.loads(recovered.bundle_metadata_json.read_text(encoding="utf-8"))[
        "status"
    ] == "compiled"


def test_repeat_compile_is_deterministic(tmp_path: Path) -> None:
    first = _compile(tmp_path)
    tracked = [
        first.manifest_json,
        first.bundle_metadata_json,
        *(case / "openfoam_case_compilation.json" for case in first.case_dirs.values()),
        *(case / "generated_openfoam_physics.json" for case in first.case_dirs.values()),
        *(case / "generated_openfoam_responses.json" for case in first.case_dirs.values()),
    ]
    before = {path.relative_to(first.output_dir).as_posix(): path.read_bytes() for path in tracked}

    second = compile_openfoam_solver_case_bundle(
        _spec(tmp_path, _valid_data(), "problem_repeat.yaml"),
        template_case_dir=tmp_path / "template",
        output_dir=first.output_dir,
        available_patch_ids=PATCHES,
        adjoint_iterations=7,
        overwrite=True,
    )
    after = {
        relative: (second.output_dir / relative).read_bytes()
        for relative in before
    }
    assert after == before
