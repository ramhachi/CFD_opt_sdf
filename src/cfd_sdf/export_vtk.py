from __future__ import annotations

from pathlib import Path

import numpy as np
import pyvista as pv

from .sdf import FieldBundle


def export_vti(bundle: FieldBundle, output_dir: Path, extra_arrays: dict[str, np.ndarray] | None = None) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    grid = _image_data(bundle)
    arrays = dict(bundle.arrays)
    if extra_arrays:
        arrays.update(extra_arrays)

    for name, values in arrays.items():
        if values.shape == bundle.grid.shape:
            grid.point_data[name] = np.ascontiguousarray(values.ravel(order="F"))

    path = output_dir / "sdf_fields.vti"
    grid.save(path)
    return [path]


def export_zero_surface(bundle: FieldBundle, output_dir: Path, field_name: str = "design_phi") -> Path | None:
    if field_name not in bundle.arrays:
        return None
    output_dir.mkdir(parents=True, exist_ok=True)
    grid = _image_data(bundle)
    grid.point_data[field_name] = np.ascontiguousarray(bundle.arrays[field_name].ravel(order="F"))
    surface = grid.contour(isosurfaces=[0.0], scalars=field_name)
    path = output_dir / "zero_surface.ply"
    surface.save(path)
    return path


def _image_data(bundle: FieldBundle) -> pv.ImageData:
    grid = pv.ImageData()
    grid.dimensions = bundle.grid.shape
    grid.origin = tuple(bundle.grid.origin.tolist())
    grid.spacing = (bundle.grid.spacing, bundle.grid.spacing, bundle.grid.spacing)
    return grid
