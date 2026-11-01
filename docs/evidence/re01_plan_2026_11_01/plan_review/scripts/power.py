import numpy as np, math
from scipy import stats
rng=np.random.default_rng(1)
F0=0.265779
names=["finalist","M","cam-11.3","C1","W4","W5","W3","C4","W8","W6"]
d80=np.array([1.077e-2,7.71e-3,7.184e-3,1.326e-2,1.300e-2,-1.018e-2,-8.953e-3,-3.204e-2,1.061e-2,1.565e-2])
p80=100*d80/F0
print("Re80 delta % of parent:",dict(zip(names,np.round(p80,2))))
# ---- 1. SE_T vs window
print("\n== SE_T (% of mean) = rms% * sqrt(2 tau/T)")
for rms in (5,10,20):
    for tau in (2,3.9,8,15):
        T196=lambda se: 2*tau*(rms/se)**2
        print(f"rms {rms:2d}% tau {tau:4.1f} CU: SE@216CU={rms*math.sqrt(2*tau/216):5.2f}%  SE@800CU={rms*math.sqrt(2*tau/800):5.2f}%  T for 1.9% = {T196(1.9):7.0f} CU ; T for 0.95% = {T196(0.95):7.0f}")
# ---- 2. batch means requirement
print("\n== estimator B needs T >= 20 batches * 5 tau = 100 tau :", {tau:100*tau for tau in (2,3.9,8,15)})
# ---- 3. MDE
print("\n== finalist power at SE_T=1.9%, P=4: 3 SE_eff =",3*math.sqrt(2)*1.9/2,"% of parent; finalist gain 4.05%")
# ---- 4. simulate
def sim(r,SE_T=1.9,P=4,n=40000,het=0.0,df_est=True):
    se_d=SE_T/math.sqrt(P)            # design-mean noise (%)
    se_eff=math.sqrt(2)*SE_T/math.sqrt(P)
    res=dict(c1=0,c2=0,c4=0,all=0,flip=0)
    for _ in range(n):
        rr=r*(1+het*rng.standard_normal(10)) if het else r
        true=rr*p80
        par=rng.standard_normal()*se_d
        est=true+rng.standard_normal(10)*se_d-par
        # estimated SE_eff from sigma_d with P-1 dof (shared across designs by pooling? use finalist's own)
        if df_est:
            s=se_eff*math.sqrt(rng.chisquare(P-1)/(P-1))
        else: s=se_eff
        c1 = (np.sign(est[0])==np.sign(p80[0])) and abs(est[0])>=3*s
        res['c1']+=c1
        resolvable=np.abs(p80)>=3*s
        keep=(np.sign(est)==np.sign(p80))
        c2 = resolvable.sum()>0 and keep[resolvable].mean()>=0.75
        tau=stats.kendalltau(p80,est)[0]
        c4=tau>=0.6
        res['c2']+=c2; res['c4']+=c4; res['all']+=(c1 and c2 and c4)
        res['flip']+= (est[0]<-3*s)
    return {k:v/n for k,v in res.items()}
print("\n== P(cond) vs true uniform retention r, SE_T=1.9% (target), P=4, sigma_d estimated with 3 dof")
for r in (1.3,1.0,0.7,0.5,0.3):
    print(" r=%.1f"%r, {k:round(v,3) for k,v in sim(r).items()})
print("\n== same with SE_T=0.95% (4x window)")
for r in (1.0,0.7,0.5,0.3):
    print(" r=%.1f"%r, {k:round(v,3) for k,v in sim(r,SE_T=0.95).items()})
print("\n== same with SE_T=1.9% but heterogeneity 25% in retention")
for r in (1.0,0.7):
    print(" r=%.1f"%r, {k:round(v,3) for k,v in sim(r,het=0.25).items()})
# null: no effect at all (r=0): P(any false 'resolved flip' for finalist)
print("\n== null r=0:", {k:round(v,3) for k,v in sim(0.0).items()})
# tau distribution attenuation
def tau_dist(r,SE_T,n=20000,P=4):
    se_d=SE_T/math.sqrt(P); t=[]
    for _ in range(n):
        est=r*p80+rng.standard_normal(10)*se_d
        t.append(stats.kendalltau(p80,est)[0])
    t=np.array(t); return t.mean(), np.mean(t>=0.6), np.mean(t<0.3)
print("\n== Kendall tau (design noise only; parent offset is rank-neutral): mean, P(tau>=.6), P(tau<.3)")
for se in (0.3,0.95,1.9):
    print(" SE_T=%.2f%% r=1:"%se, np.round(tau_dist(1.0,se),3), " r=0.5:",np.round(tau_dist(0.5,se),3))
