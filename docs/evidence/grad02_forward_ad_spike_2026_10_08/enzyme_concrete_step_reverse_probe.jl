using Enzyme
using WaterLily

const DIMS = (24, 16, 16)
const CENTER = (8.0, 8.0, 8.0)
const DIAMETER = 4.0
const NU = DIAMETER / 100.0
const STEPS = 2
const ACTIVE_CELL = CartesianIndex(10, 8, 8, 1)

function build_sim()
    body = WaterLily.AutoBody((x, t) -> sqrt(sum(abs2, x .- CENTER)) - DIAMETER / 2)
    return WaterLily.Simulation(
        DIMS,
        (1.0, 0.0, 0.0),
        DIAMETER;
        ν = NU,
        body = body,
        T = Float64,
        mem = Array,
    )
end

const SIM0 = build_sim()
const FT = typeof(SIM0.flow)
const PT = typeof(SIM0.pois)
# concrete-typed step: avoids the dynamic dispatch on Simulation's abstract-typed fields
@noinline concrete_step!(flow::FT, pois::PT) = WaterLily.mom_step!(flow, pois)
function force_after_steps!(sim)
    for _ in 1:STEPS
        concrete_step!(sim.flow::FT, sim.pois::PT)
    end
    return -WaterLily.total_force(sim)[1]
end

function objective_from_initial_cell(delta)
    sim = build_sim()
    sim.flow.u[ACTIVE_CELL] += delta
    return force_after_steps!(sim)
end

println("JULIA_VERSION ", VERSION)
println("WATERLILY_VERSION ", pkgversion(WaterLily))
println("ENZYME_VERSION ", pkgversion(Enzyme))
println("WATERLILY_PR 285 HEAD feed49f480b52047b4e9b8bfacdf3e4f8201106b")
println("FIXTURE dims=", DIMS, " center=", CENTER, " radius=", DIAMETER / 2,
        " re_d=100 steps=", STEPS, " precision=Float64 backend=Array")

sim = build_sim()
shadow = Enzyme.make_zero(sim)
base = force_after_steps!(deepcopy(sim))
fd_step = 1e-5
fd = (objective_from_initial_cell(fd_step) - objective_from_initial_cell(-fd_step)) /
     (2 * fd_step)
println("PRIMAL_BASE_DRAG ", repr(base))
println("PRIMAL_CENTERED_FD_INITIAL_U ", repr(fd))

println("CPU_STATE_REVERSE_BEGIN")
reverse_started_ns = time_ns()
try
    result = Enzyme.autodiff(
        Enzyme.ReverseWithPrimal,
        force_after_steps!,
        Enzyme.Active,
        Enzyme.Duplicated(sim, shadow),
    )
    elapsed = (time_ns() - reverse_started_ns) / 1e9
    grad = shadow.flow.u[ACTIVE_CELL]
    println("CPU_STATE_REVERSE_ELAPSED_S_INCLUDING_JIT ", repr(elapsed))
    println("CPU_STATE_REVERSE_PRIMAL ", repr(result[2]))
    println("CPU_STATE_REVERSE_D_INITIAL_U ", repr(grad))
    println("CPU_STATE_REVERSE_FINITE ", isfinite(grad))
    println("CPU_STATE_REVERSE_VS_FD_RATIO ", repr(grad / fd))
    println("CPU_STATE_REVERSE_DONE")
catch err
    elapsed = (time_ns() - reverse_started_ns) / 1e9
    println("CPU_STATE_REVERSE_ELAPSED_S_INCLUDING_JIT ", repr(elapsed))
    println("CPU_STATE_REVERSE_FAILED ", typeof(err))
    showerror(stderr, err, catch_backtrace())
    println(stderr)
    exit(2)
end
