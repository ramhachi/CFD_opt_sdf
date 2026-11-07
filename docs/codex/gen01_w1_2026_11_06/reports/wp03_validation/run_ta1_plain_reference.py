from pathlib import Path
import hashlib,json,os,subprocess,time

base=Path('/tmp/grad00-validation')
root=Path('/Users/sota/projects/FomulaTMU/CFD2026_09-wp-03-grad00')
name='final_frozen_ta1_plain_quick20_O2_t10'
wrapper=base/'ta1_plain_reference_capture.jl'
command=['julia','-O2','-t','10','--project='+str(root/'julia/CFDSDFWaterLily'),str(wrapper)]
env={**os.environ,'G2_BACKEND':'cpu','G2_DRYRUN_T_END':'0.4','TA1_PREFLIGHT_ONLY':'1','OPENBLAS_NUM_THREADS':'1','OMP_NUM_THREADS':'1'}
env.pop('TA1_BLOCK_LIMIT',None)
sha=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
frozen=root/'scripts/waterlily_grad_ta1_2026_10_15.jl'
project=root/'julia/CFDSDFWaterLily/Project.toml'
manifest=root/'julia/CFDSDFWaterLily/Manifest.toml'
before={str(path):sha(path) for path in (frozen,project,manifest)}
started=time.monotonic()
with (base/(name+'.log')).open('w') as log:
    try: code=subprocess.run(command,cwd=root,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=300).returncode
    except subprocess.TimeoutExpired: code=124
record={'name':name,'command':command,'env':{k:env[k] for k in ('G2_BACKEND','G2_DRYRUN_T_END','TA1_PREFLIGHT_ONLY','OPENBLAS_NUM_THREADS','OMP_NUM_THREADS')},'process_cap_s':300,'exit_code':code,'wall_s':time.monotonic()-started,'wrapper_sha256':sha(wrapper),'launcher_sha256':sha(Path(__file__)),'before_sha256':before,'after_sha256':{str(path):sha(path) for path in (frozen,project,manifest)}}
record['frozen_source_and_environment_unchanged']=record['before_sha256']==record['after_sha256']
command_path=base/(name+'.command.json')
command_path.write_text(json.dumps(record,indent=2)+'\n')
comparison={'evidence_class':'cpu_matched_frozen_ta1_plain_quick20_bit_comparison','julia_flags':['-O2','-t','10'],'steps':20,'command_file':str(command_path),'command_file_sha256':sha(command_path),'pass':False,'claim_scope':'Ordinary Float32 primal u/p after 20 steps of the actual frozen TA1 build versus the saved GRAD00 selected_plain preflight. No full-window or target-physics claim.'}
capture=base/'ta1_plain_reference/quick_plain_control.json'
copy=base/'final_CFDSDFWaterLily_quick_Float32_O2_t10/preflight.json'
if capture.exists():
    ref=json.loads(capture.read_text()); selected=json.loads(copy.read_text())['arms']['selected_plain']
    comparison.update({'capture':str(capture),'capture_sha256':sha(capture),'copy_preflight':str(copy),'copy_preflight_sha256':sha(copy),'comparison':{key:ref[key]==selected[key] for key in ('primal_u_sha256','primal_p_sha256')},'reference_hashes':{key:ref[key] for key in ('primal_u_sha256','primal_p_sha256')},'fields_finite':ref['fields_finite'],'julia':ref['julia'],'waterlily':ref['waterlily'],'forwarddiff':ref['forwarddiff']})
    comparison['pass']=code==0 and ref['fields_finite'] and all(comparison['comparison'].values()) and record['frozen_source_and_environment_unchanged']
else:
    comparison['failure_reason']='capture absent; see command exit and log'
(base/'final_frozen_ta1_plain_vs_grad00_quick20_comparison.json').write_text(json.dumps(comparison,indent=2)+'\n')
print(json.dumps(record),flush=True)
print(json.dumps(comparison),flush=True)
