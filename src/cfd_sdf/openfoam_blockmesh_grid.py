"""Fail-closed reconstruction of a uniform Cartesian grid from ``blockMeshDict``.

Only a single, ungraded, axis-aligned hexahedral block is accepted.  The
resulting cell order is explicitly the repository-wide ``x-fastest`` order;
arbitrary polyhedral, rotated, multi-block, and graded meshes require a
separately qualified mapping and are intentionally outside this reader.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from math import isfinite
from pathlib import Path
import re

import numpy as np

from .openfoam_grid_transfer import CANONICAL_CELL_ORDER, UniformCartesianCellGrid


_NUMBER = r"[-+]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][-+]?[0-9]+)?"
_VECTOR_RE = re.compile(rf"\(\s*({_NUMBER})\s+({_NUMBER})\s+({_NUMBER})\s*\)")
_BLOCK_RE = re.compile(
    rf"^\s*hex\s*\(\s*([0-9\s]+?)\s*\)\s*"
    rf"\(\s*([0-9]+)\s+([0-9]+)\s+([0-9]+)\s*\)\s*"
    rf"simpleGrading\s*\(\s*({_NUMBER})\s+({_NUMBER})\s+({_NUMBER})\s*\)\s*;?\s*$",
    re.DOTALL,
)
_SCALE_RE = re.compile(rf"\bscale\s+({_NUMBER})\s*;")
_EXPECTED_HEX_CORNERS = (
    (0, 0, 0),
    (1, 0, 0),
    (1, 1, 0),
    (0, 1, 0),
    (0, 0, 1),
    (1, 0, 1),
    (1, 1, 1),
    (0, 1, 1),
)


@dataclass(frozen=True)
class OpenFoamBlockMeshGrid:
    """Canonical grid plus immutable source-dictionary provenance."""

    path: Path
    grid: UniformCartesianCellGrid
    block_mesh_sha256: str
    scale: float

    @property
    def lower(self) -> tuple[float, float, float]:
        return self.grid.origin

    @property
    def spacing(self) -> tuple[float, float, float]:
        return self.grid.spacing

    @property
    def cell_shape(self) -> tuple[int, int, int]:
        return self.grid.cell_shape

    @property
    def grid_sha256(self) -> str:
        return self.grid.sha256

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": "openfoam_blockmesh_uniform_cartesian_grid",
            "path": str(self.path),
            "block_mesh_sha256": self.block_mesh_sha256,
            "scale": self.scale,
            "lower": list(self.lower),
            "spacing": list(self.spacing),
            "cell_shape": list(self.cell_shape),
            "cell_order": CANONICAL_CELL_ORDER,
            "grid_sha256": self.grid_sha256,
        }


def read_openfoam_blockmesh_uniform_cartesian_grid(
    path: str | Path,
) -> OpenFoamBlockMeshGrid:
    """Read one axis-aligned uniform ``hex`` block or refuse the dictionary."""

    source_path = Path(path).resolve()
    payload = source_path.read_bytes()
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"blockMeshDict must be UTF-8 text: {source_path}") from exc
    dictionary = _strip_comments(text)
    scale = _parse_scale(dictionary)
    vertices = _parse_vertices(dictionary)
    indices, cell_shape = _parse_single_uniform_hex(dictionary, vertex_count=len(vertices))
    _reject_curved_edges(dictionary)
    lower, upper = _axis_aligned_hex_bounds(vertices, indices)
    extents = upper - lower
    if not np.isfinite(extents).all() or np.any(extents <= 0.0):
        raise ValueError("blockMesh hex must have positive finite extents")
    spacing = extents * scale / np.asarray(cell_shape, dtype=np.float64)
    if not np.isfinite(spacing).all() or np.any(spacing <= 0.0):
        raise ValueError("blockMesh scale produces non-positive or non-finite spacing")
    grid = UniformCartesianCellGrid(
        origin=tuple(float(value * scale) for value in lower),
        spacing=tuple(float(value) for value in spacing),
        cell_shape=cell_shape,
        cell_order=CANONICAL_CELL_ORDER,
    )
    return OpenFoamBlockMeshGrid(
        path=source_path,
        grid=grid,
        block_mesh_sha256=hashlib.sha256(payload).hexdigest(),
        scale=scale,
    )


def _parse_scale(dictionary: str) -> float:
    matches = _SCALE_RE.findall(dictionary)
    if len(matches) != 1:
        raise ValueError("blockMeshDict must declare exactly one scalar scale entry")
    scale = float(matches[0])
    if not isfinite(scale) or scale <= 0.0:
        raise ValueError("blockMeshDict scale must be positive and finite")
    return scale


def _parse_vertices(dictionary: str) -> np.ndarray:
    body = _parenthesized_entry(dictionary, "vertices")
    matches = list(_VECTOR_RE.finditer(body))
    residue = _VECTOR_RE.sub("", body).strip()
    if residue or len(matches) != 8:
        raise ValueError("only one hex block with exactly eight vertex vectors is supported")
    values = np.asarray([[float(value) for value in match.groups()] for match in matches], dtype=np.float64)
    if not np.isfinite(values).all():
        raise ValueError("blockMesh vertices must be finite")
    if len(np.unique(values, axis=0)) != 8:
        raise ValueError("blockMesh hex must have eight distinct vertices")
    return values


def _parse_single_uniform_hex(dictionary: str, *, vertex_count: int) -> tuple[tuple[int, ...], tuple[int, int, int]]:
    body = _parenthesized_entry(dictionary, "blocks")
    match = _BLOCK_RE.fullmatch(body)
    if match is None:
        raise ValueError(
            "only one hex block with simpleGrading (1 1 1) is supported; "
            "multi-block, non-hex, and graded meshes are refused"
        )
    indices = tuple(int(value) for value in match.group(1).split())
    if len(indices) != 8 or len(set(indices)) != 8 or set(indices) != set(range(vertex_count)):
        raise ValueError("hex must reference each of the eight vertices exactly once")
    cell_shape = tuple(int(match.group(index)) for index in (2, 3, 4))
    if any(value <= 0 for value in cell_shape):
        raise ValueError("hex cell counts must be positive")
    grading = tuple(float(match.group(index)) for index in (5, 6, 7))
    if not all(isfinite(value) and value == 1.0 for value in grading):
        raise ValueError("only simpleGrading (1 1 1) is supported")
    return indices, cell_shape


def _reject_curved_edges(dictionary: str) -> None:
    body = _parenthesized_entry(dictionary, "edges")
    if body.strip():
        raise ValueError("blockMesh curved edges are not supported by the uniform Cartesian reader")


def _axis_aligned_hex_bounds(vertices: np.ndarray, indices: tuple[int, ...]) -> tuple[np.ndarray, np.ndarray]:
    ordered = vertices[np.asarray(indices, dtype=np.int64)]
    lower = np.min(ordered, axis=0)
    upper = np.max(ordered, axis=0)
    extent = upper - lower
    if not np.isfinite(extent).all() or np.any(extent <= 0.0):
        raise ValueError("hex must span a positive finite extent on all Cartesian axes")
    tolerance = np.maximum(1.0e-12, np.abs(extent) * 1.0e-12)
    corners: list[tuple[int, int, int]] = []
    for point in ordered:
        coordinate_bits: list[int] = []
        for axis in range(3):
            if abs(point[axis] - lower[axis]) <= tolerance[axis]:
                coordinate_bits.append(0)
            elif abs(point[axis] - upper[axis]) <= tolerance[axis]:
                coordinate_bits.append(1)
            else:
                raise ValueError("hex vertices are not axis-aligned Cartesian corners")
        corners.append(tuple(coordinate_bits))
    if tuple(corners) != _EXPECTED_HEX_CORNERS:
        raise ValueError(
            "hex vertex ordering is not the canonical axis-aligned order required for x-fastest cells"
        )
    return lower, upper


def _parenthesized_entry(dictionary: str, key: str) -> str:
    match = re.search(rf"\b{re.escape(key)}\b\s*\(", dictionary)
    if match is None:
        raise ValueError(f"blockMeshDict is missing {key} entry")
    start = dictionary.find("(", match.start())
    depth = 0
    for index in range(start, len(dictionary)):
        character = dictionary[index]
        if character == "(":
            depth += 1
        elif character == ")":
            depth -= 1
            if depth == 0:
                return dictionary[start + 1 : index]
    raise ValueError(f"blockMeshDict {key} entry has unbalanced parentheses")


def _strip_comments(text: str) -> str:
    without_block = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    return re.sub(r"//[^\r\n]*", "", without_block)


__all__ = ["OpenFoamBlockMeshGrid", "read_openfoam_blockmesh_uniform_cartesian_grid"]
