using WaterLily, Statistics, Printf, LinearAlgebra
function run2d(n, Re; T=60.0, alpha=deg2rad(20.395))
    s=n/32
    nx,nz = round(Int,200s), round(Int,72s)
    c = 1.2192/0.8*n; t = 0.1153/0.8*n
    cx, cz = (2.4875/0.8)*n, (0.9/0.8)*n
    h = (c-t)/2
    ax,az = cx - h*cos(alpha), cz - h*sin(alpha)
    bx,bz = cx + h*cos(alpha), cz + h*sin(alpha)
    function sdf(x,tt)
        px,pz = x[1],x[2]; abx,abz=bx-ax,bz-az; u=clamp(((px-ax)*abx+(pz-az)*abz)/(abx^2+abz^2),0,1)
        return sqrt((px-(ax+u*abx))^2+(pz-(az+u*abz))^2) - t/2
    end
    sim = Simulation((nx,nz),(1,0),n; ν=n/Re, body=AutoBody(sdf), T=Float32, exitBC=true)
    mf=Float64[]; Fz=Float64[]; ts=Float64[]
    tcu = 0.0
    while tcu < T
        tcu += 0.1
        sim_step!(sim, tcu; remeasure=false)
        push!(mf, 1/sim.flow.Δt[end]-5*sim.flow.ν); push!(ts, sim_time(sim))
        F = WaterLily.pressure_force(sim); push!(Fz, F[2])
    end
    sel = ts .> T/2
    nsteps = length(sim.flow.Δt)-1
    fz = Fz[sel]
    return (; n, Re, nsteps, steps_per_CU = nsteps/ sim_time(sim), mfmax=maximum(mf[sel]), mfmean=mean(mf[sel]), Fzmean=mean(fz), relrms=std(fz)/abs(mean(fz)))
end
for n in (32,48), Re in (80,250,800,2500)
    r = run2d(n, Re; T=60.0)
    @printf("n=%d Re=%5d steps=%6d steps/CU=%6.1f  maxflux(max|mean, 2nd half)=%.2f|%.2f   Fz mean=%.3f rms/mean=%.3f\n", r.n, r.Re, r.nsteps, r.steps_per_CU, r.mfmax, r.mfmean, r.Fzmean, r.relrms)
    flush(stdout)
end
