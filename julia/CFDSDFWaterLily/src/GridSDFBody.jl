"""
GridSDFBody — SDF-native W1 geometry adapter contract (contract 1, plan v2.1).

Semantics (registered in `docs/evidence/sdf_native_w1_adapter_criteria_2026_09.json`):

- `phi < 0` solid / `phi > 0` fluid (immutable repository convention).
- `phi` is a 3D array of nodal SDF samples on a uniform axis-aligned point
  lattice in *world* space (meters): node `(i, j, k)` sits at
  `origin[d] + (idx[d] - 1) * h[d]`.
- `sdf_at_world(x_world)` evaluates the trilinear interpolation over the
  eight surrounding nodes.  Any world point outside the closed design box
  returns the registered strictly positive fluid extension constant (the
  zero level can never exist there), never an interpolated negative value.
- The world<->solver map is the exact affine pair
  `x_world = scale .* x_solver .+ offset` with `scale = 1 ./ h`, so the
  round trip `world -> solver -> world` is exact in Float64.
- The zero level must keep at least `margin_m` clearance from every design
  box face; a fixture violating that is refused fail-closed at construction.

No solver, force, or physics semantics live in this module (W1 scope).
"""

module GridSDFBody

export GridSDF, GridSDFError, sdf_at_world, sdf_value_gradient_at_world,
    world_to_solver, solver_to_world, zero_level_margin_m

struct GridSDFError <: Exception
    msg::String
end

Base.showerror(io::IO, e::GridSDFError) = print(io, "GridSDFError: ", e.msg)

function _check(cond::Bool, msg::AbstractString)
    cond || throw(GridSDFError(msg))
    return nothing
end

"""
    GridSDF{A,T}

Uniform Cartesian grid SDF in world (meter) coordinates.

`phi[i, j, k]` is the nodal SDF sample at world position
`origin + (i-1, j-1, k-1) .* h`.  Construct through [`GridSDF`](@ref), which
enforces the fail-closed contract gates.
"""
struct GridSDF{A,T}
    phi::A
    origin::NTuple{3,T}          # world position of node (1,1,1), meters
    h::NTuple{3,T}               # node spacing per axis, meters
    shape::NTuple{3,Int}         # number of nodes per axis
    outside_value::T             # strictly positive fluid extension
    margin_m::T                  # required zero-level clearance to a box face
end

"""
    GridSDF(phi; origin, h, outside_value, margin_m)

Build the adapter with fail-closed contract checks:

1. `phi` is a 3D array of real values, finite everywhere;
2. `origin` and `h` hold three finite entries, and every `h` is positive;
3. `outside_value` is finite and strictly positive;
4. the zero level keeps at least `margin_m` clearance from every design box
   face (the margin hard gate; a violating fixture is refused).
"""
function GridSDF(
    phi::AbstractArray{<:Real,3};
    origin::NTuple{3,<:Real},
    h::NTuple{3,<:Real},
    outside_value::Real,
    margin_m::Real,
)
    _check(size(phi, 1) >= 2 && size(phi, 2) >= 2 && size(phi, 3) >= 2,
        "phi needs at least two nodes per axis")
    _check(all(isfinite, phi), "phi must be finite everywhere")
    _check(all(isfinite, origin), "origin must be finite")
    _check(all(isfinite, h), "h must be finite")
    _check(all(>(0.0), h), "h must be strictly positive per axis")
    _check(isfinite(outside_value) && outside_value > 0.0,
        "outside_value must be finite and strictly positive")
    _check(isfinite(margin_m) && margin_m >= 0.0,
        "margin_m must be finite and non-negative")
    shape = (size(phi, 1), size(phi, 2), size(phi, 3))
    margin = zero_level_margin_m(phi, origin, h)
    # the margin arithmetic accumulates two legal rounding sources: the
    # face-gap Float64 arithmetic (~1 ulp per subtraction) and the caller's
    # Float32 phi quantization (up to ~1.2e-8 m at phi ~ -0.05), so the
    # hard gate allows a 1e-6 m absolute slack; anything larger refuses
    # fail-closed
    tol = 1e-6
    if !(margin >= margin_m - tol)
        throw(GridSDFError(
            "interface-to-boundary margin gate failed: measured zero-level " *
            "clearance $(margin) m to a design-box face is below the " *
            "required margin $(margin_m) m; refusing the fixture fail-closed"))
    end
    return GridSDF(phi, origin, h, shape, outside_value, margin_m)
end

"""
    zero_level_margin_m(phi, origin, h)

Conservative solid-side Lipschitz bound on the zero-level clearance (meters)
to the design-box boundary.  For a nodal metric signed-distance field
(|phi| = distance to the surface, Lipschitz-1) every zero level is within
`|phi|` of any node, so per solid node the surface stays at least
`(face_gap - |phi|)` away from a box face; the bound is the minimum of that
quantity over all `phi < 0` nodes.  This is valid for any metric phi and
tight by construction.  All-solid fixtures raise fail-closed.
"""
function zero_level_margin_m(
    phi::AbstractArray{<:Real,3},
    origin::NTuple{3,<:Real},
    h::NTuple{3,<:Real},
)
    nx, ny, nz = size(phi)
    ox, oy, oz = origin
    hx, hy, hz = h
    best = Inf
    @inbounds for k in 1:nz, j in 1:ny, i in 1:nx
        p = phi[i, j, k]
        if p < 0.0
            dx = min((i - 1) * hx, (nx - i) * hx)
            dy = min((j - 1) * hy, (ny - j) * hy)
            dz = min((k - 1) * hz, (nz - k) * hz)
            best = min(best, min(dx, dy, dz) + p)  # gap - |phi| = gap + p (p < 0)
        end
    end
    if !isfinite(best)
        all(q -> q > zero(eltype(phi)), phi) ||
            throw(GridSDFError(
                "all-solid fixture: solid touching the design box leaves no " *
                "zero level and would pollute the outside fluid extension"))
        return Inf
    end
    return best
end

"""
    world_to_solver(g, x_world) -> x_solver

Affine map `x_solver = (x_world - origin) ./ h` (exact in Float64).
"""
world_to_solver(g::GridSDF, x_world::NTuple{3,Float64}) =
    ((x_world[1] - g.origin[1]) / g.h[1],
     (x_world[2] - g.origin[2]) / g.h[2],
     (x_world[3] - g.origin[3]) / g.h[3])

"""
    solver_to_world(g, x_solver) -> x_world

Affine inverse `x_world = origin + x_solver .* h` (exact in Float64).
"""
solver_to_world(g::GridSDF, x_solver::NTuple{3,Float64}) =
    (g.origin[1] + x_solver[1] * g.h[1],
     g.origin[2] + x_solver[2] * g.h[2],
     g.origin[3] + x_solver[3] * g.h[3])

"""
    sdf_at_world(g, x_world) -> Float64

Trilinear interpolation of `phi` at the world point, caller-side guidance
value.  Outside the closed design box returns `g.outside_value` exactly.
"""
function sdf_at_world(g::GridSDF{A,T}, x_world::NTuple{3,Float64})::Float64 where {A,T}
    nx, ny, nz = g.shape
    xs = (x_world[1] - g.origin[1]) / g.h[1]
    ys = (x_world[2] - g.origin[2]) / g.h[2]
    zs = (x_world[3] - g.origin[3]) / g.h[3]
    if !(0.0 <= xs <= (nx - 1) && 0.0 <= ys <= (ny - 1) && 0.0 <= zs <= (nz - 1))
        return Float64(g.outside_value)
    end
    i0 = min(floor(Int, xs) + 1, nx - 1)
    j0 = min(floor(Int, ys) + 1, ny - 1)
    k0 = min(floor(Int, zs) + 1, nz - 1)
    tx = xs - (i0 - 1)
    ty = ys - (j0 - 1)
    tz = zs - (k0 - 1)
    phi = g.phi
    v000 = Float64(phi[i0,     j0,     k0])
    v100 = Float64(phi[i0 + 1, j0,     k0])
    v010 = Float64(phi[i0,     j0 + 1, k0])
    v110 = Float64(phi[i0 + 1, j0 + 1, k0])
    v001 = Float64(phi[i0,     j0,     k0 + 1])
    v101 = Float64(phi[i0 + 1, j0,     k0 + 1])
    v011 = Float64(phi[i0,     j0 + 1, k0 + 1])
    v111 = Float64(phi[i0 + 1, j0 + 1, k0 + 1])
    bilinear_bot = (1 - tx) * v000 + tx * v100
    bilinear_top = (1 - tx) * v001 + tx * v101
    bilinear_bot_hi = (1 - tx) * v010 + tx * v110
    bilinear_top_hi = (1 - tx) * v011 + tx * v111
    front = (1 - tz) * bilinear_bot + tz * bilinear_top
    back = (1 - tz) * bilinear_bot_hi + tz * bilinear_top_hi
    return (1 - ty) * front + ty * back
end

"""
    sdf_value_gradient_at_world(g, x_world) -> (value, gradient)

World-space trilinear SDF value and its analytic gradient.  The value is
defined as `sdf_at_world(g, x_world)` (bitwise identical by construction);
the gradient is the exact gradient of the same trilinear polynomial with
respect to the world coordinates.  Outside the closed design box the value
is the extension constant and the gradient is exactly zero (the extension is
constant).  This is the bridge geometry normal for the W2 WaterLily body; it
is not a finite-difference stencil.
"""
function sdf_value_gradient_at_world(
    g::GridSDF{A,T},
    x_world::NTuple{3,Float64},
)::Tuple{Float64,NTuple{3,Float64}} where {A,T}
    value = sdf_at_world(g, x_world)
    nx, ny, nz = g.shape
    xs = (x_world[1] - g.origin[1]) / g.h[1]
    ys = (x_world[2] - g.origin[2]) / g.h[2]
    zs = (x_world[3] - g.origin[3]) / g.h[3]
    if !(0.0 <= xs <= (nx - 1) && 0.0 <= ys <= (ny - 1) && 0.0 <= zs <= (nz - 1))
        return (value, (0.0, 0.0, 0.0))
    end
    i0 = min(floor(Int, xs) + 1, nx - 1)
    j0 = min(floor(Int, ys) + 1, ny - 1)
    k0 = min(floor(Int, zs) + 1, nz - 1)
    tx = xs - (i0 - 1)
    ty = ys - (j0 - 1)
    tz = zs - (k0 - 1)
    phi = g.phi
    v000 = Float64(phi[i0,     j0,     k0])
    v100 = Float64(phi[i0 + 1, j0,     k0])
    v010 = Float64(phi[i0,     j0 + 1, k0])
    v110 = Float64(phi[i0 + 1, j0 + 1, k0])
    v001 = Float64(phi[i0,     j0,     k0 + 1])
    v101 = Float64(phi[i0 + 1, j0,     k0 + 1])
    v011 = Float64(phi[i0,     j0 + 1, k0 + 1])
    v111 = Float64(phi[i0 + 1, j0 + 1, k0 + 1])
    dvdtx = (1 - ty) * (1 - tz) * (v100 - v000) +
            ty * (1 - tz) * (v110 - v010) +
            (1 - ty) * tz * (v101 - v001) +
            ty * tz * (v111 - v011)
    dvdtz = (1 - ty) * ((1 - tx) * v001 + tx * v101) +
            ty * ((1 - tx) * v011 + tx * v111) -
            ((1 - ty) * ((1 - tx) * v000 + tx * v100) +
             ty * ((1 - tx) * v010 + tx * v110))
    dvdtz_ty = (1 - tx) * (v011 - v001) + tx * (v111 - v101)
    dvdtz_ty0 = (1 - tx) * (v010 - v000) + tx * (v110 - v100)
    dvdty = dvdtz_ty0 + tz * (dvdtz_ty - dvdtz_ty0)
    return (value, (dvdtx / g.h[1], dvdty / g.h[2], dvdtz / g.h[3]))
end

end # module
