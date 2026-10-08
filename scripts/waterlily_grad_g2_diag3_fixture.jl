# G2-DIAG3: a small controlled Poisson fixture (a Dual sphere body whose radius carries the tangent) shared by the CPU fixture test and the
# T4 preflight.  The includer must define `FD`, `to_device`, and have `using WaterLily` active and `SVector` defined.
struct DualSphere{R,V} <: WaterLily.AbstractBody
    c::SVector{3,V}
    R::R            # Dual radius: d(sdf)/d(alpha) = -1
end
function WaterLily.measure(b::DualSphere, x, t; fastd²=Inf)
    r = x - b.c
    ρ = sqrt(sum(abs2, r))
    return (ρ - b.R, r / ρ, zero(x))
end

fixture_tag() = nothing
fixture_dual_type(::Type{V}) where {V} = FD.Dual{typeof(FD.Tag(fixture_tag, V)),V,1}

# returns (sim, ml) with the Poisson operator of a flow around a Dual sphere; `radius_shift` moves the primal radius (finite differences)
function fixture_system(::Type{V}; N=32, R0=7.0, radius_shift=0.0, mem=Array) where {V}
    DT = fixture_dual_type(V)
    R = DT(V(R0 + radius_shift), FD.Partials((one(V),)))
    body = DualSphere(SVector{3,V}(N / 2, N / 2, N / 2), R)
    sim = WaterLily.Simulation((N, N, N), (1, 0, 0), N / 4; ν=V(0.01), body=body, T=DT, mem=mem)
    return sim, sim.pois, DT
end

# smooth value / tangent right-hand sides on the ACTIVE cells (iD != 0; the cells inside the body are masked out of the system), with the mean over the
# active cells set to `vmean` / `tmean` (0 = a compatible Neumann right-hand side)
function fixture_rhs(::Type{V}, ml; vmean=0.0, tmean=0.0, scale=1.0) where {V}
    dims = size(ml.x)
    active = Array(ml.levels[1].iD) .!= 0
    for I in CartesianIndices(dims)
        i, j, k = Tuple(I)
        (1 < i < dims[1] && 1 < j < dims[2] && 1 < k < dims[3]) || (active[I] = false)
    end
    active = map(a -> FD.value(a), active) |> x -> x .!= 0
    z = zeros(V, dims); t = zeros(V, dims)
    for I in CartesianIndices(dims)
        active[I] || continue
        i, j, k = Tuple(I)
        z[I] = V(sin(0.37i) * cos(0.23j) + 0.5 * sin(0.11k + 0.3i))
        t[I] = V(0.7cos(0.29i + 0.1j) * sin(0.31k) + 0.2 * sin(0.5j))
    end
    n = count(active)
    z[active] .+= V(vmean) - sum(z[active]) / n
    t[active] .+= V(tmean) - sum(t[active]) / n
    return V(scale) .* z, V(scale) .* t
end

function fixture_load!(ml, z, t, DT)   # x = 0, z = Dual(z, t)
    p = ml.levels[1]
    p.z .= to_device(DT.(z, FD.Partials.(tuple.(t))))
    fill!(p.x, zero(DT))
    return ml
end

function make_refiner(ml, DT; fixed=0, tau=1e-6, maxit=64)
    V = FD.valtype(DT)
    tan_of = TanOf(); add_tan = AddTan(); tmax = TMax()
    aux = WaterLily.MultiLevelPoisson(to_device(zeros(V, size(ml.x))), to_device(FD.value.(Array(ml.L))), to_device(zeros(V, size(ml.x))))
    WaterLily.update!(aux)
    mask = to_device(V.(Array(aux.levels[1].iD) .!= 0))
    return WaterLily.TangentRefine(aux, tan_of, add_tan, tmax, mask, Float64(count(!iszero, Array(mask))), fixed, tau, maxit, NTuple{7,Float64}[])
end
struct TanOf end
(::TanOf)(x) = FD.partials(x, 1)
struct TMax end
(::TMax)(x) = abs(FD.partials(x, 1))
struct AddTan end
(::AddTan)(x::FD.Dual{T,V,1}, e) where {T,V} = FD.Dual{T,V,1}(FD.value(x), FD.Partials{1,V}((FD.partials(x, 1) + V(e),)))

function make_dual_stop(ml, DT; tau=1e-6, maxit=64)
    V = FD.valtype(DT)
    mask = to_device(V.(FD.value.(Array(ml.levels[1].iD)) .!= 0))
    return WaterLily.DualStop(tau, maxit, TMax(), TanOf(), mask, Float64(count(!iszero, Array(mask))), NTuple{7,Float64}[])
end
# the value-only operator and the active mask must still be those of the live Dual system (geometry is time independent: measure! reproduces L bit for bit)
function aux_operator_matches(ml, h)
    FD.value.(Array(ml.L)) == Array(h.aux.L) && (Array(h.mask) .!= 0) == (FD.value.(Array(ml.levels[1].iD)) .!= 0)
end
