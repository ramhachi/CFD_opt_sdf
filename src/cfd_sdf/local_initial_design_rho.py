"""Direct STL occupancy initialization for a localized design ``rho_raw``.

The local topology state is authoritative on its own 2 mm Cartesian grid.  A
coarse CFD ``alpha`` field is consequently never used as an initializer.  This
module instead samples the declared ``initial_design`` STL directly at a fixed
set of eight subcell locations and writes the resulting raw density as a
float64 NumPy memmap.

The sampler intentionally has no filtering or projection step.  Those are
separate, provenance-bearing transformations; this module records only the
geometric occupancy source for ``rho_raw``.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any

import numpy as np
import trimesh

from .localized_design_state_manifest import LocalizedDesignGrid


LOCAL_INITIAL_DESIGN_RHO_SCHEMA_VERSION = 1
LOCAL_INITIAL_DESIGN_RHO_KIND = "local_initial_design_rho_raw"
LOCAL_INITIAL_DESIGN_RHO_FILENAME = "local_initial_design_rho_raw.json"
LOCAL_INITIAL_DESIGN_RHO_ARRAY_FILENAME = "rho_raw.npy"
_SURFACE_TOLERANCE_M = 1.0e-9
_SAMPLE_Q = np.asarray((0.25, 0.75), dtype=np.float64)
# The ordering is part of the artifact contract.  ``qx`` is the fastest
# subcell index, followed by ``qy`` then ``qz``.
_SUBCELL_OFFSETS = np.asarray(
    [(qx, qy, qz) for qz in _SAMPLE_Q for qy in _SAMPLE_Q for qx in _SAMPLE_Q],
    dtype=np.float64,
)


@dataclass(frozen=True)
class LocalInitialDesignRhoRawManifest:
    """Portable provenance for one direct initial-design occupancy field."""

    schema_version: int
    kind: str
    stl_sha256: str
    role: str
    component_count: int
    grid_sha256: str
    active_design_mask_sha256: str
    method: str
    subcell_offsets: tuple[tuple[float, float, float], ...]
    surface_rejection_tolerance_m: float
    rho_raw_relative_path: str
    rho_raw_sha256: str
    rho_raw_dtype: str
    rho_raw_shape: tuple[int, ...]
    occupancy_volume_m3: float


@dataclass(frozen=True)
class LocalInitialDesignRhoRawArtifacts:
    """Published raw-density file and the manifest that binds its source."""

    directory: Path
    rho_raw_path: Path
    manifest_path: Path
    manifest: LocalInitialDesignRhoRawManifest


def build_local_initial_design_rho_raw(
    *,
    grid: LocalizedDesignGrid,
    active_design_mask: np.ndarray,
    initial_design_stl: str | Path,
    output_dir: str | Path,
    role: str = "initial_design",
    expected_component_count: int = 10,
    z_chunk_size: int = 1,
    point_chunk_size: int = 65_536,
) -> LocalInitialDesignRhoRawArtifacts:
    """Directly sample ``initial_design_stl`` into a local ``rho_raw`` field.

    Each cell receives the arithmetic mean of containment over the fixed
    ``2 x 2 x 2`` subcell points with coordinates
    ``lower + h * ([i, j, k] + q)``.  Only active design cells retain that
    value; every non-active cell is written as exactly ``0.0``.  The default
    ten-component requirement is the front-wing asset contract.  A smaller
    explicit expectation is available solely for compact synthetic fixtures.

    ``output_dir`` is immutable: existing output is refused, and an exception
    never leaves a partially published directory.
    """

    if not isinstance(grid, LocalizedDesignGrid):
        raise ValueError("grid must be LocalizedDesignGrid")
    if role != "initial_design":
        raise ValueError("role must be 'initial_design'")
    if (
        not isinstance(expected_component_count, int)
        or isinstance(expected_component_count, bool)
        or expected_component_count <= 0
    ):
        raise ValueError("expected_component_count must be a positive integer")
    _positive_int(z_chunk_size, "z_chunk_size")
    _positive_int(point_chunk_size, "point_chunk_size")

    active = _active_mask(active_design_mask, grid.cell_count)
    source = Path(initial_design_stl)
    components = _load_initial_design_components(source, expected_component_count)
    destination = Path(output_dir)
    if destination.exists():
        raise FileExistsError(f"refusing to overwrite existing rho_raw output: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{destination.name}.tmp-", dir=destination.parent))
    try:
        rho_path = staging / LOCAL_INITIAL_DESIGN_RHO_ARRAY_FILENAME
        occupancy_sum = _write_rho_raw(
            rho_path,
            grid=grid,
            active=active,
            components=components,
            z_chunk_size=z_chunk_size,
            point_chunk_size=point_chunk_size,
        )
        manifest = LocalInitialDesignRhoRawManifest(
            schema_version=LOCAL_INITIAL_DESIGN_RHO_SCHEMA_VERSION,
            kind=LOCAL_INITIAL_DESIGN_RHO_KIND,
            stl_sha256=_file_sha256(source),
            role=role,
            component_count=len(components),
            grid_sha256=grid.sha256,
            active_design_mask_sha256=_bool_vector_sha256(active),
            method="direct_stl_union_occupancy_2x2x2",
            subcell_offsets=tuple(tuple(float(value) for value in offset) for offset in _SUBCELL_OFFSETS),
            surface_rejection_tolerance_m=_SURFACE_TOLERANCE_M,
            rho_raw_relative_path=LOCAL_INITIAL_DESIGN_RHO_ARRAY_FILENAME,
            rho_raw_sha256=_file_sha256(rho_path),
            rho_raw_dtype=np.dtype(np.float64).name,
            rho_raw_shape=(grid.cell_count,),
            occupancy_volume_m3=float(occupancy_sum * np.prod(grid.spacing, dtype=np.float64)),
        )
        manifest_path = staging / LOCAL_INITIAL_DESIGN_RHO_FILENAME
        _write_manifest(manifest_path, manifest)
        _validate_published_artifacts(rho_path, manifest, active)
        os.replace(staging, destination)
    except Exception:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
        raise
    return LocalInitialDesignRhoRawArtifacts(
        directory=destination,
        rho_raw_path=destination / LOCAL_INITIAL_DESIGN_RHO_ARRAY_FILENAME,
        manifest_path=destination / LOCAL_INITIAL_DESIGN_RHO_FILENAME,
        manifest=manifest,
    )


def _write_rho_raw(
    path: Path,
    *,
    grid: LocalizedDesignGrid,
    active: np.ndarray,
    components: tuple[trimesh.Trimesh, ...],
    z_chunk_size: int,
    point_chunk_size: int,
) -> float:
    nx, ny, nz = grid.cell_shape
    values = np.lib.format.open_memmap(path, mode="w+", dtype=np.float64, shape=(grid.cell_count,))
    occupancy_sum = 0.0
    try:
        for z_start in range(0, nz, z_chunk_size):
            z_stop = min(z_start + z_chunk_size, nz)
            slab_start = nx * ny * z_start
            slab_stop = nx * ny * z_stop
            for cell_start in range(slab_start, slab_stop, point_chunk_size):
                cell_stop = min(cell_start + point_chunk_size, slab_stop)
                active_cells = np.flatnonzero(active[cell_start:cell_stop])
                # Never construct sample coordinates or ask STL containment
                # for non-active cells.  Fixed/root/forbidden cells do not
                # belong to the initial topology state, so even a source
                # surface crossing one cannot make this artifact ambiguous.
                written = np.zeros(cell_stop - cell_start, dtype=np.float64)
                if len(active_cells):
                    cell_indices = cell_start + active_cells
                    points = _subcell_points_for_cells(grid, cell_indices)
                    contained = _union_contains(components, points.reshape(-1, 3, order="C"))
                    occupancy = contained.reshape((len(active_cells), 8), order="C").mean(axis=1, dtype=np.float64)
                    written[active_cells] = occupancy
                values[cell_start:cell_stop] = written
                occupancy_sum += float(np.sum(written, dtype=np.float64))
        values.flush()
    finally:
        # Drop the Windows mapping before the staging directory is renamed.
        del values
    return occupancy_sum


def _subcell_points(grid: LocalizedDesignGrid, start: int, stop: int) -> np.ndarray:
    """Return fixed-order subcell points for contiguous x-fastest cells."""

    return _subcell_points_for_cells(grid, np.arange(start, stop, dtype=np.int64))


def _subcell_points_for_cells(grid: LocalizedDesignGrid, cells: np.ndarray) -> np.ndarray:
    """Return fixed-order subcell points for selected x-fastest cell labels."""

    nx, ny, _ = grid.cell_shape
    if cells.dtype != np.dtype(np.int64) or cells.ndim != 1:
        raise ValueError("cells must be a one-dimensional int64 vector")
    x = cells % nx
    yz = cells // nx
    y = yz % ny
    z = yz // ny
    indices = np.column_stack((x, y, z)).astype(np.float64, copy=False)
    lower = np.asarray(grid.origin, dtype=np.float64)
    spacing = np.asarray(grid.spacing, dtype=np.float64)
    return lower + spacing * (indices[:, np.newaxis, :] + _SUBCELL_OFFSETS[np.newaxis, :, :])


def _union_contains(components: tuple[trimesh.Trimesh, ...], points: np.ndarray) -> np.ndarray:
    """Classify points in the union, querying only each component's AABB."""

    result = np.zeros(len(points), dtype=np.bool_)
    for component in components:
        bounds = np.asarray(component.bounds, dtype=np.float64)
        candidates = np.flatnonzero(
            np.all(
                (points >= bounds[0] - _SURFACE_TOLERANCE_M)
                & (points <= bounds[1] + _SURFACE_TOLERANCE_M),
                axis=1,
            )
        )
        if len(candidates) == 0:
            continue
        candidate_points = points[candidates]
        try:
            _, distances, _ = trimesh.proximity.closest_point(component, candidate_points)
        except Exception as exc:
            raise ValueError("Unable to calculate initial_design STL surface distance") from exc
        if not np.isfinite(distances).all():
            raise ValueError("initial_design STL surface distance is non-finite")
        if np.any(distances <= _SURFACE_TOLERANCE_M):
            raise ValueError("initial_design STL occupancy is ambiguous: a sample lies on the STL surface")
        try:
            inside = component.contains(candidate_points)
        except Exception as exc:
            raise ValueError("Unable to determine initial_design STL containment") from exc
        if inside.dtype != np.dtype(np.bool_) or inside.shape != (len(candidate_points),):
            raise ValueError("initial_design STL containment returned an invalid mask")
        result[candidates] |= inside
    return result


def _load_initial_design_components(path: Path, expected_component_count: int) -> tuple[trimesh.Trimesh, ...]:
    if not path.is_file():
        raise ValueError(f"initial_design STL is missing: {path}")
    try:
        mesh = trimesh.load_mesh(path, process=True)
    except Exception as exc:
        raise ValueError(f"Unable to load initial_design STL: {path}") from exc
    if not isinstance(mesh, trimesh.Trimesh):
        raise ValueError("initial_design STL must contain one mesh, not a scene")
    if mesh.is_empty or len(mesh.vertices) == 0 or len(mesh.faces) == 0:
        raise ValueError("initial_design STL is empty")
    if not np.isfinite(np.asarray(mesh.vertices, dtype=np.float64)).all():
        raise ValueError("initial_design STL has non-finite vertices")
    # Check this before splitting.  Besides failing earlier for an invalid
    # source, it avoids trimesh's optional hole-repair path while inspecting
    # an open mesh (which can depend on an unrequired graph package).
    if not mesh.is_watertight:
        raise ValueError("initial_design STL must be watertight")
    components = tuple(mesh.split(only_watertight=False))
    if len(components) != expected_component_count:
        raise ValueError(
            "initial_design STL connected component count does not match the declared contract: "
            f"expected {expected_component_count}, got {len(components)}"
        )
    for index, component in enumerate(components):
        vertices = np.asarray(component.vertices, dtype=np.float64)
        if component.is_empty or len(vertices) == 0 or len(component.faces) == 0:
            raise ValueError(f"initial_design STL component {index} is empty")
        if not np.isfinite(vertices).all() or not np.isfinite(np.asarray(component.bounds, dtype=np.float64)).all():
            raise ValueError(f"initial_design STL component {index} has non-finite geometry")
        if not component.is_watertight:
            raise ValueError(f"initial_design STL component {index} must be watertight")
        if not component.is_volume:
            raise ValueError(
                f"initial_design STL component {index} must be consistently wound with positive volume"
            )
    _reject_supported_nested_components(components)
    return components


def _reject_supported_nested_components(components: tuple[trimesh.Trimesh, ...]) -> None:
    """Reject nested solids when their enclosure can be established robustly.

    Nested-shell parity is not an initialization semantic for the front-wing
    source.  We therefore treat separately closed solids as a union and reject
    the subset which can be proven nested: every vertex of one component is
    strictly inside another component.  This avoids incorrectly rejecting
    merely overlapping axis-aligned bounds around non-convex, disjoint parts.
    """

    for outer_index, outer in enumerate(components):
        outer_bounds = np.asarray(outer.bounds, dtype=np.float64)
        for inner_index, inner in enumerate(components):
            if outer_index == inner_index:
                continue
            inner_vertices = np.asarray(inner.vertices, dtype=np.float64)
            # Strict AABB enclosure is cheap and necessary for all inner
            # vertices to be contained.  It also keeps costly mesh queries
            # bounded to plausible nested pairs.
            if not (
                np.all(inner_vertices.min(axis=0) > outer_bounds[0] + _SURFACE_TOLERANCE_M)
                and np.all(inner_vertices.max(axis=0) < outer_bounds[1] - _SURFACE_TOLERANCE_M)
            ):
                continue
            try:
                enclosed = outer.contains(inner_vertices)
            except Exception as exc:
                raise ValueError("Unable to test initial_design STL components for unsupported nesting") from exc
            if enclosed.dtype == np.dtype(np.bool_) and bool(np.all(enclosed)):
                raise ValueError(
                    "initial_design STL has unsupported nested components: "
                    f"component {inner_index} is enclosed by component {outer_index}"
                )


def _active_mask(value: np.ndarray, cell_count: int) -> np.ndarray:
    active = np.asarray(value)
    if active.dtype != np.dtype(np.bool_) or active.ndim != 1 or active.shape != (cell_count,):
        raise ValueError(f"active_design_mask must be a bool vector with shape ({cell_count},)")
    return active


def _validate_published_artifacts(path: Path, manifest: LocalInitialDesignRhoRawManifest, active: np.ndarray) -> None:
    values = np.load(path, mmap_mode="r", allow_pickle=False)
    try:
        if values.dtype != np.dtype(np.float64) or values.shape != manifest.rho_raw_shape:
            raise ValueError("published rho_raw layout does not match manifest")
        for start in range(0, len(values), 1_048_576):
            stop = min(start + 1_048_576, len(values))
            chunk = values[start:stop]
            if not np.isfinite(chunk).all():
                raise ValueError("published rho_raw contains non-finite values")
            if np.any(chunk[~active[start:stop]] != 0.0):
                raise ValueError("published rho_raw must be exactly zero outside active_design_mask")
    finally:
        del values
    if _file_sha256(path) != manifest.rho_raw_sha256:
        raise ValueError("published rho_raw hash does not match manifest")


def _write_manifest(path: Path, manifest: LocalInitialDesignRhoRawManifest) -> None:
    raw = asdict(manifest)
    raw["subcell_offsets"] = [list(offset) for offset in manifest.subcell_offsets]
    raw["rho_raw_shape"] = list(manifest.rho_raw_shape)
    path.write_text(json.dumps(raw, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n", encoding="utf-8")


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1_048_576), b""):
            digest.update(block)
    return digest.hexdigest()


def _bool_vector_sha256(values: np.ndarray) -> str:
    # This is intentionally a logical-vector hash so an ndarray test fixture
    # and a read-only bool NPY memmap bind identically to the same mask state.
    digest = hashlib.sha256()
    for start in range(0, len(values), 1_048_576):
        digest.update(np.asarray(values[start : start + 1_048_576], dtype=np.bool_).tobytes(order="C"))
    return digest.hexdigest()


def _positive_int(value: int, label: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError(f"{label} must be a positive integer")


__all__ = [
    "LOCAL_INITIAL_DESIGN_RHO_ARRAY_FILENAME",
    "LOCAL_INITIAL_DESIGN_RHO_FILENAME",
    "LOCAL_INITIAL_DESIGN_RHO_KIND",
    "LOCAL_INITIAL_DESIGN_RHO_SCHEMA_VERSION",
    "LocalInitialDesignRhoRawArtifacts",
    "LocalInitialDesignRhoRawManifest",
    "build_local_initial_design_rho_raw",
]
