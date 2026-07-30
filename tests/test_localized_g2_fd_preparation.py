from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil

import numpy as np
import pytest
import trimesh
import yaml
from typer.testing import CliRunner

from cfd_sdf.cli import app
from cfd_sdf.local_design_geometry_snapshot import create_local_design_geometry_mask_snapshot
from cfd_sdf.localized_alpha_reference_binding import (
    create_localized_alpha_reference_binding,
    write_localized_alpha_reference_binding,
)
from cfd_sdf.localized_design_state_manifest import read_localized_design_state_manifest
from cfd_sdf.localized_g2_fd_preparation import (
    LOCALIZED_G2_FD_PREPARATION_FILENAME,
    prepare_localized_g2_openfoam_fd_direction,
)
from cfd_sdf.localized_g2_fd_runner import (
    LOCALIZED_G2_FD_RUN_FILENAME,
    run_localized_g2_openfoam_fd_direction,
)
from cfd_sdf.localized_reference_state_bundle import build_localized_reference_state_bundle
from cfd_sdf.openfoam_grid_transfer import UniformCartesianCellGrid


runner = CliRunner()


def test_prepares_atomic_one_sided_cases_and_records_fixed_protocol(tmp_path: Path) -> None:
    inputs = _inputs(tmp_path)
    result = prepare_localized_g2_openfoam_fd_direction(
        inputs["project"], reference_bundle_path=inputs["bundle"], topology_report_path=inputs["topology"],
        alpha_reference_binding_path=inputs["binding"], compiled_case_dir=inputs["compiled"],
        direction=inputs["direction"], epsilon_ladder=(0.01, 0.005, 0.0025), output_dir=tmp_path / "prepared",
    )
    assert result.status == "prepared_one_sided"
    assert (result.path / "cases" / "reference").is_dir()
    assert len(result.cases) == 4
    report = json.loads((result.path / LOCALIZED_G2_FD_PREPARATION_FILENAME).read_text(encoding="utf-8"))
    assert report["execution_status"] == "not_run"
    assert report["topology_stability"]["all_prepared_perturbations_unchanged"] is True
    assert report["validation_protocol"]["baseline_repeats_minimum"] == 2
    assert report["validation_protocol"]["final_gate"].endswith("absolute_error<=5*sigmaD")
    assert "reference" in report["cases"]
    assert {item["epsilon"] for key, item in report["cases"].items() if key != "reference"} == {0.01, 0.005, 0.0025}


def test_fail_closed_for_raw_bound_topology_change_and_bad_direction(tmp_path: Path) -> None:
    inputs = _inputs(tmp_path)
    with pytest.raises(ValueError, match="exceeds positive raw feasibility"):
        prepare_localized_g2_openfoam_fd_direction(
            inputs["project"], reference_bundle_path=inputs["bundle"], topology_report_path=inputs["topology"],
            alpha_reference_binding_path=inputs["binding"], compiled_case_dir=inputs["compiled"],
            direction=inputs["direction"], epsilon_ladder=(1.1, 0.55, 0.275), output_dir=tmp_path / "too_large",
        )
    assert not (tmp_path / "too_large").exists()
    with pytest.raises(ValueError, match="topology predicate changes"):
        prepare_localized_g2_openfoam_fd_direction(
            inputs["project"], reference_bundle_path=inputs["bundle"], topology_report_path=inputs["topology"],
            alpha_reference_binding_path=inputs["binding"], compiled_case_dir=inputs["compiled"],
            direction=inputs["direction"], epsilon_ladder=(0.7, 0.35, 0.175), output_dir=tmp_path / "predicate_change",
        )
    assert not (tmp_path / "predicate_change").exists()
    with pytest.raises(ValueError, match="negative raw feasibility"):
        prepare_localized_g2_openfoam_fd_direction(
            inputs["project"], reference_bundle_path=inputs["bundle"], topology_report_path=inputs["topology"],
            alpha_reference_binding_path=inputs["binding"], compiled_case_dir=inputs["compiled"],
            direction=inputs["direction"], epsilon_ladder=(0.01, 0.005, 0.0025),
            output_dir=tmp_path / "central_infeasible", mode="central",
        )
    assert not (tmp_path / "central_infeasible").exists()
    bad = np.load(inputs["direction"]); bad[0] = 0.5; np.save(tmp_path / "bad.npy", bad)
    with pytest.raises(ValueError, match="outside active"):
        prepare_localized_g2_openfoam_fd_direction(
            inputs["project"], reference_bundle_path=inputs["bundle"], topology_report_path=inputs["topology"],
            alpha_reference_binding_path=inputs["binding"], compiled_case_dir=inputs["compiled"],
            direction=tmp_path / "bad.npy", epsilon_ladder=(0.01, 0.005, 0.0025), output_dir=tmp_path / "bad_direction",
        )


def test_refuses_non_success_or_mismatched_topology_report_without_publish(tmp_path: Path) -> None:
    inputs = _inputs(tmp_path)
    report = json.loads(Path(inputs["topology"]).read_text(encoding="utf-8"))
    report["status"] = "rejected"
    bad = tmp_path / "rejected_topology.json"; bad.write_text(json.dumps(report), encoding="utf-8")
    with pytest.raises(ValueError, match="status='success'"):
        prepare_localized_g2_openfoam_fd_direction(
            inputs["project"], reference_bundle_path=inputs["bundle"], topology_report_path=bad,
            alpha_reference_binding_path=inputs["binding"], compiled_case_dir=inputs["compiled"],
            direction=inputs["direction"], epsilon_ladder=(0.01, 0.005, 0.0025), output_dir=tmp_path / "bad_topology",
        )
    assert not (tmp_path / "bad_topology").exists()


def test_cli_stages_but_does_not_execute(tmp_path: Path) -> None:
    inputs = _inputs(tmp_path)
    out = tmp_path / "cli_prepared"
    result = runner.invoke(app, [
        "prepare-localized-g2-openfoam-fd-direction", str(inputs["project"]), str(inputs["bundle"]),
        str(inputs["topology"]), str(inputs["binding"]), str(inputs["compiled"]), str(inputs["direction"]),
        "0.01", str(out),
    ])
    assert result.exit_code == 0, result.output
    summary = json.loads(result.output)
    assert summary["execution_status"] == "not_run"
    assert summary["report_path"] == str(out / LOCALIZED_G2_FD_PREPARATION_FILENAME)


def test_runner_uses_fresh_exact_reference_then_one_sided_ladder_without_validation(tmp_path: Path) -> None:
    inputs = _inputs(tmp_path)
    prepared = prepare_localized_g2_openfoam_fd_direction(
        inputs["project"], reference_bundle_path=inputs["bundle"], topology_report_path=inputs["topology"],
        alpha_reference_binding_path=inputs["binding"], compiled_case_dir=inputs["compiled"],
        direction=inputs["direction"], epsilon_ladder=(0.01, 0.005, 0.0025), output_dir=tmp_path / "prepared",
    )
    original_hash = hashlib.sha256(prepared.report_json.read_bytes()).hexdigest()
    calls: list[tuple[str, str, Path | None]] = []

    def synthetic(**kwargs):
        calls.append((kwargs["phase"], kwargs["label"], kwargs["reference_case_dir"]))
        case = kwargs["case_dir"]
        (case / "2").mkdir(exist_ok=True)
        objective = case / "optimisation" / "objective"; objective.mkdir(parents=True, exist_ok=True)
        (objective / "drag.dat").write_text("0 0 1\n", encoding="utf-8")
        return {"ok": True, "command": ["synthetic", kwargs["phase"], kwargs["label"]], "backend": "synthetic",
                "execution_identity": {"openfoam_version": "synthetic-v1"}, "convergence": {"status": "converged"},
                "final_time": 2.0, "response_provenance": {"response_id": "drag", "source": "synthetic"}}

    result = run_localized_g2_openfoam_fd_direction(
        prepared.path, output_dir=tmp_path / "run", adjoint_name="dragAdjoint", execute=True, runner=synthetic,
    )
    assert result.status == "run_complete"
    assert hashlib.sha256(prepared.report_json.read_bytes()).hexdigest() == original_hash
    assert [(phase, label) for phase, label, _ in calls] == [
        ("primal", "reference_001"), ("primal", "reference_002"), ("adjoint", "dragAdjoint"),
        ("primal", "plus_h0.01"), ("primal", "plus_h0.0050000000000000001"), ("primal", "plus_h0.0025000000000000001"),
    ]
    assert calls[2][2] is not None and calls[2][2].name == "reference_001"
    report = json.loads((result.path / LOCALIZED_G2_FD_RUN_FILENAME).read_text(encoding="utf-8"))
    assert report["validation_status"] == "not_run"
    assert report["attempts"][0]["case_input_tree_sha256"] != report["attempts"][0]["case_output_tree_sha256"]
    assert report["attempts"][2]["reference_primal_relative_path"] == "primal/reference_001"


def test_runner_honors_central_minus_cases_and_publishes_failure_status(tmp_path: Path) -> None:
    inputs = _inputs(tmp_path)
    prepared = prepare_localized_g2_openfoam_fd_direction(
        inputs["project"], reference_bundle_path=inputs["bundle"], topology_report_path=inputs["topology"],
        alpha_reference_binding_path=inputs["binding"], compiled_case_dir=inputs["compiled"],
        direction=inputs["direction"], epsilon_ladder=(0.01, 0.005, 0.0025), output_dir=tmp_path / "prepared",
    )
    _make_central_fixture(prepared.path)
    calls: list[str] = []

    def synthetic(**kwargs):
        calls.append(kwargs["label"])
        if kwargs["label"].startswith("minus_h"):
            return {"ok": False, "command": ["synthetic"], "backend": "synthetic", "error": "intentional failure"}
        return {"ok": True, "command": ["synthetic"], "backend": "synthetic"}

    result = run_localized_g2_openfoam_fd_direction(
        prepared.path, output_dir=tmp_path / "failed", adjoint_name="adj", execute=True, runner=synthetic,
    )
    assert result.status == "execution_failed"
    assert calls[-1].startswith("minus_h")
    report = json.loads((result.path / LOCALIZED_G2_FD_RUN_FILENAME).read_text(encoding="utf-8"))
    assert str(report["failure"]["label"]).startswith("minus_h")
    assert report["validation_status"] == "not_run"


def test_runner_refuses_tampered_prepared_case_before_creating_output(tmp_path: Path) -> None:
    inputs = _inputs(tmp_path)
    prepared = prepare_localized_g2_openfoam_fd_direction(
        inputs["project"], reference_bundle_path=inputs["bundle"], topology_report_path=inputs["topology"],
        alpha_reference_binding_path=inputs["binding"], compiled_case_dir=inputs["compiled"],
        direction=inputs["direction"], epsilon_ladder=(0.01, 0.005, 0.0025), output_dir=tmp_path / "prepared",
    )
    (prepared.path / "cases" / "reference" / "0.orig" / "alpha").write_text("tampered", encoding="utf-8")
    with pytest.raises(ValueError, match="alpha"):
        run_localized_g2_openfoam_fd_direction(
            prepared.path, output_dir=tmp_path / "must_not_exist", adjoint_name="adj", execute=True,
            runner=lambda **_: {"ok": True, "command": [], "backend": "synthetic"},
        )
    assert not (tmp_path / "must_not_exist").exists()


def test_run_cli_requires_explicit_execute_before_any_openfoam_runtime(tmp_path: Path) -> None:
    result = runner.invoke(app, [
        "run-localized-g2-openfoam-fd-direction", str(tmp_path / "prepared"), "dragAdjoint", str(tmp_path / "run"),
    ])
    assert result.exit_code != 0
    assert "pass --execute" in result.output
    assert not (tmp_path / "run").exists()


def _make_central_fixture(path: Path) -> None:
    """Extend a valid one-sided fixture solely to exercise run ordering.

    Preparation itself owns raw-feasibility and topology proof; this tiny test
    fixture copies already validated staged cases to assert that the runner
    neither invents minus cases for one-sided input nor skips declared ones.
    """
    report_path = path / LOCALIZED_G2_FD_PREPARATION_FILENAME
    report = json.loads(report_path.read_text(encoding="utf-8"))
    cases = report["cases"]
    for epsilon in report["epsilon_ladder"]:
        plus = f"plus_h{float(epsilon):.17g}".replace("+", "p").replace("-", "m")
        minus = f"minus_h{float(epsilon):.17g}".replace("+", "p").replace("-", "m")
        source = path / cases[plus]["case_relative_path"]
        target = path / "cases" / minus
        shutil.copytree(source, target)
        copied = dict(cases[plus]); copied["sign"] = "minus"; copied["case_relative_path"] = f"cases/{minus}"
        cases[minus] = copied
    report["mode"] = "central"; report["status"] = "prepared_central"
    report_path.write_text(json.dumps(report, sort_keys=True), encoding="utf-8")


def _inputs(tmp_path: Path) -> dict[str, Path]:
    project = _project(tmp_path)
    snapshot = create_local_design_geometry_mask_snapshot(project, output_dir=tmp_path / "snapshot", z_chunk_size=1, containment_chunk_size=8)
    bundle = build_localized_reference_state_bundle(
        project, geometry_snapshot_path=snapshot.snapshot.path, output_dir=tmp_path / "bundle", expected_component_count=1,
        z_slab_size=1, disk_free_bytes=lambda _: 9 * 1024**3, available_memory_bytes=lambda: 9 * 1024**3,
    ).path
    state = read_localized_design_state_manifest(bundle / "localized_design_state_manifest.json")
    grid = UniformCartesianCellGrid(origin=state.grid.origin, spacing=state.grid.spacing, cell_shape=state.grid.cell_shape)
    alpha = np.full(grid.cell_count, 0.5, dtype=np.float64)
    alpha_path = bundle / "alpha_reference.npy"; np.save(alpha_path, alpha)
    binding_path = write_localized_alpha_reference_binding(create_localized_alpha_reference_binding(
        path=bundle / "alpha_reference_binding.json", reference_state_manifest_path=bundle / "localized_design_state_manifest.json",
        cfd_grid=grid, alpha_reference_path=alpha_path, provenance={"source": "fd-preparation-test"},
    ))
    raw = np.load(bundle / "raw" / "rho_raw.npy")
    active = np.load(bundle / "geometry_snapshot" / "masks" / "active_design_mask.npy")
    direction = np.zeros_like(raw)
    direction[int(np.flatnonzero(active & (raw == 0.0))[0])] = 1.0
    direction_path = tmp_path / "direction.npy"; np.save(direction_path, direction)
    topology = tmp_path / "topology_success.json"
    topology.write_text(json.dumps({
        "schema_version": 1, "kind": "localized_reference_topology_report", "status": "success",
        "problem_spec_sha256": state.problem_spec_sha256, "grid_sha256": state.grid_sha256,
        "reference_bundle_path": str(bundle.resolve()), "reference_state_manifest_sha256": state.sha256,
        "rho_projected_sha256": state.states["rho_projected"].byte_sha256,
        "reference_bundle_geometry_snapshot_sha256": json.loads((bundle / "localized_reference_state.json").read_text())["geometry_snapshot_sha256"],
        "reference_bundle_raw_manifest_sha256": json.loads((bundle / "localized_reference_state.json").read_text())["raw_manifest_sha256"],
        "initial_design_stl_sha256": json.loads((bundle / "localized_reference_state.json").read_text())["initial_design_stl_sha256"],
    }, sort_keys=True), encoding="utf-8")
    return {"project": project, "bundle": bundle, "topology": topology, "binding": binding_path,
            "compiled": _compiled_case(tmp_path, state.grid.cell_shape), "direction": direction_path}


def _project(tmp_path: Path) -> Path:
    data = yaml.safe_load(Path("examples/g2_openfoam_compile/project.yaml").read_text(encoding="utf-8"))
    geometry = tmp_path / "geometry"; geometry.mkdir()
    for name, center, extent in (
        ("design.stl", (1., 1., 1.), (2., 2., 2.)), ("fixed.stl", (.25, .25, .25), (.2, .2, .2)),
        ("root.stl", (.25, .25, .25), (.2, .2, .2)), ("forbidden.stl", (2.3, 2.3, 2.3), (.1, .1, .1)),
        ("initial.stl", (1., 1., 1.), (1.2, 1.2, 1.2)),
    ):
        mesh = trimesh.creation.box(extents=extent); mesh.apply_translation(center); mesh.export(geometry / name)
    data["geometry_regions"] = [
        {"id": "design", "role": "design_domain", "file": "geometry/design.stl"},
        {"id": "fixed", "role": "fixed_solid", "file": "geometry/fixed.stl"},
        {"id": "root", "role": "root", "file": "geometry/root.stl"},
        {"id": "forbidden", "role": "forbidden_region", "file": "geometry/forbidden.stl"},
        {"id": "initial", "role": "initial_design", "file": "geometry/initial.stl"},
    ]
    data["topology_policy"]["root_groups"] = [{"id": "mounts", "region_ids": ["root"]}]
    for key in ("minimum_solid_width_m", "minimum_void_width_m", "minimum_gap_m", "erosion_radius_m"):
        data["topology_policy"][key] = .5
    data["design_grid"] = {"kind": "uniform_cartesian", "design_domain_region_id": "design", "voxel_size_m": .5,
        "domain_bounds_m": {"lower": [0., 0., 0.], "upper": [2., 2., 2.]}, "expected_cell_shape": [4, 4, 4],
        "expected_cell_count": 64, "topology_resolution": {"minimum_solid_width_cells": 1, "minimum_void_width_cells": 1, "minimum_gap_cells": 1, "erosion_radius_cells": 1}}
    path = tmp_path / "project.yaml"; path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return path


def _compiled_case(tmp_path: Path, shape: tuple[int, int, int]) -> Path:
    case = tmp_path / "compiled"; case.mkdir(); (case / "0.orig").mkdir(); (case / "constant").mkdir(); (case / "system").mkdir()
    nx, ny, nz = shape
    (case / "0.orig" / "alpha").write_text("FoamFile\n{ class volScalarField; object alpha; }\ninternalField uniform 0;\n", encoding="utf-8")
    (case / "Allrun").write_text("#!/bin/sh\nrunApplication setFields\nrunApplication solver\n", encoding="utf-8")
    (case / "Allclean").write_text("#!/bin/sh\n", encoding="utf-8")
    (case / "system" / "blockMeshDict").write_text(
        "FoamFile\n{ version 2.0; format ascii; class dictionary; object blockMeshDict; }\nscale 1;\nvertices\n(\n"
        "(0 0 0) (2 0 0) (2 2 0) (0 2 0) (0 0 2) (2 0 2) (2 2 2) (0 2 2)\n);\nblocks\n(\n"
        f"hex (0 1 2 3 4 5 6 7) ({nx} {ny} {nz}) simpleGrading (1 1 1);\n);\nedges\n(\n);\n", encoding="utf-8")
    (case / "openfoam_case_compilation.json").write_text(json.dumps({"status": "compiled"}), encoding="utf-8")
    return case
