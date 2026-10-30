using CUDA
using SHA
using WaterLily

include(joinpath(@__DIR__, "..", "julia", "CFDSDFWaterLily", "src", "CFDSDFWaterLily.jl"))
using .CFDSDFWaterLily.GridSDFBody: GridSDF
Base.include(CFDSDFWaterLily,
    joinpath(@__DIR__, "..", "julia", "CFDSDFWaterLily", "src", "V16PhysicalProfile.jl"))
Base.include(CFDSDFWaterLily,
    joinpath(@__DIR__, "..", "julia", "CFDSDFWaterLily", "src", "DeviceGridSDF.jl"))
using .CFDSDFWaterLily: V16_CANONICAL_SDF_ORIGIN_M, V16_PROFILE_POINT_SHAPE,
    V16_PROFILE_SPACING_M
using .CFDSDFWaterLily.DeviceGridSDF: device_copy, device_roundtrip_sha, kernel_grid

length(ARGS) == 2 || error("usage: owner_type_probe_job.jl <canonical_phi_fortran.raw> <output_dir>")
phi_path, output_dir = ARGS
mkpath(output_dir)

json_escape(value::AbstractString) = replace(replace(replace(String(value), "\\" => "\\\\"), "\"" => "\\\""), "\n" => "\\n")
json_value(::Nothing) = "null"
json_value(value::Bool) = value ? "true" : "false"
json_value(value::Integer) = string(value)
json_value(value::AbstractFloat) = isfinite(value) ? repr(Float64(value)) : "null"
json_value(value::AbstractString) = "\"" * json_escape(value) * "\""
json_value(value::AbstractDict) = "{" * join((json_value(string(k)) * ":" * json_value(v)
    for (k, v) in sort!(collect(pairs(value)); by=pair -> string(first(pair)))), ",") * "}"
json_value(value::AbstractArray) = "[" * join(json_value.(vec(value)), ",") * "]"
write_json(path, value) = write(path, json_value(value), "\n")

function package_identity(mod)
    id = Base.PkgId(mod)
    version = try
        Base.pkgversion(mod)
    catch
        nothing
    end
    return Dict(
        "module" => string(mod),
        "module_fullname" => join(string.(Base.fullname(mod)), "."),
        "package_name" => id.name,
        "package_uuid" => string(id.uuid),
        "package_version" => version === nothing ? nothing : string(version),
    )
end

bytes = read(phi_path)
phi_sha = bytes2hex(sha256(bytes))
length(bytes) == prod(V16_PROFILE_POINT_SHAPE) * sizeof(Float32) || error("canonical phi length mismatch")
phi = reshape(copy(reinterpret(Float32, bytes)), V16_PROFILE_POINT_SHAPE)
c_sha = bytes2hex(sha256(reinterpret(UInt8, vec(permutedims(phi, (3, 2, 1))))))
grid = GridSDF(phi; origin=V16_CANONICAL_SDF_ORIGIN_M,
    h=(V16_PROFILE_SPACING_M, V16_PROFILE_SPACING_M, V16_PROFILE_SPACING_M),
    outside_value=3.0, margin_m=0.15)
owner = device_copy(grid)
view = kernel_grid(owner)
memory_type = typeof(owner.grid.phi).parameters[3]
memory_module = parentmodule(memory_type)
cuda_has_device_memory = isdefined(CUDA, :DeviceMemory)
cuda_memory_type = cuda_has_device_memory ? getfield(CUDA, :DeviceMemory) : nothing
module_has_device_memory = isdefined(memory_module, :DeviceMemory)
module_memory_type = module_has_device_memory ? getfield(memory_module, :DeviceMemory) : nothing

report = Dict{String,Any}(
    "evidence_type" => "diagnostic_only",
    "solver_steps" => 0,
    "qualification" => false,
    "canonical_phi_fortran_sha256" => phi_sha,
    "canonical_phi_c_order_sha256" => c_sha,
    "gpu_roundtrip_sha256" => device_roundtrip_sha(owner),
    "owner" => Dict(
        "type" => string(typeof(owner.grid.phi)),
        "eltype" => string(eltype(owner.grid.phi)),
        "ndims" => ndims(owner.grid.phi),
        "size" => collect(size(owner.grid.phi)),
        "memory_parameter" => string(memory_type),
        "memory_parameter_type" => string(typeof(memory_type)),
        "memory_module" => package_identity(memory_module),
        "module_device_memory_defined" => module_has_device_memory,
        "module_device_memory_is_parameter" => module_has_device_memory ? module_memory_type === memory_type : nothing,
        "cuda_device_memory_defined" => cuda_has_device_memory,
        "cuda_device_memory_is_parameter" => cuda_has_device_memory ? cuda_memory_type === memory_type : nothing,
        "cuda_device_memory_is_module_binding" => cuda_has_device_memory && module_has_device_memory ?
            cuda_memory_type === module_memory_type : nothing,
    ),
    "kernel_view_type" => string(typeof(view.phi)),
    "julia_version" => string(VERSION),
    "cuda_jl_version" => string(pkgversion(CUDA)),
    "waterlily_version" => string(pkgversion(WaterLily)),
    "selected_gpu_name" => CUDA.name(CUDA.device()),
    "selected_gpu_uuid" => get(ENV, "W3_TYPE_PROBE_SELECTED_GPU_UUID", ""),
    "cuda_visible_devices" => get(ENV, "CUDA_VISIBLE_DEVICES", ""),
    "claim_scope" => "exact T4 Julia runtime type identity only; no solver or qualification claim",
)
write_json(joinpath(output_dir, "type_identity.json"), report)
println("W3_OWNER_TYPE_PROBE_RESULT ", json_value(report))
