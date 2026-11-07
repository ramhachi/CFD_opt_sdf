"""Source-table wing series in mm, with polygon SDFs and pre-CFD gates.

Flow is +x and z is up. Positive overlap is upstream TE-midpoint x minus
downstream LE x. Positive gap is downstream suction minimum z minus upstream
TE-midpoint z: the stable reference for a finite TE under symmetric thickening.
The source's quoted gap must not be mistaken for minimum Euclidean clearance.

The retained LE cap extends 2% of nominal chord in surface arc length from LE.
Natural cubic splines interpolate the source contour (T2-0's rule), keeping its
finite TE. Polygon segments are 0.1–1 mm, adjacent lengths differ by <=3,
and turns are <=5 degrees except at the two TE cap corners. The implicit
closing edge is included in every check; no closing vertex is duplicated.
The normal-thickness floor applies from the original maximum thickness
station aft, including TE; the cap and smoothstep ramp are disclosed.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
from functools import lru_cache
from pathlib import Path
import zipfile

import numpy as np
from scipy.integrate import quad
from scipy.interpolate import CubicSpline, PchipInterpolator


ROOT = Path(__file__).resolve().parents[3]
C1_MM = 223.4
C_MM = 380.0
SCHEMA = "topo2d-scene-v1"
TOL = 1e-9
MAX_ARC_MM = 1.0
MIN_SEGMENT_MM = 0.1
MAX_ADJACENT_RATIO = 3.0
MAX_TURN_DEG = 5.0


def _arc(curve):
    return np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(curve, axis=0), axis=1))]


def _cap_weights(suction, pressure, thickness, chord_mm):
    """Preserve both surface caps, then smoothstep in camber arc (not indices)."""
    camber_arc = _arc((suction + pressure) / 2)
    surface_arc = np.minimum(_arc(suction), _arc(pressure))
    cap_arc = .02 * chord_mm
    kept = surface_arc <= cap_arc + TOL
    start = int(np.argmax(thickness))
    # Interpolate the precise cap end in the common paired coordinate. A pair
    # stays untouched whenever either of its surface points is in its cap.
    cap_end = float(np.interp(cap_arc, surface_arc, camber_arc))
    if camber_arc[start] <= cap_end or start == len(suction) - 1:
        raise GeometryError("maximum thickness must lie after the preserved LE cap and before TE")
    fraction = np.clip((camber_arc - cap_end) / (camber_arc[start] - cap_end), 0, 1)
    weights = fraction ** 2 * (3 - 2 * fraction)
    weights[kept] = 0
    return start, weights, kept, cap_arc


def _turns(curve):
    edges = np.diff(curve, axis=0)
    lengths = np.linalg.norm(edges, axis=1)
    cosine = np.einsum("ij,ij->i", edges[:-1], edges[1:]) / (lengths[:-1] * lengths[1:])
    return np.degrees(np.arccos(np.clip(cosine, -1, 1)))


def _sampling_gate(polygon, cap_vertices):
    """Check the four registered bounds cyclically, including the closing edge."""
    p = np.asarray(polygon, dtype=float)
    if len(np.unique(p, axis=0)) != len(p):
        raise GeometryError("polygon has a duplicated vertex, including its closing endpoint")
    edges = np.roll(p, -1, axis=0) - p
    lengths = np.linalg.norm(edges, axis=1)
    if lengths.min() < MIN_SEGMENT_MM - TOL:
        raise GeometryError("polygon segment below 0.1 mm")
    if lengths.max() > MAX_ARC_MM + TOL:
        raise GeometryError("polygon segment exceeds 1 mm")
    ratios = lengths / np.roll(lengths, 1)
    ratio = float(np.maximum(ratios, 1 / ratios).max())
    if ratio > MAX_ADJACENT_RATIO + TOL:
        raise GeometryError("polygon adjacent-segment length ratio exceeds 3")
    cosine = np.einsum("ij,ij->i", edges, np.roll(edges, 1, axis=0)) / (lengths * np.roll(lengths, 1))
    turns = np.degrees(np.arccos(np.clip(cosine, -1, 1)))
    maximum_turn = float(np.delete(turns, cap_vertices).max())
    if maximum_turn > MAX_TURN_DEG + TOL:
        raise GeometryError("polygon non-cap turning angle exceeds 5 degrees")
    return {"min_segment_mm": float(lengths.min()), "max_segment_mm": float(lengths.max()),
            "max_adjacent_segment_ratio": ratio, "max_noncap_turn_deg": maximum_turn}


def _sampling_metrics(suction, pressure, chord_mm):
    # Only the two TE corners are exempt, not the preserved leading-edge cap.
    polygon = _closed_from_surfaces(suction, pressure)
    return {**_sampling_gate(polygon, [0, len(suction) + len(pressure) - 2]),
            "leading_edge_cap_arc_mm": .02 * chord_mm,
            "trailing_edge_cap": "straight finite-thickness closure"}


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
    if p.ndim != 2 or p.shape[1] != 2 or len(p) < 3 or not np.isfinite(p).all():
        raise GeometryError("polygon must contain finite two-dimensional vertices")
    # Geometry files use an implicit closing edge. Retain explicit closure as
    # an input convenience for the general SDF helpers, never in scene JSON.
    if not np.array_equal(p[0], p[-1]):
        p = np.vstack((p, p[:1]))
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
    # Sampling is nonuniform after spline refinement. Differentiate in arc
    # length so inserting a vertex does not change the offset direction.
    tangent = np.gradient(c, _arc(c), axis=0)
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
    # Collinear subdivisions on the finite TE have exactly the same boundary.
    # Use one cap segment for the continuous ray proof: its endpoints are the
    # extremes, rather than artificial zero-distance interior cap vertices.
    return _normal_ray_minimum(_closed_from_surfaces(s, p, densify_cap=False), camber, start)


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


def thicken_element(suction, pressure, *, t_min_mm, chord_mm=None):
    """Camber-normal reconstruction; keep the 2% chord LE cap and TE midpoint.

    Remove the source pairs' tangential separation while smoothly leaving the
    LE cap; construct the controlled bulk as camber +/- normal * half-thickness.
    The actual polygon normal-ray width gate is independent of paired projection.
    The preserved cap and smoothstep ramp are explicitly excluded from that
    positive floor, since thickness at a closed leading edge is zero.
    """
    floor = _positive(t_min_mm, "t_min_mm")
    s, p, camber, normals, segment_normals, thickness = _curves(suction, pressure)
    chord = _positive(chord_mm if chord_mm is not None else np.linalg.norm(camber[-1] - camber[0]), "chord_mm")
    start, weights, kept, cap_arc = _cap_weights(s, p, thickness, chord)
    # A hard max(original, floor) introduces a tangent kink where they cross.
    # Its smooth L8 envelope remains >= both widths without moving the camber.
    # The scaled form avoids overflow and needs no geometry tuning threshold.
    scale = np.maximum(thickness, floor)
    target = scale * ((thickness / scale) ** 8 + (floor / scale) ** 8) ** (1 / 8)
    for j in range(start, len(s) - 1):
        for i in (j, j + 1):
            projection = float(normals[i] @ segment_normals[j])
            if projection <= 0:
                raise GeometryError("camber normal turns by >=90 degrees")
            target[i] = max(target[i], floor / projection)
    def reconstruct(extra):
        offsets = (target - thickness) / 2
        offsets[start:] += extra
        offsets[:start] = offsets[start] * weights[:start]
        difference = ((1 - weights[:, None]) * (p - s)
                      + weights[:, None] * thickness[:, None] * normals
                      + 2 * offsets[:, None] * normals)
        lower, upper = camber - difference / 2, camber + difference / 2
        lower[kept], upper[kept] = s[kept], p[kept]
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
        "method": "camber-normal-arclength-v2",
        "t_min_mm": floor,
        "bulk_width_envelope": "smooth L8 norm of source normal width and t_min; projection/ray correction only increases it",
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
        "preserved_cap_pairs": int(kept.sum()),
        "preserved_cap_arc_mm": cap_arc,
        "cap_radius_claim": "unchanged interpolating spline samples in the 2% chord surface-arc cap",
        "ramp": "smoothstep in camber arc from surface-arc cap end to original maximum-thickness station",
        "global_positive_thickness_claim": False,
        "original_max_thickness_mm": float(thickness.max()),
        "max_thickness_ratio": float(np.max(actual[1:] / thickness[1:])),
        "te_midpoint_preserved": bool(np.allclose((lower[-1] + upper[-1]) / 2, camber[-1], atol=TOL, rtol=0)),
    }
    return lower, upper, metadata


def _closed_from_surfaces(s, p, *, densify_cap=True):
    # Keep the finite TE, and subdivide its straight closure too. Both closure
    # corners are explicit caps, not spurious aerodynamic surface vertices.
    divisions = max(1, math.ceil(np.linalg.norm(p[-1] - s[-1]) / MAX_ARC_MM)) if densify_cap else 1
    # Exclude both endpoints: pressure TE is already present; the suction TE
    # is polygon[0] and is joined implicitly, never duplicated as a last point.
    cap = np.linspace(p[-1], s[-1], divisions + 1)[1:-1]
    polygon = np.vstack((s[::-1], p[1:], cap))
    return polygon


@lru_cache(maxsize=4)
def _resampled_table(filename, source_sha):
    """T2-0 natural contour spline, with monotone pairing of the source rows.

    airfoil_points itself fixes COORDS/CHORD and collapses the finite TE. Reuse
    its CubicSpline(chordal arc, contour, bc_type='natural') rule instead. The
    two monotone PCHIP maps only pair surface stations; they do not change the
    contour spline. Distribute a common arc/curvature monitor separately within
    each source interval, keeping every table point without unioning nearly
    coincident sample grids. Final polygon gates check the actual output.
    """
    path = ROOT / "data" / "zz2003" / filename
    if hashlib.sha256(path.read_bytes()).hexdigest() != source_sha:
        raise GeometryError("source changed during spline resampling")
    rows = np.loadtxt(path) * C_MM
    s, p = rows[:, :2], rows[:, 2:]
    q = _arc((s + p) / 2)
    sa, pa = _arc(s), _arc(p)
    contour = np.vstack((s[::-1], p[1:]))
    spline = CubicSpline(_arc(contour), contour, bc_type="natural")
    smap, pmap = PchipInterpolator(q, sa), PchipInterpolator(q, pa)
    # These sampling targets leave room for offsets and the E3 half-scale;
    # the registered acceptance bounds remain 0.1–1 mm, 5 degrees and ratio 3.
    u = np.unique(np.r_[q, np.linspace(0, q[-1], math.ceil(max(sa[-1], pa[-1]) / .01) + 1)])
    monitor = np.zeros(len(u))
    for mapping, sign in ((smap, -1), (pmap, 1)):
        parameter = sa[-1] + sign * mapping(u)
        dpar, ddpar = sign * mapping(u, 1), sign * mapping(u, 2)
        first = spline(parameter, 1) * dpar[:, None]
        second = spline(parameter, 2) * dpar[:, None] ** 2 + spline(parameter, 1) * ddpar[:, None]
        speed = np.linalg.norm(first, axis=1)
        if np.any(speed <= 0):
            raise GeometryError("singular spline parameterization")
        rotation = np.abs(_cross(first, second)) / speed ** 2
        monitor = np.maximum(monitor, np.maximum(speed / .65, rotation / math.radians(3.5)))
    metric = np.r_[0, np.cumsum(np.diff(u) * (monitor[1:] + monitor[:-1]) / 2)]
    knots = np.interp(q, u, metric)
    intervals = []
    for i, (a, b) in enumerate(zip(knots[:-1], knots[1:])):
        part = np.interp(np.linspace(a, b, math.ceil(b - a) + 1)[:-1], metric, u)
        part[0] = q[i]
        intervals.append(part)
    stations = np.r_[np.concatenate(intervals), q[-1]]
    st, pt = sa[-1] - smap(stations), sa[-1] + pmap(stations)
    lower, upper = spline(st), spline(pt)
    lower[0] = upper[0] = s[0]
    lower[-1], upper[-1] = s[-1], p[-1]
    # Independent speed integral bounds the spline arc, not just its chord.
    derivative = spline.derivative()
    arc_max = max(quad(lambda v: float(np.linalg.norm(derivative(v))), min(a, b), max(a, b),
                       epsabs=1e-10, epsrel=1e-10)[0]
                  for parameters in (st, pt) for a, b in zip(parameters[:-1], parameters[1:]))
    if arc_max > MAX_ARC_MM + TOL:
        raise GeometryError("spline arc spacing exceeds 1 mm")
    return lower, upper, float(arc_max)


def _source_table(filename):
    path = ROOT / "data" / "zz2003" / filename
    if not path.is_file():
        raise GeometryError(f"required source table is missing: {path}")
    rows = np.loadtxt(path)
    if rows.ndim != 2 or rows.shape[1] != 4 or not np.isfinite(rows).all():
        raise GeometryError(f"invalid source table: {path}")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    suction, pressure, arc_max = _resampled_table(filename, digest)
    return suction, pressure, {
        "path": path.relative_to(ROOT).as_posix(),
        "sha256": digest,
        "url": "https://eprints.soton.ac.uk/426058/1/00192634.pdf",
        "verification": "UNVERIFIED_OCR",
        "normalization_chord_mm": C_MM,
        "spline_max_arc_mm": arc_max,
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
        "sampling": _sampling_metrics(s, p, nominal_chord),
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
    if scene.get("sampling") != {"method": "natural-cubic-spline-arclength", "max_arc_mm": MAX_ARC_MM,
                                 "min_segment_mm": MIN_SEGMENT_MM, "max_adjacent_segment_ratio": MAX_ADJACENT_RATIO,
                                 "closure": "implicit; no duplicated terminal vertex",
                                 "max_noncap_turn_deg": MAX_TURN_DEG, "leading_edge_cap_chord_fraction": .02}:
        raise GeometryError("spline sampling contract mismatch")
    if len(scene["placement"]["transformations"]) != len(profiles):
        raise GeometryError("source transformation count mismatch")
    if (scene["placement"]["gap_reference"] != "upstream trailing-edge midpoint"
            or scene["placement"]["flap_rotation_center_mm"] != [0.567 * C_MM, 0.076 * C_MM]):
        raise GeometryError("source gap/pivot reference mismatch")
    chord_vector = (np.asarray(scene["elements"][-1]["trailing_edge_midpoint_mm"])
                    - np.asarray(scene["elements"][0]["leading_edge_mm"]))
    if (not math.isclose(scene["placement"]["combined_chord_mm"], float(np.linalg.norm(chord_vector)), abs_tol=TOL)
            or not math.isclose(scene["placement"]["combined_incidence_deg"], math.degrees(math.atan2(chord_vector[1], chord_vector[0])), abs_tol=TOL)
            or scene["placement"]["nominal_incidence_deg"] != 14.1):
        raise GeometryError("placed chord/incidence metadata mismatch")
    polygons = []
    minima = []
    required = not sharp
    for e, source, transform in zip(scene["elements"], profiles, scene["placement"]["transformations"]):
        name, raw_s, raw_p, chord, nominal = source
        if e["name"] != name:
            raise GeometryError("source element names/order mismatch")
        if len(np.unique(np.asarray(e["polygon_mm"]), axis=0)) != len(e["polygon_mm"]):
            raise GeometryError(f"{name}: duplicated polygon vertex, including closing endpoint")
        p = _polygon(e["polygon_mm"])
        if _self_intersects(p):
            raise GeometryError(f"{e['name']}: polygon self-intersection")
        if abs(float(_cross(p[:-1], p[1:]).sum())) <= TOL:
            raise GeometryError(f"{e['name']}: degenerate polygon area")
        s, upper = np.asarray(e["suction_mm"]), np.asarray(e["pressure_mm"])
        if s.shape != raw_s.shape or upper.shape != raw_p.shape:
            raise GeometryError(f"{name}: source paired row counts differ")
        if not np.array_equal(p[:-1], _closed_from_surfaces(s, upper)):
            _sampling_gate(e["polygon_mm"], [0, len(s) + len(upper) - 2])
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
        _, _, _, raw_normals, _, raw_thickness = _curves(raw_s, raw_p)
        start, weights, kept, cap_arc = _cap_weights(raw_s, raw_p, raw_thickness, nominal)
        if (not np.allclose(s[kept], raw_s[kept] + shift, atol=TOL, rtol=0)
                or not np.allclose(upper[kept], raw_p[kept] + shift, atol=TOL, rtol=0)):
            raise GeometryError(f"{name}: source LE cap was changed")
        if (not math.isclose(e["source_chord_mm"], chord, abs_tol=TOL, rel_tol=0)
                or e["nominal_chord_mm"] != nominal
                or not math.isclose(e["chord_angle_rad"], _angle(raw_s, raw_p), abs_tol=TOL, rel_tol=0)):
            raise GeometryError(f"{name}: source chord identity mismatch")
        if required:
            if type(e["thickening"]["controlled_from_index"]) is not int or e["thickening"]["controlled_from_index"] != start:
                raise GeometryError(f"{name}: controlled thickness scope differs from source maximum")
            actual_thickness = np.einsum("ij,ij->i", upper - s, raw_normals)
            if np.any(actual_thickness < raw_thickness - TOL):
                raise GeometryError(f"{name}: source normal thickness was reduced")
            expected_tangential = (1 - weights) * _cross(raw_p - raw_s, raw_normals)
            if not np.allclose(_cross(upper - s, raw_normals), expected_tangential, atol=TOL, rtol=0):
                raise GeometryError(f"{name}: source camber-normal reconstruction differs")
            ratio = float(np.max(actual_thickness[1:] / raw_thickness[1:]))
            if not math.isclose(e["thickening"]["max_thickness_ratio"], ratio, abs_tol=TOL, rel_tol=0):
                raise GeometryError(f"{name}: source thickness-ratio metadata differs")
            if (e["thickening"]["method"] != "camber-normal-arclength-v2"
                    or e["thickening"]["preserved_cap_pairs"] != int(kept.sum())
                    or e["thickening"]["preserved_cap_arc_mm"] != cap_arc
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
        sampling = _sampling_metrics(s, upper, nominal)
        if sampling != e["sampling"]:
            raise GeometryError(f"{name}: stale sampling metrics")
        if sampling["max_segment_mm"] > MAX_ARC_MM + TOL:
            raise GeometryError(f"{name}: polygon arc spacing exceeds 1 mm")
        if sampling["max_noncap_turn_deg"] > MAX_TURN_DEG + TOL:
            raise GeometryError(f"{name}: non-cap turning angle exceeds 5 degrees")
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
            suction, pressure, metadata = thicken_element(suction, pressure, t_min_mm=t_cells * dx, chord_mm=nominal)
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
    chord_vector = np.asarray(elements[-1]["trailing_edge_midpoint_mm"]) - elements[0]["leading_edge_mm"]
    scene = {
        "schema": SCHEMA, "configuration": configuration, "height_mm": height, "dx_mm": dx,
        "ground_z_mm": 0.0, "t_min_mm": t_cells * dx, "g_min_mm": g_cells * dx,
        "normalizations": {"c1_mm": C1_MM, "c_mm": C_MM,
                           "h_over_c1": height / C1_MM, "h_over_c": height / C_MM},
        "sampling": {"method": "natural-cubic-spline-arclength", "max_arc_mm": MAX_ARC_MM,
                     "min_segment_mm": MIN_SEGMENT_MM, "max_adjacent_segment_ratio": MAX_ADJACENT_RATIO,
                     "closure": "implicit; no duplicated terminal vertex",
                     "max_noncap_turn_deg": MAX_TURN_DEG, "leading_edge_cap_chord_fraction": .02},
        "placement": {"overlap_mm": float(overlap_mm), "gap_mm": float(gap_mm),
                      "gap_reference": "upstream trailing-edge midpoint",
                      "flap_rotation_center_mm": [0.567 * C_MM, 0.076 * C_MM],
                      "combined_chord_mm": float(np.linalg.norm(chord_vector)),
                      "combined_incidence_deg": math.degrees(math.atan2(chord_vector[1], chord_vector[0])),
                      "nominal_incidence_deg": 14.1,
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
