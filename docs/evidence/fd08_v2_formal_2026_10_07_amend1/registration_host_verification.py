import hashlib, importlib.util, json, subprocess, tempfile, traceback
from pathlib import Path
ROOT=Path.cwd(); E=ROOT/'docs/evidence/fd08_v2_formal_2026_10_07_amend1'; D=ROOT/'work/kaggle_fd08_v2_formal_amend1_dataset'
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
p=E/'formal_criteria.json'; c=json.loads(p.read_text()); cs=sha(p)
assert p.with_suffix('.json.sha256').read_text().strip()==cs
assert sha(E/'formal_preflight.json')==c['preflight']['sha256']
assert c['source_commit']=='30aa20a6891ccabefaa2ef6d41a2e2b5e26701b5'
assert c['calibration_binding']['source_commit']=='f8ee8ae9ff433efc009258c29c230c5c9cdeb7b9'
assert c['formal_preregistration_amendment']['scientific_contract_changed'] is False
for entry in c['source_inputs'].values():
 blob=subprocess.check_output(['git','show',c['source_commit']+':'+entry['path']])
 assert hashlib.sha256(blob).hexdigest()==entry['sha256']
s=importlib.util.spec_from_file_location('registered_runner', ROOT/'infra/kaggle/kernel_fd08_v2_r6/runner.py'); r=importlib.util.module_from_spec(s); s.loader.exec_module(r)
report={'kind':'fd08_v2_formal_registration_host_verification','formal_registered':True,'formal_solver_executed':False,'formal_response_observed':False,'formal_analyzer_executed':False,'criteria_sha256':cs,'formal_source_commit':c['source_commit'],'R6_parent_source_commit':c['calibration_binding']['source_commit'],'source_input_sha_verification':'PASS','source_input_count':len(c['source_inputs']),'expected_state_count':25,'qualification_flags':c['qualification_flags'],'checks':{}}
with tempfile.TemporaryDirectory(prefix='fd08-formal-mount-') as td:
 mount=Path(td)
 for f in D.iterdir():
  if f.name!='dataset-metadata.json': (mount/f.name).symlink_to(f)
 _,loaded,loaded_sha=r.load_criteria(mount)
 assert loaded==c and loaded_sha==cs
 report['checks']['load_criteria']='PASS'
 r.verify_dataset(mount,c,cs)
 report['checks']['verify_dataset']='PASS'
 report['mounted_file_count']=len(list(mount.iterdir()))
 try:
  r.validate_state_files(mount,c)
  report['checks']['validate_state_files']='PASS'
  report['status']='PASS_REGISTERED_HOST_VERIFICATION'
 except Exception as exc:
  report['checks']['validate_state_files']='FAIL'
  report['status']='BLOCKED_INFRASTRUCTURE'
  report['exception_type']=type(exc).__name__
  report['exception_message']=str(exc)
  report['traceback']=traceback.format_exc()
  report['formal_verdict']=None
  report['reason']='Registered formal criteria use geometry; registered shared runner requires geometry_reject_gates. Source/criteria amendment required; immutable registration preserved; no upload or solver submission.'
report['dataset_manifest_sha256']=sha(D/'fd08_v2_dataset_manifest.json')
report['dataset_metadata_sha256']=sha(D/'dataset-metadata.json')
report['dataset_id']=c['input_dataset_id']
report['kernel_id']=c['kernel_id']
report['dataset_uploaded']=False; report['kernel_submitted']=False
out=E/'registration_host_verification.json'
out.write_text(json.dumps(report,sort_keys=True,indent=2)+'\n'); out.with_suffix('.json.sha256').write_text(sha(out)+'\n')
print(json.dumps({k:report[k] for k in ['status','criteria_sha256','mounted_file_count','checks','exception_type','exception_message']},indent=2))
