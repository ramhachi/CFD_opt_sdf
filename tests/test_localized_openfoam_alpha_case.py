from __future__ import annotations

from dataclasses import replace
import json
import os
from pathlib import Path
import stat

import numpy as np
import pytest

import cfd_sdf.localized_openfoam_alpha_case as staging_module
from cfd_sdf.localized_alpha_reference_binding import (
    calculate_localized_alpha_source,
    create_localized_alpha_reference_binding,
    load_and_verify_localized_alpha_reference_binding,
    write_localized_alpha_reference_binding,
)
from cfd_sdf.localized_design_state_manifest import (
    LocalizedDesignGrid,
    create_localized_design_state_manifest,
    read_localized_design_state_manifest,
    write_localized_design_state_manifest,
)
from cfd_sdf.localized_design_transfer import LocalizedDesignToCfdTransfer
from cfd_sdf.localized_filter_projection import (
    LocalizedConeFilterConfig,
    LocalizedHeavisideProjectionConfig,
    write_canonical_filter_config,
    write_canonical_projection_config,
)
from cfd_sdf.localized_openfoam_alpha_case import (
    stage_localized_openfoam_alpha_case,
    validate_localized_openfoam_alpha_case,
)
from cfd_sdf.openfoam_grid_transfer import UniformCartesianCellGrid


_PROBLEM_HASH = "a" * 64
_FILTER_HASH = "b" * 64
_PROJECTION_HASH = "c" * 64


def _state(root: Path, *, rho_projected: np.ndarray) -> Path:
    (root / "arrays").mkdir(parents=True)
    masks = {
        "active_design_mask": np.array([True, True, False, False], dtype=np.bool_),
        "forbidden_mask": np.array([False, False, True, False], dtype=np.bool_),
        "fixed_solid_mask": np.array([False, False, False, True], dtype=np.bool_),
        "root_mask": np.array([False, False, False, True], dtype=np.bool_),
    }
    states = {identifier: rho_projected for identifier in ("rho", "rho_filtered", "rho_projected")}
    mask_paths: dict[str, str] = {}
    state_paths: dict[str, str] = {}
    for identifier, values in masks.items():
        path = root / "arrays" / f"{identifier}.npy"
        np.save(path, values)
        mask_paths[identifier] = path.relative_to(root).as_posix()
    for identifier, values in states.items():
        path = root / "arrays" / f"{identifier}.npy"
        np.save(path, values)
        state_paths[identifier] = path.relative_to(root).as_posix()
    filter_path = root / "filter_config.json"
    projection_path = root / "projection_config.json"
    filter_hash = write_canonical_filter_config(filter_path, LocalizedConeFilterConfig())
    projection_hash = write_canonical_projection_config(
        projection_path, LocalizedHeavisideProjectionConfig()
    )
    manifest = create_localized_design_state_manifest(
        path=root / "state.json",
        problem_spec_sha256=_PROBLEM_HASH,
        grid=LocalizedDesignGrid(origin=(0.0, 0.0, 0.0), spacing=(1.0, 1.0, 1.0), cell_shape=(2, 2, 1)),
        masks=mask_paths,
        states=state_paths,
        filter_config_sha256=filter_hash,
        projection_config_sha256=projection_hash,
        filter_config_path=filter_path.relative_to(root).as_posix(),
        projection_config_path=projection_path.relative_to(root).as_posix(),
    )
    return write_localized_design_state_manifest(manifest)


def _verified_source(tmp_path: Path):
    reference_path = _state(tmp_path / "reference", rho_projected=np.array([0.2, 0.8, 0.0, 0.0], dtype=np.float64))
    cfd_grid = UniformCartesianCellGrid(
        origin=(0.0, 0.0, 0.0), spacing=(1.0, 1.0, 1.0), cell_shape=(2, 2, 1)
    )
    alpha_path = tmp_path / "alpha_reference.npy"
    np.save(alpha_path, np.array([0.4, 0.6, 0.0, 0.0], dtype=np.float64))
    binding_path = write_localized_alpha_reference_binding(
        create_localized_alpha_reference_binding(
            path=tmp_path / "alpha_reference_binding.json",
            reference_state_manifest_path=reference_path,
            cfd_grid=cfd_grid,
            alpha_reference_path=alpha_path,
            provenance={"source": "unit-test", "raw_alpha_file_sha256": "d" * 64},
        )
    )
    verified = load_and_verify_localized_alpha_reference_binding(binding_path)
    transfer = LocalizedDesignToCfdTransfer.build(
        cfd_grid=cfd_grid, design_grid=verified.reference_state.manifest.grid
    )
    source = calculate_localized_alpha_source(
        binding=verified,
        current_state=read_localized_design_state_manifest(reference_path),
        transfer=transfer,
    )
    return source, verified, cfd_grid


def _block_mesh(*, grading: str = "1 1 1", extra_block: bool = False, scale: str = "1") -> str:
    blocks = "hex (0 1 2 3 4 5 6 7) (2 2 1) simpleGrading (" + grading + ")"
    if extra_block:
        blocks += "\nhex (0 1 2 3 4 5 6 7) (2 2 1) simpleGrading (1 1 1)"
    return (
        "FoamFile\n{ version 2.0; format ascii; class dictionary; object blockMeshDict; }\n"
        "scale " + scale + ";\nvertices\n(\n"
        "(0 0 0) (2 0 0) (2 2 0) (0 2 0)\n"
        "(0 0 1) (2 0 1) (2 2 1) (0 2 1)\n);\n"
        "blocks\n(\n" + blocks + ";\n);\nedges\n(\n);\n"
    )


def _compiled_case(root: Path, *, allrun: str | None = None, block_mesh: str | None = None) -> Path:
    case = root / "compiled"
    (case / "0.orig").mkdir(parents=True)
    (case / "constant").mkdir()
    (case / "system").mkdir()
    (case / "Allclean").write_bytes(b"#!/bin/sh\nexit 0\n")
    (case / "0.orig" / "alpha").write_bytes(
        b"FoamFile\n{\n class volScalarField;\n object alpha;\n}\n"
        b"dimensions [0 0 0 0 0 0 0];\ninternalField uniform 0;\n"
        b"boundaryField\n{ outlet { type zeroGradient; } }\n"
    )
    allrun_path = case / "Allrun"
    allrun_path.write_bytes(
        (allrun or "#!/bin/sh\nrunApplication blockMesh\nrunApplication setFields\nrunApplication solver\n").encode("utf-8")
    )
    allrun_path.chmod(allrun_path.stat().st_mode | stat.S_IXUSR)
    (case / "system" / "blockMeshDict").write_bytes((block_mesh or _block_mesh()).encode("utf-8"))
    (case / "openfoam_case_compilation.json").write_text(json.dumps({"status": "compiled"}), encoding="utf-8")
    # Evidence copied from a qualification case must not survive a fresh run.
    for directory in ("processor0", "0", "optimisation", "postProcessing", "VTK"):
        (case / directory).mkdir()
    (case / "log.solver").write_text("stale", encoding="utf-8")
    (case / "openfoam_run_summary.json").write_text("{}", encoding="utf-8")
    return case


def test_stages_fresh_case_with_verified_grid_bound_source(tmp_path: Path) -> None:
    source, binding, grid = _verified_source(tmp_path)
    template = _compiled_case(tmp_path / "case")

    artifacts = stage_localized_openfoam_alpha_case(
        compiled_case_dir=template,
        output_case_dir=tmp_path / "staged",
        alpha_source=source,
        verified_alpha_binding=binding,
    )

    assert artifacts.alpha_cell_count == grid.cell_count
    assert {"processor0/", "0/", "optimisation/", "postProcessing/", "VTK/", "log.solver", "openfoam_run_summary.json"} == set(artifacts.removed_runtime_artifacts)
    staged_alpha = artifacts.alpha_path.read_bytes()
    assert b"\r" not in staged_alpha
    assert b"internalField nonuniform List<scalar>\n4\n(" in staged_alpha
    allrun = (artifacts.case_dir / "Allrun").read_bytes()
    assert b"\r" not in allrun
    assert b"runApplication setFields\ncp 0.orig/alpha 0/alpha\nrunApplication solver" in allrun
    if os.name != "nt":
        assert os.stat(artifacts.case_dir / "Allrun").st_mode & stat.S_IXUSR
    assert (template / "processor0").is_dir()  # immutable template evidence
    verified = validate_localized_openfoam_alpha_case(artifacts.case_dir)
    assert verified.alpha_values_sha256 == source.alpha_sha256
    manifest = json.loads(artifacts.manifest_json.read_text(encoding="utf-8"))
    assert manifest["status"] == "prepared"
    assert manifest["execution_qualification"] == "not_run"
    assert manifest["block_mesh"]["template_block_mesh_sha256"] == manifest["block_mesh"]["staged_block_mesh_sha256"]
    assert manifest["block_mesh"]["grid_sha256"] == grid.sha256
    assert manifest["alpha_source"]["values_sha256"] == source.alpha_sha256
    assert manifest["alpha_source"]["current_state_manifest_sha256"] == source.current_state_manifest_sha256
    assert manifest["alpha_binding"]["binding_sha256"] == binding.binding.sha256
    manifest["alpha_source"]["current_state_manifest_sha256"] = "not-a-sha256"
    artifacts.manifest_json.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="current state manifest"):
        validate_localized_openfoam_alpha_case(artifacts.case_dir)


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda source: replace(source, cfd_cell_count=source.cfd_cell_count + 1), "cfd_cell_count"),
        (lambda source: replace(source, cfd_grid_sha256="e" * 64), "CFD grid"),
        (lambda source: replace(source, cell_order="z-fastest"), "cell_order"),
        (lambda source: replace(source, alpha_sha256="f" * 64), "vector hash"),
        (lambda source: replace(source, binding_sha256="0" * 64), "binding hash"),
    ],
)
def test_refuses_source_contract_mismatches(tmp_path: Path, mutate, message: str) -> None:
    source, binding, _grid = _verified_source(tmp_path)
    template = _compiled_case(tmp_path / "case")
    with pytest.raises(ValueError, match=message):
        stage_localized_openfoam_alpha_case(
            compiled_case_dir=template,
            output_case_dir=tmp_path / "staged",
            alpha_source=mutate(source),
            verified_alpha_binding=binding,
        )


@pytest.mark.parametrize(
    ("block_mesh", "message"),
    [
        (_block_mesh(scale="2"), "CFD grid"),
        (_block_mesh(grading="2 1 1"), "simpleGrading"),
        (_block_mesh(extra_block=True), "multi-block"),
    ],
)
def test_refuses_noncanonical_compiled_blockmesh(tmp_path: Path, block_mesh: str, message: str) -> None:
    source, binding, _grid = _verified_source(tmp_path)
    template = _compiled_case(tmp_path / "case", block_mesh=block_mesh)
    with pytest.raises(ValueError, match=message):
        stage_localized_openfoam_alpha_case(
            compiled_case_dir=template,
            output_case_dir=tmp_path / "staged",
            alpha_source=source,
            verified_alpha_binding=binding,
        )


def test_refuses_staged_blockmesh_tamper_before_publish(tmp_path: Path, monkeypatch) -> None:
    source, binding, _grid = _verified_source(tmp_path)
    template = _compiled_case(tmp_path / "case")
    real_patch = staging_module._patch_allrun_to_restore_alpha

    def tamper(path: Path) -> None:
        real_patch(path)
        (path.parent / "system" / "blockMeshDict").write_bytes((_block_mesh() + "// byte-level tamper\n").encode("utf-8"))

    monkeypatch.setattr(staging_module, "_patch_allrun_to_restore_alpha", tamper)
    with pytest.raises(ValueError, match="byte-identical"):
        stage_localized_openfoam_alpha_case(
            compiled_case_dir=template,
            output_case_dir=tmp_path / "staged",
            alpha_source=source,
            verified_alpha_binding=binding,
        )
    assert not (tmp_path / "staged").exists()


@pytest.mark.parametrize(
    ("allrun", "message"),
    [
        ("#!/bin/sh\nrunApplication solver\n", "exactly one"),
        ("#!/bin/sh\nrunApplication setFields\nrunApplication setFields\n", "exactly one"),
        ("runApplication setFields\n", "POSIX shell shebang"),
    ],
)
def test_refuses_ambiguous_or_non_posix_allrun_without_publishing(tmp_path: Path, allrun: str, message: str) -> None:
    source, binding, _grid = _verified_source(tmp_path)
    template = _compiled_case(tmp_path / "case", allrun=allrun)
    with pytest.raises(ValueError, match=message):
        stage_localized_openfoam_alpha_case(
            compiled_case_dir=template,
            output_case_dir=tmp_path / "staged",
            alpha_source=source,
            verified_alpha_binding=binding,
        )


def test_refuses_existing_or_nested_output_and_tampered_manifest_contract(tmp_path: Path) -> None:
    source, binding, _grid = _verified_source(tmp_path)
    template = _compiled_case(tmp_path / "case")
    output = tmp_path / "staged"
    output.mkdir()
    with pytest.raises(FileExistsError, match="already exists"):
        stage_localized_openfoam_alpha_case(
            compiled_case_dir=template, output_case_dir=output, alpha_source=source, verified_alpha_binding=binding
        )
    with pytest.raises(ValueError, match="disjoint"):
        stage_localized_openfoam_alpha_case(
            compiled_case_dir=template, output_case_dir=template / "nested", alpha_source=source, verified_alpha_binding=binding
        )
    output.rmdir()
    artifacts = stage_localized_openfoam_alpha_case(
        compiled_case_dir=template, output_case_dir=output, alpha_source=source, verified_alpha_binding=binding
    )
    (artifacts.case_dir / "Allrun").write_bytes(b"#!/bin/sh\nrunApplication setFields\n")
    with pytest.raises(ValueError, match="post-setFields"):
        validate_localized_openfoam_alpha_case(artifacts.case_dir)
