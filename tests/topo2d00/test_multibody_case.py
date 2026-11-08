"""Development contracts; synthetic second body is not the published E2 geometry."""
from __future__ import annotations

import gzip
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
from topo2d00 import t2d_multibody_case as M
from topo2d00 import t2d_foam_case as F
import t20_case as T

_NO_GMSH = importlib.util.find_spec('gmsh') is None


def geometry(kind='sharp'):
    # Analytic synthetic teardrop, with ~0.5 mm arc spacing supplied HERE.
    # Its broad nose stays >=0.1 mm and <=5 degrees even at the test's .3 scale.
    # No source coordinates, production resampling or physical E2 claim.
    theta = np.linspace(0, np.pi, 50001)
    side = np.c_[.5*T.CHORD*(1 + np.cos(theta)), -.04*np.sin(theta)*np.sin(theta/2)]
    arc = np.r_[0, np.cumsum(np.linalg.norm(np.diff(side, axis=0), axis=1))]
    s = np.linspace(0, arc[-1], int(np.ceil(arc[-1]/.0005)) + 1)
    lower = np.c_[np.interp(s, arc, side[:, 0]), np.interp(s, arc, side[:, 1])]
    upper = lower[::-1] * [1, -1]
    cap_start = None
    if kind == 'blunt':
        lower, upper = (p[p[:, 0] <= .97*T.CHORD] for p in (lower, upper))
    q = np.vstack((lower, upper[1:]))
    if kind == 'blunt':
        cap_start = len(q) - 1
        cap = np.linspace(q[-1], q[0], int(np.ceil(np.linalg.norm(q[-1] - q[0])/.0005)) + 1)
        q = np.vstack((q, cap[1:]))
    else:
        q[-1] = q[0]
    q[:, 1] += .1 - q[:, 1].min()
    flap = q.copy() * 0.55 + [0.23, 0.08]
    return {'config': 'synthetic_two_body', 'main_chord_m': T.CHORD,
            'elements': [{'name': name, 'te_kind': kind, 'points_m': p.tolist(), 'cap_start_index': cap_start}
                         for name, p in [('main', q), ('synthetic_flap', flap)]]}


def test_geometry_json_npz_contract(tmp_path):
    spec = geometry()
    src = tmp_path / 'geometry.json'
    src.write_text(json.dumps(spec))
    got = M.load_geometry(src)
    assert got['config'] == spec['config']
    assert got['geometry_sha256'] == hashlib.sha256(src.read_bytes()).hexdigest()
    metadata = {**spec, 'elements': [{k: v for k, v in e.items() if k != 'points_m'} | {'points_key': f'element_{i + 1}'}
                                   for i, e in enumerate(spec['elements'])]}
    npz = tmp_path / 'geometry.npz'
    np.savez(npz, metadata_json=json.dumps(metadata),
             **{f'element_{i + 1}': np.array(e['points_m']) for i, e in enumerate(spec['elements'])})
    other = M.load_geometry(npz)
    for a, b in zip(got['elements'], other['elements']):
        np.testing.assert_array_equal(a['points_m'], b['points_m'])
    assert other['geometry_sha256'] == hashlib.sha256(npz.read_bytes()).hexdigest()


@pytest.mark.parametrize('change', ['open', 'overlap', 'unknown_te', 'nonfinite', 'self_intersection', 'wrong_chord', 'wrong_reference_chord', 'wrong_units'])
def test_geometry_fails_closed(change):
    spec = geometry()
    if change == 'open':
        spec['elements'][0]['points_m'][-1][0] += 0.001
    elif change == 'overlap':
        spec['elements'][1]['points_m'] = spec['elements'][0]['points_m']
    elif change == 'unknown_te':
        spec['elements'][0]['te_kind'] = 'rounded-ish'
    elif change == 'nonfinite':
        spec['elements'][0]['points_m'][5][0] = float('nan')
    elif change == 'wrong_chord':
        spec['main_chord_m'] = 0.380
    elif change == 'wrong_reference_chord':
        spec['reference_chord_m'] = 0.380
    elif change == 'wrong_units':
        spec['units'] = 'mm'
    else:
        spec['elements'][0]['points_m'] = [[0, .1], [.1, .2], [0, .2], [.1, .1], [0, .1]]
    with pytest.raises(ValueError):
        M.load_geometry(spec)


@pytest.mark.parametrize('kind', ['sharp', 'blunt'])
def test_density_guard_preserves_dense_vertices(kind):
    spec = geometry(kind)
    got = M.load_geometry(spec, family='fine30')
    np.testing.assert_array_equal(got['elements'][0]['points_m'], spec['elements'][0]['points_m'])
    assert got['elements'][0]['density']['max_noncap_turn_deg'] <= 5
    assert got['elements'][0]['density']['max_segment_m'] <= T.MESHES['fine30']['ds']


@pytest.mark.parametrize('family', M.FAMILIES)
@pytest.mark.parametrize('where', ['body', 'cap'])
def test_density_rejects_5_6_micrometre_sliver(family, where):
    # Round-2 WP4's 5.6 micrometre sliver, without using another worktree's code.
    spec = geometry('blunt')
    e = spec['elements'][0]
    q = np.asarray(e['points_m'])
    j = 50 if where == 'body' else e['cap_start_index']
    v = q[j + 1] - q[j]
    sliver = q[j] + v * (5.6e-6 / np.linalg.norm(v))
    e['points_m'] = np.insert(q, j + 1, sliver, axis=0).tolist()
    if where == 'body':
        e['cap_start_index'] += 1
    with pytest.raises(ValueError, match=r'main.*segment.*0\.0001'):
        M.load_geometry(spec, family)


@pytest.mark.parametrize('family', M.FAMILIES)
def test_density_rejects_exact_wp4_attempt2_polygon_snapshot(family):
    # Data-only immutable snapshot from WP4 ba3164c7; never import its code.
    snapshot = Path(__file__).with_name('fixtures')/'wp4_attempt2_E2_sharp.json.gz'
    raw = gzip.decompress(snapshot.read_bytes())
    assert hashlib.sha256(raw).hexdigest() == 'b89e77a44cca8a9f5434d390dd9422c01c49be33f4445f242d07e0917a863341'
    scene = json.loads(raw)
    main = np.asarray(scene['elements'][0]['polygon_mm']) * .001
    assert np.linalg.norm(np.diff(main, axis=0), axis=1).min() < M.MIN_SEGMENT_M
    with pytest.raises(ValueError, match=r'main.*segment.*below minimum.*0\.0001'):
        M.load_geometry(scene, family)


@pytest.mark.parametrize('where', ['body', 'cap'])
def test_density_rejects_adjacent_ratio_above_three(where):
    spec = geometry('blunt')
    e = spec['elements'][0]
    q = np.asarray(e['points_m'])
    j = 50 if where == 'body' else e['cap_start_index']
    v = q[j + 1] - q[j]
    e['points_m'] = np.insert(q, j + 1, q[j] + v*(.00011/np.linalg.norm(v)), axis=0).tolist()
    if where == 'body':
        e['cap_start_index'] += 1
    with pytest.raises(ValueError, match=r'main.*adjacent.*ratio.*3'):
        M.load_geometry(spec)


def test_density_rejects_long_segment_and_reports_family():
    spec = geometry()
    q = np.asarray(spec['elements'][0]['points_m'])[::3].copy()
    if not np.array_equal(q[-1], q[0]):
        q = np.vstack((q, q[0]))
    spec['elements'] = [{**spec['elements'][0], 'points_m': q.tolist()}]
    with pytest.raises(ValueError, match=r'main.*segment.*fine30.*ds'):
        M.load_geometry(spec, family='fine30')


def test_density_rejects_kink_even_with_short_edges():
    spec = geometry()
    spec['elements'][0]['points_m'][100][1] += .0004
    with pytest.raises(ValueError, match=r'main.*turn.*5'):
        M.load_geometry(spec)


def test_blunt_cap_spacing_and_endpoint_exemption():
    spec = geometry('blunt')
    # Cap corners exceed 5 degrees but are the only exempt vertices.
    got = M.load_geometry(spec)
    assert got['elements'][0]['cap_start_index'] == spec['elements'][0]['cap_start_index']
    e = spec['elements'][0]
    # Supply a still-straight single cap exceeding ds; do not corrupt its line.
    e['points_m'] = e['points_m'][:e['cap_start_index'] + 1] + [e['points_m'][0].copy()]
    e['points_m'][0][1] -= .004
    e['points_m'][-1] = e['points_m'][0].copy()
    assert np.linalg.norm(np.array(e['points_m'][-2]) - e['points_m'][0]) > T.MESHES['fine30']['ds']
    with pytest.raises(ValueError, match='segment'):
        M.load_geometry(spec)


def test_study_boundary_layers_are_fixed_across_configurations():
    specs = {}
    for n in (1, 2, 3):
        for suffix in ('', '_sharp'):
            spec = geometry('sharp' if suffix else 'blunt')
            spec['config'] = f'E{n}{suffix}'
            if n == 1:
                spec['elements'] = spec['elements'][:1]
            elif n == 3:
                q = np.asarray(spec['elements'][0]['points_m']) * .3 + [.4, .15]
                spec['elements'].append({'name': 'flap2', 'te_kind': 'sharp' if suffix else 'blunt', 'points_m': q.tolist(),
                                         'cap_start_index': spec['elements'][0]['cap_start_index']})
            specs[spec['config']] = spec
    plan = M.boundary_layer_plan(specs)
    assert set(plan['geometry_sha256']) == M.STUDY_CONFIGS
    for family in M.FAMILIES:
        counts = {M.boundary_layer_settings(plan, M.load_geometry(s), family)['n_layers'] for s in specs.values()}
        assert counts == {plan['families'][family]['n_layers']}
        assert plan['families'][family]['bl_thickness_m'] <= .4 * plan['minimum_gap_m']
    with pytest.raises(ValueError, match='six|E3_sharp'):
        M.boundary_layer_plan({k: v for k, v in specs.items() if k != 'E3_sharp'})
    changed = M.load_geometry(specs['E1'])
    changed['geometry_sha256'] = 'f' * 64
    with pytest.raises(ValueError, match='SHA'):
        M.boundary_layer_settings(plan, changed, 'fine30')


def test_production_requires_study_boundary_layers_before_writing(tmp_path):
    with pytest.raises(ValueError, match='boundary.layer plan'):
        F.write_case(tmp_path / 'case', geometry(), iters=5000)
    assert not (tmp_path / 'case').exists()


@pytest.mark.parametrize('metadata', [np.array(b'{}'), np.array('{}', dtype=object), np.array(['{}'])])
def test_npz_metadata_requires_unicode_scalar(tmp_path, metadata):
    path = tmp_path / 'malformed.npz'
    np.savez(path, metadata_json=metadata)
    with pytest.raises(ValueError):
        M.load_geometry(path)


def test_foam_dictionary_contract():
    files = F.case_files('sst-wf', 'fine30', ['airfoil', 'airfoil_2'], 5000)
    cd = files['system/controlDict']
    assert 'endTime 5000;' in cd
    assert 'forceCoeffs_airfoil_2' in cd
    assert '    forces_airfoil\n' in cd and '    forces_airfoil_2\n' in cd
    assert 'patches (airfoil airfoil_2);' in cd
    assert cd.count('Aref 0.0004468;') == 3
    assert cd.count('liftDir (0 -1 0);') == 3
    for field in ('U', 'p', 'k', 'omega', 'nut'):
        assert '    airfoil_2\n' in files['0/' + field]
    assert '0/gammaInt' not in files
    cont = files['continuation/system/controlDict']
    assert 'endTime 15000;' in cont and 'startFrom latestTime;' in cont
    assert 'consistent yes;' in files['system/fvSolution']
    assert '0.9;' in files['system/fvSolution']
    with pytest.raises(ValueError):
        F.case_files('sst-lm', 'fine30', ['airfoil'], 5000)
    with pytest.raises(ValueError):
        F.case_files('sa-wf', 'fine30', ['airfoil'], 201)


@pytest.mark.skipif(_NO_GMSH, reason='gmsh not installed')
@pytest.mark.parametrize('kind', ['sharp', 'blunt'])
def test_multibody_mesh_manifest(tmp_path, kind):
    src = tmp_path / 'geometry.json'
    src.write_text(json.dumps(geometry(kind)))
    out = tmp_path / 'case'
    man = F.write_case(out, src, family='fine30', iters=1)
    assert len(man['elements']) == man['element_count'] == 2
    assert [e['patch'] for e in man['elements']] == ['airfoil', 'airfoil_2']
    assert man['geometry_sha256'] == T.sha256(src)
    assert man['mesh_msh_sha256'] == T.sha256(out / 'mesh.msh')
    assert man['mesh_spec'] == T.MESHES['fine30']
    assert man['chord_m'] == T.CHORD and man['Aref_m2'] == T.CHORD * T.Z
    assert man['realisation'] == 0
    assert man['mesh_stats']['quality']['unused_nodes'] == 0
    assert man['mesh_stats']['cells_3d'] > 0
    assert man['mesh_stats']['fan_elements'] == ([4, 4] if kind == 'sharp' else [0, 0])
    assert man['mesh_stats']['first_cell_airfoil_m']['median'] == pytest.approx(0.0006, rel=0.1)
    for name in ('inlet', 'outlet', 'top', 'ground', 'airfoil', 'airfoil_2', 'front', 'back'):
        assert f'"{name}"' in (out / 'mesh.msh').read_text()
    # The local proxy remains informational (Amendment 1 §8). The broader
    # synthetic finite cap can trigger its stricter weight_min limit; checkMesh
    # acceptance of a future physical E2 is a separate, deferred measurement.
    quality = man['mesh_stats']['quality']
    assert all(np.isfinite(quality[k]) for k in ('nonorth_max', 'skew_max', 'weight_min', 'vol_ratio_min', 'det_min'))
    assert man['mesh_quality_failures'] == T.quality_failures(quality, man['mesh_stats']['gmsh_min_sicn_tri'])
    assert json.loads((out / 'case_manifest.json').read_text()) == man


def test_fix_boundary_additional_walls():
    b = '\n'.join(name + '\n{\n type patch;\n nFaces 1;\n startFace 0;\n}'
                  for name in ('front', 'back', 'airfoil', 'airfoil_2', 'ground'))
    fixed = F.fix_boundary(b, ['airfoil', 'airfoil_2'])
    assert fixed.count('type wall;') == 3
    assert fixed.count('type empty;') == 2


@pytest.mark.skipif(_NO_GMSH, reason='gmsh not installed')
def test_threebody_med30(tmp_path):
    spec = geometry()
    q = np.asarray(spec['elements'][0]['points_m']) * .3 + [.4, .15]
    spec['elements'].append({'name': 'synthetic_flap_2', 'points_m': q.tolist(), 'te_kind': 'sharp'})
    man = F.write_case(tmp_path / 'case', spec, family='med30', iters=1)
    mesh = (tmp_path / 'case/mesh.msh').read_text()
    assert man['element_count'] == 3 and '"airfoil_3"' in mesh
    assert '3 10 "fluid"' in mesh
    assert man['mesh_stats']['fan_elements'] == [4, 4, 4]
    # This synthetic tiny third nose exercises topology, not mesh qualification.
    # Amendment 1 §8: proxy failures remain informative, never a solver gate.
    quality = man['mesh_stats']['quality']
    assert quality['unused_nodes'] == 0
    assert all(np.isfinite(quality[k]) for k in ('nonorth_max', 'skew_max', 'weight_min', 'vol_ratio_min', 'det_min'))
    assert isinstance(man['mesh_quality_failures'], list)


@pytest.mark.parametrize('config', ['E1', 'E1_sharp', 'E2', 'E2_sharp', 'E3', 'E3_sharp'])
def test_known_config_rejects_wrong_element_count(config):
    spec = geometry()
    spec['config'] = config
    if config.startswith('E2'):
        spec['elements'] = spec['elements'][:1]
    with pytest.raises(ValueError, match='element count'):
        M.load_geometry(spec)


def test_nominal_height_separate_from_measured_clearance():
    spec = geometry()
    spec['nominal_ride_height_m'] = .11
    spec['height_datum'] = 'published_zero_incidence_ground_distance'
    result = M.load_geometry(spec)
    assert result['nominal_ride_height_m'] == .11
    assert result['height_datum'] == spec['height_datum']
    assert result['minimum_clearance_m'] != result['nominal_ride_height_m']
    assert result['main_element_clearance_m'] == result['minimum_clearance_m']


def wp4_scene():
    """Source-compatible WP4 export; synthetic values, not the paper's E2."""
    elements = []
    for e in geometry('blunt')['elements']:
        polygon = np.asarray(e['points_m']) * 1000
        polygon[:, 1] -= 10
        le = int(np.argmin(polygon[:, 0]))
        lower, upper = polygon[:le + 1][::-1], polygon[le:e['cap_start_index'] + 1]
        assert lower.shape == upper.shape
        name = 'main' if not elements else 'flap1'
        elements.append({'name': name, 'suction_mm': lower.tolist(), 'pressure_mm': upper.tolist(),
                         'polygon_mm': polygon.tolist(),
                         'thickening': {'method': 'unthickened-source'}})
    return {'schema': 'topo2d-scene-v1', 'configuration': 'E2_sharp', 'elements': elements,
            'height_mm': 90., 'dx_mm': 1.86, 'ground_z_mm': 0.,
            'normalizations': {'c1_mm': 223.4, 'c_mm': 380.},
            'sharp_variant': {'enabled': True, 'mathematically_sharp': False},
            'gates': {'accepted': True, 'overlap': False, 'self_intersections': False},
            'sources': [{'path': '<synthetic fixture>', 'verification': 'DEVELOPMENT_SYNTHETIC'}],
            'placement': {'gap_reference': 'upstream trailing-edge midpoint'}}


def test_wp4_scene_json_adapter_preserves_identity(tmp_path):
    scene = wp4_scene()
    path = tmp_path / 'scene.json'
    path.write_text(json.dumps(scene))
    result = M.load_geometry(path)
    assert result['config'] == 'E2_sharp'
    assert [e['te_kind'] for e in result['elements']] == ['blunt', 'blunt']
    np.testing.assert_array_equal(result['elements'][0]['points_m'], np.asarray(scene['elements'][0]['polygon_mm']) * .001)
    assert result['nominal_ride_height_m'] == .09
    assert 'main-element' in result['height_datum']
    assert result['source_scene_metadata']['sources'] == scene['sources']
    assert result['source_scene_metadata']['gates'] == scene['gates']
    assert result['source_scene_metadata']['placement'] == scene['placement']
    assert result['geometry_sha256'] == T.sha256(path)


def test_wp4_scene_npz_adapter_checks_duplicate_arrays(tmp_path):
    scene = wp4_scene()
    arrays = {f'polygon_{i}_mm': np.asarray(e['polygon_mm']) for i, e in enumerate(scene['elements'])}
    path = tmp_path / 'scene.npz'
    np.savez(path, scene_json=json.dumps(scene), **arrays)
    result = M.load_geometry(path)
    assert result['geometry_sha256'] == T.sha256(path)
    assert result['config'] == 'E2_sharp'
    arrays['polygon_1_mm'] = arrays['polygon_1_mm'].copy()
    arrays['polygon_1_mm'][1, 0] += .001
    np.savez(path, scene_json=json.dumps(scene), **arrays)
    with pytest.raises(ValueError, match='polygon.*mismatch'):
        M.load_geometry(path)


def test_subdivided_cap_is_preserved_without_resampling():
    spec = geometry('blunt')
    e = spec['elements'][0]
    q = np.asarray(e['points_m'])
    # Subdividing a cap supplied upstream does not change its physical shape.
    # Split the final supplied segment again, leaving the cap-start metadata.
    e['points_m'] = np.vstack((q[:-1], (q[-2] + q[0]) / 2, q[0])).tolist()
    got = M.load_geometry(spec)
    np.testing.assert_array_equal(got['elements'][0]['points_m'], e['points_m'])
    e['points_m'][-2][0] += .0001
    with pytest.raises(ValueError, match='cap_start_index'):
        M.load_geometry(spec)


@pytest.mark.parametrize('source', ['scene', 'generic'])
def test_declared_height_is_bound_before_meshing(tmp_path, source):
    spec = wp4_scene() if source == 'scene' else geometry()
    expected = .09 if source == 'scene' else .1
    loaded = M.load_geometry(spec, expected_height_m=expected)
    assert loaded['height_m'] == pytest.approx(expected)
    with pytest.raises(ValueError, match='declared.*height|height.*declared'):
        F.write_case(tmp_path/'wrong-height', spec, iters=1, expected_height_m=expected+.02)
    assert not (tmp_path/'wrong-height').exists()


def test_height_datum_uses_main_element_not_lower_flap():
    spec = geometry()
    p = np.asarray(spec['elements'][1]['points_m'])
    p[:, 1] -= .09
    spec['elements'][1]['points_m'] = p.tolist()
    result = M.load_geometry(spec, expected_height_m=.1)
    assert result['height_m'] == .1
    assert result['minimum_clearance_m'] < result['height_m']


@pytest.mark.parametrize('bad', [0, -.1, float('nan'), float('inf'), True, '.1'])
def test_declared_height_requires_positive_finite_number(bad):
    with pytest.raises(ValueError, match='declared expected_height_m'):
        M.load_geometry(geometry(), expected_height_m=bad)


def test_boundary_layer_plan_rejects_hand_edited_layer_count():
    spec = geometry()
    plan = M.boundary_layer_plan({spec['config']: spec}, require_complete=False)
    settings = plan['families']['med30']
    settings['n_layers'] -= 1
    mesh = T.MESHES['med30']
    settings['bl_thickness_m'] = mesh['y1']*(mesh['g']**settings['n_layers']-1)/(mesh['g']-1)
    with pytest.raises(ValueError, match='layer count'):
        M.boundary_layer_settings(plan, M.load_geometry(spec), 'med30')


def test_realisation_parameters_preserve_features_and_ground():
    g = M.load_geometry(geometry('blunt'))
    ds = T.MESHES['med30']['ds']
    for k in range(8):
        r = M.realisation_parameters(g, 'med30', k)
        assert r['index'] == k
        assert all(0 <= value < ds for value in r['far_field_shift_m'].values())
        assert r['domain_bounds_m']['ground'] == 0
        for e in g['elements']:
            p = np.asarray(e['points_m'])[:-1]
            offset = k*(len(p)//8)
            features = r['elements'][e['name']]
            assert features['vertex_start_offset'] == offset
            rotated = np.roll(p, -offset, axis=0)
            np.testing.assert_array_equal(rotated[features['trailing_edge_index']], p[0])
            np.testing.assert_array_equal(rotated[features['leading_edge_index']], p[e['leading_edge_index']])
            np.testing.assert_array_equal(rotated[features['cap_start_index']], p[e['cap_start_index']])
    assert M.realisation_parameters(g, 'med30', 0)['halton_point'] == [0., 0.]
    assert M.realisation_parameters(g, 'med30', 1)['halton_point'] == [.5, 1/3]


@pytest.mark.skipif(_NO_GMSH, reason='gmsh not installed')
def test_eight_med30_realisations_are_distinct_and_fresh_process_repeatable(tmp_path):
    # Registered E2_sharp topology only; synthetic teardrops are not physical E2.
    spec = wp4_scene()
    src = tmp_path/'synthetic_E2_sharp.json'
    src.write_text(json.dumps(spec))
    # The runner launches exactly one case per fresh generator subprocess.
    # Reusing gmsh repeatedly in one process can retain process-history state.
    code = ('from pathlib import Path; from topo2d00.t2d_foam_case import write_case; '
            'import json,sys; m=write_case(Path(sys.argv[2]),Path(sys.argv[1]),family="med30",'
            'iters=1,realisation=int(sys.argv[3]),expected_height_m=.09); print(json.dumps(m))')
    env = {**os.environ, 'PYTHONPATH': str(SCRIPTS)}

    def generate(k, label):
        run = subprocess.run([sys.executable, '-c', code, str(src), str(tmp_path/label), str(k)],
                             capture_output=True, text=True, env=env, check=True, timeout=120)
        return json.loads(run.stdout)

    manifests = [generate(k, f'k{k}') for k in range(8)]
    shas = [m['mesh_msh_sha256'] for m in manifests]
    fresh = generate(3, 'repeat3')
    # Persist failed repeats as evidence BEFORE asserting their contract.
    receipt = {'evidence_class': 'DEVELOPMENT_SYNTHETIC_MESH_MECHANISM_CHECK',
               'config': 'E2_sharp', 'family': 'med30', 'gmsh_version': manifests[0]['gmsh_version'],
               'gmsh_options': {'General.NumThreads': 1, 'Mesh.Algorithm': 6,
                                'Mesh.MeshSizeFromPoints': 0, 'Mesh.MeshSizeFromCurvature': 0,
                                'Mesh.MeshSizeExtendFromBoundary': 0},
               'generator_sha256': manifests[0]['generator_sha256'],
               'mesh_writer': 'Unmodified scripts/t20_case.py:_write_msh; no coordinate post-processing.',
               'te_kinds': [e['te_kind'] for e in manifests[0]['elements']],
               'geometry_sha256': manifests[0]['geometry_sha256'],
               'runs': [{'realisation': m['realisation'], 'mesh_msh_sha256': m['mesh_msh_sha256'],
                         'mesh_realisation': m['mesh_realisation'], 'cells_3d': m['mesh_stats']['cells_3d'],
                         'fan_elements': m['mesh_stats']['fan_elements'],
                         'quality': m['mesh_stats']['quality'], 'proxy_failures': m['mesh_quality_failures']}
                        for m in manifests],
               'distinct_mesh_sha_count': len(set(shas)), 'fresh_process_repeat_index': 3,
               'process_scope': 'Each of the eight indices and its repeat ran in a fresh process, matching run_rans.py.',
               'fresh_process_repeat_mesh_sha256': fresh['mesh_msh_sha256'],
               'fresh_process_repeat_generator_sha256': fresh['generator_sha256'],
               'fresh_process_repeat_mesh_stats': fresh['mesh_stats'],
               'fresh_process_repeat_inputs_match': fresh['mesh_realisation'] == manifests[3]['mesh_realisation'],
               'fresh_process_repeat_matches': fresh['mesh_msh_sha256'] == shas[3],
               'scope': 'Synthetic topology/realisation mechanism only; no checkMesh, physical E2 or Kaggle claim.'}
    destination = Path(os.environ.get('WP05_MESH_REALISATION_RECEIPT', tmp_path/'mesh_realisations.json'))
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(receipt, indent=2, sort_keys=True, allow_nan=False)+'\n')
    print(json.dumps({'mesh_mechanism_receipt': str(destination), 'distinct_sha_count': len(set(shas)),
                      'fresh_process_repeat_matches': receipt['fresh_process_repeat_matches']}))
    assert len(set(shas)) == 8
    assert fresh['mesh_msh_sha256'] == shas[3]
    assert fresh['mesh_realisation'] == manifests[3]['mesh_realisation']
    assert manifests[0]['height_m'] == pytest.approx(.09)
    assert manifests[0]['h_over_c1'] == pytest.approx(.09/T.CHORD)
    assert manifests[0]['h_over_c'] == pytest.approx(.09/F.COMBINED_CHORD_M)


@pytest.mark.parametrize('change', ['units', 'chord', 'ground', 'gate', 'sharp_claim', 'surface_mismatch', 'cap_zero'])
def test_wp4_scene_adapter_fails_closed(change):
    scene = wp4_scene()
    if change == 'units':
        scene['units'] = 'm'
    elif change == 'chord':
        scene['normalizations']['c1_mm'] = 380.
    elif change == 'ground':
        scene['ground_z_mm'] = 1.
    elif change == 'gate':
        scene['gates']['accepted'] = False
    elif change == 'sharp_claim':
        scene['sharp_variant']['mathematically_sharp'] = True
    elif change == 'surface_mismatch':
        scene['elements'][0]['polygon_mm'][1][0] += .001
    else:
        scene['elements'][0]['pressure_mm'][-1] = scene['elements'][0]['suction_mm'][-1]
        e = scene['elements'][0]
        e['polygon_mm'] = np.vstack((np.asarray(e['suction_mm'])[::-1], np.asarray(e['pressure_mm'])[1:], np.asarray(e['suction_mm'])[-1:])).tolist()
    with pytest.raises(ValueError):
        M.load_geometry(scene)
