#!/usr/bin/env python3
"""Multi-body gmsh assembly using the immutable T2-0 mesh/statistics helpers.

Inputs are metre-valued closed contours; no published geometry is reconstructed.
The mesh SHA identifies each realisation: gmsh is not run-to-run reproducible.
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
        expected = np.vstack((lower[::-1], upper[1:], lower[-1:]))
        if not np.array_equal(polygon, expected):
            raise ValueError('WP4 polygon/surface identity mismatch')
        if np.linalg.norm(lower[-1] - upper[-1]) <= 1e-9:
            raise ValueError('WP4 finite trailing-edge cap is missing')
        converted.append({'name': element['name'], 'points_m': (polygon * .001).tolist(), 'te_kind': 'blunt',
                          'source_element_metadata': {k: v for k, v in element.items() if k not in ('polygon_mm', 'suction_mm', 'pressure_mm')}})
    nominal = float(scene['height_mm']) * .001
    main_clearance = float(np.asarray(converted[0]['points_m'])[:, 1].min())
    if not math.isfinite(nominal) or nominal <= 0 or not math.isclose(nominal, main_clearance, rel_tol=0, abs_tol=1e-9):
        raise ValueError('WP4 height_mm differs from main-element contour clearance')
    metadata = {key: value for key, value in scene.items() if key != 'elements'}
    return {'config': scene['configuration'], 'elements': converted, 'main_chord_m': T.CHORD,
            'nominal_ride_height_m': nominal,
            'height_datum': 'WP4 height_mm: main-element minimum of exported current contour above ground'}, metadata


def load_geometry(source: Path | str | dict) -> dict:
    """Read strict JSON or NPZ(metadata_json + points_key arrays), validate, hash.

    JSON keys: config, elements[{name, points_m, te_kind:sharp|blunt}].
    First point is the TE; for blunt bodies the closing edge is the finite cap.
    All forces use the common T2-0 main chord, never each body's own chord.
    """
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
        last = len(p) - 2 if e['te_kind'] == 'blunt' else len(p) - 1
        if not 0 < ile < last:
            raise ValueError('contour starts at trailing edge and traverses both sides via leading edge')
        out.append({**({'source_element_metadata': e['source_element_metadata']} if 'source_element_metadata' in e else {}),
                    'name': e['name'], 'te_kind': e['te_kind'], 'points_m': p.tolist(),
                    'patch': 'airfoil' if i == 0 else f'airfoil_{i + 1}', 'leading_edge_index': ile})
    h = min(np.asarray(e['points_m'])[:, 1].min() for e in out)
    if 'ride_height_m' in spec and not math.isclose(float(spec['ride_height_m']), h, abs_tol=1e-9, rel_tol=0):
        raise ValueError('ride_height_m differs from geometry minimum')
    return {'config': spec['config'], 'main_chord_m': T.CHORD, 'ride_height_m': float(h),
            'minimum_clearance_m': float(h), 'main_element_clearance_m': float(np.asarray(out[0]['points_m'])[:, 1].min()),
            'nominal_ride_height_m': None if nominal is None else float(nominal), 'height_datum': datum, 'elements': out,
            'geometry_file': label, 'geometry_sha256': hashlib.sha256(raw).hexdigest(),
            **({'source_scene_metadata': source_metadata} if source_metadata is not None else {})}


def build_mesh(geometry: dict, family: str, out_msh: Path, verbose=False) -> dict:
    """Assemble all holes in one 2D mesh, then extrude one cell using T2-0 helpers.

    Geometry is a validated load_geometry return value. Quality is recorded, never
    repaired by retrying until a favorable gmsh draw appears.
    """
    if family not in FAMILIES:
        raise ValueError(f'family must be one of {FAMILIES}')
    import gmsh
    mesh = T.MESHES[family]
    polygons = [np.asarray(e['points_m']) for e in geometry['elements']]
    gap = min([geometry['ride_height_m']] + [_distance(a, b) for i, a in enumerate(polygons) for b in polygons[i + 1:]])
    ds, y1, g = (mesh[k] for k in ('ds', 'y1', 'g'))
    nspec, nlayer, bl = T.layers(ds, y1, g, gap)
    if not math.isfinite(gap) or bl > 0.4 * gap:
        raise ValueError('gap too small for unchanged T2-0 boundary layers')
    out_msh = Path(out_msh)
    gmsh.initialize()
    try:
        gmsh.option.setNumber('General.Verbosity', 5 if verbose else 0)
        for key, value in {'General.NumThreads': 1, 'Mesh.MeshSizeFromPoints': 0, 'Mesh.MeshSizeFromCurvature': 0,
                           'Mesh.MeshSizeExtendFromBoundary': 0, 'Mesh.Algorithm': 6}.items():
            gmsh.option.setNumber(key, value)
        m, geo, f = gmsh.model, gmsh.model.geo, gmsh.model.mesh.field
        m.add('topo2d00')
        loops, body_curves, fans, wakes = [], [], [], []
        for e, q in zip(geometry['elements'], polygons):
            pts = [geo.addPoint(float(x), float(y), 0) for x, y in q[:-1]]
            # Each WP4 contour is a polygon; lines preserve the exact same body.
            curves = [geo.addLine(a, b) for a, b in zip(pts, pts[1:] + pts[:1])]
            if e['te_kind'] == 'sharp':
                fans.append(pts[0])
            body_curves.append(curves)
            loops.append(geo.addCurveLoop(curves))
            wakes.append(geo.addLine(pts[0], geo.addPoint(T.DOWN * T.CHORD, float(q[0, 1]), 0)))
        xl, xr, top = -T.UP * T.CHORD, T.DOWN * T.CHORD, T.TOP * T.CHORD
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

        fields = [expression(str(T.SIZE_FAR)), expression(f'{ds}+{T.GROW}*F{distance(wall_curves, 3)}'),
                  expression(f'{ds}+0.2*F{distance(wakes, 100)}')]
        threshold = f.add('Threshold')
        for key, value in {'InField': distance(gtop, 3000), 'SizeMin': ds, 'SizeMax': T.SIZE_FAR,
                           'DistMin': .5 * bl, 'DistMax': .5 * bl + (T.SIZE_FAR - ds) / T.GROW}.items():
            f.setNumber(threshold, key, value)
        fields.append(threshold)
        for q, e in zip(polygons, geometry['elements']):
            ball = f.add('Ball')
            le = q[e['leading_edge_index']]
            for key, value in {'Radius': .012, 'Thickness': .03, 'VIn': ds / 3, 'VOut': T.SIZE_FAR,
                               'XCenter': le[0], 'YCenter': le[1]}.items():
                f.setNumber(ball, key, value)
            fields.append(ball)
            for x, y in ([q[0]] if e['te_kind'] == 'sharp' else [q[0], q[-2]]):
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
                 minimum_gap_m=gap, n_layers_spec=nspec, n_layers=nlayer, bl_thickness_m=bl,
                 input_segment_spacing_m=[{'min': float(np.linalg.norm(np.diff(q, axis=0), axis=1).min()),
                                           'max': float(np.linalg.norm(np.diff(q, axis=0), axis=1).max())} for q in polygons],
                 element_count=len(polygons), fan_elements=[mesh['fan'] if e['te_kind'] == 'sharp' else 0 for e in geometry['elements']],
                 quality=T.mesh_quality(out_msh))
    return stats
