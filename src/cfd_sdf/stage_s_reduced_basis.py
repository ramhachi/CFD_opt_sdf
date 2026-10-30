"""Stage S reduced-basis FD architecture (S0 contract and S1 solver-free tools).

The architecture keeps the registered ``volumetricBSplines`` morpher and the
same body-fitted baseline, but replaces the 648 control-point components with a
pre-registered K=16 smooth mode basis. The gradient is produced by centered
finite differences of the primal responses in mode-coefficient space, never by
the continuous adjoint.

This module owns:

- the deterministic, geometry-only sine-mode candidate set on the active
  6x6x6 control-point lattice (zero on boundary control points, frequency
  ordered, y-symmetry preserving, canonical sign);
- the mode-to-control-point movement map;
- the design-surface normal-displacement measurement used for the
  normalization to unit maximum normal displacement per unit mode coefficient;
- the manifest-hash-derived holdout directions in mode space.

No flow solver, response or adjoint is involved.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

import numpy as np

from .stage_s_adjoint_qualification import active_var_ids

N_CONTROL_POINTS: tuple[int, int, int] = (8, 8, 8)
INTERIOR_POINTS: int = 6
K_MODES: int = 16
CANDIDATE_COUNT: int = 32
AXIS_ORDER: tuple[str, ...] = ("x", "y", "z")
AXIS_INDEX: dict[str, int] = {"x": 0, "y": 1, "z": 2}
MIN_NORMAL_EFFICIENCY: float = 0.01
REFERENCE_AMPLITUDE_M: float = 1.0e-3
EPSILON_LADDER_M: tuple[float, ...] = (1.0e-4, 2.5e-4, 5.0e-4, 1.0e-3)
NORMAL_DISPLACEMENT_RELATIVE_TOLERANCE: float = 1.0e-3


class ReducedBasisError(ValueError):
    """Fail-closed reduced-basis contract violation."""


def _interior_index(value: int, n_cps: int) -> float:
    return float(value) * np.pi / float(n_cps - 1)


def preserves_y_symmetry(axis: str, b: int) -> bool:
    """The sideMin/sideMax symmetry planes require a y-mirror-preserving basis.

    Mirroring y maps interior index ``j`` to ``n-1-j``; the x/z displacement
    components must be even and the y component odd in the mirror.
    """

    if axis in ("x", "z"):
        return b % 2 == 1
    if axis == "y":
        return b % 2 == 0
    raise ReducedBasisError(f"unknown axis {axis!r}")


@dataclass(frozen=True)
class ModeCandidate:
    """One registered sine-mode candidate on the active control-point lattice."""

    a: int
    b: int
    c: int
    axis: str

    @property
    def frequency(self) -> int:
        return self.a * self.a + self.b * self.b + self.c * self.c

    @property
    def name(self) -> str:
        return f"mode_k{self.frequency:02d}_a{self.a}b{self.b}c{self.c}_{self.axis}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "a": self.a,
            "b": self.b,
            "c": self.c,
            "axis": self.axis,
            "frequency": self.frequency,
        }


def mode_candidates(count: int = CANDIDATE_COUNT) -> tuple[ModeCandidate, ...]:
    """Frequency-ordered y-symmetry-preserving sine-mode candidates."""

    items: list[ModeCandidate] = []
    n = INTERIOR_POINTS
    for a in range(1, n + 1):
        for b in range(1, n + 1):
            for c in range(1, n + 1):
                for axis in AXIS_ORDER:
                    if preserves_y_symmetry(axis, b):
                        items.append(ModeCandidate(a=a, b=b, c=c, axis=axis))
    items.sort(key=lambda item: (item.frequency, item.a, item.b, item.c, AXIS_ORDER.index(item.axis)))
    return tuple(items[:count])


def canonical_sign(values: np.ndarray) -> tuple[np.ndarray, bool]:
    """The largest-magnitude component is positive (deterministic sign)."""

    array = np.asarray(values, dtype=np.float64)
    if array.size == 0 or not np.isfinite(array).all():
        raise ReducedBasisError("mode vector is empty or non-finite")
    index = int(np.argmax(np.abs(array)))
    if array[index] < 0.0:
        return -array, True
    return array, False


def sine_mode_vector(
    candidate: ModeCandidate,
    *,
    active_ids: tuple[int, ...] | None = None,
    n_cps: tuple[int, int, int] = N_CONTROL_POINTS,
) -> np.ndarray:
    """The candidate mode as a unit-infinity-norm vector over active varIDs."""

    ids = tuple(active_var_ids(n_cps)) if active_ids is None else active_ids
    nx, ny, nz = (int(value) for value in n_cps)
    component = AXIS_INDEX[candidate.axis]
    values = np.zeros(len(ids), dtype=np.float64)
    for index, var_id in enumerate(ids):
        cp_id, var_component = divmod(int(var_id), 3)
        k, remainder = divmod(cp_id, nx * ny)
        j, i = divmod(remainder, nx)
        if var_component != component:
            continue
        scalar = (
            np.sin(candidate.a * _interior_index(i + 1, nx))
            * np.sin(candidate.b * _interior_index(j + 1, ny))
            * np.sin(candidate.c * _interior_index(k + 1, nz))
        )
        values[index] = scalar
    if not np.any(values):
        raise ReducedBasisError(f"{candidate.name}: the mode is empty on the active set")
    return values / float(np.max(np.abs(values)))


def mode_to_movement(
    mode_values: np.ndarray,
    *,
    active_ids: tuple[int, ...],
    coefficient: float,
    sign: float,
    n_cps: tuple[int, int, int] = N_CONTROL_POINTS,
) -> np.ndarray:
    """The 512-vector control-point movement ``sign * coefficient * mode``."""

    values = np.asarray(mode_values, dtype=np.float64)
    if values.size != len(active_ids):
        raise ReducedBasisError("mode vector size does not match the active varID set")
    if not np.isfinite(values).all():
        raise ReducedBasisError("mode vector contains non-finite values")
    nx, ny, nz = (int(value) for value in n_cps)
    movement = np.zeros((nx * ny * nz, 3), dtype=np.float64)
    for value, var_id in zip(values, active_ids, strict=True):
        cp_id, component = divmod(int(var_id), 3)
        movement[cp_id, component] = float(sign) * float(coefficient) * float(value)
    return movement


def mode_sha256(mode_values: np.ndarray) -> str:
    array = np.ascontiguousarray(np.asarray(mode_values, dtype=np.float64))
    return hashlib.sha256(array.tobytes()).hexdigest()


def patch_point_normals(vertices: np.ndarray, faces: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Outward unit vertex normals of the closed patch surface, per used point."""

    import trimesh

    used = np.unique(np.asarray(faces, dtype=np.int64))
    inverse = np.searchsorted(used, np.asarray(faces, dtype=np.int64))
    mesh = trimesh.Trimesh(
        vertices=np.asarray(vertices, dtype=np.float64)[used], faces=inverse, process=False
    )
    normals = np.asarray(mesh.vertex_normals, dtype=np.float64)
    norms = np.linalg.norm(normals, axis=1, keepdims=True)
    normals = np.divide(normals, norms, out=np.zeros_like(normals), where=norms > 0.0)
    return used, normals


def normal_displacement(
    *, base_vertices: np.ndarray, faces: np.ndarray, moved_vertices: np.ndarray
) -> dict[str, Any]:
    """Max signed normal displacement of the patch points between two meshes."""

    used, normals = patch_point_normals(base_vertices, faces)
    base = np.asarray(base_vertices, dtype=np.float64)[used]
    moved = np.asarray(moved_vertices, dtype=np.float64)[used]
    displacement = moved - base
    normal_component = np.einsum("ij,ij->i", displacement, normals)
    return {
        "point_count": int(used.size),
        "max_abs_normal_displacement_m": float(np.max(np.abs(normal_component))),
        "max_normal_displacement_m": float(np.max(normal_component)),
        "min_normal_displacement_m": float(np.min(normal_component)),
        "normal_component": normal_component,
        "point_indices": used,
    }


def holdout_seed(manifest_sha256: str, index: int) -> int:
    if index < 1:
        raise ReducedBasisError("holdout seed indices start at 1")
    digest = hashlib.sha256(f"{manifest_sha256}:holdout:mode:{index}".encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big")


def holdout_mode_directions(
    manifest_sha256: str, *, k_modes: int = K_MODES, n_random: int = 2
) -> list[dict[str, Any]]:
    """Deterministic unused random directions in mode space."""

    directions: list[dict[str, Any]] = []
    for index in range(1, n_random + 1):
        rng = np.random.default_rng(holdout_seed(manifest_sha256, index))
        values = rng.standard_normal(k_modes)
        values, flipped = canonical_sign(values)
        directions.append(
            {
                "kind": "random",
                "index": index,
                "seed": holdout_seed(manifest_sha256, index),
                "sign_flipped": flipped,
                "values": [float(value) for value in values],
            }
        )
    return directions


__all__ = [
    "AXIS_INDEX",
    "AXIS_ORDER",
    "CANDIDATE_COUNT",
    "EPSILON_LADDER_M",
    "INTERIOR_POINTS",
    "K_MODES",
    "MIN_NORMAL_EFFICIENCY",
    "ModeCandidate",
    "N_CONTROL_POINTS",
    "NORMAL_DISPLACEMENT_RELATIVE_TOLERANCE",
    "REFERENCE_AMPLITUDE_M",
    "ReducedBasisError",
    "canonical_sign",
    "holdout_mode_directions",
    "holdout_seed",
    "mode_candidates",
    "mode_sha256",
    "mode_to_movement",
    "normal_displacement",
    "patch_point_normals",
    "preserves_y_symmetry",
    "sine_mode_vector",
]
