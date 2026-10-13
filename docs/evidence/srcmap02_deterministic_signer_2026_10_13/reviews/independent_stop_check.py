#!/usr/bin/env python3
"""Verify the immutable SRCMAP02 stop from saved files; no campaign imports or queries."""
from pathlib import Path
import hashlib
import json
import numpy as np
ROOT = Path(__file__).resolve().parents[4]
E = Path(__file__).resolve().parents[1]

def read(path): return json.loads(path.read_text())
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def ah(a): return hashlib.sha256(a.astype(a.dtype.newbyteorder('<'),copy=False).tobytes(order='C')).hexdigest()
def check(ok, why):
    if not ok: raise ValueError(why)
def structural(runtime):
    return {k:v for k,v in runtime.items() if k not in ('numpy_legacy_random_state_sha256','trimesh_entropy_random_state')}

def verify():
    freeze = read(E/'prerun_freeze.json'); marker = read(E/'execution_started.json')
    approval = read(E/'prerun_approval.json'); terminal = read(E/'classification.json')
    frozen_hash = sha(E/'prerun_freeze.json')
    check(marker['freeze_sha256'] == approval['freeze_sha256'] == frozen_hash, 'freeze/marker/approval binding')
    check(approval['review_verdict']=='PASS', 'prerun approval')
    check(len(freeze['files'])==161, '161 frozen authority/source files')
    for record in freeze['files']:
        check(sha(ROOT/record['path'])==record['sha256'], 'frozen file drift: '+record['path'])
    check(len(freeze['jobs'])==marker['job_count']==32, 'preregistered matrix size')
    check(marker['rerun_allowed'] is False and freeze['measurement_reruns_allowed'] is False, 'no rerun declaration')
    preflight = read(E/'runtime_preflight.json'); runtimes = {}
    check(len(preflight['checks'])==2 and preflight['no_distance_queries'], 'preflight scope')
    for row in preflight['checks']:
        label = row['environment']; path = E/'logs'/f'{label}_preflight_inventory.json'
        check(sha(path)==row['inventory_sha256'] and row['pass'], 'preflight artifact identity')
        baseline = read(ROOT/freeze['runtime_inventories'][label]); actual = read(path)
        check(structural(actual['runtime'])==structural(baseline['runtime']), label+': structural runtime')
        check(actual['mesh']==baseline['mesh'], label+': static mesh identity')
        runtimes[label] = {'pass':True, 'inventory_sha256':sha(path)}
    fixture = read(E/'analytic_fixtures.json'); points = labels = zeros = hashes = 0; fixtures = []
    check(structural(fixture['runtime'])==structural(read(ROOT/freeze['runtime_inventories']['current'])['runtime']), 'analytic runtime')
    for f in fixture['fixtures']:
        vertices = np.asarray(f['vertices'],dtype='f8'); faces = np.asarray(f['faces'],dtype='i8')
        queries = np.asarray(f['queries'],dtype='f8'); expected = np.asarray(f['expected_signs'],dtype='i1')
        triangles = vertices[faces]
        normals = np.cross(triangles[:,1]-triangles[:,0],triangles[:,2]-triangles[:,0])
        # Static half-space arithmetic over saved convex fixture triangles, not library sign/distance queries.
        computed = []
        for q in queries:
            if np.any(np.all(vertices==q,axis=1)): computed.append(0); continue
            halfspaces = np.einsum('ij,ij->i', normals, q-triangles[:,0])
            computed.append(1 if np.any(halfspaces>0) else -1 if np.all(halfspaces<0) else 0)
        check(np.array_equal(np.asarray(computed,dtype='i1'),expected), f['fixture']+': independent analytic labels')
        for candidate in ('A','B'):
            r = f['candidates'][candidate]
            u = np.asarray(r['unsigned'],dtype='f8'); raw = np.asarray(r['raw_signer'],dtype='f8')
            s = np.sign(raw).astype('i1'); s[u==0]=0
            phi = s.astype('f8')*u; phi[u==0]=0.0
            check(np.isfinite(u).all() and np.isfinite(raw).all() and not (u<0).any(), 'analytic finite unsigned')
            check(not np.signbit(u[u==0]).any() and not ((raw==0)&(u>0)).any(), 'analytic zero contract')
            check(np.array_equal(s,expected) and r['signs']==expected.tolist(), 'analytic candidate labels')
            check(phi.tobytes()==np.asarray(r['combined'],dtype='f8').tobytes(), 'analytic combination')
            check(not np.signbit(phi[u==0]).any() and r['positive_zero_pass'] and r['pass'], 'analytic positive zeros')
            for name,array in [('unsigned_float64',u),('raw_signer_float64',raw),('sign_int8',s),('phi_float64',phi),('phi_float32',phi.astype('f4'))]:
                check(ah(array)==r['hashes'][name], 'analytic canonical array hash'); hashes+=1
            labels+=len(s); zeros+=int((s==0).sum())
        points+=len(queries); fixtures.append({'name':f['fixture'],'points':len(queries),'independent_labels_pass':True})
    check(points==42 and labels==84 and fixture['pass'], 'analytic fixture totals')
    first = freeze['jobs'][0]; log = E/'logs'/(first['id']+'.log'); text = log.read_text()
    check(first['id']=='B_A_repeat_1' and first['candidate']=='A' and first['grid']=='v17', 'first attempted job')
    guard = 'signer zero at strictly positive unsigned distance'
    check('ValueError: '+guard in text and 'line 74, in combine' in text and 'arrays = query(' in text, 'guard traceback')
    source = (ROOT/'scripts/qualify_srcmap02.py').read_text()
    check("np.any((raw == 0) & (unsigned > 0))" in source and "raise ValueError('"+guard+"')" in source, 'frozen literal guard')
    check(terminal['terminal_classification']=='SRCMAP02_INCONCLUSIVE' and terminal['complete'] is False, 'incomplete fail-closed classification')
    check(terminal['completed_job_ids']==[] and terminal['exception_class']=='CalledProcessError', 'no completed target jobs')
    check(first['id']+'.json' in terminal['exception_message'] and 'non-zero exit status 1' in terminal['exception_message'], 'recorded worker exit 1')
    check(terminal['rerun_allowed'] is False and terminal['selected_delta'] is None and terminal['shape_update_allowed'] is False, 'stop flags')
    check(terminal['cfd_runs']==terminal['kaggle_submissions']==0, 'solver-free result')
    check(not list((E/'diagnostics').iterdir()), 'no target job JSON/NPZ output')
    attempted = [j['id'] for j in freeze['jobs'] if (E/'logs'/(j['id']+'.log')).exists()]
    check(attempted==[first['id']], 'only first registered job attempted')
    check(not (E/'independent_numeric_check.json').exists(), 'full numeric checker not executed')
    return {'pass':True,'scope':'Independent saved-file stop audit; no campaign imports, target/fixture library queries or reruns',
        'checker_sha256':sha(Path(__file__)),'freeze_sha256':frozen_hash,'frozen_files_verified':161,
        'preflight_structural_runtime_checks':runtimes,'fixtures':fixtures,'analytic_points':points,
        'analytic_candidate_sign_labels':labels,'analytic_zero_labels':zeros,'analytic_array_hash_checks':hashes,
        'attempted_target_jobs':attempted,'attempted_count':1,'completed_target_jobs':0,'not_attempted_target_jobs':31,
        'recorded_child_worker_exit_code':1,'expected_terminal_classification':'SRCMAP02_INCONCLUSIVE',
        'first_job_log_sha256':sha(log),'no_saved_target_arrays_or_job_json':True,'full_numeric_checker_executed':False,
        'limitations':['Target raw unsigned/signer arrays were not persisted before the frozen combine guard raised.',
            'Failing node identities/counts, closest features, raw signer values and candidate target fields cannot be independently recovered.',
            'No target repeat, chunk/order, cross-environment, A/B agreement, 19-node sign or deterministic volume result is available.',
            'Preflight identity is verified; per-target post-query runtime/mesh output was not saved.',
            'Worker exit status 1 is verified from the saved CalledProcessError classification; runner outer exit is not separately captured here.']}

if __name__=='__main__':
    output = E/'independent_stop_check.json'; check(not output.exists(), 'refusing overwrite')
    result = verify()
    with output.open('x') as stream: json.dump(result,stream,indent=2,sort_keys=True,allow_nan=False); stream.write('\n')
    print(json.dumps({k:result[k] for k in ('pass','frozen_files_verified','analytic_points','analytic_candidate_sign_labels','expected_terminal_classification')}))
