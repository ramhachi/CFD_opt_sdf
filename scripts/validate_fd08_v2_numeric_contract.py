"""Freeze then validate synthetic FD08 arithmetic; never loads solver results."""
from __future__ import annotations
import argparse
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal, localcontext
import hashlib
import gzip
import importlib.util
import json
import math
from pathlib import Path
import platform
import struct
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'scripts')]
OUT = ROOT / 'docs/evidence/fd08_v2_stage1p5_2026_10_06'
OLD = ROOT / 'docs/evidence/fd08_v2_stage1_2026_10_06'
NUMBERS = [1,2,3,4,6,7,9,10,11,12,13,15,16,17,18,19,20,22,24,27]
EXTENDED = [15,16,17,18,22,24]
BASE = 46150000


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def decimal_strings(v):
    if isinstance(v,dict):return {k:decimal_strings(x) for k,x in v.items()}
    if isinstance(v,list):return [decimal_strings(x) for x in v]
    return str(v) if isinstance(v,Decimal) else v


def jsonable(v):
    if isinstance(v, dict): return {k: jsonable(x) for k,x in v.items()}
    if isinstance(v, (list,tuple)): return [jsonable(x) for x in v]
    if isinstance(v, Decimal): return float(v)
    if isinstance(v, np.generic): return v.item()
    return v


def save(path, value):
    path.write_text(json.dumps(jsonable(value), sort_keys=True, indent=2, allow_nan=False)+'\n')


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def freeze():
    path = OUT / 'comparison_rule_freeze.json'
    if path.exists(): raise RuntimeError('freeze exists; never overwrite')
    files = [OUT/'numeric_contract.md', ROOT/'scripts/analyze_fd08_v2_numeric_contract.py',
             ROOT/'scripts/fd08_v2_forward_error.py',Path(__file__),
             ROOT/'tests/test_fd08_v2_numeric_contract.py',
             ROOT/'src/cfd_sdf/fd08_v2_gate.py',ROOT/'src/cfd_sdf/fd08_v2_gate_params.json',
             ROOT/'scripts/simulate_fd08_v2_gate.py', OLD/'independent_checker.py',
             OLD/'synthetic_inputs.json',OLD/'independent_comparison.json',OLD/'prerun_freeze.json',
             OUT/'independent_numerical_review.md']
    seeds = [dict(scenario=s,n=n,seed=BASE+1000*s+n,upper_mm=5)
             for s in NUMBERS for n in (6,8)]
    seeds += [dict(scenario=s,n=7,seed=BASE+1000*s+7,upper_mm=15) for s in EXTENDED]
    oldfreeze=json.loads((OLD/'prerun_freeze.json').read_text());oldbase=oldfreeze['base_seed']
    oldseeds={oldbase+1000*number+n for number in range(1,28) for n in (6,8)}
    oldseeds.update(oldbase+1000*number+7 for number in range(13,27))
    oldseeds.update(c['seed'] for c in json.loads((OLD/'synthetic_inputs.json').read_text())['cases'])
    if oldseeds & {s['seed'] for s in seeds}:raise RuntimeError('seed overlap')
    save(path,dict(recorded_utc=datetime.now(timezone.utc).isoformat(),
         evidence_class='solver_free_numeric_contract_design_unregistered',
         sha256={str(p.relative_to(ROOT)):sha(p) for p in files},
         seeds=seeds,base_seed=BASE,generator='PCG64',python=platform.python_version(),
         historical_seed_inventory=sorted(oldseeds),seed_overlap=[],
         ladder_construction='np.geomspace(.5,5,6); np.geomspace(.3,5,8); np.geomspace(.5,15,7)',
         draw_order='per point absolute then relative standard normal, always consume both',
         serialization="Python format(value,'.12g') then json parse to shared binary64",
         parameters=json.loads((ROOT/'src/cfd_sdf/fd08_v2_gate_params.json').read_text()),
         numpy=np.__version__,reference_digits=[80,120],
         historical_strict_numeric_mismatch_count=17,execution_started=False))
    print('RULES_FROZEN',sha(path),flush=True)


def flatten(v, prefix=''):
    if isinstance(v, dict):
        for k,x in v.items():
            if k not in ('numeric','params','epsilon_mm','s_n','q_n_per_m'):
                yield from flatten(x, f'{prefix}.{k}' if prefix else k)
    elif isinstance(v,list):
        for i,x in enumerate(v): yield from flatten(x,f'{prefix}[{i}]')
    else: yield prefix,v


def fit_common(f):
    if f is None: return dict(available=False)
    if 'coefficients_mm' in f:
        return dict(available=True,beta=f['coefficients_mm'],covariance=f['covariance_mm'],
                    pilot_s_n=f['pilot_predictions_n'],weights=f['weights_n_inverse_squared'],
                    g_n_per_mm=f['coefficients_mm'][0],g_n_per_m=f['g_n_per_m'],
                    se_g_n_per_mm=f['se_g_n_per_m']/1000,se_g_n_per_m=f['se_g_n_per_m'])
    return {k:f[k] for k in ('available','beta','covariance','pilot_s_n','weights',
                            'g_n_per_mm','g_n_per_m','se_g_n_per_mm','se_g_n_per_m')}


def common(r):
    if 'full_fits' in r:
        items = {('internal_holdout' if k=='holdout' else k):dict(passed=v['pass'])
                 for k,v in r['items'].items()}
        for k in ('relative_se','model_difference'): items[k]['value']=r['items'][k]['value']
        items['nested_stability']['maximum_relative_shift']=r['items']['nested_stability']['value']
        items['magnitude'].update(point_count=r['items']['magnitude']['value'],threshold_n=r['items']['magnitude']['threshold_n'])
        nested=[dict(drop=x['drop'],model_a=fit_common(x['fits']['A']),model_b=fit_common(x['fits']['B']),
                     relative_shift_a=x['relative_g_A_change']) for x in r['nested']]
        holds=[dict(index=x['index'],fit=fit_common(x['fit']),s_pred_n=x.get('prediction_n'),
                    sigma_pred_n=x.get('sigma_prediction_n'),error_n=x.get('absolute_error_n'),
                    limit_n=x.get('tolerance_n'),passed=x['pass']) for x in r['holdouts']]
        a,b=fit_common(r['full_fits']['A']),fit_common(r['full_fits']['B'])
    else:
        items={k:dict(passed=v['passed']) for k,v in r['items'].items()}
        for k in ('relative_se','model_difference'): items[k]['value']=r['items'][k]['value']
        items['nested_stability']['maximum_relative_shift']=r['items']['nested_stability']['maximum_relative_shift']
        items['magnitude'].update(point_count=r['items']['magnitude']['point_count'],threshold_n=r['items']['magnitude']['threshold_n'])
        nested=[dict(drop=x['drop'],model_a=fit_common(x['model_a']),model_b=fit_common(x['model_b']),relative_shift_a=x['relative_shift_a']) for x in r['nested']]
        holds=[{**{k:x[k] for k in ('index','s_pred_n','sigma_pred_n','error_n','limit_n','passed')},'fit':fit_common(x['fit'])} for x in r['holdout']]
        a,b=fit_common(r['model_a']),fit_common(r['model_b'])
    slopes=[a.get('g_n_per_mm'),b.get('g_n_per_mm')]+[x[m].get('g_n_per_mm') for x in nested for m in ('model_a','model_b')]
    items['sign']['signs']=[(g>0)-(g<0) for g in slopes if g is not None]
    return dict(model_a=a,model_b=b,nested=nested,holdout=holds,items=items,verdict=r['verdict'])


def ulp(a,b):
    def ordered(x):
        i=struct.unpack('>Q',struct.pack('>d',float(x)))[0]
        return (~i & ((1<<64)-1)) if i>>63 else i+(1<<63)
    return abs(ordered(a)-ordered(b)) if a!=b else 0


def round12(v):
    if isinstance(v,dict): return {k:round12(x) for k,x in v.items()}
    if isinstance(v,list): return [round12(x) for x in v]
    return float(format(v,'.12g')) if isinstance(v,float) else v


def serialization_bound(v):
    if not v: return Decimal(0)
    u=Decimal(2)**-53
    relative=Decimal('5e-12')+u*(1+Decimal('5e-12'))
    # Input is already an archived saved value, so invert its rounding gap.
    return relative*abs(Decimal.from_float(float(v)))/(1-relative)+Decimal(2)**-1075


def category(path):
    if 'covariance' in path:return 'covariance'
    if 'pilot' in path:return 'pilot'
    if 'weights' in path:return 'weights'
    if 'se_g' in path:return 'SE'
    if 'relative_shift' in path:return 'nested_shift'
    if 'relative_se' in path:return 'relative_SE'
    if 'model_difference' in path:return 'model_difference'
    if 'holdout' in path and '.fit.' not in path:return 'holdout'
    if '.beta' in path:return 'beta'
    if 'g_n_per' in path:return 'g'
    return 'other'


def subset_case(path,case):
    if path.startswith('nested['):
        index=int(path.split('[')[1].split(']')[0]);drop=index+1
        return {**case,'epsilon_mm':case['epsilon_mm'][:-drop],'response_n':case['response_n'][:-drop]}
    if path.startswith('holdout[') and '.fit.' in path:
        index=int(path.split('[')[1].split(']')[0])+1
        return {**case,'epsilon_mm':[e for j,e in enumerate(case['epsilon_mm']) if j!=index],
                'response_n':[y for j,y in enumerate(case['response_n']) if j!=index]}
    return case


def mixed_scale(path, ref, case):
    case=subset_case(path,case)
    if category(path) in ('nested_shift','relative_SE','model_difference'):return 1.
    if category(path)=='weights':return abs(float(ref))
    if category(path)=='covariance':return abs(float(ref)) # overridden using diagonal scales below
    if category(path) in ('g','SE','beta'):
        e=np.asarray(case['epsilon_mm']); y=np.asarray(case['response_n'])
        power=3 if 'model_b' not in path else 2
        column=e**power if '.beta[1]' in path else e
        value=float(np.linalg.norm(y)/np.linalg.norm(column))
        return value*1000 if 'n_per_m' in path and 'n_per_mm' not in path else value
    return max(max(abs(x) for x in case['response_n']),case['params']['sigma0_n'])


def margins(c,p):
    out={}
    for k,t in [('relative_se','tol_se'),('model_difference','tol_model')]:
        v=c['items'][k]['value'];out[k]=(Decimal.from_float(float(p[t])) if isinstance(v,Decimal) else p[t])-v if v is not None else None
    v=c['items']['nested_stability']['maximum_relative_shift']
    out['nested_stability']=(Decimal.from_float(float(p['tol_nested'])) if isinstance(v,Decimal) else p['tol_nested'])-v if v is not None else None
    for i,h in enumerate(c['holdout']):out[f'holdout[{i}]']=h['limit_n']-h['error_n'] if h['limit_n'] is not None else None
    return out


def run():
    frozen=json.loads((OUT/'comparison_rule_freeze.json').read_text())
    for rel,digest in frozen['sha256'].items():
        if sha(ROOT/rel)!=digest:raise RuntimeError('frozen source changed '+rel)
    if np.__version__!=frozen['numpy']:raise RuntimeError('runtime drift')
    if (OUT/'arithmetic_comparison.json').exists():raise RuntimeError('results exist; do not overwrite')
    from cfd_sdf.fd08_v2_gate import evaluate_series,load_params
    import analyze_fd08_v2_numeric_contract as numeric
    import fd08_v2_forward_error as forward
    source=load_module('stage1_synthetic',ROOT/'scripts/simulate_fd08_v2_gate.py')
    blind=load_module('frozen_stage1_blind',OLD/'independent_checker.py')
    params=load_params();new=[]
    for spec in frozen['seeds']:
        n=spec['n'];e=np.geomspace(.5 if n!=8 else .3,spec['upper_mm'],n)
        scenario=source.scenarios()[spec['scenario']-1]
        y=source.observation(scenario,e,np.random.Generator(np.random.PCG64(spec['seed'])))
        new.append(dict(id=f"unseen_{scenario['id']}_n{n}_upper{spec['upper_mm']}",epsilon_mm=e.tolist(),response_n=y.tolist(),params=params,seed=spec['seed']))
    save(OUT/'unseen_synthetic_inputs.json',round12(dict(cases=new)))
    new=json.loads((OUT/'unseen_synthetic_inputs.json').read_text())['cases']
    historical=json.loads((OLD/'synthetic_inputs.json').read_text())['cases']
    rows=[];ulp_rows=[];semantic_fail=[];bound_fail=[];convergence_fail=[];conditions=[];archived=[];all_results=[];precision_records=[];ambiguities=[];bound_diagnostics=[];magnitude_certifications=[]
    with localcontext() as context:
        context.prec=120
        for ix,case in enumerate(new+historical):
            e,y,p=case['epsilon_mm'],case['response_n'],case['params'];identifier=case['id'];isnew=ix<len(new)
            refraw=numeric.reference_series(e,y,p,precision=80,decimal_output=True)
            refhigh=numeric.reference_series(e,y,p,precision=120,decimal_output=True)
            ref=common(refraw);high=common(refhigh);rf=dict(flatten(ref));hf=dict(flatten(high))
            max_convergence=Decimal(0);max_scaled_convergence=Decimal(0)
            for path,v in rf.items():
                if isinstance(v,Decimal) and isinstance(hf.get(path),Decimal):
                    error=abs(v-hf[path]);scale=max(abs(hf[path]),Decimal.from_float(mixed_scale(path,hf[path],case)),Decimal('1e-300'))
                    max_convergence=max(max_convergence,error);max_scaled_convergence=max(max_scaled_convergence,error/scale)
                    if error>Decimal('1e-60')*scale:convergence_fail.append(dict(case=identifier,path=path,error=str(error)))
                elif v!=hf.get(path):convergence_fail.append(dict(case=identifier,path=path,semantic=True))
            results={'primary':common(evaluate_series(e,y,p)),'blind':common(blind.evaluate(e,y,p))}
            rawvariants={name:numeric.evaluate_variant(e,y,p,name) for name in ('N1','N2','N3')}
            results.update({name:common(r) for name,r in rawvariants.items()})
            bounds={name:forward.bound_series(e,y,p,variant=name,decimal_output=True) for name in ('N1','N2','N3')}
            bound_high={name:forward.bound_series(e,y,p,variant=name,precision=120,decimal_output=True) for name in ('N1','N2','N3')}
            def all_leaves(v,prefix=''):
                if isinstance(v,dict):
                    for k,x in v.items():
                        if k!='precision_decimal_digits':yield from all_leaves(x,f'{prefix}.{k}' if prefix else k)
                elif isinstance(v,list):
                    for j,x in enumerate(v):yield from all_leaves(x,f'{prefix}[{j}]')
                else:yield prefix,v
            max_bound_scaled=Decimal(0)
            for name,low in bounds.items():
                highleaves=dict(all_leaves(bound_high[name]))
                for path,v in all_leaves(low):
                    hv=highleaves.get(path)
                    if isinstance(v,Decimal) and isinstance(hv,Decimal):
                        scale=max(abs(hv),Decimal('1e-300'))
                        if any(key in path for key in ('radius','l_max','weight_variance_l','sqrt_weight_relative_error')):scale=max(scale,Decimal(1))
                        delta=abs(v-hv)/scale;max_bound_scaled=max(max_bound_scaled,delta)
                        if delta>Decimal('1e-60'):convergence_fail.append(dict(case=identifier,implementation=name,path='bound.'+path,scaled_error=str(delta)))
                    elif v!=hv:convergence_fail.append(dict(case=identifier,implementation=name,path='bound.'+path,semantic=True))
            precision_records.append(dict(case=identifier,max_reference_absolute_delta=str(max_convergence),max_reference_scaled_delta=str(max_scaled_convergence),max_bound_scaled_delta=str(max_bound_scaled)))
            # Both frozen legacy fits are mm; blind only forms dimensionless diagnostics after presentation conversion.
            bounds['primary']=bounds['N1'];bounds['blind']=forward.bound_series(e,y,p,variant='N1',presentation_ratios=True,decimal_output=True)
            for name,raw in rawvariants.items():
                def fits(r):
                    yield 'full_A',r['model_a'];yield 'full_B',r['model_b']
                    for nrow in r['nested']:
                        for m in ('a','b'):yield f"nested{nrow['drop']}_{m}",nrow[f'model_{m}']
                    for h in r['holdout']:yield f"holdout{h['index']}",h['fit']
                for label,f in fits(raw):conditions.append(dict(case=identifier,implementation=name,fit=label,**f['numeric']))
            case_summary={}
            for name,result in results.items():
                diag=bounds[name]['diagnostics']
                bound_diagnostics.append(dict(case=identifier,implementation=name,valid=diag['valid'],ratio_bounds_valid=diag['ratio_bounds_valid'],fits={label:{k:v for k,v in fit.items() if k in ('valid','reason','design_cond2','weighted_design_cond2','pilot_radius','weighted_radius','l_max','covariance_variance_positivity')} for label,fit in diag['fits'].items()}))
                lower=upper=0
                for j,obs in enumerate(y):
                    margin=abs(Decimal.from_float(obs))-Decimal.from_float(p['k_mag'])*Decimal.from_float(p['sigma0_n']);budget=bounds[name]['margins'][f'magnitude[{j}]']
                    lower+=margin-budget>0;upper+=margin+budget>=0
                magnitude_certifications.append(dict(case=identifier,implementation=name,lower_count=lower,upper_count=upper,certified_pass=lower>=4,certified_fail=upper<4))
                if lower<4<=upper:ambiguities.append(dict(case=identifier,unseen=isnew,implementation=name,margin='magnitude_aggregate',lower_count=lower,upper_count=upper))
                actual=dict(flatten(result));bf=dict(flatten(bounds[name]['bounds']));groups=defaultdict(lambda:dict(count=0,c1_fail=0,c2_fail=0,c3_fail=0,c5_fail=0,c5_unavailable=0,max_absolute_forward_error=0.,max_error_over_bound=0.,max_ulp=0))
                for path,v in actual.items():
                    r=rf.get(path)
                    if isinstance(v,(float,int)) and not isinstance(v,bool) and isinstance(r,Decimal):
                        err=abs(Decimal.from_float(float(v))-r);d=max(abs(Decimal.from_float(float(v))),abs(r));b=bf.get(path)
                        valid=b is not None and isinstance(b,(float,int,Decimal)) and math.isfinite(float(b))
                        bound=Decimal.from_float(float(b)) if valid else None
                        c1=err<=Decimal('1e-9')*d
                        subset_n=len(subset_case(path,case)['epsilon_mm'])
                        gamma=(8*subset_n+32)*2**-53/(1-(8*subset_n+32)*2**-53)
                        scale=mixed_scale(path,r,case)
                        if 'covariance' in path:
                            parent,indices=path.split('.covariance');i,j=[int(z.split(']')[0]) for z in indices.split('[')[1:]]
                            scale=math.sqrt(abs(float(rf[f'{parent}.covariance[{i}][{i}]'])*float(rf[f'{parent}.covariance[{j}][{j}]'])))
                        c2=err<=Decimal('1e-9')*d+Decimal.from_float(gamma*scale)
                        ud=ulp(v,float(r));c5=valid and err<=bound
                        g=groups[category(path)];g['count']+=1;g['c1_fail']+=not c1;g['c2_fail']+=not c2;g['c3_fail']+=ud>8
                        g['c5_fail']+=valid and not c5;g['c5_unavailable']+=not valid
                        g['max_absolute_forward_error']=max(g['max_absolute_forward_error'],float(err));g['max_ulp']=max(g['max_ulp'],ud)
                        if valid and bound:g['max_error_over_bound']=max(g['max_error_over_bound'],float(err/bound))
                        if valid and not c5:bound_fail.append(dict(case=identifier,unseen=isnew,implementation=name,path=path,error=str(err),bound=str(bound)))
                        if not valid:bound_fail.append(dict(case=identifier,unseen=isnew,implementation=name,path=path,reason='bound_unavailable'))
                    elif v!=r:semantic_fail.append(dict(case=identifier,unseen=isnew,implementation=name,path=path,actual=v,reference=jsonable(r)))
                # Explicit threshold margin propagation (the same raw C5 component budgets).
                am=margins(result,p);rm=margins(ref,p)
                for key,v in am.items():
                    if v is None:continue
                    if key.startswith('holdout'):
                        prefix=key;bb=bf.get(prefix+'.limit_n');be=bf.get(prefix+'.error_n');budget=None if bb is None or be is None else float(bb)+float(be)
                    else:
                        path={'nested_stability':'items.nested_stability.maximum_relative_shift'}.get(key,f'items.{key}.value');budget=bf.get(path)
                    if budget is None:continue
                    delta=abs(Decimal.from_float(float(v))-rm[key]);budget=Decimal.from_float(float(bounds[name]['margins'][key]))
                    if abs(rm[key])<=budget:ambiguities.append(dict(case=identifier,unseen=isnew,implementation=name,margin=key,reference_margin=str(rm[key]),bound=str(budget)))
                    if delta>budget:bound_fail.append(dict(case=identifier,unseen=isnew,implementation=name,path='margin.'+key,error=str(delta),bound=str(budget)))
                for label,budget in bounds[name]['margins'].items():
                    if budget is None:continue
                    if label.startswith('magnitude['):
                        j=int(label.split('[')[1].split(']')[0]);margin=abs(Decimal.from_float(y[j]))-Decimal.from_float(p['k_mag'])*Decimal.from_float(p['sigma0_n'])
                        if abs(margin)<=budget:ambiguities.append(dict(case=identifier,unseen=isnew,implementation=name,margin=label,reference_margin=str(margin),bound=str(budget)))
                    if label.startswith('sign['):
                        # All exact slope signs are also compared through fit diagnostics.
                        pass
                for path,r in rf.items():
                    if path.endswith('g_n_per_mm') and isinstance(r,Decimal):
                        budget=bf.get(path)
                        if budget is not None and abs(r)<=budget:ambiguities.append(dict(case=identifier,unseen=isnew,implementation=name,margin='sign.'+path,reference_margin=str(r),bound=str(budget)))
                for cat,g in groups.items():rows.append(dict(case=identifier,unseen=isnew,implementation=name,quantity=cat,**g))
                ulp_rows.append(dict(case=identifier,implementation=name,failures_over_8ulp=sum(g['c3_fail'] for g in groups.values()),max_ulp=max(g['max_ulp'] for g in groups.values())))
                case_summary[name]=result
            all_results.append(dict(case=identifier,unseen=isnew,reference80_decimal=decimal_strings(ref),reference120_decimal=decimal_strings(high),implementations=case_summary))
            print(f'validated {ix+1}/66 {identifier}',flush=True)
        # Archived 17 are tested as a consequence against two forward budgets + decimal12 serialization, never relabeled historically.
        mismatches=json.loads((OLD/'independent_comparison.json').read_text())['numeric_mismatches']
        byid={case['id']:case for case in historical}
        for item in mismatches:
            case=byid[item['case']];p=case['params'];base=forward.bound_series(case['epsilon_mm'],case['response_n'],p,variant='N1');other=forward.bound_series(case['epsilon_mm'],case['response_n'],p,variant='N1',presentation_ratios=True)
            path=item['field'];a=item['primary'];b=item['independent'];budget=Decimal.from_float(float(dict(flatten(base['bounds']))[path]))+Decimal.from_float(float(dict(flatten(other['bounds']))[path]))+serialization_bound(a)+serialization_bound(b)
            err=abs(Decimal.from_float(a)-Decimal.from_float(b))
            archived.append(dict(**item,c5_pair_bound_nondimensional=float(budget),c5_consequence_within_bound=err<=budget,ulp_distance=ulp(a,b),historical_strict_status='unmet_preserved'))
    save(OUT/'arithmetic_comparison.json',dict(rows=rows,conditions=conditions,semantic_disagreements=semantic_fail,forward_bound_violations=bound_fail,reference_precision_failures=convergence_fail,precision_convergence=precision_records,forward_bound_diagnostics=bound_diagnostics,magnitude_certifications=magnitude_certifications,numerically_ambiguous_margins=ambiguities,historical_17_future_rule_consequences=archived,
        historical_strict_numeric_condition='unmet 17',reference_independence=False))
    save(OUT/'ulp_comparison.json',dict(allowance=8,diagnostic_only=True,rows=ulp_rows,historical_17=archived,interpretation='Final near-zero diagnostic ULP does not represent operand rounding.'))
    payload=json.dumps(jsonable(dict(cases=all_results)),sort_keys=True,allow_nan=False).encode()
    (OUT/'arithmetic_results.json.gz').write_bytes(gzip.compress(payload,mtime=0))
    stopa=bool(semantic_fail);stopb=bool([x for x in bound_fail if x['unseen']]) or bool(convergence_fail)
    stopc=bool([x for x in semantic_fail if x['implementation'] in ('N1','N2','N3')])
    save(OUT/'unseen_seed_validation.json',dict(rule_freeze_sha256=sha(OUT/'comparison_rule_freeze.json'),fixture_sha256=sha(OUT/'unseen_synthetic_inputs.json'),unseen_cases=len(new),historical_cases=len(historical),stop_a=stopa,stop_b=stopb,stop_c=stopc,
        can_start_decision_design=not(stopa or stopb or stopc),bound_violations=len(bound_fail),semantic_disagreements=len(semantic_fail),precision_failures=len(convergence_fail),numerically_ambiguous_margins=len(ambiguities),
        classification_scope='solver_free_synthetic_only',qualification_flags=source.FLAGS))
    print(json.dumps(json.loads((OUT/'unseen_seed_validation.json').read_text()),sort_keys=True),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--freeze',action='store_true');args=parser.parse_args()
    freeze() if args.freeze else run()
