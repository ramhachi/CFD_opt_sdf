#!/usr/bin/env julia
# CPU capability test only; this does not qualify CUDA restart behaviour.
using Test, WaterLily, SHA
include(joinpath(@__DIR__, "..", "julia", "CFDSDFWaterLily", "src", "CFDSDFWaterLily.jl"))
Base.include(CFDSDFWaterLily,
    joinpath(@__DIR__, "..", "julia", "CFDSDFWaterLily", "gen01", "Checkpoint.jl"))
using .CFDSDFWaterLily.Checkpoint

function fixture(; dims=(64, 32), ν=0.08f0)
    body = AutoBody((x, t) -> sqrt((x[1] - clamp(x[1], 19f0, 27f0))^2 +
                                  (x[2] - 16f0)^2) - 2f0)
    Simulation(dims, (1f0, 0f0), 12f0; ν, body, T=Float32, mem=Array, exitBC=true)
end

function advance!(sim, rows, first, last)
    for step in first:last
        sim_step!(sim)
        pressure = -WaterLily.pressure_force(sim)
        viscous = -WaterLily.viscous_force(sim)
        force = pressure + viscous
        push!(rows, (Float64(step), Float64(sim_time(sim)), force[1], force[2]))
    end
end

function window_mean(rows, column, lo, hi)
    result = duration = 0.0
    for (left, right) in zip(rows[1:end-1], rows[2:end])
        start, stop = max(lo, left[2]), min(hi, right[2])
        stop > start || continue
        interpolate(t) = left[column] + (right[column] - left[column]) *
                         (t - left[2]) / (right[2] - left[2])
        result += (interpolate(start) + interpolate(stop)) * (stop - start) / 2
        duration += stop - start
    end
    @assert isapprox(duration, hi - lo; rtol=1e-14)
    result / duration
end

relative(a, b) = abs(a - b) / max(abs(a), abs(b), 1e-300)
bytes(a) = collect(reinterpret(UInt8, vec(a)))

function main()
    (isempty(ARGS) || (length(ARGS) == 2 && ARGS[1] == "--out")) ||
        error("usage: checkpoint_selftest.jl [--out RESULT.json]")
    started = time()
    result = mktempdir() do dir
        full, split = fixture(), fixture()
        full_rows, split_rows = NTuple{4,Float64}[], NTuple{4,Float64}[]
        advance!(full, full_rows, 1, 100)
        advance!(split, split_rows, 1, 50)
        path = joinpath(dir, "checkpoint.bin")
        @testset "checkpoint data and refusal" begin
            @test save_checkpoint(path, split, 50, split_rows; identity="cpu-plate-v1") == path
            data = load_checkpoint(path)
            @test data.step == 50
            @test data.rows == split_rows
            @test data.identity == "cpu-plate-v1"
            @test data.time == WaterLily.time(split)
            @test data.sim_time == sim_time(split)
            @test data.Δt == split.flow.Δt
            @test bytes(data.u) == bytes(split.flow.u)
            @test bytes(data.u⁰) == bytes(split.flow.u⁰)
            @test bytes(data.p) == bytes(split.flow.p)
            @test_throws ArgumentError save_checkpoint(path, split, 49, split_rows)
            @test_throws ArgumentError restore_checkpoint!(fixture(dims=(64, 64)), data)
            @test_throws ArgumentError restore_checkpoint!(fixture(ν=0.09f0), data)
            @test_throws ArgumentError restore_checkpoint!(split, data)
            damaged = joinpath(dir, "damaged.bin")
            write(damaged, read(path)[1:30])
            @test_throws ArgumentError load_checkpoint(damaged)
        end
        data = load_checkpoint(path)
        resumed = fixture()
        restore_checkpoint!(resumed, data)
        resumed_rows = copy(data.rows)
        @test WaterLily.time(resumed) == data.time
        advance!(resumed, resumed_rows, data.step + 1, 100)
        lo = (full_rows[79][2] + full_rows[80][2]) / 2
        hi = (full_rows[99][2] + full_rows[100][2]) / 2
        whole_means = [window_mean(full_rows, c, lo, hi) for c in (3, 4)]
        resumed_means = [window_mean(resumed_rows, c, lo, hi) for c in (3, 4)]
        all_differences = [relative(a, b) for (r, s) in zip(full_rows, resumed_rows)
                           for (a, b) in zip(r, s)]
        max_difference = maximum(all_differences)
        bitwise = all(isequal.(full_rows, resumed_rows)) &&
                  bytes(full.flow.u) == bytes(resumed.flow.u) &&
                  bytes(full.flow.u⁰) == bytes(resumed.flow.u⁰) &&
                  bytes(full.flow.p) == bytes(resumed.flow.p)
        @testset "100-step uninterrupted versus fresh-simulation restart" begin
            @test length(resumed_rows) == 100
            @test resumed.flow.Δt == full.flow.Δt
            @test max_difference <= 1e-6
            @test maximum(relative.(whole_means, resumed_means)) <= 1e-6
            @test all(isfinite, resumed.flow.u) && all(isfinite, resumed.flow.p)
        end
        (bitwise=bitwise, maximum_relative_difference=max_difference,
         means=whole_means, resumed_means=resumed_means,
         checkpoint_sha256=bytes2hex(sha256(read(path))))
    end
    # The force window is deliberately clipped between samples, rather than selected by row.
    json = "{\"status\":\"PASS\",\"evidence_class\":\"CPU_CHECKPOINT_SELFTEST\"," *
           "\"julia_version\":\"$(VERSION)\",\"waterlily_version\":\"$(pkgversion(WaterLily))\"," *
           "\"julia_threads\":$(Threads.nthreads())," *
           "\"julia_executable_sha256\":\"$(bytes2hex(sha256(read(joinpath(Sys.BINDIR, Base.julia_exename())))))\"," *
           "\"manifest_sha256\":\"$(bytes2hex(sha256(read(joinpath(dirname(Base.active_project()), "Manifest.toml")))))\"," *
           "\"checkpoint_source_sha256\":\"$(bytes2hex(sha256(read(joinpath(@__DIR__, "..", "julia", "CFDSDFWaterLily", "gen01", "Checkpoint.jl")))))\"," *
           "\"selftest_source_sha256\":\"$(bytes2hex(sha256(read(@__FILE__))))\"," *
           "\"flow_dims\":[64,32],\"steps\":100,\"checkpoint_step\":50," *
           "\"class\":\"$(result.bitwise ? "BITWISE" : "TOLERANCE")\"," *
           "\"maximum_relative_difference\":$(result.maximum_relative_difference)," *
           "\"window_means\":[$(join(result.means, ','))]," *
           "\"resumed_window_means\":[$(join(result.resumed_means, ','))]," *
           "\"checkpoint_sha256\":\"$(result.checkpoint_sha256)\"," *
           "\"wall_seconds\":$(time()-started)}\n"
    if !isempty(ARGS)
        ispath(ARGS[2]) && error("refusing to overwrite $(ARGS[2])")
        write(ARGS[2], json)
    end
    print(json)
end

main()
