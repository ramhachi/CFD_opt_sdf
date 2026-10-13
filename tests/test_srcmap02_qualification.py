"""Qualification logic tested on small analytic meshes; no source-STL queries."""
import importlib.util
from pathlib import Path
from unittest.mock import patch
import numpy as np
import pytest
spec=importlib.util.spec_from_file_location('srcmap02',Path(__file__).parents[1]/'scripts/qualify_srcmap02.py')
Q=importlib.util.module_from_spec(spec);spec.loader.exec_module(Q)
import run_srcmap02 as R


def libigl_available():
    try: Q.igl_module()
    except (ImportError,ValueError): pytest.skip('diagnostic-only libigl2.6.3 not installed; formal fixture campaign requires exact pin')


def fixture(name):
    return next(row for row in Q.fixture_definitions() if row[0]==name)


def test_analytic_sphere_sign():
    libigl_available()
    _,mesh,points,expected,_,_=fixture('triangulated_sphere')
    for candidate in ('A','B'):
        assert np.array_equal(Q.query(mesh,points,candidate,3)['sign_int8'],expected)


def test_analytic_box_edge_vertex_sign():
    libigl_available()
    for name in ('axis_aligned_box','rotated_box','tetrahedron'):
        _,mesh,points,expected,_,_=fixture(name)
        for candidate in ('A','B'):
            assert np.array_equal(Q.query(mesh,points,candidate,4)['sign_int8'],expected)


def test_ab_sign_convention_and_unsigned_separation():
    libigl_available()
    mesh=Q.trimesh.creation.box(extents=(2,2,2));points=np.array([[0.,0,0],[2,0,0]])
    with patch.object(Q.trimesh.proximity,'signed_distance',side_effect=AssertionError('random path forbidden')):
        for c in ('A','B'):
            result=Q.query(mesh,points,c,1)
            assert result['sign_int8'].tolist()==[-1,1]
            assert result['phi_float64'].tolist()==[-1.,1.]
            assert result['unsigned_float64'].tolist()==[1.,1.]


def test_exact_zero_and_fail_closed_states():
    signs,phi=Q.combine([0.,0.,2.],[-1.,0.,-4.])
    assert signs.tolist()==[0,0,-1]
    assert phi.tolist()==[0.,0.,-2.] and not np.signbit(phi[:2]).any()
    for unsigned,raw in (([-0.],[1.]),([-1.],[1.]),([1.],[0.]),([np.inf],[1.]),([1.],[np.nan])):
        with pytest.raises(ValueError):Q.combine(unsigned,raw)
    libigl_available()
    mesh=Q.trimesh.creation.box(extents=(2,2,2))
    for c in ('A','B'):
        data=Q.query(mesh,np.array([[1.,0,0],[1,1,0],[1,1,1]]),c,2)
        assert not np.signbit(data['phi_float64']).any()
        assert not np.signbit(data['phi_float32']).any()
        assert np.count_nonzero(data['phi_float64'])==0


def test_chunk_assembly():
    libigl_available()
    _,mesh,points,_,_,_=fixture('axis_aligned_box')
    for candidate in ('A','B'):
        reference=Q.query(mesh,points,candidate,len(points))
        changed=Q.query(mesh,points,candidate,3)
        assert R.compare(reference,changed)['exact']


def test_order_restoration():
    libigl_available()
    _,mesh,points,_,_,_=fixture('axis_aligned_box')
    for c in ('A','B'):
        reference=Q.query(mesh,points,c,4)
        for order in ('reverse','permuted'):
            indices=Q.permutation(len(points),order)
            result={k:Q.restore(v,indices) for k,v in Q.query(mesh,points[indices],c,4).items()}
            assert R.compare(reference,result)['exact']
    with pytest.raises(ValueError):Q.restore(np.arange(3),np.zeros(3,dtype=int))


def test_repeat_hash_equality_and_state_volume_helpers():
    libigl_available()
    _,mesh,points,_,_,_=fixture('tetrahedron')
    for c in ('A','B'):
        a,b=Q.query(mesh,points,c,3),Q.query(mesh,points,c,3)
        for key in Q.ARRAY_KEYS:assert Q.array_sha(a[key])==Q.array_sha(b[key])
    state=Q.SDFDesignState.create(phi=np.ones((3,3,3),dtype='f4'),origin_m=(0.,0.,0.),spacing_m=1.,narrow_band_width_m=1.)
    clone=Q.candidate_state(state,state.phi.copy())
    assert clone.state_sha256==state.state_sha256
    assert Q.volume_record(clone)['hard_volume_m3']==0.
    assert Q.volume_record(clone)['smooth_gV']==-1.


def test_classification_logic_and_raw_magnitude_not_a_gate():
    inputs=dict(integrity=True,analytic=True,zero_semantics=True,a_stable=True,b_stable=True,
                nonzero_disagreements=0,cross_environment_exact=True)
    assert Q.classify(**inputs)=='DETERMINISTIC_SIGNER_QUALIFIED'
    cases=[('integrity',False,'SRCMAP02_INCONCLUSIVE'),('analytic',False,'SRCMAP02_INCONCLUSIVE'),
        ('zero_semantics',False,'SRCMAP02_INCONCLUSIVE'),('a_stable',False,'PSEUDONORMAL_NOT_DETERMINISTIC'),
        ('b_stable',False,'WINDING_CONTROL_NOT_STABLE'),('nonzero_disagreements',1,'DETERMINISTIC_SIGNER_DISAGREEMENT'),
        ('cross_environment_exact',False,'SRCMAP02_INCONCLUSIVE')]
    for key,value,expected in cases:assert Q.classify(**dict(inputs,**{key:value}))==expected
    assert Q.classify(**dict(inputs,integrity=False,a_stable=False))=='SRCMAP02_INCONCLUSIVE'
    data={k:np.ones(2,dtype='i1' if k=='sign_int8' else 'f4' if k=='phi_float32' else 'f8') for k in Q.ARRAY_KEYS}
    data['raw_signer_float64']=np.ones(2)
    changed={k:v.copy() for k,v in data.items()};changed['raw_signer_float64']*=2
    assert R.compare(data,changed)['exact']
    changed['unsigned_float64'][0]=np.nextafter(1.,2.)
    assert not R.compare(data,changed)['exact']
