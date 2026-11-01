import math
# --- measured anchors (SCREEN-01 kernel summaries, flow_32 f32a and flow_48 f48k13) ---
L=0.8; c=1.2192; alpha=math.radians(20.395); t=0.1153
dims={32:(200,96,72),48:(300,144,108),64:(400,192,144),96:(600,288,216),128:(800,384,288)}
cells={n:a*b*d for n,(a,b,d) in dims.items()}
# measured: flow_32 13,500 steps / 120 CU, wall 347 s solve (410-440 s with overhead); flow_48 26,360 steps, 2424 s
rate32=cells[32]*13500/347; rate48=cells[48]*26360/2424
print("cell-steps/s T4: flow_32 %.2e flow_48 %.2e"%(rate32,rate48))
rate=5.1e7
# CFL rule (WaterLily 1.8 Flow.jl): dt = min(10, 1/(max flux_out + 5 nu)), nu = n/Re (lattice)
# infer max flux from measured dt
dt32=120*32/13500; dt48=120*48/26360
mf32=1/dt32-5*32/80; mf48=1/dt48-5*48/80
print("dt32 %.3f dt48 %.3f -> inferred max flux %.2f %.2f"%(dt32,dt48,mf32,mf48))
mf=1.55  # lattice units; at higher Re local velocities may be larger (separation) -> use 1.8 as pessimistic
def steps(n,Re,T,mf=1.55):
    nu=n/Re; dt=min(10,1/(mf+5*nu)); return T*n/dt, dt
print("\nRe  n   cells(M)  dt   steps(T=120)  solve_h  wall_h(+20%)  mem_GB(128B/cell)  delta_lam/h  cells_per_delta")
for Re in [80,250,800,2500,8000,25000]:
    Rec=Re*c/L
    delta=5*c/math.sqrt(Rec)   # Blasius at trailing edge, laminar
    for n in [32,48,64,96,128]:
        st,dt=steps(n,Re,120)
        solve=cells[n]*st/rate/3600
        h=L/n
        print("%5d %3d %7.2f %6.3f %9.0f %8.2f %8.2f %8.2f %10.2f %8.1f"%(Re,n,cells[n]/1e6,dt,st,solve,solve*1.2,cells[n]*128/1e9,delta/h,delta/h))
print("\nRe_c (chord) and Re_t (thickness) for ladder:")
for Re in [80,250,800,2500,8000,25000,1e5,5e5]:
    print(" Re_L=%g  Re_c=%.0f  Re_t=%.0f  Re_projected_width=%.0f"%(Re,Re*c/L,Re*t/L,Re*c*math.sin(alpha)/L))
# shedding period estimate: St ~0.17 on projected width w=c sin(alpha)+t cos(alpha)
w=c*math.sin(alpha)+t*math.cos(alpha)
Tsh=w/0.17/1.0   # seconds with U=1 m/s
print("\nprojected width w=%.3f m, shedding period ~%.2f s = %.2f convective units (L/U=0.8 s)"%(w,Tsh,Tsh/0.8))
for ncyc in [20,50,100]:
    print(" %d cycles = %.0f CU; plus 80 CU burn-in -> T=%.0f CU (x%.2f of current 120)"%(ncyc,ncyc*Tsh/0.8,80+ncyc*Tsh/0.8,(80+ncyc*Tsh/0.8)/120))
# OpenFOAM anchors (local Docker, Apple M4 Rosetta, 1 core/case): V2 212,822 cells 1562 it in 31 min; V3 1.461M cells 8-10 s/it
print("\nOpenFOAM laminar simpleFoam cost: V2 %.2f us/cell-iter, V3 %.2f-%.2f us/cell-iter"%(31*60/1562/212822*1e6, 8/1.461e6*1e6, 10/1.461e6*1e6))
us=6.0
for name,ncell,nit,fac in [("laminar 3D Re 250-2500, V2-like 0.2M, 3000 it",0.213e6,3000,1.0),("laminar 3D V3 1.46M, 4500 it",1.461e6,4500,1.0),("pimpleFoam laminar unsteady V2 0.2M, 40k steps x2 PISO",0.213e6,40000,1.5),("RANS SST 3D 3M cells, 3000 it, x1.8 for k-omega",3e6,3000,1.8),("RANS SST 3D 8M cells, 3000 it",8e6,3000,1.8)]:
    sec=ncell*nit*us*1e-6*fac
    print(" %-55s %8.1f h/case (1 core)   %6.1f h at 4 cores (eff 0.8)"%(name,sec/3600,sec/3600/4/0.8))
# wall-function first cell for RANS at Re_c 5e5 (c=1.22 m, U=1, nu=2.44e-6 m2/s): Cf ~0.0045 -> u_tau
for Rec in [1e5,5e5,1e6]:
    nu=1.0*c/Rec; Cf=0.074/Rec**0.2; utau=math.sqrt(Cf/2)*1.0
    yplus30=30*nu/utau
    print(" Re_c=%.0e: nu=%.2e, Cf=%.4f, u_tau=%.4f, y(y+=30)=%.2e m = %.2e c; laminar delta_TE/c=%.3f"%(Rec,nu,Cf,utau,yplus30,yplus30/c,5/math.sqrt(Rec)))
# force scale: parent downforce 0.266 N -> CL with planform 1.067 m^2, rho=1, U=1
print("\nparent CL=%.3f CD=%.3f (flow_48 viscous share of drag 463/1026=%.2f)"%(0.266/(0.5*1.067),0.284/(0.5*1.067),463.3/1026.6))
