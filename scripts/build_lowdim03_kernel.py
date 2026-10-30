#!/usr/bin/env python3
"""Render the two LOWDIM-03 workers from committed, byte-verified inputs."""
from __future__ import annotations
import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / 'docs/evidence/lowdim03_dual_grid_primal_2026_10_10'
TEMPLATE = ROOT / 'scripts/lowdim03_runner_template.py'
PROJECT = 'julia/CFDSDFWaterLilyT4'
KERNEL_IDS = {k:f'ramhachi888/cfd-opt-sdf-lowdim03-{k}' for k in ('a','b')}
TIMEOUT_S = 10800


def sha(path):
    path=Path(path)
    if path.is_dir():
        files=sorted(p for p in path.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix not in ('.pyc','.pyo'))
        return hashlib.sha256(('\n'.join(f'{p.relative_to(path)}  {sha(p)}' for p in files)+'\n').encode()).hexdigest()
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pins(kernel):
    inv=json.loads((EVIDENCE/'inventory.json').read_text())
    paths={f'{PROJECT}/Project.toml',f'{PROJECT}/Manifest.toml',inv['grids'][kernel]['job'],
           'scripts/step01_states.py','scripts/lowdim01_states.py','scripts/lowdim03_states.py','scripts/grid01_gpu.py',
           str((EVIDENCE/'inventory.json').relative_to(ROOT)),inv['baseline']['path'],inv['proposal']['file'],
           inv['grids'][kernel]['baseline_reference']['forces_csv_path'],'julia/CFDSDFWaterLily/src'}
    paths.update(r['path'] for r in inv['directions'].values())
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
    inv=json.loads((EVIDENCE/'inventory.json').read_text())
    substitutions={'PIN_KERNEL':kernel,'PIN_KERNEL_ID':KERNEL_IDS[kernel],'PIN_SOURCE_COMMIT':source_commit,
                   'PIN_CASE_ID':inv['grids'][kernel]['case_id'],'PIN_JOB':inv['grids'][kernel]['job'],
                   'PIN_BASELINE_FORCE_CSV':inv['grids'][kernel]['baseline_reference']['forces_csv_path']}
    text=TEMPLATE.read_text()
    # Replace quoted constants before the unquoted dictionary placeholder.
    for key,value in substitutions.items():
        old=json.dumps(key)
        if text.count(old)!=1:
            raise ValueError(f'runner placeholder count differs: {key}')
        text=text.replace(old,json.dumps(value))
    text=text.replace('PINS = PIN_PINS','PINS = '+repr(pins(kernel)))
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
        d=ROOT/f'infra/kaggle/kernel_lowdim03_{k}'
        if d.exists():
            raise SystemExit(f'refusing to overwrite rendered worker: {d}')
        d.mkdir(parents=True);(d/'runner.py').write_text(render(args.source_commit,k))
        (d/'kernel-metadata.json').write_text(json.dumps(metadata(k),sort_keys=True,indent=2)+'\n')

if __name__=='__main__':
    main()
