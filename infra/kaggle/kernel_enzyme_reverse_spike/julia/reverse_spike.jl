using CUDA
using Enzyme
using WaterLily

const DIMS = (24, 16, 16)
const CENTER = (8.0f0, 8.0f0, 8.0f0)
const DIAMETER = 4.0f0
const NU = DIAMETER / 100.0f0
const STEPS = 2
const ACTIVE_CELL = CartesianIndex(10, 8, 8, 1)

function build_sim()
    body = WaterLily.AutoBody((x, t) -> sqrt(sum(abs2, x .- CENTER)) - DIAMETER / 2)
    return WaterLily.Simulation(DIMS, (1.0f0, 0.0f0, 0.0f0), DIAMETER;
                                ν=NU, body, T=Float32, mem=CUDA.CuArray)
end

function force_after_steps!(sim)
    for _ in 1:STEPS
        WaterLily.sim_step!(sim; remeasure=false)
    end
    return -WaterLily.total_force(sim)[1]
end

function quadratic(x)
    return sum(abs2, x)
end

function poisson_cost!(p, weights)
    WaterLily.poisson_solve!(p)
    return sum(p.x .* weights)
end

function poisson_objective(amplitude, pbase, source, weights)
    p = deepcopy(pbase)
    p.levels[1].z .= amplitude .* source
    WaterLily.poisson_solve!(p)
    return sum(p.x .* weights)
end

function report_failure(stage, err)
    println(stage, "_STATUS FAIL type=", typeof(err))
    showerror(stdout, err, catch_backtrace())
    println()
end

println("JULIA_VERSION ", VERSION)
println("CUDA_JL_VERSION ", pkgversion(CUDA))
println("CUDA_RUNTIME ", CUDA.runtime_version())
println("ENZYME_VERSION ", pkgversion(Enzyme))
println("WATERLILY_VERSION ", pkgversion(WaterLily))
println("WATERLILY_PR_285_HEAD feed49f480b52047b4e9b8bfacdf3e4f8201106b")
println("WATERLILY_ENZYME_EXTENSION ", !isnothing(Base.get_extension(WaterLily, :WaterLilyEnzymeCoreExt)))
println("CUDA_FUNCTIONAL ", CUDA.functional())
println("FIXTURE dims=", DIMS, " D=", DIAMETER, " Re_D=100 steps=", STEPS, " Float32 CuArray")

CUDA.functional() || error("CUDA.jl is not functional on this Kaggle worker")

println("GPU_ARRAY_REVERSE_BEGIN")
try
    x = CUDA.CuArray(Float32.(1:8))
    dx = CUDA.zeros(Float32, length(x))
    result = Enzyme.autodiff(Enzyme.ReverseWithPrimal, quadratic, Enzyme.Active,
                             Enzyme.Duplicated(x, dx))
    grad = Array(dx)
    expected = 2 .* Array(x)
    println("GPU_ARRAY_REVERSE_PRIMAL ", repr(result[2]))
    println("GPU_ARRAY_REVERSE_GRAD_ERROR ", repr(maximum(abs.(grad .- expected))))
    println("GPU_ARRAY_REVERSE_STATUS ", all(isfinite, grad) ? "PASS" : "FAIL")
catch err
    report_failure("GPU_ARRAY_REVERSE", err)
end

sim = build_sim()
primal_sim = deepcopy(sim)
println("WATERLILY_PRIMAL_BEGIN")
try
    force = force_after_steps!(primal_sim)
    println("WATERLILY_PRIMAL_DRAG ", repr(force))
    println("WATERLILY_PRIMAL_STATUS ", isfinite(force) ? "PASS" : "FAIL")
catch err
    report_failure("WATERLILY_PRIMAL", err)
end

const poisson_weights_host = Float32[sin(0.17f0 * i) + cos(0.11f0 * i)
                                    for i in eachindex(sim.pois.x)]
poisson_weights_host .-= sum(poisson_weights_host) / length(poisson_weights_host)
const POISSON_WEIGHTS = CUDA.CuArray(poisson_weights_host)
const poisson_source_host = Float32[sin(0.07f0 * i) for i in eachindex(sim.pois.x)]
poisson_source_host .-= sum(poisson_source_host) / length(poisson_source_host)
const POISSON_SOURCE = CUDA.CuArray(poisson_source_host)
const POISSON_SOURCE_GRID = reshape(POISSON_SOURCE, size(sim.pois.x))

println("POISSON_VJP_BEGIN")
try
    p = deepcopy(sim.pois)
    p.levels[1].z .= POISSON_SOURCE_GRID
    dp = Enzyme.make_zero(p)
    result = @time Enzyme.autodiff(Enzyme.ReverseWithPrimal, poisson_cost!, Enzyme.Active,
                                    Enzyme.Duplicated(p, dp), Enzyme.Const(POISSON_WEIGHTS))
    directional_gradient = sum(dp.levels[1].z .* POISSON_SOURCE_GRID)
    epsilon = 1e-2f0
    fd = (poisson_objective(1 + epsilon, sim.pois, POISSON_SOURCE_GRID, POISSON_WEIGHTS) -
          poisson_objective(1 - epsilon, sim.pois, POISSON_SOURCE_GRID, POISSON_WEIGHTS)) /
         (2epsilon)
    println("POISSON_VJP_PRIMAL ", repr(result[2]))
    println("POISSON_VJP_DIRECTIONAL_GRADIENT ", repr(directional_gradient))
    println("POISSON_VJP_CENTERED_FD ", repr(fd))
    println("POISSON_VJP_VS_FD_RATIO ", repr(directional_gradient / fd))
    println("POISSON_VJP_FINITE ", isfinite(directional_gradient))
    println("POISSON_VJP_STATUS ", isfinite(directional_gradient) ? "PASS" : "FAIL")
catch err
    report_failure("POISSON_VJP", err)
end

println("WATERLILY_STEP_REVERSE_BEGIN")
try
    shadow = Enzyme.make_zero(sim)
    result = @time Enzyme.autodiff(Enzyme.ReverseWithPrimal, force_after_steps!, Enzyme.Active,
                                    Enzyme.Duplicated(sim, shadow))
    grad = Array(shadow.flow.u)[ACTIVE_CELL]
    println("WATERLILY_STEP_REVERSE_PRIMAL ", repr(result[2]))
    println("WATERLILY_STEP_REVERSE_INITIAL_U_GRAD ", repr(grad))
    println("WATERLILY_STEP_REVERSE_STATUS ", isfinite(grad) ? "PASS" : "FAIL")
catch err
    report_failure("WATERLILY_STEP_REVERSE", err)
end

println("REVERSE_SPIKE_SCRIPT_DONE")
