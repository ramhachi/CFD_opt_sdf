"""Unregistered budget arithmetic and input-only ladder conditioning; no solver."""
import json
from pathlib import Path
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'docs/evidence/fd08_v2_stage1p5_2026_10_06'


def anchor(path,text):
    lines=(ROOT/path).read_text().splitlines()
    matches=[i for i,line in enumerate(lines,1) if text in line]
    if len(matches)!=1:raise ValueError(f'nonunique anchor: {path} {text}')
    return f'{path}:{matches[0]}'


def costs(count):
    solver=count*108.7;elapsed=count*182.7
    return dict(states=count,solver_s=round(solver,4),elapsed_s=round(elapsed,4),
                solver_20pct_s=round(solver*1.2,4),elapsed_20pct_s=round(elapsed*1.2,4),
                within_current_solver_with_margin=solver*1.2<=5400,
                within_current_kernel_with_margin=elapsed*1.2<=10800)


def report():
    budgets=[dict(label=f'4directions_6epsilon_baseline1_jitter{j}_per_direction',**costs(49+4*j)) for j in (0,2,4)]
    budgets += [dict(label='4directions_8epsilon_baseline1_nojitter',**costs(65)),
                dict(label='formal_pairs_only',**costs(24)),dict(label='formal_with_baseline1',**costs(25)),
                dict(label='recommended_total_two_separate_rounds',**costs(74))]
    ladders=[]
    for label,lower,upper,n in [('L6',.5,5,6),('L8',.3,5,8),('L15',.5,15,7)]:
        e=np.geomspace(lower,upper,n);conditions=[]
        for model,power in [('A',3),('B',2)]:
            for variant,scale in [('N1',1),('N2',1000),('N3',max(e))]:
                native=e/scale;x=np.column_stack((native,native**power))
                conditions.append(dict(model=model,variant=variant,unweighted_cond2=float(np.linalg.cond(x)),normal_cond2=float(np.linalg.cond(x)**2)))
        indices=sorted({0,(n-2)//2,n-2})
        formal=[float(np.sqrt(e[i]*e[i+1])) for i in indices]
        assert all(lower<x<upper for x in formal)
        assert not set(formal)&set(e)
        ladders.append(dict(id=label,epsilon_mm=e.tolist(),span=upper/lower,n=n,dof=n-2,
                            minimum_nested_sign_points=n-3,minimum_nested_stability_points=n-2,
                            holdouts=n-2,holdout_fit_dof=n-3,formal_interval_indices=indices,
                            formal_epsilon_mm=formal,conditions=conditions))
    anchors={
      'solver_budget':anchor('docs/evidence/xfid_candidate_c_2026_10_04/xfidc_criteria.json','"aggregate_solver_wall_time_limit_s": 5400.0'),
      'kernel_limit':anchor('docs/phase_plan.md','with a 10,800-second Kaggle run limit.'),
      'r5_kernel_limit':anchor('docs/phase_plan.md','and the requested execution timeout is 10,800 s.'),
      'ladder_min_count':anchor('src/cfd_sdf/fd08_calibration.py','MINIMUM_CALIBRATION_EPSILON_COUNT = 7'),
      'ladder_span':anchor('src/cfd_sdf/fd08_calibration.py','MINIMUM_CALIBRATION_SPAN_RATIO = 100.0'),
      'ladder_validator':anchor('src/cfd_sdf/fd08_calibration.py','def validate_calibration_ladder(')}
    return dict(evidence_class='solver_free_contract_design_unregistered',runtime_assumptions=dict(solver_s_per_state=108.7,overhead_s_per_state=74.0,elapsed_s_per_state=182.7,provenance='fixed Stage1 design table and supplied R5 aggregate; no R5 raw read'),current_limits=dict(solver_s=5400,kernel_s=10800),budget_rows=budgets,ladder_options=ladders,source_anchors=anchors,recommended=False)


if __name__=='__main__':
    print(json.dumps(report(),sort_keys=True,indent=2,allow_nan=False))
