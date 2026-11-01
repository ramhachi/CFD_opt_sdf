import numpy as np, math
from scipy import stats
rng=np.random.default_rng(5)
p80=np.array([4.05,2.90,2.70,4.99,4.89,-3.83,-3.37,-12.06,3.99,5.89])
S2=(p80**2).sum(); print("sum Delta80^2 =",round(S2,1)," sqrt=",round(math.sqrt(S2),2), " signed sum/S2 =",round(p80.sum()/S2,4))
def trial(r,SE_T=1.9,P=4,het=0.0,n=20000):
    s_d=SE_T/math.sqrt(P)
    ok_lo=0; ok_sign=0; cover=0; res=[]
    for _ in range(n):
        rr=r*(1+het*rng.standard_normal(10)) if het else r
        par=rng.standard_normal()*s_d
        est=rr*p80+rng.standard_normal(10)*s_d-par
        b=(p80*est).sum()/S2
        resid=est-b*p80; s2=(resid**2).sum()/9
        se=math.sqrt(s2/S2)
        lo=b-stats.t.ppf(0.95,9)*se
        ok_lo+= lo>0.3
        res.append(b)
    return np.mean(res),np.std(res),ok_lo/n
print("r, mean b, sd b, P(90% lower bound > 0.3):")
for SE_T in (1.9,0.95):
    for r in (0.0,0.3,0.5,0.7,1.0):
        print(" SE_T",SE_T,"r",r,[round(float(x),3) for x in trial(r,SE_T)])
print("with 25% heterogeneity in retention, SE_T=1.9:")
for r in (0.5,0.7,1.0):
    print(" r",r,[round(float(x),3) for x in trial(r,1.9,het=0.25)])
