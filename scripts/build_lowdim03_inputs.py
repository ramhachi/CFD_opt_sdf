#!/usr/bin/env python3
"""Generate LOWDIM-03's seven shared geometries from the saved robust solution."""
from __future__ import annotations
import argparse
import hashlib
import json
import sys
import tempfile
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'scripts')]
import lowdim03_states as L
import lowdim01_states
import step01_states as S
import build_lowdim01_inputs as geometry_helpers
from build_grid01_inputs import CANONICAL_NPZ, FORMAL, canonical_json
from analyze_lowdim02a import flow32_criteria
from cfd_sdf.design.sdf_state import SDFDesignState
from cfd_sdf.fd08_v2_campaign import construct_state, state_identity
from fd08_v2_campaign_io import recompute_force_n

EVIDENCE = ROOT / 'docs/evidence/lowdim03_dual_grid_primal_2026_10_10'
GRID01 = ROOT / 'docs/evidence/grid01_cross_grid_secant_2026_10_09'
ANALYSIS = GRID01 / 'grid01_analysis.json'
PROPOSAL = EVIDENCE / 'inputs/robust_cross_grid.dir_f4_fortran.raw'
FLOW24_CSV = 'docs/evidence/step01_finite_step_secant_2026_10_09/kernel_output/a/states/step01__baseline/flow_24.forces.csv'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def build():
    if sha(ANALYSIS) != L.ANALYSIS_SHA256:
        raise ValueError('GRID-01 analysis differs from the approved immutable result')
    analysis = json.loads(ANALYSIS.read_text())
    if analysis['integrity']['pass'] is not True or analysis['verdict'] != 'GRID01_SECANT_RECORDED' or analysis['proposal_verdict']['verdict'] != 'FEASIBLE_CONE_FOUND':
        raise ValueError('GRID-01 result is not intact and feasible')
    saved = analysis['proposal_predictions_with_actual_m']['robust_cross_grid']
    source = json.loads((GRID01 / 'inventory.json').read_text())
    arrays = {n: S.read_f4(ROOT / source['directions'][n]['path']) for n in L.BASIS}
    for n in L.BASIS:
        if sha(ROOT / source['directions'][n]['path']) != source['directions'][n]['sha256_fortran_raw']:
            raise ValueError(f'basis hash mismatch: {n}')
    prop, info = lowdim01_states.coefficient_direction(dict(zip(L.BASIS, saved['coefficient_vector'])), arrays)
    raw = S.to_raw(prop)
    if S.sha256_bytes(raw) != L.PROPOSAL_SHA256 or info['m_max_abs_sum'] != saved['m_max_abs_sum_from_actual_four_direction_arrays']:
        raise ValueError('actual robust proposal differs from the approved direction')
    parent = SDFDesignState.load(CANONICAL_NPZ)
    if sha(CANONICAL_NPZ) != source['canonical_npz']['sha256'] or S.to_raw(parent.phi) != (ROOT / source['baseline']['path']).read_bytes():
        raise ValueError('canonical baseline differs from GRID-01')
    base_geo = geometry_helpers.geometry(parent)
    rows, seen = [], set()
    for item in L.plan():
        if item['kind'] == 'baseline':
            child = parent
            audit = {'changed_node_count': 0, 'maximum_pointwise_change_m': 0.0, 'zero_level_margin_m': state_identity(parent)['margin_m']}
            geo, gate = base_geo, None
        else:
            child, audit = construct_state(parent, prop, item['step_mm'], item['sign'])
            if S.to_raw(child.phi) != S.to_raw(S.perturb(parent.phi, prop, item['step_mm'], item['sign'])):
                raise ValueError('host and runner perturbation bytes differ')
            geo = geometry_helpers.geometry(child)
            gate = geometry_helpers.gates(base_geo, geo, audit)
            if not gate['all_hard_gates_pass']:
                raise ValueError(f'geometry preflight failed; do not reduce the ladder: {item["name"]}')
        ident = state_identity(child)
        if ident['phi_fortran_order_sha256'] in seen:
            raise ValueError('duplicate registered geometry')
        seen.add(ident['phi_fortran_order_sha256'])
        with tempfile.TemporaryDirectory() as tmp:
            p1, p2 = Path(tmp)/'1.npz', Path(tmp)/'2.npz'
            child.save(p1); child.save(p2)
            npz_sha = sha(p1)
            if npz_sha != sha(p2):
                raise ValueError('non-deterministic NPZ serialization')
        rows.append({**item, 'direction': None if item['kind']=='baseline' else 'robust_cross_grid',
                     **{k: ident[k] for k in ('phi_fortran_order_sha256','phi_c_order_sha256','state_sha256')},
                     'npz_sha256': npz_sha, 'changed_node_count': int(audit['changed_node_count']),
                     'maximum_pointwise_change_m': float(audit['maximum_pointwise_change_m']),
                     'zero_level_margin_m': float(audit['zero_level_margin_m']), 'margin_tolerance_m': 1e-6,
                     'geometry': geo, 'geometry_gates': gate})
    formal = json.loads(FORMAL.read_text())
    grids = {}
    for kernel, case, csv_path, measurement, job in (
        ('a','flow_24',FLOW24_CSV,formal['measurement'],'scripts/waterlily_xfid_candidate_c_job.jl'),
        ('b','flow_32',source['flow32_baseline_reference']['forces_csv_path'],flow32_criteria(formal)['measurement'],'scripts/waterlily_lowdim02_flow32_job.jl')):
        measurement = json.loads(json.dumps(measurement))
        measurement.update({'case_id':case,'kernel_execution_allowance_s':10800,'per_state_timeout_s':900,'solver_wall_time_cap_s':6300,'qualification_claim':'bounded LOWDIM-03 two-grid actual-primal capability; no qualification'})
        host = recompute_force_n(ROOT/csv_path, {'measurement': measurement})
        expected = S.FD08_BASELINE_CSV_SHA256 if kernel=='a' else source['flow32_baseline_reference']['forces_csv_sha256']
        if sha(ROOT/csv_path) != expected:
            raise ValueError(f'{case} baseline bytes differ')
        grids[kernel] = {'case_id': case, 'job': job, 'measurement': measurement,
                         'baseline_reference': {'forces_csv_path': csv_path, 'forces_csv_sha256': expected,
                                                'host_recomputed_n': {q:host[q] for q in ('drag_n','downforce_n')},
                                                'force_scale_n_per_solver_force': host['force_scale_n_per_solver_force']}}
    inventory = {'kind':'lowdim03_dual_grid_primal_inventory', 'basis_order': list(L.BASIS),
                 'canonical_npz': source['canonical_npz'], 'baseline': source['baseline'], 'directions':source['directions'],
                 'job_env_common': source['job_env_common'], 'margin_gate_m': 0.15,
                 'grids': grids, 'kernels': {k:[r['name'] for r in rows] for k in grids}, 'states':rows,
                 'proposal': {'file':str(PROPOSAL.relative_to(ROOT)), 'sha256_fortran_raw':L.PROPOSAL_SHA256,
                              'analysis_path':str(ANALYSIS.relative_to(ROOT)), 'analysis_sha256':L.ANALYSIS_SHA256,
                              'coefficient_vector':saved['coefficient_vector'], 'm_max_abs_sum':saved['m_max_abs_sum_from_actual_four_direction_arrays'],
                              'per_unit_step_basis_coefficients': saved['per_unit_step_basis_coefficients_c_over_m'], 'per_grid':saved['per_grid']},
                 'geometry_gate_thresholds': json.loads((ROOT/'docs/evidence/lowdim01_four_direction_capability_2026_10_09/inventory.json').read_text())['geometry_gate_thresholds'],
                 'perturbation':source['perturbation'], 'formal_criteria_path':str(FORMAL.relative_to(ROOT)), 'formal_criteria_sha256':sha(FORMAL)}
    return inventory, raw


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--check',action='store_true')
    args=p.parse_args()
    inv,raw=build(); data=canonical_json(inv); target=EVIDENCE/'inventory.json'
    if args.check:
        if target.read_bytes()!=data or PROPOSAL.read_bytes()!=raw:
            raise SystemExit('frozen inventory/proposal differs from its derivation')
    else:
        if target.exists() or PROPOSAL.exists():
            raise SystemExit('refusing to overwrite LOWDIM-03 inputs')
        PROPOSAL.parent.mkdir(parents=True,exist_ok=True); PROPOSAL.write_bytes(raw)
        target.write_bytes(data); target.with_suffix('.json.sha256').write_text(hashlib.sha256(data).hexdigest()+'\n')
    print('inventory reproduced',hashlib.sha256(data).hexdigest())

if __name__=='__main__':
    main()
