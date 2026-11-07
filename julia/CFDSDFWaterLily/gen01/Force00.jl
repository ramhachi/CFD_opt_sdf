# Opt-in FORCE-00 readouts. Explicitly include into CFDSDFWaterLily.
using WaterLily

# FORCE-00 project-side readouts. WaterLily remains pinned at 1.8.0.
# Primary recipes: https://github.com/WaterLily-jl/WaterLily.jl/issues/369
# and https://github.com/WaterLily-jl/WaterLily.jl/issues/293 .

@inline _force00_nds(I::CartesianIndex{D}, μ₀, ::Type{T}) where {D,T} =
    WaterLily.SVector{D,T}(ntuple(i -> T(μ₀[I + WaterLily.δ(i, I), i]) - T(μ₀[I, i]), D))

"""
    nds_telescoping(sim)

The discrete outward body area vector `μ₀[I+δ(i,I),i] - μ₀[I,i]`
from the moments already stored by `measure!`. Ghost cells are zero. Face
values are promoted *before* subtraction, so Float32 face differences also
telescope under Float64 reduction. No SDF is measured and no flow field changes.

This raw field includes WaterLily's zeroed domain faces. The force functions
below omit those artificial boundary jumps, or integrate an explicit candidate
box when the scene also contains a ground/body outside that box.
"""
function nds_telescoping(sim)
    μ₀ = sim.flow.μ₀
    T = promote_type(Float64, eltype(μ₀))
    n = similar(μ₀, T)
    n .= zero(T)
    WaterLily.@loop n[I, :] .= _force00_nds(I, μ₀, T) over I in WaterLily.inside(sim.flow.p)
    return n
end

function _force00_region(sim, box; domain_inset=1)
    p = sim.flow.p
    D = ndims(p)
    D in (2, 3) || throw(ArgumentError("FORCE-00 supports 2D and 3D"))
    if isnothing(box)
        # BC! sets normal μ₀ to zero at faces 2 and size(p,i). Exclude
        # their one-cell jumps; the closed body must be inside this region.
        return WaterLily.inside(p; buff=2)
    end
    box isa Tuple && length(box) == D && all(r -> r isa UnitRange{<:Integer} && !isempty(r), box) ||
        throw(ArgumentError("box must be a tuple of nonempty integer cell-index ranges"))
    all(i -> first(box[i]) >= 2 + domain_inset &&
             last(box[i]) <= size(p, i) - 1 - domain_inset, 1:D) ||
        throw(ArgumentError("box violates the $domain_inset-cell physical-domain inset"))
    return CartesianIndices(box)
end

_force00_sum(field, D) = Array(sum(identity, field; dims=ntuple(identity, D)))[:]

"""
    pressure_force_nds(sim; box=nothing)

Pressure reaction on the fluid, using stored `μ₀` and Float64 arithmetic.
`box` contains pressure-cell indices; it must enclose the complete candidate
support and exclude other bodies. The default omits domain BC jumps and is
for a closed body entirely inside the domain. Use `force_on_body_nds` for
the repository's opposite, physical body-force convention.
"""
function pressure_force_nds(sim; box=nothing)
    p, μ₀ = sim.flow.p, sim.flow.μ₀
    T = promote_type(Float64, eltype(p))
    region = _force00_region(sim, box)
    df = similar(μ₀, T)
    df .= zero(T)
    WaterLily.@loop df[I, :] .= T(p[I]) * _force00_nds(I, μ₀, T) over I in region
    return _force00_sum(df, ndims(p))
end

"""
    viscous_force_nds(sim; box=nothing)

The existing `-2ν S(I,u)` viscous reaction with the same telescoping area
vector and region as `pressure_force_nds`. This retains the existing strain
discretization; it does not supply a wall-resolved shear model.
"""
function viscous_force_nds(sim; box=nothing)
    u, μ₀, ν = sim.flow.u, sim.flow.μ₀, sim.flow.ν
    T = promote_type(Float64, eltype(u))
    region = _force00_region(sim, box)
    df = similar(μ₀, T)
    df .= zero(T)
    WaterLily.@loop df[I, :] .= -2T(ν) * WaterLily.S(I, u) * _force00_nds(I, μ₀, T) over I in region
    return _force00_sum(df, ndims(sim.flow.p))
end

"""`-(pressure_force_nds(sim) + viscous_force_nds(sim))`, force on the body."""
force_on_body_nds(sim; box=nothing) = -(pressure_force_nds(sim; box) + viscous_force_nds(sim; box))

@inline function _force00_cv_face!(values, p, u, ν, I::CartesianIndex{D}, J,
                                  axis, side, ::Type{T}) where {D,T}
    x = WaterLily.loc(axis, I, eltype(p))
    vel = WaterLily.interp(x, u)
    pressure = WaterLily.interp(x, p)
    strain = (WaterLily.S(I, u) + WaterLily.S(I - WaterLily.δ(axis, I), u)) / 2
    for i in 1:D
        values[J, i, 1] = -T(side) * T(vel[i]) * T(vel[axis])
        values[J, i, 2] = i == axis ? -T(side) * T(pressure) : zero(T)
        values[J, i, 3] = T(side) * 2T(ν) * T(strain[i, axis])
    end
end

@inline function _force00_cv_storage!(values, u, u⁰, dt, I::CartesianIndex{D}, J,
                                     ::Type{T}) where {D,T}
    for i in 1:D
        δ = WaterLily.δ(i, I)
        # Interpolate both staggered velocities to the pressure-cell centre.
        now = (T(u[I, i]) + T(u[I + δ, i])) / 2
        prev = (T(u⁰[I, i]) + T(u⁰[I + δ, i])) / 2
        values[J, i] = -(now - prev) / dt
    end
end

@inline _force00_cv_distance(body, I, axis, T, t) =
    WaterLily.sdf(body, WaterLily.loc(axis, I, T), t; fastd²=T(Inf))

function _force00_cv_face_clearance(sim, indices, axis, T)
    # Validation stays on the array backend; only a scalar reduction is read
    # on the host. Distances are checked at every face quadrature point.
    distances = similar(sim.flow.p, T, size(indices))
    offset = first(indices) - oneunit(first(indices))
    body, t, Tp = sim.body, WaterLily.time(sim.flow), eltype(sim.flow.p)
    WaterLily.@loop distances[J] = _force00_cv_distance(body,
        J + offset, axis, Tp, t) over J in CartesianIndices(size(distances))
    minimum(distances) >= T(4) ||
        throw(ArgumentError("CV face is less than four cells from the scene body (including ground)"))
    return nothing
end

@inline function _force00_box_support!(flags, body, I::CartesianIndex{D}, lower,
                                     upper, band, t, ::Type{T}) where {D,T}
    d = WaterLily.sdf(body, WaterLily.loc(0, I, T), t; fastd²=band^2)
    enclosed = all(i -> lower[i] <= I[i] <= upper[i], 1:D)
    flags[I] = !isfinite(d) ? UInt8(4) : d < band ?
        (enclosed ? UInt8(1) : UInt8(2)) : UInt8(0)
end

"""
    validate_force_box(sim, box; body=sim.body)

Read-only candidate/box preflight. Require nonempty candidate support and
enclose every physical pressure-cell centre with candidate SDF `< 2+ϵ`
(including the solid), matching `measure!`'s narrow-band extent. Check the
two-cell domain inset and four-cell sampled scene-face clearance as well.
An explicit `body` selects the candidate when `sim.body` includes ground.
Only backend reductions reach the host; no solver field is changed.

Static-body jobs may call this once, then use `force_readouts(...;
validate_box=false)` for that same immutable body and box. Moving bodies
must retain the default validation at each measurement.
"""
function validate_force_box(sim, box; body=sim.body)
    cells = _force00_region(sim, box; domain_inset=2)
    isnothing(box) && throw(ArgumentError("candidate readouts require an explicit box"))
    p = sim.flow.p
    T, D = eltype(p), ndims(p)
    ϵ = hasproperty(sim, :ϵ) ? T(sim.ϵ) : one(T)
    band, t = T(2) + ϵ, WaterLily.time(sim.flow)
    lower, upper = Tuple(first(cells)), Tuple(last(cells))
    flags = similar(p, UInt8)
    flags .= UInt8(0)
    WaterLily.@loop _force00_box_support!(flags, body, I, lower, upper,
        band, t, T) over I in WaterLily.inside(p)
    largest = maximum(flags)
    largest < 4 || throw(ArgumentError("candidate SDF is non-finite"))
    largest < 2 || throw(ArgumentError("box does not enclose the complete candidate support"))
    largest == 1 || throw(ArgumentError("candidate has no support in the flow domain"))
    for axis in 1:D, side in (-1, 1)
        face_index = side < 0 ? first(box[axis]) : last(box[axis]) + 1
        face = CartesianIndices(ntuple(i -> i == axis ? (face_index:face_index) : box[i], D))
        _force00_cv_face_clearance(sim, face, axis, promote_type(Float64, T))
    end
    return box
end

"""
    control_volume_terms(sim, box)

Cartesian unit-cell momentum balance, in the repository's body-force sign:
`-(∮(u(u⋅n)+p*n-2ν*S*n)dS + ∫(u-u⁰)/Δt_previous dV)`.
Returns `advection`, `pressure`, `viscous`, `storage`, and `total` vectors,
so analytic tests can inspect the terms separately.

`box::NTuple{D,UnitRange}` lists enclosed pressure cells, including endpoints.
Its physical lower/upper faces are `first(box[i])-2` and `last(box[i])-1`
in solver coordinates. Faces stay at least two cells from the physical
domain boundary. Every face quadrature point must have scene SDF ≥4, which
also excludes ground; callers are responsible for enclosing the intended
candidate. This is a sampled SDF clearance check, not a continuum geometry
certificate for a nonmetric SDF.

Velocity and pressure are linearly interpolated to staggered face centres;
strain is the average of `WaterLily.S` at the two adjoining cell centres.
Storage uses cell-centred staggered velocities and `flow.Δt[end-1]`, the step
actually taken, never the proposed next CFL step. Density and grid spacing
are one in solver units. All reductions and products accumulate in Float64.
Kernels run through WaterLily's existing CPU/GPU `@loop`; no field is changed.
"""
function control_volume_terms(sim, box)
    cells = _force00_region(sim, box; domain_inset=2)
    isnothing(box) && throw(ArgumentError("CV requires an explicit box"))
    p, u, u⁰, ν = sim.flow.p, sim.flow.u, sim.flow.u⁰, sim.flow.ν
    D, T = ndims(p), promote_type(Float64, eltype(p))
    length(sim.flow.Δt) >= 2 || throw(ArgumentError("CV storage requires a completed step"))
    dt = T(sim.flow.Δt[end - 1])
    isfinite(dt) && dt > 0 || throw(ArgumentError("CV previous time step must be finite and positive"))
    advection, pressure, viscous = zeros(T, D), zeros(T, D), zeros(T, D)
    for axis in 1:D, side in (-1, 1)
        face_index = side < 0 ? first(box[axis]) : last(box[axis]) + 1
        face = CartesianIndices(ntuple(i -> i == axis ? (face_index:face_index) : box[i], D))
        _force00_cv_face_clearance(sim, face, axis, T)
        values = similar(p, T, (size(face)..., D, 3))
        offset = first(face) - oneunit(first(face))
        WaterLily.@loop _force00_cv_face!(values, p, u, ν, J + offset, J, axis, side, T) over J in CartesianIndices(size(face))
        totals = reshape(_force00_sum(values, D), D, 3)
        advection .+= totals[:, 1]
        pressure .+= totals[:, 2]
        viscous .+= totals[:, 3]
    end
    storage_values = similar(p, T, (size(cells)..., D))
    offset = first(cells) - oneunit(first(cells))
    WaterLily.@loop _force00_cv_storage!(storage_values, u, u⁰, dt, J + offset, J, T) over J in CartesianIndices(size(cells))
    storage = _force00_sum(storage_values, D)
    all(isfinite, vcat(advection, pressure, viscous, storage)) ||
        throw(ArgumentError("non-finite CV momentum term"))
    total = advection + pressure + viscous + storage
    return (; advection, pressure, viscous, storage, total)
end

"""`control_volume_terms(sim, box).total`: physical force on the enclosed body."""
control_volume_force(sim, box) = control_volume_terms(sim, box).total

"""
    force_readouts(sim, box; body=sim.body, validate_box=true) -> (cur, nds, cv)

All three physical body-force vectors. The default `cur` is byte-identical
to `-WaterLily.total_force(sim)`; an explicit `body` follows the registered
candidate-only pressure-plus-viscous arithmetic. `nds` uses the stored scene
moments inside `box`, which must exclude other bodies such as the ground.
The legacy functions use `flow.f` as scratch: preserve it even on failure,
so reading forces cannot perturb a later solver step or a second readout.
Candidate enclosure is validated by default; a static-body job can preflight
the immutable body/box once with `validate_force_box` and disable repeat scans.
"""
function force_readouts(sim, box; body=sim.body, validate_box=true)
    validate_box && validate_force_box(sim, box; body)
    saved_f = copy(sim.flow.f)
    try
        cur = if body === sim.body
            -(WaterLily.total_force(sim))
        else
            pressure = -(WaterLily.pressure_force(sim.flow, body))
            viscous = -(WaterLily.viscous_force(sim.flow, body))
            pressure + viscous
        end
        nds = force_on_body_nds(sim; box)
        cv = control_volume_force(sim, box)
        return (; cur, nds, cv)
    finally
        sim.flow.f .= saved_f
    end
end
