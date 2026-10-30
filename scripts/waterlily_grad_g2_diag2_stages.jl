# G2-DIAG2: counterfactual variants of the DIAG1 stage copies.  `Base.include`d into WaterLily after
# scripts/waterlily_grad_g2_diag1_stages.jl, whose `diag_mom_predict!` / `diag_mom_correct!` are reused unchanged.
# `diag2_mom_step!` and `diag2_mom_project!` equal `diag_mom_step!` / `diag_mom_project!` except that the Poisson solve goes through
# `solver_step!(b, poisson)`: `poisson === nothing` is exactly `solver!(b)` (WaterLily defaults, the baseline V0); a NamedTuple
# `(tol, itmx)` is a counterfactual (forced iteration count) used by the V1 variants only.
solver_step!(b, ::Nothing) = solver!(b)
solver_step!(b, poisson) = solver!(b; tol=poisson.tol, itmx=poisson.itmx)

@fastmath function diag2_mom_step!(a::AbstractFlow, b::AbstractPoisson, probe, poisson)
    a.u⁰ .= a.u; scale_u!(a,0); t₁ = sum(a.Δt); t₀ = t₁-a.Δt[end]
    probe(:pre_scale, (u0=a.u⁰,))
    diag_mom_predict!(a,t₀,t₁,probe)
    diag2_mom_project!(a,b,1,t₁,probe,:project1,poisson)
    diag_mom_correct!(a,t₁,probe)
    diag2_mom_project!(a,b,0.5,t₁,probe,:project2,poisson)
    push!(a.Δt,CFL(a))
    probe(:cfl, (sigma=a.σ,))
    probe(:cfl_dt, (dt=a.Δt[end],))
end

function diag2_mom_project!(a::AbstractFlow{D,T}, b::AbstractPoisson, w, t, probe, tag, poisson) where {D,T}
    dt = T(w)*a.Δt[end]
    @inside b.z[I] = div(I,a.u); b.x .*= dt # set source term & solution IC
    probe(Symbol(tag, :_rhs), (z=b.z, x=b.x))
    solver_step!(b, poisson)
    probe(Symbol(tag, :_solve), (x=b.x, r=b.levels[1].r); iters=Int(b.n[end]), r2=L₂(b.levels[1]))
    for i ∈ 1:ndims(a.p)  # apply solution and unscale to recover pressure
        @loop a.u[I,i] -= b.L[I,i]*∂(i,I,b.x) over I ∈ inside(b.x)
    end
    probe(Symbol(tag, :_gradient), (u=a.u,))
    b.x ./= dt
    BC!(a.u,a.uBC,a.exitBC,a.perdir,t)
    probe(Symbol(tag, :_bc), (u=a.u, p=a.p))
end
