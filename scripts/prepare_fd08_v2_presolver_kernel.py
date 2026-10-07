#!/usr/bin/env python3
"""Stage a private T4 notebook that executes the exact runner with the stop flag."""
import argparse
import json
from pathlib import Path


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--dataset-id", required=True)
    p.add_argument("--source-ref", default="refs/heads/codex/kaggle-batch-migration")
    args = p.parse_args()
    require_code = '''import hashlib, json, os, pathlib, runpy, urllib.request
criteria_paths = sorted(pathlib.Path('/kaggle/input').rglob('criteria.json'))
assert len(criteria_paths) == 1
criteria = json.loads(criteria_paths[0].read_text())
assert criteria['kind'] == 'fd08_v2_formal_validation'
bound = criteria['source_inputs']['kernel_runner']
url = 'https://raw.githubusercontent.com/ramhachi/CFD_opt_sdf/' + criteria['source_commit'] + '/' + bound['path']
data = urllib.request.urlopen(url, timeout=120).read()
assert hashlib.sha256(data).hexdigest() == bound['sha256']
runner = pathlib.Path('/kaggle/working/pre_solver_runner.py')
runner.write_bytes(data)
os.environ['FD08_V2_STOP_BEFORE_SOLVER'] = '1'
os.environ['FD08_V2_SOURCE_REF'] = SOURCE_REF
assert os.environ['FD08_V2_STOP_BEFORE_SOLVER'] == '1'
runpy.run_path(str(runner), run_name='__main__')
out = pathlib.Path('/kaggle/working') / criteria['artifact_paths']['output_root']
report = json.loads((out / 'pre_solver_execution_path.json').read_text())
assert report['status'] == 'PASS_PRE_SOLVER_EXECUTION_PATH'
assert report['solver_started'] is False
assert report['state_verification_count'] == report['state_count'] == 25
assert not any(pathlib.Path('/kaggle/working').rglob('*.forces.csv'))
assert not (out / 'DONE').exists() and not (out / 'result.json').exists()
print('REHEARSAL_ONLY_NO_FORMAL_OBSERVATIONS', flush=True)
'''
    source = "SOURCE_REF = " + repr(args.source_ref) + "\n" + require_code
    notebook = {"nbformat": 4, "nbformat_minor": 5,
        "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"}},
        "cells": [{"cell_type": "code", "execution_count": None, "metadata": {}, "outputs": [],
                   "source": source.splitlines(keepends=True)}]}
    metadata = {"id": "ramhachi888/cfd-opt-sdf-fd08-v2-formal-amend2-pre-solver",
        "title": "CFD Opt SDF FD08 V2 Formal Amend2 Pre Solver", "code_file": "rehearsal.ipynb",
        "language": "python", "kernel_type": "notebook", "is_private": True,
        "enable_gpu": True, "enable_internet": True, "dataset_sources": [args.dataset_id],
        "competition_sources": [], "kernel_sources": []}
    args.output.mkdir(parents=True, exist_ok=False)
    for name, value in (("rehearsal.ipynb", notebook), ("kernel-metadata.json", metadata)):
        (args.output / name).write_text(json.dumps(value, sort_keys=True, indent=2) + "\n")


if __name__ == "__main__":
    main()
