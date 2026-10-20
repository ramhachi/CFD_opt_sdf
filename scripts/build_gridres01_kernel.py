#!/usr/bin/env python3
"""Render a GRIDRES-01 worker (one finer grid per kernel) from committed, byte-verified inputs.  Copy-adapted from build_opt01b_kernel (never edited)."""
from __future__ import annotations
import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / 'docs/evidence/gridres01_2026_10_20'
TEMPLATE = ROOT / 'scripts/gridres01_runner_template.py'
PROJECT = 'julia/CFDSDFWaterLilyT4'
sys.path.insert(0, str(ROOT / 'scripts'))
import gridres01_states as G

KERNEL_IDS = {case: f'ramhachi888/cfd-opt-sdf-gridres01-{spec["kernel_suffix"]}' for case, spec in G.GRIDS.items()}


def sha(path):
    path = Path(path)
    if path.is_dir():
        files = sorted(p for p in path.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix not in ('.pyc', '.pyo'))
        return hashlib.sha256(('\n'.join(f'{p.relative_to(path)}  {sha(p)}' for p in files) + '\n').encode()).hexdigest()
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pins(case):
    inv = json.loads((EVIDENCE / 'inventory.json').read_text())
    paths = {f'{PROJECT}/Project.toml', f'{PROJECT}/Manifest.toml', inv['grids'][case]['job'], 'scripts/step01_states.py', 'scripts/gridres01_states.py', 'scripts/grid01_gpu.py',
             str((EVIDENCE / 'inventory.json').relative_to(ROOT)), inv['parent']['raw_path'], inv['proposal']['file'], 'julia/CFDSDFWaterLily/src'}
    return {p: sha(ROOT / p) for p in sorted(paths)}


def verify_source(source_commit, paths):
    if not re.fullmatch(r'[a-f0-9]{40}', source_commit):
        raise ValueError('source commit must be a full lowercase SHA')
    for rel in sorted(paths):
        path = ROOT / rel
        names = sorted(str(p.relative_to(ROOT)) for p in path.rglob('*') if p.is_file()) if path.is_dir() else [rel]
        for name in names:
            blob = subprocess.run(['git', '-C', str(ROOT), 'show', f'{source_commit}:{name}'], capture_output=True, check=True).stdout
            if hashlib.sha256(blob).hexdigest() != sha(ROOT / name):
                raise ValueError(f'committed source differs: {name}')
        if path.is_dir():
            tracked = subprocess.check_output(['git', '-C', str(ROOT), 'ls-tree', '-r', '--name-only', source_commit, '--', rel], text=True).splitlines()
            if names != sorted(tracked):
                raise ValueError(f'source tree members differ: {rel}')


def render(source_commit, case):
    inv = json.loads((EVIDENCE / 'inventory.json').read_text())
    grid = inv['grids'][case]
    substitutions = {'PIN_KERNEL': case, 'PIN_KERNEL_ID': KERNEL_IDS[case], 'PIN_SOURCE_COMMIT': source_commit, 'PIN_CASE_ID': case, 'PIN_JOB': grid['job'], 'PIN_CELLS': grid['cells'],
                     'PIN_PER_STATE_TIMEOUT_S': grid['limits']['per_state_timeout_s'], 'PIN_SOLVER_WALL_TIME_CAP_S': grid['limits']['solver_wall_time_cap_s'],
                     'PIN_KERNEL_TIMEOUT_S': grid['limits']['kernel_timeout_s']}
    text = TEMPLATE.read_text()
    for key, value in substitutions.items():  # quoted constants first, then the unquoted dictionary placeholder
        old = json.dumps(key)
        if text.count(old) != 1:
            raise ValueError(f'runner placeholder count differs: {key}')
        text = text.replace(old, json.dumps(value))
    text = text.replace('PINS = PIN_PINS', 'PINS = ' + repr(pins(case)))
    if 'PIN_' in text:
        raise ValueError('unresolved runner placeholder')
    compile(text, 'runner.py', 'exec')
    return text


def metadata(case):
    slug = KERNEL_IDS[case].split('/')[1]
    return {'id': KERNEL_IDS[case], 'title': slug, 'code_file': 'runner.py', 'language': 'python', 'kernel_type': 'script', 'is_private': True, 'enable_gpu': True, 'enable_internet': True,
            'machine_shape': 'NvidiaTeslaT4', 'dataset_sources': [], 'competition_sources': [], 'kernel_sources': [], 'model_sources': []}


def kernel_dir(case):
    return ROOT / f'infra/kaggle/kernel_gridres01_{G.GRIDS[case]["kernel_suffix"]}'


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source-commit', required=True)
    p.add_argument('--grid', required=True, choices=sorted(G.GRIDS))
    args = p.parse_args()
    verify_source(args.source_commit, set(pins(args.grid)) | {str(TEMPLATE.relative_to(ROOT))})
    d = kernel_dir(args.grid)
    if d.exists():
        raise SystemExit(f'refusing to overwrite rendered worker: {d}')
    d.mkdir(parents=True)
    (d / 'runner.py').write_text(render(args.source_commit, args.grid))
    (d / 'kernel-metadata.json').write_text(json.dumps(metadata(args.grid), sort_keys=True, indent=2) + '\n')


if __name__ == '__main__':
    main()
