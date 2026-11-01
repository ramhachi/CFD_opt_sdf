import math
dims={32:(200,96,72),48:(300,144,108),64:(400,192,144),96:(600,288,216)}
cells={n:a*b*c for n,(a,b,c) in dims.items()}
rate=5.2e7   # cell-steps/s measured on T4
oh=1.2
def steps(n,Re,T,mf): 
    nu=n/Re; dt=min(10,1/(mf+5*nu)); return T*n/dt
def wall_h(n,Re,T,mf): return cells[n]*steps(n,Re,T,mf)/rate/3600*oh
print("measured check: flow_32 Re80 T=120 mf=1.53 -> steps %.0f (measured 13464-13651), wall %.0f s"%(steps(32,80,120,1.53),cells[32]*steps(32,80,120,1.53)/rate))
print("dt ratios Re80 vs rung for n=32 (steps/CU Re80 / steps/CU rung) by max-flux assumption:")
for mf in (1.55,2.0,2.5,3.0,3.5):
    row=[]
    for Re in (250,800,2500):
        row.append(round(steps(32,80,1,1.55)/steps(32,Re,1,mf),2))
    print("  mf=%.2f"%mf,row," (>1 means rung cheaper per CU than Re-80 baseline mf=1.55)")
# per-rung totals
def rung(Re,Twin,mf,Tb=80,P=4):
    T=Tb+Twin
    f32=12*P*wall_h(32,Re,T,mf)
    f48=4*2*wall_h(48,Re,T,mf)   # plan: 4 confirmation states x 2 phases
    f64=2*wall_h(64,Re,T,mf)
    return f32,f48,f64,f32+f48+f64
print("\nGPU h per rung (flow_32 12x4, flow_48 4x2, flow_64 2x1), burn-in 80 CU")
for Re in (800,2500):
    for Twin in (220,400,800):
        for mf in (1.55,2.5):
            r=rung(Re,Twin,mf); print(f" Re {Re} window {Twin:4d} mf {mf}: f32 {r[0]:5.1f} f48 {r[1]:5.1f} f64 {r[2]:5.1f} total {r[3]:6.1f} h; flow_64 single run {wall_h(64,Re,80+Twin,mf):.1f} h")
# R1 steady: 120 CU, P=4 12 states f32, 4 states*2 f48
Re=250
for mf in (1.55,2.5):
    t=12*4*wall_h(32,Re,120,mf)+4*2*wall_h(48,Re,120,mf)
    print("R1 (120 CU) mf",mf,": %.1f h"%t)
print("\nSession-limit check: kernel packing with 12 h = 43200 s; flow_64 single run at cap (880 CU)")
for mf in (1.55,2.5,3.5):
    for Re in (800,2500):
        print("  Re",Re,"mf",mf,"flow_64 880 CU: %.1f h ; flow_48 880 CU: %.1f h ; flow_32 880 CU %.2f h"%(wall_h(64,Re,880,mf),wall_h(48,Re,880,mf),wall_h(32,Re,880,mf)))
# total
tot=lambda mf,Tw: rung(800,Tw,mf)[3]+rung(2500,Tw,mf)[3]+ (12*4*wall_h(32,250,120,mf)+8*wall_h(48,250,120,mf))
print("\nR1+R2+R3 at window 220/400/800 and mf 1.55/2.5:")
for Tw in (220,400,800):
    print("  Tw",Tw,[round(tot(mf,Tw),1) for mf in (1.55,2.5)])
