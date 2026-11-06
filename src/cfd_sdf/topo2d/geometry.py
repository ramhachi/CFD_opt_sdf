"""Source-table wing series in mm, with polygon SDFs and pre-CFD gates.

Flow is +x and z is up. Positive overlap is upstream TE-midpoint x minus
downstream LE x. Positive gap is downstream suction minimum z minus upstream
TE-midpoint z: the stable reference for a finite TE under symmetric thickening.
The source's quoted gap must not be mistaken for minimum Euclidean clearance.

The retained LE cap contains the first three source pairs. Its polygon shape
and three-point curvature proxies are preserved; no smooth analytic LE radius
is asserted. The normal-thickness floor applies from the original maximum
thickness station aft, including the TE. The intervening ramp is disclosed.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
from pathlib import Path
import zipfile

import numpy as np


ROOT = Path(__file__).resolve().parents[3]
C1_MM = 223.4
C_MM = 380.0
SCHEMA = "topo2d-scene-v1"
TOL = 1e-9


class GeometryError(ValueError):
    """The scene is invalid and must not be sent to a CFD solver."""


def _positive(value, name):
    if not np.isfinite(value) or value <= 0:
        raise GeometryError(f"{name} must be finite and positive")
    return float(value)


def _cross(a, b):
    return a[..., 0] * b[..., 1] - a[..., 1] * b[..., 0]


def _polygon(polygon):
    p = np.asarray(polygon, dtype=np.float64)
    if p.ndim != 2 or p.shape[1] != 2 or len(p) < 4 or not np.isfinite(p).all():
        raise GeometryError("polygon must contain finite two-dimensional vertices")
    if not np.array_equal(p[0], p[-1]):
        raise GeometryError("polygon must be explicitly closed")
    if np.any(np.linalg.norm(np.diff(p, axis=0), axis=1) <= TOL):
        raise GeometryError("polygon has a zero-length edge")
    return p


def _point_segment_squared(points, start, end):
    offset = points[:, None, :] - start[None, :, :]
    edges = end - start
    fraction = np.clip(np.einsum("psi,si->ps", offset, edges)
                       / np.einsum("si,si->s", edges, edges), 0, 1)
    delta = offset - fraction[:, :, None] * edges[None, :, :]
    return np.einsum("psi,psi->ps", delta, delta)


def polygon_sdf(points, polygon):
    """Exact distance to the closed polygon boundary, negative by winding inside.

    NumPy float64, no rasterization/interpolation. At medial axes and corners
    the derivative is undefined; away from them this has unit gradient norm.
    """
    p = _polygon(polygon)
    x = np.asarray(points, dtype=np.float64)
    if x.ndim < 1 or x.shape[-1] != 2 or not np.isfinite(x).all():
        raise GeometryError("SDF points must be finite (..., 2) coordinates")
    flat = x.reshape(-1, 2)
    a, b = p[:-1], p[1:]
    distance = np.sqrt(_point_segment_squared(flat, a, b).min(axis=1))
    cross = _cross(b[None] - a[None], flat[:, None] - a[None])
    up = (a[None, :, 1] <= flat[:, None, 1]) & (b[None, :, 1] > flat[:, None, 1])
    down = (a[None, :, 1] > flat[:, None, 1]) & (b[None, :, 1] <= flat[:, None, 1])
    winding = ((up & (cross > 0)).sum(axis=1) - (down & (cross < 0)).sum(axis=1))
    return np.where(winding != 0, -distance, distance).reshape(x.shape[:-1])


def scene_sdf(points, scene):
    """Union of wing elements; moving ground is a separate solver body."""
    if not scene.get("elements"):
        raise GeometryError("scene has no elements")
    return np.minimum.reduce([polygon_sdf(points, e["polygon_mm"]) for e in scene["elements"]])


def _intersections(a, b):
    """Inclusive intersection matrix for segment arrays (start, end)."""
    a0, a1 = a
    b0, b1 = b
    aa, ab = a0[:, None], a1[:, None]
    ba, bb = b0[None], b1[None]
    boxes = np.all(np.maximum(np.minimum(aa, ab), np.minimum(ba, bb))
                   <= np.minimum(np.maximum(aa, ab), np.maximum(ba, bb)) + TOL, axis=2)
    o1, o2 = _cross(ab - aa, ba - aa), _cross(ab - aa, bb - aa)
    o3, o4 = _cross(bb - ba, aa - ba), _cross(bb - ba, ab - ba)
    return boxes & (o1 * o2 <= TOL ** 2) & (o3 * o4 <= TOL ** 2)


def _self_intersects(p):
    hits = _intersections((p[:-1], p[1:]), (p[:-1], p[1:]))
    n = len(p) - 1
    i, j = np.indices((n, n))
    return bool(np.any(hits & (j > i + 1) & ~((i == 0) & (j == n - 1))))


def polygon_gap(a, b):
    """True minimum Euclidean boundary distance; intersection/containment is zero."""
    a, b = _polygon(a), _polygon(b)
    if np.any(_intersections((a[:-1], a[1:]), (b[:-1], b[1:]))):
        return 0.0
    if polygon_sdf(a[:1], b)[0] < 0 or polygon_sdf(b[:1], a)[0] < 0:
        return 0.0
    return float(np.sqrt(min(_point_segment_squared(a[:-1], b[:-1], b[1:]).min(),
                             _point_segment_squared(b[:-1], a[:-1], a[1:]).min())))


def _curves(suction, pressure):
    s, p = np.asarray(suction, float), np.asarray(pressure, float)
    if s.shape != p.shape or s.ndim != 2 or s.shape[1] != 2 or len(s) < 4:
        raise GeometryError("paired suction/pressure arrays must have matching (N>=4,2) shape")
    if not np.isfinite(s).all() or not np.isfinite(p).all() or not np.array_equal(s[0], p[0]):
        raise GeometryError("surface arrays must be finite and share their leading edge")
    c = (s + p) / 2
    segments = np.diff(c, axis=0)
    lengths = np.linalg.norm(segments, axis=1)
    if np.any(lengths <= TOL):
        raise GeometryError("camber line has coincident stations")
    tangent = np.gradient(c, axis=0)
    tangent /= np.linalg.norm(tangent, axis=1)[:, None]
    normal = np.column_stack((-tangent[:, 1], tangent[:, 0]))
    segment_normal = np.column_stack((-segments[:, 1], segments[:, 0])) / lengths[:, None]
    thickness = np.einsum("ij,ij->i", p - s, normal)
    if np.any(thickness[1:] <= 0):
        raise GeometryError("surface order or camber-normal thickness is invalid")
    return s, p, c, normal, segment_normal, thickness


def _projection_minimum(suction, pressure, start):
    s, p, _, _, normal, _ = _curves(suction, pressure)
    # On each linear camber segment its normal is constant. The paired-surface
    # separation projected on it is linear, so endpoints prove the segment.
    widths0 = np.einsum("ij,ij->i", (p - s)[start:-1], normal[start:])
    widths1 = np.einsum("ij,ij->i", (p - s)[start + 1:], normal[start:])
    return float(min(widths0.min(), widths1.min()))


def _controlled_minimum(suction, pressure, start):
    s, p, camber, _, _, _ = _curves(suction, pressure)
    return _normal_ray_minimum(_closed_from_surfaces(s, p), camber, start)


def _normal_ray_minimum(polygon, camber, start):
    """Continuous normal-ray width minimum on a piecewise-linear camber bulk.

    For each camber segment its normal is fixed. Polygon-line intersection
    distances are affine in the tangential coordinate between projections of
    polygon vertices. Camber/boundary crossings are extra events so the ray
    origin cannot silently switch between disconnected interior intervals.
    Event and interval-midpoint inside checks establish the chosen interior
    branch; its affine width attains its minimum at an event or endpoint.
    Collinear end caps contribute both of their endpoints.
    """
    polygon, camber = _polygon(polygon), np.asarray(camber, dtype=float)
    segments = np.diff(camber, axis=0)
    normals = np.column_stack((-segments[:, 1], segments[:, 0])) / np.linalg.norm(segments, axis=1)[:, None]
    a, edges = polygon[:-1], np.diff(polygon, axis=0)
    minimum = math.inf
    for j in range(start, len(camber) - 1):
        vector = camber[j + 1] - camber[j]
        length = np.linalg.norm(vector)
        tangent, normal = vector / length, normals[j]
        events = (polygon - camber[j]) @ tangent / length
        denominator_cross = _cross(vector, edges)
        transverse_cross = np.abs(denominator_cross) > TOL
        relative = a - camber[j]
        roots = np.divide(_cross(relative, edges), denominator_cross,
                          out=np.zeros(len(edges)), where=transverse_cross)
        edge_fraction = np.divide(_cross(relative, vector), denominator_cross,
                                  out=np.zeros(len(edges)), where=transverse_cross)
        roots = roots[transverse_cross & (roots >= 0) & (roots <= 1)
                      & (edge_fraction >= 0) & (edge_fraction <= 1)]
        events = np.unique(np.r_[0.0, 1.0, roots, np.clip(events[(events >= 0) & (events <= 1)], 0, 1)])
        inside_probes = np.r_[events, (events[:-1] + events[1:]) / 2]
        if np.any(polygon_sdf(camber[j] + inside_probes[:, None] * vector, polygon) > TOL):
            raise GeometryError("controlled camber is outside polygon")
        centres = camber[j] + events[:, None] * vector
        along = (centres[:, None] - a[None]) @ tangent
        denominator = edges @ tangent
        transverse = np.abs(denominator) > TOL
        fraction = np.divide(along, denominator[None], out=np.zeros_like(along), where=transverse[None])
        hits = transverse[None] & (fraction >= -TOL) & (fraction <= 1 + TOL)
        distance = (a[None] - centres[:, None]) @ normal + fraction * (edges @ normal)[None]
        positive = np.min(np.where(hits & (distance >= -TOL), np.maximum(distance, 0), np.inf), axis=1)
        negative = np.max(np.where(hits & (distance <= TOL), np.minimum(distance, 0), -np.inf), axis=1)
        # A ray lying on the finite TE cap must see its endpoints, not a zero
        # denominator silently dropped from the calculation.
        collinear = (~transverse)[None] & (np.abs(along) <= TOL)
        ends = np.stack(((a[None] - centres[:, None]) @ normal,
                         ((a + edges)[None] - centres[:, None]) @ normal), axis=2)
        positive_cap = np.min(np.where(collinear[:, :, None] & (ends >= -TOL), np.maximum(ends, 0), np.inf), axis=(1, 2))
        negative_cap = np.max(np.where(collinear[:, :, None] & (ends <= TOL), np.minimum(ends, 0), -np.inf), axis=(1, 2))
        positive = np.minimum(positive, positive_cap)
        negative = np.maximum(negative, negative_cap)
        if not np.isfinite(positive).all() or not np.isfinite(negative).all():
            raise GeometryError("controlled normal ray misses a polygon surface")
        width = positive - negative
        if np.any(width <= TOL):
            raise GeometryError("controlled camber has no positive two-sided normal width")
        minimum = min(minimum, float(width.min()))
    return minimum


def thicken_element(suction, pressure, *, t_min_mm):
    """Camber-normal reconstruction; keep the first three pairs and TE midpoint.

    Remove the source pairs' tangential separation while smoothly leaving the
    LE cap; construct the controlled bulk as camber +/- normal * half-thickness.
    The actual polygon normal-ray width gate is independent of paired projection.
    The preserved cap and smoothstep ramp are explicitly excluded from that
    positive floor, since thickness at a closed leading edge is zero.
    """
    floor = _positive(t_min_mm, "t_min_mm")
    s, p, camber, normals, segment_normals, thickness = _curves(suction, pressure)
    start = int(np.argmax(thickness))
    if start < 3 or start >= len(s) - 1:
        raise GeometryError("maximum thickness must lie after the preserved LE cap and before TE")
    target = thickness.copy()
    for j in range(start, len(s) - 1):
        for i in (j, j + 1):
            projection = float(normals[i] @ segment_normals[j])
            if projection <= 0:
                raise GeometryError("camber normal turns by >=90 degrees")
            target[i] = max(target[i], floor / projection)
    # The first three source pairs are unchanged. If the source maximum itself
    # is too thin (E3), reach its required offset through this disclosed ramp.
    weights = np.ones(len(s))
    weights[:3] = 0
    fraction = (np.arange(3, start, dtype=float) - 2) / (start - 2)
    weights[3:start] = fraction ** 2 * (3 - 2 * fraction)

    def reconstruct(extra):
        offsets = (target - thickness) / 2
        offsets[start:] += extra
        offsets[3:start] = offsets[start] * weights[3:start]
        difference = ((1 - weights[:, None]) * (p - s)
                      + weights[:, None] * thickness[:, None] * normals
                      + 2 * offsets[:, None] * normals)
        lower, upper = camber - difference / 2, camber + difference / 2
        lower[:3], upper[:3] = s[:3], p[:3]
        return lower, upper

    extra = 0.0
    lower, upper = reconstruct(extra)
    measured = _controlled_minimum(lower, upper, start)
    if measured < floor - TOL:
        lo, hi = 0.0, max((floor - measured) / 2, 1e-8)
        for _ in range(30):
            trial = reconstruct(hi)
            if _controlled_minimum(*trial, start) >= floor:
                break
            hi *= 2
        else:
            raise GeometryError("normal reconstruction cannot reach its thickness floor")
        # ponytail: scalar bisection only when the independently measured ray
        # width requires more than the projection bound; no geometry optimizer.
        for _ in range(32):
            mid = (lo + hi) / 2
            if _controlled_minimum(*reconstruct(mid), start) < floor:
                lo = mid
            else:
                hi = mid
        extra = hi
        lower, upper = reconstruct(extra)
        measured = _controlled_minimum(lower, upper, start)
    actual = np.einsum("ij,ij->i", upper - lower, normals)
    metadata = {
        "method": "camber-normal-reconstruction-v1",
        "t_min_mm": floor,
        "controlled_from_index": start,
        "controlled_from_camber_fraction": float(np.linalg.norm(camber[start] - camber[0])
                                                  / np.linalg.norm(camber[-1] - camber[0])),
        "controlled_min_thickness_mm": measured,
        "thickness_metric": "actual polygon width along each controlled camber-segment normal",
        "ray_minimum_rule": "segment endpoints, polygon-vertex projections and camber-boundary events; interval-inside checks and affine width proof",
        "paired_projection_min_thickness_mm": _projection_minimum(lower, upper, start),
        "extra_normal_offset_mm": extra,
        "max_tangential_reconstruction_mm": float(np.max(weights * np.abs(_cross(p - s, normals)) / 2)),
        "source_vertices_only_normal_translated": False,
        "bdim_core_qualified": False,
        "preserved_cap_pairs": 3,
        "cap_radius_claim": "source polygon and three-point curvature proxy only",
        "ramp": "smoothstep from paired station 2 to original maximum-thickness station",
        "global_positive_thickness_claim": False,
        "original_max_thickness_mm": float(thickness.max()),
        "max_thickness_ratio": float(np.max(actual[1:] / thickness[1:])),
        "te_midpoint_preserved": bool(np.allclose((lower[-1] + upper[-1]) / 2, camber[-1], atol=TOL, rtol=0)),
    }
    return lower, upper, metadata


def _closed_from_surfaces(s, p):
    polygon = np.vstack((s[::-1], p[1:], s[-1:]))
    return polygon


def _source_table(filename):
    path = ROOT / "data" / "zz2003" / filename
    if not path.is_file():
        raise GeometryError(f"required source table is missing: {path}")
    rows = np.loadtxt(path)
    if rows.ndim != 2 or rows.shape[1] != 4 or not np.isfinite(rows).all():
        raise GeometryError(f"invalid source table: {path}")
    return rows[:, :2] * C_MM, rows[:, 2:] * C_MM, {
        "path": path.relative_to(ROOT).as_posix(),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "url": "https://eprints.soton.ac.uk/426058/1/00192634.pdf",
        "verification": "UNVERIFIED_OCR",
        "normalization_chord_mm": C_MM,
    }


def _angle(s, p):
    chord = (s[-1] + p[-1]) / 2 - s[0]
    return math.atan2(chord[1], chord[0])


def _source_profiles(configuration):
    """Read the trusted source geometry and derive the declared series once."""
    ms, mp, main_source = _source_table("main_element_table3.dat")
    fs, fp, flap_source = _source_table("flap_table4.dat")
    main_angle, flap_angle = _angle(ms, mp), _angle(fs, fp)
    flap_origin = fs[0].copy()
    chords = [float(np.linalg.norm((s[-1] + p[-1]) / 2 - s[0])) for s, p in ((ms, mp), (fs, fp))]
    profiles = [("main", ms, mp, chords[0], C1_MM)]
    if configuration == "E2":
        profiles.append(("flap1", fs, fp, chords[1], 165.7))
    elif configuration == "E3":
        for i in (1, 2):
            turn = main_angle + i * (flap_angle - main_angle) / 2 - flap_angle
            rotation = np.array([[math.cos(turn), -math.sin(turn)], [math.sin(turn), math.cos(turn)]])
            profiles.append((f"flap{i}", (fs - flap_origin) @ rotation.T / 2,
                             (fp - flap_origin) @ rotation.T / 2, chords[1] / 2, 82.85))
    return profiles, [main_source, flap_source]


def _element(name, s, p, source_chord, nominal_chord, metadata):
    return {
        "name": name,
        "polygon_mm": _closed_from_surfaces(s, p).tolist(),
        "suction_mm": s.tolist(),
        "pressure_mm": p.tolist(),
        "leading_edge_mm": s[0].tolist(),
        "trailing_edge_midpoint_mm": ((s[-1] + p[-1]) / 2).tolist(),
        "chord_angle_rad": _angle(s, p),
        "source_chord_mm": source_chord,
        "nominal_chord_mm": nominal_chord,
        "thickening": metadata,
    }


def validate_scene(scene):
    """Recompute geometric gates; raise before CFD on any failure."""
    if scene.get("schema") != SCHEMA or not scene.get("elements"):
        raise GeometryError("unknown or empty scene schema")
    label = scene.get("configuration", "")
    if not isinstance(label, str):
        raise GeometryError("configuration must be a string")
    sharp = label.endswith("_sharp")
    configuration = label.removesuffix("_sharp")
    if configuration not in ("E1", "E2", "E3") or len(scene["elements"]) != int(configuration[-1]):
        raise GeometryError("unknown configuration or element count")
    dx = _positive(scene["dx_mm"], "dx_mm")
    _positive(scene["height_mm"], "height_mm")
    if not np.isfinite(scene["ground_z_mm"]):
        raise GeometryError("ground location must be finite")
    if not all(np.isfinite(scene["placement"][key]) for key in ("overlap_mm", "gap_mm")):
        raise GeometryError("signed placement quantities must be finite")
    floor = _positive(scene["t_min_mm"], "t_min_mm")
    gap_floor = _positive(scene["g_min_mm"], "g_min_mm")
    if floor < 4 * dx - TOL or gap_floor < 4 * dx - TOL:
        raise GeometryError("thickness and gap thresholds cannot be below 4 dx")
    if type(scene["sharp_variant"]["enabled"]) is not bool or scene["sharp_variant"]["enabled"] != sharp:
        raise GeometryError("sharp-arm flag differs from configuration suffix")
    if scene["sharp_variant"]["mathematically_sharp"] is not False:
        raise GeometryError("sharp-arm source retains finite trailing edges")
    profiles, sources = _source_profiles(configuration)
    if scene["sources"] != sources:
        raise GeometryError("source path/SHA/provenance identity mismatch")
    normalizations = {"c1_mm": C1_MM, "c_mm": C_MM,
                      "h_over_c1": scene["height_mm"] / C1_MM, "h_over_c": scene["height_mm"] / C_MM}
    if scene["normalizations"] != normalizations:
        raise GeometryError("source normalization/height identity mismatch")
    if len(scene["placement"]["transformations"]) != len(profiles):
        raise GeometryError("source transformation count mismatch")
    if (scene["placement"]["gap_reference"] != "upstream trailing-edge midpoint"
            or scene["placement"]["flap_rotation_center_mm"] != [0.567 * C_MM, 0.076 * C_MM]):
        raise GeometryError("source gap/pivot reference mismatch")
    polygons = []
    minima = []
    required = not sharp
    for e, source, transform in zip(scene["elements"], profiles, scene["placement"]["transformations"]):
        name, raw_s, raw_p, chord, nominal = source
        if e["name"] != name:
            raise GeometryError("source element names/order mismatch")
        p = _polygon(e["polygon_mm"])
        if _self_intersects(p):
            raise GeometryError(f"{e['name']}: polygon self-intersection")
        if abs(float(_cross(p[:-1], p[1:]).sum())) <= TOL:
            raise GeometryError(f"{e['name']}: degenerate polygon area")
        s, upper = np.asarray(e["suction_mm"]), np.asarray(e["pressure_mm"])
        if s.shape != raw_s.shape or upper.shape != raw_p.shape:
            raise GeometryError(f"{name}: source paired row counts differ")
        if not np.array_equal(p, _closed_from_surfaces(s, upper)):
            raise GeometryError(f"{e['name']}: polygon/surface identity mismatch")
        if (not np.allclose(e["leading_edge_mm"], s[0], atol=TOL, rtol=0)
                or not np.allclose(e["trailing_edge_midpoint_mm"], (s[-1] + upper[-1]) / 2, atol=TOL, rtol=0)):
            raise GeometryError(f"{e['name']}: leading/trailing-edge identity mismatch")
        shift = s[0] - raw_s[0]
        scale = 0.5 if configuration == "E3" and name != "main" else 1.0
        if (transform["element"] != name or transform["source_scale"] != scale
                or not np.allclose(transform["translation_mm"], shift, atol=TOL, rtol=0)
                or (name == "main" and abs(shift[0]) > TOL)):
            raise GeometryError(f"{name}: source transformation identity mismatch")
        if not np.allclose((s + upper) / 2, (raw_s + raw_p) / 2 + shift, atol=TOL, rtol=0):
            raise GeometryError(f"{name}: source camber/TE midpoint was changed")
        if (not np.allclose(s[:3], raw_s[:3] + shift, atol=TOL, rtol=0)
                or not np.allclose(upper[:3], raw_p[:3] + shift, atol=TOL, rtol=0)):
            raise GeometryError(f"{name}: source LE cap was changed")
        if (not math.isclose(e["source_chord_mm"], chord, abs_tol=TOL, rel_tol=0)
                or e["nominal_chord_mm"] != nominal
                or not math.isclose(e["chord_angle_rad"], _angle(raw_s, raw_p), abs_tol=TOL, rel_tol=0)):
            raise GeometryError(f"{name}: source chord identity mismatch")
        if required:
            _, _, _, raw_normals, _, raw_thickness = _curves(raw_s, raw_p)
            start = int(np.argmax(raw_thickness))
            if type(e["thickening"]["controlled_from_index"]) is not int or e["thickening"]["controlled_from_index"] != start:
                raise GeometryError(f"{name}: controlled thickness scope differs from source maximum")
            actual_thickness = np.einsum("ij,ij->i", upper - s, raw_normals)
            if np.any(actual_thickness < raw_thickness - TOL):
                raise GeometryError(f"{name}: source normal thickness was reduced")
            weights = np.ones(len(raw_s))
            weights[:3] = 0
            fraction = (np.arange(3, start, dtype=float) - 2) / (start - 2)
            weights[3:start] = fraction ** 2 * (3 - 2 * fraction)
            expected_tangential = (1 - weights) * _cross(raw_p - raw_s, raw_normals)
            if not np.allclose(_cross(upper - s, raw_normals), expected_tangential, atol=TOL, rtol=0):
                raise GeometryError(f"{name}: source camber-normal reconstruction differs")
            ratio = float(np.max(actual_thickness[1:] / raw_thickness[1:]))
            if not math.isclose(e["thickening"]["max_thickness_ratio"], ratio, abs_tol=TOL, rel_tol=0):
                raise GeometryError(f"{name}: source thickness-ratio metadata differs")
            if (e["thickening"]["method"] != "camber-normal-reconstruction-v1"
                    or e["thickening"]["preserved_cap_pairs"] != 3
                    or e["thickening"]["global_positive_thickness_claim"] is not False
                    or e["thickening"]["te_midpoint_preserved"] is not True
                    or not math.isclose(e["thickening"]["t_min_mm"], floor, abs_tol=TOL, rel_tol=0)
                    or not math.isclose(e["thickening"]["original_max_thickness_mm"], float(raw_thickness.max()), abs_tol=TOL, rel_tol=0)):
                raise GeometryError(f"{name}: source thickness contract metadata differs")
            measured = _controlled_minimum(s, upper, start)
            if measured < floor - TOL:
                raise GeometryError(f"{e['name']}: controlled thickness {measured} below {floor}")
            if not math.isclose(e["thickening"]["controlled_min_thickness_mm"], measured, abs_tol=TOL, rel_tol=0):
                raise GeometryError(f"{name}: actual thickness measurement metadata differs")
            camber = (s + upper) / 2
            candidates = np.arange(start, len(camber))
            guard = (1 + math.sqrt(2) / 2) * dx
            indices = candidates[polygon_sdf(camber[candidates], p) <= -guard + TOL]
            if not len(indices):
                raise GeometryError(f"{e['name']}: no phase-independent BDIM core probe in controlled bulk")
            if (e["bulk_core_probe_station_indices"] != indices.tolist()
                    or e["bulk_core_probe_excluded_station_indices"] != candidates[~np.isin(candidates, indices)].tolist()
                    or not math.isclose(e["bulk_core_probe_guard_mm"], guard, abs_tol=TOL, rel_tol=0)
                    or not np.allclose(e["bulk_core_probe_stations_mm"], camber[indices], atol=TOL, rtol=0)):
                raise GeometryError(f"{e['name']}: bulk-core probe identity mismatch")
            minima.append({"element": e["name"], "thickness_mm": measured})
        elif (not np.allclose(s, raw_s + shift, atol=TOL, rtol=0)
              or not np.allclose(upper, raw_p + shift, atol=TOL, rtol=0)):
            raise GeometryError(f"{name}: sharp-arm original source geometry was changed")
        polygons.append(p)
    if scene["thickening"] != [{"element": e["name"], **e["thickening"]} for e in scene["elements"]]:
        raise GeometryError("element/top-level thickness metadata identity mismatch")
    gaps = []
    for upstream, downstream in zip(scene["elements"], scene["elements"][1:]):
        te = np.asarray(upstream["trailing_edge_midpoint_mm"])
        le = np.asarray(downstream["leading_edge_mm"])
        overlap = te[0] - le[0]
        gap = np.asarray(downstream["suction_mm"])[:, 1].min() - te[1]
        if (abs(overlap - scene["placement"]["overlap_mm"]) > TOL
                or abs(gap - scene["placement"]["gap_mm"]) > TOL):
            raise GeometryError("signed placement gap/overlap identity mismatch")
    for i, a in enumerate(polygons):
        for j in range(i + 1, len(polygons)):
            gap = polygon_gap(a, polygons[j])
            if gap <= TOL:
                raise GeometryError(f"element overlap: {i}, {j}")
            if gap < gap_floor - TOL:
                raise GeometryError(f"element gap {i}, {j}: {gap:.12g} mm below {gap_floor:.12g}")
            gaps.append({"elements": [scene["elements"][i]["name"], scene["elements"][j]["name"]],
                         "distance_mm": gap})
    clearance = float(min(p[:, 1].min() for p in polygons) - scene["ground_z_mm"])
    main_height = polygons[0][:, 1].min() - scene["ground_z_mm"]
    if abs(main_height - scene["height_mm"]) > TOL:
        raise GeometryError("main minimum/height identity mismatch")
    if clearance < gap_floor - TOL:
        raise GeometryError(f"ground clearance {clearance:.12g} mm below {gap_floor:.12g}")
    return {"accepted": True, "thickness_required": required,
            "thickness_scope": "original maximum-thickness station aft; LE cap and ramp excluded",
            "thickness_metric": "actual polygon width along each controlled camber-segment normal",
            "bdim_core_qualified": False,
            "controlled_minima": minima, "pair_gaps_mm": gaps,
            "clearance_mm": clearance, "self_intersections": False, "overlap": False}


def build_scene(configuration, *, height_mm, dx_mm, t_min_cells=4, g_min_cells=4,
                overlap_mm=9, gap_mm=12):
    """Build E1/E2/E3, then refuse invalid thickness/gaps/clearance before CFD.

    Gap and overlap are signed placement quantities defined in this module's
    docstring. The separate g_min gate uses true minimum Euclidean distance.
    E3 uses two half-scale source flaps with equal angle increments. `_sharp`
    is the registration's legacy arm name for unthickened finite-TE originals.
    """
    sharp = configuration.endswith("_sharp") if isinstance(configuration, str) else False
    base = configuration.removesuffix("_sharp") if isinstance(configuration, str) else ""
    if base not in ("E1", "E2", "E3"):
        raise GeometryError(f"unknown configuration: {configuration}")
    height = _positive(height_mm, "height_mm")
    dx = _positive(dx_mm, "dx_mm")
    t_cells, g_cells = _positive(t_min_cells, "t_min_cells"), _positive(g_min_cells, "g_min_cells")
    if min(t_cells, g_cells) < 4:
        raise GeometryError("thickness and gap thresholds cannot be below 4 dx")
    if not np.isfinite(overlap_mm) or not np.isfinite(gap_mm):
        raise GeometryError("overlap and gap must be finite")
    profiles, sources = _source_profiles(base)
    elements, transformations = [], []
    for name, suction, pressure, source_chord, nominal in profiles:
        if sharp:
            metadata = {"method": "unthickened-source", "max_thickness_ratio": 1.0,
                        "global_positive_thickness_claim": False}
        else:
            suction, pressure, metadata = thicken_element(suction, pressure, t_min_mm=t_cells * dx)
        if not elements:
            shift = np.array([0.0, height - min(suction[:, 1].min(), pressure[:, 1].min())])
        else:
            previous_te = np.asarray(elements[-1]["trailing_edge_midpoint_mm"])
            shift = np.array([previous_te[0] - overlap_mm - suction[0, 0],
                              previous_te[1] + gap_mm - suction[:, 1].min()])
        suction, pressure = suction + shift, pressure + shift
        element = _element(name, suction, pressure, source_chord, nominal, metadata)
        if not sharp:
            camber = (suction + pressure) / 2
            candidates = np.arange(metadata["controlled_from_index"], len(camber))
            guard = (1 + math.sqrt(2) / 2) * dx
            selected = polygon_sdf(camber[candidates], element["polygon_mm"]) <= -guard + TOL
            element.update({
                "bulk_core_probe_station_indices": candidates[selected].tolist(),
                "bulk_core_probe_stations_mm": camber[candidates[selected]].tolist(),
                "bulk_core_probe_excluded_station_indices": candidates[~selected].tolist(),
                "bulk_core_probe_guard_mm": guard,
                "bulk_core_probe_guarantee": "exact SDF plus 1-Lipschitz nearest-grid bound; WaterLily measure! verification remains separate",
            })
        elements.append(element)
        transformations.append({"element": name, "translation_mm": shift.tolist(),
                                "source_scale": 0.5 if base == "E3" and name != "main" else 1.0})
    scene = {
        "schema": SCHEMA, "configuration": configuration, "height_mm": height, "dx_mm": dx,
        "ground_z_mm": 0.0, "t_min_mm": t_cells * dx, "g_min_mm": g_cells * dx,
        "normalizations": {"c1_mm": C1_MM, "c_mm": C_MM,
                           "h_over_c1": height / C1_MM, "h_over_c": height / C_MM},
        "placement": {"overlap_mm": float(overlap_mm), "gap_mm": float(gap_mm),
                      "gap_reference": "upstream trailing-edge midpoint",
                      "flap_rotation_center_mm": [0.567 * C_MM, 0.076 * C_MM],
                      "e3_rule": "two half-scale source profiles; equal main-to-flap angle increments",
                      "transformations": transformations},
        "sharp_variant": {"enabled": sharp, "mathematically_sharp": False,
                          "meaning": "legacy registration arm name; original finite trailing edges retained"},
        "elements": elements,
        "thickening": [{"element": e["name"], **e["thickening"]} for e in elements],
        "sources": sources,
    }
    scene["gates"] = validate_scene(scene)
    return scene


def write_scene(scene, path):
    """Export deterministic JSON after rechecking gates."""
    if validate_scene(scene) != scene["gates"]:
        raise GeometryError("scene contains stale gate results")
    Path(path).write_text(json.dumps(scene, sort_keys=True, indent=2, allow_nan=False) + "\n")


def save_npz(scene, path):
    """Export deterministic, pickle-free NPZ polygons and the complete JSON record."""
    if validate_scene(scene) != scene["gates"]:
        raise GeometryError("scene contains stale gate results")
    arrays = {f"polygon_{i}_mm": np.asarray(e["polygon_mm"], dtype="<f8")
              for i, e in enumerate(scene["elements"])}
    arrays["scene_json"] = np.array(json.dumps(scene, sort_keys=True, allow_nan=False))
    # np.savez embeds current ZIP timestamps on some NumPy versions. Fix only
    # that container metadata; .npy payloads use the standard NumPy writer.
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, array in arrays.items():
            buffer = io.BytesIO()
            np.save(buffer, array, allow_pickle=False)
            item = zipfile.ZipInfo(f"{name}.npy", date_time=(1980, 1, 1, 0, 0, 0))
            item.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(item, buffer.getvalue())


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--configuration", required=True, choices=[f"E{i}{suffix}" for i in (1, 2, 3) for suffix in ("", "_sharp")])
    parser.add_argument("--height-mm", type=float, required=True)
    parser.add_argument("--dx-mm", type=float, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--npz-output", type=Path)
    args = parser.parse_args(argv)
    scene = build_scene(args.configuration, height_mm=args.height_mm, dx_mm=args.dx_mm)
    write_scene(scene, args.output)
    if args.npz_output:
        save_npz(scene, args.npz_output)
    print(json.dumps({"output": str(args.output), "gates": scene["gates"]}, sort_keys=True))


if __name__ == "__main__":
    main()
