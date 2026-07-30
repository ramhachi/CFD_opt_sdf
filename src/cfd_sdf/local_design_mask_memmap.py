"""Streaming construction of local-design role masks.

This module deliberately knows nothing about STL files.  A caller provides
either already-classified role masks or a containment callback and this module
only owns the bounded-memory, canonical-order and atomic-publication contract.
The callback is invoked once per contiguous z slab with x-fastest cell centres.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any

import numpy as np


ROLE_IDS = ("design_domain", "forbidden_region", "fixed_solid", "root")
MASK_IDS = ("active_design_mask", "forbidden_mask", "fixed_solid_mask", "root_mask")
RoleContainment = Callable[[np.ndarray], Mapping[str, np.ndarray]]


@dataclass(frozen=True)
class LocalDesignMaskMemmapArtifacts:
    """Atomically published local mask files and their deterministic counts."""

    directory: Path
    paths: Mapping[str, Path]
    true_counts: Mapping[str, int]


def build_local_design_mask_memmaps(
    grid: Any,
    *,
    output_dir: str | Path,
    role_masks: Mapping[str, np.ndarray | Sequence[bool]] | None = None,
    role_containment: RoleContainment | None = None,
    z_chunk_size: int = 1,
    require_active: bool = True,
    require_root: bool = False,
) -> LocalDesignMaskMemmapArtifacts:
    """Write derived bool mask vectors in bounded z slabs and publish atomically.

    Exactly one of ``role_masks`` and ``role_containment`` is accepted.  Role
    masks and callback results must contain the four boolean role vectors in
    ``ROLE_IDS``.  Output is refused when ``output_dir`` already exists: a
    previously published mask snapshot is immutable rather than overwritten.
    """

    shape, origin, spacing = _grid_contract(grid)
    nx, ny, nz = shape
    cell_count = int(nx * ny * nz)
    if not isinstance(z_chunk_size, int) or isinstance(z_chunk_size, bool) or z_chunk_size <= 0:
        raise ValueError("z_chunk_size must be a positive integer")
    if (role_masks is None) == (role_containment is None):
        raise ValueError("provide exactly one of role_masks or role_containment")
    if role_containment is not None and not callable(role_containment):
        raise ValueError("role_containment must be callable")

    prepared_roles = None
    if role_masks is not None:
        prepared_roles = _role_masks(role_masks, cell_count, "role_masks")

    destination = Path(output_dir)
    if destination.exists():
        raise FileExistsError(f"refusing to overwrite existing local mask output: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{destination.name}.tmp-", dir=destination.parent))
    paths = {mask_id: staging / f"{mask_id}.npy" for mask_id in MASK_IDS}
    writers: dict[str, np.memmap] = {}
    counts = {mask_id: 0 for mask_id in MASK_IDS}
    try:
        writers = {
            mask_id: np.lib.format.open_memmap(path, mode="w+", dtype=np.bool_, shape=(cell_count,))
            for mask_id, path in paths.items()
        }
        for z_start in range(0, nz, z_chunk_size):
            z_stop = min(z_start + z_chunk_size, nz)
            start = nx * ny * z_start
            stop = nx * ny * z_stop
            if prepared_roles is None:
                points = _cell_centres(shape, origin, spacing, z_start, z_stop)
                roles = _role_masks(role_containment(points), stop - start, "role_containment result")
            else:
                roles = {role: values[start:stop] for role, values in prepared_roles.items()}
            derived = _derive(roles, offset=start)
            for mask_id, values in derived.items():
                writers[mask_id][start:stop] = values
                counts[mask_id] += int(np.count_nonzero(values))
        for writer in writers.values():
            writer.flush()
        del writer
        # Drop every Windows mmap handle before renaming the containing directory.
        writers.clear()
        if require_active and counts["active_design_mask"] == 0:
            raise ValueError("active_design_mask is empty after forbidden/fixed exclusions")
        if require_root and counts["root_mask"] == 0:
            raise ValueError("root_mask is empty although it is required")
        if destination.exists():
            raise FileExistsError(f"refusing to overwrite existing local mask output: {destination}")
        os.replace(staging, destination)
    except Exception:
        writers.clear()
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
        raise

    published_paths = {mask_id: destination / path.name for mask_id, path in paths.items()}
    return LocalDesignMaskMemmapArtifacts(
        directory=destination,
        paths=published_paths,
        true_counts=dict(counts),
    )


def _derive(roles: Mapping[str, np.ndarray], *, offset: int) -> dict[str, np.ndarray]:
    design = roles["design_domain"]
    raw_forbidden = roles["forbidden_region"]
    fixed = roles["fixed_solid"]
    root = roles["root"]
    outside_fixed = root & ~fixed
    if np.any(outside_fixed):
        raise ValueError(
            "root_mask must be contained within fixed_solid_mask; "
            f"first_cell={offset + int(np.flatnonzero(outside_fixed)[0])}"
        )
    return {
        "active_design_mask": design & ~raw_forbidden & ~fixed,
        "forbidden_mask": raw_forbidden & ~fixed,
        "fixed_solid_mask": fixed,
        "root_mask": root,
    }


def _role_masks(value: Mapping[str, Any], count: int, label: str) -> dict[str, np.ndarray]:
    if not isinstance(value, Mapping) or set(value) != set(ROLE_IDS):
        raise ValueError(f"{label} must contain exactly {ROLE_IDS!r}")
    result: dict[str, np.ndarray] = {}
    for role in ROLE_IDS:
        array = np.asarray(value[role])
        if array.dtype != np.dtype(np.bool_) or array.ndim != 1 or array.shape != (count,):
            raise ValueError(f"{label}.{role} must be a bool vector with shape ({count},)")
        result[role] = array
    return result


def _grid_contract(grid: Any) -> tuple[tuple[int, int, int], np.ndarray, np.ndarray]:
    if getattr(grid, "cell_order", None) != "x-fastest":
        raise ValueError("grid.cell_order must be 'x-fastest'")
    shape = tuple(getattr(grid, "cell_shape", ()))
    if len(shape) != 3 or any(not isinstance(value, (int, np.integer)) or value <= 0 for value in shape):
        raise ValueError("grid.cell_shape must contain three positive integers")
    origin = np.asarray(getattr(grid, "origin", ()), dtype=np.float64)
    spacing = np.asarray(getattr(grid, "spacing", ()), dtype=np.float64)
    if origin.shape != (3,) or spacing.shape != (3,) or not np.isfinite(origin).all() or not np.isfinite(spacing).all() or np.any(spacing <= 0.0):
        raise ValueError("grid origin and spacing must contain three finite values; spacing must be positive")
    return tuple(int(value) for value in shape), origin, spacing


def _cell_centres(
    shape: tuple[int, int, int], origin: np.ndarray, spacing: np.ndarray, z_start: int, z_stop: int
) -> np.ndarray:
    nx, ny, _ = shape
    indices = np.arange(nx * ny * z_start, nx * ny * z_stop, dtype=np.int64)
    x = indices % nx
    yz = indices // nx
    y = yz % ny
    z = yz // ny
    return origin + (np.column_stack((x, y, z)).astype(np.float64, copy=False) + 0.5) * spacing


__all__ = [
    "LocalDesignMaskMemmapArtifacts",
    "MASK_IDS",
    "ROLE_IDS",
    "build_local_design_mask_memmaps",
]
