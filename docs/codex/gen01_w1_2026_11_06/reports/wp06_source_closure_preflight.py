"""Reproduce the NEW historical-source-closure conflict, without editing pins.

The same immutable GRID-02 reader/registration passes on 08e0ea38 but demands
five additional frozen hashes when the required scene source files exist.
Successful exit confirms that contradiction, not phase-A acceptance.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[4]
BASE_COMMIT = "08e0ea3823168c330b3023aeb508734584a57edb"
EXPECTED = sorted(f"src/cfd_sdf/scene/{name}.py" for name in ("__init__","primitives","scene","events","gates"))
PROBE = """import json,sys
from pathlib import Path
sys.path[:0]=['src','scripts']
import analyze_grid02 as A
r=Path('.')
i=json.loads((r/A.EVIDENCE_REL/'inventory.json').read_text())
f=json.loads((r/A.EVIDENCE_REL/'prerun_freeze.json').read_text())
out={'required_not_in_frozen':sorted(A.required_file_paths(i)-set(f['file_hashes']))}
try:
 A.validate_registration(f,i)
 out['validation']='PASS'
except Exception as e:
 out['validation']=type(e).__name__+': '+str(e)
print(json.dumps(out,sort_keys=True))
"""


def probe(root):
    run = subprocess.run([sys.executable,"-c",PROBE],cwd=root,capture_output=True,text=True,check=True)
    return json.loads(run.stdout)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline",type=Path,required=True)
    baseline = parser.parse_args().baseline.resolve()
    head = subprocess.check_output(["git","rev-parse","HEAD"],cwd=baseline,text=True).strip()
    if head!=BASE_COMMIT:
        raise RuntimeError("baseline must be the detached start commit 08e0ea38")
    paths = ["scripts/analyze_grid02.py","docs/evidence/grid02_trend_2026_10_16/prerun_freeze.json"]
    for rel in paths:
        if (baseline/rel).read_bytes()!=(ROOT/rel).read_bytes():
            raise RuntimeError(f"protected reader/registration bytes changed: {rel}")
    before,after = probe(baseline),probe(ROOT)
    if before!={"required_not_in_frozen":[],"validation":"PASS"}:
        raise RuntimeError(f"unexpected baseline: {before}")
    if after!={"required_not_in_frozen":EXPECTED,"validation":"ValueError: frozen file/source closure is incomplete"}:
        raise RuntimeError(f"unexpected current result: {after}")
    paths += EXPECTED+[str(Path(__file__).relative_to(ROOT))]
    print(json.dumps({"status":"SOURCE_CLOSURE_CONFLICT_CONFIRMED","baseline_commit":BASE_COMMIT,
        "base":before,"current":after,"reader_definition":"scripts/analyze_grid02.py:105-116",
        "reader_rejection":"scripts/analyze_grid02.py:165-167",
        "evidence_class":"solver_free_contract_diagnostic_not_acceptance",
        "sha256":{rel:hashlib.sha256((ROOT/rel).read_bytes()).hexdigest() for rel in paths}},
        sort_keys=True,indent=2,allow_nan=False))


if __name__=="__main__":
    main()
