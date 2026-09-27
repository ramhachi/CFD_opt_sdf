using Enzyme
using WaterLily

const DIMS = (24, 16, 16)
const CENTER = (8.0, 8.0, 8.0)
const D = 4.0
const NU = D / 100.0
const ACTIVE_RHS = CartesianIndex(10, 8, 8)

function build_sim()
    body = WaterLily.AutoBody((x, t) -> sqrt(sum(abs2, x .- CENTER)) - D / 2)
    WaterLily.Simulation(DIMS, (1.0, 0.0, 0.0), D; ν=NU, body,
                         T=Float64, mem=Array)
end

const sim = build_sim()
const weights = [sin(0.17i) + cos(0.11i) for i in eachindex(sim.pois.x)]
const p0 = deepcopy(sim.pois)
const p0_source = 0.2
p0.levels[1].z[ACTIVE_RHS] += p0_source

function poisson_cost!(p)
    WaterLily.poisson_solve!(p)
    return sum(p.x[i] * weights[i] for i in eachindex(p.x))
end

function objective(source_shift)
    p = deepcopy(p0)
    p.levels[1].z[ACTIVE_RHS] += source_shift
    return poisson_cost!(p)
end

println("JULIA_VERSION ", VERSION)
println("WATERLILY_VERSION ", pkgversion(WaterLily))
println("ENZYME_VERSION ", pkgversion(Enzyme))
println("WATERLILY_PR 285 HEAD feed49f480b52047b4e9b8bfacdf3e4f8201106b")
println("EXTENSION_LOADED ", !isnothing(Base.get_extension(WaterLily, :WaterLilyEnzymeCoreExt)))
println("FIXTURE dims=", DIMS, " sphere_diameter=", D, " Re_D=100; Poisson input from sphere Simulation; Float64 Array")

step = 1e-5
fd = (objective(step) - objective(-step)) / (2step)
println("POISSON_CENTERED_FD_D_RHS ", repr(fd))
try
    p = deepcopy(p0)
    dp = Enzyme.make_zero(p)
    result = @time Enzyme.autodiff(Enzyme.ReverseWithPrimal,
                                    poisson_cost!, Enzyme.Active,
                                    Enzyme.Duplicated(p, dp))
    grad = dp.levels[1].z[ACTIVE_RHS]
    println("POISSON_REVERSE_PRIMAL ", repr(result[2]))
    println("POISSON_REVERSE_D_RHS ", repr(grad))
    println("POISSON_REVERSE_VS_FD_RATIO ", repr(grad / fd))
    println("POISSON_REVERSE_DONE")
catch err
    println("POISSON_REVERSE_FAILED ", typeof(err))
    showerror(stderr, err, catch_backtrace())
    println(stderr)
    exit(2)
end
