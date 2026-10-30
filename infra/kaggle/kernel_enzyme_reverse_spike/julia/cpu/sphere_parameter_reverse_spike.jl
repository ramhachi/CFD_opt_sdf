using Enzyme
using WaterLily

const DIMS = (24, 16, 16)
const CENTER = (8.0, 8.0, 8.0)
const DIAMETER = 4.0
const NU = DIAMETER / 100.0
const STEPS = 2

function sphere_drag(radius)
    body = WaterLily.AutoBody((x, t) -> sqrt(sum(abs2, x .- CENTER)) - radius)
    sim = WaterLily.Simulation(
        DIMS,
        (1.0, 0.0, 0.0),
        DIAMETER;
        ν = NU,
        body = body,
        T = Float64,
        mem = Array,
    )
    for _ in 1:STEPS
        WaterLily.sim_step!(sim)
    end
    return -WaterLily.total_force(sim)[1]
end

println("JULIA_VERSION ", VERSION)
println("WATERLILY_VERSION ", pkgversion(WaterLily))
println("ENZYME_VERSION ", pkgversion(Enzyme))
println("FIXTURE dims=", DIMS, " center=", CENTER, " radius=", DIAMETER / 2,
        " re_d=100 steps=", STEPS, " precision=Float64 backend=Array")

radius = DIAMETER / 2
step = 1e-3
base = sphere_drag(radius)
fd = (sphere_drag(radius + step) - sphere_drag(radius - step)) / (2 * step)
println("PRIMAL_BASE_DRAG ", repr(base))
println("PRIMAL_CENTERED_FD_RADIUS ", repr(fd))

try
    result = @time Enzyme.autodiff(
        Enzyme.ReverseWithPrimal,
        sphere_drag,
        Enzyme.Active,
        Enzyme.Active(radius),
    )
    grad = only(result[1])
    println("CPU_SPHERE_REVERSE_PRIMAL ", repr(result[2]))
    println("CPU_SPHERE_REVERSE_D_RADIUS ", repr(grad))
    println("CPU_SPHERE_REVERSE_FINITE ", isfinite(grad))
    println("CPU_SPHERE_REVERSE_VS_FD_RATIO ", repr(grad / fd))
    println("CPU_SPHERE_REVERSE_DONE")
catch err
    println("CPU_SPHERE_REVERSE_FAILED ", typeof(err))
    showerror(stderr, err, catch_backtrace())
    println(stderr)
    exit(2)
end
