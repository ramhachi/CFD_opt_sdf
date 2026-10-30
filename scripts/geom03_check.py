#!/usr/bin/env python3
"""Independent input, metric and run checker for GEOM-03.

No cfd_sdf imports, no production state constructors, no SciPy interpolators.
Core metrics: R0, R3, P1, P2 and composite verdict, plus R3 sign-body hashes.
"""
from __future__ import annotations

import hashlib
import json
import math
import platform
import re
import subprocess
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import scipy
from scipy import ndimage

ROOT = Path(__file__).resolve().parents[1]

LENGTH_TOLERANCE_M = 1e-9
R0_LIMIT_CELLS = 1.5
R0_GUARD_CELLS = 0.25
FEATURE_SUPERSAMPLE = 4
R3_K = 4
R3_RADIUS_CELLS = 3
R3_TAU_CELLS = 1.0
R3_PAD = 3

_STATUS_ORDER = {"pass": 0, "unmeasured": 1, "fail": 2, "blocked": 3}
_S26 = np.ones((3, 3, 3), dtype=bool)
_P2_GATE_IDS = ("mask_preservation", "component_connectivity", "topology_change_classification")
_P2_MASK_NAMES = ("fixed_solid_mask", "forbidden_mask", "root_mask")


def _worst(*statuses: str) -> str:
    return max(statuses, key=lambda s: _STATUS_ORDER.get(s, 3))


def _box(mask: np.ndarray, pad: int) -> tuple[slice, ...]:
    """Solid AABB crop with ``pad`` cells of padding, clipped to the array."""
    idx = np.argwhere(mask)
    if idx.size == 0:
        return tuple(slice(0, 0) for _ in mask.shape)
    return tuple(
        slice(max(a - pad, 0), min(b + pad + 1, n))
        for a, b, n in zip(idx.min(axis=0), idx.max(axis=0), mask.shape)
    )


def _corner_mean(phi: np.ndarray) -> np.ndarray:
    """Exact float32 eight-corner centre mean (volume_semantics source order)."""
    return (
        phi[:-1, :-1, :-1]
        + phi[1:, :-1, :-1]
        + phi[:-1, 1:, :-1]
        + phi[:-1, :-1, 1:]
        + phi[1:, 1:, :-1]
        + phi[1:, :-1, 1:]
        + phi[:-1, 1:, 1:]
        + phi[1:, 1:, 1:]
    ) * np.float32(0.125)


def _min_feature_width_m(mask: np.ndarray, spacing_m: float) -> float | None:
    """Local copy of the registered 4x EDT ridge-width estimator."""
    if not mask.any() or mask.all():
        return None
    up = np.pad(mask, 1, mode="edge")
    for axis in range(3):
        up = np.repeat(up, FEATURE_SUPERSAMPLE, axis=axis)
    distance = ndimage.distance_transform_edt(up, sampling=spacing_m / FEATURE_SUPERSAMPLE)
    ridge = up & (distance >= ndimage.maximum_filter(distance, size=3) - 1e-12)
    pad = FEATURE_SUPERSAMPLE
    interior_distance = distance[pad:-pad, pad:-pad, pad:-pad]
    interior_ridge = ridge[pad:-pad, pad:-pad, pad:-pad]
    if not interior_ridge.any():
        return None
    return float(2.0 * interior_distance[interior_ridge].min())


def _r0_status(w: float | None, h: float, *, void: bool = False) -> str:
    if w is None:
        return "pass" if void else "unmeasured"
    lo = (R0_LIMIT_CELLS - R0_GUARD_CELLS) * h
    hi = (R0_LIMIT_CELLS + R0_GUARD_CELLS) * h
    if w < lo - LENGTH_TOLERANCE_M:
        return "fail"
    if w <= hi + LENGTH_TOLERANCE_M:
        return "unmeasured"
    return "pass"


def _r0(phi: np.ndarray, h: float) -> dict[str, Any]:
    """Registered R0: 4x-repeated cell-occupancy EDT ridge minimum."""
    occ = _corner_mean(phi) < 0.0
    if not occ.any():
        return {"solid": None, "void": None, "status": "unmeasured"}
    crop = occ[_box(occ, 1)]
    solid_w = _min_feature_width_m(crop, float(h))
    void_w = _min_feature_width_m(~crop, float(h))
    return {
        "solid": solid_w,
        "void": void_w,
        "status": _worst(_r0_status(solid_w, h), _r0_status(void_w, h, void=True)),
    }


def _trilinear_refine(phi: np.ndarray, k: int = R3_K) -> np.ndarray:
    """Separable trilinear refinement at fractional positions j/k in float64."""
    arr = np.asarray(phi, dtype=np.float64)
    for axis in range(3):
        n = arr.shape[axis]
        m = (n - 1) * k + 1
        frac = np.arange(m) / k
        i0 = np.floor(frac).astype(int)
        i1 = np.minimum(i0 + 1, n - 1)
        w1 = frac - i0
        w0 = 1.0 - w1
        shape = [1, 1, 1]
        shape[axis] = m
        arr = (
            w0.reshape(shape) * np.take(arr, i0, axis=axis)
            + w1.reshape(shape) * np.take(arr, i1, axis=axis)
        )
    return arr


def _r3_ball() -> np.ndarray:
    """Closed Euclidean digital ball of radius 3 refined cells."""
    c = R3_RADIUS_CELLS
    grid = np.indices((2 * c + 1, 2 * c + 1, 2 * c + 1)) - c
    return (grid[0] ** 2 + grid[1] ** 2 + grid[2] ** 2) <= R3_RADIUS_CELLS ** 2


def _opening_defect(body: np.ndarray, h: float) -> float | None:
    """Morphological opening defect with radius = 3 refined cells."""
    if not body.any():
        return None
    ball = _r3_ball()
    eroded = ndimage.binary_erosion(body, structure=ball, border_value=1)
    if not eroded.any():
        return math.inf
    opened = ndimage.binary_dilation(eroded, structure=ball, border_value=0)
    removed = body & ~opened
    if not removed.any():
        return 0.0
    dist = ndimage.distance_transform_edt(~opened, sampling=float(h) / R3_K)
    return float(dist[removed].max())


def _r3_status(d: float | None, h: float, *, void: bool = False) -> str:
    if d is None:
        return "pass" if void else "unmeasured"
    tau = R3_TAU_CELLS * h
    if d <= tau + LENGTH_TOLERANCE_M:
        return "pass"
    if d <= tau + (h / R3_K) + LENGTH_TOLERANCE_M:
        return "unmeasured"
    return "fail"


def _r3(phi: np.ndarray, h: float) -> dict[str, Any]:
    """R3 opening-defect rule on the h/4 trilinear refinement."""
    solid = phi < 0.0
    if not solid.any():
        return {"solid": None, "void": None, "status": "unmeasured"}
    crop = phi[_box(solid, R3_PAD)].astype(np.float64)
    refined = _trilinear_refine(crop, R3_K)
    B = refined < 0.0
    s = _opening_defect(B, h)
    v = _opening_defect(~B, h)
    return {
        "solid": s,
        "void": v,
        "status": _worst(_r3_status(s, h), _r3_status(v, h, void=True)),
    }


def _p1(phi: np.ndarray, parent_phi: np.ndarray, masks: dict[str, np.ndarray], h: float) -> dict[str, Any]:
    active = (
        masks["design_mask"]
        & ~masks["fixed_solid_mask"]
        & ~masks["forbidden_mask"]
        & ~masks["root_mask"]
    )
    frozen = ~active
    if not frozen.any():
        raise ValueError("empty frozen node mask is an input error")
    parent_m = float(np.abs(parent_phi[frozen]).min())
    cand_m = float(np.abs(phi[frozen]).min())
    half = float(h) / 2.0
    return {
        "parent_margin_m": parent_m,
        "candidate_margin_m": cand_m,
        "status": "pass" if (parent_m >= half and cand_m >= half) else "fail",
    }


def _mask_preservation_status(phi_solid: np.ndarray, masks: dict[str, np.ndarray]) -> list[str]:
    allowed = masks["design_mask"] | masks["fixed_solid_mask"] | masks["root_mask"]
    fail: list[str] = []
    if np.any(phi_solid & masks["forbidden_mask"]):
        fail.append("material_in_forbidden_mask")
    if np.any(phi_solid & ~allowed):
        fail.append("material_outside_design_fixed_root_masks")
    if np.any(masks["fixed_solid_mask"] & ~phi_solid):
        fail.append("fixed_solid_not_retained")
    if np.any(masks["root_mask"] & ~phi_solid):
        fail.append("root_material_not_retained")
    return fail


def _events(parent_labels: np.ndarray, parent_count: int, cand_labels: np.ndarray, cand_count: int) -> list[str]:
    old_to_new: dict[int, set[int]] = {i: set() for i in range(1, parent_count + 1)}
    new_to_old: dict[int, set[int]] = {j: set() for j in range(1, cand_count + 1)}
    overlap = (parent_labels > 0) & (cand_labels > 0)
    if overlap.any():
        pairs = np.unique(np.stack((parent_labels[overlap], cand_labels[overlap]), axis=1), axis=0)
        for o, n in pairs:
            old_to_new[int(o)].add(int(n))
            new_to_old[int(n)].add(int(o))
    events: list[str] = []
    if any(not owners for owners in new_to_old.values()):
        events.append("birth")
    if any(not children for children in old_to_new.values()):
        events.append("deletion")
    if any(len(children) > 1 for children in old_to_new.values()):
        events.append("split")
    if any(len(parents) > 1 for parents in new_to_old.values()):
        events.append("merge")
    return sorted(events)


def _p2(phi: np.ndarray, parent_phi: np.ndarray, masks: dict[str, np.ndarray], policy: Any) -> dict[str, Any]:
    parent_solid = parent_phi < 0.0
    cand_solid = phi < 0.0
    parent_labels, parent_count = ndimage.label(parent_solid, structure=_S26)
    cand_labels, cand_count = ndimage.label(cand_solid, structure=_S26)

    parent_mp = _mask_preservation_status(parent_solid, masks)
    cand_mp = _mask_preservation_status(cand_solid, masks)
    mp_status = "fail" if (parent_mp or cand_mp) else "pass"

    cc_fail: list[str] = []
    if parent_count == 0:
        cc_fail.append("current_solid_is_empty")
    if cand_count == 0:
        cc_fail.append("proposed_solid_is_empty")
    max_components = getattr(policy, "max_components", None)
    if max_components is not None and max(parent_count, cand_count) > max_components:
        cc_fail.append("solid_component_count_exceeds_policy_limit")
    cc_status = "fail" if cc_fail else "pass"

    event_list = _events(parent_labels, parent_count, cand_labels, cand_count)
    tc_status = "fail" if event_list else "pass"

    statuses = {
        "mask_preservation": mp_status,
        "component_connectivity": cc_status,
        "topology_change_classification": tc_status,
    }
    empty_masks = [name.removesuffix("_mask") for name in _P2_MASK_NAMES if not masks[name].any()]
    return {
        "statuses": statuses,
        "events": event_list,
        "parent_components": parent_count,
        "candidate_components": cand_count,
        "empty_masks": empty_masks,
    }


def _validate_pair(phi: np.ndarray, parent_phi: np.ndarray, masks: dict[str, np.ndarray], h: float, policy: Any) -> None:
    if not isinstance(phi, np.ndarray) or phi.dtype != np.float32 or phi.ndim != 3 or not np.isfinite(phi).all():
        raise ValueError("phi must be a finite 3D float32 array")
    if not isinstance(parent_phi, np.ndarray) or parent_phi.dtype != np.float32 or parent_phi.shape != phi.shape or not np.isfinite(parent_phi).all():
        raise ValueError("parent_phi must be a finite 3D float32 array matching phi")
    if isinstance(h, bool) or not isinstance(h, (int, float, np.floating)) or not math.isfinite(h) or h <= 0.0:
        raise ValueError("h must be finite and positive")
    for name in ("design_mask", "fixed_solid_mask", "forbidden_mask", "root_mask"):
        m = masks.get(name)
        if not isinstance(m, np.ndarray) or m.dtype != bool or m.shape != phi.shape:
            raise ValueError(f"{name} must be a bool ndarray matching phi")
    if not hasattr(policy, "state_binding_id") or not hasattr(policy, "max_components"):
        raise TypeError("policy must expose state_binding_id and max_components")


def check_pair(
    phi: np.ndarray,
    parent_phi: np.ndarray,
    masks: dict[str, np.ndarray],
    h: float,
    policy: Any,
    origin_m: tuple[float, float, float] = (0.0, 0.0, 0.0),
) -> dict[str, Any]:
    """Evaluate one candidate against its parent under the GEOM-03 core metrics."""
    _validate_pair(phi, parent_phi, masks, h, policy)

    r0 = _r0(phi, h)
    r3 = _r3(phi, h)
    p1 = _p1(phi, parent_phi, masks, h)
    p2 = _p2(phi, parent_phi, masks, policy)
    p2s = _worst(*p2["statuses"].values())

    if p1["status"] == "fail":
        composite = "blocked"
    elif r3["status"] == "unmeasured" and p2s == "pass":
        composite = "unmeasured"
    else:
        composite = _worst(r3["status"], p2s, p1["status"])

    return {"r0": r0, "r3": r3, "p1": p1, "p2": p2, "composite": composite}


def _sign_observations(phi: np.ndarray) -> tuple[dict[str, str | None], int]:
    if not isinstance(phi, np.ndarray) or phi.dtype != np.float32 or phi.ndim != 3 or not np.isfinite(phi).all():
        raise ValueError("phi must be a finite 3D float32 array")
    solid = phi < 0.0
    if not solid.any():
        return {"solid": None, "void": None}, 0
    crop = phi[_box(solid, R3_PAD)].astype(np.float64)
    refined = _trilinear_refine(crop, R3_K)
    B = refined < 0.0

    def _sha(a: np.ndarray) -> str:
        return hashlib.sha256(np.asarray(a, bool).tobytes()).hexdigest()

    return {"solid": _sha(B), "void": _sha(~B)}, int(ndimage.label(B, structure=_S26)[1])


def sign_body_hashes(phi: np.ndarray) -> dict[str, str | None]:
    """SHA-256 identities of the R3 sampled solid and void sign bodies."""
    return _sign_observations(phi)[0]


# ---------------------------------------------------------------------------
# Independent input reconstruction and metadata enumeration (GEOM-03)

_H = 0.025


def _p8(j: int) -> tuple[float, float, float]:
    return (
        (2 * j + 1) / 16 - 0.5,
        (2 * ((3 * j) % 8) + 1) / 16 - 0.5,
        (2 * ((5 * j) % 8) + 1) / 16 - 0.5,
    )


_Q2 = ((1 / 8, 3 / 16, 5 / 16), (-5 / 16, -3 / 16, -1 / 16))


def _local_coords(theta_deg: float, phase: tuple[float, ...], n: int = 27, *, merge_center: bool = False) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    idx = np.indices((n, n, n), dtype=np.float64)
    c = np.asarray([13.5 if merge_center else 13.0, 13.0, 13.0]) + np.asarray(phase, dtype=np.float64)
    p = idx - c.reshape(3, 1, 1, 1)
    th = math.radians(theta_deg)
    ct, st = math.cos(th), math.sin(th)
    x, y, z = p[0], p[1], p[2]
    return (ct * x - st * z, y, st * x + ct * z)


def _box_sdf(qx: np.ndarray, qy: np.ndarray, qz: np.ndarray, b: tuple[float, float, float]) -> np.ndarray:
    d0, d1, d2 = np.abs(qx) - b[0], np.abs(qy) - b[1], np.abs(qz) - b[2]
    outside = np.sqrt(np.maximum(d0, 0.0) ** 2 + np.maximum(d1, 0.0) ** 2 + np.maximum(d2, 0.0) ** 2)
    return outside + np.minimum(np.maximum(np.maximum(d0, d1), d2), 0.0)


def _product(d: np.ndarray, v: np.ndarray) -> np.ndarray:
    return np.minimum(np.maximum(d, v), 0.0) + np.hypot(np.maximum(d, 0.0), np.maximum(v, 0.0))


def _wedge_planar(x: np.ndarray, z: np.ndarray, theta_deg: float) -> np.ndarray:
    t = math.tan(math.radians(theta_deg) / 2)
    a = min(8 * t, 2.5)
    v = 4 - a / t
    verts = [(-4.0, -a), (v, -a), (4.0, 0.0), (v, a), (-4.0, a)]
    poly = []
    for pv in verts:
        if not poly or pv[0] != poly[-1][0] or pv[1] != poly[-1][1]:
            poly.append(pv)
    while len(poly) > 1 and poly[0] == poly[-1]:
        poly.pop()
    d = None
    for i in range(len(poly)):
        (x0, z0), (x1, z1) = poly[i], poly[(i + 1) % len(poly)]
        ex, ez = x1 - x0, z1 - z0
        denom = ex * ex + ez * ez
        s = 0.0 if denom == 0 else np.clip(((x - x0) * ex + (z - z0) * ez) / denom, 0.0, 1.0)
        seg = np.sqrt((x - x0 - s * ex) ** 2 + (z - z0 - s * ez) ** 2)
        d = seg if d is None else np.minimum(d, seg)
    inside = (x >= -4) & (x <= 4) & (np.abs(z) <= np.minimum((4 - x) * t, 2.5))
    return np.where(inside, -d, d)


def _field_values(name: str, q: tuple[np.ndarray, np.ndarray, np.ndarray]) -> np.ndarray:
    qx, qy, qz = q
    if name == "bar":
        return _product(np.hypot(qx, qz) - 2.75, np.abs(qy) - 3.5)
    if name == "stadium":
        return _product(np.hypot(np.maximum(np.abs(qx) - 5.0, 0.0), qz) - 2.75, np.abs(qy) - 3.5)
    if name == "thickbox":
        return _box_sdf(qx, qy, qz, (4.5, 3.5, 2.5))
    if name == "fin_parent":
        return _box_sdf(qx, qy, qz, (3.5, 3.0, 2.5))
    if name == "S1":
        return _box_sdf(qx, qy, qz, (4.5, 4.0, 0.875 / 2))
    if name == "S2":
        return _box_sdf(qx, qy, qz, (4.5, 4.0, 1.125 / 2))
    if name == "S3":
        return _box_sdf(qx, qy, qz, (4.5, 4.0, 4.75 / 2))
    if name == "T1":
        return _box_sdf(qx, qy, qz, (4.5, 4.0, 1.625 / 2))
    if name == "T2":
        return _box_sdf(qx, qy, qz, (4.5, 4.0, 1.875 / 2))
    if name == "V1":
        return np.maximum(_box_sdf(qx, qy, qz, (6.5, 6.5, 5.5)), -_box_sdf(qx, qy, qz, (0.875 / 2, 4.25, 3.5)))
    if name == "V2":
        return np.maximum(_box_sdf(qx, qy, qz, (6.5, 6.5, 5.5)), -_box_sdf(qx, qy, qz, (1.125 / 2, 4.25, 3.5)))
    if name == "V3":
        return np.maximum(_box_sdf(qx, qy, qz, (6.5, 6.5, 5.5)), -_box_sdf(qx, qy, qz, (3.5 / 2, 4.25, 3.5)))
    if name == "V4":
        return np.maximum(_box_sdf(qx, qy, qz, (6.5, 6.5, 5.5)), -_box_sdf(qx, qy, qz - 3.5, (0.875 / 2, 4.25, 4.0)))
    if name == "V5":
        return np.maximum(_box_sdf(qx, qy, qz, (6.5, 6.5, 5.5)), -_box_sdf(qx, qy, qz - 3.5, (3.5 / 2, 4.25, 4.0)))
    if name in ("N0", "N1", "N2"):
        d = {"N0": 2.5, "N1": 0.875, "N2": 0.375}[name]
        return np.minimum(
            np.minimum(
                np.sqrt((qx - 4.75) ** 2 + qy ** 2 + qz ** 2) - 2.5,
                np.sqrt((qx + 4.75) ** 2 + qy ** 2 + qz ** 2) - 2.5,
            ),
            _product(np.hypot(qy, qz) - d / 2, np.abs(qx) - 4.75),
        )
    if name == "F1":
        return np.minimum(_box_sdf(qx, qy, qz, (3.5, 3.0, 2.5)), _box_sdf(qx - 3.625, qy, qz, (0.375, 1.5, 0.5)))
    if name == "F2":
        return np.minimum(_box_sdf(qx, qy, qz, (3.5, 3.0, 2.5)), _box_sdf(qx - 5.625, qy, qz, (2.375, 1.5, 0.5)))
    if name == "A0":
        g = 2.5
        return np.minimum(
            _box_sdf(qx - (2 + g / 2), qy, qz, (2.0, 2.5, 2.5)),
            _box_sdf(qx + (2 + g / 2), qy, qz, (2.0, 2.5, 2.5)),
        )
    if name == "A1":
        g = 0.25
        return np.minimum(
            _box_sdf(qx - (2 + g / 2), qy, qz, (2.0, 2.5, 2.5)),
            _box_sdf(qx + (2 + g / 2), qy, qz, (2.0, 2.5, 2.5)),
        )
    if name in ("W20", "W40", "W60", "W90"):
        deg = {"W20": 20.0, "W40": 40.0, "W60": 60.0, "W90": 90.0}[name]
        return _product(_wedge_planar(qx, qz, deg), np.abs(qy) - 3.0)
    raise ValueError(f"unknown analytic field {name}")


def _ordinary_masks(n: int = 27) -> dict[str, np.ndarray]:
    design = np.zeros((n, n, n), dtype=bool)
    design[2:-2, 2:-2, 2:-2] = True
    false = np.zeros((n, n, n), dtype=bool)
    return {
        "design_mask": design,
        "fixed_solid_mask": false.copy(),
        "forbidden_mask": false.copy(),
        "root_mask": false.copy(),
    }


def _k5_masks(n: int = 27) -> dict[str, np.ndarray]:
    design = np.zeros((n, n, n), dtype=bool)
    design[:, :, 1:-1] = True
    false = np.zeros((n, n, n), dtype=bool)
    return {
        "design_mask": design,
        "fixed_solid_mask": false.copy(),
        "forbidden_mask": false.copy(),
        "root_mask": false.copy(),
    }


def _has_halo(phi: np.ndarray) -> bool | None:
    solid = phi < 0.0
    if not solid.any():
        return None
    idx = np.argwhere(solid)
    top = np.asarray(phi.shape) - 1
    return bool(((idx.min(axis=0) - R3_PAD) >= 0).all() and ((idx.max(axis=0) + R3_PAD) <= top).all())


def _overlap_relation(
    parent_labels: np.ndarray,
    parent_count: int,
    cand_labels: np.ndarray,
    cand_count: int,
) -> dict[str, Any]:
    old_to_new = {i: set() for i in range(1, parent_count + 1)}
    new_to_old = {j: set() for j in range(1, cand_count + 1)}
    overlap = (parent_labels > 0) & (cand_labels > 0)
    if overlap.any():
        pairs = np.unique(np.stack((parent_labels[overlap], cand_labels[overlap]), axis=1), axis=0)
        for o, n in pairs:
            old_to_new[int(o)].add(int(n))
            new_to_old[int(n)].add(int(o))
    return {
        "old_to_new": {k: sorted(v) for k, v in old_to_new.items()},
        "new_to_old": {k: sorted(v) for k, v in new_to_old.items()},
    }


def _feature_proof(spec: dict[str, Any], phi: np.ndarray, parent_phi: np.ndarray, h: float) -> dict[str, Any] | None:
    build = spec.get("build")
    proof: dict[str, Any] = {}
    if build not in ("k5", "e2"):
        proof["halo"] = {"parent": _has_halo(parent_phi), "candidate": _has_halo(phi)}

    if build == "analytic" or build == "margin_control":
        q = _local_coords(spec["theta_deg"], spec["phase"], 27, merge_center=spec.get("field") in ("A0", "A1"))
        qx, qy, qz = q
        neg = phi.astype(np.float64) < 0.0
        pos = phi.astype(np.float64) > 0.0
        base = spec.get("field", "")
        if base in ("S1", "S2"):
            w = 0.875 if base == "S1" else 1.125
            inside = _box_sdf(qx, qy, qz, (4.5, 4.0, w / 2)) < 0.0
            proof["negative_node_in_box"] = int((neg & inside).sum())
        elif base in ("V1", "V2"):
            w = 0.875 if base == "V1" else 1.125
            void = _box_sdf(qx, qy, qz, (w / 2, 4.25, 3.5)) < 0.0
            proof["positive_node_in_closed_void"] = int((pos & void).sum())
        elif base == "V4":
            void = _box_sdf(qx, qy, qz - 3.5, (0.875 / 2, 4.25, 4.0)) < 0.0
            proof["positive_node_in_open_slot"] = int((pos & void & (qz < 5.5)).sum())
        elif base == "N1":
            neck = np.abs(qx) < 2.25
            proof["negative_node_in_neck"] = int((neg & neck).sum())
        elif base == "F2":
            tail = _box_sdf(qx - 5.625, qy, qz, (2.375, 1.5, 0.5)) < 0.0
            proof["negative_node_outside_parent_fin"] = int((neg & tail & (qx > 3.5)).sum())
        elif base in ("W20", "W40"):
            deg = 20.0 if base == "W20" else 40.0
            tip = (4 - 1.5 / (2 * math.tan(math.radians(deg) / 2)) < qx) & (qx < 4)
            proof["negative_node_in_thin_tip"] = int((neg & tip).sum())
        elif base == "F1":
            tail = _box_sdf(qx - 3.625, qy, qz, (0.375, 1.5, 0.5)) < 0.0
            coarse = int((neg & tail & (qx > 3.5)).sum())
            solid = phi < 0.0
            refined_count = 0
            if solid.any():
                sl = _box(solid, R3_PAD)
                qx_c, qy_c, qz_c = (comp[sl].astype(np.float64) for comp in q)
                qx_r = _trilinear_refine(qx_c, R3_K)
                qy_r = _trilinear_refine(qy_c, R3_K)
                qz_r = _trilinear_refine(qz_c, R3_K)
                refined = _trilinear_refine(phi[sl].astype(np.float64), R3_K) < 0.0
                tail_r = _box_sdf(qx_r - 3.625, qy_r, qz_r, (0.375, 1.5, 0.5)) < 0.0
                refined_count = int((refined & tail_r & (qx_r > 3.5)).sum())
            proof["fin_protrusion_counts"] = {"coarse": coarse, "refined": refined_count}

    if build == "analytic":
        base = spec.get("field", "")
        parent_solid = parent_phi < 0.0
        cand_solid = phi < 0.0
        parent_labels, parent_count = ndimage.label(parent_solid, structure=_S26)
        cand_labels, cand_count = ndimage.label(cand_solid, structure=_S26)
        if base == "N2":
            proof["neck_split"] = {
                "parent_components": parent_count,
                "candidate_components": cand_count,
                "overlap": _overlap_relation(parent_labels, parent_count, cand_labels, cand_count),
            }
        elif base in ("A0", "A1"):
            proof["boxes_merge" if base == "A1" else "boxes_identity"] = {
                "parent_components": parent_count,
                "candidate_components": cand_count,
                "overlap": _overlap_relation(parent_labels, parent_count, cand_labels, cand_count),
            }

    if build == "d1":
        solid = phi < 0.0
        _, coarse_count = ndimage.label(solid, structure=_S26)
        proof["coarse_components"] = coarse_count
        refined_count = 0
        if solid.any():
            sl = _box(solid, R3_PAD)
            refined = _trilinear_refine(phi[sl].astype(np.float64), R3_K) < 0.0
            _, refined_count = ndimage.label(refined, structure=_S26)
        proof["refined_components"] = refined_count

    return proof if proof else None


def _load_v18_parent(known_bindings: dict[str, Any], reasons: list[str]) -> dict[str, Any]:
    info = known_bindings["parent"]
    path = ROOT / info["path"]
    npz_bytes = path.read_bytes()
    if hashlib.sha256(npz_bytes).hexdigest() != info["npz_sha256"]:
        reasons.append("parent_npz_hash_mismatch")
    with np.load(path, allow_pickle=False) as data:
        phi = data["phi"]
        if phi.dtype.str != "<f4" or list(phi.shape) != info["shape"] or not np.isfinite(phi).all():
            raise ValueError("invalid frozen parent shape/dtype/values")
        masks = {
            name: data[name] for name in ("design_mask", *_P2_MASK_NAMES)
        }
        if any(m.dtype != bool or m.shape != phi.shape for m in masks.values()):
            raise ValueError("invalid frozen parent mask shape/dtype")
        metadata = _strict_json(str(data["metadata"].item()))
        phi_sha = hashlib.sha256(np.asarray(phi, "<f4").tobytes(order="F")).hexdigest()
        if phi_sha != info["phi_fortran_sha256"]:
            reasons.append("parent_phi_hash_mismatch")
        for name, expected in info["mask_fortran_sha256"].items():
            msha = hashlib.sha256(np.asarray(masks[name], bool).tobytes(order="F")).hexdigest()
            if msha != expected:
                reasons.append(f"parent_mask_hash_mismatch:{name}")
        result = {
            "phi": phi,
            "masks": masks,
            "origin_m": tuple(float(v) for v in metadata["origin_m"]),
            "spacing_m": float(metadata["spacing_m"]),
            "metadata": metadata,
        }
    return result


def _combo_schedule(known_bindings: dict[str, Any]) -> list[dict[str, Any]]:
    names = [entry["mode"] for entry in known_bindings["ordered_basis"]]
    rng = np.random.Generator(np.random.PCG64(np.random.SeedSequence([20261023, 1])))
    out = []
    for _ in range(28):
        n = int(rng.integers(2, 4))
        sel = [str(x) for x in rng.choice(np.asarray(names), size=n, replace=False)]
        coeffs = [float(c) for c in rng.uniform(-1.0, 1.0, size=n)]
        out.append({"names": sel, "coefficients": coeffs})
    return out


def _find_basis_array(raw: dict[str, np.ndarray], mode: str) -> np.ndarray:
    keys = [k for k in raw if isinstance(k, str) and (k == f"basis_{mode}" or k.endswith(f"_{mode}"))]
    if len(keys) != 1:
        raise KeyError(f"basis array for {mode} not found")
    return raw[keys[0]]


def _build_analytic(spec: dict[str, Any]) -> tuple[np.ndarray, np.ndarray, dict[str, np.ndarray], tuple[float, float, float], float]:
    n = 27
    q = _local_coords(spec["theta_deg"], spec["phase"], n, merge_center=spec["field"] in ("A0", "A1"))
    cand_vals = _field_values(spec["field"], q)
    parent_field = spec.get("parent_field", "identity")
    parent_vals = cand_vals.copy() if parent_field == "identity" else _field_values(parent_field, q)
    phi = (cand_vals * _H).astype("<f4")
    parent_phi = (parent_vals * _H).astype("<f4")
    return phi, parent_phi, _ordinary_masks(n), (0.0, 0.0, 0.0), _H


def _build_margin_control(spec: dict[str, Any]) -> tuple[np.ndarray, np.ndarray, dict[str, np.ndarray], tuple[float, float, float], float]:
    q = _local_coords(spec["theta_deg"], spec["phase"], 27)
    vals = _field_values(spec["field"], q)
    phi = (vals * _H).astype("<f4")
    phi[(0, 0, 0)] = np.float32(spec["corner_phi_h"])
    parent_field = spec.get("parent_field", "identity")
    if parent_field == "identity":
        parent_phi = phi.copy()
    elif parent_field == "R0":
        parent_vals = _field_values("bar", q)
        parent_phi = (parent_vals * _H).astype("<f4")
        parent_phi[(0, 0, 0)] = np.float32(_H / 2.0)
    else:
        raise ValueError(f"unknown margin-control parent {parent_field}")
    return phi, parent_phi, _ordinary_masks(), (0.0, 0.0, 0.0), _H


def _build_d1() -> tuple[np.ndarray, np.ndarray, dict[str, np.ndarray], tuple[float, float, float], float]:
    phi = np.full((27, 27, 27), _H * 0.75, dtype="<f4")
    phi[(12, 12, 13)] = np.float32(-_H * 0.25)
    phi[(13, 13, 13)] = np.float32(-_H * 0.25)
    return phi, phi.copy(), _ordinary_masks(), (0.0, 0.0, 0.0), _H


def _build_e1() -> tuple[np.ndarray, np.ndarray, dict[str, np.ndarray], tuple[float, float, float], float]:
    phi = np.full((27, 27, 27), _H, dtype="<f4")
    return phi, phi.copy(), _ordinary_masks(), (0.0, 0.0, 0.0), _H


def _build_e2() -> tuple[np.ndarray, np.ndarray, dict[str, np.ndarray], tuple[float, float, float], float]:
    phi = np.full((5, 5, 5), -_H, dtype="<f4")
    design = np.ones((5, 5, 5), dtype=bool)
    false = np.zeros((5, 5, 5), dtype=bool)
    masks = {
        "design_mask": design,
        "fixed_solid_mask": false.copy(),
        "forbidden_mask": false.copy(),
        "root_mask": false.copy(),
    }
    return phi, phi.copy(), masks, (0.0, 0.0, 0.0), _H / R3_K


def _build_k5(spec: dict[str, Any]) -> tuple[np.ndarray, np.ndarray, dict[str, np.ndarray], tuple[float, float, float], float]:
    n = 27
    h = _H
    w = spec["width_h"]
    phase_z = spec["phase_z"]
    z = np.arange(n, dtype=np.float64).reshape(1, 1, n)
    phi_vals = np.broadcast_to(h * (np.abs(z - (13.0 + phase_z)) - w / 2.0), (n, n, n)).copy()
    parent_vals = np.broadcast_to(h * (np.abs(z - (13.0 + phase_z)) - 3.5 / 2.0), (n, n, n)).copy()
    phi = phi_vals.astype("<f4")
    parent_phi = parent_vals.astype("<f4")
    return phi, parent_phi, _k5_masks(n), (0.0, 0.0, 0.0), h


def _build_historical(
    known_bindings: dict[str, Any], reasons: list[str]
) -> tuple[np.ndarray, np.ndarray, dict[str, np.ndarray], tuple[float, float, float], float]:
    p = _load_v18_parent(known_bindings, reasons)
    phi = p["phi"]
    return phi, phi.copy(), p["masks"], p["origin_m"], p["spacing_m"]


def _build_v18_combo(
    spec: dict[str, Any],
    raw: dict[str, np.ndarray],
    known_bindings: dict[str, Any],
    reasons: list[str],
) -> tuple[np.ndarray, np.ndarray, dict[str, np.ndarray], tuple[float, float, float], float]:
    i = spec["combo_index"]
    sched = _combo_schedule(known_bindings)[i]
    parent = _load_v18_parent(known_bindings, reasons)
    parent64 = parent["phi"].astype(np.float64)
    active = (
        parent["masks"]["design_mask"]
        & ~parent["masks"]["fixed_solid_mask"]
        & ~parent["masks"]["forbidden_mask"]
        & ~parent["masks"]["root_mask"]
    )
    deltas = []
    known_by_mode = {entry["mode"]: entry for entry in known_bindings["ordered_basis"]}
    for mode in sched["names"]:
        known = known_by_mode.get(mode)
        if known is None:
            reasons.append(f"unknown_basis:{mode}")
            continue
        arr = _find_basis_array(raw, mode)
        if arr.dtype.str != "<f4" or arr.shape != parent64.shape or not np.isfinite(arr).all():
            raise ValueError(f"invalid basis dtype/shape/values:{mode}")
        arr32 = arr
        arr_sha = hashlib.sha256(arr32.tobytes(order="F")).hexdigest()
        if arr_sha != known["phi_fortran_sha256"]:
            reasons.append(f"basis_hash_mismatch:{mode}")
        deltas.append(arr32.astype(np.float64) - parent64)
    acc = None
    for c, delta in zip(sched["coefficients"], deltas):
        term = c * delta
        acc = term if acc is None else acc + term
    phi64 = parent64 + (0.0 if acc is None else acc)
    if i >= 20:
        noise_rng = np.random.Generator(np.random.PCG64(np.random.SeedSequence([20261023, 2, i])))
        noise = noise_rng.uniform(-parent["spacing_m"] / 16.0, parent["spacing_m"] / 16.0, size=parent64.shape)
        phi64 = phi64 + np.where(active, noise, 0.0)
    phi64 = np.where(active, phi64, parent64)
    phi = phi64.astype("<f4")
    return phi, parent["phi"].copy(), parent["masks"], parent["origin_m"], parent["spacing_m"]


def expected_base_specs() -> dict[str, dict[str, Any]]:
    """Return the 180 base-row spec metadata (no arrays, no RNG)."""
    specs: dict[str, dict[str, Any]] = {}
    for shape in ("bar", "stadium", "thickbox"):
        for j in range(8):
            sid = f"{shape}_p8_{j}"
            specs[sid] = {
                "id": sid,
                "family": "k1_analytic",
                "build": "analytic",
                "field": shape,
                "theta_deg": 0.0,
                "phase": _p8(j),
                "parent_field": "identity",
            }
    for i in range(28):
        sid = f"C{i:02d}"
        specs[sid] = {"id": sid, "family": "k1_combos", "build": "v18_combo", "combo_index": i}
    fields = [
        "S1", "S2", "S3", "V1", "V2", "V3", "V4", "V5",
        "N0", "N1", "N2", "F1", "F2",
        "W20", "W40", "W60", "W90", "T1", "T2",
    ]
    for fld in fields:
        parent = "N0" if fld in ("N1", "N2") else ("fin_parent" if fld in ("F1", "F2") else "identity")
        for th_i, th in enumerate((0.0, 45.0)):
            for q_i, phase in enumerate(_Q2):
                sid = f"{fld}_th{th_i}_q{q_i}"
                specs[sid] = {
                    "id": sid,
                    "family": "k2_k3_controls",
                    "build": "analytic",
                    "field": fld,
                    "theta_deg": th,
                    "phase": phase,
                    "parent_field": parent,
                }
    for q_i, phase in enumerate(_Q2):
        for base in ("R0", "R1"):
            sid = f"{base}_q{q_i}"
            specs[sid] = {
                "id": sid,
                "family": "k4_controls",
                "build": "margin_control",
                "field": "bar",
                "theta_deg": 0.0,
                "phase": phase,
                "corner_phi_h": _H / 2.0 if base == "R0" else 0.3 * _H,
                "parent_field": "identity" if base == "R0" else "R0",
            }
        for base in ("A0", "A1"):
            sid = f"{base}_q{q_i}"
            specs[sid] = {
                "id": sid,
                "family": "k4_controls",
                "build": "analytic",
                "field": base,
                "theta_deg": 0.0,
                "phase": phase,
                "parent_field": "identity" if base == "A0" else "A0",
            }
    specs["D1"] = {"id": "D1", "family": "diagnostics", "build": "d1"}
    specs["E1"] = {"id": "E1", "family": "diagnostics", "build": "e1"}
    specs["E2"] = {"id": "E2", "family": "diagnostics", "build": "e2"}
    for w in (1.0, 1.25, 1.5, 1.75, 2.0):
        for j in range(8):
            sid = f"K5_w{w:g}_p8_{j}"
            specs[sid] = {
                "id": sid,
                "family": "k5_slabs",
                "build": "k5",
                "width_h": w,
                "phase_z": _p8(j)[2],
            }
    specs["H0"] = {"id": "H0", "family": "historical", "build": "historical"}
    return specs


def reconstruct_input(
    spec: dict[str, Any],
    raw_npz_dict: dict[str, np.ndarray],
    known_bindings: dict[str, Any],
) -> dict[str, Any]:
    """Independently reconstruct one row's phi/parent/masks/grid and feature proofs."""
    reasons: list[str] = []
    build = spec.get("build")
    try:
        if build == "analytic":
            phi, parent_phi, masks, origin_m, spacing_m = _build_analytic(spec)
        elif build == "margin_control":
            phi, parent_phi, masks, origin_m, spacing_m = _build_margin_control(spec)
        elif build == "v18_combo":
            phi, parent_phi, masks, origin_m, spacing_m = _build_v18_combo(spec, raw_npz_dict, known_bindings, reasons)
        elif build == "k5":
            phi, parent_phi, masks, origin_m, spacing_m = _build_k5(spec)
        elif build == "d1":
            phi, parent_phi, masks, origin_m, spacing_m = _build_d1()
        elif build == "e1":
            phi, parent_phi, masks, origin_m, spacing_m = _build_e1()
        elif build == "e2":
            phi, parent_phi, masks, origin_m, spacing_m = _build_e2()
        elif build == "historical":
            phi, parent_phi, masks, origin_m, spacing_m = _build_historical(known_bindings, reasons)
        else:
            reasons.append(f"unknown_build:{build}")
            return {
                "phi": None,
                "parent_phi": None,
                "masks": None,
                "origin_m": None,
                "spacing_m": None,
                "feature_proof": None,
                "reasons": reasons,
            }
    except Exception as exc:  # noqa: BLE001
        reasons.append(f"reconstruction_error:{type(exc).__name__}:{exc}")
        return {
            "phi": None,
            "parent_phi": None,
            "masks": None,
            "origin_m": None,
            "spacing_m": None,
            "feature_proof": None,
            "reasons": reasons,
        }

    feature_proof = _feature_proof(spec, phi, parent_phi, spacing_m)
    return {
        "phi": phi,
        "parent_phi": parent_phi,
        "masks": masks,
        "origin_m": origin_m,
        "spacing_m": spacing_m,
        "feature_proof": feature_proof,
        "reasons": reasons,
    }


# Run checking deliberately has no CLI and writes no files. A caller must first supply
# a complete frozen run; import, help and development tests never draw its new seeds.
_MASK_NAMES = ("design_mask", *_P2_MASK_NAMES)
_POLICY_SHA = "d4cd9aa42f0062923cdc8713d14d10fd334888a3c9dd5db9be15f7ac9d378d41"
_KNOWN_PATH = "docs/evidence/geom03_2026_10_23/known_inputs.json"
_REG_PATH = "docs/evidence/geom03_2026_10_23/registration.json"
_RELEASE_PATH = "docs/evidence/geom03_2026_10_23/execution_release.json"
_POLICY_PATH = "docs/evidence/geom02_v17_gates_2026_10_14/geom02_resolved_research_policy.json"
_SOURCE_PINS = {
    "docs/geom03_registration_2026_10_23.md", _KNOWN_PATH, _POLICY_PATH,
    "docs/evidence/mode01_v18_prescreen_2026_10_19/prescreen.json",
    "docs/evidence/width_rule_2026_10_20/v18_phase_sweep.json",
    "docs/evidence/v18_genesis_2026_10_19/v18_parent.npz",
    "docs/evidence/v18_genesis_2026_10_19/genesis.json",
    "scripts/width_rule_study.py", "scripts/geom03_run.py", "scripts/geom03_check.py",
    "tests/test_geom03.py", "scripts/mode01_v18_prescreen.py", "scripts/mode01_modes.py",
    "scripts/v18_plate.py", "src/cfd_sdf/design/sdf_state.py",
    "src/cfd_sdf/design/topology_policy.py", "src/cfd_sdf/design/topology_policy_research.py",
    "src/cfd_sdf/design/geometry_gates.py", "src/cfd_sdf/design/geometry_gates_v2.py",
    "src/cfd_sdf/design/volume_semantics.py",
    "src/cfd_sdf/fd08_v2_campaign.py", "src/cfd_sdf/gradients/directional_fd.py",
    "src/cfd_sdf/runtime/fingerprint.py",
}
_REVIEW_PINS = {
    "docs/evidence/geom03_2026_10_23/plan_review.json",
    "docs/evidence/geom03_2026_10_23/plan_review_go_reports.json",
    "docs/evidence/geom03_2026_10_23/geometry_review.md",
    "docs/evidence/geom03_2026_10_23/source_review.json",
}
_THIN_FIELDS = {"S1", "S2", "V1", "V2", "V4", "N1", "F2", "W20", "W40"}
_THICK_FIELDS = {"S3", "V3", "V5", "N0", "F1", "W60", "W90"}


def _strict_json(text: str) -> Any:
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError(f"duplicate JSON key:{key}")
            result[key] = value
        return result

    def bad_constant(value):
        raise ValueError(f"nonfinite JSON literal:{value}")

    result = json.loads(text, object_pairs_hook=pairs, parse_constant=bad_constant)

    def finite(value):
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("nonfinite JSON number")
        if isinstance(value, dict):
            for item in value.values():
                finite(item)
        elif isinstance(value, list):
            for item in value:
                finite(item)
    finite(result)
    return result


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def _json_sha(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode()).hexdigest()


def _file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_json(path: Path) -> Any:
    return _strict_json(path.read_text(encoding="utf-8"))


def _relative_file(base: Path, value: str) -> Path:
    if not isinstance(value, str) or Path(value).is_absolute() or ".." in Path(value).parts:
        raise ValueError("file path must be relative and contained")
    path = (base / value).resolve()
    if not path.is_relative_to(base.resolve()) or not path.is_file():
        raise ValueError(f"missing/escaping file:{value}")
    return path


def _pin_map(records: Any, required: set[str]) -> dict[str, str]:
    if not isinstance(records, list) or not records:
        raise ValueError("empty/missing pin manifest")
    pins = {}
    for record in records:
        name, sha = record["path"], record["sha256"]
        if name in pins or not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{64}", sha):
            raise ValueError(f"duplicate/invalid pin:{name}")
        if _file_sha(_relative_file(ROOT, name)) != sha:
            raise ValueError(f"pin hash mismatch:{name}")
        pins[name] = sha
    missing = required - pins.keys()
    if missing:
        raise ValueError("missing required pins:" + ",".join(sorted(missing)))
    return pins


def _frozen_inputs(reg: dict[str, Any], specs: dict[str, dict[str, Any]]) -> tuple[dict, SimpleNamespace, str]:
    """Validate provenance before any registered RNG or field construction."""
    if not isinstance(reg, dict) or reg.get("schema") != "geom03_registration_v1" or reg.get("status") != "REGISTERED_FROZEN":
        raise ValueError("registration is not REGISTERED_FROZEN")
    if reg.get("formal_plan_review_completed") is not True or reg.get("source_review_completed") is not True:
        raise ValueError("required reviews are incomplete")
    if (type(reg.get("expected_count")) is not int or reg["expected_count"] != 180
            or type(reg.get("expected_k6_count")) is not int or reg["expected_k6_count"] != 354):
        raise ValueError("registration counts are not 180/354")
    if not re.fullmatch(r"[0-9a-f]{40}", str(reg.get("source_commit", ""))):
        raise ValueError("invalid source commit")
    source_commit = reg["source_commit"]
    subprocess.run(["git", "merge-base", "--is-ancestor", source_commit, "HEAD"], cwd=ROOT, capture_output=True, timeout=10, check=True)
    git = subprocess.run(["git", "rev-parse", f"{source_commit}^{{tree}}"], cwd=ROOT, capture_output=True, text=True, timeout=10, check=True)
    if reg.get("source_tree") != git.stdout.strip():
        raise ValueError("frozen git source tree identity mismatch")
    pins = _pin_map(reg.get("source_files"), _SOURCE_PINS)
    for name, sha in pins.items():
        blob = subprocess.run(["git", "show", f"{source_commit}:{name}"], cwd=ROOT, capture_output=True, timeout=10, check=True)
        if hashlib.sha256(blob.stdout).hexdigest() != sha:
            raise ValueError("source pin differs from committed blob:" + name)
    _pin_map(reg.get("review_records"), _REVIEW_PINS)
    if reg.get("code_tree_identity") != _json_sha(pins):
        raise ValueError("code tree identity mismatch")
    versions = {"python": platform.python_version(), "numpy": np.__version__, "scipy": scipy.__version__, "platform": platform.platform()}
    if reg.get("runtime_versions") != versions:
        raise ValueError("runtime version/platform mismatch")
    if reg.get("base_specs_sha256") != _json_sha(list(specs.values())):
        raise ValueError("ordered base definitions are not frozen")
    if reg.get("seeds") != {"coefficient": [20261023, 1], "noise_prefix": [20261023, 2]}:
        raise ValueError("registered seed recipe mismatch")
    reg_path = _relative_file(ROOT, _REG_PATH)
    if _read_json(reg_path) != reg:
        raise ValueError("passed registration differs from frozen file")
    release_path = _relative_file(ROOT, _RELEASE_PATH)
    release = _read_json(release_path)
    if (release.get("schema") != "geom03_execution_release_v1"
            or release.get("purpose") not in ("FID01_GO_R3_VALIDATION", "M4_GEOMETRY_NEED")
            or release.get("registration_sha256") != _file_sha(reg_path)
            or not isinstance(release.get("reason"), str) or not release["reason"].strip()):
        raise ValueError("missing/invalid explicit execution release")
    if _file_sha(_relative_file(ROOT, release["basis_file"])) != release.get("basis_sha256"):
        raise ValueError("execution decision basis hash mismatch")
    known = _read_json(_relative_file(ROOT, _KNOWN_PATH))
    if known.get("schema") != "geom03_known_input_bindings_v1":
        raise ValueError("known input schema mismatch")
    for item, sha_key in ((known["source_prescreen"], "sha256"), (known["parent"], "npz_sha256"), (known["old_combination_source"], "sha256")):
        if _file_sha(_relative_file(ROOT, item["path"])) != item[sha_key]:
            raise ValueError("known source hash mismatch:" + item["path"])
    prescreen = _read_json(_relative_file(ROOT, known["source_prescreen"]["path"]))["basis"]
    basis = known["ordered_basis"]
    if (len(basis) != 7 or [b["mode"] for b in basis] != prescreen["proposed_basis"]
            or any(b["a_star"] != prescreen["per_mode"][b["mode"]]["a_star"] for b in basis)):
        raise ValueError("ordered basis/a_star mismatch")
    policy_record = _read_json(_relative_file(ROOT, _POLICY_PATH))
    policy_data = policy_record["policy"]
    if (policy_data.get("policy_sha256") != _POLICY_SHA or policy_data.get("max_components") is not None
            or policy_record.get("state_binding_id") != f"sdf_topology_policy_v2_research@sha256:{_POLICY_SHA}"):
        raise ValueError("resolved policy binding mismatch")
    policy = SimpleNamespace(state_binding_id=policy_record["state_binding_id"], max_components=None)
    fingerprint = _json_sha({"registration_sha256": _file_sha(reg_path), "release_sha256": _file_sha(release_path)})
    return known, policy, fingerprint


def _k6_spec(spec: dict[str, Any], scale: float) -> dict[str, Any]:
    return {**spec, "id": f"{spec['id']}@k6_{scale:g}", "base_id": spec["id"], "scale": scale, "kind": "k6"}


def _ordered_specs(specs: dict[str, dict[str, Any]]) -> list[tuple[str, dict[str, Any]]]:
    out = []
    for spec in specs.values():
        out.append(("base", spec))
        if spec["family"] != "diagnostics":
            out.extend(("k6", _k6_spec(spec, c)) for c in (0.5, 2.0))
    return out


def _expectation(spec: dict) -> str:
    sid, field = spec["id"].split("@")[0], spec.get("field")
    if spec["family"] == "diagnostics":
        return "diagnostic_only"
    if sid.startswith("R0_"):
        return "p1_and_composite_pass"
    if sid.startswith("R1_"):
        return "blocked"
    if field in ("N2", "A1"):
        return "p2_fail"
    if field == "A0":
        return "p2_pass_existing_two"
    if field in ("T1", "T2"):
        return "pass_or_unmeasured"
    if field in _THIN_FIELDS:
        return "non_pass"
    if spec["family"] == "k5_slabs":
        return "discrete_crossover"
    return "known_r0_replay" if sid == "H0" else "pass"


def _read_rows(directory: Path, specs: dict[str, dict[str, Any]]) -> tuple[list[dict], dict[str, dict]]:
    path = directory / "rows.jsonl"
    if not path.is_file():
        raise ValueError("missing rows.jsonl")
    rows = [_strict_json(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    expected = _ordered_specs(specs)
    if not rows or len(rows) != 534 or [r.get("id") for r in rows] != [s["id"] for _, s in expected]:
        raise ValueError("row enumeration/order mismatch; exact 180 base + 354 K6 required")
    if len({r["id"] for r in rows}) != len(rows):
        raise ValueError("duplicate row IDs")
    for row, (kind, spec) in zip(rows, expected):
        if row.get("kind") != kind or row.get("family") != spec["family"] or _canonical(row.get("spec")) != _canonical(spec):
            raise ValueError("row metadata/spec mismatch:" + spec["id"])
        if row.get("expectation") != _expectation(spec) or row.get("parent_kind") != spec.get("parent_field", spec["build"]):
            raise ValueError("prospective expectation/parent label mismatch:" + spec["id"])
        if row.get("input_npz") != f"inputs/{spec['id']}.npz":
            raise ValueError("input filename/id mismatch:" + spec["id"])
        path = _relative_file(directory, row["input_npz"])
        if _file_sha(path) != row.get("input_npz_sha256"):
            raise ValueError("input NPZ hash mismatch:" + spec["id"])
    return rows, {r["id"]: r for r in rows}


def _raw_input(directory: Path, row: dict[str, Any]) -> dict[str, np.ndarray]:
    with np.load(_relative_file(directory, row["input_npz"]), allow_pickle=False) as data:
        raw = {name: data[name] for name in data.files}
    if _strict_json(str(raw["spec_json"].item())) != _strict_json(_canonical(row["spec"])):
        raise ValueError("NPZ spec differs from row")
    phi, parent = raw["phi"], raw["parent_phi"]
    if (phi.ndim != 3 or min(phi.shape) < 2 or phi.dtype.str != "<f4" or parent.dtype.str != "<f4"
            or parent.shape != phi.shape or not np.isfinite(phi).all() or not np.isfinite(parent).all()):
        raise ValueError("NPZ phi/parent is not matching finite 3D little-endian float32")
    if any(raw[name].dtype != bool or raw[name].shape != phi.shape for name in _MASK_NAMES):
        raise ValueError("NPZ mask shape/dtype mismatch")
    origin, spacing = raw["origin_m"], raw["spacing_m"]
    if origin.shape != (3,) or not np.isfinite(origin).all() or spacing.size != 1 or not np.isfinite(spacing).all() or float(spacing.item()) <= 0:
        raise ValueError("invalid NPZ grid")
    identity = _field_identity(raw, row["spec"])
    if identity != row.get("field_identity") or row.get("origin_m") != identity["origin_m"] or row.get("spacing_m") != identity["spacing_m"]:
        raise ValueError("field/grid/mask identity mismatch")
    return raw


def _field_identity(raw: dict[str, np.ndarray], spec: dict[str, Any]) -> dict[str, Any]:
    grid = {"shape": list(raw["phi"].shape), "dtype": "<f4", "origin_m": [float(v) for v in raw["origin_m"]], "spacing_m": float(raw["spacing_m"].item())}
    return {**grid, "phi_fortran_sha256": hashlib.sha256(raw["phi"].tobytes(order="F")).hexdigest(),
            "parent_fortran_sha256": hashlib.sha256(raw["parent_phi"].tobytes(order="F")).hexdigest(),
            "mask_fortran_sha256": {name: hashlib.sha256(raw[name].tobytes(order="F")).hexdigest() for name in _MASK_NAMES},
            "grid_sha256": _json_sha(grid), "spec_sha256": _json_sha(spec)}


def _validate_basis(raw: dict[str, np.ndarray], known: dict) -> None:
    for item in known["ordered_basis"]:
        arr = _find_basis_array(raw, item["mode"])
        if (arr.dtype.str != "<f4" or list(arr.shape) != known["parent"]["shape"] or not np.isfinite(arr).all()
                or hashlib.sha256(arr.tobytes(order="F")).hexdigest() != item["phi_fortran_sha256"]):
            raise ValueError("basis dtype/shape/hash mismatch:" + item["mode"])


def _deadline_check(deadline: float) -> None:
    if time.time() > deadline:
        raise ValueError("cumulative two-hour budget exhausted during independent check")


def _verify_separation(directory: Path, rows: dict, known: dict, reg: dict, fingerprint: str, deadline: float) -> dict:
    """Rebuild old inputs arithmetically, then new inputs, before any outcome check."""
    manifest = _read_json(directory / "premeasurement_inputs.json")
    old = known["old_combination_source"]
    old_rows = _read_json(_relative_file(ROOT, old["path"]))["rows"]
    tasks = [r["task"] for r in old_rows if r.get("task", [None])[0] == "combo"]
    native = [item["phi_fortran_sha256"] for item in known["known_native_fields"]]
    if (len(tasks) != 250 or old.get("recorded_task_count") != 250 or _json_sha(tasks) != old["recorded_tasks_sha256"]
            or len(native) != 99 or any(not re.fullmatch(r"[0-9a-f]{64}", h) for h in native)):
        raise ValueError("incomplete/invalid historical identity/task bindings")
    recipe = {"seed_coefficients": [20261023, 1], "seed_noise_prefix": [20261023, 2], "count": 28,
              "noisy_start": 20, "ordered_basis": known["ordered_basis"], "source_files": reg["source_files"]}
    if (manifest.get("schema") != "geom03_premeasurement_inputs_v1" or manifest.get("fingerprint") != fingerprint
            or manifest.get("registration_sha256") != _file_sha(ROOT / _REG_PATH)
            or manifest.get("known_inputs_sha256") != _file_sha(ROOT / _KNOWN_PATH)
            or manifest.get("recipe_sha256") != _json_sha(recipe)
            or manifest.get("old_source_sha256") != old["sha256"]
            or manifest.get("old_tasks_sha256") != old["recorded_tasks_sha256"]
            or manifest.get("known_native_phi_sha256") != native):
        raise ValueError("premeasurement manifest source/recipe binding mismatch")
    source_reasons: list[str] = []
    parent = _load_v18_parent(known, source_reasons)
    if source_reasons:
        raise ValueError(",".join(source_reasons))
    raw = _raw_input(directory, rows["C00"])
    _validate_basis(raw, known)
    parent64 = parent["phi"].astype(np.float64)
    deltas = {item["mode"]: _find_basis_array(raw, item["mode"]).astype(np.float64) - parent64 for item in known["ordered_basis"]}
    active = parent["masks"]["design_mask"].copy()
    for name in _P2_MASK_NAMES:
        active &= ~parent["masks"][name]
    old_hashes = []
    for i, task in enumerate(tasks):
        _deadline_check(deadline)
        if (len(task) != 4 or task[:2] != ["combo", i] or task[3] != (i if i >= 200 else None)
                or len(task[2]) not in (2, 3) or len({p[0] for p in task[2]}) != len(task[2])
                or any(mode not in deltas or type(c) not in (int, float) or not -1 <= c < 1 for mode, c in task[2])):
            raise ValueError("historical combination task/index/noise mismatch")
        total = 0  # Python sum's original left-to-right arithmetic, including its initial zero.
        for mode, coefficient in task[2]:
            total = total + float(coefficient) * deltas[mode]
        phi64 = parent64 + total
        if task[3] is not None:
            rng = np.random.Generator(np.random.PCG64(np.random.SeedSequence([20261020, task[3]])))
            noise = rng.uniform(-parent["spacing_m"] / 16, parent["spacing_m"] / 16, parent64.shape)
            phi64 += np.where(active, noise, 0.0)
        old_hashes.append(hashlib.sha256(phi64.astype("<f4").tobytes(order="F")).hexdigest())
    if manifest.get("old_combination_phi_sha256") != old_hashes or len(old_hashes) != 250:
        raise ValueError("premeasurement historical combination identities mismatch")
    new = manifest.get("new_combinations")
    if not isinstance(new, list) or len(new) != 28:
        raise ValueError("missing/partial new combination identity manifest")
    schedules = _combo_schedule(known)
    seen = set(native) | set(old_hashes)
    old_schedules = [{"names": [p[0] for p in t[2]], "coefficients": [p[1] for p in t[2]], "noise_seed": [20261020, t[3]] if t[3] is not None else None} for t in tasks]
    for i, (item, schedule) in enumerate(zip(new, schedules)):
        _deadline_check(deadline)
        sid = f"C{i:02d}"
        row = rows[sid]
        expected_schedule = {**schedule, "noise_seed": [20261023, 2, i] if i >= 20 else None}
        if (item.get("id") != sid or item.get("schedule") != expected_schedule
                or any(item.get(key) != row.get(key) for key in ("field_identity", "input_npz", "input_npz_sha256"))):
            raise ValueError("new combination schedule/identity binding mismatch:" + sid)
        raw = _raw_input(directory, row)
        _validate_basis(raw, known)
        built = reconstruct_input(row["spec"], raw, known)
        _match_reconstruction(raw, built)
        sha = row["field_identity"]["phi_fortran_sha256"]
        if sha in seen:
            raise ValueError("duplicate known/old/new combination input:" + sid)
        seen.add(sha)
        if expected_schedule in old_schedules:
            raise ValueError("duplicate historical combination schedule:" + sid)
    if manifest.get("schedule_sha256") != _json_sha([item["schedule"] for item in new]):
        raise ValueError("new schedule hash mismatch")
    return {"known_native_count": 99, "old_combination_count": 250, "new_combination_count": 28,
            "old_combination_hashes_sha256": _json_sha(old_hashes), "schedule_sha256": manifest["schedule_sha256"], "verified_before_outcomes": True}


def _match_reconstruction(raw: dict, built: dict) -> None:
    if built["reasons"]:
        raise ValueError(",".join(built["reasons"]))
    for name in ("phi", "parent_phi"):
        if raw[name].dtype.str != built[name].dtype.str or raw[name].shape != built[name].shape or raw[name].tobytes(order="F") != built[name].tobytes(order="F"):
            raise ValueError("independent field construction mismatch:" + name)
    for name in _MASK_NAMES:
        if raw[name].tobytes(order="F") != built["masks"][name].tobytes(order="F"):
            raise ValueError("independent mask construction mismatch:" + name)
    if list(built["origin_m"]) != raw["origin_m"].tolist() or built["spacing_m"] != float(raw["spacing_m"].item()):
        raise ValueError("independent grid construction mismatch")


def _number_equal(actual: Any, expected: float | None) -> bool:
    if expected is None:
        return actual is None
    if math.isinf(expected):
        return actual == "inf"
    return type(actual) in (int, float) and math.isfinite(actual) and abs(actual - expected) <= LENGTH_TOLERANCE_M


def _metrics_agree(record: Any, result: dict) -> bool:
    if not isinstance(record, dict) or set(record) != set(result):
        return False
    for name in ("r0", "r3"):
        observed, expected = record[name], result[name]
        if not isinstance(observed, dict) or set(observed) != set(expected) or observed["status"] != expected["status"]:
            return False
        if any(not _number_equal(observed[key], expected[key]) for key in ("solid", "void")):
            return False
    return all(_canonical(record[name]) == _canonical(result[name]) for name in ("p1", "p2", "composite"))


def _required_feature(spec: dict, proof: dict) -> None:
    field = spec.get("field")
    keys = {"S1": "negative_node_in_box", "S2": "negative_node_in_box", "V1": "positive_node_in_closed_void",
            "V2": "positive_node_in_closed_void", "V4": "positive_node_in_open_slot", "N1": "negative_node_in_neck",
            "F2": "negative_node_outside_parent_fin", "W20": "negative_node_in_thin_tip", "W40": "negative_node_in_thin_tip"}
    if field in keys and proof.get(keys[field], 0) <= 0:
        raise ValueError("required analytic coarse feature is absent:" + keys[field])
    if field in ("N2", "A0", "A1"):
        transition = proof[{"N2": "neck_split", "A1": "boxes_merge", "A0": "boxes_identity"}[field]]
        if field == "A0":
            identity = {1: [1], 2: [2]}
            if (transition["parent_components"] != 2 or transition["candidate_components"] != 2
                    or transition["overlap"] != {"old_to_new": identity, "new_to_old": identity}):
                raise ValueError("registered A0 existing two-component overlap not represented")
            return
        old, new = (1, 2) if field == "N2" else (2, 1)
        relation = transition["overlap"]
        expected_old = {1: [1, 2]} if old == 1 else {1: [1], 2: [1]}
        expected_new = {1: [1], 2: [1]} if new == 2 else {1: [1, 2]}
        if (transition["parent_components"] != old or transition["candidate_components"] != new
                or relation["old_to_new"] != expected_old or relation["new_to_old"] != expected_new):
            raise ValueError("registered split/merge overlap construction not represented")


def _halo_record(spec: dict, phi: np.ndarray, parent: np.ndarray) -> dict | None:
    if spec["build"] == "k5":
        return {"rule": "inapplicable_k5_finite_array_contract", "candidate": None, "parent": None}
    if spec["family"] == "diagnostics":
        return None
    return {"candidate": _has_halo(phi), "parent": _has_halo(parent)}


def _check_observations(row: dict, result: dict, refined_count: int, proof: dict) -> None:
    if type(row.get("coarse_components")) is not int or row["coarse_components"] != result["p2"]["candidate_components"]:
        raise ValueError("coarse component observation disagreement")
    if type(row.get("refined_components")) is not int or row["refined_components"] != refined_count:
        raise ValueError("refined sampled component observation disagreement")
    observed = row.get("feature_observables")
    if row["spec"]["build"] == "analytic":
        expected = {key: value for key, value in proof.items() if key != "halo"}
        if _canonical(observed) != _canonical(expected or None):
            raise ValueError("family feature/overlap observation disagreement")
    if row["spec"]["build"] == "d1":
        expected = {"coarse_components": proof["coarse_components"], "refined_components": proof["refined_components"]}
        if _canonical(row.get("diagnostic")) != _canonical(expected):
            raise ValueError("D1 coarse/refined diagnostic record disagreement")


def _criterion_result(criterion: str, expected: int, observations: list[tuple[str, bool]], counterexamples: list[dict]) -> dict:
    failures = [sid for sid, passed in observations if not passed]
    for sid in failures:
        counterexamples.append({"criterion": criterion, "id": sid})
    return {"pass": len(observations) == expected and not failures, "expected_rows": expected,
            "checked_rows": len(observations), "counterexamples": failures}


def _criteria(base: dict[str, dict], scaled: dict[str, bool], specs: dict, reasons: list[str], counterexamples: list[dict]) -> dict:
    groups = {name: [] for name in ("K1", "K2", "K3", "K4")}
    for sid, result in base.items():
        spec = specs[sid]
        field = spec.get("field")
        status, p2 = result["composite"], result["p2"]
        if spec["family"] in ("k1_analytic", "k1_combos"):
            groups["K1"].append((sid, status == "pass"))
        if field in _THIN_FIELDS:
            groups["K2"].append((sid, status != "pass"))
        if field in _THICK_FIELDS:
            groups["K3"].append((sid, status == "pass"))
        if sid.startswith("R0_q"):
            groups["K4"].append((sid, result["p1"]["status"] == "pass" and status == "pass"))
        elif sid.startswith("R1_q"):
            groups["K4"].append((sid, status == "blocked"))
        elif field in ("N2", "A1"):
            event = "split" if field == "N2" else "merge"
            groups["K4"].append((sid, p2["statuses"]["topology_change_classification"] == "fail" and event in p2["events"]))
        elif field == "A0":
            groups["K4"].append((sid, all(v == "pass" for v in p2["statuses"].values()) and p2["parent_components"] == p2["candidate_components"] == 2 and not p2["events"]))
        elif field in ("T1", "T2"):
            groups["K4"].append((sid, status in ("pass", "unmeasured")))
    result = {key: _criterion_result(key, count, groups[key], counterexamples) for key, count in (("K1", 52), ("K2", 36), ("K3", 28), ("K4", 20))}
    widths = (1.0, 1.25, 1.5, 1.75, 2.0)
    brackets = {}
    curves = {}
    slab_count = sum(specs[sid]["build"] == "k5" for sid in base)
    for rule in ("r0", "composite"):
        q = []
        for w in widths:
            ids = [f"K5_w{w:g}_p8_{j}" for j in range(8)]
            if not all(sid in base for sid in ids):
                reasons.append("K5:missing slab observations")
                break
            q.append(sum((base[sid]["r0"]["status"] if rule == "r0" else base[sid]["composite"]) == "pass" for sid in ids) / 8)
        curves[rule] = q
        if len(q) != 5 or any(a > b for a, b in zip(q, q[1:])):
            reasons.append("K5:missing/nonmonotone curve:" + rule)
            continue
        lo = [w for w, p in zip(widths, q) if p < 0.5]
        hi = [w for w, p in zip(widths, q) if p >= 0.5]
        if not lo or not hi:
            reasons.append("K5:missing crossover bracket:" + rule)
            continue
        brackets[rule] = {"lo": max(lo), "hi": min(hi)}
    k5_complete = len(brackets) == 2
    k5_pass = k5_complete and all(brackets["composite"][side] >= brackets["r0"][side] for side in ("lo", "hi"))
    if k5_complete and not k5_pass:
        counterexamples.append({"criterion": "K5", "id": "slab_crossover", "brackets_h": brackets})
    result["K5"] = {"pass": bool(k5_pass), "complete": k5_complete, "expected_rows": 40, "checked_rows": slab_count,
                    "widths_h": list(widths), "q": curves, "brackets_h": brackets}
    result["K6"] = _criterion_result("K6", 354, list(scaled.items()), counterexamples)
    h0 = base.get("H0", {}).get("r0")
    result["H0"] = {"pass": h0 is not None and h0["status"] == "pass" and h0["void"] is None
                     and h0["solid"] is not None and abs(h0["solid"] - 0.09762812094883319) <= LENGTH_TOLERANCE_M}
    if h0 is not None and not result["H0"]["pass"]:
        reasons.append("H0:historical R0 replay mismatch")
    return result


def check_run(directory: str | Path, registration_dict: dict[str, Any]) -> dict[str, Any]:
    """Independently check one complete frozen run, returning strict-JSON-safe findings.

    INCOMPLETE has precedence over valid contrary observations; those counterexamples
    remain visible. The caller owns the sole append-only terminal write and watchdog.
    """
    report: dict[str, Any] = {"verdict": "GEOM03_INCOMPLETE", "complete": False, "criteria": {},
                              "incomplete_reasons": [], "counterexamples": [], "checked_rows": 0,
                              "diagnostics": {}, "scope": "represented sampled geometry only; no continuous/physical/flow qualification"}
    reasons, counterexamples = report["incomplete_reasons"], report["counterexamples"]
    try:
        directory = Path(directory)
        if not directory.is_dir():
            raise ValueError("missing run directory")
        specs = expected_base_specs()  # metadata only; no arrays or registered random draws.
        known, policy, fingerprint = _frozen_inputs(registration_dict, specs)
        rows, by_id = _read_rows(directory, specs)
        if (directory / "stop_reason.json").exists() or (directory / "results.json").exists():
            raise ValueError("pre-existing terminal stop/result cannot be checked as a new completion")
        state = _read_json(directory / "state.json")
        started = state.get("run_started_epoch")
        if (state.get("schema") != "geom03_run_state_v1" or state.get("fingerprint") != fingerprint or state.get("status") != "RUNNING"
                or type(state.get("attempts")) is not int or state["attempts"] != 1
                or type(state.get("resume_count")) is not int or state["resume_count"] < 0
                or type(started) not in (int, float) or not math.isfinite(started) or started > time.time()):
            raise ValueError("invalid original run state/time/attempt/fingerprint")
        deadline = started + 7200
        _deadline_check(deadline)
        report["separation"] = _verify_separation(directory, by_id, known, registration_dict, fingerprint, deadline)
        base_results: dict[str, dict] = {}
        scale_results: dict[str, bool] = {}
        for spec in specs.values():
            sid = spec["id"]
            try:
                _deadline_check(deadline)
                row = by_id[sid]
                raw = _raw_input(directory, row)
                if spec["build"] == "v18_combo":
                    _validate_basis(raw, known)
                built = reconstruct_input(spec, raw, known)
                _match_reconstruction(raw, built)
                halo = _halo_record(spec, raw["phi"], raw["parent_phi"])
                if row.get("halo") != halo:
                    raise ValueError("halo record disagreement")
                if spec["family"] != "diagnostics" and spec["build"] != "k5" and not all(halo.values()):
                    raise ValueError("ordinary parent/candidate three-node halo absent")
                _required_feature(spec, built["feature_proof"] or {})
                parent_kind = spec.get("parent_field", spec["build"])
                if row.get("parent_kind") != parent_kind:
                    raise ValueError("parent identity label mismatch")
                h = built["spacing_m"]
                if spec["build"] == "e2":
                    diagnostic = row.get("diagnostic")
                    if (row.get("candidate") is not None or not isinstance(diagnostic, dict) or set(diagnostic) != {"solid", "void", "spacing_m"}
                            or diagnostic["spacing_m"] != h
                            or any(value is not None and value != "inf" and (type(value) not in (int, float) or value < 0)
                                   for value in (diagnostic["solid"], diagnostic["void"]))):
                        raise ValueError("E2 must carry helper-only diagnostic")
                    body = raw["phi"] < 0
                    report["diagnostics"][sid] = {"observed": row["diagnostic"], "morphology_solid": _opening_defect(body, h * R3_K),
                                                     "morphology_void": _opening_defect(~body, h * R3_K), "comparison": "diagnostic_only"}
                    report["checked_rows"] += 1
                    continue
                result = check_pair(raw["phi"], raw["parent_phi"], built["masks"], h, policy, built["origin_m"])
                signs, refined_count = _sign_observations(raw["phi"])
                if not _metrics_agree(row.get("candidate"), result) or row.get("sign_body_hashes") != signs:
                    raise ValueError("candidate/independent checker metric or sign-hash disagreement")
                _check_observations(row, result, refined_count, built["feature_proof"] or {})
                if sid == "H0" and row["field_identity"]["phi_fortran_sha256"] != "29d53b2318c54548da321f265aa2102d59e24d96bbd04fb2dd70d62fbc10c82a":
                    raise ValueError("H0 known phi identity mismatch")
                report["checked_rows"] += 1
                if spec["family"] == "diagnostics":
                    report["diagnostics"][sid] = {"candidate": row["candidate"], "independent_feature_proof": built["feature_proof"]}
                    continue
                base_results[sid] = result
                for scale in (0.5, 2.0):
                    scaled_spec = _k6_spec(spec, scale)
                    scaled_id = scaled_spec["id"]
                    try:
                        _deadline_check(deadline)
                        scaled_row = by_id[scaled_id]
                        scaled_raw = _raw_input(directory, scaled_row)
                        expected = {"phi": (raw["phi"] * np.float32(scale)).astype("<f4"),
                                    "parent_phi": (raw["parent_phi"] * np.float32(scale)).astype("<f4"),
                                    "masks": built["masks"], "origin_m": built["origin_m"], "spacing_m": h, "reasons": []}
                        _match_reconstruction(scaled_raw, expected)
                        if scaled_row.get("halo") != halo or scaled_row.get("parent_kind") != parent_kind:
                            raise ValueError("K6 grid/halo/parent label mismatch")
                        k6 = scaled_row.get("k6", {})
                        if k6 != {"base_id": sid, "scale": scale, "unscaled_p1": result["p1"]}:
                            raise ValueError("K6 must bind original metre-valued P1")
                        scaled_result = check_pair(scaled_raw["phi"], scaled_raw["parent_phi"], built["masks"], h, policy, built["origin_m"])
                        scaled_result["p1"] = result["p1"]
                        scaled_result["composite"] = "blocked" if result["p1"]["status"] == "fail" else _worst(scaled_result["r3"]["status"], *scaled_result["p2"]["statuses"].values())
                        scaled_signs, scaled_refined_count = _sign_observations(scaled_raw["phi"])
                        if not _metrics_agree(scaled_row.get("candidate"), scaled_result) or scaled_row.get("sign_body_hashes") != scaled_signs:
                            raise ValueError("K6 candidate/independent metric or sign-hash disagreement")
                        # Feature labels use unscaled geometry; positive scales preserve it.
                        _check_observations(scaled_row, scaled_result, scaled_refined_count, built["feature_proof"] or {})
                        scale_results[scaled_id] = (scaled_signs == signs and scaled_result["r0"]["status"] == result["r0"]["status"]
                                                    and scaled_result["r3"]["status"] == result["r3"]["status"] and scaled_result["p2"] == result["p2"]
                                                    and scaled_result["composite"] == result["composite"])
                        report["checked_rows"] += 1
                    except Exception as exc:
                        reasons.append(f"{scaled_id}:{type(exc).__name__}:{exc}")
            except Exception as exc:
                reasons.append(f"{sid}:{type(exc).__name__}:{exc}")
                if time.time() > deadline:
                    break
        report["criteria"] = _criteria(base_results, scale_results, specs, reasons, counterexamples)
        if report["checked_rows"] != 534:
            reasons.append(f"incomplete independent row count:{report['checked_rows']}/534")
        _deadline_check(deadline)
        report["complete"] = not reasons
        if report["complete"]:
            report["verdict"] = "GEOM03_PASS" if all(c["pass"] for c in report["criteria"].values()) else "GEOM03_NO_GO"
    except Exception as exc:
        reasons.append(f"{type(exc).__name__}:{exc}")
        report["complete"] = False
        report["verdict"] = "GEOM03_INCOMPLETE"
    reasons[:] = list(dict.fromkeys(reasons))
    return report


__all__ = ["check_pair", "sign_body_hashes", "expected_base_specs", "reconstruct_input", "check_run"]
