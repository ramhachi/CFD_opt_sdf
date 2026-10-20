# CPU proof that the GRIDRES-01 Poisson probe is passive: the same small 3-D WaterLily run three times (no probe, no probe, probe sampled every 2 steps)
# must give byte-identical force CSV text and identical u/p fields.  Run 1 vs 2 is the determinism control (a difference there would void the comparison).
# Prints GRIDRES01_PASSIVITY_OK <sha256-of-force-csv> <solves-recorded> on success, errors otherwise.
using WaterLily, SHA
include(joinpath(@__DIR__, "gridres01_poisson_probe.jl"))

function run_once(probe; steps=16)
    n = 16
    sim = Simulation((2n, n, n), (1, 0, 0), n; ν=n / 80, body=AutoBody((x, t) -> sqrt(sum(abs2, x .- (n / 2, n / 2, n / 2))) - n / 4), T=Float32, mem=Array, exitBC=true)
    io = IOBuffer()
    for step in 1:steps
        sim_step!(sim)
        if step % 2 == 0
            f = -WaterLily.pressure_force(sim); v = -WaterLily.viscous_force(sim)
            println(io, step, ",", Float64(sim_time(sim)), ",", join(Float64.(f), ","), ",", join(Float64.(v), ","))
            probe === nothing || probe_sample!(probe, sim, step, sim_time(sim))
        end
    end
    return String(take!(io)), copy(sim.flow.u), copy(sim.flow.p)
end

a, b = run_once(nothing), run_once(nothing)
a == b || error("determinism control failed: two identical probe-free runs differ")
probe = PoissonProbe()
c = run_once(probe)
c[1] == a[1] && c[2] == a[2] && c[3] == a[3] || error("probe is NOT passive: force text or fields differ")
length(probe.rows) == 8 && probe.seen > 0 || error("probe recorded nothing")
println("GRIDRES01_PASSIVITY_OK ", bytes2hex(sha256(c[1])), " solves=", probe.seen, " rows=", length(probe.rows))
haskey(ENV, "GRIDRES01_PROBE_CSV") && write_poisson_csv(ENV["GRIDRES01_PROBE_CSV"], probe)
