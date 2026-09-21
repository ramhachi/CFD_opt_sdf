"""One owner for the Stage T design transform and its adjoint (DF1).

The filtered-ramp script owned the cone filter, the block filter, the tanh
projection, the RAMP interpolation and the chain rule inside
``scripts/stage_t_filtered_ramp.py``. DF1 moves that stack here so that

    rho_design -> rho_filtered -> rho_projected -> beta

and its transpose ``g_rho = H.T (h' * f' * g_beta)`` have one implementation,
one transformation hash, and one set of fail-closed checks. Scripts keep their
behaviour by delegating to this module.

The block filter replicates the exact length-scale guarantees of a
super-cell mean, but it is diagnostics-only: its declaration width is not a
production guarantee because the block edge snaps to the nearest divisor of
the active box. ``DesignTransform.production_ready`` refuses it unless the
caller explicitly asks for a diagnostic transform.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from scipy.ndimage import convolve

from .shape_feature_metrics import occupancy_metrics


class DesignTransformError(ValueError):
    """Fail-closed design-transform contract violation."""


def _as3d(flat: np.ndarray, shape: tuple[int, ...]) -> np.ndarray:
    return np.asarray(flat).reshape(shape, order="F")


def _as_flat(array3d: np.ndarray) -> np.ndarray:
    return np.asarray(array3d).ravel(order="F")


def _validate_design(rho: np.ndarray, active: np.ndarray, *, tolerance: float = 1e-9) -> np.ndarray:
    values = np.asarray(rho, dtype=np.float64)
    if values.shape != active.shape:
        raise DesignTransformError(
            f"rho shape {values.shape} does not match the active mask {active.shape}"
        )
    if not np.isfinite(values).all():
        raise DesignTransformError("rho contains non-finite values")
    lo, hi = values.min(), values.max()
    if lo < -tolerance or hi > 1.0 + tolerance:
        raise DesignTransformError(
            f"rho must be within [0, 1]; observed [{lo}, {hi}]"
        )
    return np.clip(values, 0.0, 1.0)


@dataclass
class ConeFilter:
    """Cone (linear-hat) density filter over a physical radius.

    ``H = M K M / d`` with ``M`` the active mask, ``K`` a symmetric cone
    convolution, ``d = K M`` the per-cell weight sum; the exact transpose is
    ``H.T = M K (M . / d)``.
    """

    shape: tuple[int, int, int]
    spacing_m: float
    active_mask: np.ndarray
    radius_m: float
    production_allowed: bool = True
    kind: str = "cone_density_filter"

    def __post_init__(self) -> None:
        if self.radius_m <= 0.0 or not math.isfinite(self.radius_m):
            raise DesignTransformError("cone filter radius must be finite and positive")
        if self.spacing_m <= 0.0 or not math.isfinite(self.spacing_m):
            raise DesignTransformError("spacing must be finite and positive")
        self.radius_cells = self.radius_m / self.spacing_m
        reach = int(math.ceil(self.radius_cells))
        ijk = np.mgrid[-reach : reach + 1, -reach : reach + 1, -reach : reach + 1]
        self.kernel = np.maximum(self.radius_cells - np.sqrt((ijk**2).sum(axis=0)), 0.0)
        self.mask = _as3d(self.active_mask, self.shape).astype(np.float64)
        if not np.any(self.mask > 0):
            raise DesignTransformError("active mask is empty")
        self.denom = convolve(self.mask, self.kernel, mode="constant", cval=0.0)
        self.denom_safe = np.where(self.mask > 0, self.denom, 1.0)
        self.meta = {
            "kind": self.kind,
            "minimum_solid_width_m": 2.0 * self.radius_m,
            "relation": "filter_radius_m = minimum_solid_width_m / 2",
            "filter_radius_m": self.radius_m,
            "filter_radius_cells": self.radius_cells,
            "weights": "max(R - |x_i - x_j|, 0), uniform cell volume",
            "boundary": "restricted to active design cells; normalised by weights present",
            "transpose": "H.T y = M K (M y / d) with d = K M (exact; H is not symmetric)",
        }

    def H(self, flat: np.ndarray) -> np.ndarray:
        x3 = _as3d(flat, self.shape) * self.mask
        filtered = convolve(x3, self.kernel, mode="constant", cval=0.0) / self.denom_safe
        return _as_flat(self.mask * filtered)

    def HT(self, flat: np.ndarray) -> np.ndarray:
        y3 = _as3d(flat, self.shape) * self.mask / self.denom_safe
        return _as_flat(self.mask * convolve(y3, self.kernel, mode="constant", cval=0.0))


@dataclass
class BlockFilter:
    """Super-cell block-mean filter, diagnostics only (DF1 production ban).

    ``H = B D^-1 B^T`` is an orthogonal projection (``H.T == H``). The block
    edge snaps to the nearest divisor of the active box, so the declared width
    is not a production guarantee; ``production_allowed`` is False and
    ``DesignTransform.production_ready`` refuses it.
    """

    shape: tuple[int, int, int]
    spacing_m: float
    active_mask: np.ndarray
    width_m: float
    production_allowed: bool = False
    kind: str = "block_average_filter"

    def __post_init__(self) -> None:
        if self.width_m <= 0.0 or not math.isfinite(self.width_m):
            raise DesignTransformError("block filter width must be finite and positive")
        self.mask = _as3d(self.active_mask, self.shape).astype(np.float64)
        index = np.flatnonzero(self.mask.ravel(order="F") > 0)
        if index.size == 0:
            raise DesignTransformError("active mask is empty")
        nx, ny, nz = self.shape
        ix, iy, iz = index % nx, (index // nx) % ny, index // (nx * ny)
        self.lo = np.array([ix.min(), iy.min(), iz.min()])
        extent = np.array([ix.max(), iy.max(), iz.max()]) - self.lo + 1
        if int(self.mask.sum()) != int(np.prod(extent)):
            raise DesignTransformError("active design cells must form one box")
        target = int(round(self.width_m / self.spacing_m))
        self.block = np.array(
            [
                min((d for d in range(1, e + 1) if e % d == 0), key=lambda d: abs(d - target))
                for e in extent
            ]
        )
        self.nblocks = extent // self.block
        self.extent = extent
        self.radius_cells = float(self.block.min()) / 2.0
        self.meta = {
            "kind": self.kind,
            "minimum_solid_width_m": self.width_m,
            "block_cells": self.block.tolist(),
            "block_m": (self.block * self.spacing_m).tolist(),
            "relation": "block edge (y, z) = minimum_solid_width_m; x edge = nearest divisor",
            "guaranteed_min_solid_thickness_cells": int(self.block.min()),
            "transpose": "H = B D^-1 B^T is an orthogonal projection: H.T == H (exact)",
            "production_allowed": False,
            "production_note": "block edge snaps to the nearest divisor; diagnostics only",
        }

    def _blocks(self, x3: np.ndarray) -> tuple[np.ndarray, tuple[slice, slice, slice]]:
        slices = tuple(slice(int(self.lo[i]), int(self.lo[i] + self.extent[i])) for i in range(3))
        sub = x3[slices]
        b = self.block
        return (
            sub.reshape(
                self.nblocks[0], b[0], self.nblocks[1], b[1], self.nblocks[2], b[2]
            ),
            slices,
        )

    def H(self, flat: np.ndarray) -> np.ndarray:
        x3 = _as3d(flat, self.shape) * self.mask
        blocks, slices = self._blocks(x3)
        mean = blocks.mean(axis=(1, 3, 5), keepdims=True)
        out = np.zeros_like(x3)
        out[slices] = np.broadcast_to(mean, blocks.shape).reshape(tuple(self.extent))
        return _as_flat(out * self.mask)

    def HT(self, flat: np.ndarray) -> np.ndarray:
        return self.H(flat)


@dataclass(frozen=True)
class TanhProjection:
    """Smoothed Heaviside projection at threshold ``eta``; ``b <= 0`` is identity."""

    sharpness: float = 0.0
    eta: float = 0.5

    def __post_init__(self) -> None:
        if self.sharpness < 0.0 or not math.isfinite(self.sharpness):
            raise DesignTransformError("projection sharpness must be finite and non-negative")
        if not 0.0 < self.eta < 1.0:
            raise DesignTransformError("projection threshold eta must be within (0, 1)")

    def forward(self, values: np.ndarray) -> np.ndarray:
        if self.sharpness <= 0.0:
            return np.asarray(values, dtype=np.float64)
        b, eta = self.sharpness, self.eta
        denominator = np.tanh(b * eta) + np.tanh(b * (1.0 - eta))
        return (np.tanh(b * eta) + np.tanh(b * (np.asarray(values) - eta))) / denominator

    def derivative(self, values: np.ndarray) -> np.ndarray:
        if self.sharpness <= 0.0:
            return np.ones_like(np.asarray(values, dtype=np.float64))
        b, eta = self.sharpness, self.eta
        denominator = np.tanh(b * eta) + np.tanh(b * (1.0 - eta))
        return b * (1.0 - np.tanh(b * (np.asarray(values) - eta)) ** 2) / denominator

    def meta(self) -> dict[str, Any]:
        return {
            "kind": "tanh_heaviside" if self.sharpness > 0.0 else "identity",
            "b": self.sharpness,
            "eta": self.eta,
        }


@dataclass(frozen=True)
class RampInterpolation:
    """RAMP material interpolation ``p / (1 + q (1 - p))`` (q = 0 is linear)."""

    q: float = 0.0

    def __post_init__(self) -> None:
        if self.q < 0.0 or not math.isfinite(self.q):
            raise DesignTransformError("RAMP q must be finite and non-negative")

    def forward(self, projected: np.ndarray) -> np.ndarray:
        p = np.asarray(projected, dtype=np.float64)
        return p / (1.0 + self.q * (1.0 - p))

    def derivative(self, projected: np.ndarray) -> np.ndarray:
        p = np.asarray(projected, dtype=np.float64)
        return (1.0 + self.q) / (1.0 + self.q * (1.0 - p)) ** 2

    def meta(self) -> dict[str, Any]:
        return {"kind": "ramp", "q": self.q}


@dataclass(frozen=True)
class DesignTransformState:
    rho_design: np.ndarray
    rho_filtered: np.ndarray
    rho_projected: np.ndarray
    beta: np.ndarray


@dataclass
class DesignTransform:
    """Filter, projection, interpolation, and their chain, with one identity hash."""

    shape: tuple[int, int, int]
    spacing_m: float
    active_mask: np.ndarray
    filter: ConeFilter | BlockFilter
    projection: TanhProjection = field(default_factory=TanhProjection)
    ramp: RampInterpolation = field(default_factory=RampInterpolation)
    schema_version: int = 1

    def __post_init__(self) -> None:
        self.active = np.asarray(self.active_mask, dtype=bool)
        if self.active.shape != (math.prod(self.shape),):
            raise DesignTransformError(
                "active mask must be a flat boolean array of the grid cell count"
            )
        if self.filter.shape != tuple(self.shape):
            raise DesignTransformError("filter shape does not match the transform shape")

    def forward(self, rho: np.ndarray) -> DesignTransformState:
        design = _validate_design(np.asarray(rho, dtype=np.float64), self.active)
        unfiltered = self.filter.H(design)
        filtered = np.clip(unfiltered, 0.0, 1.0)
        projected = np.clip(self.projection.forward(filtered), 0.0, 1.0)
        beta = self.ramp.forward(projected)
        return DesignTransformState(
            rho_design=design,
            rho_filtered=filtered,
            rho_projected=projected,
            beta=beta,
        )

    def backward(self, rho: np.ndarray, g_beta: np.ndarray) -> np.ndarray:
        """``g_rho = H.T (projection' * ramp' * g_beta)`` evaluated at ``rho``."""

        gradient = np.asarray(g_beta, dtype=np.float64)
        if gradient.shape != self.active.shape:
            raise DesignTransformError("adjoint seed shape does not match the design")
        if not np.isfinite(gradient).all():
            raise DesignTransformError("adjoint seed contains non-finite values")
        state = self.forward(rho)
        derivative = self.projection.derivative(state.rho_filtered) * self.ramp.derivative(
            state.rho_projected
        )
        return self.filter.HT(derivative * gradient)

    def chain(self, rho: np.ndarray, g_beta: np.ndarray) -> tuple[DesignTransformState, np.ndarray]:
        state = self.forward(rho)
        derivative = self.projection.derivative(state.rho_filtered) * self.ramp.derivative(
            state.rho_projected
        )
        return state, self.filter.HT(derivative * g_beta)

    def projected_volume_fraction(self, state: DesignTransformState) -> float:
        values = np.asarray(state.rho_projected)[self.active]
        return float(np.mean(values)) if values.size else 0.0

    def projected_occupancy_stats(
        self, state: DesignTransformState, *, threshold: float = 0.5
    ) -> dict[str, Any]:
        solid = _as3d(state.rho_projected, self.shape) > threshold
        if not solid.any():
            return {"empty": True, "n_cells": 0}
        return occupancy_metrics(solid, self.spacing_m, threshold_m=threshold)

    def production_ready(self, *, allow_diagnostics: bool = False) -> None:
        if not self.filter.production_allowed and not allow_diagnostics:
            raise DesignTransformError(
                f"{self.filter.kind} is diagnostics only; it cannot own a production design transform"
            )

    def describe(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "kind": "design_transform",
            "shape": list(self.shape),
            "spacing_m": float(self.spacing_m),
            "active_cells": int(self.active.sum()),
            "active_mask_sha256": hashlib.sha256(
                np.ascontiguousarray(self.active, dtype=np.uint8).tobytes()
            ).hexdigest(),
            "filter": dict(self.filter.meta),
            "projection": self.projection.meta(),
            "ramp": self.ramp.meta(),
        }

    def transform_hash(self) -> str:
        payload = json.dumps(self.describe(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


__all__ = [
    "BlockFilter",
    "ConeFilter",
    "DesignTransform",
    "DesignTransformError",
    "DesignTransformState",
    "RampInterpolation",
    "TanhProjection",
]
