"""Canonical immutable SDF design state for the SDF-native optimizer.

Repository-wide immutable convention::

    phi < 0 : solid
    phi = 0 : interface
    phi > 0 : fluid

The SDF field is the canonical design variable.  STL, B-spline control
points and body-fitted meshes are derived artifacts, never the design state.
The state hash binds the field, the grid, every geometry mask, the sign
convention, the topology policy and the reinitialization policy, so two
states with the same hash are the same optimization state.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import numpy as np

from ..runtime.fingerprint import FingerprintError, validate_sha256_hex

SDF_STATE_SCHEMA_VERSION = 1
SIGN_CONVENTION: Literal["negative_inside"] = "negative_inside"
DEFAULT_TOPOLOGY_POLICY_ID = "sdf_native_topology_policy_v1"
DEFAULT_REINITIALIZATION_POLICY_ID = "sdf_reinitialization_policy_v1"


class SDFStateError(ValueError):
    """Fail-closed SDF design-state contract violation."""


def _array_bytes(array: np.ndarray, dtype: str) -> bytes:
    return np.ascontiguousarray(np.asarray(array, dtype=dtype)).tobytes()


def _mask_bytes(mask: Any, shape: tuple[int, int, int], field_name: str) -> np.ndarray:
    if not isinstance(mask, np.ndarray) or mask.dtype != np.bool_ or mask.shape != shape:
        raise SDFStateError(f"{field_name} must be a boolean ndarray of shape {shape}")
    return mask


def sdf_state_sha256(
    *,
    phi: np.ndarray,
    origin_m: tuple[float, float, float],
    spacing_m: float,
    shape: tuple[int, int, int],
    design_mask: np.ndarray,
    fixed_solid_mask: np.ndarray,
    forbidden_mask: np.ndarray,
    root_mask: np.ndarray,
    sign_convention: str,
    narrow_band_width_m: float,
    generation: int,
    source_sha256: str | None,
    topology_policy_id: str,
    reinitialization_policy_id: str,
    schema_version: int = SDF_STATE_SCHEMA_VERSION,
) -> str:
    """Canonical state hash over the field, grid, masks and policies."""

    metadata = {
        "schema_version": int(schema_version),
        "kind": "sdf_design_state",
        "sign_convention": str(sign_convention),
        "shape": [int(value) for value in shape],
        "origin_m": [float(value) for value in origin_m],
        "spacing_m": float(spacing_m),
        "narrow_band_width_m": float(narrow_band_width_m),
        "generation": int(generation),
        "source_sha256": None if source_sha256 is None else str(source_sha256),
        "topology_policy_id": str(topology_policy_id),
        "reinitialization_policy_id": str(reinitialization_policy_id),
    }
    digest = hashlib.sha256()
    digest.update(json.dumps(metadata, sort_keys=True, separators=(",", ":")).encode("utf-8"))
    digest.update(b"\x00phi\x00")
    digest.update(_array_bytes(phi, "<f4"))
    for name, mask in (
        ("design", design_mask),
        ("fixed_solid", fixed_solid_mask),
        ("forbidden", forbidden_mask),
        ("root", root_mask),
    ):
        digest.update(f"\x00{name}\x00".encode("ascii"))
        digest.update(_array_bytes(mask, "u1"))
    return digest.hexdigest()


@dataclass(frozen=True, eq=False)
class SDFDesignState:
    """Immutable canonical SDF design state; construct through :meth:`create`."""

    phi: np.ndarray
    origin_m: tuple[float, float, float]
    spacing_m: float
    shape: tuple[int, int, int]
    design_mask: np.ndarray
    fixed_solid_mask: np.ndarray
    forbidden_mask: np.ndarray
    root_mask: np.ndarray
    sign_convention: Literal["negative_inside"]
    narrow_band_width_m: float
    generation: int
    source_sha256: str | None
    state_sha256: str
    topology_policy_id: str = DEFAULT_TOPOLOGY_POLICY_ID
    reinitialization_policy_id: str = DEFAULT_REINITIALIZATION_POLICY_ID

    def __post_init__(self) -> None:
        if self.sign_convention != SIGN_CONVENTION:
            raise SDFStateError(
                f"sign_convention must be {SIGN_CONVENTION!r}; got {self.sign_convention!r}"
            )
        if not isinstance(self.phi, np.ndarray) or self.phi.dtype != np.float32 or self.phi.ndim != 3:
            raise SDFStateError("phi must be a 3D float32 ndarray")
        if not np.isfinite(self.phi).all():
            raise SDFStateError("phi must be finite everywhere")
        if tuple(int(value) for value in self.phi.shape) != tuple(int(v) for v in self.shape):
            raise SDFStateError("phi.shape does not match the declared shape")
        if len(self.shape) != 3 or any(int(value) <= 0 for value in self.shape):
            raise SDFStateError("shape must contain three positive integers")
        if len(self.origin_m) != 3 or not np.isfinite(np.asarray(self.origin_m, dtype=np.float64)).all():
            raise SDFStateError("origin_m must contain three finite values")
        if not np.isfinite(self.spacing_m) or self.spacing_m <= 0.0:
            raise SDFStateError("spacing_m must be finite and positive")
        if not np.isfinite(self.narrow_band_width_m) or self.narrow_band_width_m <= 0.0:
            raise SDFStateError("narrow_band_width_m must be finite and positive")
        if int(self.generation) < 0:
            raise SDFStateError("generation must be non-negative")
        if self.source_sha256 is not None:
            try:
                validate_sha256_hex(self.source_sha256, field_name="source_sha256")
            except FingerprintError as error:
                raise SDFStateError(str(error)) from error
        if not str(self.topology_policy_id).strip() or not str(self.reinitialization_policy_id).strip():
            raise SDFStateError("topology/reinitialization policy ids must be non-empty")
        for name in ("design_mask", "fixed_solid_mask", "forbidden_mask", "root_mask"):
            _mask_bytes(getattr(self, name), self.shape, name)
        expected = self.recompute_sha256()
        if self.state_sha256 != expected:
            raise SDFStateError(
                "state_sha256 does not match the state content; "
                f"expected {expected}, got {self.state_sha256}"
            )

    def __eq__(self, other: object) -> bool:
        return isinstance(other, SDFDesignState) and other.state_sha256 == self.state_sha256

    def __hash__(self) -> int:
        return hash(self.state_sha256)

    def recompute_sha256(self) -> str:
        return sdf_state_sha256(
            phi=self.phi,
            origin_m=self.origin_m,
            spacing_m=self.spacing_m,
            shape=self.shape,
            design_mask=self.design_mask,
            fixed_solid_mask=self.fixed_solid_mask,
            forbidden_mask=self.forbidden_mask,
            root_mask=self.root_mask,
            sign_convention=self.sign_convention,
            narrow_band_width_m=self.narrow_band_width_m,
            generation=self.generation,
            source_sha256=self.source_sha256,
            topology_policy_id=self.topology_policy_id,
            reinitialization_policy_id=self.reinitialization_policy_id,
        )

    @property
    def solid_mask(self) -> np.ndarray:
        return self.phi < 0.0

    @property
    def fluid_mask(self) -> np.ndarray:
        return self.phi > 0.0

    def phi_sha256(self) -> str:
        return hashlib.sha256(_array_bytes(self.phi, "<f4")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        """Metadata only; the raw arrays are written by :meth:`save`."""

        return {
            "schema_version": SDF_STATE_SCHEMA_VERSION,
            "kind": "sdf_design_state",
            "state_sha256": self.state_sha256,
            "phi_sha256": self.phi_sha256(),
            "sign_convention": self.sign_convention,
            "shape": [int(value) for value in self.shape],
            "origin_m": [float(value) for value in self.origin_m],
            "spacing_m": float(self.spacing_m),
            "narrow_band_width_m": float(self.narrow_band_width_m),
            "generation": int(self.generation),
            "source_sha256": self.source_sha256,
            "topology_policy_id": self.topology_policy_id,
            "reinitialization_policy_id": self.reinitialization_policy_id,
            "solid_cell_count": int(self.solid_mask.sum()),
            "fluid_cell_count": int(self.fluid_mask.sum()),
            "design_cell_count": int(self.design_mask.sum()),
        }

    def save(self, path: Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(
            path,
            phi=self.phi,
            design_mask=self.design_mask,
            fixed_solid_mask=self.fixed_solid_mask,
            forbidden_mask=self.forbidden_mask,
            root_mask=self.root_mask,
            metadata=np.array(json.dumps(self.to_dict(), sort_keys=True)),
        )
        return path

    @classmethod
    def load(cls, path: Path) -> "SDFDesignState":
        with np.load(Path(path), allow_pickle=False) as data:
            metadata = json.loads(str(data["metadata"].item()))
            state = cls(
                phi=data["phi"],
                origin_m=tuple(float(value) for value in metadata["origin_m"]),
                spacing_m=float(metadata["spacing_m"]),
                shape=tuple(int(value) for value in metadata["shape"]),
                design_mask=data["design_mask"],
                fixed_solid_mask=data["fixed_solid_mask"],
                forbidden_mask=data["forbidden_mask"],
                root_mask=data["root_mask"],
                sign_convention=metadata["sign_convention"],
                narrow_band_width_m=float(metadata["narrow_band_width_m"]),
                generation=int(metadata["generation"]),
                source_sha256=metadata["source_sha256"],
                state_sha256=metadata["state_sha256"],
                topology_policy_id=metadata["topology_policy_id"],
                reinitialization_policy_id=metadata["reinitialization_policy_id"],
            )
        return state

    @classmethod
    def create(
        cls,
        *,
        phi: np.ndarray,
        origin_m: tuple[float, float, float],
        spacing_m: float,
        design_mask: np.ndarray | None = None,
        fixed_solid_mask: np.ndarray | None = None,
        forbidden_mask: np.ndarray | None = None,
        root_mask: np.ndarray | None = None,
        narrow_band_width_m: float,
        generation: int = 0,
        source_sha256: str | None = None,
        topology_policy_id: str = DEFAULT_TOPOLOGY_POLICY_ID,
        reinitialization_policy_id: str = DEFAULT_REINITIALIZATION_POLICY_ID,
    ) -> "SDFDesignState":
        field = np.ascontiguousarray(np.asarray(phi, dtype=np.float32))
        if field.ndim != 3:
            raise SDFStateError("phi must be a 3D array")
        shape = tuple(int(value) for value in field.shape)

        def mask_or_default(value: np.ndarray | None, default: bool) -> np.ndarray:
            if value is None:
                return np.full(shape, default, dtype=np.bool_)
            return np.ascontiguousarray(np.asarray(value, dtype=np.bool_))

        design = mask_or_default(design_mask, True)
        fixed_solid = mask_or_default(fixed_solid_mask, False)
        forbidden = mask_or_default(forbidden_mask, False)
        root = mask_or_default(root_mask, False)
        digest = sdf_state_sha256(
            phi=field,
            origin_m=origin_m,
            spacing_m=spacing_m,
            shape=shape,
            design_mask=design,
            fixed_solid_mask=fixed_solid,
            forbidden_mask=forbidden,
            root_mask=root,
            sign_convention=SIGN_CONVENTION,
            narrow_band_width_m=narrow_band_width_m,
            generation=generation,
            source_sha256=source_sha256,
            topology_policy_id=topology_policy_id,
            reinitialization_policy_id=reinitialization_policy_id,
        )
        return cls(
            phi=field,
            origin_m=tuple(float(value) for value in origin_m),
            spacing_m=float(spacing_m),
            shape=shape,
            design_mask=design,
            fixed_solid_mask=fixed_solid,
            forbidden_mask=forbidden,
            root_mask=root,
            sign_convention=SIGN_CONVENTION,
            narrow_band_width_m=float(narrow_band_width_m),
            generation=int(generation),
            source_sha256=source_sha256,
            state_sha256=digest,
            topology_policy_id=str(topology_policy_id),
            reinitialization_policy_id=str(reinitialization_policy_id),
        )


__all__ = [
    "DEFAULT_REINITIALIZATION_POLICY_ID",
    "DEFAULT_TOPOLOGY_POLICY_ID",
    "SDF_STATE_SCHEMA_VERSION",
    "SIGN_CONVENTION",
    "SDFDesignState",
    "SDFStateError",
    "sdf_state_sha256",
]
