from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest
import pyvista as pv
import trimesh
import yaml

from cfd_sdf.canonical_geometry_masks import build_canonical_geometry_mask_snapshot
from cfd_sdf.canonical_grid_snapshot import load_and_verify_canonical_grid_snapshot
from cfd_sdf.fixed_grid_contract import CartesianCellGrid, _write_cell_vti
from cfd_sdf.fixed_grid_gradient_gate import load_verified_gradient_problem_binding
from cfd_sdf.problem_spec import (
    load_problem_spec,
    problem_spec_sha256,
    write_problem_spec_snapshot,
)
from cfd_sdf.stage_t_candidate_binding import (
    verify_stage_t_candidate_binding,
    write_stage_t_candidate_binding,
)


def test_candidate_binding_round_trip_binds_problem_grid_masks_and_lineage(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)

    verified = verify_stage_t_candidate_binding(
        fixture["binding"], fixture["project"]
    )

    assert verified.candidate_id == "candidate_0000"
    assert verified.canonical_grid.snapshot.grid_sha256 == fixture["grid_sha256"]
    assert verified.density_grid.cell_shape == (4, 4, 4)
    assert set(verified.density_arrays) >= {
        "rho",
        "active_design_mask",
        "forbidden_mask",
        "fixed_solid_mask",
        "root_mask",
    }
    assert verified.density_arrays["root_mask"].flags.writeable is False


def test_gradient_identity_uses_verified_candidate_artifact_hashes(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)

    identity = load_verified_gradient_problem_binding(
        fixture["binding"],
        fixture["project"],
        expected_topology_state=fixture["topology"],
    )

    assert identity["candidate_id"] == "candidate_0000"
    assert identity["canonical_grid_sha256"] == fixture["grid_sha256"]
    assert identity["baseline_topology_state_sha256"] == _sha256(fixture["topology"])
    assert identity["baseline_density_sha256"] == _sha256(fixture["density"])
    assert identity["rho_variant"] == "rho"

    with pytest.raises(ValueError, match="does not reference the suite baseline"):
        load_verified_gradient_problem_binding(
            fixture["binding"],
            fixture["project"],
            expected_topology_state=tmp_path / "different-topology.json",
        )


def test_candidate_binding_rejects_density_hash_tamper(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    density = fixture["density"]
    density.write_bytes(density.read_bytes() + b"\n")

    with pytest.raises(ValueError, match="density VTI sha256"):
        verify_stage_t_candidate_binding(fixture["binding"], fixture["project"])


def test_candidate_binding_rejects_grid_change_without_resampling(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    density = pv.read(fixture["density"])
    density.origin = (0.25, 0.0, 0.0)
    density.save(fixture["density"])

    raw = json.loads(fixture["binding"].read_text(encoding="utf-8"))
    raw["density"]["sha256"] = _sha256(fixture["density"])
    fixture["binding"].write_text(json.dumps(raw), encoding="utf-8")

    with pytest.raises(ValueError, match="Grid origin mismatch|source state resampling"):
        verify_stage_t_candidate_binding(fixture["binding"], fixture["project"])


def test_candidate_binding_rejects_mask_tamper_and_invalid_lineage(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    density = pv.read(fixture["density"])
    values = np.asarray(density.cell_data["root_mask"], dtype=np.uint8).copy()
    values[:] = 0
    density.cell_data["root_mask"] = values
    density.save(fixture["density"])

    raw = json.loads(fixture["binding"].read_text(encoding="utf-8"))
    raw["density"]["sha256"] = _sha256(fixture["density"])
    fixture["binding"].write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ValueError, match="root_mask does not match"):
        verify_stage_t_candidate_binding(fixture["binding"], fixture["project"])

    fixture = _fixture(tmp_path / "lineage")
    raw = json.loads(fixture["binding"].read_text(encoding="utf-8"))
    raw["candidate"]["iteration"] = 1
    raw["candidate"]["parent_candidate_id"] = None
    fixture["binding"].write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ValueError, match="require parent_candidate_id"):
        verify_stage_t_candidate_binding(fixture["binding"], fixture["project"])


def test_candidate_binding_rejects_out_of_range_rho_and_missing_state_lineage(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    density = pv.read(fixture["density"])
    rho = np.asarray(density.cell_data["rho"], dtype=np.float32).copy()
    rho[0] = 2.0
    density.cell_data["rho"] = rho
    density.save(fixture["density"])
    raw = json.loads(fixture["binding"].read_text(encoding="utf-8"))
    raw["density"]["sha256"] = _sha256(fixture["density"])
    fixture["binding"].write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ValueError, match="0 <= rho <= 1"):
        verify_stage_t_candidate_binding(fixture["binding"], fixture["project"])

    fixture = _fixture(tmp_path / "lineage")
    raw = json.loads(fixture["binding"].read_text(encoding="utf-8"))
    topology = fixture["topology"]
    state = json.loads(topology.read_text(encoding="utf-8"))
    del state["candidate_id"]
    topology.write_text(json.dumps(state), encoding="utf-8")
    raw["topology_state"]["sha256"] = _sha256(topology)
    fixture["binding"].write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ValueError, match="missing candidate lineage"):
        verify_stage_t_candidate_binding(fixture["binding"], fixture["project"])


def _fixture(tmp_path: Path) -> dict[str, Path | str]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    geometry = tmp_path / "geometry"
    geometry.mkdir()
    _box(geometry / "vehicle.stl", (0.25, 0.25, 0.25), (0.3, 0.3, 0.3))
    _box(geometry / "initial.stl", (0.0, 0.0, 0.0), (0.3, 0.3, 0.3))
    _box(geometry / "design.stl", (0.0, 0.0, 0.0), (3.0, 3.0, 3.0))
    _box(geometry / "forbidden.stl", (-0.25, -0.25, -0.25), (0.3, 0.3, 0.3))
    _box(geometry / "mount.stl", (0.25, 0.25, 0.25), (0.3, 0.3, 0.3))

    project = tmp_path / "project.yaml"
    project.write_text(
        yaml.safe_dump(
            {
                "schema_version": 2,
                "problem_id": "binding_fixture",
                "units": {"length": "m", "time": "s", "mass": "kg"},
                "coordinate_frame": {
                    "id": "global",
                    "origin_m": [0.0, 0.0, 0.0],
                    "basis": {
                        "x": [1.0, 0.0, 0.0],
                        "y": [0.0, 1.0, 0.0],
                        "z": [0.0, 0.0, 1.0],
                    },
                },
                "grid": {
                    "kind": "uniform_cartesian",
                    "voxel_size_m": 0.5,
                    "padding_m": 0.0,
                    "domain_bounds_m": {
                        "lower": [-1.0, -1.0, -1.0],
                        "upper": [1.0, 1.0, 1.0],
                    },
                },
                "reference_values": {
                    "area_m2": 1.0,
                    "length_m": 1.0,
                    "moment_center_m": [0.0, 0.0, 0.0],
                },
                "geometry_regions": [
                    {"id": "vehicle", "role": "fixed_solid", "file": "geometry/vehicle.stl"},
                    {"id": "initial", "role": "initial_design", "file": "geometry/initial.stl"},
                    {"id": "design", "role": "design_domain", "file": "geometry/design.stl"},
                    {"id": "forbidden", "role": "forbidden_region", "file": "geometry/forbidden.stl"},
                    {"id": "mount", "role": "root", "file": "geometry/mount.stl"},
                ],
                "flow_cases": [
                    {
                        "id": "straight",
                        "freestream_velocity_mps": [10.0, 0.0, 0.0],
                        "fluid": {
                            "model": "incompressible_newtonian",
                            "density_kg_m3": 1.0,
                            "dynamic_viscosity_pa_s": 1.0e-5,
                        },
                        "turbulence": {"model": "laminar"},
                        "boundary_conditions": {
                            "inlet": "freestream",
                            "outlet": "pressure_outlet",
                        },
                        "motion_profiles": {},
                    }
                ],
                "responses": [
                    {
                        "id": "force_x",
                        "kind": "force",
                        "flow_case_id": "straight",
                        "direction": [1.0, 0.0, 0.0],
                    }
                ],
                "objectives": [
                    {
                        "id": "objective",
                        "sense": "minimize",
                        "terms": [
                            {
                                "coefficient": 1.0,
                                "flow_case_id": "straight",
                                "response_id": "force_x",
                            }
                        ],
                    }
                ],
                "constraints": [],
                "topology_policy": {
                    "root_groups": [{"id": "mounts", "region_ids": ["mount"]}],
                    "solid_connectivity": {
                        "mode": "required_root_groups",
                        "required_root_group_ids": ["mounts"],
                        "max_components": 1,
                        "evaluate_eroded": False,
                    },
                    "void_connectivity": {
                        "mode": "disabled",
                        "required_root_group_ids": [],
                        "max_components": None,
                        "evaluate_eroded": False,
                    },
                    "minimum_solid_width_m": None,
                    "minimum_void_width_m": None,
                    "minimum_gap_m": None,
                    "erosion_radius_m": None,
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    spec = load_problem_spec(project)
    problem_snapshot = write_problem_spec_snapshot(spec, tmp_path / "problem_spec_snapshot.json")
    geometry_artifacts = build_canonical_geometry_mask_snapshot(
        spec,
        output_dir=tmp_path,
        chunk_size=16,
    )
    verified_grid = load_and_verify_canonical_grid_snapshot(
        geometry_artifacts.snapshot_path, spec
    )
    canonical = verified_grid.snapshot.grid
    grid = CartesianCellGrid(
        origin=canonical.origin,
        spacing=canonical.spacing,
        cell_shape=canonical.cell_shape,
    )
    masks = {name: values.copy() for name, values in verified_grid.masks.items()}
    allowed = np.logical_or(masks["active_design_mask"], masks["fixed_solid_mask"]).astype(np.uint8)
    rho = np.zeros(grid.cell_count, dtype=np.float32)
    rho[np.flatnonzero(masks["fixed_solid_mask"])] = 1.0
    active_indices = np.flatnonzero(masks["active_design_mask"])
    rho[active_indices[0]] = 0.75
    arrays = {
        "rho": rho,
        "rho_filtered": rho.copy(),
        "rho_projected": rho.copy(),
        "alpha": np.zeros(grid.cell_count, dtype=np.float32),
        "allowed_mask": allowed,
        "forbidden_mask": masks["forbidden_mask"],
        "fixed_solid_mask": masks["fixed_solid_mask"],
        "root_mask": masks["root_mask"],
        "active_design_mask": masks["active_design_mask"],
    }
    density = _write_cell_vti(
        grid,
        arrays,
        tmp_path / "density.vti",
        kind="fixed_grid_density",
    )
    state = {
        "schema_version": 1,
        "kind": "fixed_grid_topology_state",
        "design_variable": "rho",
        "grid": grid.to_dict(),
        "density_vti": density.name,
        "density_array": "rho",
        "problem_id": spec.problem_id,
        "problem_spec_sha256": problem_spec_sha256(spec),
        "candidate_id": "candidate_0000",
        "parent_candidate_id": None,
        "iteration": 0,
    }
    topology_state = tmp_path / "topology_state.json"
    topology_state.write_text(json.dumps(state), encoding="utf-8")
    binding = write_stage_t_candidate_binding(
        tmp_path / "stage_t_candidate_binding.json",
        problem=spec,
        problem_snapshot=problem_snapshot,
        canonical_grid_snapshot=geometry_artifacts.snapshot_path,
        canonical_geometry_manifest=geometry_artifacts.geometry_manifest_path,
        topology_state=topology_state,
        density_vti=density,
        candidate_id="candidate_0000",
    ).path
    return {
        "project": project,
        "binding": binding,
        "density": density,
        "topology": topology_state,
        "grid_sha256": verified_grid.snapshot.grid_sha256,
    }


def _box(path: Path, center: tuple[float, float, float], extents: tuple[float, float, float]) -> None:
    mesh = trimesh.creation.box(
        extents=extents,
        transform=trimesh.transformations.translation_matrix(center),
    )
    mesh.export(path)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
