#!/usr/bin/env python3
"""Capture authenticated provider absence for one GRIDRES-01 kernel, then freeze the reviewed bytes of that kernel (copy-adapted from freeze_opt01b, never edited).

--check-identities --grid G: read-only Kaggle listings (kernels and datasets) show the kernel id is free.  --source-commit C --grid G: write prerun_freeze_G.json.
"""
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
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'src')]
import analyze_gridres01 as A
import build_gridres01_kernel as K
import gridres01_states as G
from build_grid01_inputs import canonical_json
E = K.EVIDENCE


def identity_path(case):
    return E / f'identity_free_check_{case}.json'


def command(args):
    r = subprocess.run(['kaggle', *args], capture_output=True, text=True)
    return {'command': ['kaggle', *args], 'exit_code': r.returncode, 'stdout': r.stdout, 'stderr': r.stderr}


def capture_identity(case):
    path = identity_path(case)
    if path.exists():
        raise ValueError('refusing to overwrite identity preflight')
    record = {'kind': 'gridres01_authenticated_identity_free_check', 'owner': 'ramhachi888', 'captured_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'kernel_ids': [K.KERNEL_IDS[case]], 'listings': {}, 'positive_controls': {}}
    targets = {K.KERNEL_IDS[case].split('/')[1]}
    for kind in ('kernels', 'datasets'):
        pages, rows = [], []
        for page in range(1, 101):
            result = command([kind, 'list', '--mine', '--page-size', '100', '--page', str(page), '--csv'])
            if result['exit_code'] or re.search(r'403|forbidden|unauthorized', result['stdout'] + result['stderr'], re.I):
                raise ValueError(f'{kind} authenticated listing failed')
            parsed = list(csv.DictReader(io.StringIO(result['stdout'])))
            if result['stdout'].strip() in ('Not found', 'No datasets found', 'No kernels found', ''):
                parsed = []
            if any(not row.get('ref', '').startswith('ramhachi888/') for row in parsed):
                raise ValueError(f'{kind} listing returned a different owner or malformed CSV')
            pages.append({**result, 'rows': parsed}); rows.extend(parsed)
            if len(parsed) < 100:
                break
        else:
            raise ValueError('listing pagination limit reached')
        if not rows or len({r['ref'] for r in rows}) != len(rows):
            raise ValueError('positive owned listing or unique rows missing')
        taken = {r['ref'].split('/')[1] for r in rows} | {re.sub(r'[^a-z0-9]+', '-', r.get('title', '').lower()).strip('-') for r in rows}
        if targets & taken:
            raise ValueError(f'{kind} provider identity collision: {targets & taken}')
        ref = rows[0]['ref']
        control = command([kind, 'status', ref] if kind == 'kernels' else [kind, 'files', ref, '--csv'])
        if control['exit_code'] or not control['stdout'].strip() or re.search(r'403|forbidden|unauthorized', control['stdout'] + control['stderr'], re.I):
            raise ValueError('existing-resource positive access control failed')
        record['listings'][kind] = {'pages': pages, 'rows': rows, 'complete': True}
        record['positive_controls'][kind] = control
    record['all_free'] = True
    path.write_bytes(canonical_json(record)); path.with_suffix('.json.sha256').write_text(K.sha(path) + '\n')
    print('authenticated identity absence captured', K.sha(path))


def require_identity(case, record, *, as_of=None):
    path = identity_path(case)
    if record.get('all_free') is not True or record.get('kernel_ids') != [K.KERNEL_IDS[case]] or record.get('owner') != 'ramhachi888':
        raise ValueError('identity preflight mismatch')
    age = ((as_of or datetime.datetime.now(datetime.timezone.utc)) - datetime.datetime.fromisoformat(record['captured_utc'])).total_seconds()
    if not 0 <= age <= 86400 or path.with_suffix('.json.sha256').read_text().strip() != K.sha(path):
        raise ValueError('stale identity proof or sidecar mismatch')
    targets = {K.KERNEL_IDS[case].split('/')[1]}
    for kind in ('kernels', 'datasets'):
        listing = record['listings'][kind]; rows = listing['rows']; pages = listing['pages']
        if listing['complete'] is not True or not rows or not pages or len(pages[-1]['rows']) >= 100:
            raise ValueError('incomplete provider listing')
        if [r for page in pages for r in page['rows']] != rows or len({r['ref'] for r in rows}) != len(rows):
            raise ValueError('provider page mismatch')
        for i, page in enumerate(pages, 1):
            if page['command'] != ['kaggle', kind, 'list', '--mine', '--page-size', '100', '--page', str(i), '--csv'] or page['exit_code'] != 0:
                raise ValueError('provider listing command mismatch')
            if list(csv.DictReader(io.StringIO(page['stdout']))) != page['rows'] and page['stdout'].strip() not in ('Not found', 'No datasets found', 'No kernels found', ''):
                raise ValueError('provider CSV mismatch')
        taken = {r['ref'].split('/')[1] for r in rows} | {re.sub(r'[^a-z0-9]+', '-', r.get('title', '').lower()).strip('-') for r in rows}
        if targets & taken or any(not r['ref'].startswith('ramhachi888/') for r in rows):
            raise ValueError('provider collision or owner mismatch')
        control = record['positive_controls'][kind]
        ref = control['command'][3]
        expected = ['kaggle', kind, 'status', ref] if kind == 'kernels' else ['kaggle', kind, 'files', ref, '--csv']
        if control['command'] != expected or ref not in {r['ref'] for r in rows} or control['exit_code'] != 0 or not control['stdout'].strip():
            raise ValueError('provider access control mismatch')


def project_closure():
    """Every project file loaded by importing the host scripts (hashed in the freeze), found by importing them, not by a glob."""
    code = ("import sys;sys.path[:0]=['src','scripts'];import analyze_gridres01,build_gridres01_inputs,build_gridres01_kernel,freeze_gridres01;"
            "print('\\n'.join(sorted(getattr(m,'__file__','') or '' for m in sys.modules.values())))")
    out = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True, cwd=ROOT, check=True).stdout.splitlines()
    return {str(Path(p).resolve().relative_to(ROOT)) for p in out if p and str(Path(p).resolve()).startswith(str(ROOT) + '/') and '/.venv/' not in p and '/site-packages/' not in p}


def freeze(case, source_commit):
    target = E / f'prerun_freeze_{case}.json'
    if target.exists():
        raise ValueError('refusing to overwrite an immutable freeze')
    inv = json.loads((E / 'inventory.json').read_text()); proof = json.loads(identity_path(case).read_text()); require_identity(case, proof)
    files = project_closure() | {str(p.relative_to(ROOT)) for p in (ROOT / 'tests').glob('test_gridres01_*.py')} | {
        'scripts/gridres01_runner_template.py', 'scripts/waterlily_gridres01_job.jl', str(identity_path(case).relative_to(ROOT)), str(identity_path(case).with_suffix('.json.sha256').relative_to(ROOT)),
        str((E / 'prerun_note.md').relative_to(ROOT)), str((E / 'inventory.json').relative_to(ROOT)), inv['parent']['raw_path'], inv['proposal']['file'], inv['opt01b_inventory']['path'],
        inv['opt01b_analysis']['path'], 'docs/gridres01_plan_2026_10_20.md'}
    files |= {f'{G.OPT01B_REL}/kernel_output/opt01b_{k}/states/{n}/{g}.forces.csv' for g, k in A.RETAINED.items() for n in G.NAMES}
    if subprocess.run(['git', '-C', str(ROOT), 'status', '--porcelain', '--untracked-files=no'], capture_output=True, text=True).stdout.strip():
        raise ValueError('tracked files have uncommitted changes; freeze only committed reviewed bytes')
    if not subprocess.run(['git', '-C', str(ROOT), 'branch', '-r', '--contains', source_commit], capture_output=True, text=True).stdout.strip():
        raise ValueError('the source commit is not on a remote branch; push it before freezing (the Kaggle runner fetches it from GitHub)')
    K.verify_source(source_commit, files)
    if subprocess.run(['git', '-C', str(ROOT), 'merge-base', '--is-ancestor', A.PARENT_INTEGRATION_COMMIT, source_commit]).returncode:
        raise ValueError('source does not descend from the committed plan with Amendment 1')
    path = K.kernel_dir(case) / 'runner.py'
    if path.read_text() != K.render(source_commit, case):
        raise ValueError('rendered worker differs from reviewed source')
    meta = path.with_name('kernel-metadata.json')
    if json.loads(meta.read_text()) != K.metadata(case):
        raise ValueError('kernel metadata mismatch')
    runtime = {**A.runtime_fixed(case), 'kernel_id': K.KERNEL_IDS[case], 'case_id': case, 'runner_sha256': K.sha(path), 'metadata_sha256': K.sha(meta)}
    result = {'kind': A.FREEZE_KIND, 'case_id': case, 'frozen_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'source_commit': source_commit, 'source_tree_id': A.git_tree_sha(source_commit),
              'parent_integration_commit': A.PARENT_INTEGRATION_COMMIT, 'inventory_sha256': K.sha(E / 'inventory.json'), 'frozen_parameters': A.FROZEN_PARAMETERS,
              'file_hashes': {p: K.sha(ROOT / p) for p in sorted(files)}, 'pins': K.pins(case), 'runtime': runtime, 'identity_free_check': proof, 'qualification_flags': {k: False for k in A.FLAGS},
              'rules': {'question': 'do finer grids follow flow_32 (a positive slope capability along the OPT-01 direction) or flow_24 (none)?',
                        'quantity': 'G_max = max(0, sup over s in (0, 1.25] mm of a*s + b*s^2), the no-intercept least-squares fit of the downforce change on the five-state steps (+0.3125, +0.625, +1.25, -1.25 mm)',
                        'verdict': 'FLOW40_SIDES_WITH_FLOW32 iff G_max(flow_40) > 4e-5 N; FLOW40_SIDES_WITH_FLOW24 iff G_max < 2e-5 N; AMBIGUOUS otherwise (then the flow_48 branch, frozen and reviewed separately); '
                                   'INCOMPLETE on an integrity failure or any downforce fit residual above 2e-5 N on any of flow_24, flow_32, flow_40',
                        'report_only': 'forward-only fit, contraction ratios and CONTRACTING/THIRD_VALUE labels, acceptance emulation per tested step, drag a and b per grid',
                        'integrity': 'phi hashes byte-identical to the OPT-01 Stage B inventory; retained flow_24/flow_32 force CSVs hash-checked against the Stage B analysis; a plain fresh parent run (no cross-grid byte identity exists)'},
              'known_before_run': 'non-blind: the flow_24/flow_32 values and their quadratic structure are known; the direction is a selected line (max-min of the flow_24/flow_32 predictions); see the prerun note for the lattice-commensurability confound',
              'prohibitions': ['no result of this run alone supports a GRID-01 amendment', 'no automatic resubmission or repair after an integrity failure', 'flow_48 only by a separate reviewed freeze after an AMBIGUOUS flow_40 verdict']}
    target.write_bytes(canonical_json(result)); target.with_suffix('.json.sha256').write_text(K.sha(target) + '\n'); print('freeze', K.sha(target))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--grid', required=True, choices=sorted(G.GRIDS))
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument('--check-identities', action='store_true'); g.add_argument('--source-commit')
    args = p.parse_args()
    capture_identity(args.grid) if args.check_identities else freeze(args.grid, args.source_commit)


if __name__ == '__main__':
    main()
