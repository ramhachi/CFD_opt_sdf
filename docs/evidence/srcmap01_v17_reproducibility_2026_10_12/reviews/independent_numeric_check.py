"""Independent post-run check of saved fields only: no mapping or primary helpers."""
import hashlib,itertools,json,pathlib
import numpy as np
ROOT=pathlib.Path.cwd(); E=ROOT/'docs/evidence/srcmap01_v17_reproducibility_2026_10_12'
freeze=json.loads((E/'prerun_freeze.json').read_text()); rows=[]; fields={}; checks=0
for entry in freeze['files']:
 assert hashlib.sha256((ROOT/entry['path']).read_bytes()).hexdigest()==entry['sha256'];checks+=1
for job in freeze['jobs']:
 name=job['id']; path=E/f'diagnostics/{name}.npz'; d=json.loads(path.with_suffix('.json').read_text()); f=np.load(path)
 assert hashlib.sha256(path.read_bytes()).hexdigest()==d['npz_sha256']
 ref=np.load(ROOT/'docs/evidence/p22_v17_volume_semantics_bridge_2026_10_11/inputs'/('v16_reference.npz' if job['grid']=='v16' else 'v17_baseline.npz'))['phi']
 a=f['phi_float32']; b=f['phi_float64']; assert a.dtype==np.dtype('<f4') and b.dtype==np.dtype('<f8')
 assert a.shape==b.shape==ref.shape and np.array_equal(b.astype('<f4').view('<u4'),a.view('<u4'))
 delta=a.astype('f8')-ref.astype('f8'); bits=a.view('<u4')!=ref.view('<u4'); signs=np.signbit(a)!=np.signbit(ref)
 stats={'different_bits_count':int(bits.sum()),'different_sign_count':int(signs.sum()),'max_absolute_difference_m':float(np.abs(delta).max())}
 for key,value in stats.items():assert d['comparison_float32_registered'][key]==value,(name,key)
 for key,arr in [('phi_float32',a),('phi_float64',b)]:
  for endian,order in itertools.product(('<','>'),('C','F')):
   h=hashlib.sha256(arr.astype(arr.dtype.newbyteorder(endian),copy=False).tobytes(order=order)).hexdigest()
   assert h==d[key]['bytes_sha256'][f'{endian}_{order}'];checks+=1
  for mask,keyname in [(np.signbit(arr),'sign_mask_sha256'),(arr==0,'exact_zero_mask_sha256'),(arr<0,'negative_mask_sha256')]:
   assert hashlib.sha256(mask.astype('u1').tobytes(order='C')).hexdigest()==d[key][keyname];checks+=1
 fields[name]=(a,b); rows.append(dict(id=name,stage=job['stage'],grid=job['grid'],**stats,differing_indices=np.argwhere(bits).tolist()))
groups={}
for job in freeze['jobs']:
 key=(job['python'],job['grid'],job['chunk'],job['order'],job['mode']);groups.setdefault(key,[]).append(job['id'])
pairs=[]
for key,names in groups.items():
 for x,y in itertools.combinations(names,2):
  counts=[int(np.count_nonzero(fields[x][i].view('<u'+str(fields[x][i].itemsize))!=fields[y][i].view('<u'+str(fields[y][i].itemsize)))) for i in (0,1)]
  pairs.append(dict(a=x,b=y,float32_differing_bits=counts[0],float64_differing_bits=counts[1]))
base=fields['A_v17_1'][1];magnitudes=[]
for job in freeze['jobs']:
 if job['grid']=='v17':
  a=fields[job['id']][1]
  magnitudes.append(dict(id=job['id'],unsigned_float64_different_bits_from_A1=int(np.count_nonzero(np.abs(a).view('<u8')!=np.abs(base).view('<u8')))))
classification=json.loads((E/'classification.json').read_text());nondet=any(p['float32_differing_bits'] or p['float64_differing_bits'] for p in pairs)
if nondet:assert classification['terminal_classification']=='SOURCE_MAPPING_ALGORITHM_NONDETERMINISTIC'
result=dict(method='independent NumPy saved-array verification; no primary helper import or fresh geometry query',frozen_and_field_hash_checks=checks,job_count=len(rows),runs=rows,same_condition_pairs=pairs,unsigned_magnitude_comparisons=magnitudes,same_condition_nondeterminism_observed=nondet,classification_consistent=True,check_passed=True)
with (E/'independent_numeric_check.json').open('x') as stream:json.dump(result,stream,indent=2);stream.write('\n')
print(json.dumps({'jobs':len(rows),'hash_checks':checks,'same_condition_pairs':len(pairs),'nondeterminism_observed':nondet,'check_passed':True}))
