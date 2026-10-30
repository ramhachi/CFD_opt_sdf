# Diagnostic-only solver-free FD-07 review: actual WaterLily sign-consistency branch exposure.
# Usage: julia --threads=1 --project=julia/CFDSDFWaterLily scripts/sdf_native_fd07_sign_branch_census.jl <phi-f4-fortran.raw> <origin-x,y,z> <faces.csv>
# Fixed union includes the registered moving ground; no flow step is run.
# Near-zero cutoff is 1e-6 m, seed 1, paired +/-1e-8 m white phi noise.
using WaterLily, Random, SHA
const ROOT=abspath(joinpath(@__DIR__, ".."))
const SRC=joinpath(ROOT,"julia/CFDSDFWaterLily/src")
include(joinpath(SRC,"CFDSDFWaterLily.jl"))
using .CFDSDFWaterLily, .CFDSDFWaterLily.GridSDFBody
Base.include(CFDSDFWaterLily,joinpath(SRC,"V16PhysicalProfile.jl"))
Base.include(CFDSDFWaterLily,joinpath(SRC,"WaterLilyNormalFloorBody.jl"))
const SHAPE=(121,65,49)
const SPACING=Float32(1/30)
const FLOW_ORIGIN=Float32.((-2.5,-1.2,-0.9))
const DIMS=(150,72,54)
function body(phi,origin)
    grid=GridSDF(phi;origin=origin,h=(.025,.025,.025),outside_value=3.,margin_m=.15)
    candidate=CFDSDFWaterLily.NormalFloorWaterLilyBody(grid,FLOW_ORIGIN,SPACING,.25f0)
    return candidate+CFDSDFWaterLily.V16MovingGroundBody(0f0,1f0)
end
function census(path,origin,out)
    ispath(out) && error("refusing to overwrite review artifact: $out")
    mkpath(dirname(out))
    phi=reshape(copy(reinterpret(Float32,read(path))),SHAPE)
    b=body(phi,origin)
    noise=randn(MersenneTwister(1),Float64,SHAPE)
    bp=body(Float32.(Float64.(phi).+1e-8 .*noise),origin)
    bm=body(Float32.(Float64.(phi).-1e-8 .*noise),origin)
    total=0; near=0; candidates=0; flipsplus=0; flipsminus=0; maxdiffplus=0.; maxdiffminus=0.; changedplus=0; changedminus=0
    open(out,"w") do io
        println(io,"i,j,k,d_center_solver,face_axis,d_face_solver,center_plus_solver,center_minus_solver,flip_plus,flip_minus,face_plus_solver,face_minus_solver,mu0_base,mu0_plus,mu0_minus")
        for I in CartesianIndices((2:DIMS[1]+1,2:DIMS[2]+1,2:DIMS[3]+1))
            total+=1
            x=WaterLily.loc(0,I,Float32)
            dc=WaterLily.sdf(b,x,0f0;fastd²=0f0)
            abs(dc)*SPACING<=1e-6 || continue
            near+=1
            dp=WaterLily.sdf(bp,x,0f0;fastd²=0f0)
            dm=WaterLily.sdf(bm,x,0f0;fastd²=0f0)
            for axis in 1:3
                df=WaterLily.sdf(b,WaterLily.loc(axis,I,Float32),0f0;fastd²=0f0)
                abs(df)>.5f0 || continue
                candidates+=1
                fp=signbit(dc)!=signbit(dp); fm=signbit(dc)!=signbit(dm)
                flipsplus+=fp; flipsminus+=fm
                dfp=WaterLily.sdf(bp,WaterLily.loc(axis,I,Float32),0f0;fastd²=0f0)
                dfm=WaterLily.sdf(bm,WaterLily.loc(axis,I,Float32),0f0;fastd²=0f0)
                adjusted(dface,dcenter)=abs(dface)<=.5f0 ? dface : copysign(dface,dcenter)
                mu=WaterLily.μ₀(adjusted(df,dc),1)
                mup=WaterLily.μ₀(adjusted(dfp,dp),1)
                mum=WaterLily.μ₀(adjusted(dfm,dm),1)
                maxdiffplus=max(maxdiffplus,abs(Float64(mup)-mu)); maxdiffminus=max(maxdiffminus,abs(Float64(mum)-mu))
                changedplus+=abs(Float64(mup)-mu)>1e-3; changedminus+=abs(Float64(mum)-mu)>1e-3
                println(io,I[1],",",I[2],",",I[3],",",dc,",",axis,",",df,",",dp,",",dm,",",fp,",",fm,",",dfp,",",dfm,",",mu,",",mup,",",mum)
            end
        end
    end
    println("path=",path," phi_sha256=",bytes2hex(sha256(read(path))))
    println("origin=",origin," centers=",total," near_zero_centers=",near," sign_branch_faces=",candidates," noise1e-8_plus_flips=",flipsplus," minus_flips=",flipsminus)
    println("exposed_faces max_mu0_diff_plus=",maxdiffplus," max_mu0_diff_minus=",maxdiffminus," faces_mu0_delta_gt_1e-3_plus=",changedplus," minus=",changedminus)
    println("WaterLily path=",pathof(WaterLily)," version=",pkgversion(WaterLily)," Body.jl sha256=",bytes2hex(sha256(read(joinpath(dirname(pathof(WaterLily)),"Body.jl")))))
end
length(ARGS)==3 || error("expected raw phi path, origin x,y,z, and fresh output CSV path")
origin=Tuple(parse.(Float64,split(ARGS[2],",")))
census(ARGS[1],origin,ARGS[3])
