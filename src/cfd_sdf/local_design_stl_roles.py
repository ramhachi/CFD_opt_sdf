"""STL-backed role containment for the localized topology design grid.

``local_design_mask_memmap`` owns streaming file publication and deliberately
does not know about geometry.  This module is the companion that turns the
declared, portable STL region contract into its z-slab callback.  It must not
be used to infer a design state from a CFD field: its only input geometry is
the native problem's declared STL regions and its only grid is the separately
declared local design grid.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
from typing import Any

import numpy as np
import trimesh

from .local_design_mask_memmap import ROLE_IDS, RoleContainment
from .problem_spec import ProblemSpec, canonical_local_design_grid, load_problem_spec


_CLASSIFIED_ROLES = frozenset(ROLE_IDS)


@dataclass(frozen=True)
class _STLRoleSource:
    region_id: str
    role: str
    relative_path: str
    resolved_relative_path: str
    path: Path
    sha256: str
    bounds: np.ndarray
    mesh: trimesh.Trimesh


class LocalDesignSTLRoleClassifier:
    """Classify local-design cell centres by declared STL role.

    Instances are callable and can be passed directly as ``role_containment``
    to :func:`build_local_design_mask_memmaps`.  The callback accepts an
    ``(N, 3)`` float array in canonical x-fastest order and returns the four
    role vectors required by that writer.  It is nevertheless independent of
    the supplied slab size: containment is re-chunked internally so results
    are deterministic for all caller chunking choices.
    """

    def __init__(
        self,
        spec: ProblemSpec,
        *,
        containment_chunk_size: int = 65_536,
    ) -> None:
        if not isinstance(spec, ProblemSpec):
            raise ValueError("spec must be ProblemSpec")
        if not isinstance(containment_chunk_size, int) or isinstance(containment_chunk_size, bool) or containment_chunk_size <= 0:
            raise ValueError("containment_chunk_size must be a positive integer")
        self._spec = spec
        self._grid = canonical_local_design_grid(spec)
        self._chunk_size = containment_chunk_size
        self._surface_tolerance = max(1.0e-12, float(min(self._grid.spacing)) * 1.0e-10)
        self._sources = _load_sources(spec)

    @property
    def grid(self) -> Any:
        """The exact ``canonical_local_design_grid`` bound to this classifier."""

        return self._grid

    @property
    def provenance_metadata(self) -> Mapping[str, Mapping[str, Any]]:
        """Immutable per-region provenance suitable for a local-state manifest.

        Paths are deliberately relative to the problem file.  Absolute paths
        are not stable provenance and would make portable artifacts host-bound.
        """

        return {
            source.region_id: {
                "role": source.role,
                "relative_source_path": source.relative_path,
                "resolved_relative_source_path": source.resolved_relative_path,
                "sha256": source.sha256,
                "bounds_m": {
                    "lower": [float(value) for value in source.bounds[0]],
                    "upper": [float(value) for value in source.bounds[1]],
                },
            }
            for source in self._sources
        }

    def __call__(self, points: np.ndarray) -> Mapping[str, np.ndarray]:
        """Return raw role containment vectors for one writer slab.

        Cells exactly on an STL surface are refused; assigning those cells to
        either side would make the topology contract depend on floating-point
        containment implementation details.
        """

        array = np.asarray(points, dtype=np.float64)
        if array.ndim != 2 or array.shape[1:] != (3,) or not np.isfinite(array).all():
            raise ValueError("points must be a finite float array with shape (N, 3)")
        roles = {role: np.zeros(len(array), dtype=np.bool_) for role in ROLE_IDS}
        for source in self._sources:
            # ``initial_design`` is deliberately source provenance only.  It
            # cannot define immutable geometry or remove/allow local DOFs.
            if source.role not in _CLASSIFIED_ROLES:
                continue
            roles[source.role] |= self._contains(source, array)
        return roles

    def as_role_containment(self) -> RoleContainment:
        """Return the explicitly typed callback accepted by the memmap writer."""

        return self

    def _contains(self, source: _STLRoleSource, points: np.ndarray) -> np.ndarray:
        result = np.zeros(len(points), dtype=np.bool_)
        lower, upper = source.bounds
        candidates = np.all(
            (points >= lower - self._surface_tolerance) & (points <= upper + self._surface_tolerance),
            axis=1,
        )
        candidate_indices = np.flatnonzero(candidates)
        for start in range(0, len(candidate_indices), self._chunk_size):
            indices = candidate_indices[start : start + self._chunk_size]
            candidate_points = points[indices]
            try:
                _, distances, _ = trimesh.proximity.closest_point(source.mesh, candidate_points)
            except Exception as exc:
                raise ValueError(
                    f"Unable to establish unambiguous containment for region {source.region_id!r}"
                ) from exc
            if np.any(~np.isfinite(distances)):
                raise ValueError(f"Containment distance is non-finite for region {source.region_id!r}")
            if np.any(distances <= self._surface_tolerance):
                raise ValueError(
                    f"Containment is ambiguous for region {source.region_id!r}: "
                    "a local-design cell centre lies on the STL surface"
                )
            try:
                contained = source.mesh.contains(candidate_points)
            except Exception as exc:
                raise ValueError(f"Containment failed for region {source.region_id!r}") from exc
            if contained.dtype != np.dtype(np.bool_) or contained.shape != (len(candidate_points),):
                raise ValueError(f"Containment returned an invalid mask for region {source.region_id!r}")
            result[indices] = contained
        return result


def local_design_stl_role_classifier(
    problem: ProblemSpec | str | Path,
    *,
    containment_chunk_size: int = 65_536,
) -> LocalDesignSTLRoleClassifier:
    """Load a portable problem and return its local-design mask callback."""

    spec = problem if isinstance(problem, ProblemSpec) else load_problem_spec(problem)
    return LocalDesignSTLRoleClassifier(spec, containment_chunk_size=containment_chunk_size)


def _load_sources(spec: ProblemSpec) -> tuple[_STLRoleSource, ...]:
    sources: list[_STLRoleSource] = []
    for region in spec.geometry_regions:
        path = (spec.base_dir / region.file).resolve()
        if not path.is_file():
            raise ValueError(f"Geometry STL is missing for region {region.id!r}: {region.file}")
        mesh = _load_closed_mesh(path, region.id)
        try:
            resolved_relative = Path(os.path.relpath(path, spec.base_dir)).as_posix()
        except ValueError as exc:  # Different drives on Windows are not portable.
            raise ValueError(f"Geometry STL for region {region.id!r} cannot be resolved relative to the problem") from exc
        sources.append(
            _STLRoleSource(
                region_id=region.id,
                role=region.role,
                relative_path=region.file.as_posix(),
                resolved_relative_path=resolved_relative,
                path=path,
                sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                bounds=np.asarray(mesh.bounds, dtype=np.float64),
                mesh=mesh,
            )
        )
    if not sources:
        raise ValueError("local-design STL role classifier requires at least one geometry region")
    return tuple(sources)


def _load_closed_mesh(path: Path, region_id: str) -> trimesh.Trimesh:
    try:
        # STL repeats vertices per triangle.  Processing merges those exact
        # duplicates before checking topology; it never repairs an open mesh.
        mesh = trimesh.load_mesh(path, process=True)
    except Exception as exc:  # Parser exceptions are backend-specific.
        raise ValueError(f"Unable to load geometry STL for region {region_id!r}: {path}") from exc
    if not isinstance(mesh, trimesh.Trimesh):
        raise ValueError(f"Geometry STL for region {region_id!r} must contain one mesh, not a scene")
    if mesh.is_empty or len(mesh.vertices) == 0 or len(mesh.faces) == 0:
        raise ValueError(f"Geometry STL for region {region_id!r} is empty")
    if not np.isfinite(mesh.vertices).all():
        raise ValueError(f"Geometry STL for region {region_id!r} has non-finite vertices")
    if not mesh.is_watertight:
        raise ValueError(f"Geometry STL for region {region_id!r} must be watertight")
    if not mesh.is_volume:
        raise ValueError(
            f"Geometry STL for region {region_id!r} must be consistently wound with positive volume"
        )
    return mesh


__all__ = [
    "LocalDesignSTLRoleClassifier",
    "local_design_stl_role_classifier",
]
