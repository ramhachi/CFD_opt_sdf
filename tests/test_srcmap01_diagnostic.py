"""Diagnostic invariants: no measured mapping values and no production changes."""
import importlib.util
from pathlib import Path
from unittest.mock import patch
import numpy as np
import pytest
spec=importlib.util.spec_from_file_location('srcmap',Path(__file__).parents[1]/'scripts/diagnose_srcmap01.py')
D=importlib.util.module_from_spec(spec);spec.loader.exec_module(D)

def test_strict_bits_distinguishes_signed_zero_and_ulp():
    a=np.array([0.,1.],dtype=np.float32);b=a.copy();b[0]=-0.
    r=D.strict(a,b)
    assert r['array_equal'] and not r['bit_equal'] and r['signed_zero_only_count']==1
    b[1]=np.nextafter(b[1],np.float32(2))
    assert D.strict(a,b)['different_bits_count']==2
    assert not D.strict(a.astype('f8'),b.astype('f8'))['bit_equal']

def test_explicit_memory_and_endian_hashes():
    a=np.arange(12,dtype=np.float32).reshape(3,4)
    assert D.array_sha(a,'C')!=D.array_sha(a,'F')
    assert D.array_sha(a,'C','<')!=D.array_sha(a,'C','>')
    assert D.array_sha(a)==D.array_sha(np.asfortranarray(a))
    assert D.array_sha(a)==D.array_sha(a.astype('>f4'))

def test_permutation_restores_and_rejects_duplicate():
    a=np.arange(101);order=D.permutation(len(a),'permuted')
    assert np.array_equal(D.restore(a[order],order),a)
    assert np.array_equal(order,D.permutation(len(a),'permuted'))
    with pytest.raises(ValueError):D.restore(a,np.zeros(len(a),dtype=int))

def test_production_chunk_assembly_unchanged():
    mesh=D.trimesh.creation.box();points=np.arange(21,dtype=float).reshape(7,3)
    def direct(mesh,p):return p[:,0]
    with patch.object(D.trimesh.proximity,'signed_distance',direct):
        values,events=D.traced_production(mesh,points,3)
    assert np.array_equal(values,-points[:,0])
    assert [e['point_count'] for e in events if e['call']=='try_signed_distance']==[3,3,1]

def test_fallback_and_contains_exception_provenance():
    mesh=D.trimesh.creation.box();points=np.zeros((3,3))
    def fail(*args,**kwargs):raise RuntimeError('synthetic direct failure')
    def closest(mesh,p):return p.copy(),np.ones(len(p)),np.zeros(len(p),dtype=int)
    with patch.object(D.trimesh.proximity,'signed_distance',fail),patch.object(D.trimesh.proximity,'closest_point',closest),patch.object(D.trimesh.Trimesh,'contains',side_effect=ValueError('synthetic contains failure')):
        values,events=D.traced_production(mesh,points,2)
    assert np.array_equal(values,np.ones(3)) # actual _contains_safe zero mask
    assert any(e['call']=='try_signed_distance' and e['exception_class']=='RuntimeError' for e in events)
    assert any(e['call']=='mesh_contains' and e['exception_class']=='ValueError' for e in events)
    assert sum(e['call']=='production_contains_safe' for e in events)==2

def test_terminal_classification_requires_complete_and_localized_evidence():
    assert D.classify(True,True,True)=='SOURCE_MAPPING_REPRODUCIBLE'
    assert D.classify(False,False,False)=='SOURCE_MAPPING_ALGORITHM_NONDETERMINISTIC'
    assert D.classify(True,False,False,environment_match=True)=='SOURCE_MAPPING_ENVIRONMENT_DEPENDENT'
    assert D.classify(True,False,False,historical_path_proven=True)=='SOURCE_MAPPING_IMPLEMENTATION_PATH_DIVERGENCE'
    assert D.classify(True,False,False)=='SOURCE_MAPPING_UNRESOLVED'
    assert D.classify(False,False,False,complete=False)=='SOURCE_MAPPING_UNRESOLVED'

def test_rng_wrappers_preserve_draws_and_final_states():
    mesh=D.trimesh.creation.box();points=np.zeros((4,3));saved=np.random.get_state()
    def fake(mesh,p):
        return np.full(len(p),D.trimesh.util.random_generator().random(3)[0]+np.random.random(3)[0])
    try:
        first=np.random.default_rng(123);np.random.seed(456)
        with patch.object(D.trimesh.util,'random_generator',lambda *a,**k:first),patch.object(D.trimesh.proximity,'signed_distance',fake):
            expected=D.sdf.signed_distance(mesh,points,chunk_size=2)
        first_state=first.bit_generator.state;legacy_state=repr(np.random.get_state())
        second=np.random.default_rng(123);np.random.seed(456)
        with patch.object(D.trimesh.util,'random_generator',lambda *a,**k:second),patch.object(D.trimesh.proximity,'signed_distance',fake):
            actual,events=D.traced_production(mesh,points,2)
        assert np.array_equal(expected,actual)
        assert first_state==second.bit_generator.state and legacy_state==repr(np.random.get_state())
        assert sum(e['call']=='random_retry_draw' for e in events)==2
        assert sum(e['call']=='legacy_random_retry_draw' for e in events)==2
    finally:np.random.set_state(saved)

def test_aggregator_grouping_and_local_direction_gate():
    import run_srcmap01 as R
    reference=np.array([1.,2.],dtype='f4')
    def row(id,stage,offset=0):
        f32=reference.copy();f32[0]+=offset
        return dict(id=id,stage=stage,grid='v17',chunk_size=200000,ordering='canonical',mode='production',
                    comparison_float32_registered=D.strict(f32,reference),_float32=f32,_float64=f32.astype('f8'),events=[])
    base=[row('A1','A'),row('A2','A'),row('B200000','B'),row('Ccanonical','C'),row('G1','G'),row('G2','G')]
    assert R.classification_inputs(base,False)['terminal_classification']=='SOURCE_MAPPING_REPRODUCIBLE'
    for index in (2,3,5):
        changed=base.copy();changed[index]=row(base[index]['id'],base[index]['stage'],1)
        assert R.classification_inputs(changed,False)['terminal_classification']=='SOURCE_MAPPING_ALGORITHM_NONDETERMINISTIC'
    stable=[row('A1','A',1),row('A2','A',1),row('G1','G',1),row('G2','G',1)]
    assert R.classification_inputs(stable,False)['terminal_classification']=='SOURCE_MAPPING_UNRESOLVED'
    mixed=[dict(r,events=[{'call':'production_contains_safe' if i else 'try_signed_distance'}]) for i,r in enumerate(base)]
    assert R.classification_inputs(mixed,False)['terminal_classification']=='SOURCE_MAPPING_REPRODUCIBLE'
    assert R.classification_inputs(base,True)['terminal_classification']=='SOURCE_MAPPING_UNRESOLVED'
    env=[row('A1','A'),row('A2','A'),row('G1','G',1),row('G2','G',1)]
    assert R.classification_inputs(env,False)['terminal_classification']=='SOURCE_MAPPING_ENVIRONMENT_DEPENDENT'
