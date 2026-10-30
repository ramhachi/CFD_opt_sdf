# W0b T4 CUDA environment smoke (no CFD solver step).
#
# Usage (on the explicitly selected T4 runtime):
#   julia --project=<T4 env> scripts/w0b_t4_smoke.jl
#
# Exercises only CUDA.jl, CuArray, KernelAbstractions and the WaterLily CUDA
# extension activation.  It constructs no WaterLily.Simulation and calls no
# sim_step!/mom_step! (registered gate G5).

using CUDA
using WaterLily  # reexports @kernel, @index, get_backend
using Pkg

println("JULIA_VERSION ", VERSION)
println("CUDA_FUNCTIONAL ", CUDA.functional())
CUDA.functional() || error("CUDA.functional() is false")

device = CUDA.device()
println("GPU_NAME ", CUDA.name(device))
capability = try
    CUDA.capability(device)
catch err
    nothing
end
println("GPU_COMPUTE_CAPABILITY ", capability === nothing ? "unknown" : string(capability))
total_memory = try
    CUDA.total_memory(device)
catch err
    nothing
end
println("GPU_TOTAL_MEMORY_BYTES ", total_memory === nothing ? "unknown" : string(total_memory))
println("CUDA_DRIVER_VERSION ", CUDA.driver_version())
println("CUDA_RUNTIME_VERSION ", CUDA.runtime_version())
println("CUDA_JL_VERSION ", pkgversion(CUDA))
println("WATERLILY_VERSION ", pkgversion(WaterLily))

waterlily_cuda_ext = Base.get_extension(WaterLily, :WaterLilyCUDAExt)
println("WATERLILY_CUDA_EXT ", waterlily_cuda_ext !== nothing)
waterlily_cuda_ext !== nothing || error("WaterLilyCUDAExt is not loaded")

host = Float32[1, 2, 3, 4]
a = CuArray(host)
b = a .* 2.0f0
cuarray_ok = Array(b) == Float32[2, 4, 6, 8] && sum(a) == 10.0f0
println("CUARRAY_SMOKE ", cuarray_ok)
cuarray_ok || error("CuArray smoke failed")

@kernel function halve!(x)
    I = @index(Global)
    x[I] = x[I] / 2
end
halve!(get_backend(a))(a; ndrange = length(a))
synchronize()
ka_ok = Array(a) == Float32[0.5, 1.0, 1.5, 2.0]
println("KA_SMOKE ", ka_ok)
ka_ok || error("KernelAbstractions CUDA smoke failed")

println("NO_SOLVER_STEP")
println("W0B_SMOKE_DONE")
