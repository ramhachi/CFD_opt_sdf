import argparse,hashlib,importlib.util,json,subprocess,tempfile
from pathlib import Path
from scripts import register_fd08_v2_formal as r
root=r.ROOT; work=root/'work/formal_lineage_validation';source=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()
a=argparse.Namespace(state=root/'work/sdf_native_genesis_v17/sdf_design_state.npz',r6_criteria=r.DEFAULT_R6_CRITERIA,r6_result=r.DEFAULT_R6_RESULT,r6_terminal=r.DEFAULT_R6_TERMINAL,r6_dataset_dir=r.DEFAULT_R6_DATASET,dataset_dir=work/'candidate_dataset',criteria=work/'candidate_criteria_unused.json',preflight=work/'candidate_preflight_unused.json',budget_evidence=work/'budget_preflight.json',source_commit=source,dry_run=True)
built=r.build_formal(a);c=built['criteria'];assert not a.criteria.exists() and not a.preflight.exists() and not a.dataset_dir.exists()
sp=importlib.util.spec_from_file_location('runner',root/'infra/kaggle/kernel_fd08_v2_r6/runner.py');runner=importlib.util.module_from_spec(sp);sp.loader.exec_module(runner)
with tempfile.TemporaryDirectory(prefix='fd08-source-') as t:
 checkout=Path(t)/'source';subprocess.run(['git','clone','--quiet','--shared','--no-checkout',str(root),str(checkout)],check=True)
 subprocess.run(['git','-C',str(checkout),'sparse-checkout','set','--no-cone',*sorted({x['path'] for x in c['source_inputs'].values()})],check=True,capture_output=True)
 subprocess.run(['git','-C',str(checkout),'checkout','--quiet','--detach',source],check=True)
 runner.verify_source(checkout,c,r.digest(root/'infra/kaggle/kernel_fd08_v2_r6/runner.py'))
 frozen=json.loads((r.EVIDENCE/'scientific_contract_frozen.json').read_text())['scientific_contract']
 assert c['numeric_prediction_rule']==frozen['numeric_prediction_rule'] and c['decision_tree']==frozen['decision_tree']
 for field in frozen['measurement_caps']:assert c['measurement'][field]==frozen['measurement_caps'][field]
 report={'kind':'fd08_v2_formal_solver_free_lineage_validation','status':'PASS','formal_registered':False,'formal_solver_executed':False,'candidate_source_commit':source,'parent_identity':r.R6_PARENT,'formal_source_commit_not_R6':source!=r.R6_PARENT['source_commit'],'fresh_checkout_runner_source_verification':'PASS','source_input_count':len(c['source_inputs']),'source_inputs':c['source_inputs'],'amendment_lineage':c['formal_preregistration_amendment'],'formal_criteria_id':c['criteria_id'],'formal_dataset_id':c['input_dataset_id'],'kernel_id':c['kernel_id'],'metadata_id_matches':built['metadata']['id']==c['input_dataset_id'],'state_count':len(c['state_inventory']),'signed_states':24,'baseline_states':1,'epsilon_mm':c['formal_epsilon']['epsilon_mm'],'byte_disjointness':c['byte_disjointness'],'direction_hashes':c['direction_inventory']['hashes'],'float32_audits':c['float32_centered_direction_audits'],'state_inventory':c['state_inventory'],'scientific_contract_frozen_sha256':r.digest(r.EVIDENCE/'scientific_contract_frozen.json'),'scientific_contract_changed':False,'R6_analysis_or_solver_executed':False,'qualification_flags':c['qualification_flags'],'validation_script_sha256':r.digest(Path(__file__))}
 p=work/'dry_run_report.json';blob=(json.dumps(report,sort_keys=True,indent=2)+'\n').encode();p.write_bytes(blob);p.with_suffix('.json.sha256').write_text(hashlib.sha256(blob).hexdigest()+'\n')
 print(json.dumps({k:report[k] for k in ['status','formal_registered','candidate_source_commit','fresh_checkout_runner_source_verification','source_input_count','state_count','scientific_contract_changed']},indent=2))
