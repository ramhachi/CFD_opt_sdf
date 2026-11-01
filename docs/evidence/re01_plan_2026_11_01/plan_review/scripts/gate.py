from scipy import stats
import numpy as np
rng=np.random.default_rng(3)
# A: sample SD of P=4 deltas (3 dof). B: pooled batch-means SE estimate with ~19 dof (20 batches) per run, two runs -> sqrt(sum): ~38 dof but sigma_pred has bias/noise
for dfA in (3,33):
    lo=stats.chi2.cdf(dfA*0.25,dfA); hi=stats.chi2.sf(dfA*4,dfA)
    print(f"A dof {dfA}: P(ratio<0.5)={lo:.3f}  P(ratio>2)={hi:.4f}  total={lo+hi:.3f}")
# with B noise (19 dof per run, two runs)
n=400000
A=np.sqrt(rng.chisquare(3,n)/3)
B=np.sqrt((rng.chisquare(19,n)/19 + rng.chisquare(19,n)/19)/2)
r=A/B
print("A(3 dof)/B(19+19 dof) outside [0.5,2]:",np.mean((r<0.5)|(r>2)))
print("any of 11 designs fails (indep):",1-(1-np.mean((r<0.5)|(r>2)))**11)
# t3 false-resolution
print("P(|t_3|>=3)=",2*stats.t.sf(3,3)," P(|t_1|>=3)=",2*stats.t.sf(3,1), " P(|t_33|>=3)=",2*stats.t.sf(3,33))
print("90% CI of s/sigma with 3 dof:",np.sqrt(stats.chi2.ppf([0.05,0.95],3)/3), " 1 dof:",np.sqrt(stats.chi2.ppf([0.05,0.95],1)/1))
# domain control: two independent runs, SE_T 1.9% each, threshold 2%
from math import sqrt
for P in (1,2,4):
    sd=sqrt(2)*1.9/sqrt(P)
    print(f"domain control, P={P}: noise sd of difference {sd:.2f}%; P(|diff|>2% | no effect)={2*stats.norm.sf(2/sd):.2f}; power to see a true 3% effect={stats.norm.sf((2-3)/sd)+stats.norm.cdf((-2-3)/sd):.2f}")
