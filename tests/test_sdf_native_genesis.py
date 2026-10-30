"""Contract tests for SDF genesis from a registered handoff directory."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import numpy as np
import pyvista as pv
import pytest

from cfd_sdf.design.genesis import (
    GENESIS_MASK_PROJECTION_POLICY,
    GenesisError,
    persist_genesis_report,
    sdf_state_from_handoff,
)

CELL_SHAPE = (6, 7, 5)
SPACING = 0.05
ORIGIN = (-0.2, -0.1, 0.05)


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_path(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _sphere_sdf(point_shape, origin, spacing, radius=0.12):
    center = np.array(
        [
            origin[i] + spacing * (point_shape[i] - 1) / 2.0
            for i in range(3)
        ]
    )
    xs = origin[0] + spacing * np.arange(point_shape[0], dtype=np.float64)
    ys = origin[1] + spacing * np.arange(point_shape[1], dtype=np.float64)
    zs = origin[2] + spacing * np.arange(point_shape[2], dtype=np.float64)
    x, y, z = np.meshgrid(xs, ys, zs, indexing="ij")
    return np.sqrt((x - center[0]) ** 2 + (y - center[1]) ** 2 + (z - center[2]) ** 2) - radius


def _build_handoff(
    directory: Path,
    *,
    cell_shape=CELL_SHAPE,
    origin=ORIGIN,
    spacing=SPACING,
    sphere_radius=0.12,
    allowed_mode: str = "all",
    status: str = "diagnostic_only",
    material_bias: np.ndarray | None = None,
) -> tuple[Path, dict]:
    directory.mkdir(parents=True, exist_ok=True)
    point_shape = tuple(value + 1 for value in cell_shape)
    sdf_points = _sphere_sdf(point_shape, origin, spacing, sphere_radius).astype(np.float32)
    cell_centers = [
        origin[index] + spacing * (np.arange(cell_shape[index], dtype=np.float64) + 0.5)
        for index in range(3)
    ]
    cx, cy, cz = np.meshgrid(*cell_centers, indexing="ij")
    radius_at_cells = np.sqrt(
        (cx - (origin[0] + spacing * cell_shape[0] / 2.0)) ** 2
        + (cy - (origin[1] + spacing * cell_shape[1] / 2.0)) ** 2
        + (cz - (origin[2] + spacing * cell_shape[2] / 2.0)) ** 2
    )
    rho = (radius_at_cells < sphere_radius).astype(np.float64)
    if material_bias is not None:
        rho = rho + material_bias
        rho = np.clip(rho, 0.0, 1.0)

    if allowed_mode == "all":
        allowed = np.ones(cell_shape, dtype=np.uint8)
    elif allowed_mode == "slab":
        # mutable cells exclude the single outermost cell layer in every
        # direction, which freezes the outer node layer pairs
        allowed = np.ones(cell_shape, dtype=np.uint8)
        allowed[0, :, :] = 0
        allowed[-1, :, :] = 0
        allowed[:, 0, :] = 0
        allowed[:, -1, :] = 0
        allowed[:, :, 0] = 0
        allowed[:, :, -1] = 0
    else:  # pragma: no cover - developer guard
        raise ValueError(allowed_mode)
    empty = np.zeros(cell_shape, dtype=np.uint8)
    masks = {
        "allowed_mask": allowed,
        "active_design_mask": allowed.copy(),
        "forbidden_mask": empty.copy(),
        "fixed_solid_mask": empty.copy(),
        "root_mask": empty.copy(),
    }

    density = pv.ImageData(
        dimensions=point_shape, spacing=(spacing, spacing, spacing), origin=origin
    )
    density.cell_data["rho_projection"] = rho.ravel(order="F").astype(np.float32)
    for name, values in masks.items():
        density.cell_data[name] = values.ravel(order="F")
    density.field_data["schema_version"] = np.array([1], dtype=np.int32)
    density.field_data["kind"] = np.array(["fixed_grid_density"])
    density.field_data["cell_order"] = np.array(["vtk-x-fastest"])
    density_path = directory / "source_density.vti"
    density.save(density_path)

    sdf = pv.ImageData(
        dimensions=point_shape, spacing=(spacing, spacing, spacing), origin=origin
    )
    sdf.point_data["sdf"] = sdf_points.ravel(order="F")
    sdf.point_data["rho_projection"] = sdf_points.astype(np.float64).ravel(order="F")
    grid_sha = "f" * 64
    sdf.field_data["schema_version"] = np.array([1], dtype=np.int32)
    sdf.field_data["kind"] = np.array(["stage_s_signed_distance"])
    sdf.field_data["sdf_sign_convention"] = np.array(["negative_inside_positive_outside"])
    sdf.field_data["rho_variant"] = np.array(["rho_projection"])
    sdf.field_data["iso_value"] = np.array([0.5], dtype=np.float64)
    sdf.field_data["grid_sha256"] = np.array([grid_sha])
    sdf_path = directory / "signed_distance.vti"
    sdf.save(sdf_path)

    topology_state = {
        "schema_version": 1,
        "kind": "fixed_grid_topology_state",
        "design_variable": "rho",
        "grid": {
            "location": "cell",
            "cell_order": "vtk-x-fastest",
            "origin": [float(value) for value in origin],
            "spacing": [float(spacing)] * 3,
            "cell_shape": [int(value) for value in cell_shape],
            "point_dimensions": [int(value) for value in point_shape],
            "cell_count": int(np.prod(cell_shape)),
            "sha256": grid_sha,
        },
    }
    topology_path = directory / "source_topology_state.json"
    topology_path.write_text(json.dumps(topology_state))

    surface_path = directory / "surface.stl"
    surface_path.write_bytes(b"solid synthetic\nendsolid synthetic\n")

    artifacts = {
        "sdf_vti": {"path": sdf_path.name, "sha256": _sha256_path(sdf_path)},
        "source_density_vti": {
            "path": density_path.name,
            "sha256": _sha256_path(density_path),
        },
        "surface_stl": {"path": surface_path.name, "sha256": _sha256_path(surface_path)},
        "source_topology_state": {
            "path": topology_path.name,
            "sha256": _sha256_path(topology_path),
        },
    }
    manifest = {
        "schema_version": 1,
        "kind": "stage_t_to_stage_s_handoff",
        "ok": True,
        "status": status,
        "artifacts": artifacts,
        "rho": {"variant": "rho_projection", "iso_value": 0.5},
    }
    manifest_path = directory / "handoff_manifest.json"
    manifest_path.write_text(json.dumps(manifest))
    return manifest_path, manifest


def test_genesis_is_deterministic_and_roundtrips(tmp_path):
    manifest_a, _ = _build_handoff(tmp_path / "a")
    manifest_b, _ = _build_handoff(tmp_path / "b")
    result_a = sdf_state_from_handoff(manifest_a, persist=False)
    result_b = sdf_state_from_handoff(manifest_b, persist=False)
    assert result_a.state.state_sha256 == result_b.state.state_sha256
    assert result_a.state.phi_sha256() == result_b.state.phi_sha256()

    persisted = sdf_state_from_handoff(manifest_a, output_dir=tmp_path / "a" / "out")
    loaded = type(persisted.state).load(persisted.state_path)
    assert loaded.state_sha256 == persisted.state.state_sha256
    assert np.array_equal(loaded.phi, persisted.state.phi)


def test_genesis_sign_convention_and_material_agreement(tmp_path):
    manifest, _ = _build_handoff(tmp_path / "sign")
    result = sdf_state_from_handoff(manifest, persist=False)
    state = result.state
    assert state.sign_convention == "negative_inside"
    assert state.shape == tuple(value + 1 for value in CELL_SHAPE)
    assert state.solid_mask.sum() > 0 and state.fluid_mask.sum() > 0
    assert np.array_equal(state.solid_mask, state.phi < 0.0)
    counts = result.report["material_diagnostics"]
    assert counts["phi_negative_point_count"] == int((state.phi < 0).sum())
    assert result.report["state_phi_sha256"] == state.phi_sha256()


def test_genesis_mask_projection_policy(tmp_path):
    manifest, _ = _build_handoff(tmp_path / "masks")
    result = sdf_state_from_handoff(manifest, persist=False)
    state = result.state
    # With every cell mutable, a point may move exactly when it has a full
    # 2x2x2 neighbourhood: the outermost node layer is frozen.
    interior = np.ones(state.shape, dtype=np.bool_)
    interior[0] = False
    interior[-1] = False
    interior[:, 0] = False
    interior[:, -1] = False
    interior[:, :, 0] = False
    interior[:, :, -1] = False
    assert np.array_equal(state.design_mask, interior)
    assert GENESIS_MASK_PROJECTION_POLICY == "v16_handoff_mask_projection_v1"


def _build_handoff_restricted(directory: Path) -> Path:
    """Handoff whose mutable cells stop one cell short of every outer layer."""

    manifest, manifest_doc = _build_handoff(
        directory, allowed_mode="slab", sphere_radius=0.06
    )
    density = pv.read(directory / "source_density.vti")
    allowed = (
        np.asarray(density.cell_data["allowed_mask"])
        .astype(bool)
        .reshape(CELL_SHAPE, order="F")
    )
    density.cell_data["active_design_mask"] = allowed.ravel(order="F")
    density.save(directory / "source_density.vti")
    manifest_doc["artifacts"]["source_density_vti"]["sha256"] = _sha256_path(
        directory / "source_density.vti"
    )
    (directory / "handoff_manifest.json").write_text(json.dumps(manifest_doc))
    return manifest


def test_restricted_active_region_freezes_boundary_nodes(tmp_path):
    manifest = _build_handoff_restricted(tmp_path / "restricted")
    result = sdf_state_from_handoff(manifest, persist=False)
    state = result.state
    # strict projection: a design node must have all eight adjacent cells in
    # the mutable region, and every node touching a non-mutable cell is frozen
    density = pv.read(tmp_path / "restricted" / "source_density.vti")
    active = (
        np.asarray(density.cell_data["active_design_mask"])
        .astype(bool)
        .reshape(CELL_SHAPE, order="F")
    )
    padded = np.pad(active, ((1, 1), (1, 1), (1, 1)))
    sx, sy, sz = CELL_SHAPE
    expected_all = np.ones(state.shape, dtype=bool)
    for di in (0, 1):
        for dj in (0, 1):
            for dk in (0, 1):
                expected_all &= padded[di : di + sx + 1, dj : dj + sy + 1, dk : dk + sz + 1]
    expected_all[0] = False
    expected_all[-1] = False
    expected_all[:, 0] = False
    expected_all[:, -1] = False
    expected_all[:, :, 0] = False
    expected_all[:, :, -1] = False
    assert np.array_equal(state.design_mask, expected_all)
    # nodes on the outer boundary of the mutable region are frozen
    assert not state.design_mask[0].any() and not state.design_mask[-1].any()
    assert result.report["mask_cell_counts"]["active_design"] == int(active.sum())


def test_any_adjacent_projection_for_readonly_masks(tmp_path):
    manifest = _build_handoff_forbidden_edge(tmp_path / "forbidden")
    result = sdf_state_from_handoff(manifest, persist=False)
    state = result.state
    # any point touching a forbidden cell must be projected into the
    # forbidden point mask (over-complete, conservative)
    assert _forbidden_points_covered(tmp_path / "forbidden", state)


def _build_handoff_forbidden_edge(directory: Path) -> Path:
    manifest, manifest_doc = _build_handoff(directory)
    density = pv.read(directory / "source_density.vti")
    allowed = np.asarray(density.cell_data["allowed_mask"]).astype(bool).reshape(
        CELL_SHAPE, order="F"
    )
    active = allowed.copy()
    # forbid one far corner cell for which the allowed mask is lifted
    allowed[-1, 0, 0] = False
    active[-1, 0, 0] = False
    forbidden = np.zeros(CELL_SHAPE, dtype=np.uint8)
    forbidden[-1, 0, 0] = 1
    density.cell_data["allowed_mask"] = allowed.ravel(order="F")
    density.cell_data["active_design_mask"] = active.ravel(order="F")
    density.cell_data["forbidden_mask"] = forbidden.ravel(order="F")
    density.save(directory / "source_density.vti")
    manifest_doc["artifacts"]["source_density_vti"]["sha256"] = _sha256_path(
        directory / "source_density.vti"
    )
    (directory / "handoff_manifest.json").write_text(json.dumps(manifest_doc))
    return manifest


def _forbidden_points_covered(directory: Path, state) -> bool:
    density = pv.read(directory / "source_density.vti")
    forbidden = (
        np.asarray(density.cell_data["forbidden_mask"])
        .astype(bool)
        .reshape(CELL_SHAPE, order="F")
    )
    padded = np.pad(forbidden, ((1, 1), (1, 1), (1, 1)))
    projected = np.zeros(state.shape, dtype=bool)
    for di in (0, 1):
        for dj in (0, 1):
            for dk in (0, 1):
                projected |= padded[di : di + state.shape[0], dj : dj + state.shape[1], dk : dk + state.shape[2]]
    return np.array_equal(state.forbidden_mask, projected)


def test_genesis_fails_closed_on_artifact_hash_mismatch(tmp_path):
    manifest, manifest_doc = _build_handoff(tmp_path / "tamper")
    stl_path = tmp_path / "tamper" / "surface.stl"
    stl_path.write_bytes(stl_path.read_bytes() + b" ")
    with pytest.raises(GenesisError, match="surface_stl"):
        sdf_state_from_handoff(manifest, persist=False)


def test_genesis_fails_closed_when_fixed_solid_not_retained(tmp_path):
    manifest, manifest_doc = _build_handoff(tmp_path / "fixed")
    density = pv.read(tmp_path / "fixed" / "source_density.vti")
    # mark a void cell far from the sphere as fixed solid: the material rule
    # material_inside_allowed_or_fixed holds (allowed is all-true), but the
    # fixed_solid_retained rule fails because that cell carries no material
    fixed = np.zeros(CELL_SHAPE, dtype=np.uint8)
    fixed[0, 0, 0] = 1
    density.cell_data["fixed_solid_mask"] = fixed.ravel(order="F")
    density.save(tmp_path / "fixed" / "source_density.vti")
    manifest_doc["artifacts"]["source_density_vti"]["sha256"] = _sha256_path(
        tmp_path / "fixed" / "source_density.vti"
    )
    (tmp_path / "fixed" / "handoff_manifest.json").write_text(json.dumps(manifest_doc))
    with pytest.raises(GenesisError, match="fixed_solid_retained"):
        sdf_state_from_handoff(manifest, persist=False)


def test_genesis_fails_closed_when_material_leaves_allowed(tmp_path):
    manifest, manifest_doc = _build_handoff(tmp_path / "escape", allowed_mode="slab")
    with pytest.raises(GenesisError, match="material_inside_allowed_or_fixed"):
        sdf_state_from_handoff(manifest, persist=False)


def test_genesis_fails_closed_on_wrong_expected_surface_hash(tmp_path):
    manifest, _ = _build_handoff(tmp_path / "expect")
    with pytest.raises(GenesisError, match="surface hash mismatch"):
        sdf_state_from_handoff(
            manifest,
            persist=False,
            expected_surface_sha256="0" * 64,
        )


def test_genesis_fails_closed_on_unregistered_status(tmp_path):
    manifest, _ = _build_handoff(tmp_path / "status", status="registered")
    with pytest.raises(GenesisError, match="status"):
        sdf_state_from_handoff(manifest, persist=False)


def test_genesis_fails_closed_when_sdf_has_single_sign(tmp_path):
    manifest, _ = _build_handoff(tmp_path / "signs", sphere_radius=10.0)
    with pytest.raises(GenesisError, match="both solid and fluid"):
        sdf_state_from_handoff(manifest, persist=False)


def test_genesis_report_is_written_for_persisted_states(tmp_path):
    manifest, _ = _build_handoff(tmp_path / "report")
    result = sdf_state_from_handoff(manifest, output_dir=tmp_path / "report" / "out")
    report_path = persist_genesis_report(result, output_dir=tmp_path / "report" / "out")
    document = json.loads(report_path.read_text())
    assert document["state_sha256"] == result.state.state_sha256
    assert document["kind"] == "sdf_native_genesis"
    assert result.report["flags"]["shape_update_allowed"] is False
