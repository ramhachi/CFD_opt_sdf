# G2-DIAG5: one-step map instrumentation of WaterLily 1.8.0 (`Base.include`d into WaterLily after scripts/waterlily_grad_g2_diag1_stages.jl, whose
# `diag_mom_predict!` / `diag_mom_correct!` / `diag_mom_project!` are NOT reused here: the convective operator needs a pluggable limiter).
#
# `diag5_mom_step!` equals WaterLily's `mom_step!` statement for statement (Flow.jl 156-167, 190-209, 223-232) except that
#   * the convective scheme `λ` is an explicit argument (`λ = a.λ` reproduces the original; the E4 variants replace only the DERIVATIVE of the limiter),
#   * read-only `hook(tag, a)` calls before the two `conv_diff!` calls and before the two `BDIM!` calls, and read-only `probe(...)` calls after each stage.
# Nothing is clipped, reset, rescaled or replaced.  `@fastmath` only on the step function (as `mom_step!`; it contains only the time arithmetic).
#
# The limiter.  `quick(u,c,d) = median((5c+2d-u)/6, c, median(10c-9u, c, d))` selects one of five candidate expressions; ForwardDiff returns the
# partials of the selected branch (comparisons act on values).  `QuickTie` keeps the VALUE bit for bit (it calls the original `quick`) and replaces only the
# partials by the average of the partials of all candidates whose value lies within `τ` of the selected one (a generalised / surrogate derivative, NOT the
# derivative of the implemented map).  `QuickLinear` returns the partials of the unlimited QUICK candidate (control).

# ---- separable convective operator: same statements as `conv_diff!` (Flow.jl 38-62, `perdir == ()`), with the three roles of `u` split ------------------
#   uadv: the advecting velocity  ϕ(i,CI(I,j),uadv);   ufld: the advected field passed to the limiter;   uvis: the viscous term  ν*∂(j,CI(I,i),uvis)
# `region` selects the boundary-slice loops (:boundary), the inner loops (:interior) or all (:all, the original order); `pair = (i,j)` restricts to one (i,j).
function conv_diff5!(r, uadv, ufld, uvis, Φ, λ::F; ν=0.1, region=:all, pair=nothing) where {F}
    r .= zero(eltype(r))
    N, n = size_u(ufld)
    for i ∈ 1:n, j ∈ 1:n
        (pair === nothing || pair == (i, j)) || continue
        if region !== :interior
            @loop r[I,i] += ϕuL(j,CI(I,i),ufld,ϕ(i,CI(I,j),uadv),λ) - ν*∂(j,CI(I,i),uvis) over I ∈ slice(N,2,j,2)
        end
        if region !== :boundary
            @loop (Φ[I] = ϕu(j,CI(I,i),ufld,ϕ(i,CI(I,j),uadv),λ) - ν*∂(j,CI(I,i),uvis);
                   r[I,i] += Φ[I]) over I ∈ inside_u(N,j)
            @loop r[I-δ(j,I),i] -= Φ[I] over I ∈ inside_u(N,j)
        end
        if region !== :interior
            @loop r[I-δ(j,I),i] += -ϕuR(j,CI(I,i),ufld,ϕ(i,CI(I,j),uadv),λ) + ν*∂(j,CI(I,i),uvis) over I ∈ slice(N,N[j],j,2)
        end
    end
end

# ---- limiter derivative variants -----------------------------------------------------------------------------------------------------------------------
struct QuickTie{T}
    τ::T
end
struct QuickLinear end
@inline function _p1(x)
    return ForwardDiff.partials(x, 1)
end
function (q::QuickTie)(u::D, c::D, d::D) where {D<:ForwardDiff.Dual}
    m = quick(u, c, d)                                         # the original: the VALUE (and the selected branch's partials) are exactly the original ones
    vu, vc, vd = ForwardDiff.value(u), ForwardDiff.value(c), ForwardDiff.value(d)
    pu, pc, pd = _p1(u), _p1(c), _p1(d)
    vC, pC = 10vc - 9vu, 10pc - 9pu                            # inner candidates: 10c-9u, c, d
    mi = median(vC, vc, vd)
    n = 0; s = zero(pu)
    abs(vC - mi) <= q.τ && (n += 1; s += pC)
    abs(vc - mi) <= q.τ && (n += 1; s += pc)
    abs(vd - mi) <= q.τ && (n += 1; s += pd)
    pin = s / n                                                 # n >= 1: the selected inner value is one of the three
    vA, pA = (5vc + 2vd - vu) / 6, (5pc + 2pd - pu) / 6         # outer candidates: (5c+2d-u)/6, c, inner
    mo = median(vA, vc, mi)
    n = 0; s = zero(pu)
    abs(vA - mo) <= q.τ && (n += 1; s += pA)
    abs(vc - mo) <= q.τ && (n += 1; s += pc)
    abs(mi - mo) <= q.τ && (n += 1; s += pin)
    return typeof(m)(ForwardDiff.value(m), ForwardDiff.Partials((s / n,)))
end
function (::QuickLinear)(u::D, c::D, d::D) where {D<:ForwardDiff.Dual}
    m = quick(u, c, d)
    pu, pc, pd = _p1(u), _p1(c), _p1(d)
    return typeof(m)(ForwardDiff.value(m), ForwardDiff.Partials(((5pc + 2pd - pu) / 6,)))
end
(q::QuickTie)(u, c, d) = quick(u, c, d)                         # value-only arguments: the original limiter
(::QuickLinear)(u, c, d) = quick(u, c, d)

# ---- value-only branch audit of one `quick` call --------------------------------------------------------------------------------------------------------
# `median_pick` replicates WaterLily's `median(a,b,c)` (Flow.jl, ties included) but returns WHICH operand it returns: 1, 2 or 3.
@inline function median_pick(a, b, c)
    if a > b
        b >= c && return 2
        a > c && return 3
    else
        b <= c && return 2
        a < c && return 3
    end
    return 1
end
# id: 1 = (5c+2d-u)/6, 2 = c (outer), 3 = 10c-9u, 4 = c (through the inner median), 5 = d.  The kink distance is the smallest pairwise gap among the outer
# candidates and among the inner ones.
function quick_branch(u, c, d)
    vC = 10c - 9u
    ip = median_pick(vC, c, d); mi = ip == 1 ? vC : (ip == 2 ? c : d)
    vA = (5c + 2d - u) / 6
    op = median_pick(vA, c, mi)
    id = op == 1 ? 1 : (op == 2 ? 2 : (ip == 1 ? 3 : (ip == 2 ? 4 : 5)))
    kd = min(abs(vA - c), abs(vA - mi), abs(c - mi), abs(vC - c), abs(vC - d), abs(c - d))
    return id, kd
end
# ids / kink distances of every interior upwind limiter call of `conv_diff!` for the velocity `u` (value arrays): the same stencil and upwind selection as `ϕu`.
function audit_quick(u::AbstractArray{T}) where {T<:AbstractFloat}
    N, n = size_u(u)
    ids = zeros(UInt8, size(u)..., n); kds = fill(T(Inf), size(u)..., n)      # [I..., i, j]  (component i, direction j)
    for i ∈ 1:n, j ∈ 1:n
        for I ∈ inside_u(N, j)
            Ii = CI(I, i)
            a = (u[CI(I, j)] + u[CI(I, j) - δ(i, CI(I, j))]) / 2             # ϕ(i,CI(I,j),u): the advecting velocity
            f = a > 0 ? (u[Ii - 2δ(j, Ii)], u[Ii - δ(j, Ii)], u[Ii]) : (u[Ii + δ(j, Ii)], u[Ii], u[Ii - δ(j, Ii)])
            id, kd = quick_branch(f[1], f[2], f[3])
            ids[Ii, j] = id; kds[Ii, j] = kd
        end
    end
    return ids, kds
end

# ---- the instrumented step -------------------------------------------------------------------------------------------------------------------------------
@fastmath function diag5_mom_step!(a::AbstractFlow, b::AbstractPoisson, λ, probe, hook)
    a.u⁰ .= a.u; scale_u!(a,0); t₁ = sum(a.Δt); t₀ = t₁-a.Δt[end]
    probe(:pre_scale, (u0=a.u⁰,))
    diag5_mom_predict!(a,t₀,t₁,λ,probe,hook)
    diag5_mom_project!(a,b,1,t₁,probe,:project1)
    diag5_mom_correct!(a,t₁,λ,probe,hook)
    diag5_mom_project!(a,b,0.5,t₁,probe,:project2)
    push!(a.Δt,CFL(a))
    probe(:cfl_dt, (dt=a.Δt[end],))
end

function diag5_mom_predict!(a::AbstractFlow, t₀, t₁, λ, probe, hook)
    hook(:predict_conv, a)
    conv_diff!(a.f,a.u⁰,a.σ,λ;ν=a.ν,perdir=a.perdir)
    probe(:predict_conv_diff, (f=a.f,))
    accelerate!(a.f,t₀,a.g,a.uBC)
    hook(:predict_bdim, a)
    BDIM!(a)
    probe(:predict_bdim, (u=a.u, f=a.f))
    BC!(a.u,a.uBC,a.exitBC,a.perdir,t₁) # BC MUST be at t₁
    probe(:predict_bc, (u=a.u,))
    a.exitBC && exitBC!(a.u,a.u⁰,a.Δt[end]) # convective exit
    probe(:predict_exitbc, (u=a.u,))
end

function diag5_mom_correct!(a::AbstractFlow, t, λ, probe, hook)
    hook(:correct_conv, a)
    conv_diff!(a.f,a.u,a.σ,λ;ν=a.ν,perdir=a.perdir)
    probe(:correct_conv_diff, (f=a.f,))
    accelerate!(a.f,t,a.g,a.uBC)
    hook(:correct_bdim, a)
    BDIM!(a)
    probe(:correct_bdim, (u=a.u, f=a.f))
    scale_u!(a,0.5)
    probe(:correct_scale, (u=a.u,))
    BC!(a.u,a.uBC,a.exitBC,a.perdir,t)
    probe(:correct_bc, (u=a.u,))
end

function diag5_mom_project!(a::AbstractFlow{D,T}, b::AbstractPoisson, w, t, probe, tag) where {D,T}
    dt = T(w)*a.Δt[end]
    @inside b.z[I] = div(I,a.u); b.x .*= dt # set source term & solution IC
    solver!(b)
    probe(Symbol(tag, :_solve), (x=b.x,))
    for i ∈ 1:ndims(a.p)  # apply solution and unscale to recover pressure
        @loop a.u[I,i] -= b.L[I,i]*∂(i,I,b.x) over I ∈ inside(b.x)
    end
    probe(Symbol(tag, :_gradient), (u=a.u,))
    b.x ./= dt
    BC!(a.u,a.uBC,a.exitBC,a.perdir,t)
    probe(Symbol(tag, :_bc), (u=a.u, p=a.p))
end

struct NullHook end
(::NullHook)(tag, a) = nothing
struct NullProbe5 end
(::NullProbe5)(stage, fields; kwargs...) = nothing
