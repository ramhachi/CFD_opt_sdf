#!/usr/bin/env python3
"""Multi-body gmsh assembly using the immutable T2-0 mesh/statistics helpers.

Inputs are metre-valued closed contours; no published geometry is reconstructed.
The registered realisation index deterministically changes line ordering and
the far-field box. Its mesh SHA remains the artifact; Kaggle determinism is
recorded separately for one index (TOPO-2D-00 Amendment 3 §2).
"""
from __future__ import annotations

import hashlib
import io
import json
import math
import re
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import t20_case as T

FAMILIES = ('fine30', 'med30')
STUDY_CONFIGS = {f'E{i}{suffix}' for i in (1, 2, 3) for suffix in ('', '_sharp')}
# TOPO-2D-00 Amendment 1 §1; density is validated, never repaired in WP5.
MAX_TURN_DEG = 5.0
# TOPO-2D-00 Amendment 3 §1: fixed fine30-based floor, also for med30/caps.
MIN_SEGMENT_M = .05 * T.MESHES['fine30']['ds']
MAX_ADJACENT_RATIO = 3.0


def _density(p, kind, cap_start, family, name):
    edges = np.diff(p, axis=0)
    lengths = np.linalg.norm(edges, axis=1)
    ds = T.MESHES[family]['ds']
    # Amendment 3 §1 replaces the old <=1 mm wording with four joint guards.
    # Its 1 mm maximum also satisfies the family's coarser wall-spacing bound.
    max_segment = min(T.PT_SPACING, ds)
    j = int(np.argmax(lengths))
    if lengths[j] > max_segment + 1e-12:
        raise ValueError(f'{name}: segment {j} length {lengths[j]:.9g} m exceeds registered maximum {max_segment:g} m ({family} ds={ds:g} m; including cap segments)')
    j = int(np.argmin(lengths))
    if lengths[j] < MIN_SEGMENT_M - 1e-12:
        raise ValueError(f'{name}: segment {j} length {lengths[j]:.9g} m is below minimum {MIN_SEGMENT_M:g} m (including cap segments)')
    previous_lengths = np.roll(lengths, 1)
    ratios = np.maximum(lengths / previous_lengths, previous_lengths / lengths)
    j = int(np.argmax(ratios))
    if ratios[j] > MAX_ADJACENT_RATIO + 1e-10:
        raise ValueError(f'{name}: adjacent segments {(j - 1) % len(lengths)}/{j} length ratio {ratios[j]:.9g} exceeds {MAX_ADJACENT_RATIO:g} (including cap segments)')
    previous = np.roll(edges, 1, axis=0)
    turns = np.degrees(np.arccos(np.clip((previous * edges).sum(1) /
                       (np.roll(lengths, 1) * lengths), -1, 1)))
    # A sharp cusp's TE or the two finite-cap endpoint corners are intentional.
    turns[0] = 0
    if kind == 'blunt':
        turns[cap_start] = 0
    j = int(np.argmax(turns))
    if turns[j] > MAX_TURN_DEG + 1e-10:
        raise ValueError(f'{name}: non-cap vertex {j} turn {turns[j]:.9g} deg exceeds {MAX_TURN_DEG:g} deg; require WP4 smooth resampling')
    return {'family': family, 'max_segment_m': float(lengths.max()), 'min_segment_m': float(lengths.min()),
            'max_adjacent_segment_ratio': float(ratios.max()), 'limit_adjacent_segment_ratio': MAX_ADJACENT_RATIO,
            'limit_min_segment_m': MIN_SEGMENT_M,
            'max_noncap_turn_deg': float(turns.max()), 'limit_turn_deg': MAX_TURN_DEG,
            'limit_segment_m': max_segment, 'family_wall_spacing_m': ds}


def _cap(p, start):
    """Validate supplied straight cap vertices; no insertion/interpolation."""
    if type(start) is not int or not 0 < start < len(p) - 1:
        raise ValueError('blunt cap_start_index must identify the second TE endpoint')
    v = p[0] - p[start]
    length = np.linalg.norm(v)
    if length <= 1e-12:
        raise ValueError('finite trailing-edge cap is missing')
    r = p[start:] - p[start]
    t = r @ v / length**2
    if (np.linalg.norm(r - t[:, None] * v, axis=1).max() > 1e-12 or
            np.any(np.diff(t) <= 0) or t[0] != 0 or abs(t[-1] - 1) > 1e-12):
        raise ValueError('cap_start_index must bound a straight, ordered finite closing cap')
    return start


def _distance(a, b):
    """Minimum distance between disjoint polygon edges (endpoints to segments)."""
    def one(p, q):
        v = q[1:] - q[:-1]
        r = p[:-1, None] - q[None, :-1]
        s = np.clip((r * v).sum(2) / (v * v).sum(1), 0, 1)
        return float(np.linalg.norm(r - s[..., None] * v, axis=2).min())
    return min(one(a, b), one(b, a))


def _crossings(a, b):
    """Closed-segment intersections, including touches/collinear overlap."""
    p, q = a[:-1, None], b[None, :-1]
    r, s = (a[1:] - a[:-1])[:, None], (b[1:] - b[:-1])[None]
    cross = lambda u, v: u[..., 0] * v[..., 1] - u[..., 1] * v[..., 0]
    o1, o2 = cross(r, q - p), cross(r, q + s - p)
    o3, o4 = cross(s, p - q), cross(s, p + r - q)
    boxes = (np.maximum(np.minimum(p, p + r), np.minimum(q, q + s)) <=
             np.minimum(np.maximum(p, p + r), np.maximum(q, q + s)) + 1e-12).all(2)
    return boxes & (o1 * o2 <= 0) & (o3 * o4 <= 0)


def _inside(p, q):
    a, b = q[:-1], q[1:]
    hit = (a[:, 1] > p[1]) != (b[:, 1] > p[1])
    return bool(np.count_nonzero(hit & (p[0] < a[:, 0] + (p[1] - a[:, 1]) *
                (b[:, 0] - a[:, 0]) / np.where(b[:, 1] != a[:, 1], b[:, 1] - a[:, 1], 1))) % 2)


def _wp4_scene(scene: dict) -> tuple[dict, dict]:
    """Adapt the actual WP4 polygon/surface contract without changing the body."""
    if scene.get('schema') != 'topo2d-scene-v1' or scene.get('units', 'mm') != 'mm':
        raise ValueError('unsupported WP4 scene schema or units')
    # Metre↔millimetre conversion permits only floating-point serialization roundoff.
    c1 = scene.get('normalizations', {}).get('c1_mm')
    if scene.get('ground_z_mm') != 0 or not isinstance(c1, (int, float)) or not math.isclose(c1, T.CHORD * 1000, rel_tol=0, abs_tol=1e-10):
        raise ValueError('WP4 scene requires ground_z_mm=0 and common c1_mm=223.4')
    if scene.get('gates', {}).get('accepted') is not True:
        raise ValueError('WP4 scene requires accepted geometric gates')
    if scene.get('sharp_variant', {}).get('mathematically_sharp') is not False:
        raise ValueError('WP4 scene must explicitly retain finite-thickness trailing edges')
    elements = scene.get('elements')
    if not isinstance(elements, list) or not elements:
        raise ValueError('WP4 scene requires elements')
    converted = []
    for element in elements:
        lower = np.asarray(element.get('suction_mm'), float)
        upper = np.asarray(element.get('pressure_mm'), float)
        polygon = np.asarray(element.get('polygon_mm'), float)
        if lower.ndim != 2 or lower.shape[1] != 2 or len(lower) < 4 or upper.shape != lower.shape or not np.isfinite(lower).all() or not np.isfinite(upper).all():
            raise ValueError('WP4 paired surfaces must be finite matching N x 2 arrays, N>=4')
        if not np.array_equal(lower[0], upper[0]):
            raise ValueError('WP4 surfaces must share their leading edge')
        prefix = np.vstack((lower[::-1], upper[1:]))
        # WP4 may supply extra straight cap points to meet the all-segment ds
        # guard. The exact supplied vertices, including those points, are kept.
        if (polygon.ndim != 2 or polygon.shape[1] != 2 or len(polygon) <= len(prefix) or
                not np.array_equal(polygon[:len(prefix)], prefix) or not np.array_equal(polygon[-1], lower[-1])):
            raise ValueError('WP4 polygon/surface identity mismatch')
        if np.linalg.norm(lower[-1] - upper[-1]) <= 1e-9:
            raise ValueError('WP4 finite trailing-edge cap is missing')
        _cap(polygon, len(prefix) - 1)
        converted.append({'name': element['name'], 'points_m': (polygon * .001).tolist(), 'te_kind': 'blunt',
                          'cap_start_index': len(prefix) - 1,
                          'source_element_metadata': {k: v for k, v in element.items() if k not in ('polygon_mm', 'suction_mm', 'pressure_mm')}})
    nominal = float(scene['height_mm']) * .001
    main_clearance = float(np.asarray(converted[0]['points_m'])[:, 1].min())
    if not math.isfinite(nominal) or nominal <= 0 or not math.isclose(nominal, main_clearance, rel_tol=0, abs_tol=1e-9):
        raise ValueError('WP4 height_mm differs from main-element contour clearance')
    metadata = {key: value for key, value in scene.items() if key != 'elements'}
    return {'config': scene['configuration'], 'elements': converted, 'main_chord_m': T.CHORD,
            'nominal_ride_height_m': nominal,
            'height_datum': 'WP4 height_mm: main-element minimum of exported current contour above ground'}, metadata


def load_geometry(source: Path | str | dict, family='fine30', *, expected_height_m=None) -> dict:
    """Read strict JSON or NPZ(metadata_json + points_key arrays), validate, hash.

    JSON keys: config, elements[{name, points_m, te_kind:sharp|blunt}].
    First point is the TE; for blunt bodies the closing edge is the finite cap.
    All forces use the common T2-0 main chord, never each body's own chord.
    """
    if family not in FAMILIES:
        raise ValueError(f'family must be one of {FAMILIES}')
    if isinstance(source, dict):
        spec = source
        raw = json.dumps(source, sort_keys=True, separators=(',', ':'), allow_nan=True).encode()
        label = '<inline geometry>'
    else:
        path = Path(source)
        raw, label = path.read_bytes(), str(path)
        if path.suffix.lower() == '.json':
            spec = json.loads(raw)
        elif path.suffix.lower() == '.npz':
            with np.load(io.BytesIO(raw), allow_pickle=False) as data:
                if 'scene_json' in data:
                    if 'metadata_json' in data or data['scene_json'].shape != () or data['scene_json'].dtype.kind != 'U':
                        raise ValueError('WP4 NPZ requires an unambiguous Unicode scalar scene_json')
                    spec = json.loads(str(data['scene_json'].item()))
                    if not isinstance(spec, dict) or spec.get('schema') != 'topo2d-scene-v1' or not isinstance(spec.get('elements'), list):
                        raise ValueError('WP4 NPZ scene_json schema is invalid')
                    for i, e in enumerate(spec['elements']):
                        key = f'polygon_{i}_mm'
                        if key not in data or not np.array_equal(data[key], np.asarray(e.get('polygon_mm'), float)):
                            raise ValueError(f'WP4 NPZ {key} polygon/scene_json mismatch')
                else:
                    if 'metadata_json' not in data or data['metadata_json'].shape != () or data['metadata_json'].dtype.kind != 'U':
                        raise ValueError('NPZ requires scalar Unicode metadata_json')
                    spec = json.loads(str(data['metadata_json'].item()))
                    for e in spec['elements']:
                        if 'points_m' in e or e.get('points_key') not in data:
                            raise ValueError('NPZ element requires an existing points_key, not points_m')
                        e['points_m'] = data[e['points_key']].tolist()
        else:
            raise ValueError('geometry must be .json or .npz')
    source_metadata = None
    if isinstance(spec, dict) and 'schema' in spec:
        spec, source_metadata = _wp4_scene(spec)
    if not isinstance(spec, dict) or not isinstance(spec.get('config'), str) or not re.fullmatch(r'[A-Za-z0-9_.-]+', spec['config']):
        raise ValueError('geometry requires a nonempty safe config identifier')
    if spec.get('units', 'm') != 'm':
        raise ValueError('geometry units must be m')
    if any(spec.get(key, T.CHORD) != T.CHORD for key in ('main_chord_m', 'reference_chord_m')):
        raise ValueError(f'all configs require common main/reference_chord_m={T.CHORD}')
    elements = spec.get('elements')
    if not isinstance(elements, list) or not 1 <= len(elements) <= 3:
        raise ValueError('geometry requires 1, 2 or 3 elements')
    expected = {'E1': 1, 'E1_sharp': 1, 'E2': 2, 'E2_sharp': 2, 'E3': 3, 'E3_sharp': 3}.get(spec['config'])
    if expected is not None and len(elements) != expected:
        raise ValueError(f'{spec["config"]} element count must be {expected}')
    nominal = spec.get('nominal_ride_height_m')
    datum = spec.get('height_datum')
    if nominal is not None and (not math.isfinite(float(nominal)) or float(nominal) <= 0 or not isinstance(datum, str) or not datum):
        raise ValueError('nominal_ride_height_m must be positive finite and carry height_datum')
    out, names = [], set()
    for i, e in enumerate(elements):
        if not isinstance(e, dict) or not isinstance(e.get('name'), str) or not e['name'] or e['name'] in names:
            raise ValueError('elements require unique nonempty names')
        names.add(e['name'])
        if e.get('te_kind') not in ('sharp', 'blunt'):
            raise ValueError('each element requires te_kind sharp or blunt')
        p = np.asarray(e.get('points_m'), dtype=float)
        if p.ndim != 2 or p.shape[1] != 2 or len(p) < 4 or not np.isfinite(p).all():
            raise ValueError('points_m must be finite N x 2, N>=4')
        if not np.array_equal(p[0], p[-1]) or np.any(np.linalg.norm(np.diff(p, axis=0), axis=1) <= 1e-12):
            raise ValueError('contour must be explicitly closed without repeated adjacent points')
        cap_start = _cap(p, e.get('cap_start_index', len(p) - 2)) if e['te_kind'] == 'blunt' else None
        if e['te_kind'] == 'sharp' and e.get('cap_start_index') is not None:
            raise ValueError('sharp cusp has no finite cap_start_index')
        density = _density(p, e['te_kind'], cap_start, family, e['name'])
        if np.any(p[:, 0] <= -T.UP * T.CHORD) or np.any(p[:, 0] >= T.DOWN * T.CHORD) or np.any(p[:, 1] <= 0) or np.any(p[:, 1] >= T.TOP * T.CHORD):
            raise ValueError('contours must lie strictly above ground and inside T2-0 domain')
        x = _crossings(p, p)
        n = len(p) - 1
        ix = np.arange(n)
        x[ix, ix] = x[ix, (ix + 1) % n] = x[ix, (ix - 1) % n] = False
        area = abs(np.sum(p[:-1, 0] * p[1:, 1] - p[1:, 0] * p[:-1, 1])) / 2
        if x.any() or area <= 1e-12:
            raise ValueError('contour must be simple with nonzero enclosed area')
        for other in out:
            q = np.asarray(other['points_m'])
            if _crossings(p, q).any() or _inside(p[0], q) or _inside(q[0], p):
                raise ValueError('element contours overlap or touch')
        ile = int(np.argmin(p[:-1, 0]))
        last = cap_start if e['te_kind'] == 'blunt' else len(p) - 1
        if not 0 < ile < last:
            raise ValueError('contour starts at trailing edge and traverses both sides via leading edge')
        out.append({**({'source_element_metadata': e['source_element_metadata']} if 'source_element_metadata' in e else {}),
                    'name': e['name'], 'te_kind': e['te_kind'], 'points_m': p.tolist(),
                    'cap_start_index': cap_start, 'density': density,
                    'patch': 'airfoil' if i == 0 else f'airfoil_{i + 1}', 'leading_edge_index': ile})
    h = min(np.asarray(e['points_m'])[:, 1].min() for e in out)
    if 'ride_height_m' in spec and not math.isclose(float(spec['ride_height_m']), h, abs_tol=1e-9, rel_tol=0):
        raise ValueError('ride_height_m differs from geometry minimum')
    main_clearance = float(np.asarray(out[0]['points_m'])[:, 1].min())
    # TOPO-2D-00 Amendments 2 §5 / 3 §4: physical h is the scene's declared
    # main-element clearance, never the minimum over all elements or a constant.
    height = float(nominal) if source_metadata is not None else main_clearance
    height_datum = datum if source_metadata is not None else 'main-element minimum of exported current contour above ground'
    if 'height_m' in spec and not math.isclose(float(spec['height_m']), height, abs_tol=1e-9, rel_tol=0):
        raise ValueError('geometry height_m differs from main-element contour clearance')
    if expected_height_m is not None:
        if (isinstance(expected_height_m, bool) or not isinstance(expected_height_m, (int, float)) or
                not math.isfinite(expected_height_m) or expected_height_m <= 0):
            raise ValueError('declared expected_height_m must be positive finite metres')
        if not math.isclose(height, expected_height_m, abs_tol=1e-9, rel_tol=0):
            raise ValueError(f'geometry height {height:g} m differs from declared study height {expected_height_m:g} m')
    return {'config': spec['config'], 'main_chord_m': T.CHORD, 'ride_height_m': float(h),
            'height_m': height, 'physical_height_datum': height_datum,
            'expected_height_m': expected_height_m,
            'minimum_clearance_m': float(h), 'main_element_clearance_m': main_clearance,
            'nominal_ride_height_m': None if nominal is None else float(nominal), 'height_datum': datum, 'elements': out,
            'geometry_file': label, 'geometry_sha256': hashlib.sha256(raw).hexdigest(),
            **({'source_scene_metadata': source_metadata} if source_metadata is not None else {})}


def minimum_gap(geometry):
    polygons = [np.asarray(e['points_m']) for e in geometry['elements']]
    return min([geometry['ride_height_m']] + [_distance(a, b) for i, a in enumerate(polygons) for b in polygons[i + 1:]])


def boundary_layer_plan(geometries: dict, require_complete=True) -> dict:
    """Compute the study-wide stack ONCE, before rendering/generating cases.

    TOPO-2D-00 Amendment 1 §3: include all six thick/sharp geometries, even
    E3_sharp (a geometry member, not an extra production force run).
    """
    if not geometries or require_complete and set(geometries) != STUDY_CONFIGS:
        raise ValueError(f'boundary-layer plan requires all six configurations: {sorted(STUDY_CONFIGS)}')
    loaded = {c: load_geometry(p) for c, p in geometries.items()}
    if any(c != g['config'] for c, g in loaded.items()):
        raise ValueError('boundary-layer plan config/geometry mismatch')
    gaps = {c: minimum_gap(g) for c, g in loaded.items()}
    gap = min(gaps.values())
    families = {}
    for family in FAMILIES:
        mesh = T.MESHES[family]
        nspec, nlayer, bl = T.layers(mesh['ds'], mesh['y1'], mesh['g'], gap)
        # t20_case.layers caps EACH wall stack at 0.4*gap (lines 82–90).
        if not math.isfinite(gap) or bl > .4 * gap:
            raise ValueError(f'{family}: study minimum gap too small for unchanged T2-0 boundary layers')
        families[family] = {'mesh_spec': mesh, 'n_layers_spec': nspec, 'n_layers': nlayer, 'bl_thickness_m': bl}
    return {'schema': 'topo2d00-boundary-layers-v1',
            'scope': 'study' if set(loaded) == STUDY_CONFIGS else 'development',
            'geometry_sha256': {c: g['geometry_sha256'] for c, g in loaded.items()},
            'minimum_gap_by_config_m': gaps, 'minimum_gap_m': gap, 'families': families,
            'rule_source': 'TOPO-2D-00 Amendment 1 §3; scripts/t20_case.py:layers'}


def plan_sha256(plan):
    return hashlib.sha256(json.dumps(plan, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def boundary_layer_settings(plan, geometry, family):
    """Read the fixed plan; never re-clip the layer count to this case's gap."""
    if plan.get('schema') != 'topo2d00-boundary-layers-v1' or plan.get('geometry_sha256', {}).get(geometry['config']) != geometry['geometry_sha256']:
        raise ValueError('boundary-layer plan schema/geometry SHA mismatch')
    settings = plan.get('families', {}).get(family, {})
    mesh = T.MESHES[family]
    n = settings.get('n_layers')
    if settings.get('mesh_spec') != mesh or type(n) is not int or not 3 <= n <= settings.get('n_layers_spec', 0):
        raise ValueError('boundary-layer plan family/spec/layer count mismatch')
    thickness = mesh['y1'] * (mesh['g']**n - 1) / (mesh['g'] - 1)
    gap = plan.get('minimum_gap_m', 0)
    if (not math.isfinite(gap) or gap <= 0 or
            not math.isclose(settings.get('bl_thickness_m', 0), thickness, abs_tol=1e-12, rel_tol=0) or
            thickness > .4 * gap or minimum_gap(geometry) < gap - 1e-12):
        raise ValueError('boundary-layer plan gap/thickness mismatch')
    expected_spec, expected_n, _ = T.layers(mesh['ds'], mesh['y1'], mesh['g'], gap)
    if settings['n_layers_spec'] != expected_spec or n != expected_n:
        raise ValueError('boundary-layer plan layer count differs from unchanged T2-0 layers rule')
    return settings


def realisation_parameters(geometry, family, realisation):
    """Exact input perturbation, TOPO-2D-00 Amendment 3 §2; no body moves.

    Halton indexing is zero-based: point 0 is (0,0), point 1 is (1/2,1/3).
    Ground remains y=0; only its inlet/outlet endpoints follow the shifted box.
    """
    if family not in FAMILIES or type(realisation) is not int or not 0 <= realisation < 8:
        raise ValueError('realisation requires a known family and integer index in [0,7]')

    def radical_inverse(k, base):
        result, weight = 0., 1.
        while k:
            k, digit = divmod(k, base)
            weight /= base
            result += digit * weight
        return result

    point = [radical_inverse(realisation, base) for base in (2, 3)]
    dx, dy = (p * T.MESHES[family]['ds'] for p in point)
    features = {}
    for e in geometry['elements']:
        n = len(e['points_m']) - 1
        offset = realisation * (n // 8)
        features[e['name']] = {'vertex_count': n, 'vertex_start_offset': offset,
                               'trailing_edge_index': (-offset) % n,
                               'leading_edge_index': (e['leading_edge_index'] - offset) % n,
                               'cap_start_index': None if e['cap_start_index'] is None else (e['cap_start_index'] - offset) % n}
    return {'mechanism': 'topo2d00-indexed-mesh-input-v1', 'index': realisation,
            'determinism_scope': 'one mesh per fresh generator process; record same-index repeat for each gmsh/backend environment',
            'halton_point': point, 'halton_indexing': 'zero-based, point 0=(0,0)',
            'far_field_shift_m': {'x': dx, 'y': dy}, 'elements': features,
            'domain_bounds_m': {'inlet': -T.UP*T.CHORD + dx, 'outlet': T.DOWN*T.CHORD + dx,
                                'top': T.TOP*T.CHORD + dy, 'ground': 0.},
            'rule_source': 'TOPO-2D-00 Amendment 3 §2'}


def build_mesh(geometry: dict, family: str, out_msh: Path, verbose=False, boundary_layers=None, *, realisation=0) -> dict:
    """Assemble all holes in one 2D mesh, then extrude one cell using T2-0 helpers.

    Geometry is a validated load_geometry return value. Quality is recorded, never
    repaired by retrying until favorable quality appears. Each index fixes the
    ordering/box perturbation; it does not rely on gmsh run-to-run randomness.
    """
    if family not in FAMILIES:
        raise ValueError(f'family must be one of {FAMILIES}')
    import gmsh
    mesh = T.MESHES[family]
    polygons = [np.asarray(e['points_m']) for e in geometry['elements']]
    for e, q in zip(geometry['elements'], polygons):
        _density(q, e['te_kind'], e['cap_start_index'], family, e['name'])
    perturbation = realisation_parameters(geometry, family, realisation)
    polygons = [np.roll(q[:-1], -perturbation['elements'][e['name']]['vertex_start_offset'], axis=0)
                for e, q in zip(geometry['elements'], polygons)]
    polygons = [np.vstack((q, q[0])) for q in polygons]
    gap = minimum_gap(geometry)
    ds, y1, g = (mesh[k] for k in ('ds', 'y1', 'g'))
    if boundary_layers is None:
        raise ValueError('build_mesh requires a precomputed boundary-layer plan')
    fixed = boundary_layer_settings(boundary_layers, geometry, family)
    nspec, nlayer, bl = (fixed[k] for k in ('n_layers_spec', 'n_layers', 'bl_thickness_m'))
    out_msh = Path(out_msh)
    gmsh.initialize()
    try:
        gmsh.option.setNumber('General.Verbosity', 5 if verbose else 0)
        for key, value in {'General.NumThreads': 1, 'Mesh.MeshSizeFromPoints': 0, 'Mesh.MeshSizeFromCurvature': 0,
                           'Mesh.MeshSizeExtendFromBoundary': 0, 'Mesh.Algorithm': 6}.items():
            gmsh.option.setNumber(key, value)
        m, geo, f = gmsh.model, gmsh.model.geo, gmsh.model.mesh.field
        m.add('topo2d00')
        loops, body_curves, fans, wakes, wall_points = [], [], [], [], []
        xl, xr, top = (perturbation['domain_bounds_m'][key] for key in ('inlet', 'outlet', 'top'))
        for e, q in zip(geometry['elements'], polygons):
            pts = [geo.addPoint(float(x), float(y), 0) for x, y in q[:-1]]
            wall_points.extend(pts)
            # Each WP4 contour is a polygon; lines preserve the exact same body.
            curves = [geo.addLine(a, b) for a, b in zip(pts, pts[1:] + pts[:1])]
            te_index = perturbation['elements'][e['name']]['trailing_edge_index']
            if e['te_kind'] == 'sharp':
                fans.append(pts[te_index])
            body_curves.append(curves)
            loops.append(geo.addCurveLoop(curves))
            wakes.append(geo.addLine(pts[te_index], geo.addPoint(xr, float(q[te_index, 1]), 0)))
        d0 = min(ds, T.END_AR * y1)
        nend = math.ceil(math.log(ds / d0) / math.log(T.END_R)) + 1 if d0 < ds else 0
        end_width = d0 * (T.END_R ** nend - 1) / (T.END_R - 1) if nend else 0
        xs = [xl, xl + end_width, xr - end_width, xr] if nend else [xl, xr]
        bottom = [geo.addPoint(x, 0, 0) for x in xs]
        upper = [geo.addPoint(x, bl, 0) for x in xs]
        ground = [geo.addLine(a, b) for a, b in zip(bottom[:-1], bottom[1:])]
        gtop = [geo.addLine(a, b) for a, b in zip(upper[:-1], upper[1:])]
        vl, vr = geo.addLine(bottom[0], upper[0]), geo.addLine(bottom[-1], upper[-1])
        tl, tr = geo.addPoint(xl, top, 0), geo.addPoint(xr, top, 0)
        outlet, roof, inlet = geo.addLine(upper[-1], tr), geo.addLine(tr, tl), geo.addLine(tl, upper[0])
        block = geo.addPlaneSurface([geo.addCurveLoop(ground + [vr] + [-c for c in gtop[::-1]] + [-vl])])
        core = geo.addPlaneSurface([geo.addCurveLoop(gtop + [outlet, roof, inlet])] + loops)
        counts = [nend, round((xs[-2] - xs[1]) / ds), nend] if nend else [round((xr - xl) / ds)]
        for curves in (ground, gtop):
            for k, (cv, n) in enumerate(zip(curves, counts)):
                ratio = T.END_R if k == 0 else 1 / T.END_R
                geo.mesh.setTransfiniteCurve(cv, n + 1, 'Progression', ratio if nend and k != 1 else 1)
        for cv in (vl, vr):
            geo.mesh.setTransfiniteCurve(cv, nlayer + 1, 'Progression', g)
        geo.mesh.setTransfiniteSurface(block, 'Left', [bottom[0], bottom[-1], upper[-1], upper[0]])
        geo.mesh.setRecombine(2, block)
        extrusions = [geo.extrude([(2, surf)], 0, 0, T.Z, [1], [], True) for surf in (block, core)]
        geo.synchronize()
        wall_curves = [c for curves in body_curves for c in curves]
        layer = f.add('BoundaryLayer')
        f.setNumbers(layer, 'CurvesList', wall_curves)
        for key, value in {'Size': y1, 'Ratio': g, 'NbLayers': nlayer, 'Thickness': bl, 'Quads': 1}.items():
            f.setNumber(layer, key, value)
        if fans:
            f.setNumbers(layer, 'FanPointsList', fans)
            f.setNumbers(layer, 'FanPointsSizesList', [mesh['fan']] * len(fans))
        f.setAsBoundaryLayer(layer)

        def distance(curves, samples):
            tag = f.add('Distance')
            f.setNumbers(tag, 'CurvesList', curves)
            f.setNumber(tag, 'Sampling', samples)
            return tag

        def expression(value):
            tag = f.add('MathEval')
            f.setString(tag, 'F', value)
            return tag

        wall_distance = f.add('Distance')
        # T2-0 build_mesh samples 200 points per spline (line 187). With dense
        # supplied polylines use their exact vertices, no 3-per-segment drift.
        f.setNumbers(wall_distance, 'PointsList', wall_points)
        # Wake growth 0.2 and Sampling=100: t20_case.build_mesh line 187.
        fields = [expression(str(T.SIZE_FAR)), expression(f'{ds}+{T.GROW}*F{wall_distance}'),
                  expression(f'{ds}+0.2*F{distance(wakes, 100)}')]
        threshold = f.add('Threshold')
        for key, value in {'InField': distance(gtop, 3000), 'SizeMin': ds, 'SizeMax': T.SIZE_FAR,
                           'DistMin': .5 * bl, 'DistMax': .5 * bl + (T.SIZE_FAR - ds) / T.GROW}.items():
            f.setNumber(threshold, key, value)
        fields.append(threshold)
        for q, e in zip(polygons, geometry['elements']):
            ball = f.add('Ball')
            indices = perturbation['elements'][e['name']]
            le = q[indices['leading_edge_index']]
            # t20_case.build_mesh line 188: ball(LE, .012, ds/3); its helper
            # uses Thickness=2.5*radius=.03 (lines 175–180).
            for key, value in {'Radius': .012, 'Thickness': .03, 'VIn': ds / 3, 'VOut': T.SIZE_FAR,
                               'XCenter': le[0], 'YCenter': le[1]}.items():
                f.setNumber(ball, key, value)
            fields.append(ball)
            te = q[indices['trailing_edge_index']]
            for x, y in ([te] if e['te_kind'] == 'sharp' else [te, q[indices['cap_start_index']]]):
                ste = min(ds / 2, mesh['te'] * y1)
                fields.append(expression(f'{ste}+{T.TE_GROW}*Sqrt((x-({x:.12g}))^2+(y-({y:.12g}))^2)'))
        if nend:
            fields.extend(expression(f'{d0}+{T.TE_GROW}*Sqrt((x-({x}))^2+(y-({bl}))^2)') for x in (xl, xr))
        minimum = f.add('Min')
        f.setNumbers(minimum, 'FieldsList', fields)
        f.setAsBackgroundMesh(minimum)
        m.mesh.generate(2)
        lowest = min(polygons, key=lambda q: q[:, 1].min())
        ilow = int(np.argmin(lowest[:, 1]))
        stats = T._stats(m, [block, core], wall_curves, ground, ilow, geometry['ride_height_m'], lowest[ilow, 0])
        m.mesh.generate(3)
        lateral = {}
        for base, ext in zip((block, core), extrusions):
            curves = [cv for _, cv in m.getBoundary([(2, base)], combined=False, oriented=False)]
            for cv, (_, face) in zip(curves, ext[2:]):
                if cv not in [tag for _, tag in m.getBoundary([(2, face)], combined=False, oriented=False)]:
                    raise RuntimeError('lateral face/base curve mismatch')
                lateral[cv] = face
        groups = {'inlet': [lateral[inlet], lateral[vl]], 'outlet': [lateral[outlet], lateral[vr]],
                  'top': [lateral[roof]], 'ground': [lateral[c] for c in ground]}
        groups.update({e['patch']: [lateral[c] for c in curves] for e, curves in zip(geometry['elements'], body_curves)})
        groups.update(front=[block, core], back=[ext[0][1] for ext in extrusions])
        volumes = [ext[1][1] for ext in extrusions]
        T._write_msh(m, out_msh, groups, volumes)
        stats['cells_3d'] = int(sum(len(tags) for vol in volumes for tags in m.mesh.getElements(3, vol)[1]))
    finally:
        gmsh.finalize()
    stats.update(ride_height_m=geometry['ride_height_m'], x_lowest_m=float(lowest[ilow, 0]),
                 height_m=geometry['height_m'], mesh_realisation=perturbation,
                 minimum_gap_m=gap, n_layers_spec=nspec, n_layers=nlayer, bl_thickness_m=bl,
                 boundary_layer_plan_sha256=plan_sha256(boundary_layers),
                 boundary_layer_plan_scope=boundary_layers['scope'],
                 input_segment_spacing_m=[{'min': float(np.linalg.norm(np.diff(q, axis=0), axis=1).min()),
                                           'max': float(np.linalg.norm(np.diff(q, axis=0), axis=1).max())} for q in polygons],
                 element_count=len(polygons), fan_elements=[mesh['fan'] if e['te_kind'] == 'sharp' else 0 for e in geometry['elements']],
                 quality=T.mesh_quality(out_msh))
    return stats
