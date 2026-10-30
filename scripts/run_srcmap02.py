#!/usr/bin/env python3
"""Run the preregistered SRCMAP-02 matrix exactly once, then saved-array analysis."""
from __future__ import annotations
import argparse
import itertools
import json
import os
from pathlib import Path
import subprocess
import sys
import numpy as np
from qualify_srcmap02 import (ROOT, E, OLD, SRCMAP01, sha, write_json, array_sha,
    strict, load_inputs, points_for, structural_runtime, classify, ARRAY_KEYS)


def frozen_files_check(freeze):
    for record in freeze['files']:
        if sha(ROOT / record['path']) != record['sha256']:
            raise ValueError(f"frozen input changed: {record['path']}")


def environment(freeze):
    env = dict(os.environ)
    env['PYTHONHASHSEED'] = '0'
    env['PYTHONPATH'] = freeze['pythonpath']
    return env


def expected_inventory(freeze, label):
    return json.loads((ROOT / freeze['runtime_inventories'][label]).read_text())


def assert_run_identity(row, job, freeze):
    baseline = expected_inventory(freeze, job['environment'])
    for key in ('runtime_before', 'runtime_after'):
        if structural_runtime(row[key]) != structural_runtime(baseline['runtime']):
            raise ValueError(f"{job['id']}: frozen runtime/source drift {key}")
    if row['mesh'] != baseline['mesh']: raise ValueError(f"{job['id']}: mesh drift")
    if row['point_coordinates_c_little_sha256'] != freeze['point_coordinate_hashes'][job['grid']]:
        raise ValueError(f"{job['id']}: coordinates drift")
    for a, b in [('grid','grid'),('candidate','candidate'),('chunk_size','chunk'),('ordering','order')]:
        if row[a] != job[b]: raise ValueError(f"{job['id']}: job contract drift")
    path = E / 'diagnostics' / f"{job['id']}.npz"
    if sha(path) != row['npz_sha256']: raise ValueError('field file hash mismatch')
    with np.load(path) as arrays:
        if set(arrays.files) != set(row['arrays']): raise ValueError('array key mismatch')
        for key, record in row['arrays'].items():
            value = arrays[key]
            if array_sha(value) != record['sha256'] or list(value.shape) != record['shape'] or value.dtype.str != record['dtype']:
                raise ValueError('saved array identity mismatch')


def compare(a, b):
    result = {}
    for key in ARRAY_KEYS:
        if a[key].dtype.kind == 'f': result[key] = strict(a[key], b[key])
        else:
            result[key] = {'bit_equal': bool(np.array_equal(a[key], b[key])),
                           'different_bits_count': int(np.count_nonzero(a[key] != b[key]))}
    result['raw_signer_float64_descriptive'] = strict(a['raw_signer_float64'], b['raw_signer_float64'])
    result['exact'] = all(result[k]['bit_equal'] for k in ARRAY_KEYS)
    return result


def pair_result(a, b, arrays):
    result = compare(arrays[a['id']], arrays[b['id']])
    result.update(a=a['id'], b=b['id'], state_hash_equal=a['state_sha256'] == b['state_sha256'])
    result['exact'] = result['exact'] and result['state_hash_equal']
    return result


def sample_distribution(values):
    values = np.asarray(values, dtype='f8')
    return {'count': int(values.size), 'min_m': float(values.min()) if values.size else None,
            'max_m': float(values.max()) if values.size else None,
            'quantiles_m': {str(q): float(np.quantile(values, q)) if values.size else None for q in (0,.25,.5,.75,1)},
            'descriptive_near_counts': {str(t): int(np.count_nonzero(values <= t)) for t in (0,1e-10,1e-9,1e-8,1e-7)},
            'threshold_role': 'descriptive only; no tolerance in any equality/qualification gate'}


def difference_detail(a, b, unsigned, coordinates):
    diff = a.view('u4') != b.view('u4')
    sign = np.sign(a).astype('i1') != np.sign(b).astype('i1')
    indices = np.argwhere(diff)
    flat = np.flatnonzero(diff)
    return {'comparison': strict(a,b), 'three_way_sign_difference_count':int(sign.sum()),
            'differing_indices':indices.tolist(), 'coordinates_m':coordinates[flat].tolist(),
            'a_values':a.ravel()[flat].astype('f8').tolist(),
            'b_values':b.ravel()[flat].astype('f8').tolist(),
            'unsigned_distance_distribution':sample_distribution(unsigned[diff]),
            'sign_disagreement_unsigned_distance_distribution':sample_distribution(unsigned[sign])}


def summarize(records, freeze):
    arrays = {}
    for row in records:
        with np.load(E / 'diagnostics' / f"{row['id']}.npz") as data:
            arrays[row['id']] = {k:data[k] for k in data.files}
    refs = {grid: load_inputs(grid)[0] for grid in ('v16','v17')}
    coordinates = {g:points_for(state) for g,state in refs.items()}
    base = {c:next(r for r in records if r['stage']=='B' and r['candidate']==c) for c in ('A','B')}
    repeat = {}
    chunk_order = {}
    cross = {}
    stable = {}
    for candidate in ('A','B'):
        rows = [r for r in records if r['stage']=='B' and r['candidate']==candidate]
        pairs = [pair_result(a,b,arrays) for a,b in itertools.combinations(rows,2)]
        repeat[candidate] = {'run_ids':[r['id'] for r in rows], 'pairwise':pairs,
                             'pass':len(rows)==5 and all(p['exact'] for p in pairs)}
        perturbations = [r for r in records if r['stage']=='C' and r['candidate']==candidate]
        comparisons = [pair_result(base[candidate],r,arrays) for r in perturbations]
        chunk_order[candidate] = {'comparisons_to_first_repeat':comparisons,
                                 'pass':len(perturbations)==9 and all(p['exact'] for p in comparisons)}
        alternative = [r for r in records if r['stage']=='D' and r['candidate']==candidate]
        comparisons = [pair_result(base[candidate],r,arrays) for r in alternative]
        cross[candidate] = {'comparisons':comparisons, 'pass':len(alternative)==1 and all(p['exact'] for p in comparisons)}
        stable[candidate] = repeat[candidate]['pass'] and chunk_order[candidate]['pass']
    write_json(E/'repeatability.json',{'independent_processes':True,'candidates':repeat,
        'gate_arrays':list(ARRAY_KEYS),'state_hash_in_gate':True,
        'raw_signer_magnitude_role':'retained descriptive only; signed winding output is not unsigned magnitude'})
    write_json(E/'chunk_order.json',{'full_factorial':True,'candidates':chunk_order})
    write_json(E/'cross_environment.json',{'candidates':cross,
        'scope':'only the two frozen bundles; not universal portability',
        'float64_required':True,'float32_only_rescue_allowed':False})
    a, b = arrays[base['A']['id']], arrays[base['B']['id']]
    unequal = a['sign_int8'] != b['sign_int8']
    both_nonzero = (a['unsigned_float64'] > 0) & (b['unsigned_float64'] > 0)
    material = unequal & both_nonzero
    zero_disagreement = unequal & ~both_nonzero
    agreement = {'sign_difference_count':int(unequal.sum()),
        'nonzero_sign_difference_count':int(material.sum()),
        'exact_zero_disagreement_count':int(zero_disagreement.sum()),
        'differing_indices':np.argwhere(unequal).tolist(),
        'coordinates_m':coordinates['v17'][np.flatnonzero(unequal)].tolist(),
        'unsigned_distance_distribution':sample_distribution(a['unsigned_float64'][unequal]),
        'field_comparison':compare(a,b),'pass':not unequal.any()}
    v16_rows={c:next(r for r in records if r['stage']=='G' and r['candidate']==c) for c in ('A','B')}
    a16,b16=(arrays[v16_rows[c]['id']] for c in ('A','B'))
    unequal16=a16['sign_int8']!=b16['sign_int8']
    both_nonzero16=(a16['unsigned_float64']>0)&(b16['unsigned_float64']>0)
    material16=unequal16&both_nonzero16
    zero_disagreement16=unequal16&~both_nonzero16
    agreement['v16']={'sign_difference_count':int(unequal16.sum()),
        'nonzero_sign_difference_count':int(material16.sum()),
        'exact_zero_disagreement_count':int(zero_disagreement16.sum()),
        'differing_indices':np.argwhere(unequal16).tolist(),
        'coordinates_m':coordinates['v16'][np.flatnonzero(unequal16)].tolist(),
        'unsigned_distance_distribution':sample_distribution(a16['unsigned_float64'][unequal16]),
        'field_comparison':compare(a16,b16),'pass':not unequal16.any()}
    agreement['both_grids_pass']=agreement['pass'] and agreement['v16']['pass']
    write_json(E/'candidate_agreement.json',agreement)
    old_rows = []
    for path in sorted((SRCMAP01/'diagnostics').glob('*.json')):
        row = json.loads(path.read_text())
        if row.get('mode') == 'production' and row.get('grid') == 'v17':
            old_rows.append((path.stem, path.with_suffix('.npz')))
    differences = []
    for candidate in ('A','B'):
        field = arrays[base[candidate]['id']]
        for label, old_field in [('registered_v17', refs['v17'].phi)] + [
                (label,np.load(path)['phi_float32']) for label,path in old_rows]:
            detail = difference_detail(field['phi_float32'],old_field,field['unsigned_float64'],coordinates['v17'])
            detail.update(candidate=candidate,reference=label,
                registered_field_agreement_is_gate=False)
            differences.append(detail)
    write_json(E/'old_field_comparison.json',{'comparisons':differences,
        'float64_historical_limitation':'registered field has Float32 only; no reconstructed Float64 authority'})
    authority = json.loads((E/'authority_saved_nodes.json').read_text())
    # Accept the explicit saved-node authority schema; no new query or node selection.
    known = authority['nodes']
    problem = []
    mesh = load_inputs('v17')[1]
    for node in known:
        ijk = tuple(node['ijk'])
        flat = int(np.ravel_multi_index(ijk, refs['v17'].shape))
        point = coordinates['v17'][flat]
        item = {'ijk':list(ijk),'coordinate_m':point.tolist(),'authority':node,'candidates':{}}
        for candidate in ('A','B'):
            field = arrays[base[candidate]['id']]
            face = int(field['closest_face_int64'][flat])
            closest = field['closest_point_float64'][flat]
            triangle = mesh.triangles[face]
            bary = trimesh_barycentric(triangle,closest)
            zeros = int(np.count_nonzero(bary == 0))
            item['candidates'][candidate] = {'sign':int(field['sign_int8'][ijk]),
                'unsigned_distance_m':float(field['unsigned_float64'][ijk]),
                'raw_signer':float(field['raw_signer_float64'][ijk]),
                'phi_float64':float(field['phi_float64'][ijk]),
                'phi_float32':float(field['phi_float32'][ijk]),
                'closest_triangle_id':face,'closest_point_m':closest.tolist(),
                'barycentric':bary.tolist(),
                'closest_feature_exact_barycentric': 'vertex' if zeros>=2 else 'edge' if zeros==1 else 'face',
                'feature_label_role':'exact computed barycentric zeros, descriptive, not a tolerance or sign gate'}
            if candidate=='A':item['candidates'][candidate]['pseudonormal']=field['pseudonormal_float64'][flat].tolist()
        problem.append(item)
    write_json(E/'problem_nodes.json',{'source_authority_sha256':sha(E/'authority_saved_nodes.json'),
        'no_additional_geometry_queries':True,'nodes':problem,
        'all_known_nodes_agree':all(n['candidates']['A']['sign']==n['candidates']['B']['sign'] for n in problem)})
    volume_rows = []
    for candidate in ('A','B'):
        for grid in ('v16','v17'):
            row = base[candidate] if grid=='v17' else next(r for r in records if r['stage']=='G' and r['candidate']==candidate)
            field = arrays[row['id']]
            difference_path=E/'diagnostics'/f'{candidate}_{grid}_registered_difference.npz'
            if difference_path.exists(): raise ValueError('refusing difference map overwrite')
            reference=refs[grid].phi;new=field['phi_float32']
            np.savez_compressed(difference_path, different_bits_float32=new.view('u4')!=reference.view('u4'),
                sign_difference=np.sign(new)!=np.sign(reference),
                delta_float32_vs_registered=new.astype('f8')-reference.astype('f8'))
            volume_rows.append({'difference_npz':str(difference_path.relative_to(ROOT)),
                'difference_npz_sha256':sha(difference_path),'candidate':candidate,'grid':grid,'id':row['id'],
                'volume':row['volume'],'registered_volume':row['registered_volume'],
                'hard_volume_delta_registered_m3':row['volume']['hard_volume_m3']-row['registered_volume']['hard_volume_m3'],
                'registered_comparison':difference_detail(field['phi_float32'],refs[grid].phi,field['unsigned_float64'],coordinates[grid])})
    write_json(E/'volume_bridge_diagnostic.json',{'rows':volume_rows,
        'v17_minus_v16_hard_m3':{c:next(r['volume']['hard_volume_m3'] for r in volume_rows if r['candidate']==c and r['grid']=='v17')-
            next(r['volume']['hard_volume_m3'] for r in volume_rows if r['candidate']==c and r['grid']=='v16') for c in ('A','B')},
        'descriptive_only':True,'reference_migration':False,'p22_v1_changed':False})
    analytic = json.loads((E/'analytic_fixtures.json').read_text())
    zero = all(r['zero_semantics_pass'] for r in records) and not zero_disagreement.any() and not zero_disagreement16.any()
    cross_exact = all(cross[c]['pass'] for c in ('A','B'))
    terminal = classify(integrity=True,analytic=analytic['pass'],zero_semantics=zero,
        a_stable=stable['A'],b_stable=stable['B'],nonzero_disagreements=int(material.sum()+material16.sum()),
        cross_environment_exact=cross_exact)
    frozen_files_check(freeze)
    write_json(E/'classification.json',{'terminal_classification':terminal,'complete':True,
        'integrity_pass':True,'analytic_pass':analytic['pass'],'zero_semantics_pass':zero,
        'a_repeat_chunk_order_exact':stable['A'],'b_repeat_chunk_order_exact':stable['B'],
        'a_b_nonzero_sign_disagreements':int(material.sum()+material16.sum()),
        'v17_nonzero_sign_disagreements':int(material.sum()),
        'v16_nonzero_sign_disagreements':int(material16.sum()),
        'cross_environment_exact':cross_exact,'preferred_candidate_preregistered':'A',
        'old_hash_matching_objective':False,'candidate_adopted':False,'production_changed':False,
        'finite_observation_scope':'only preregistered processes, perturbations and two frozen environments; no universal determinism/portability proof',
        'cfd_runs':0,'kaggle_submissions':0,'p22_v1_changed':False,'p22_v2_registered':False,
        'lowdim04a_restarted':False,'qualification_flags_changed':False,
        'selected_delta':None,'shape_update_allowed':False,'completed_job_ids':[r['id'] for r in records]})


def trimesh_barycentric(triangle,point):
    import trimesh
    return trimesh.triangles.points_to_barycentric(triangle[None],point[None])[0]


def _run(approval):
    freeze = json.loads((E/'prerun_freeze.json').read_text())
    if approval != sha(E/'prerun_freeze.json'): raise ValueError('approval must name exact freeze hash')
    frozen_files_check(freeze)
    if (E/'execution_started.json').exists(): raise ValueError('campaign already started; no rerun')
    (E/'logs').mkdir(parents=True,exist_ok=True)
    (E/'diagnostics').mkdir(parents=True,exist_ok=True)
    env = environment(freeze)
    # Metadata-only preflight precedes the irreversible campaign marker.
    checks = []
    for label in ('current','minimum'):
        job = next(j for j in freeze['jobs'] if j['environment']==label)
        output = E/'logs'/f'{label}_preflight_inventory.json'
        subprocess.run([job['python'],str(ROOT/'scripts/qualify_srcmap02.py'),'inventory','--output',str(output)],
            cwd=ROOT,env=env,check=True)
        observed = json.loads(output.read_text())
        baseline = expected_inventory(freeze,label)
        if structural_runtime(observed['runtime'])!=structural_runtime(baseline['runtime']) or observed['mesh']!=baseline['mesh']:
            raise ValueError(f'{label}: frozen preflight identity changed')
        checks.append({'environment':label,'inventory_sha256':sha(output),'pass':True})
    write_json(E/'runtime_preflight.json',{'checks':checks,'no_distance_queries':True})
    write_json(E/'execution_started.json',{'freeze_sha256':approval,'job_count':len(freeze['jobs']),'rerun_allowed':False})
    records = []
    try:
        current = next(j for j in freeze['jobs'] if j['environment']=='current')
        with (E/'logs/analytic_fixtures.log').open('x') as stream:
            subprocess.run([current['python'],str(ROOT/'scripts/qualify_srcmap02.py'),'fixtures','--output',str(E/'analytic_fixtures.json')],
                           cwd=ROOT,env=env,stdout=stream,stderr=subprocess.STDOUT,check=True)
        fixture = json.loads((E/'analytic_fixtures.json').read_text())
        if structural_runtime(fixture['runtime']) != structural_runtime(expected_inventory(freeze,'current')['runtime']):
            raise ValueError('analytic fixture runtime drift')
        if not fixture['pass']: raise ValueError('analytic sign qualification failed; no target queries allowed')
        for job in freeze['jobs']:
            output = E/'diagnostics'/f"{job['id']}.json"
            command = [job['python'],str(ROOT/'scripts/qualify_srcmap02.py'),'worker','--output',str(output),
                       '--grid',job['grid'],'--candidate',job['candidate'],'--chunk',str(job['chunk']),'--order',job['order']]
            with (E/'logs'/f"{job['id']}.log").open('x') as stream:
                subprocess.run(command,cwd=ROOT,env=env,stdout=stream,stderr=subprocess.STDOUT,check=True)
            row = json.loads(output.read_text())
            assert_run_identity(row,job,freeze)
            row.update(id=job['id'],stage=job['stage'],environment=job['environment'])
            records.append(row)
            print(job['id'],row['arrays']['phi_float64']['sha256'],flush=True)
        frozen_files_check(freeze)
        summarize(records,freeze)
    except Exception as exc:
        write_json(E/'classification.json',{'terminal_classification':'SRCMAP02_INCONCLUSIVE','complete':False,
            'exception_class':type(exc).__name__,'exception_message':str(exc),
            'completed_job_ids':[r['id'] for r in records],'rerun_allowed':False,
            'selected_delta':None,'shape_update_allowed':False,'cfd_runs':0,'kaggle_submissions':0})
        raise


def run(approval):
    try:
        _run(approval)
    except Exception as exc:
        if not (E/'classification.json').exists():
            write_json(E/'classification.json',{'terminal_classification':'SRCMAP02_INCONCLUSIVE',
                'complete':False,'exception_class':type(exc).__name__,'exception_message':str(exc),
                'execution_started':(E/'execution_started.json').exists(),
                'completed_job_ids':[],'rerun_allowed':False,'selected_delta':None,
                'shape_update_allowed':False,'cfd_runs':0,'kaggle_submissions':0})
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--approved-freeze-sha256',required=True)
    run(parser.parse_args().approved_freeze_sha256)
