import csv, hashlib, json, math, pathlib, re
import numpy as np

CRIT=pathlib.Path('/Users/sota/.codex/worktrees/fd08-p2a/CFD2026_09/docs/evidence/fd08_candidate_c_calibration_2026_10_04_r5/xfidc_criteria.json')
ANALYSIS=CRIT.with_name('calibration_analysis.json')
RUN=CRIT.parent/'result/fd08_calibration'
DATA=pathlib.Path('/Users/sota/.codex/worktrees/issue45-root-certifier-integration/work/fd08_candidate_c_calibration_dataset_r5')
OUT=pathlib.Path('/tmp/fd08_p2a_independent.json')
EXPECT={'criteria':'928292ca1911875a564e74ffbe64b7d3d4790d9e49b81272ed39dedd9ebdce6c','analysis':'dc769d6f2b5a2d6dfa45c6a5aeddfde726dd75f6e44ac564b128effecce3fb8b','runner_sha256_json':'1b04c3c2243459d2889dc16aa0f3c02c2ff6a5555a64406bb8177b9ee0b8600e'}
def sha(p):
 h=hashlib.sha256()
 with open(p,'rb') as f:
  for b in iter(lambda:f.read(1<<20),b''): h.update(b)
 return h.hexdigest()
def jload(p): return json.loads(p.read_text())
def f(x): return float(x)
def median(xs): return float(np.median(np.asarray(xs,dtype=np.float64)))
def finite(x):
 x=float(x)
 if not math.isfinite(x): raise ValueError(f'nonfinite {x}')
 return x
def csvmean(p,col):
 with open(p,newline='') as fp:
  rows=list(csv.DictReader(fp))
 t=np.array([f(r['t_u_l']) for r in rows],dtype=np.float64)
 y=np.array([f(r[col]) for r in rows],dtype=np.float64)
 order=np.argsort(t); t=t[order]; y=y[order]
 if np.any(np.diff(t)<=0): raise ValueError(f'nonmonotone time {p}')
 lo,hi=80.,120.
 inside=(t>lo)&(t<hi)
 ts=np.concatenate(([lo],t[inside],[hi]))
 ys=np.interp(ts,t,y)
 return finite(math.fsum(float((ys[i]+ys[i+1])*.5*(ts[i+1]-ts[i])) for i in range(len(ts)-1))/(hi-lo)/900.)
def ls(x,y):
 x=np.asarray(x,dtype=np.float64); y=np.asarray(y,dtype=np.float64)
 if len(x)<2: return None
 xm=math.fsum(map(float,x))/len(x); ym=math.fsum(map(float,y))/len(y)
 den=math.fsum((float(v)-xm)**2 for v in x)
 if den==0:return None
 c=math.fsum((float(a)-xm)*(float(b)-ym) for a,b in zip(x,y))/den
 g=ym-c*xm
 pred=g+c*x
 rms=math.sqrt(math.fsum((float(a)-float(b))**2 for a,b in zip(y,pred))/len(y))
 return {'g_N_per_m':finite(g),'c_N_per_m_mm2':finite(c),'rms_N_per_m':finite(rms),'rms_over_abs_g_percent':finite(100*rms/abs(g)) if g else None}
def vol(phi,h):
 # chunks flattened to bound memory; fsum in source-precision-defined float64
 flat=np.asarray(phi,dtype=np.float32).ravel(order='C')
 v=np.clip(0.5-flat.astype(np.float64)/h,0.,1.)
 return finite(math.fsum(map(float,v))*h**3)

def main():
 hashes={k:sha(p) for k,p in [('criteria',CRIT),('analysis',ANALYSIS),('runner_sha256_json',RUN/'sha256.json')]}
 crit=jload(CRIT); man=jload(RUN/'sha256.json'); result=jload(RUN/'result.json')
 dataset_checks={k:{'expected':v,'actual':sha(DATA/k),'match':sha(DATA/k)==v} for k,v in crit['dataset_files'].items()}
 # runner payload inventory: all requested 47 states, expected output files, path/hash reconciliation
 csv_checks={}; state_checks={}; missing=[]; extras=[]
 for rel,expected in man.items():
  p=RUN/rel
  if not p.is_file(): missing.append(rel)
 for s in crit['state_order']:
  rid=s['run_id']
  d=RUN/'states'/rid
  for nm,kind in [('flow_24.forces.csv','force_csv_sha256'),('state_result.json','state_result_sha256')]:
   p=d/nm; rel=f'states/{rid}/{nm}'
   got=sha(p) if p.is_file() else None
   # force entry is keyed by path in sha256; state results likewise
   csv_checks[rid]=csv_checks.get(rid,{})
   if nm.endswith('.csv'):
    csv_checks[rid]={'present':bool(p.is_file()),'expected_runner_hash':man.get(rel),'actual':got,'match':bool(got and man.get(rel)==got)}
   else:
    state_checks[rid]={'present':bool(p.is_file()),'expected_runner_hash':man.get(rel),'actual':got,'match':bool(got and man.get(rel)==got)}
 # Map run id force means
 means={}
 for s in crit['state_order']:
  if s['role']=='baseline':
   means[s['run_id']]={r:csvmean(RUN/'states'/s['run_id']/'flow_24.forces.csv',col) for r,col in [('drag','drag_solver'),('downforce','downforce_solver')]}
  else:
   p=RUN/'states'/s['run_id']/'flow_24.forces.csv'
   means[s['run_id']]={r:csvmean(p,col) for r,col in [('drag','drag_solver'),('downforce','downforce_solver')]}
 # R0 from five ordered baselines
 bases=[s for s in crit['state_order'] if s['role']=='baseline']
 R0={r:finite(math.fsum(means[s['run_id']][r] for s in bases)/5) for r in ['drag','downforce']}
 baseline_vals={r:[means[s['run_id']][r] for s in bases] for r in ['drag','downforce']}
 rule=crit['response_floor_rule']
 floors={r:max(max(baseline_vals[r])-min(baseline_vals[r]),1e-8*max(1.,abs(median(baseline_vals[r])))) for r in R0}
 eps_mm=[float(e)*1000 for e in crit['calibration_epsilon_ladder_m']]
 dirs=sorted({s['direction_id'] for s in crit['state_order'] if s['role']=='perturbation'})
 by={(s['direction_id'],s['epsilon_m'],s['sign']):s['run_id'] for s in crit['state_order'] if s['role']=='perturbation'}
 a1={};
 for d in dirs:
  a1[d]={}
  for r in R0:
   a1[d][r]=[]
   for em,emm in zip(crit['calibration_epsilon_ladder_m'],eps_mm):
    rp=means[by[(d,em,1)]][r]; rm=means[by[(d,em,-1)]][r]
    S=(rp-rm)/2; q=S/em; E=(rp+rm)/2-R0[r]
    a1[d][r].append({'epsilon_mm':emm,'R_plus_N':rp,'R_minus_N':rm,'S_N':finite(S),'q_N_per_m':finite(q),'E_N':finite(E),'abs_S_ge_floor':abs(S)>=floors[r]})
 # A2 fit by interval and |S| cut, then g spread among intervals for each cut
 intervals=[(0.5,5.),(0.5,15.),(1.5,15.)]; cuts=[0.,10e-6,30e-6,50e-6]
 a2={}
 for d in dirs:
  a2[d]={}
  for r in R0:
   points=a1[d][r]; a2[d][r]={}
   for cut in cuts:
    ck='all' if cut==0 else f'abs_S_ge_{cut*1e6:.0f}_uN'
    a2[d][r][ck]={}
    for lo,hi in intervals:
     chosen=[p for p in points if lo<=p['epsilon_mm']<=hi and abs(p['S_N'])>=cut]
     fit=ls([p['epsilon_mm']**2 for p in chosen],[p['q_N_per_m'] for p in chosen])
     a2[d][r][ck][f'{lo:g}_{hi:g}_mm']={'n':len(chosen),'fit':fit}
    gs=[a2[d][r][ck][f'{lo:g}_{hi:g}_mm']['fit']['g_N_per_m'] for lo,hi in intervals if a2[d][r][ck][f'{lo:g}_{hi:g}_mm']['fit']]
    a2[d][r][ck]['three_interval_g_spread_percent']=finite(100*(max(gs)-min(gs))/abs(median(gs))) if len(gs)==3 and median(gs)!=0 else None
 # A3 windows start at indices 0,1,2; each window uses its own five-point q median
 a3={}
 for d in dirs:
  a3[d]={}
  for r in R0:
   qs=[p['q_N_per_m'] for p in a1[d][r]]
   windows=[]
   for st in [0,1,2]:
    vals=qs[st:st+5]
    qref=median(vals); norm=max(abs(qref),floors[r]/min(crit['calibration_epsilon_ladder_m']))
    windows.append({'start_index':st,'epsilon_mm':[eps_mm[st],eps_mm[st+4]],'median_q_ref_N_per_m':finite(qref),'normalizer_N_per_m':finite(norm),'max_relative_deviation_percent':finite(100*max(abs(q-qref) for q in vals)/norm)})
   a3[d][r]={'response_floor_N':finite(floors[r]),'windows':windows}
 # A3-prime LOO fits per requested inclusive interval/cut
 a3p={}
 for d in dirs:
  a3p[d]={}
  for r in R0:
   a3p[d][r]={}
   for cut in [10e-6,30e-6,50e-6]:
    ck=f'abs_S_ge_{cut*1e6:.0f}_uN'; a3p[d][r][ck]={}
    for lo,hi in intervals:
     pts=[p for p in a1[d][r] if lo<=p['epsilon_mm']<=hi and abs(p['S_N'])>=cut]
     outcomes=[]
     for i,p in enumerate(pts):
      train=pts[:i]+pts[i+1:]
      fit=ls([x['epsilon_mm']**2 for x in train],[x['q_N_per_m'] for x in train]) if len(pts)>=4 and len(train)>=3 else None
      pred=(fit['g_N_per_m']+fit['c_N_per_m_mm2']*p['epsilon_mm']**2) if fit else None
      obs=p['q_N_per_m']; ae=abs(obs-pred) if pred is not None else None
      re=(ae/abs(obs)) if pred is not None and abs(obs)>=1e-9 else None
      outcomes.append({'holdout_epsilon_mm':p['epsilon_mm'],'n_train':len(train),'q_observed_N_per_m':obs,'q_predicted_N_per_m':finite(pred) if pred is not None else None,'absolute_error_N_per_m':finite(ae) if ae is not None else None,'relative_error':finite(re) if re is not None else None,'relative_error_defined':re is not None,'classification':'undeterminable'})
     a3p[d][r][ck][f'{lo:g}_{hi:g}_mm']={'n_points':len(pts),'status':'undeterminable','classification':'undeterminable','loo':outcomes}
 # A3 double-prime assumed sigma sensitivities, windows 5pt starts
 a3pp={}
 for d in dirs:
  a3pp[d]={}
  for r in R0:
   a3pp[d][r]={}
   qs=[p['q_N_per_m'] for p in a1[d][r]]
   for st in [0,1,2]:
    qref=median(qs[st:st+5]); ref=abs(qref)
    eps_rows=[]
    for j in range(st,st+5):
     em=crit['calibration_epsilon_ladder_m'][j]
     eps_rows.append({'epsilon_mm':eps_mm[j],'epsilon_m':em,'assumed_sigma':{str(sig):{'sigma_over_epsilon_N_per_m':finite(sig*1e-6/em),'ratio_to_abs_window_q_ref_percent':finite(100*(sig*1e-6/em)/ref) if ref else None} for sig in [2,3,4]}})
    a3pp[d][r][f'window_{st}']={'window_indices':[st,st+4],'q_ref_median_N_per_m':finite(qref),'abs_q_ref_N_per_m':finite(ref),'epsilon_rows':eps_rows}
 # A4 fields and saved perturbation reproduction
 shape=(121,65,49); n=int(np.prod(shape)); hvals=[0.025,0.03333]
 base_raw=np.fromfile(DATA/'baseline_v17.phi_f4_fortran.raw',dtype='<f4').reshape(shape,order='F')
 with np.load(DATA/'baseline_v17.npz') as z: base_npz=np.array(z['phi'])
 base=np.asarray(base_raw,dtype=np.float32)
 if base_npz.shape!=shape: raise ValueError(f'base NPZ shape {base_npz.shape}')
 baseline_equal=bool(np.array_equal(base_raw,base_npz))
 volumes={}
 for h in hvals: volumes[h]=vol(base,h)
 a4={'shape':list(shape),'base_raw_order':'little-endian float32 Fortran','base_npz_phi_shape':list(base_npz.shape),'base_raw_matches_baseline_npz_phi':baseline_equal,'direction_order':'float32 C','saved_state_order':'float32 Fortran','saved_perturbation_checks':{},'all_epsilon_functional':{},'functional_definition':'fsum(clip(0.5 - phi/h, 0, 1))*h^3','h_m':hvals,'baseline_functionals_m3':{str(h):volumes[h] for h in hvals}}
 for d in dirs:
  direction=np.fromfile(DATA/f'directions/{d}.f4-c.raw',dtype='<f4').reshape(shape,order='C')
  if direction.dtype!=np.float32: raise AssertionError('direction dtype')
  # validate the seven registered states byte-value exact against independent expression
  for s in crit['state_order']:
   if s['role']!='perturbation' or s['direction_id']!=d: continue
   raw=np.fromfile(DATA/s['raw_file'],dtype='<f4').reshape(shape,order='F')
   expected=np.asarray(base.astype(np.float64)+int(s['sign'])*float(s['epsilon_m'])*direction.astype(np.float64),dtype=np.float32)
   key=s['run_id']; a4['saved_perturbation_checks'][key]={'match':bool(np.array_equal(raw,expected)),'mismatch_count':int(np.count_nonzero(raw!=expected))}
  # union registered seven and 40-point logspace ladder; exact unique float values
  es=sorted(set(float(x) for x in crit['calibration_epsilon_ladder_m'])|set(map(float,np.logspace(math.log10(.00005),math.log10(.05),40))))
  rows=[]
  for em in es:
   phis={}
   for sign,label in [(1,'plus'),(-1,'minus')]:
    phis[label]=np.asarray(base.astype(np.float64)+sign*em*direction.astype(np.float64),dtype=np.float32)
   for h in hvals:
    fplus=vol(phis['plus'],h); fminus=vol(phis['minus'],h); f0=volumes[h]
    rows.append({'epsilon_m':em,'h_m':h,'F_plus_m3':fplus,'F_minus_m3':fminus,'odd_m3':finite((fplus-fminus)/2),'odd_over_epsilon_m2':finite((fplus-fminus)/(2*em)),'even_m3':finite((fplus+fminus)/2-f0)})
  a4['all_epsilon_functional'][d]=rows
 # counts/missing and deterministic serializable output
 checks={'criteria_sha256_match':hashes['criteria']==EXPECT['criteria'],'analysis_sha256_match':hashes['analysis']==EXPECT['analysis'],'runner_manifest_sha256_match':hashes['runner_sha256_json']==EXPECT['runner_sha256_json'],'criteria_dataset_hashes':dataset_checks,'criteria_dataset_hashes_all_match':all(x['match'] for x in dataset_checks.values()),'criteria_dataset_hash_count':len(dataset_checks),'runner_force_csv_checked_count':sum(v.get('present',False) for v in csv_checks.values()),'runner_force_csv_match_count':sum(v.get('match',False) for v in csv_checks.values()),'runner_state_result_checked_count':sum(v.get('present',False) for v in state_checks.values()),'runner_state_result_match_count':sum(v.get('match',False) for v in state_checks.values()),'missing_runner_manifest_files':sorted(missing),'force_csv_hashes':csv_checks,'state_result_hashes':state_checks,'sha256_json_entries':len(man)}
 out={'schema':'fd08-p2a-independent-recalculation-v1','input_hashes':hashes,'hash_checks':checks,'state_count':len(means),'baseline_response_means_N':R0,'baseline_repeat_means_N':baseline_vals,'response_floor_N':{k:finite(v) for k,v in floors.items()},'A1':a1,'A2':a2,'A3':a3,'A3_prime_LOO':a3p,'A3_double_prime_assumed_sigma':a3pp,'A4':a4}
 OUT.write_text(json.dumps(out,sort_keys=True,indent=2,allow_nan=False)+'\n')
 print(json.dumps({'output':str(OUT),'output_sha256':sha(OUT),'state_count':len(means),'dataset_hashes_match':checks['criteria_dataset_hashes_all_match'],'dataset_hash_count':len(dataset_checks),'force_csv_count':checks['runner_force_csv_checked_count'],'force_csv_match':checks['runner_force_csv_match_count'],'state_result_count':checks['runner_state_result_checked_count'],'state_result_match':checks['runner_state_result_match_count'],'missing_runner_manifest_files':missing,'saved_perturbations_match':sum(x['match'] for x in a4['saved_perturbation_checks'].values()),'saved_perturbations_count':len(a4['saved_perturbation_checks'])},sort_keys=True))
 if not all(checks[k] for k in ['criteria_sha256_match','analysis_sha256_match','runner_manifest_sha256_match','criteria_dataset_hashes_all_match']): raise SystemExit('input hash check failed')
 if checks['runner_force_csv_match_count']!=47 or checks['runner_state_result_match_count']!=47: raise SystemExit('runner state hash check incomplete')
 if not baseline_equal or not all(v['match'] for v in a4['saved_perturbation_checks'].values()): raise SystemExit('A4 saved phi mismatch')
 if any(not np.all(np.isfinite([row['odd_m3'],row['odd_over_epsilon_m2'],row['even_m3']])) for rows in a4['all_epsilon_functional'].values() for row in rows): raise SystemExit('A4 nonfinite')
 if not OUT.is_file(): raise SystemExit('no output')

if __name__ == '__main__':
 main()
