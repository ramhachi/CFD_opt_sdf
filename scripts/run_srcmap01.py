#!/usr/bin/env python3
"""Execute exactly the frozen SRCMAP-01 job list once; aggregate strict evidence."""
from __future__ import annotations
import argparse
import itertools
import json
import os
from pathlib import Path
import subprocess
import sys
import numpy as np
from diagnose_srcmap01 import ROOT,E,OLD,sha,write_json,strict,classify

def structural_runtime(runtime):
    # Entropy is the instrumented algorithm behavior; all runtime structure is fixed.
    return {k:v for k,v in runtime.items() if k not in ('numpy_legacy_random_state_sha256','trimesh_entropy_random_state')}

def assert_run_identity(row,job,freeze):
    baseline=json.loads((E/('alternative_runtime_inventory.json' if job['stage']=='G' else 'runtime_inventory.json')).read_text())
    expected=structural_runtime(baseline['runtime'])
    for key in ('runtime_before','runtime_after'):
        if structural_runtime(row[key])!=expected:raise ValueError(f"{job['id']}: structural runtime differs from frozen inventory ({key})")
    if any('metadata_error' in event for event in row['events']):raise ValueError(f"{job['id']}: instrumentation metadata failure")
    if row['mesh']!=baseline['mesh']:raise ValueError(f"{job['id']}: loaded mesh/backend differs from frozen inventory")
    if row['point_coordinates_c_little_sha256']!=freeze['point_coordinate_hashes'][job['grid']]:
        raise ValueError(f"{job['id']}: node coordinates differ from genesis coordinate freeze")
    for result_key,job_key in [('grid','grid'),('chunk_size','chunk'),('ordering','order'),('mode','mode')]:
        if row[result_key]!=job[job_key]:raise ValueError(f"{job['id']}: job contract drift")

def classification_inputs(records,local_direction_sensitive):
    groups={}
    for row in records:
        key=('minimum' if row['stage']=='G' else 'current',row['grid'],row['chunk_size'],row['ordering'],row['mode'])
        groups.setdefault(key,[]).append(row)
    comparisons=[]
    for key,rows in groups.items():
        for a,b in itertools.combinations(rows,2):
            comparisons.append({'group':list(key),'a':a['id'],'b':b['id'],
                                'float32':strict(a['_float32'],b['_float32']),
                                'float64':strict(a['_float64'],b['_float64'])})
    same=all(p['float32']['bit_equal'] and p['float64']['bit_equal'] for p in comparisons)
    a=[r for r in records if r['stage']=='A'];g=[r for r in records if r['stage']=='G']
    exact=all(r['comparison_float32_registered']['bit_equal'] for r in a)
    perturb=all(r['comparison_float32_registered']['bit_equal'] for r in records if r['stage'] in ('B','C'))
    current=[r for r in a if r['grid']=='v17']
    curmatch=all(r['comparison_float32_registered']['bit_equal'] for r in current)
    altmatch=all(r['comparison_float32_registered']['bit_equal'] for r in g)
    environment=same and curmatch!=altmatch and (curmatch or altmatch)
    # Frozen bundle evidence is permitted; individual dependency attribution remains UNKNOWN.
    terminal=classify(same,exact,perturb,environment_match=environment,local_direction_sensitive=local_direction_sensitive)
    return {'terminal_classification':terminal,'same_condition_pairwise':comparisons,
            'all_repeated_groups_float32_and_float64_exact':same,'current_all_v16_v17_registered_exact':exact,
            'chunk_order_all_registered_exact':perturb,'environment_bundle_dependence_demonstrated':environment,
            'local_fixed_direction_sensitive':local_direction_sensitive}

def frozen_files_check(freeze):
    for record in freeze['files']:
        if sha(ROOT/record['path'])!=record['sha256']:raise ValueError(f"frozen input changed: {record['path']}")

def runtime_preflight(freeze):
    checks=[]
    for stage,label in [('A','current'),('G','minimum')]:
        job=next(j for j in freeze['jobs'] if j['stage']==stage)
        output=E/'logs'/f'{label}_preflight_inventory.json'
        env=dict(os.environ);env['PYTHONHASHSEED']='0'
        subprocess.run([job['python'],str(ROOT/'scripts/diagnose_srcmap01.py'),'inventory','--output',str(output)],cwd=ROOT,env=env,check=True)
        observed=json.loads(output.read_text())
        baseline=json.loads((E/('alternative_runtime_inventory.json' if stage=='G' else 'runtime_inventory.json')).read_text())
        if structural_runtime(observed['runtime'])!=structural_runtime(baseline['runtime']) or observed['mesh']!=baseline['mesh']:
            raise ValueError(f'{label}: inventory-only preflight differs from frozen runtime')
        checks.append({'environment':label,'python':job['python'],'structural_identity':True,'inventory_sha256':sha(output)})
    write_json(E/'runtime_preflight.json',{'no_distance_queries':True,'checks':checks})

def run(approval):
    freeze=json.loads((E/'prerun_freeze.json').read_text())
    if approval!=sha(E/'prerun_freeze.json'):raise ValueError('approval must name exact freeze SHA')
    frozen_files_check(freeze)
    if (E/'execution_started.json').exists():raise ValueError('campaign already started; no rerun')
    (E/'logs').mkdir(parents=True,exist_ok=True);(E/'diagnostics').mkdir(parents=True,exist_ok=True)
    runtime_preflight(freeze)
    write_json(E/'execution_started.json',{'freeze_sha256':approval,'job_count':len(freeze['jobs']),'rerun_allowed':False})
    records=[]
    try:
        for job in freeze['jobs']:
            output=E/'diagnostics'/f"{job['id']}.json"
            command=[job['python'],str(ROOT/'scripts/diagnose_srcmap01.py'),'worker','--output',str(output),'--grid',job['grid'],
                     '--chunk',str(job['chunk']),'--order',job['order'],'--mode',job['mode']]
            env=dict(os.environ);env['PYTHONHASHSEED']='0'
            log=E/'logs'/f"{job['id']}.log"
            with log.open('x') as stream:result=subprocess.run(command,cwd=ROOT,env=env,stdout=stream,stderr=subprocess.STDOUT)
            if result.returncode:raise RuntimeError(f"{job['id']} failed with exit {result.returncode}; see {log}")
            row=json.loads(output.read_text());assert_run_identity(row,job,freeze);row['id']=job['id'];row['stage']=job['stage'];records.append(row)
            print(job['id'],row['comparison_float32_registered'],flush=True)
        with (E/'logs/problem_nodes.log').open('x') as stream:
            result=subprocess.run([freeze['jobs'][0]['python'],str(ROOT/'scripts/diagnose_srcmap01.py'),'nodes','--output',str(E/'problem_nodes.json')],
                                  cwd=ROOT,env=env,stdout=stream,stderr=subprocess.STDOUT)
        if result.returncode:raise RuntimeError('Stage E failed; see problem_nodes.log')
        frozen_files_check(freeze)
        summarize(records,freeze)
    except Exception as exc:
        write_json(E/'classification.json',{'terminal_classification':'SOURCE_MAPPING_UNRESOLVED','complete':False,
                    'unexpected_exception_class':type(exc).__name__,'unexpected_exception_message':str(exc),
                    'completed_job_ids':[r['id'] for r in records],'no_retry':True})
        raise

def summarize(records,freeze):
    byid={r['id']:r for r in records}
    def fields(r):return np.load(E/'diagnostics'/f"{r['id']}.npz")
    def pairs(rows):
        return [{'a':a['id'],'b':b['id'],'float32':strict(fields(a)['phi_float32'],fields(b)['phi_float32']),
                 'float64':strict(fields(a)['phi_float64'],fields(b)['phi_float64'])} for a,b in itertools.combinations(rows,2)]
    def concise(row):return {k:row[k] for k in ('id','grid','chunk_size','ordering','mode','phi_float32','phi_float64','comparison_float32_registered','comparison_float64_to_registered_promoted','fallback_invoked','events')}
    a=[r for r in records if r['stage']=='A'];pairwise={g:pairs([r for r in a if r['grid']==g]) for g in ('v16','v17')}
    write_json(E/'repeatability.json',{'runs':[concise(r) for r in a],'pairwise':pairwise,'independent_processes':True})
    for stage,name in [('B','chunk_dependence'),('C','ordering_dependence'),('D','backend_path_comparison'),('G','dependency_sensitivity')]:
        rows=[r for r in records if r['stage']==stage]
        write_json(E/f'{name}.json',{'runs':[concise(r) for r in rows],'pairwise':pairs(rows)})
    reference=np.load(OLD/'inputs/v17_baseline.npz')['phi'];distribution=[]
    for r in records:
        if r['grid']!='v17':continue
        f=fields(r);a64=f['phi_float64'];a32=f['phi_float32']
        path=E/'diagnostics'/f"{r['id']}_difference.npz"
        if path.exists():raise ValueError('refusing difference NPZ overwrite')
        np.savez_compressed(path,delta_float64_vs_registered_promoted=a64-reference.astype('f8'),delta_float32_vs_registered=a32.astype('f8')-reference,
                            different_bits_float32=a32.view('<u4')!=reference.view('<u4'),different_bits_float64_vs_registered_promoted=a64.view('<u8')!=reference.astype('<f8').view('<u8'),sign_difference=np.signbit(a32)!=np.signbit(reference))
        distribution.append({'id':r['id'],'float32':r['comparison_float32_registered'],'float64_vs_registered_promoted':r['comparison_float64_to_registered_promoted'],
                             'difference_npz':str(path.relative_to(ROOT)),'difference_npz_sha256':sha(path),
                             'differing_indices':np.argwhere(a32.view('<u4')!=reference.view('<u4')).tolist()})
    write_json(E/'field_difference_summary.json',{'runs':distribution,'float64_reference_limitation':'no retained historical Float64 exists; comparison is to exact promotion of retained Float32'})
    local=json.loads((E/'problem_nodes.json').read_text())
    expected=json.loads((E/'runtime_inventory.json').read_text())
    for key in ('runtime_before','runtime_after'):
        if structural_runtime(local[key])!=structural_runtime(expected['runtime']):raise ValueError('local E runtime drift')
    if local['mesh']!=expected['mesh']:raise ValueError('local E mesh drift')
    direction_results=[np.asarray(c['direct_project_float64'],dtype='f8') for c in local['fixed_ray_retry_direction_diagnostic']]
    local_sensitive=any(not strict(a,b)['bit_equal'] for a,b in itertools.combinations(direction_results,2)) or len({tuple(c['contains']) for c in local['fixed_ray_retry_direction_diagnostic']})>1
    if any('metadata_error' in event for node in local['nodes'] for key in ('nominal_direct_events','nominal_fallback_events') for event in node[key]):raise ValueError('local E instrumentation metadata failure')
    classifier_rows=[]
    for r in records:
        f=fields(r);classifier_rows.append(dict(r,_float32=f['phi_float32'],_float64=f['phi_float64']))
    decision=classification_inputs(classifier_rows,local_sensitive)
    cur=json.loads((E/'runtime_inventory.json').read_text());alt=json.loads((E/'alternative_runtime_inventory.json').read_text())
    bundle_differences=[{'key':k,'current':v,'minimum':alt['runtime'].get(k)} for k,v in structural_runtime(cur['runtime']).items() if v!=structural_runtime(alt['runtime']).get(k)]
    mesh_differences=[{'key':k,'current':v,'minimum':alt['mesh'].get(k)} for k,v in cur['mesh'].items() if v!=alt['mesh'].get(k)]
    frozen_files_check(freeze)
    path_signatures=[{'id':r['id'],'fallback_invoked':r['fallback_invoked'],'try_successes':sum(e['call']=='try_signed_distance' and e.get('success',False) for e in r['events']),'exceptions':[{'call':e['call'],'class':e['exception_class'],'message':e['exception_message']} for e in r['events'] if 'exception_class' in e],'random_retry_draw_count':sum(e['call'] in ('random_retry_draw','legacy_random_retry_draw') for e in r['events']),'ray_recursive_query_count':sum(e['call']=='ray_util_contains_points' for e in r['events'])} for r in records]
    write_json(E/'classification.json',dict(decision,complete=True,path_signatures=path_signatures,frozen_precedence=freeze['classification_precedence'],
                all_runs_structural_runtime_source_and_loaded_mesh_identity_verified=True,
                all_frozen_input_hashes_verified_after_measurements=True,
                environment_bundle_differences=bundle_differences,loaded_mesh_environment_differences=mesh_differences,
                dependency_localization='UNKNOWN; several dependency versions change together; only exact frozen bundle dependence eligible',
                historical_path_divergence_proven=False,historical_paths='UNKNOWN; direct/fallback disagreement alone cannot prove historical divergence',
                historical_cause_resolved=False,finite_run_limit='invariance only over the fixed observed runs; finite repetitions do not prove universal determinism',
                evidence_scope='frozen source-mapping diagnostic only; no volume/physical qualification',
                cfd_runs=0,kaggle_submissions=0,p22_v1_changed=False,p22_v2_registered=False,lowdim04a_restarted=False,
                selected_delta=None,shape_update_allowed=False,qualification_flags_changed=False))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--approved-freeze-sha256',required=True);run(p.parse_args().approved_freeze_sha256)
