"""Analytic scene fields in metres; negative values denote solid.

The flat stadium, rectangular endplate and sphere are exact signed distances.
Deformed plates preserve v18's zero set and use numerical polynomial projection
to improve its first-order distance approximation (Amendment 1). General
superellipsoids use a gradient-normalized implicit field, not an exact SDF.
These are solver-free geometry contracts, not BDIM or SRCMAP qualification.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import io
import math
from pathlib import Path
import re

import numpy as np
import trimesh


def _number(value, name, positive=False):
    if isinstance(value, (str, bytes, bool, np.bool_)) or np.iscomplexobj(value) or not np.isscalar(value):
        raise ValueError(f"{name} must be a finite number")
    try:
        value = float(value)
    except (ValueError, TypeError) as exc:
        raise ValueError(f"{name} must be a finite number") from exc
    if not np.isfinite(value) or (positive and value <= 0):
        raise ValueError(f"{name} must be finite" + (" and positive" if positive else ""))
    return 0.0 if value == 0 else value


def _validate_id(value):
    if not isinstance(value, str) or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]*", value) is None:
        raise ValueError("id must be a nonempty stable ASCII identifier")
    return value


def _validate(instance, positive=()):
    _validate_id(instance.id)
    for name in instance.__dataclass_fields__:
        if name != "id" and not name.startswith("_"):
            object.__setattr__(instance, name, _number(getattr(instance, name), name, name in positive))


def _points(points, dimensions=(2, 3)):
    if np.iscomplexobj(points):
        raise ValueError("points must contain real coordinates")
    points = np.asarray(points, dtype=np.float64)
    if points.ndim < 1 or points.shape[-1] not in dimensions or not np.all(np.isfinite(points)):
        raise ValueError(f"points must be finite (...,{dimensions}) coordinates")
    return points


def _dimension(dimension):
    if isinstance(dimension, (bool, np.bool_)) or not isinstance(dimension, (int, np.integer)) or dimension not in (2, 3):
        raise ValueError("dimension must be 2 (x,z) or 3 (x,y,z)")


def _spacing(spacing):
    return _number(spacing, "spacing", positive=True)


def _linspace(lo, hi, spacing):
    return np.linspace(lo, hi, max(2, int(np.ceil((hi - lo) / spacing)) + 1))


def _extrude(section, axial):
    return np.minimum(np.maximum(section, axial), 0) + np.hypot(np.maximum(section, 0), np.maximum(axial, 0))


def _box_phi(points, half_width):
    q = np.abs(points) - half_width
    return np.minimum(np.max(q, axis=-1), 0) + np.linalg.norm(np.maximum(q, 0), axis=-1)


@dataclass(frozen=True)
class PlateElement:
    """v18 stadium section in x,z, optionally extruded with flat y tips.

    ``chord`` is v18's straight middle length L; the flat stadium's total chord
    is L+thickness. ``angle`` is radians with the v18 rotation convention;
    camber/reflex are dimensional polynomial amplitudes. A single section
    function serves both 2D (x,z) and 3D (x,y,z).

    Undeformed phi is the exact stadium/extrusion SDF. With deformation, the
    zero set is exactly v18's clipped polynomial stadium, and distance values
    use a fixed multistart projection to its cubic sides plus exact half-circle
    caps. Projection is numerical: no global exact-distance claim is made.
    The development band tests cover |camber|<=.06L, |reflex|<=.04L, |phi|<=2h
    and error<=.02 thickness. GPU/Julia must evaluate the same projection;
    trilinear interpolation of a design lattice is a different field.
    """

    id: str
    x: float
    z: float
    chord: float
    thickness: float
    angle: float = 0.0
    camber: float = 0.0
    reflex: float = 0.0
    span: float = 1.0
    y: float = 0.0

    def __post_init__(self):
        _validate(self, ("chord", "thickness", "span"))

    def _f(self, u):
        s = np.clip(2 * u / self.chord, -1, 1)
        return self.camber * (s * s - 1 / 3) + self.reflex * (s ** 3 - 0.6 * s)

    def _section(self, u, v):
        raw = np.hypot(np.maximum(np.abs(u) - self.chord / 2, 0), v + self._f(u)) - self.thickness / 2
        if self.camber == 0 and self.reflex == 0:
            return raw
        shape = u.shape
        u, v = u.reshape(-1), v.reshape(-1)
        best = np.full(u.shape, np.inf)
        half, radius = self.chord / 2, self.thickness / 2
        # ponytail: fixed small multistart beats per-node optimizers; WP4 must
        # check Julia parity/performance before adopting this in a GPU job.
        for start in range(0, len(u), 32768):
            stop = min(start + 32768, len(u))
            uq, vq = u[start:stop, None], v[start:stop, None]
            query_start = np.clip(uq, -half, half)
            seeds = np.broadcast_to(np.linspace(-half, half, 5), (len(uq), 5))
            chunk_best = np.full(len(uq), np.inf)
            for side in (-1, 1):
                a = np.concatenate((seeds, query_start), axis=1)
                # Keep every candidate, including endpoints and clipped query u.
                # The latter preserves zero values even before Newton converges.
                for _ in range(13):
                    s = 2 * a / self.chord
                    f = self.camber * (s * s - 1 / 3) + self.reflex * (s ** 3 - 0.6 * s)
                    residual = vq + f - side * radius
                    squared = (a - uq) ** 2 + residual ** 2
                    chunk_best = np.minimum(chunk_best, np.min(squared, axis=1))
                    df = (2 / self.chord) * (2 * self.camber * s + self.reflex * (3 * s * s - 0.6))
                    ddf = (2 / self.chord) ** 2 * (2 * self.camber + 6 * self.reflex * s)
                    first = a - uq + residual * df
                    second = 1 + df * df + residual * ddf
                    step = np.clip(first / np.maximum(second, 0.25), -self.chord / 4, self.chord / 4)
                    a = np.clip(a - step, -half, half)
            for side in (-1, 1):
                dx = uq[:, 0] - side * half
                dz = vq[:, 0] + self._f(np.asarray(side * half))
                # A full-circle projection is valid only on the outward half.
                cap = np.where(side * dx >= 0, (np.hypot(dx, dz) - radius) ** 2,
                               dx * dx + (np.abs(dz) - radius) ** 2)
                chunk_best = np.minimum(chunk_best, cap)
            best[start:stop] = np.sqrt(chunk_best)
        return np.where(raw < 0, -best.reshape(shape), best.reshape(shape))

    def phi(self, points):
        points = _points(points)
        dx, dz = points[..., 0] - self.x, points[..., -1] - self.z
        ca, sa = math.cos(self.angle), math.sin(self.angle)
        section = self._section(dx * ca + dz * sa, -dx * sa + dz * ca)
        return section if points.shape[-1] == 2 else _extrude(section, np.abs(points[..., 1] - self.y) - self.span / 2)

    def bbox(self, dimension=3):
        """Conservative finite bounds, including deformation and round caps."""
        _dimension(dimension)
        half_u = self.chord / 2 + self.thickness / 2
        half_v = self.thickness / 2 + 2 * abs(self.camber) / 3 + 0.4 * abs(self.reflex)
        ca, sa = abs(math.cos(self.angle)), abs(math.sin(self.angle))
        extent = np.array([ca * half_u + sa * half_v, self.span / 2, sa * half_u + ca * half_v])
        center = np.array([self.x, self.y, self.z])
        indices = [0, 2] if dimension == 2 else [0, 1, 2]
        return (center - extent)[indices], (center + extent)[indices]

    def to_dict(self):
        return {"kind": "plate", "id": self.id,
                "parameters": {name: getattr(self, name) for name in self.__dataclass_fields__ if name != "id"}}

    def boundary_points(self, spacing, dimension=3):
        """Deterministic zero-surface samples; side/axial steps <=spacing.

        This is a covering approximation, never an exact distance oracle. Tip
        interiors use a Cartesian mesh clipped to the section; their furthest
        uncovered distance is at most sqrt(2)*spacing plus boundary spacing.
        """
        spacing = _spacing(spacing)
        _dimension(dimension)
        # Bound side speed using |f'| <=4|C|/L+4.8|R|/L.
        speed = math.hypot(1, (4 * abs(self.camber) + 4.8 * abs(self.reflex)) / self.chord)
        u = _linspace(-self.chord / 2, self.chord / 2, spacing / speed)
        section = [np.column_stack((u, -self._f(u) + sign * self.thickness / 2)) for sign in (-1, 1)]
        theta = _linspace(-np.pi / 2, np.pi / 2, spacing / (self.thickness / 2))
        for sign in (-1, 1):
            edge = sign * self.chord / 2
            section.append(np.column_stack((edge + sign * self.thickness / 2 * np.cos(theta),
                                            -self._f(np.asarray(edge)) + self.thickness / 2 * np.sin(theta))))
        section = np.concatenate(section)
        ca, sa = math.cos(self.angle), math.sin(self.angle)

        def global_section(local):
            return local @ np.array([[ca, sa], [-sa, ca]]) + [self.x, self.z]

        if dimension == 2:
            return global_section(section)
        y = _linspace(self.y - self.span / 2, self.y + self.span / 2, spacing)
        xz = np.repeat(global_section(section), len(y), axis=0)
        surface = np.column_stack((xz[:, 0], np.tile(y, len(section)), xz[:, 1]))
        radius = self.thickness / 2
        uu = _linspace(-self.chord / 2 - radius, self.chord / 2 + radius, spacing)
        vv = _linspace(-radius - 2 * abs(self.camber) / 3 - 0.4 * abs(self.reflex),
                       radius + 2 * abs(self.camber) / 3 + 0.4 * abs(self.reflex), spacing)
        U, V = np.meshgrid(uu, vv, indexing="ij")
        inside = np.hypot(np.maximum(np.abs(U) - self.chord / 2, 0), V + self._f(U)) <= radius
        tips = global_section(np.column_stack((U[inside], V[inside])))
        return np.concatenate([surface] + [np.column_stack((tips[:, 0], np.full(len(tips), tip), tips[:, 1]))
                                            for tip in (y[0], y[-1])])


@dataclass(frozen=True)
class EndplatePlate:
    """Exact axis-aligned rectangular plate SDF, centred at (x,y,z).

    Extents are chord in x, thickness in y, and height in z; 2D evaluates its
    x,z rectangular section. Intentional wing/endplate joints are scene policy.
    """
    id: str
    x: float
    y: float
    z: float
    height: float
    chord: float
    thickness: float

    def __post_init__(self):
        _validate(self, ("height", "chord", "thickness"))

    def phi(self, points):
        points = _points(points)
        indices = [0, 2] if points.shape[-1] == 2 else [0, 1, 2]
        center = np.asarray([self.x, self.y, self.z])[indices]
        half = np.asarray([self.chord, self.thickness, self.height])[indices] / 2
        return _box_phi(points - center, half)

    def bbox(self, dimension=3):
        _dimension(dimension)
        indices = [0, 2] if dimension == 2 else [0, 1, 2]
        center = np.asarray([self.x, self.y, self.z])[indices]
        half = np.asarray([self.chord, self.thickness, self.height])[indices] / 2
        return center - half, center + half

    def to_dict(self):
        return {"kind": "endplate", "id": self.id,
                "parameters": {name: getattr(self, name) for name in self.__dataclass_fields__ if name != "id"}}

    def boundary_points(self, spacing, dimension=3):
        """Rectangular face meshes with each coordinate step <=spacing."""
        spacing = _spacing(spacing)
        lo, hi = self.bbox(dimension)
        result = []
        for axis in range(dimension):
            for edge in (lo[axis], hi[axis]):
                axes = [[edge] if i == axis else _linspace(lo[i], hi[i], spacing) for i in range(dimension)]
                result.append(np.stack(np.meshgrid(*axes, indexing="ij"), axis=-1).reshape(-1, dimension))
        return np.unique(np.concatenate(result), axis=0)


@dataclass(frozen=True)
class BoxBody:
    """Convex Lp superellipsoid implicit field with exponent>=2.

    The zero set is sum(abs((x-center)/radii)**exponent)=1. Phi is
    (Lp_norm-1)/|grad Lp_norm|, a first-order distance approximation, not an
    exact SDF for general radii/exponent. In the deep interior (norm<.5), a
    smoothstep blends the normalizer to 1/min(radii), giving a continuous
    centre value phi=-min(radii) instead of a direction-dependent limit.
    This continuation is not monotone along outward rays and can overstate
    interior depth; continuity does not make it an exact distance there.
    Equal radii and exponent=2 take an exact sphere/circle distance shortcut.
    A 2D call evaluates the centred x,z section, not a finite-y extrusion.
    """
    id: str
    center: tuple[float, float, float]
    radii: tuple[float, float, float]
    exponent: float = 2.0

    def __post_init__(self):
        _validate_id(self.id)
        for name in ("center", "radii"):
            values = getattr(self, name)
            if not isinstance(values, (tuple, list, np.ndarray)) or len(values) != 3:
                raise ValueError(f"{name} must contain three coordinates")
            object.__setattr__(self, name, tuple(_number(v, name, name == "radii") for v in values))
        exponent = _number(self.exponent, "exponent")
        if exponent < 2:
            raise ValueError("exponent must be >=2")
        object.__setattr__(self, "exponent", exponent)

    def phi(self, points):
        points = _points(points)
        indices = [0, 2] if points.shape[-1] == 2 else [0, 1, 2]
        radii = np.asarray(self.radii)[indices]
        delta = points - np.asarray(self.center)[indices]
        if self.exponent == 2 and np.all(radii == radii[0]):
            return np.linalg.norm(delta, axis=-1) - radii[0]
        relative = np.abs(delta) / radii
        scale = np.max(relative, axis=-1, keepdims=True)
        normalized = relative / np.where(scale > 0, scale, 1)
        norm = scale[..., 0] * np.sum(normalized ** self.exponent, axis=-1) ** (1 / self.exponent)
        direction = relative / np.where(norm[..., None] > 0, norm[..., None], 1)
        grad_norm = np.linalg.norm(direction ** (self.exponent - 1) / radii, axis=-1)
        blend = np.clip(2 * norm, 0, 1)
        blend = blend * blend * (3 - 2 * blend)
        normalizer = (1 - blend) / np.min(radii) + blend * grad_norm
        return (norm - 1) / normalizer

    def bbox(self, dimension=3):
        _dimension(dimension)
        indices = [0, 2] if dimension == 2 else [0, 1, 2]
        center, radii = np.asarray(self.center)[indices], np.asarray(self.radii)[indices]
        return center - radii, center + radii

    def to_dict(self):
        return {"kind": "box", "id": self.id,
                "parameters": {"center": list(self.center), "radii": list(self.radii), "exponent": self.exponent}}

    def boundary_points(self, spacing, dimension=3):
        """Signed-power angular zero-set samples (angular spacing heuristic).

        Sampling is deterministic. For large exponent the signed-power map can
        stretch angular cells; spacing is not a certified covering radius.
        """
        spacing = _spacing(spacing)
        _dimension(dimension)
        azimuth = _linspace(-np.pi, np.pi, spacing / max(self.radii))
        if dimension == 2:
            unit = np.column_stack((np.cos(azimuth), np.sin(azimuth)))
            indices = [0, 2]
        else:
            elevation = _linspace(-np.pi / 2, np.pi / 2, spacing / max(self.radii))
            a, e = np.meshgrid(azimuth, elevation, indexing="ij")
            unit = np.stack((np.cos(e) * np.cos(a), np.cos(e) * np.sin(a), np.sin(e)), axis=-1).reshape(-1, 3)
            indices = [0, 1, 2]
        power = np.sign(unit) * np.abs(unit) ** (2 / self.exponent)
        return np.asarray(self.center)[indices] + np.asarray(self.radii)[indices] * power


@dataclass(frozen=True)
class MeshBody:
    """Fixed, hash-bound STL with triangle distance and winding-number sign.

    Negative phi denotes solid. ``trimesh.proximity.signed_distance`` uses the
    opposite sign (positive inside) and is deliberately not used: unsigned
    nearest-triangle distance is signed by the solid-angle winding number.
    SRCMAP-02 / GitHub #53 remains INCONCLUSIVE for the registered target
    mesh signer; these synthetic tests do not qualify that target pipeline.
    Meshes must be closed, consistently oriented and positive-volume. SHA256
    is mandatory; construction, phi and serialization verify the current STL
    bytes. The loaded geometry is an internal snapshot of those same bytes.
    Each phi call re-hashes the entire STL and signs distances in
    O(points*triangles) work. Boundary sampling loops over triangles in Python;
    neither path is qualified for car-body mesh sizes before MW-01.
    """
    id: str
    path: str
    sha256: str
    _mesh: trimesh.Trimesh = field(init=False, repr=False, compare=False)

    def __post_init__(self):
        _validate_id(self.id)
        if not isinstance(self.path, (str, Path)) or not str(self.path):
            raise ValueError("path must identify an STL file")
        object.__setattr__(self, "path", str(self.path))
        if not isinstance(self.sha256, str) or re.fullmatch("[0-9a-f]{64}", self.sha256) is None:
            raise ValueError("sha256 must be a lowercase SHA256 digest")
        payload = self._verified_bytes()
        mesh = trimesh.load(io.BytesIO(payload), file_type="stl", force="mesh", process=True)
        if not isinstance(mesh, trimesh.Trimesh) or not len(mesh.faces) or not np.all(np.isfinite(mesh.vertices)):
            raise ValueError("STL must contain a finite triangle mesh")
        if not mesh.is_watertight or not mesh.is_winding_consistent:
            raise ValueError("STL must be watertight with consistent winding")
        if not np.isfinite(mesh.volume) or mesh.volume <= 0:
            raise ValueError("STL must have positive oriented volume")
        object.__setattr__(self, "_mesh", mesh)

    def _verified_bytes(self):
        payload = Path(self.path).read_bytes()
        if hashlib.sha256(payload).hexdigest() != self.sha256:
            raise ValueError(f"STL SHA256 hash mismatch for {self.id}")
        return payload

    def phi(self, points):
        """Re-hash the full STL, then use O(points*triangles) winding work."""
        points = _points(points, (3,))
        self._verified_bytes()
        flat = points.reshape(-1, 3)
        if not len(flat):
            return np.empty(points.shape[:-1], dtype=np.float64)
        _, distance, _ = trimesh.proximity.closest_point(self._mesh, flat)
        result = distance.copy()
        triangles = np.asarray(self._mesh.triangles)
        scale = max(float(np.max(self._mesh.extents)), 1e-300)
        off_surface = np.flatnonzero(distance > 1e-12 * scale)
        chunk_size = max(1, 500000 // len(triangles))
        for start in range(0, len(off_surface), chunk_size):
            selection = off_surface[start:start + chunk_size]
            vectors = triangles[None, ...] - flat[selection, None, None, :]
            a, b, c = vectors[:, :, 0], vectors[:, :, 1], vectors[:, :, 2]
            la, lb, lc = np.linalg.norm(a, axis=-1), np.linalg.norm(b, axis=-1), np.linalg.norm(c, axis=-1)
            numerator = np.einsum("...i,...i->...", a, np.cross(b, c))
            denominator = (la * lb * lc + np.einsum("...i,...i->...", a, b) * lc
                           + np.einsum("...i,...i->...", b, c) * la + np.einsum("...i,...i->...", c, a) * lb)
            winding = np.abs(np.sum(2 * np.arctan2(numerator, denominator), axis=1)) / (4 * np.pi)
            if np.any((winding > 1e-6) & (np.abs(winding - 1) > 1e-6)):
                raise ValueError("ambiguous STL winding number")
            result[selection] *= np.where(winding > 0.5, -1, 1)
        result[distance <= 1e-12 * scale] = 0.0
        return result.reshape(points.shape[:-1])

    def bbox(self, dimension=3):
        _dimension(dimension)
        if dimension != 3:
            raise ValueError("MeshBody supports only 3D coordinates")
        self._verified_bytes()
        return self._mesh.bounds[0].copy(), self._mesh.bounds[1].copy()

    def to_dict(self):
        self._verified_bytes()
        return {"kind": "mesh", "id": self.id, "parameters": {"path": self.path, "sha256": self.sha256}}

    def boundary_points(self, spacing, dimension=3):
        """Barycentric samples, edge steps<=spacing; Python loops per triangle.

        The full STL is re-hashed first. Sample count also grows with face area
        divided by spacing squared; this is a small-mesh diagnostic path.
        """
        spacing = _spacing(spacing)
        _dimension(dimension)
        if dimension != 3:
            raise ValueError("MeshBody supports only 3D coordinates")
        self._verified_bytes()
        result = []
        for a, b, c in self._mesh.triangles:
            segments = max(1, int(np.ceil(max(np.linalg.norm(b - a), np.linalg.norm(c - a), np.linalg.norm(c - b)) / spacing)))
            for i in range(segments + 1):
                j = np.arange(segments - i + 1)
                result.append(a + (i / segments) * (b - a) + (j[:, None] / segments) * (c - a))
        return np.unique(np.concatenate(result), axis=0)
