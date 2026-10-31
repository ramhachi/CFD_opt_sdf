import numpy as np, math
rng=np.random.default_rng(2)
p80=np.array([4.05,2.90,4.89])  # finalist, M, W4 (% of parent)
def run(r,SE_T=1.9,n=200000):
    s32=SE_T/2; s48=SE_T/math.sqrt(2)
    par32=rng.standard_normal(n)*s32; par48=rng.standard_normal(n)*s48
    e32=r*p80+rng.standard_normal((n,3))*s32[...,None] if False else r*p80+rng.standard_normal((n,3))*s32-par32[:,None]
    e48=r*p80+rng.standard_normal((n,3))*s48-par48[:,None]
    allsame48=(e48>0).all(1)       # cond 3 (sign as Re80)
    final_diff=(e32[:,0]>0)!=(e48[:,0]>0)
    ndiff=((e32>0)!=(e48>0)).sum(1)
    reslim=final_diff|(ndiff>=2)
    return allsame48.mean(), final_diff.mean(), reslim.mean()
print("r : P(cond3 all-3-sign-ok) P(finalist sign differs) P(RESOLUTION_LIMITED)")
for r in (1.5,1.0,0.7,0.5,0.3):
    print(r,[round(x,3) for x in run(r)])
