# W1g CUDA GridSDF geometry fixture.
#
# Usage:
#   julia --project=<T4 env> scripts/w1g_gpu_geometry_fixture.jl gpu <out_prefix>
#   julia --project=<CPU env> scripts/w1g_gpu_geometry_fixture.jl cpu <out_prefix>   # local validation only
#
# Registered by docs/evidence/sdf_native_w1g_gpu_gridsdf_criteria_2026_09.json.
# The gpu mode is the registered measurement; the cpu mode validates the same
# kernel and generic-body code path locally without CUDA.

using SHA, Random

backend = length(ARGS) >= 1 ? ARGS[1] : "gpu"
out_prefix = length(ARGS) >= 2 ? ARGS[2] : "work/w1g_gpu_geometry_fixture"

include(joinpath(@__DIR__, "..", "julia", "CFDSDFWaterLily", "src", "CFDSDFWaterLily.jl"))
using .CFDSDFWaterLily
using .CFDSDFWaterLily.GridSDFBody
using WaterLily

if backend == "gpu"
    @eval using CUDA
    Base.include(CFDSDFWaterLily, joinpath(@__DIR__, "..", "julia", "CFDSDFWaterLily", "src", "DeviceGridSDF.jl"))
    @eval using .CFDSDFWaterLily.DeviceGridSDF
end

phi_sha(phi) = bytes2hex(sha256(reinterpret(UInt8, vec(phi))))

const RNG_SEED = 202606
const BULK_BOX = 100_000
const BULK_BAND = 100_000
const SCALE = CFDSDFWaterLily.WORLD_PER_SOLVER
const ORIGIN_M = CFDSDFWaterLily.WORLD_ORIGIN_M
const BOX_ORIGIN = CFDSDFWaterLily.SPHERE_PHI_ORIGIN
const BOX_H = CFDSDFWaterLily.SPHERE_PHI_SPACING
const BOX_SHAPE = CFDSDFWaterLily.SPHERE_PHI_SHAPE
const CENTER = CFDSDFWaterLily.SPHERE_CENTER_M
const RADIUS = CFDSDFWaterLily.SPHERE_RADIUS_M

function outside_world(p)
    for axis in 1:3
        lo = BOX_ORIGIN[axis]
        hi = lo + (BOX_SHAPE[axis] - 1) * BOX_H
        (lo <= p[axis] <= hi) || return true
    end
    return false
end

function generate_probes()
    rng = MersenneTwister(RNG_SEED)
    probes = Vector{WaterLily.SVector{3,Float32}}()
    for _ in 1:BULK_BOX
        p = ntuple(axis -> Float32(BOX_ORIGIN[axis] + rand(rng) * (BOX_SHAPE[axis] - 1) * BOX_H), 3)
        push!(probes, WaterLily.SVector{3,Float32}(p))
    end
    for _ in 1:BULK_BAND
        theta = acos(1 - 2 * rand(rng))
        azimuth = 2 * pi * rand(rng)
        direction = (sin(theta) * cos(azimuth), sin(theta) * sin(azimuth), cos(theta))
        u = (2 * rand(rng) - 1) * 1e-3
        p = ntuple(axis -> Float32(CENTER[axis] + (RADIUS + u) * direction[axis]), 3)
        push!(probes, WaterLily.SVector{3,Float32}(p))
    end
    representatives = [
        ("inside_solid", (0.25 + 0.2, 0.0, 0.0)),
        ("near_interface_fluid", (0.25, 0.0, 0.5 + 0.002)),
        ("near_interface_solid", (0.25, 0.0, 0.5 - 0.002)),
        ("on_surface", (0.25 + RADIUS, 0.0, 0.0)),
        ("non_axis_aligned_a", (0.25 + 0.31, 0.21, 0.13)),
        ("non_axis_aligned_b", (0.25 - 0.27, -0.19, 0.35)),
        ("outside_x_lo", (-1.5, 0.0, 0.0)),
        ("outside_x_hi", (2.5, 0.0, 0.0)),
        ("outside_y_lo", (0.25, -1.2, 0.0)),
        ("outside_y_hi", (0.25, 1.2, 0.0)),
        ("outside_z_lo", (0.25, 0.0, -1.1)),
        ("outside_z_hi", (0.25, 0.0, 1.1)),
    ]
    for (_, p) in representatives
        push!(probes, WaterLily.SVector{3,Float32}(Float32.(p)))
    end
    return probes, representatives
end

to_solver(p) = WaterLily.SVector{3,Float32}(
    Float32((Float64(p[1]) - ORIGIN_M[1]) / SCALE),
    Float32((Float64(p[2]) - ORIGIN_M[2]) / SCALE),
    Float32((Float64(p[3]) - ORIGIN_M[3]) / SCALE),
)

@kernel function w1g_probe_kernel!(d_out, nx_out, ny_out, nz_out, body, probes)
    i = @index(Global)
    d, n, _ = WaterLily.measure(body, probes[i], 0.0f0; fastd² = 1.0f0)
    d_out[i] = d
    nx_out[i] = n[1]
    ny_out[i] = n[2]
    nz_out[i] = n[3]
end

canonical = CFDSDFWaterLily.sphere_phi_fixture()
source_sha = phi_sha(canonical.phi)

device_owner = nothing
device_grid, roundtrip_sha = if backend == "gpu"
    device = device_copy(canonical)
    device_owner = device
    roundtrip = device_roundtrip_sha(device)
    kernel_grid(device), roundtrip
else
    (
        GridSDF(
            Float32.(canonical.phi),
            Float32.(canonical.origin),
            Float32.(canonical.h),
            canonical.shape,
            Float32(canonical.outside_value),
            Float32(canonical.margin_m),
        ),
        source_sha,
    )
end

cpu_body = CFDSDFWaterLily.GridSDFWaterLilyBody(canonical, CFDSDFWaterLily.WORLD_ORIGIN_M, SCALE)
gpu_body = CFDSDFWaterLily.GridSDFWaterLilyBody(device_grid, Float32.(ORIGIN_M), Float32(SCALE))

probes, representatives = generate_probes()
probe_solver = [to_solver(p) for p in probes]
probe_count = length(probes)

cpu_d = Vector{Float32}(undef, probe_count)
cpu_n = Vector{WaterLily.SVector{3,Float32}}(undef, probe_count)
for index in 1:probe_count
    d, n, _ = WaterLily.measure(cpu_body, probe_solver[index], 0.0f0; fastd² = 1.0f0)
    cpu_d[index] = d
    cpu_n[index] = n
end

if backend == "gpu"
    probe_memory = CuArray(probe_solver)
    d_out = CuArray{Float32}(undef, probe_count)
    nx_out = CuArray{Float32}(undef, probe_count)
    ny_out = CuArray{Float32}(undef, probe_count)
    nz_out = CuArray{Float32}(undef, probe_count)
else
    probe_memory = probe_solver
    d_out = Vector{Float32}(undef, probe_count)
    nx_out = Vector{Float32}(undef, probe_count)
    ny_out = Vector{Float32}(undef, probe_count)
    nz_out = Vector{Float32}(undef, probe_count)
end

kernel! = w1g_probe_kernel!(get_backend(probe_memory))
kernel!(d_out, nx_out, ny_out, nz_out, gpu_body, probe_memory; ndrange = probe_count)
scalar_index_blocked = if backend == "gpu"
    synchronize()
    try
        device_owner.grid.phi[1, 1, 1]  # negative control: must throw fail-closed
        false
    catch
        true
    end
else
    true  # cpu validation mode: no device scalar-index policy exists
end
gpu_d = Array(d_out)
gpu_nx = Array(nx_out)
gpu_ny = Array(ny_out)
gpu_nz = Array(nz_out)

function compare_all(cpu_d, cpu_n, gpu_d, gpu_nx, gpu_ny, gpu_nz, probes)
    max_value_error = 0.0
    max_normal_error = 0.0
    sign_violations = 0
    sign_gated = 0
    normal_gated = 0
    all_finite = true
    for index in 1:length(probes)
        d_cpu_world = Float64(cpu_d[index]) * SCALE
        d_gpu_world = Float64(gpu_d[index]) * SCALE
        all_finite &= isfinite(cpu_d[index]) && isfinite(gpu_d[index])
        all_finite &= all(isfinite, cpu_n[index])
        all_finite &= all(isfinite, (gpu_nx[index], gpu_ny[index], gpu_nz[index]))
        if !outside_world(probes[index])
            max_value_error = max(max_value_error, abs(d_gpu_world - d_cpu_world))
            if abs(d_cpu_world) > 1e-5
                sign_gated += 1
                sign_violations += ((d_cpu_world > 0) == (d_gpu_world > 0)) ? 0 : 1
            end
            fractional = ntuple(3) do axis
                s = (Float64(probes[index][axis]) - BOX_ORIGIN[axis]) / BOX_H
                s - floor(s)
            end
            if all(f -> 1e-4 <= f <= 1 - 1e-4, fractional)
                normal_gated += 1
                n_cpu = cpu_n[index]
                delta = sqrt((gpu_nx[index] - n_cpu[1])^2 + (gpu_ny[index] - n_cpu[2])^2 +
                             (gpu_nz[index] - n_cpu[3])^2)
                max_normal_error = max(max_normal_error, Float64(delta))
            end
        end
    end
    return (
        max_value_error_world_m = max_value_error,
        max_normal_error = max_normal_error,
        sign_violations = sign_violations,
        sign_gated = sign_gated,
        normal_gated = normal_gated,
        all_finite = all_finite,
    )
end

comparison = compare_all(cpu_d, cpu_n, gpu_d, gpu_nx, gpu_ny, gpu_nz, probes)

outside_indices = [index for index in 1:probe_count if outside_world(probes[index])]
outside_exact = all(index -> begin
    expected = Float32(canonical.outside_value) / Float32(SCALE)
    cpu_d[index] == expected && gpu_d[index] == expected &&
        gpu_nx[index] == 0.0f0 && gpu_ny[index] == 0.0f0 && gpu_nz[index] == 0.0f0
end, outside_indices)

identity = if backend == "gpu"
    device = CUDA.device()
    visible = get(ENV, "CUDA_VISIBLE_DEVICES", "0")
    visible in ("0", "1") || error("W1g requires one CUDA-visible GPU index")
    uuid = strip(read(`nvidia-smi --id=$visible --query-gpu=uuid --format=csv,noheader`, String))
    startswith(uuid, "GPU-") && !occursin('\n', uuid) || error("invalid selected GPU UUID")
    (
        gpu_name = CUDA.name(device),
        gpu_uuid = uuid,
        compute_capability = string(CUDA.capability(device)),
        cuda_jl_version = string(pkgversion(CUDA)),
        waterlily_version = string(pkgversion(WaterLily)),
        julia_version = string(VERSION),
        cuda_runtime_version = string(CUDA.runtime_version()),
    )
else
    (
        gpu_name = "cpu", gpu_uuid = "cpu", compute_capability = "cpu",
        cuda_jl_version = "cpu", waterlily_version = string(pkgversion(WaterLily)),
        julia_version = string(VERSION), cuda_runtime_version = "cpu",
    )
end

json_number(x) = x isa Bool ? (x ? "true" : "false") : string(Float64(x))
summary = string(
    "{",
    "\"mode\":\"", backend, "\",",
    "\"source_phi_sha256\":\"", source_sha, "\",",
    "\"device_roundtrip_sha256\":\"", roundtrip_sha, "\",",
    "\"probe_count\":", probe_count, ",",
    "\"bulk_box\":", BULK_BOX, ",",
    "\"bulk_band\":", BULK_BAND, ",",
    "\"representative_count\":", length(representatives), ",",
    "\"representative_names\":[", join(("\"" * name * "\"" for (name, _) in representatives), ","), "],",
    "\"max_value_error_world_m\":", json_number(comparison.max_value_error_world_m), ",",
    "\"max_normal_error\":", json_number(comparison.max_normal_error), ",",
    "\"sign_violations\":", comparison.sign_violations, ",",
    "\"sign_gated_probes\":", comparison.sign_gated, ",",
    "\"normal_gated_probes\":", comparison.normal_gated, ",",
    "\"outside_probes\":", length(outside_indices), ",",
    "\"outside_exact\":", outside_exact, ",",
    "\"all_finite\":", comparison.all_finite, ",",
    "\"scalar_index_blocked\":", scalar_index_blocked, ",",
    "\"backend_identity\":{",
    "\"gpu_name\":\"", identity.gpu_name, "\",",
    "\"gpu_uuid\":\"", identity.gpu_uuid, "\",",
    "\"compute_capability\":\"", identity.compute_capability, "\",",
    "\"cuda_jl_version\":\"", identity.cuda_jl_version, "\",",
    "\"waterlily_version\":\"", identity.waterlily_version, "\",",
    "\"julia_version\":\"", identity.julia_version, "\",",
    "\"cuda_runtime_version\":\"", identity.cuda_runtime_version, "\"",
    "}",
    "}",
)
summary_path = out_prefix * ".summary.json"
write(summary_path, summary * "\n")
println("W1G_SUMMARY_BEGIN")
println(summary)
println("W1G_SUMMARY_END")
println("W1G_FIXTURE_DONE ", backend, " ", summary_path)
