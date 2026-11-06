"""Development contracts; synthetic second body is not the published E2 geometry."""
from __future__ import annotations

import hashlib
import importlib.util
import json
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
    q, _, _ = T.airfoil_points(0.448)
    if kind == 'blunt':
        # Cut the last 3% from both surfaces. Closing edge is an explicit cap.
        le = int(np.argmin(q[:, 0]))
        lo = q[:le + 1]
        hi = q[le:]
        xcut = q[:, 0].max() - 0.03 * T.CHORD
        lo = lo[lo[:, 0] <= xcut]
        hi = hi[hi[:, 0] <= xcut]
        q = np.vstack([lo, hi[1:], lo[0]])
    flap = q.copy() * 0.55 + [0.23, 0.08]
    return {'config': 'synthetic_two_body', 'main_chord_m': T.CHORD,
            'elements': [{'name': name, 'te_kind': kind, 'points_m': p.tolist()}
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
    assert not man['mesh_quality_failures'], man['mesh_stats']['quality']
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
    assert not man['mesh_quality_failures'], man['mesh_stats']['quality']


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
    spec['nominal_ride_height_m'] = .1
    spec['height_datum'] = 'published_zero_incidence_ground_distance'
    result = M.load_geometry(spec)
    assert result['nominal_ride_height_m'] == .1
    assert result['height_datum'] == spec['height_datum']
    assert result['minimum_clearance_m'] != result['nominal_ride_height_m']
    assert result['main_element_clearance_m'] == result['minimum_clearance_m']


def wp4_scene():
    """Source-compatible WP4 export; synthetic values, not the paper's E2."""
    s = np.array([[0, 100], [50, 90], [120, 100], [220, 120]], float)
    p = np.array([[0, 100], [50, 120], [120, 135], [220, 130]], float)
    elements = []
    for name, lower, upper in [('main', s, p), ('flap1', s * .55 + [230, 80], p * .55 + [230, 80])]:
        elements.append({'name': name, 'suction_mm': lower.tolist(), 'pressure_mm': upper.tolist(),
                         'polygon_mm': np.vstack((lower[::-1], upper[1:], lower[-1:])).tolist(),
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
