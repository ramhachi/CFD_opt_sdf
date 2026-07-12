from __future__ import annotations

from pathlib import Path

import numpy as np
import trimesh

from .parametric import build_parametric_front_wing, default_parameters


def write_front_wing_demo_geometry(output_dir: Path) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    meshes: dict[str, trimesh.Trimesh] = {
        "vehicle_nose.stl": _box((0.0, 0.0, 0.45), (0.65, 0.55, 0.35)),
        "front_wing_initial.stl": _front_wing(),
        "tire_fl.stl": _tire((0.15, 0.95, 0.30)),
        "tire_fr.stl": _tire((0.15, -0.95, 0.30)),
        "ground.stl": _box((0.45, 0.0, -0.035), (2.8, 2.2, 0.05)),
        "allowed_front_box.stl": _box((0.82, 0.0, 0.22), (1.15, 1.45, 0.42)),
        "forbidden_tire_clearance.stl": _clearance_zones(),
        "root_mount_left.stl": _box((0.52, 0.32, 0.27), (0.16, 0.10, 0.18)),
        "root_mount_right.stl": _box((0.52, -0.32, 0.27), (0.16, 0.10, 0.18)),
    }
    written = []
    for name, mesh in meshes.items():
        path = output_dir / name
        mesh.export(path)
        written.append(path)
    return written


def _front_wing() -> trimesh.Trimesh:
    return build_parametric_front_wing(default_parameters())


def _tire(center: tuple[float, float, float]) -> trimesh.Trimesh:
    tire = trimesh.creation.cylinder(radius=0.26, height=0.22, sections=48)
    # Cylinder axis starts on z; rotate it so the wheel axle is lateral (y).
    tire.apply_transform(trimesh.transformations.rotation_matrix(np.pi / 2.0, [1.0, 0.0, 0.0]))
    tire.apply_translation(center)
    return tire


def _clearance_zones() -> trimesh.Trimesh:
    left = _box((0.15, 0.95, 0.30), (0.62, 0.42, 0.62))
    right = _box((0.15, -0.95, 0.30), (0.62, 0.42, 0.62))
    return trimesh.util.concatenate([left, right])


def _box(center: tuple[float, float, float], extents: tuple[float, float, float]) -> trimesh.Trimesh:
    mesh = trimesh.creation.box(extents=extents)
    mesh.apply_translation(center)
    return mesh
