# G2-DIAG1: observation-only stage copies of WaterLily 1.8.0 `mom_step!`/`mom_predict!`/`mom_correct!`/`mom_project!`.
#
# `Base.include`d into the WaterLily module by scripts/waterlily_grad_g2_diag1_d0_nonfinite_2026_10_08.jl so the macros
# (@loop/@inside) and internal helpers resolve exactly as in Flow.jl.  The statement order is that of Flow.jl (lines 156-167,
# 190-209, 223-232); the only additions are `probe(...)` calls that read arrays, and the only omissions are `@log` (a no-op
# unless a pressure-solver logger is installed) and `udf!(..., nothing, ...)` (a no-op method).  Nothing is clipped, reset,
# rescaled or replaced.  `diag_mom_step!` is @fastmath like `mom_step!` (it contains only the same time arithmetic).
@fastmath function diag_mom_step!(a::AbstractFlow, b::AbstractPoisson, probe)
    a.u⁰ .= a.u; scale_u!(a,0); t₁ = sum(a.Δt); t₀ = t₁-a.Δt[end]
    probe(:pre_scale, (u0=a.u⁰,))
    diag_mom_predict!(a,t₀,t₁,probe)
    diag_mom_project!(a,b,1,t₁,probe,:project1)
    diag_mom_correct!(a,t₁,probe)
    diag_mom_project!(a,b,0.5,t₁,probe,:project2)
    push!(a.Δt,CFL(a))
    probe(:cfl, (sigma=a.σ,))
    probe(:cfl_dt, (dt=a.Δt[end],))
end

function diag_mom_predict!(a::AbstractFlow, t₀, t₁, probe)
    conv_diff!(a.f,a.u⁰,a.σ,a.λ;ν=a.ν,perdir=a.perdir)
    probe(:predict_conv_diff, (f=a.f, sigma=a.σ))
    accelerate!(a.f,t₀,a.g,a.uBC)
    probe(:predict_accelerate, (f=a.f,))
    BDIM!(a)
    probe(:predict_bdim, (u=a.u, f=a.f))
    BC!(a.u,a.uBC,a.exitBC,a.perdir,t₁) # BC MUST be at t₁
    probe(:predict_bc, (u=a.u,))
    a.exitBC && exitBC!(a.u,a.u⁰,a.Δt[end]) # convective exit
    probe(:predict_exitbc, (u=a.u,))
end

function diag_mom_correct!(a::AbstractFlow, t, probe)
    conv_diff!(a.f,a.u,a.σ,a.λ;ν=a.ν,perdir=a.perdir)
    probe(:correct_conv_diff, (f=a.f, sigma=a.σ))
    accelerate!(a.f,t,a.g,a.uBC)
    probe(:correct_accelerate, (f=a.f,))
    BDIM!(a)
    probe(:correct_bdim, (u=a.u, f=a.f))
    scale_u!(a,0.5)
    probe(:correct_scale, (u=a.u,))
    BC!(a.u,a.uBC,a.exitBC,a.perdir,t)
    probe(:correct_bc, (u=a.u,))
end

function diag_mom_project!(a::AbstractFlow{D,T}, b::AbstractPoisson, w, t, probe, tag) where {D,T}
    dt = T(w)*a.Δt[end]
    @inside b.z[I] = div(I,a.u); b.x .*= dt # set source term & solution IC
    probe(Symbol(tag, :_rhs), (z=b.z, x=b.x))
    solver!(b)
    probe(Symbol(tag, :_solve), (x=b.x, r=b.levels[1].r); iters=Int(b.n[end]), r2=L₂(b.levels[1]))
    for i ∈ 1:ndims(a.p)  # apply solution and unscale to recover pressure
        @loop a.u[I,i] -= b.L[I,i]*∂(i,I,b.x) over I ∈ inside(b.x)
    end
    probe(Symbol(tag, :_gradient), (u=a.u,))
    b.x ./= dt
    BC!(a.u,a.uBC,a.exitBC,a.perdir,t)
    probe(Symbol(tag, :_bc), (u=a.u, p=a.p))
end
