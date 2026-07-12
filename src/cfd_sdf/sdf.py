from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import trimesh

from .config import MeshRef, ProjectConfig, RootSpec
from .grid import UniformGrid, grid_from_bounds


@dataclass(frozen=True)
class FieldBundle:
    grid: UniformGrid
    arrays: dict[str, np.ndarray]
    component_labels: dict[int, str]

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "origin": self.grid.origin,
            "spacing": np.array([self.grid.spacing]),
            "shape": np.array(self.grid.shape, dtype=np.int64),
            "component_keys": np.array(list(self.component_labels.keys()), dtype=np.int64),
            "component_values": np.array(list(self.component_labels.values()), dtype=object),
        }
        payload.update({key: value for key, value in self.arrays.items()})
        np.savez_compressed(path, **payload)

    @staticmethod
    def load(path: Path) -> "FieldBundle":
        data = np.load(path, allow_pickle=True)
        grid = UniformGrid(
            origin=data["origin"].astype(float),
            spacing=float(data["spacing"][0]),
            shape=tuple(data["shape"].astype(int).tolist()),
        )
        metadata_keys = {"origin", "spacing", "shape", "component_keys", "component_values"}
        arrays = {key: data[key] for key in data.files if key not in metadata_keys}
        labels = {
            int(key): str(value)
            for key, value in zip(data["component_keys"].tolist(), data["component_values"].tolist())
        }
        return FieldBundle(grid=grid, arrays=arrays, component_labels=labels)


def build_fields(config: ProjectConfig) -> FieldBundle:
    meshes_by_role = _load_project_meshes(config)
    all_meshes = [mesh for meshes in meshes_by_role.values() for _, mesh in meshes]
    if not all_meshes:
        raise ValueError("No STL geometry was configured.")

    bounds = _combined_bounds(all_meshes)
    grid = grid_from_bounds(
        bounds=bounds,
        spacing=config.grid.voxel_size_m,
        padding=config.grid.padding_m,
        max_points=config.grid.max_points,
    )
    points = grid.points_flat()

    arrays: dict[str, np.ndarray] = {}
    labels: dict[int, str] = {}
    label_offset = 1

    for role, meshes in meshes_by_role.items():
        if not meshes:
            continue
        signed_fields = []
        unsigned_fields = []
        component_ids = []
        for label, mesh in meshes:
            phi = signed_distance(mesh, points).reshape(grid.shape)
            signed_fields.append(phi)
            unsigned_fields.append(np.abs(phi))
            labels[label_offset] = f"{role}:{label}"
            component_ids.append(label_offset)
            label_offset += 1

        stacked_signed = np.stack(signed_fields, axis=0)
        stacked_unsigned = np.stack(unsigned_fields, axis=0)
        role_phi = np.min(stacked_signed, axis=0)
        arrays[f"{role}_phi"] = role_phi.astype(np.float32)
        arrays[f"{role}_narrow_band"] = (np.abs(role_phi) <= config.grid.band_width_m).astype(np.uint8)
        arrays[f"{role}_nearest_distance"] = np.min(stacked_unsigned, axis=0).astype(np.float32)

        nearest = np.argmin(stacked_unsigned, axis=0).astype(np.int16)
        arrays[f"{role}_nearest_local_index"] = nearest
        component_id_lookup = np.array(component_ids, dtype=np.int32)
        arrays[f"{role}_nearest_component_id"] = component_id_lookup[nearest].astype(np.int32)
        arrays[f"{role}_nearest_patch_id"] = arrays[f"{role}_nearest_component_id"]
        if len(meshes) >= 2:
            partitioned = np.partition(stacked_unsigned, kth=1, axis=0)
            second_local = np.argpartition(stacked_unsigned, kth=1, axis=0)[1].astype(np.int16)
            arrays[f"{role}_second_distance"] = partitioned[1].astype(np.float32)
            arrays[f"{role}_second_nearest_component_id"] = component_id_lookup[second_local].astype(np.int32)
            arrays[f"{role}_second_nearest_patch_id"] = arrays[f"{role}_second_nearest_component_id"]
        else:
            arrays[f"{role}_second_distance"] = np.full(grid.shape, np.nan, dtype=np.float32)
            arrays[f"{role}_second_nearest_component_id"] = np.full(grid.shape, -1, dtype=np.int32)
            arrays[f"{role}_second_nearest_patch_id"] = arrays[f"{role}_second_nearest_component_id"]

    if "design_phi" in arrays:
        arrays["design_normal_x"], arrays["design_normal_y"], arrays["design_normal_z"] = _normals(
            arrays["design_phi"],
            grid.spacing,
        )

    return FieldBundle(grid=grid, arrays=arrays, component_labels=labels)


def signed_distance(mesh: trimesh.Trimesh, points: np.ndarray, chunk_size: int = 200_000) -> np.ndarray:
    values = np.empty(len(points), dtype=np.float64)
    for start in range(0, len(points), chunk_size):
        stop = min(start + chunk_size, len(points))
        chunk = points[start:stop]
        try:
            # trimesh returns positive values inside watertight meshes; this project uses phi < 0 inside.
            values[start:stop] = -trimesh.proximity.signed_distance(mesh, chunk)
        except Exception:
            closest, distance, _ = trimesh.proximity.closest_point(mesh, chunk)
            del closest
            inside = _contains_safe(mesh, chunk)
            signed = distance.astype(np.float64, copy=True)
            signed[inside] *= -1.0
            values[start:stop] = signed
    return values


def load_cache(config: ProjectConfig) -> FieldBundle:
    return FieldBundle.load(config.resolved_output_dir / "fields.npz")


def cache_path(config: ProjectConfig) -> Path:
    return config.resolved_output_dir / "fields.npz"


def _load_project_meshes(config: ProjectConfig) -> dict[str, list[tuple[str, trimesh.Trimesh]]]:
    return {
        "fixed": _load_mesh_refs(config, config.fixed_solids),
        "design": _load_mesh_refs(config, config.design_geometry),
        "allowed": _load_mesh_refs(config, config.design_domains),
        "forbidden": _load_mesh_refs(config, config.forbidden_regions),
        "root": _load_roots(config, config.roots),
    }


def _load_mesh_refs(config: ProjectConfig, refs: list[MeshRef]) -> list[tuple[str, trimesh.Trimesh]]:
    meshes = []
    for ref in refs:
        path = config.resolve(ref.file)
        if not path.exists():
            raise FileNotFoundError(f"Missing STL for {ref.id}: {path}")
        mesh = trimesh.load_mesh(path, force="mesh")
        if mesh.is_empty:
            raise ValueError(f"Empty mesh for {ref.id}: {path}")
        meshes.extend(_split_mesh(ref.id, mesh))
    return meshes


def _load_roots(config: ProjectConfig, roots: list[RootSpec]) -> list[tuple[str, trimesh.Trimesh]]:
    meshes = []
    for root in roots:
        if root.type == "stl":
            if root.file is None:
                raise ValueError(f"Root {root.id} has type=stl but no file")
            path = config.resolve(root.file)
            meshes.extend(_split_mesh(root.id, trimesh.load_mesh(path, force="mesh")))
        elif root.type == "sphere":
            if root.center_m is None or root.radius_m is None:
                raise ValueError(f"Root {root.id} sphere needs center_m and radius_m")
            mesh = trimesh.creation.icosphere(radius=root.radius_m, subdivisions=3)
            mesh.apply_translation(root.center_m)
            meshes.append((root.id, mesh))
        elif root.type == "box":
            if root.center_m is None or root.extents_m is None:
                raise ValueError(f"Root {root.id} box needs center_m and extents_m")
            mesh = trimesh.creation.box(extents=root.extents_m)
            mesh.apply_translation(root.center_m)
            meshes.append((root.id, mesh))
        else:
            raise ValueError(f"Unsupported root type for {root.id}: {root.type}")
    return meshes


def _split_mesh(label: str, mesh: trimesh.Trimesh) -> list[tuple[str, trimesh.Trimesh]]:
    parts = [part for part in mesh.split(only_watertight=False) if not part.is_empty]
    if len(parts) <= 1:
        return [(label, mesh)]
    return [(f"{label}#{index}", part) for index, part in enumerate(parts)]


def _contains_safe(mesh: trimesh.Trimesh, points: np.ndarray) -> np.ndarray:
    try:
        return mesh.contains(points)
    except Exception:
        return np.zeros(len(points), dtype=bool)


def _combined_bounds(meshes: list[trimesh.Trimesh]) -> np.ndarray:
    mins = np.array([mesh.bounds[0] for mesh in meshes])
    maxs = np.array([mesh.bounds[1] for mesh in meshes])
    return np.vstack([np.min(mins, axis=0), np.max(maxs, axis=0)])


def _normals(phi: np.ndarray, spacing: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    gx, gy, gz = np.gradient(phi.astype(np.float64), spacing, spacing, spacing, edge_order=1)
    mag = np.sqrt(gx * gx + gy * gy + gz * gz)
    mag = np.where(mag > 1.0e-12, mag, 1.0)
    return (gx / mag).astype(np.float32), (gy / mag).astype(np.float32), (gz / mag).astype(np.float32)
