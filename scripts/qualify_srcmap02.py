#!/usr/bin/env python3
"""Solver-free SRCMAP-02 candidates; never used by production mapping."""
from __future__ import annotations
import argparse
import importlib.metadata
import json
from pathlib import Path
import time
import sys
sys.path[:0] = [str(Path(__file__).resolve().parent), str(Path(__file__).resolve().parents[1] / "src")]
import numpy as np
import trimesh
from diagnose_srcmap01 import (ROOT, OLD, E as SRCMAP01, sha, write_json,
    array_sha, strict, points_for, restore, load_inputs, inventory as old_inventory,
    mesh_inventory, SDFDesignState)
from cfd_sdf.design import volume_semantics as V
E = ROOT / 'docs/evidence/srcmap02_deterministic_signer_2026_10_13'
SEED = 20261013
ARRAY_KEYS = ('unsigned_float64', 'sign_int8', 'phi_float64', 'phi_float32')


def igl_module():
    import igl
    if importlib.metadata.version('libigl') != '2.6.3':
        raise ValueError('only frozen libigl==2.6.3 is eligible')
    return igl


def runtime_inventory():
    igl = igl_module()
    runtime = old_inventory()
    dist = importlib.metadata.distribution('libigl')
    artifacts = []
    for entry in dist.files or []:
        path = Path(dist.locate_file(entry))
        if path.is_file() and (path.suffix in ('.so', '.dylib') or path.name in ('RECORD', 'METADATA', 'WHEEL') or path == Path(igl.__file__)):
            artifacts.append({'path': str(path), 'sha256': sha(path)})
    runtime.update(diagnostic_source_path=str(Path(__file__).resolve()),
                   diagnostic_source_sha256=sha(__file__),
                   libigl={'version': importlib.metadata.version('libigl'),
                           'module_path': igl.__file__, 'artifacts': artifacts},
                   runner_source_sha256=sha(ROOT / 'scripts/run_srcmap02.py'),
                   srcmap01_helper_sha256=sha(ROOT / 'scripts/diagnose_srcmap01.py'))
    return runtime


def structural_runtime(runtime):
    return {k: v for k, v in runtime.items() if k not in
            ('numpy_legacy_random_state_sha256', 'trimesh_entropy_random_state')}


def loaded_mesh_record(mesh):
    record = mesh_inventory(mesh)
    # SRCMAP-01's generic Scene wording does not describe old trimesh versions.
    record.pop('force_mesh_semantics')
    return record


def permutation(n, order):
    if order == 'canonical': return np.arange(n)
    if order == 'reverse': return np.arange(n - 1, -1, -1)
    if order == 'permuted': return np.random.default_rng(SEED).permutation(n)
    raise ValueError(order)


def combine(unsigned, raw):
    """Frozen no-tolerance rule: exact distance zero always becomes positive zero."""
    unsigned, raw = np.asarray(unsigned, dtype='f8'), np.asarray(raw, dtype='f8')
    if unsigned.shape != raw.shape or not np.isfinite(unsigned).all() or not np.isfinite(raw).all():
        raise ValueError('nonfinite or shape-invalid distance/signer')
    if np.any(unsigned < 0) or np.any((unsigned == 0) & np.signbit(unsigned)):
        raise ValueError('unsigned query must be nonnegative, positive zero')
    if np.any((raw == 0) & (unsigned > 0)):
        raise ValueError('signer zero at strictly positive unsigned distance')
    signs = np.sign(raw).astype('i1')
    signs[unsigned == 0] = 0
    phi = signs.astype('f8') * unsigned
    phi[unsigned == 0] = 0.0
    return signs, phi


def query(mesh, points, candidate, chunk):
    """Unsigned proximity and libigl signing are separate calls and saved arrays."""
    if candidate not in ('A', 'B') or chunk <= 0:
        raise ValueError('invalid candidate/chunk')
    points = np.ascontiguousarray(points, dtype='f8')
    if points.ndim != 2 or points.shape[1] != 3 or not np.isfinite(points).all():
        raise ValueError('invalid query points')
    if not mesh.is_watertight or not mesh.is_winding_consistent:
        raise ValueError('candidate mesh must be closed and consistently wound')
    igl = igl_module()
    kind = igl.SIGNED_DISTANCE_TYPE_PSEUDONORMAL if candidate == 'A' else igl.SIGNED_DISTANCE_TYPE_WINDING_NUMBER
    n = len(points)
    arrays = {'unsigned_float64': np.empty(n, dtype='f8'),
              'raw_signer_float64': np.empty(n, dtype='f8'),
              'closest_face_int64': np.empty(n, dtype='i8'),
              'closest_point_float64': np.empty((n, 3), dtype='f8'),
              'unsigned_closest_face_int64': np.empty(n, dtype='i8'),
              'unsigned_closest_point_float64': np.empty((n, 3), dtype='f8')}
    if candidate == 'A': arrays['pseudonormal_float64'] = np.empty((n, 3), dtype='f8')
    vertices, faces = np.ascontiguousarray(mesh.vertices, dtype='f8'), np.ascontiguousarray(mesh.faces, dtype='i8')
    for start in range(0, n, chunk):
        q = points[start:start + chunk]
        closest, distance, face = trimesh.proximity.closest_point(mesh, q)
        result = igl.signed_distance(q, vertices, faces, kind)
        raw, triangle, location = result[:3]
        stop = start + len(q)
        arrays['unsigned_float64'][start:stop] = distance
        arrays['raw_signer_float64'][start:stop] = raw
        arrays['closest_face_int64'][start:stop] = triangle
        arrays['closest_point_float64'][start:stop] = location
        arrays['unsigned_closest_face_int64'][start:stop] = face
        arrays['unsigned_closest_point_float64'][start:stop] = closest
        if candidate == 'A': arrays['pseudonormal_float64'][start:stop] = result[3]
    if any(not np.isfinite(a).all() for a in arrays.values()):
        raise ValueError('nonfinite raw proximity output')
    arrays['sign_int8'], arrays['phi_float64'] = combine(arrays['unsigned_float64'], arrays['raw_signer_float64'])
    arrays['phi_float32'] = arrays['phi_float64'].astype('f4')
    arrays['phi_float32'][arrays['phi_float32'] == 0] = 0.0
    if not np.isfinite(arrays['phi_float32']).all(): raise ValueError('nonfinite Float32 field')
    return arrays


def candidate_state(reference, phi):
    return SDFDesignState.create(phi=phi, origin_m=reference.origin_m,
        spacing_m=reference.spacing_m, design_mask=reference.design_mask,
        fixed_solid_mask=reference.fixed_solid_mask, forbidden_mask=reference.forbidden_mask,
        root_mask=reference.root_mask, narrow_band_width_m=reference.narrow_band_width_m,
        generation=reference.generation, source_sha256=reference.source_sha256,
        topology_policy_id=reference.topology_policy_id,
        reinitialization_policy_id=reference.reinitialization_policy_id)


def volume_record(state):
    smooth = V.smoothed_volume_and_gradient(state)
    return {'hard_volume_m3': V.sharp_volume_m3(state),
            'solid_center_count': V.sampled_solid_centers_count(state),
            'exact_zero_centers_fluid': int(np.count_nonzero(V._corner_mean(state.phi) == 0)),
            'smooth_volume_m3': smooth.smoothed_volume_m3,
            'smooth_gV': smooth.constraint_residual,
            'smooth_volume_limit_m3': smooth.volume_limit_m3,
            'hard_authority': V.VOLUME_SEMANTICS_KIND,
            'smooth_authority': V.SMOOTHED_VOLUME_CONTRACT_ID,
            'smooth_role': 'descriptive only, never substitutes hard feasibility'}


def worker(output, grid, candidate, chunk, order):
    output = Path(output)
    if output.exists() or output.with_suffix('.npz').exists(): raise ValueError('refusing overwrite')
    state, mesh = load_inputs(grid)
    coordinates = points_for(state)
    indices = permutation(len(coordinates), order)
    before = runtime_inventory()
    started = time.time()
    arrays = query(mesh, coordinates[indices], candidate, chunk)
    arrays = {key: restore(value, indices) for key, value in arrays.items()}
    for key in ('unsigned_float64', 'raw_signer_float64', 'sign_int8', 'phi_float64', 'phi_float32'):
        arrays[key] = arrays[key].reshape(state.shape)
    combined_state = candidate_state(state, arrays['phi_float32'])
    output.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(output.with_suffix('.npz'), **arrays)
    write_json(output, {'grid': grid, 'candidate': candidate, 'chunk_size': chunk,
        'ordering': order, 'seed': SEED, 'runtime_before': before,
        'runtime_after': runtime_inventory(), 'mesh': loaded_mesh_record(mesh),
        'point_coordinates_c_little_sha256': array_sha(coordinates),
        'permutation_c_little_sha256': array_sha(indices.astype('i8')),
        'arrays': {key: {'sha256': array_sha(value), 'dtype': value.dtype.str,
                         'shape': list(value.shape)} for key, value in arrays.items()},
        'state_sha256': combined_state.state_sha256,
        'comparison_float32_registered': strict(arrays['phi_float32'], state.phi),
        'comparison_float64_registered_promoted': strict(arrays['phi_float64'], state.phi.astype('f8')),
        'volume': volume_record(combined_state), 'registered_volume': volume_record(state),
        'exact_zero_count': int(np.count_nonzero(arrays['unsigned_float64'] == 0)),
        'raw_signer_zero_count': int(np.count_nonzero(arrays['raw_signer_float64'] == 0)),
        'float32_cast_underflow_zero_count': int(np.count_nonzero((arrays['phi_float64'] != 0) & (arrays['phi_float32'] == 0))),
        'array_hash_semantics': 'complete explicit little-endian C-order bytes',
        'sign_mask_sha256': array_sha((arrays['phi_float64'] < 0).astype('u1')),
        'exact_zero_mask_sha256': array_sha((arrays['phi_float64'] == 0).astype('u1')),
        'zero_semantics_pass': True, 'elapsed_seconds': time.time() - started,
        'npz_sha256': sha(output.with_suffix('.npz'))})


def fixture_definitions():
    """Convex fixtures with analytic half-space labels; no target geometry access."""
    fixtures = []
    box = trimesh.creation.box(extents=(2., 2., 2.))
    q = np.array([[0,0,0], [2,0,0], [1-1e-6,0,0], [1+1e-6,0,0],
                  [1-1e-6,1-1e-6,0], [1+1e-6,1+1e-6,0],
                  [1-1e-6,1-1e-6,1-1e-6], [1+1e-6,1+1e-6,1+1e-6],
                  [1,0,0], [1,1,0], [1,1,1]], dtype='f8')
    labels = [-1,1,-1,1,-1,1,-1,1,0,0,0]
    names = ['inside','outside','face_near_in','face_near_out','edge_near_in','edge_near_out',
             'vertex_near_in','vertex_near_out','face_exact','edge_exact','vertex_exact']
    fixtures.append(('axis_aligned_box', box, q, labels, names,
                     'max(abs(x),abs(y),abs(z)) < 1; boundary exact'))
    rotation = np.array([[0.6,-0.8,0],[0.8,0.6,0],[0,0,1.]])
    translation = np.array([0.25,-0.5,0.75])
    rotated = trimesh.Trimesh(vertices=box.vertices @ rotation.T + translation, faces=box.faces, process=False)
    # Only vertex exact zero is retained: computed face projections need not be bit-zero after rotation.
    rq = q[:8] @ rotation.T + translation
    rq = np.vstack((rq, rotated.vertices[0]))
    fixtures.append(('rotated_box', rotated, rq, labels[:8]+[0], names[:8]+['vertex_exact'],
                     'inverse rigid transform reduces to analytic box; no approximate zero tie'))
    vertices = np.array([[0.,0,0],[1,0,0],[0,1,0],[0,0,1]])
    tetra = trimesh.Trimesh(vertices=vertices, faces=[[0,2,1],[0,1,3],[0,3,2],[1,2,3]], process=False)
    tq = np.array([[.125,.125,.125],[-1,0,0],[.25,.25,1e-6],[.25,.25,-1e-6],
                   [1e-6,1e-6,.25],[-1e-6,-1e-6,.25],[1e-6,1e-6,1e-6],
                   [-1e-6,-1e-6,-1e-6],[.25,.25,0],[0,0,.25],[0,0,0]])
    fixtures.append(('tetrahedron',tetra,tq,labels,names,
                     'x>0,y>0,z>0,x+y+z<1; boundary exact'))
    sphere = trimesh.creation.icosphere(subdivisions=1, radius=1.)
    # A triangulated sphere is the convex polyhedron, not the smooth unit sphere.
    # Radial inward points are inside all face half-spaces. Outward feature points
    # are beyond a supporting face/edge/vertex; these labels are analytic for this mesh.
    tri = sphere.triangles[0]
    feature_points = [tri.mean(axis=0), (tri[0]+tri[1])/2, tri[0]]
    sq = [[0,0,0],[2,0,0],[.9,0,0],[1.1,0,0]]
    sn = ['inside','outside','sphere_safe_near_inside','sphere_safe_near_outside']
    sl = [-1,1,-1,1]
    for name, p in zip(('face','edge','vertex'), feature_points):
        sq.extend((p*(1-1e-6),p*(1+1e-6)))
        sn.extend((name+'_near_in',name+'_near_out')); sl.extend((-1,1))
    sq.append(sphere.vertices[0]); sn.append('vertex_exact'); sl.append(0)
    fixtures.append(('triangulated_sphere',sphere,np.asarray(sq),sl,sn,
        'convex inscribed polyhedron: radial contraction inside; radial expansion at boundary feature outside; smooth sphere boundary not used'))
    return fixtures


def analytic_fixtures():
    records = []
    for name, mesh, points, expected, names, explanation in fixture_definitions():
        rows = {}
        face_points = mesh.triangles[:,0]
        halfspaces = points[:,None,:] - face_points[None,:,:]
        plane_values = np.einsum('qfi,fi->qf', halfspaces, mesh.face_normals)
        for i, expected_sign in enumerate(expected):
            if expected_sign < 0 and not np.all(plane_values[i] < 0):
                raise ValueError('fixture interior label fails independent convex half-space check')
            if expected_sign > 0 and not np.any(plane_values[i] > 0):
                raise ValueError('fixture exterior label fails independent convex half-space check')
        for candidate in ('A','B'):
            arrays = query(mesh, points, candidate, 3)
            signs = arrays['sign_int8']
            passed = np.array_equal(signs, np.asarray(expected,dtype='i1'))
            rows[candidate] = {'pass': bool(passed), 'signs': signs.tolist(),
                'raw_signer': arrays['raw_signer_float64'].tolist(),
                'unsigned': arrays['unsigned_float64'].tolist(),
                'combined': arrays['phi_float64'].tolist(),
                'positive_zero_pass': bool(not np.signbit(arrays['phi_float64'][signs == 0]).any()),
                'hashes': {k: array_sha(v) for k,v in arrays.items()}}
        records.append({'fixture':name,'explanation':explanation,'queries':points.tolist(),
                        'query_names':names,'expected_signs':expected,
                        'vertices':mesh.vertices.tolist(),'faces':mesh.faces.tolist(),
                        'analytic_nonzero_halfspace_check':True,'watertight':bool(mesh.is_watertight),'winding_consistent':bool(mesh.is_winding_consistent),
                        'candidates':rows})
    return {'pass':all(r['candidates'][c]['pass'] and r['candidates'][c]['positive_zero_pass']
                       for r in records for c in ('A','B')),
            'runtime':runtime_inventory(),'fixtures':records,
            'zero_rule':'unsigned bitwise +0 gives phi +0; signer zero with unsigned>0 fails; Float32 cast zeros normalized +0; no tolerance'}


def classify(*, integrity, analytic, zero_semantics, a_stable, b_stable,
             nonzero_disagreements, cross_environment_exact):
    if not integrity or not analytic or not zero_semantics: return 'SRCMAP02_INCONCLUSIVE'
    if not a_stable: return 'PSEUDONORMAL_NOT_DETERMINISTIC'
    if not b_stable: return 'WINDING_CONTROL_NOT_STABLE'
    if nonzero_disagreements: return 'DETERMINISTIC_SIGNER_DISAGREEMENT'
    if not cross_environment_exact: return 'SRCMAP02_INCONCLUSIVE'
    return 'DETERMINISTIC_SIGNER_QUALIFIED'


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest='command',required=True)
    for command in ('inventory','fixtures','worker'):
        p = sub.add_parser(command); p.add_argument('--output',required=True)
        if command == 'worker':
            p.add_argument('--grid', choices=('v16','v17'), required=True)
            p.add_argument('--candidate', choices=('A','B'),required=True)
            p.add_argument('--chunk',type=int,required=True)
            p.add_argument('--order',choices=('canonical','reverse','permuted'),required=True)
    args = parser.parse_args()
    if args.command == 'inventory':
        _, mesh = load_inputs('v17')
        write_json(args.output, {'runtime':runtime_inventory(),'mesh':loaded_mesh_record(mesh),'no_distance_queries':True})
    elif args.command == 'fixtures': write_json(args.output,analytic_fixtures())
    else: worker(args.output,args.grid,args.candidate,args.chunk,args.order)
