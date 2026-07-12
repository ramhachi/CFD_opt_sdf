from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class UniformGrid:
    origin: np.ndarray
    spacing: float
    shape: tuple[int, int, int]

    @property
    def bounds(self) -> np.ndarray:
        max_corner = self.origin + self.spacing * (np.array(self.shape) - 1)
        return np.vstack([self.origin, max_corner])

    @property
    def point_count(self) -> int:
        return int(np.prod(self.shape))

    def axis(self, dim: int) -> np.ndarray:
        return self.origin[dim] + self.spacing * np.arange(self.shape[dim])

    def points_flat(self) -> np.ndarray:
        xs = self.axis(0)
        ys = self.axis(1)
        zs = self.axis(2)
        x, y, z = np.meshgrid(xs, ys, zs, indexing="ij")
        return np.column_stack([x.ravel(), y.ravel(), z.ravel()])


def grid_from_bounds(bounds: np.ndarray, spacing: float, padding: float, max_points: int) -> UniformGrid:
    padded_min = bounds[0] - padding
    padded_max = bounds[1] + padding
    shape = tuple((np.ceil((padded_max - padded_min) / spacing).astype(int) + 1).tolist())
    point_count = int(np.prod(shape))
    if point_count > max_points:
        raise ValueError(
            f"Grid has {point_count:,} points, above max_points={max_points:,}. "
            "Increase voxel_size_m or reduce bounds/padding."
        )
    return UniformGrid(origin=padded_min.astype(float), spacing=float(spacing), shape=shape)
