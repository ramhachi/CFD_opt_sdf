# Issue #22 diagnostic only. Run with the pinned Project.toml/Manifest.toml.
# This mean-zero interior fixture tests the pinned Poisson VJP rule only; it is
# not a full WaterLily step, SDF gradient, or backend qualification.
using Enzyme
using SHA
using WaterLily

const DIMS = (24, 16, 16)
const CENTER = (8.0, 8.0, 8.0)
const DIAMETER = 4.0
const NU = DIAMETER / 100.0
const GRAD02_POISSON_TOLERANCE = Ref(1e-4)

function build_sim()
    body = WaterLily.AutoBody((x, t) -> sqrt(sum(abs2, x .- CENTER)) - DIAMETER / 2)
    WaterLily.Simulation(DIMS, (1.0, 0.0, 0.0), DIAMETER;
                         ν=NU, body, T=Float64, mem=Array)
end

# Test-local method exposes solver!'s tolerance keyword while preserving the
# pinned extension's poisson_solve! function identity for Enzyme rule dispatch.
# The method override is process-local and is never applied to production code.
@eval WaterLily function poisson_solve!(p::MultiLevelPoisson)
    solver!(p; tol=Main.GRAD02_POISSON_TOLERANCE[])
    return nothing
end

const sim = build_sim()
const interior = collect(WaterLily.inside(sim.pois.x))
const weights = zeros(Float64, size(sim.pois.x))
const source = zeros(Float64, size(sim.pois.x))
for I in interior
    i = LinearIndices(sim.pois.x)[I]
    weights[I] = sin(0.17i) + cos(0.11i)
    source[I] = sin(0.07i)
end
# The operator has a constant-pressure nullspace. Keep both the RHS direction
# and objective cotangent mean-zero over the active interior.
weights[interior] .-= sum(weights[interior]) / length(interior)
source[interior] .-= sum(source[interior]) / length(interior)
const initial_poisson = deepcopy(sim.pois)

function poisson_cost!(p)
    WaterLily.poisson_solve!(p)
    return sum(p.x[I] * weights[I] for I in interior)
end

function poisson_objective(amplitude, tolerance)
    p = deepcopy(initial_poisson)
    p.levels[1].z .= amplitude .* source
    GRAD02_POISSON_TOLERANCE[] = tolerance
    WaterLily.poisson_solve!(p)
    return sum(p.x[I] * weights[I] for I in interior), last(p.n)
end

project_path = Base.active_project()
manifest_path = joinpath(dirname(project_path), "Manifest.toml")
println("JULIA_VERSION ", VERSION)
println("HOST_KERNEL ", Sys.KERNEL)
println("HOST_ARCH ", Sys.ARCH)
println("HOST_MACHINE ", Sys.MACHINE)
println("JULIA_THREADS ", Threads.nthreads())
println("WATERLILY_VERSION ", pkgversion(WaterLily))
println("ENZYME_VERSION ", pkgversion(Enzyme))
println("CUDA_JL_PIN 6.2.1; CPU Array fixture; no GPU execution")
println("WATERLILY_PR_285_HEAD feed49f480b52047b4e9b8bfacdf3e4f8201106b")
println("WATERLILY_ENZYME_EXTENSION_LOADED ", !isnothing(Base.get_extension(WaterLily, :WaterLilyEnzymeCoreExt)))
println("PROJECT_SHA256 ", bytes2hex(sha256(read(project_path))))
println("MANIFEST_SHA256 ", bytes2hex(sha256(read(manifest_path))))
println("POISSON_FIXTURE padded_grid=", size(sim.pois.x),
        " interior_cells=", length(interior),
        " mean_zero_source_sum=", repr(sum(source[interior])),
        " mean_zero_weight_sum=", repr(sum(weights[interior])),
        " centered_fd_step=1e-5")

for tolerance in (1e-4, 1e-10)
    GRAD02_POISSON_TOLERANCE[] = tolerance
    fd_step = 1e-5
    plus, plus_cycles = poisson_objective(1 + fd_step, tolerance)
    minus, minus_cycles = poisson_objective(1 - fd_step, tolerance)
    fd = (plus - minus) / (2 * fd_step)
    p = deepcopy(initial_poisson)
    p.levels[1].z .= source
    dp = Enzyme.make_zero(p)
    reverse_seconds = @elapsed result = Enzyme.autodiff(
        Enzyme.ReverseWithPrimal, poisson_cost!, Enzyme.Active,
        Enzyme.Duplicated(p, dp))
    reverse_directional = sum(dp.levels[1].z[I] * source[I] for I in interior)
    println("POISSON_TOLERANCE ", repr(tolerance),
            " FD_CYCLES=", plus_cycles, ",", minus_cycles,
            " REVERSE_CYCLES=", last(p.n))
    println("POISSON_PRIMAL ", repr(result[2]))
    println("POISSON_CENTERED_FD_DIRECTIONAL ", repr(fd))
    println("POISSON_REVERSE_DIRECTIONAL ", repr(reverse_directional))
    println("POISSON_REVERSE_OVER_FD ", repr(reverse_directional / fd))
    println("POISSON_REVERSE_RELATIVE_ERROR ", repr(abs(reverse_directional - fd) / abs(fd)))
    println("POISSON_REVERSE_ELAPSED_S_INCLUDING_JIT ", repr(reverse_seconds))
end
println("POISSON_TOLERANCE_SWEEP_DONE (isolated Poisson rule only)")
