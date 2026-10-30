"""
Runtime — solver runtime fingerprint for registered runs.

Every registered WaterLily run advertises its runtime identity: Julia
version, thread count, WaterLily version, backend, and the registered
affine solver<->world map.  The Python job runner records this fingerprint
next to the evidence; a changed Julia patch, WaterLily version, backend, or
map is a different backend identity.
"""

using WaterLily
using LinearAlgebra

"""
    runtime_fingerprint() -> NamedTuple

Environment identity of the executing process.
"""
function runtime_fingerprint()
    return (
        julia_version = string(VERSION),
        julia_threads = Threads.nthreads(),
        waterlily_version = string(pkgversion(WaterLily)),
        waterlily_backend = string(WaterLily.backend),
        blas_threads = BLAS.get_num_threads(),
    )
end

"""
    affine_map_fingerprint(body::GridSDFWaterLilyBody) -> NamedTuple

Registered solver->world affine map advertised for a grid-SDF body.
"""
function affine_map_fingerprint(body::GridSDFWaterLilyBody)
    return (
        world_origin_m = collect(body.world_origin_m),
        world_per_solver = body.world_per_solver,
        solver_per_meter = 1.0 / body.world_per_solver,
    )
end
