"""Measured feature sizes of the registered analytic shapes (DF0).

WP6-2's manifest declares two different minimum-solid-width values (purpose
``>= 0.15 m`` and ``definition.reachable_set`` ``>= 0.10 m``) while several
composite parts contain 0.05--0.12 m features. This module measures, instead
of assuming: the maximum inscribed sphere diameter per part (the feature
thickness of a convex part), the local-thickness ridge statistics, connected
components, per-part decomposition of union definitions, and part-to-part gaps
and overlaps. The measurement is the machine-readable half of the DF0 audit;
the declared half is compared against it in ``evidence_audit.py``.

Why not the plain EDT local thickness: with cell-center distances a 3-cell
slab reports 4 or 2 cells depending on parity, so the measure cannot be
compared with a declared metric width. The distance field is therefore
evaluated on a 4x supersampled grid (so a voxel is a solid cube and the slab
mid-plane carries the true half-thickness), and:

- ``max_inscribed_diameter_m`` = the largest ball that fits in the occupancy
  (for a convex part this is its smallest declared extent);
- ``thickness_ridge_m_*`` = statistics of the thickness map on its ridge
  (medial-axis) cells, i.e. cells that attain the local thickness maximum.

Both are quantized by at most half a voxel; every declared/measured difference
is classified as ``exact``, ``grid_quantized``, ``under_resolved`` or
``grid_over_read`` in the audit rather than silently rounded.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
from scipy import ndimage

from .analytic_candidate_shapes import (
    CANONICAL_SHAPE,
    CANONICAL_SPACING,
    ShapeDefinition,
    build_shape,
)

_CONNECTIVITY_26 = np.ones((3, 3, 3), dtype=bool)
_SUPERSAMPLE = 4


def as_canonical_3d(occupancy: np.ndarray) -> np.ndarray:
    """Canonical x-fastest flat occupancy or 3D array -> 3D bool array."""

    arr = np.asarray(occupancy, dtype=bool)
    if arr.shape == CANONICAL_SHAPE:
        return arr
    if arr.shape != (math.prod(CANONICAL_SHAPE),):
        raise ValueError(
            f"occupancy must be {CANONICAL_SHAPE} or its flat {math.prod(CANONICAL_SHAPE)} cells"
        )
    return arr.reshape(CANONICAL_SHAPE, order="F")


def _supersample(solid: np.ndarray, factor: int = _SUPERSAMPLE) -> np.ndarray:
    up = np.asarray(solid, dtype=bool)
    for axis in range(3):
        up = np.repeat(up, factor, axis=axis)
    return up


def thickness_map_m(
    solid: np.ndarray, spacing_m: float, factor: int = _SUPERSAMPLE
) -> tuple[np.ndarray, np.ndarray]:
    """Supersampled solid mask and its thickness map (2 x distance, in meters)."""

    up = _supersample(solid, factor)
    if not up.any():
        return up, np.zeros(up.shape, dtype=float)
    sub = float(spacing_m) / factor
    distance = ndimage.distance_transform_edt(up, sampling=sub)
    return up, 2.0 * distance


def _ridge_values(thickness: np.ndarray, up: np.ndarray) -> np.ndarray:
    ridge = up & (thickness >= ndimage.maximum_filter(thickness, size=3) - 1e-12)
    return thickness[ridge]


def occupancy_metrics(
    solid: np.ndarray,
    spacing_m: float,
    *,
    threshold_m: float | None = None,
    factor: int = _SUPERSAMPLE,
) -> dict[str, Any]:
    """Volume, components and feature-thickness statistics of one occupancy."""

    solid = (
        as_canonical_3d(solid)
        if np.asarray(solid).shape != CANONICAL_SHAPE
        else np.asarray(solid, dtype=bool)
    )
    spacing = float(spacing_m)
    metrics: dict[str, Any] = {
        "n_cells": int(solid.sum()),
        "volume_m3": float(solid.sum() * spacing**3),
        "empty": not bool(solid.any()),
    }
    if metrics["empty"]:
        return metrics

    labels, n_labels = ndimage.label(solid, structure=_CONNECTIVITY_26)
    sizes = sorted(
        (int(v) for v in np.bincount(labels.ravel())[1:] if v > 0), reverse=True
    )
    metrics["n_components_26"] = int(n_labels)
    metrics["component_cells"] = sizes[:16]

    up, thickness = thickness_map_m(solid, spacing, factor=factor)
    ridge = _ridge_values(thickness, up)
    metrics.update(
        {
            "max_inscribed_diameter_m": float(thickness[up].max()),
            "thickness_ridge_m_min": float(ridge.min()),
            "thickness_ridge_m_p5": float(np.percentile(ridge, 5)),
            "thickness_ridge_m_p50": float(np.percentile(ridge, 50)),
            "thickness_ridge_m_max": float(ridge.max()),
            "ridge_cells_m": int(ridge.size),
            "fraction_ridge_below_threshold": (
                float((ridge < threshold_m - 1e-12).mean())
                if threshold_m is not None
                else None
            ),
            "local_thickness_threshold_m": threshold_m,
            "supersample_factor": int(factor),
        }
    )
    return metrics


def _single_part(part: ShapeDefinition) -> ShapeDefinition:
    return ShapeDefinition(
        part.shape_id,
        part.chord_m,
        part.span_m,
        part.thickness_m,
        part.angle_y_deg,
        part.center_m,
        parts=(),
    )


def declared_min_dimension_m(part: ShapeDefinition) -> float:
    """The box's smallest declared extent (the analytic minimum feature)."""

    return float(min(part.chord_m, part.span_m, part.thickness_m))


def _part_occupancies(
    definition: ShapeDefinition,
) -> list[tuple[ShapeDefinition, np.ndarray]]:
    parts = list(definition.parts) if definition.parts else [definition]
    return [
        (part, as_canonical_3d(build_shape(_single_part(part)).occupancy))
        for part in parts
    ]


def measure_shape_definition(
    definition: ShapeDefinition,
    *,
    spacing_m: float = CANONICAL_SPACING,
    threshold_m: float | None = None,
) -> dict[str, Any]:
    """Per-part and union measurements of one analytic shape definition."""

    union = as_canonical_3d(build_shape(definition).occupancy)
    parts = _part_occupancies(definition)
    part_metrics = []
    for part, occupancy in parts:
        entry = {
            "part_id": part.shape_id,
            "declared_min_dimension_m": declared_min_dimension_m(part),
            "declared_thickness_m": float(part.thickness_m),
            "declared_chord_m": float(part.chord_m),
            "declared_span_m": float(part.span_m),
            **occupancy_metrics(occupancy, spacing_m, threshold_m=threshold_m),
        }
        part_metrics.append(entry)
    interactions = []
    for i in range(len(parts)):
        for j in range(i + 1, len(parts)):
            a, b = parts[i][1], parts[j][1]
            overlap = int((a & b).sum())
            if overlap:
                gap = 0.0
            else:
                distance = ndimage.distance_transform_edt(~a, sampling=spacing_m)
                gap = max(float(distance[b].min()) - spacing_m, 0.0)
            interactions.append(
                {
                    "part_a": parts[i][0].shape_id,
                    "part_b": parts[j][0].shape_id,
                    "overlap_cells": overlap,
                    "min_face_gap_m": gap,
                }
            )
    return {
        "shape_id": definition.shape_id,
        "n_parts": len(parts),
        "union": occupancy_metrics(union, spacing_m, threshold_m=threshold_m),
        "parts": part_metrics,
        "part_interactions": interactions,
        "min_declared_part_dimension_m": float(
            min(declared_min_dimension_m(part) for part, _ in parts)
        ),
        "min_measured_feature_size_m": float(
            min(entry["max_inscribed_diameter_m"] for entry in part_metrics)
        ),
    }


def measure_shape_definitions(
    definitions: dict[str, ShapeDefinition],
    *,
    spacing_m: float = CANONICAL_SPACING,
    threshold_m: float | None = None,
) -> dict[str, Any]:
    """measure_shape_definition over a registry dict, with a summary."""

    shapes = {
        shape_id: measure_shape_definition(
            definition, spacing_m=spacing_m, threshold_m=threshold_m
        )
        for shape_id, definition in definitions.items()
    }
    return {
        "spacing_m": float(spacing_m),
        "threshold_m": threshold_m,
        "n_shapes": len(shapes),
        "shapes": shapes,
    }


def measure_shape_registry(
    registry_dir: str | Path,
    *,
    spacing_m: float = CANONICAL_SPACING,
    threshold_m: float | None = None,
) -> dict[str, Any]:
    """Measure the occupancy actually run for a registry directory.

    Reads ``shape_registry_manifest.json`` and every ``<shape>/occupancy.npy``,
    verifies the recorded SHA-256 against the bytes, and measures the stored
    occupancy (which may have had the active mask intersected, unlike the raw
    definition).
    """

    root = Path(registry_dir).resolve()
    registry_path = root / "shape_registry_manifest.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    shapes: dict[str, Any] = {}
    for shape_id, manifest in registry.items():
        npy_path = root / shape_id / manifest["files"]["occupancy_npy"]["path"]
        raw = npy_path.read_bytes()
        expected = manifest["files"]["occupancy_npy"]["sha256"]
        actual = hashlib.sha256(raw).hexdigest()
        if actual != expected:
            raise ValueError(
                f"occupancy SHA-256 mismatch for {shape_id!r}: {actual} != {expected}"
            )
        occupancy = np.load(npy_path, allow_pickle=False)
        shapes[shape_id] = {
            "occupancy_sha256": actual,
            "active_mask_intersected": bool(manifest.get("active_mask_intersected")),
            "as_run": occupancy_metrics(occupancy, spacing_m, threshold_m=threshold_m),
        }
    return {
        "registry_dir": str(root),
        "registry_manifest_sha256": hashlib.sha256(registry_path.read_bytes()).hexdigest(),
        "spacing_m": float(spacing_m),
        "threshold_m": threshold_m,
        "shapes": shapes,
    }


def policy_exclusion_report(
    feature_table: dict[str, Any], policy_widths_m: list[float]
) -> dict[str, Any]:
    """Which registered shapes a given declared min-width policy excludes.

    A shape is excluded when its measured minimum feature size (over parts, on
    the canonical grid) is below the policy width beyond the half-voxel
    quantization the audit records separately.
    """

    spacing = float(feature_table["spacing_m"])
    widths = sorted({float(w) for w in policy_widths_m})
    per_shape: dict[str, Any] = {}
    for shape_id, entry in feature_table["shapes"].items():
        measured = float(entry["min_measured_feature_size_m"])
        per_shape[shape_id] = {
            "min_measured_feature_size_m": measured,
            "min_measured_feature_size_cells": measured / spacing,
            "excluded_under_policy": {
                f"{width:g}": bool(measured < width - spacing / 2)
                for width in widths
            },
        }
    return {
        "policy_widths_m": widths,
        "quantization_tolerance_m": spacing / 2,
        "per_shape": per_shape,
        "excluded_shape_ids": {
            f"{width:g}": sorted(
                shape_id
                for shape_id, entry in per_shape.items()
                if entry["excluded_under_policy"][f"{width:g}"]
            )
            for width in widths
        },
    }


__all__ = [
    "as_canonical_3d",
    "declared_min_dimension_m",
    "measure_shape_definition",
    "measure_shape_definitions",
    "measure_shape_registry",
    "occupancy_metrics",
    "policy_exclusion_report",
    "thickness_map_m",
]
