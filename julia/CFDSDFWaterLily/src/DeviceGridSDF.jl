"""
DeviceGridSDF — derived CUDA representation of the canonical CPU `GridSDF`.

Ownership contract (W1g): the canonical CPU phi is authoritative.  The device
representation is an explicit derived copy created by [`device_copy`]; its
`source_phi_sha256` records the canonical source, and
[`device_roundtrip_sha`] recomputes the same byte rule after reading the
device array back to the host, so G1 can require exact equality.

The canonical CPU gate (outside extension, margin) is evaluated before the
copy; the device representation reuses the registered Float32 fields through
the raw (gate-free) constructor, because the margin gate is a CPU-side
pre-launch check and must not run on device data.

This file is loaded on the T4 runtime only:

    include(".../CFDSDFWaterLily/src/CFDSDFWaterLily.jl")
    Base.include(CFDSDFWaterLily, ".../CFDSDFWaterLily/src/DeviceGridSDF.jl")
    using .CFDSDFWaterLily.DeviceGridSDF

The CPU environment has no CUDA dependency and never loads this file.
"""

module DeviceGridSDF

using CUDA
using SHA
using ..GridSDFBody: GridSDF

export DeviceGridSDF, device_copy, canonical_phi_sha256, device_roundtrip_sha

"""
    DeviceGridSDF(grid, source_phi_sha256)

Derived device grid plus the SHA-256 of the canonical CPU source phi.
"""
struct DeviceGridSDF{A,T}
    grid::GridSDF{A,T}
    source_phi_sha256::String
end

"""
    canonical_phi_sha256(phi) -> String

Registered byte rule: SHA-256 of the column-major Float32 bytes of the phi
array (Julia `vec` order), identical for host and device arrays.
"""
canonical_phi_sha256(phi) = bytes2hex(sha256(reinterpret(UInt8, vec(phi))))

"""
    device_copy(grid::GridSDF) -> DeviceGridSDF

Explicit derived copy: phi moves to a CuArray, the map fields are Float32, and
the canonical source phi sha is recorded.  The gate constructor is not rerun
(the gate already passed on the canonical CPU grid).
"""
function device_copy(grid::GridSDF)
    device_phi = CuArray(grid.phi)
    device_grid = GridSDF(
        device_phi,
        Float32.(grid.origin),
        Float32.(grid.h),
        grid.shape,
        Float32(grid.outside_value),
        Float32(grid.margin_m),
    )
    return DeviceGridSDF(device_grid, canonical_phi_sha256(grid.phi))
end

"""
    device_roundtrip_sha(device::DeviceGridSDF) -> String

Read the device phi back to the host and apply the same byte rule.
"""
function device_roundtrip_sha(device::DeviceGridSDF)
    return canonical_phi_sha256(Array(device.grid.phi))
end

end # module
