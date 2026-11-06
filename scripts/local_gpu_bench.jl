#!/usr/bin/env julia
# R0 engineering throughput probe. Never run automatically by tests on a GPU.
using WaterLily, SHA, Dates

# Load the extension at top level before compiling any GPU stepping method.
# The explicitly selected CPU selftest never imports CUDA or probes a GPU.
if !("--cpu-selftest" in ARGS)
    ENV["CUDA_VISIBLE_DEVICES"] = "0"
    using CUDA
end

const TGV_SIZE = 128
const FIXED_STEPS = 100
const WARMUP_STEPS = 10

function arguments(args)
    options = Dict("--out" => "", "--steps" => "100", "--warmup" => "10",
                   "--host-label" => Sys.iswindows() ? "native_windows" : "wsl2")
    cpu = "--cpu-selftest" in args
    args = filter(!=("--cpu-selftest"), args)
    iseven(length(args)) || error("bench options require a value")
    for i in 1:2:length(args)
        haskey(options, args[i]) || error("unknown bench option $(args[i])")
        options[args[i]] = args[i + 1]
    end
    isempty(options["--out"]) && error("usage: local_gpu_bench.jl --out RESULT.json [--host-label LABEL] [--cpu-selftest]")
    ispath(options["--out"]) && error("refusing to overwrite $(options["--out"])")
    options["--host-label"] in ("wsl2", "native_windows") || error("unknown R0 host label")
    parse(Int, options["--steps"]) == FIXED_STEPS || error("R0 fixes 100 measured steps")
    parse(Int, options["--warmup"]) == WARMUP_STEPS || error("R0 fixes 10 warmup steps")
    return options, cpu
end

# WaterLily's 3D TGV example uses a π-length symmetry box, Re=1600.
# Primary source read 2026-11-06:
# https://github.com/WaterLily-jl/WaterLily-Examples/blob/main/examples/ThreeD_TaylorGreenVortex.jl
# The initial field and symmetry BCs below are also valid in pinned WaterLily 1.8.0.
function tgv(L, mem)
    κ = Float32(π / L)
    function initial(i, x)
        a, b, c = x .* κ
        i == 1 && return -sin(a) * cos(b) * cos(c)
        i == 2 && return cos(a) * sin(b) * cos(c)
        0f0
    end
    Simulation((L, L, L), (0f0, 0f0, 0f0), Float32(L);
        U=1f0, ν=Float32(L / 1600), u0=initial, T=Float32, mem)
end

# R0 rev0 leaves the 2D plate's dimensions unspecified. This is a fixed engineering
# fixture: 256x128 cells, capsule chord 32, thickness 4, angle 10°, Re_chord=1000.
# It is not a registered force/geometry qualification case.
function plate(dims, mem)
    scale = dims[2] / 128
    chord, half_thickness = Float32(32scale), Float32(2scale)
    centre = (Float32(dims[1] / 4), Float32(dims[2] / 2))
    sine, cosine = sincos(Float32(10π / 180))
    sdf(x, t) = begin
        dx, dy = x[1] - centre[1], x[2] - centre[2]
        along, across = cosine * dx + sine * dy, -sine * dx + cosine * dy
        straight_half = chord / 2 - half_thickness
        sqrt(max(abs(along) - straight_half, 0f0)^2 + across^2) - half_thickness
    end
    Simulation(dims, (1f0, 0f0), chord; ν=chord / 1000f0,
        body=AutoBody(sdf), T=Float32, mem, exitBC=true)
end

function timed_case(name, sim, steps, warmup, synchronize)
    synchronize()
    warmed = time_ns()
    for _ in 1:warmup
        sim_step!(sim)
    end
    synchronize()
    warmup_seconds = (time_ns() - warmed) / 1e9
    initial_time = Float64(sim_time(sim))
    started = time_ns()
    for _ in 1:steps
        sim_step!(sim)
    end
    synchronize()
    wall = (time_ns() - started) / 1e9
    dims = size(sim.flow.p) .- 2
    cells = prod(dims)
    finite_u, finite_p = all(isfinite, sim.flow.u), all(isfinite, sim.flow.p)
    finite_u && finite_p || error("$name produced a non-finite field")
    (name=name, flow_dims=dims, dtype="Float32", warmup_steps=warmup,
     warmup_wall_seconds=warmup_seconds, steps=steps, cells=cells,
     wall_seconds=wall, cell_steps_per_second=cells * steps / wall,
     ns_per_cell_step=wall * 1e9 / (cells * steps), initial_t_u_l=initial_time,
     final_t_u_l=Float64(sim_time(sim)), finite_u=finite_u, finite_p=finite_p)
end

json(x::AbstractString) = "\"" * replace(x, "\\" => "\\\\", "\"" => "\\\"", "\n" => "\\n", "\r" => "\\r", "\t" => "\\t") * "\""
json(x::Bool) = x ? "true" : "false"
json(x::Real) = isfinite(x) ? string(x) : error("non-finite JSON value")
json(x::Tuple) = "[" * join(json.(x), ",") * "]"
json(x::AbstractVector) = "[" * join(json.(x), ",") * "]"
json(x::NamedTuple) = "{" * join((json(string(k)) * ":" * json(v) for (k, v) in pairs(x)), ",") * "}"

function main()
    options, cpu = arguments(ARGS)
    VERSION == v"1.12.6" || error("bench requires Julia 1.12.6")
    pkgversion(WaterLily) == v"1.8.0" || error("bench requires WaterLily 1.8.0")
    project = Base.active_project()
    manifest = joinpath(dirname(project), "Manifest.toml")
    isfile(manifest) || error("bench requires an active locked Manifest.toml")
    if cpu
        mem, synchronize = Array, () -> nothing
        gpu = (name="CPU selftest; no GPU invoked", uuid="not-applicable")
    else
        basename(dirname(project)) == "CFDSDFWaterLilyT4" ||
            error("GPU R0 requires --project=julia/CFDSDFWaterLilyT4")
        CUDA.functional() || error("CUDA.functional() is false")
        length(collect(CUDA.devices())) == 1 || error("R0 requires one visible GPU")
        CUDA.device!(0)
        CUDA.name(CUDA.device()) == "NVIDIA GeForce RTX 4070 Ti" || error("R0 requires the RTX 4070 Ti identity")
        mem, synchronize = CUDA.CuArray, CUDA.synchronize
        gpu = (name=CUDA.name(CUDA.device()), uuid=string(CUDA.uuid(CUDA.device())))
    end
    steps, warmup = cpu ? (2, 1) : (FIXED_STEPS, WARMUP_STEPS)
    size_tgv, size_plate = cpu ? (16, (64, 32)) : (TGV_SIZE, (256, 128))
    cases = [timed_case("tgv", tgv(size_tgv, mem), steps, warmup, synchronize),
             timed_case("plate_2d", plate(size_plate, mem), steps, warmup, synchronize)]
    result = (schema_version=1, evidence_class=cpu ? "CPU_BENCH_SELFTEST" : "R0_ENGINEERING_BENCHMARK",
        host_label=cpu ? "cpu_selftest" : options["--host-label"], captured_utc=string(now(UTC)) * "Z",
        julia_version=string(VERSION), waterlily_version=string(pkgversion(WaterLily)),
        manifest_sha256=bytes2hex(sha256(read(manifest))), gpu_identity=gpu,
        cuda_visible_devices=cpu ? "not-applicable" : ENV["CUDA_VISIBLE_DEVICES"],
        used_gpu_count=cpu ? 0 : 1, measured_steps=steps, warmup_steps=warmup,
        plate_definition=(chord_cells=cpu ? 8 : 32, thickness_cells=cpu ? 1 : 4,
                          angle_degrees=10, reynolds=1000),
        cases=cases)
    output = json(result) * "\n"
    write(options["--out"], output)
    print(output)
end

main()
