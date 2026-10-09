#!/usr/bin/env python3
"""Capture authenticated provider absence, then freeze reviewed LOWDIM-03 bytes."""
from __future__ import annotations
import argparse
import csv
import datetime
import io
import json
import re
import subprocess
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'src')]
import build_lowdim03_kernel as K
from build_grid01_inputs import canonical_json
E=K.EVIDENCE
IDENTITY=E/'identity_free_check.json'
PARENT='29fd60dd7b985e79b907700ab5600376b10ce230'


def command(args):
    r=subprocess.run(['kaggle',*args],capture_output=True,text=True)
    return {'command':['kaggle',*args],'exit_code':r.returncode,'stdout':r.stdout,'stderr':r.stderr}


def capture_identity():
    if IDENTITY.exists():
        raise ValueError('refusing to overwrite identity preflight')
    record={'kind':'lowdim03_authenticated_identity_free_check','owner':'ramhachi888',
            'captured_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'kernel_ids':list(K.KERNEL_IDS.values()),'listings':{},'positive_controls':{}}
    targets={ref.split('/')[1] for ref in K.KERNEL_IDS.values()}
    for kind in ('kernels','datasets'):
        pages=[];rows=[]
        for page in range(1,101):
            result=command([kind,'list','--mine','--page-size','100','--page',str(page),'--csv'])
            if result['exit_code'] or re.search(r'403|forbidden|unauthorized',result['stdout']+result['stderr'],re.I):
                raise ValueError(f'{kind} authenticated listing failed')
            parsed=list(csv.DictReader(io.StringIO(result['stdout'])))
            if result['stdout'].strip() in ('Not found','No datasets found','No kernels found',''):
                parsed=[]
            if any(not row.get('ref','').startswith('ramhachi888/') for row in parsed):
                raise ValueError(f'{kind} listing returned a different owner or malformed CSV')
            pages.append({**result,'rows':parsed});rows.extend(parsed)
            if len(parsed)<100:
                break
        else:
            raise ValueError('listing pagination limit reached')
        if not rows or len({r['ref'] for r in rows})!=len(rows):
            raise ValueError('positive owned listing or unique rows missing')
        taken={r['ref'].split('/')[1] for r in rows}|{re.sub(r'[^a-z0-9]+','-',r.get('title','').lower()).strip('-') for r in rows}
        if targets & taken:
            raise ValueError(f'{kind} provider identity collision: {targets & taken}')
        ref=rows[0]['ref']
        control=command([kind,'status',ref] if kind=='kernels' else [kind,'files',ref,'--csv'])
        if control['exit_code'] or not control['stdout'].strip() or re.search(r'403|forbidden|unauthorized',control['stdout']+control['stderr'],re.I):
            raise ValueError('existing-resource positive access control failed')
        record['listings'][kind]={'pages':pages,'rows':rows,'complete':True}
        record['positive_controls'][kind]=control
    record['all_free']=True
    IDENTITY.write_bytes(canonical_json(record));IDENTITY.with_suffix('.json.sha256').write_text(K.sha(IDENTITY)+'\n')
    print('authenticated identity absence captured',K.sha(IDENTITY))


def require_identity(record, *, as_of=None):
    if record.get('all_free') is not True or record.get('kernel_ids')!=list(K.KERNEL_IDS.values()) or record.get('owner')!='ramhachi888':
        raise ValueError('identity preflight mismatch')
    age=((as_of or datetime.datetime.now(datetime.timezone.utc))-datetime.datetime.fromisoformat(record['captured_utc'])).total_seconds()
    if not 0<=age<=86400 or IDENTITY.with_suffix('.json.sha256').read_text().strip()!=K.sha(IDENTITY):
        raise ValueError('stale identity proof or sidecar mismatch')
    targets={ref.split('/')[1] for ref in K.KERNEL_IDS.values()}
    for kind in ('kernels','datasets'):
        listing=record['listings'][kind]; rows=listing['rows'];pages=listing['pages']
        if listing['complete'] is not True or not rows or not pages or len(pages[-1]['rows'])>=100:
            raise ValueError('incomplete provider listing')
        if [r for page in pages for r in page['rows']]!=rows or len({r['ref'] for r in rows})!=len(rows):
            raise ValueError('provider page mismatch')
        for i,page in enumerate(pages,1):
            if page['command']!=['kaggle',kind,'list','--mine','--page-size','100','--page',str(i),'--csv'] or page['exit_code']!=0:
                raise ValueError('provider listing command mismatch')
            if list(csv.DictReader(io.StringIO(page['stdout'])))!=page['rows'] and page['stdout'].strip() not in ('Not found','No datasets found','No kernels found',''):
                raise ValueError('provider CSV mismatch')
        taken={r['ref'].split('/')[1] for r in rows}|{re.sub(r'[^a-z0-9]+','-',r.get('title','').lower()).strip('-') for r in rows}
        if targets&taken or any(not r['ref'].startswith('ramhachi888/') for r in rows):
            raise ValueError('provider collision or owner mismatch')
        control=record['positive_controls'][kind]
        ref=control['command'][3]
        expected=['kaggle',kind,'status',ref] if kind=='kernels' else ['kaggle',kind,'files',ref,'--csv']
        if control['command']!=expected or ref not in {r['ref'] for r in rows} or control['exit_code']!=0 or not control['stdout'].strip():
            raise ValueError('provider access control mismatch')


def freeze(source_commit):
    import analyze_lowdim03 as A
    target=E/'prerun_freeze.json'
    if target.exists():
        raise ValueError('refusing to overwrite an immutable freeze')
    inv=json.loads((E/'inventory.json').read_text());proof=json.loads(IDENTITY.read_text());require_identity(proof)
    files=set(A.required_file_paths(inv))|{str(IDENTITY.relative_to(ROOT)),str(IDENTITY.with_suffix('.json.sha256').relative_to(ROOT)),
                                      str((E/'prerun_note.md').relative_to(ROOT))}
    if subprocess.run(['git','-C',str(ROOT),'status','--porcelain','--untracked-files=no'],capture_output=True,text=True).stdout.strip():
        raise ValueError('tracked files have uncommitted changes; freeze only committed reviewed bytes')
    if not subprocess.run(['git','-C',str(ROOT),'branch','-r','--contains',source_commit],capture_output=True,text=True).stdout.strip():
        raise ValueError('the source commit is not on a remote branch; push it before freezing (the Kaggle runner fetches it from GitHub)')
    K.verify_source(source_commit,files)
    if subprocess.run(['git','-C',str(ROOT),'merge-base','--is-ancestor',PARENT,source_commit]).returncode:
        raise ValueError('source does not descend from the approved integration checkpoint')
    runtimes={}
    for k in K.KERNEL_IDS:
        path=ROOT/f'infra/kaggle/kernel_lowdim03_{k}/runner.py'
        if path.read_text()!=K.render(source_commit,k):
            raise ValueError('rendered worker differs from reviewed source')
        meta=path.with_name('kernel-metadata.json')
        if json.loads(meta.read_text())!=K.metadata(k):
            raise ValueError('kernel metadata mismatch')
        runtimes[k]={'kernel_id':K.KERNEL_IDS[k],'case_id':inv['grids'][k]['case_id'],'runner_sha256':K.sha(path),'metadata_sha256':K.sha(meta),
                     'machine_shape':'NvidiaTeslaT4','kernel_timeout_s':10800,'timeout_s':10800,'per_state_timeout_s':900,'solver_wall_time_cap_s':6300,
                     'instantiate_timeout_s':2400,'gpu_probe_timeout_s':300,'reserve_s':300,'julia_threads':1,
                     'cuda_device_order':'PCI_BUS_ID','cuda_visible_devices':'0','selected_gpu_physical_index':0,'used_gpu_count':1,'dataset_sources':[]}
    result={'kind':'lowdim03_dual_grid_primal_prerun_freeze','frozen_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'source_commit':source_commit,'parent_integration_commit':PARENT,'inventory_sha256':K.sha(E/'inventory.json'),
            'file_hashes':{p:K.sha(ROOT/p) for p in sorted(files)},'pins':{k:K.pins(k) for k in K.KERNEL_IDS},'runtime':runtimes,'identity_free_check':proof,
            'rules':{'downforce_gain_strictly_greater_than_n':3e-5,'drag_change_at_most_n':0.0,'small_drag_margin_n':3e-5,
                     'selection':'max min actual downforce gain over both grids; exact ties choose smaller step','reverse_controls':'diagnostic only; excluded from selection'},
            'qualification_flags':{k:False for k in ('fd_oracle','field_gradient','reverse','optimizer','topology','shape_update_allowed')},
            'selected_delta':None,'reinitialization':'none','known_before_run':'All STEP-01, LOWDIM-01/02A and GRID-01 results, and six-state geometry preflight were visible; not blind validation.',
            'prohibitions':['no automatic resubmission or repair after terminal/integrity failure','no secant rebuild/second iteration/basis expansion/reinitialization/Stage B/#30 supersession']}
    target.write_bytes(canonical_json(result));target.with_suffix('.json.sha256').write_text(K.sha(target)+'\n');print('freeze',K.sha(target))


def main():
    p=argparse.ArgumentParser(description=__doc__);g=p.add_mutually_exclusive_group(required=True)
    g.add_argument('--check-identities',action='store_true');g.add_argument('--source-commit');args=p.parse_args()
    capture_identity() if args.check_identities else freeze(args.source_commit)

if __name__=='__main__':
    main()
