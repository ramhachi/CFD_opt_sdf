# Solver-free canonical geometry tests for the diagnostic-only sign operators.
using Test, Statistics, WaterLily
include(joinpath(@__DIR__, "sdf_native_fd07_continuous_sign_operators.jl"))
using .SDFNativeFD07ContinuousSignOperators

const DELTA = DEFAULT_DELTA
const MODES_TO_COMPARE = MODES
const DOMAIN = -3.0:3.0

box_sdf(x, half) = begin
    q = ntuple(i -> abs(x[i]) - half[i], 3)
    outside = sqrt(sum(max(q[i], 0.0)^2 for i in 1:3))
    outside + min(maximum(q), 0.0)
end

function geometry_pairs(sdf, shift=(0.0, 0.0, 0.0))
    rows = NamedTuple[]
    for k in DOMAIN, j in DOMAIN, i in DOMAIN
        center = (i + shift[1], j + shift[2], k + shift[3])
        dc = sdf(center)
        for axis in 1:3
            face = ntuple(q -> center[q] - (q == axis ? 0.5 : 0.0), 3)
            push!(rows, (; axis, center, face, center_distance=dc, face_distance=sdf(face)))
        end
    end
    rows
end

function row_moments(row, mode)
    moment_values(Float32(row.face_distance), Float32(row.center_distance), Val(mode), DELTA, 1f0)
end

function geometry_stats(name, sdf)
    pairs = geometry_pairs(sdf)
    upstream = [row_moments(row, :UPSTREAM) for row in pairs]
    rows = NamedTuple[]
    for mode in MODES_TO_COMPARE
        values = [row_moments(row, mode) for row in pairs]
        d0 = [Float64(values[n][1] - upstream[n][1]) for n in eachindex(pairs)]
        d1 = [Float64(values[n][2] - upstream[n][2]) for n in eachindex(pairs)]
        support0 = count(n -> (values[n][1] < 1f0) != (upstream[n][1] < 1f0), eachindex(pairs))
        support1 = count(n -> (values[n][2] != 0f0) != (upstream[n][2] != 0f0), eachindex(pairs))
        legal_crossings = [n for n in eachindex(pairs)
            if abs(pairs[n].face_distance) <= 0.5 &&
               pairs[n].center_distance * pairs[n].face_distance < 0]
        rows_out = (fixture=name, mode=String(mode), sample_pairs=length(pairs),
            center_inside_count=count(row -> row.center_distance < 0, pairs),
            center_outside_count=count(row -> row.center_distance > 0, pairs),
            face_inside_count=count(row -> row.face_distance < 0, pairs),
            face_outside_count=count(row -> row.face_distance > 0, pairs),
            center_face_opposite_sign_count=count(row -> row.center_distance * row.face_distance < 0, pairs),
            sign_disagree_gt_half=count(row -> abs(row.face_distance) > 0.5 + 1e-12 &&
                signbit(row.face_distance) != signbit(row.center_distance), pairs),
            max_abs_delta_mu0=maximum(abs, d0), count_delta_mu0_gt_1e_3=count(x -> abs(x) > 1e-3, d0),
            max_abs_delta_mu1=maximum(abs, d1), count_delta_mu1_gt_1e_3=count(x -> abs(x) > 1e-3, d1),
            legal_half_cell_crossing_count=length(legal_crossings),
            legal_half_cell_crossing_max_abs_delta_mu0=isempty(legal_crossings) ? 0.0 :
                maximum(abs(d0[n]) for n in legal_crossings),
            legal_half_cell_crossing_changed_mu0_count=count(n -> abs(d0[n]) > 0, legal_crossings),
            mu0_support_membership_changes=support0, mu1_support_membership_changes=support1,
            nonfinite=count(n -> !isfinite(values[n][1]) || !isfinite(values[n][2]), eachindex(pairs)))
        push!(rows, rows_out)
    end
    return rows
end

function reflection_stats(name, sdf, mirror, antisymmetric)
    pairs = geometry_pairs(sdf)
    rows = NamedTuple[]
    for mode in MODES_TO_COMPARE
        geometry_error = mu0_error = mu1_error = 0.0
        for row in pairs
            reflected_center = sdf(mirror(row.center))
            reflected_face = sdf(mirror(row.face))
            geometry_error = max(geometry_error,
                abs(reflected_center - (antisymmetric ? -row.center_distance : row.center_distance)),
                abs(reflected_face - (antisymmetric ? -row.face_distance : row.face_distance)))
            original = row_moments(row, mode)
            reflected = row_moments(merge(row, (; center_distance=reflected_center,
                                     face_distance=reflected_face)), mode)
            mu0_error = max(mu0_error, abs(Float64(original[1]) -
                (antisymmetric ? 1.0 - Float64(reflected[1]) : Float64(reflected[1]))))
            mu1_error = max(mu1_error, abs(Float64(original[2]) - Float64(reflected[2])))
        end
        push!(rows, (; fixture=name, mode=String(mode), antisymmetric_sdf=antisymmetric,
            samples=length(pairs), geometry_max_abs_residual=geometry_error,
            mu0_reflection_max_abs_residual=mu0_error,
            mu1_reflection_max_abs_residual=mu1_error))
    end
    rows
end

function translation_steps(mode; shift_values=-0.001:0.000001:0.001)
    # Sign-disagreeing pair located just beyond the geometric half-cell bound.
    face = Float32(0.5 + DELTA / 2)
    previous = nothing
    max_adjacent_delta = 0.0
    minimum_slope = Inf
    nondecreasing = true
    values = Float64[]
    for c in shift_values
        mu0, _ = moment_values(face, Float32(c), Val(mode), DELTA, 1f0)
        push!(values, Float64(mu0))
        if !isnothing(previous)
            diff = Float64(mu0) - previous
            max_adjacent_delta = max(max_adjacent_delta, abs(diff))
            minimum_slope = min(minimum_slope, diff)
            nondecreasing &= diff >= -2e-7
        end
        previous = Float64(mu0)
    end
    return (; sweep="center_sign", mode=String(mode), samples=length(values), max_adjacent_delta,
        minimum_adjacent_delta=minimum_slope, nondecreasing, nonincreasing=false,
        endpoint_change=last(values)-first(values))
end

function face_threshold_steps(mode; face_values=0.5:0.000001:0.5005)
    center = Float32(-2DELTA)
    previous = nothing
    max_adjacent_delta = 0.0
    minimum_slope = Inf
    nonincreasing = true
    values = Float64[]
    for face in face_values
        mu0, _ = moment_values(Float32(face), center, Val(mode), DELTA, 1f0)
        push!(values, Float64(mu0))
        if !isnothing(previous)
            diff = Float64(mu0) - previous
            max_adjacent_delta = max(max_adjacent_delta, abs(diff))
            minimum_slope = min(minimum_slope, diff)
            nonincreasing &= diff <= 2e-7
        end
        previous = Float64(mu0)
    end
    return (; sweep="face_threshold", mode=String(mode), samples=length(values),
        max_adjacent_delta, minimum_adjacent_delta=minimum_slope,
        nondecreasing=false, nonincreasing, endpoint_change=last(values)-first(values))
end

function write_csv(path, rows)
    isempty(rows) && error("refusing to write empty fixture output")
    names = propertynames(first(rows))
    open(path, "w") do io
        println(io, join(string.(names), ","))
        for row in rows
            println(io, join((replace(string(getproperty(row, name)), ',' => ';') for name in names), ","))
        end
    end
end

function run_fixtures(outdir)
    mkpath(outdir)
    fixture_defs = [
        ("plane_center_aligned", x -> x[1], x -> (-x[1], x[2], x[3]), true),
        ("plane_face_aligned", x -> x[1] - 0.5, x -> (1.0 - x[1], x[2], x[3]), true),
        ("plane_face_offset_1e-4", x -> x[1] - (0.5 + 1e-4),
            x -> (1.0 + 2e-4 - x[1], x[2], x[3]), true),
        ("plane_near_center_offset_1e-4", x -> x[1] + 1e-4,
            x -> (-2e-4 - x[1], x[2], x[3]), true),
        ("sphere", x -> sqrt(sum(abs2, x)) - 1.25, x -> (-x[1], -x[2], -x[3]), false),
        ("one_cell_plate", x -> box_sdf(x, (2.0, 0.5, 2.0)), x -> (-x[1], -x[2], -x[3]), false),
        ("two_cell_plate", x -> box_sdf(x, (2.0, 1.0, 2.0)), x -> (-x[1], -x[2], -x[3]), false),
    ]
    summary = reduce(vcat, (geometry_stats(name, sdf) for (name, sdf, _, _) in fixture_defs))
    reflections = reduce(vcat, (reflection_stats(name, sdf, mirror, antisymmetric)
        for (name, sdf, mirror, antisymmetric) in fixture_defs))
    transitions = reduce(vcat, [[translation_steps(mode), face_threshold_steps(mode)]
        for mode in MODES_TO_COMPARE])
    sweep = NamedTuple[]
    for c in (-DELTA, -DELTA/4, -DELTA/100, 0f0, DELTA/100, DELTA/4, DELTA)
        face = Float32(0.5 + DELTA / 2)
        vals = Dict(String(mode) => moment_values(face, Float32(c), Val(mode), DELTA, 1f0)[1]
                    for mode in MODES_TO_COMPARE)
        push!(sweep, (; center_distance=c, face_distance=face,
            (Symbol("mu0_" * name) => value for (name, value) in vals)...))
    end
    write_csv(joinpath(outdir, "analytic_fixture_coefficients.csv"), summary)
    write_csv(joinpath(outdir, "analytic_reflection_symmetry.csv"), reflections)
    write_csv(joinpath(outdir, "analytic_center_sign_sweep.csv"), sweep)
    write_csv(joinpath(outdir, "analytic_translation_continuity.csv"), transitions)
    return (; summary, reflections, transitions)
end

function selftest()
    @test smoothstep01(-1f0) == 0f0
    @test smoothstep01(0f0) == 0f0
    @test smoothstep01(0.5f0) ≈ 0.5f0
    @test smoothstep01(1f0) == 1f0
    @test smooth_sign(-2DELTA, DELTA) == -1f0
    @test smooth_sign(0f0, DELTA) == 0f0
    @test smooth_sign(2DELTA, DELTA) == 1f0

    jump_pair(face=0.5 + DELTA) = begin
        moment_values(Float32(face), Float32(-DELTA/100), Val(:A_THRESHOLD), DELTA, 1f0)[1],
        moment_values(Float32(face), Float32(DELTA/100), Val(:A_THRESHOLD), DELTA, 1f0)[1]
    end
    a_minus, a_plus = jump_pair()
    b_minus = moment_values(Float32(0.5 + DELTA), Float32(-DELTA/100), Val(:B_CENTER_SIGN), DELTA, 1f0)[1]
    b_plus = moment_values(Float32(0.5 + DELTA), Float32(DELTA/100), Val(:B_CENTER_SIGN), DELTA, 1f0)[1]
    c_minus = moment_values(Float32(0.5 + DELTA), Float32(-DELTA/100), Val(:C_MOMENT_BLEND), DELTA, 1f0)[1]
    c_plus = moment_values(Float32(0.5 + DELTA), Float32(DELTA/100), Val(:C_MOMENT_BLEND), DELTA, 1f0)[1]
    @test abs(Float64(a_plus - a_minus)) > 0.7
    @test abs(Float64(b_plus - b_minus)) < 0.02
    @test abs(Float64(c_plus - c_minus)) < 0.02

    # Candidate C preserves the strict half-cell non-correction region and μ₁.
    for face in (-0.5f0, 0f0, 0.5f0)
        for center in (-0.4f0, 0f0, 0.4f0)
            upstream = moment_values(face, center, Val(:UPSTREAM), DELTA, 1f0)
            candidate = moment_values(face, center, Val(:C_MOMENT_BLEND), DELTA, 1f0)
            @test candidate[1] == upstream[1]
            @test candidate[2] == upstream[2]
        end
    end

    # The moving-ground plane has exactly half-cell center-to-face distances.
    ground = x -> x[3]
    rows = geometry_pairs(ground)
    for row in rows
        @test row.face_distance == row.center_distance ||
              abs(abs(row.face_distance - row.center_distance) - 0.5) < 1e-12
    end

    near_plane = x -> x[1] + 1e-4
    legal_crossings = filter(row -> abs(row.face_distance) <= 0.5 &&
        row.center_distance * row.face_distance < 0, geometry_pairs(near_plane))
    @test !isempty(legal_crossings)
    @test any(row -> row_moments(row, :A_THRESHOLD)[1] != row_moments(row, :UPSTREAM)[1], legal_crossings)
    @test any(row -> row_moments(row, :B_CENTER_SIGN)[1] != row_moments(row, :UPSTREAM)[1], legal_crossings)
    @test all(row -> row_moments(row, :C_MOMENT_BLEND) == row_moments(row, :UPSTREAM), legal_crossings)
    println("analytic_sign_operator_selftest=passed")
end

if length(ARGS) == 1 && ARGS[1] == "--selftest"
    selftest()
elseif length(ARGS) == 1
    run_fixtures(abspath(only(ARGS)))
else
    error("usage: julia --project=julia/CFDSDFWaterLily scripts/sdf_native_fd07_continuous_replacement_fixtures.jl <output-dir> | --selftest")
end
