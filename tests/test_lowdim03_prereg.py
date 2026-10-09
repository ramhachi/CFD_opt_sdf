"""Verify persisted inputs and the exact rendered worker arithmetic before CFD."""
import copy
import importlib.util
import json
import sys
import types
from pathlib import Path

import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'src')]
import build_lowdim03_inputs as I
import build_lowdim03_kernel as K
import lowdim03_states as L
import step01_states as S


@pytest.fixture(scope='module')
def inputs():
    return I.build()


def test_persisted_seven_shared_geometries_match_saved_solution(inputs):
    inv,raw=inputs
    assert inv==json.loads((I.EVIDENCE/'inventory.json').read_text())
    assert raw==I.PROPOSAL.read_bytes()
    assert S.sha256_bytes(raw)==L.PROPOSAL_SHA256
    assert len({r['phi_fortran_order_sha256'] for r in inv['states']})==7
    assert inv['kernels']['a']==inv['kernels']['b']==[r['name'] for r in L.plan()]
    assert all(r['geometry_gates']['all_hard_gates_pass'] for r in inv['states'][1:])


@pytest.mark.parametrize('kernel',['a','b'])
def test_rendered_runner_matches_registered_phi_and_preserves_runtime(inputs,kernel):
    inv,raw=inputs
    worker=types.ModuleType('lowdim03_test_worker')
    worker.__file__='synthetic_runner.py'
    exec(compile(K.render('0'*40,kernel),'runner.py','exec'),worker.__dict__)
    assert worker.expected_plan(inv)==inv['states']
    assert 'JSON3' not in worker.GPU_PROBE_CODE
    base=S.read_f4(ROOT/inv['baseline']['path'])
    prop=S.read_f4(I.PROPOSAL)
    for row in inv['states']:
        generated=worker.generate_phi(S,ROOT,row,base,{'robust_cross_grid':prop})
        assert S.sha256_bytes(generated)==row['phi_fortran_order_sha256']
        env=worker.state_env({'CUDA_DEVICE_ORDER':'PCI_BUS_ID','CUDA_VISIBLE_DEVICES':'0','JULIA_NUM_THREADS':'1'},inv,row,'GPU-test')
        assert env['W4_CANONICAL_DESIGN_SPACING_M']=='0.025'
        assert env['W4_PHI_FORTRAN_SHA256']==row['phi_fortran_order_sha256']
        assert env['CUDA_VISIBLE_DEVICES']=='0'
    bad=copy.deepcopy(inv);bad['states'][1]['sign']=-1
    with pytest.raises(ValueError):worker.expected_plan(bad)
    bad=copy.deepcopy(inv);bad['grids'][kernel]['case_id']='wrong_grid'
    with pytest.raises(ValueError):worker.expected_plan(bad)
