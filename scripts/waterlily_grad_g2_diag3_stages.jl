# G2-DIAG3: tangent-only Poisson continuation and a tangent-aware stopping rule.  `Base.include`d into WaterLily after
# scripts/waterlily_grad_g2_diag1_stages.jl (whose `diag_mom_predict!` / `diag_mom_correct!` are reused unchanged).
#
# `diag3_mom_step!` / `diag3_mom_project!` equal WaterLily 1.8.0's `mom_step!` / `mom_project!` (and the DIAG1/DIAG2 copies) except that the
# Poisson solve goes through `solve_step!(b, hook)`.  `hook === nothing` is exactly `solver!(b)` (the baseline).
#
# Mathematics.  The pressure system is  A(L) x = z  (Neumann, `L` = mu0, `A` the face-weighted Laplacian).  Under ForwardDiff the stored
# residual is  r = z - A x  with partials  dr = dz - dA x - A dx  (dA = A'(L) dL is NOT zero inside the body band, mu0 carries a tangent).
# The primal stop test (r2 < tol) looks at values only, so the tangent part is left wherever the same iteration count puts it.
#   * TangentRefine  keeps the primal solve unchanged (`solver!(b)`), then solves  A e = dr  with a plain (value-only) Float32 multigrid
#     on the same operator (aux system: L = values of mu0), and adds e to the TANGENT of x only (values are never written):
#     dx <- dx + e,  i.e.  A dx = dz - dA x  with x the primal iterate (iterative refinement of the tangent system).
#   * DualStop       continues the ordinary Dual iteration until the primal AND the tangent residual are small (changes the primal).
#   * ForcedSolve    forces the Dual iteration count (the DIAG2 V1 arms).
solve_step!(b, ::Nothing) = solver!(b)
solve_step!(b, hook) = hook(b)

@fastmath function diag3_mom_step!(a::AbstractFlow, b::AbstractPoisson, probe, hook)
    a.u⁰ .= a.u; scale_u!(a,0); t₁ = sum(a.Δt); t₀ = t₁-a.Δt[end]
    probe(:pre_scale, (u0=a.u⁰,))
    diag_mom_predict!(a,t₀,t₁,probe)
    diag3_mom_project!(a,b,1,t₁,probe,:project1,hook)
    diag_mom_correct!(a,t₁,probe)
    diag3_mom_project!(a,b,0.5,t₁,probe,:project2,hook)
    push!(a.Δt,CFL(a))
    probe(:cfl, (sigma=a.σ,))
    probe(:cfl_dt, (dt=a.Δt[end],))
end

function diag3_mom_project!(a::AbstractFlow{D,T}, b::AbstractPoisson, w, t, probe, tag, hook) where {D,T}
    dt = T(w)*a.Δt[end]
    @inside b.z[I] = div(I,a.u); b.x .*= dt # set source term & solution IC
    probe(Symbol(tag, :_rhs), (z=b.z, x=b.x))
    solve_step!(b, hook)
    probe(Symbol(tag, :_solve), (x=b.x, r=b.levels[1].r); iters=Int(b.n[end]), r2=L₂(b.levels[1]))
    for i ∈ 1:ndims(a.p)  # apply solution and unscale to recover pressure
        @loop a.u[I,i] -= b.L[I,i]*∂(i,I,b.x) over I ∈ inside(b.x)
    end
    probe(Symbol(tag, :_gradient), (u=a.u,))
    b.x ./= dt
    BC!(a.u,a.uBC,a.exitBC,a.perdir,t)
    probe(Symbol(tag, :_bc), (u=a.u, p=a.p))
end

# ---- the value-only (aux) multigrid solve, same V-cycle / smoother / relaxation logic as `solver!` -------------------------------
# `target` is an absolute max-norm bound on the residual (threshold mode, `fixed == 0`); `fixed > 0` runs exactly that many cycles.
function aux_solve!(ml::MultiLevelPoisson{T}, target, maxit, fixed) where T
    p = ml.levels[1]
    residual!(p); r₂ = L₂(p); ω = T(1)
    n = 0
    while n < (fixed > 0 ? fixed : maxit)
        fixed == 0 && L∞(p) <= target && break
        Vcycle!(ml; ω); smooth!(p; ω)
        rnew = L₂(p); n += 1
        if     rnew ≥ r₂
            ω = max(0.2, 0.9ω) |> T
        elseif rnew < r₂
            ω = min(1.0, 1.02ω) |> T
        end
        r₂ = rnew
    end
    perBC!(p.x, p.perdir)
    return n
end

# hooks record one tuple per call:
#   (cycles, max|dr|/max|dz| before, after, active-set mean of dr before, max|dz|, active-demeaned max|dr|/max|dz| after, ... before)
# The pressure system is singular (Neumann).  WaterLily removes the mean of r over ALL inside cells, but only when the PRIMAL mean exceeds 2 eps
# (`residual!` returns early otherwise, for Dual numbers too), so the tangent mean of r may stay in the residual and the tangent RHS can be
# incompatible on the active set (iD != 0).  TangentRefine projects the tangent RHS onto the compatible subspace (active-set mean removed,
# masked cells zeroed) before the value-only solve and reports the removed mean.
mutable struct TangentRefine{M,F,G,H,K}
    aux::M          # value-only MultiLevelPoisson on the primal operator
    tan_of::F       # Dual -> its partial (value type)
    add_tan::G      # (Dual, e) -> Dual with the same value and partial + e
    tmax::H         # Dual -> |partial|
    mask::K         # 1 on the active cells (iD != 0), 0 elsewhere (value type)
    nact::Float64
    fixed::Int      # > 0: exactly this many aux cycles
    tau::Float64    # threshold mode: stop when max|dr| <= tau * max|dz| (active-demeaned)
    maxit::Int
    stats::Vector{NTuple{7,Float64}}
end

function active_demeaned(h, r)   # (active mean, max |dr - mean| over the active cells); `h` carries tan_of, mask, nact
    tr = h.tan_of.(r)
    m = sum(tr .* h.mask) / h.nact
    return m, maximum(abs.((tr .- m) .* h.mask))
end

function (h::TangentRefine)(b)
    solver!(b)                                         # the original primal solve: values are final from here on
    p = b.levels[1]
    zt = maximum(h.tmax, b.z)
    residual!(p)                                       # Dual residual of the current iterate; partials = dz - dA x - A dx
    rt0 = maximum(h.tmax, p.r)
    m0, rt0c = active_demeaned(h, p.r)
    n = 0
    if zt > 0 && rt0c > 0
        aux = h.aux.levels[1]
        aux.z .= (h.tan_of.(p.r) .- m0) .* h.mask
        fill!(aux.x, 0)
        n = aux_solve!(h.aux, h.tau * zt, h.maxit, h.fixed)
        b.x .= h.add_tan.(b.x, aux.x)                  # tangent part only; the primal bytes of x are not touched
    end
    residual!(p)
    rt1 = maximum(h.tmax, p.r)
    _, rt1c = active_demeaned(h, p.r)
    push!(h.stats, (n, zt > 0 ? rt0 / zt : 0.0, zt > 0 ? rt1 / zt : 0.0, m0, zt, zt > 0 ? rt1c / zt : 0.0, zt > 0 ? rt0c / zt : 0.0))
    return nothing
end

mutable struct DualStop{F,G,K}
    tau::Float64
    maxit::Int
    tmax::F
    tan_of::G
    mask::K
    nact::Float64
    stats::Vector{NTuple{7,Float64}}
end

function (h::DualStop)(b::MultiLevelPoisson{T}; tol=1e-4) where T   # `solver!` with an extra tangent stop test
    p = b.levels[1]
    zt = maximum(h.tmax, b.z)
    residual!(p); r₂ = L₂(p); ω = T(1)
    n = 0
    while n < h.maxit
        Vcycle!(b; ω); smooth!(p; ω)
        rnew = L₂(p); n += 1
        if     rnew ≥ r₂
            ω = max(0.2, 0.9ω) |> T
        elseif rnew < r₂
            ω = min(1.0, 1.02ω) |> T
        end
        r₂ = rnew
        r₂ < tol && active_demeaned(h, p.r)[2] <= h.tau * zt && break    # the same active-demeaned tangent residual as TangentRefine
    end
    perBC!(p.x, p.perdir)
    push!(b.n, n)
    push!(h.stats, (n, 0.0, zt > 0 ? maximum(h.tmax, p.r) / zt : 0.0, 0.0, zt, zt > 0 ? active_demeaned(h, p.r)[2] / zt : 0.0, 0.0))
    return nothing
end

mutable struct ForcedSolve
    itmx::Int
    stats::Vector{NTuple{7,Float64}}
end
function (h::ForcedSolve)(b)
    solver!(b; tol=0.0, itmx=h.itmx)
    push!(h.stats, (Float64(b.n[end]), 0.0, 0.0, 0.0, 0.0, 0.0, 0.0))
    return nothing
end
