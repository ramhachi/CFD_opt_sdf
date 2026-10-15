#!/usr/bin/env python3
"""Render the five GRID-02 workers (s24, s32, f48a, f48b, f16) from the committed, byte-verified inventory.  Refuses to overwrite."""
from __future__ import annotations
import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'scripts')]
from cfd_sdf import grid02_contract as C  # noqa: E402

EVIDENCE = ROOT / 'docs/evidence/grid02_trend_2026_10_16'
TEMPLATE = ROOT / 'scripts/grid02_runner_template.py'
PROJECT = 'julia/CFDSDFWaterLilyT4'
KERNEL_IDS = {k: f'ramhachi888/cfd-opt-sdf-grid02-{k}' for k in C.KERNELS}
TIMEOUT_S = {k: v['kernel_timeout_s'] for k, v in C.KERNELS.items()}  # must equal `kaggle kernels push --timeout`
# files the new job reads at run time beyond its own source and the julia src tree (waterlily_grid02_job.jl includes scripts/grid02_case.jl); extend here and nowhere else
GRID02_JOB_EXTRA_PINS = ('scripts/grid02_case.jl',)
RUNTIME_KEYS = ('W4_CANONICAL_ORIGIN_M', 'canonical_origin_m', 'GRID02_CASE', 'per_state_timeout_s', 'solver_wall_time_cap_s', 'kernel_timeout_s', 'instantiate_timeout_s', 'gpu_probe_timeout_s', 'reserve_s')


def sha(path):
    path=Path(path)
    if path.is_dir():
        files=sorted(p for p in path.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix not in ('.pyc','.pyo'))
        return hashlib.sha256(('\n'.join(f'{p.relative_to(path)}  {sha(p)}' for p in files)+'\n').encode()).hexdigest()
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inventory():
    return json.loads((EVIDENCE/'inventory.json').read_text())


def pins(kernel):
    inv=inventory(); cfg=inv['kernel_config'][kernel]
    paths={f'{PROJECT}/Project.toml',f'{PROJECT}/Manifest.toml',cfg['job'],'scripts/step01_states.py','scripts/grid01_gpu.py',
           str((EVIDENCE/'inventory.json').relative_to(ROOT)),inv['parent']['raw_path'],inv['proposal']['file'],'julia/CFDSDFWaterLily/src'}
    if cfg['job']==C.JOB_G02:
        paths|=set(GRID02_JOB_EXTRA_PINS)
    return {p:sha(ROOT/p) for p in sorted(paths)}


def verify_source(source_commit, paths):
    if not re.fullmatch(r'[a-f0-9]{40}',source_commit):
        raise ValueError('source commit must be a full lowercase SHA')
    for rel in sorted(paths):
        path=ROOT/rel
        names=sorted(str(p.relative_to(ROOT)) for p in path.rglob('*') if p.is_file()) if path.is_dir() else [rel]
        for name in names:
            blob=subprocess.run(['git','-C',str(ROOT),'show',f'{source_commit}:{name}'],capture_output=True,check=True).stdout
            if hashlib.sha256(blob).hexdigest()!=sha(ROOT/name):
                raise ValueError(f'committed source differs: {name}')
        if path.is_dir():
            tracked=subprocess.check_output(['git','-C',str(ROOT),'ls-tree','-r','--name-only',source_commit,'--',rel],text=True).splitlines()
            if names!=sorted(tracked):
                raise ValueError(f'source tree members differ: {rel}')


def render(source_commit,kernel):
    inv=inventory(); cfg=inv['kernel_config'][kernel]
    if cfg['kernel_id']!=KERNEL_IDS[kernel] or inv['kernels'][kernel]!=list(C.KERNELS[kernel]['states']):
        raise ValueError('the inventory differs from the registered kernel plan')
    substitutions={'PIN_KERNEL':kernel,'PIN_KERNEL_ID':KERNEL_IDS[kernel],'PIN_SOURCE_COMMIT':source_commit,'PIN_CASE_ID':cfg['case_id'],'PIN_JOB':cfg['job'],
                   'PIN_BASELINE_RAW':inv['parent']['raw_path'],'PIN_PROPOSAL_RAW':inv['proposal']['file']}
    text=TEMPLATE.read_text()
    # Replace quoted constants before the unquoted placeholders.
    for key,value in substitutions.items():
        old=json.dumps(key)
        if text.count(old)!=1:
            raise ValueError(f'runner placeholder count differs: {key}')
        text=text.replace(old,json.dumps(value))
    for old,new in (('PINS = PIN_PINS','PINS = '+repr(pins(kernel))),('CONFIG = PIN_CONFIG','CONFIG = '+repr({k:cfg[k] for k in RUNTIME_KEYS})),
                    ('EXPECTED_NAMES = PIN_NAMES','EXPECTED_NAMES = '+repr(inv['kernels'][kernel]))):
        if text.count(old)!=1:
            raise ValueError(f'runner placeholder count differs: {old}')
        text=text.replace(old,new)
    if 'PIN_' in text:
        raise ValueError('unresolved runner placeholder')
    compile(text,'runner.py','exec')
    return text


def metadata(kernel):
    slug=KERNEL_IDS[kernel].split('/')[1]
    return {'id':KERNEL_IDS[kernel],'title':slug,'code_file':'runner.py','language':'python','kernel_type':'script',
            'is_private':True,'enable_gpu':True,'enable_internet':True,'machine_shape':'NvidiaTeslaT4',
            'dataset_sources':[],'competition_sources':[],'kernel_sources':[],'model_sources':[]}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source-commit',required=True);args=p.parse_args()
    for k in KERNEL_IDS:
        verify_source(args.source_commit,set(pins(k))|{str(TEMPLATE.relative_to(ROOT))})
        if (ROOT/f'infra/kaggle/kernel_grid02_{k}').exists():
            raise SystemExit(f'refusing to overwrite rendered worker: kernel_grid02_{k}')
    for k in KERNEL_IDS:
        d=ROOT/f'infra/kaggle/kernel_grid02_{k}'
        d.mkdir(parents=True);(d/'runner.py').write_text(render(args.source_commit,k))
        (d/'kernel-metadata.json').write_text(json.dumps(metadata(k),sort_keys=True,indent=2)+'\n')

if __name__=='__main__':
    main()
