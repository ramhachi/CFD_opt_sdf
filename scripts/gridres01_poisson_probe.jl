# GRIDRES-01 passive Poisson probe (plan Amendment 2 H1).  Included by the job (and by the CPU passivity check) after `using WaterLily`.
# It only READS solver state: the host vector `sim.pois.n` (iterations of every pressure solve, pushed by WaterLily's own `solver!`) and
# `L₂(sim.pois.levels[1])` = r⋅r of the finest-level residual left by the last solve (the quantity the solver's own tol test uses).
# Nothing is called that writes a field, changes a solver setting or reorders work; `scripts/gridres01_poisson_passivity_check.jl` shows it on CPU.
const POISSON_ITERATION_CAP = 32   # WaterLily 1.8.0 MultiLevelPoisson.jl:108 `solver!(ml; tol=1e-4, itmx=32)`
const POISSON_CSV_HEADER = "step,t_u_l,solves,iters_sum,iters_max,solves_at_cap,final_residual_l2,iters"

mutable struct PoissonProbe
    seen::Int                # solves already attributed to an earlier sample
    rows::Vector{String}
end
PoissonProbe() = PoissonProbe(0, String[])

function probe_sample!(probe::PoissonProbe, sim, step, t)
    n = Int.(sim.pois.n[probe.seen+1:end])         # slice copy of the host vector; iteration counts since the previous sample
    probe.seen = length(sim.pois.n)
    r2 = Float64(L₂(sim.pois.levels[1]))           # read-only reduction over the residual array
    push!(probe.rows, join((step, Float64(t), length(n), sum(n), isempty(n) ? 0 : maximum(n), count(==(POISSON_ITERATION_CAP), n), r2, join(n, " ")), ","))
    return nothing
end

write_poisson_csv(path, probe::PoissonProbe) = open(path, "w") do io
    println(io, POISSON_CSV_HEADER)
    foreach(row -> println(io, row), probe.rows)
end
