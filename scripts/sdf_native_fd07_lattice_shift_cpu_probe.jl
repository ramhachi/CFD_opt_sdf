# Diagnostic only: fixed 10-call preregistered lattice phase/noise matrix.
# Usage: julia -t 4 --project=julia/CFDSDFWaterLily scripts/sdf_native_fd07_lattice_shift_cpu_probe.jl <prepared_outdir>
using WaterLily, Random, SHA, Statistics
const SRC = joinpath(@__DIR__, "..", "julia", "CFDSDFWaterLily", "src")
include(joinpath(SRC, "CFDSDFWaterLily.jl"))
using .CFDSDFWaterLily
using .CFDSDFWaterLily.GridSDFBody
for f in ("V16PhysicalProfile.jl", "V16W4Sensitivity.jl", "WaterLilyNormalFloorBody.jl")
    Base.include(CFDSDFWaterLily, joinpath(SRC, f))
end
const SHAPE = (121, 65, 49)
const H = 0.025
const ORIGIN = (-1.0, -0.8, -0.6)
const SHIFT = (0.27, 0.37, 0.43)
const CASE = only(filter(c -> c.case_id == "flow_24", CFDSDFWaterLily.V16W4Sensitivity.w4_cases(ORIGIN, H)))

function immutable_open(f, path)
    ispath(path) && error("refusing existing artifact: $path")
    mkpath(dirname(path))
    open(f, path, "w")
end

function main(outdir)
    plan = joinpath(outdir, "plan.json")
    isfile(plan) || error("persistent preregistration absent")
    immutable_open(joinpath(outdir, "runtime.txt")) do io
        println(io, "plan_sha256=", bytes2hex(sha256(read(plan))))
        println(io, "julia_version=", VERSION, " threads=", Threads.nthreads())
        println(io, "kernel=", Sys.KERNEL, " arch=", Sys.ARCH, " cpu=", Sys.CPU_NAME)
        println(io, "WaterLily_version=", Base.pkgversion(WaterLily), " package=", pkgdir(WaterLily))
        for (dir, _, files) in walkdir(joinpath(pkgdir(WaterLily), "src")), file in sort(files)
            endswith(file, ".jl") || continue
            path = joinpath(dir, file)
            println(io, bytes2hex(sha256(read(path))), "  ", path)
        end
    end
    noise = randn(MersenneTwister(1), Float64, SHAPE)
    immutable_open(joinpath(outdir, "noise_f8_fortran.raw")) do io
        write(io, noise)
    end
    immutable_open(joinpath(outdir, "initial_fields_and_realized_noise.csv")) do stats
        println(stats, "lattice,run_id,noise_sha256,changed_nodes,rms_delta_phi_m,max_delta_phi_m,mu0_changed,mu0_max_delta,mu0_rms_delta,mu1_changed,mu1_max_delta,mu1_rms_delta")
        for lattice in ("control", "shifted")
            origin = lattice == "control" ? ORIGIN : ntuple(i -> ORIGIN[i] + H * SHIFT[i], 3)
            base = reshape(copy(reinterpret(Float32, read(joinpath(outdir, lattice, "phi.raw")))), SHAPE)
            mu0_base = nothing; mu1_base = nothing
            for (run_id, eps) in (("baseline", 0.0), ("noise_seed1@+1e-8", 1e-8), ("noise_seed1@-1e-8", -1e-8), ("noise_seed1@+1e-7", 1e-7), ("noise_seed1@-1e-7", -1e-7))
                started = time()
                phi = eps == 0.0 ? copy(base) : Float32.(Float64.(base) .+ eps .* noise)
                delta = Float64.(phi) .- Float64.(base)
                grid = GridSDF(phi; origin, h=(H,H,H), outside_value=3.0, margin_m=0.15)
                cand = CFDSDFWaterLily.NormalFloorWaterLilyBody(grid, Float32.(CASE.flow_origin_m), Float32(CASE.flow_spacing_m), 0.25f0)
                ground = CFDSDFWaterLily.V16MovingGroundBody(0f0, 1f0)
                sim = WaterLily.Simulation(CASE.flow_dims, CFDSDFWaterLily.v16_native_far_field_uBC,
                    Float32(CASE.solver_length); U=Float32(CASE.solver_velocity), ν=Float32(CASE.solver_viscosity),
                    exitBC=true, body=cand+ground, T=Float32, mem=Array)
                if eps == 0.0
                    mu0_base = copy(sim.flow.μ₀); mu1_base = copy(sim.flow.μ₁)
                end
                d0 = Float64.(sim.flow.μ₀) .- Float64.(mu0_base)
                d1 = Float64.(sim.flow.μ₁) .- Float64.(mu1_base)
                println(stats, join((lattice,run_id,bytes2hex(sha256(reinterpret(UInt8,vec(noise)))),
                    count(!iszero,delta),sqrt(mean(abs2,delta)),maximum(abs,delta),
                    count(!iszero,d0),maximum(abs,d0),sqrt(mean(abs2,d0)),
                    count(!iszero,d1),maximum(abs,d1),sqrt(mean(abs2,d1))), ","))
                flush(stats)
                immutable_open(joinpath(outdir,lattice,run_id*".csv")) do io
                    println(io,"step,t_u_l,drag_solver,downforce_solver,pressure_fx_solver,viscous_fx_solver,pressure_downforce_solver,viscous_downforce_solver")
                    step=0
                    while sim_time(sim) < 3.0
                        sim_step!(sim); step+=1
                        if step % 8 == 0 || sim_time(sim) >= 3.0
                            p=-WaterLily.pressure_force(sim.flow,cand); v=-WaterLily.viscous_force(sim.flow,cand)
                            f=p+v
                            all(isfinite,f) || error("nonfinite diagnostic force")
                            println(io,join((step,sim_time(sim),f[1],-f[3],p[1],v[1],-p[3],-v[3]),","))
                        end
                    end
                end
                println(stderr,lattice,"/",run_id," done ",round(time()-started;digits=1)," s")
                GC.gc()
            end
        end
    end
end
main(only(ARGS))
