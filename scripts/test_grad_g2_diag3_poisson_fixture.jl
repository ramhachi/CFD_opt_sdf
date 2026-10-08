# G2-DIAG3 CPU fixture checks of the tangent-only Poisson continuation (math, not a T4 measurement).
# usage: julia --project=julia/CFDSDFWaterLily scripts/test_grad_g2_diag3_poisson_fixture.jl <out.json>
using WaterLily, SHA
const SVector = WaterLily.SVector
const FD = WaterLily.ForwardDiff
to_device(a) = a
Base.include(WaterLily, joinpath(@__DIR__, "waterlily_grad_g2_diag3_stages.jl"))
include(joinpath(@__DIR__, "waterlily_grad_g2_diag3_fixture.jl"))

json(x::Nothing) = "null"
json(x::Bool) = x ? "true" : "false"
json(x::Integer) = string(x)
json(x::AbstractFloat) = isfinite(x) ? string(x) : "null"
json(x::AbstractString) = "\"" * x * "\""
json(x::AbstractVector) = "[" * join(json.(x), ",") * "]"
json(x::AbstractDict) = "{" * join([json(string(k)) * ":" * json(x[k]) for k in sort(collect(keys(x)); by=string)], ",") * "}"

const V = Float64
vals(A) = FD.value.(A)
tans(A) = [FD.partials(x, 1) for x in A]
maxabs(A) = maximum(abs, A)
relerr(a, b) = maxabs(a .- b) / max(maxabs(b), 1e-300)

function converged_reference(; tmean=0.0, vmean=0.0)
    sim, ml, DT = fixture_system(V)
    z, t = fixture_rhs(V, ml; vmean, tmean)
    fixture_load!(ml, z, t, DT)
    solver!(ml; tol=1e-26, itmx=400)
    return ml, DT, z, t
end

out = Dict{String,Any}()

# (1) limit equivalence: primal converged, tangent reset to 0, then tangent-only refinement == the converged Dual tangent
mlr, DT, z, t = converged_reference()
dx_star = tans(mlr.x); x_star = vals(mlr.x)
sim, ml, _ = fixture_system(V); fixture_load!(ml, z, t, DT)
ml.x .= DT.(x_star, FD.Partials.(tuple.(zeros(V, size(x_star)))))      # converged primal, tangent 0
h = make_refiner(ml, DT; tau=1e-12, maxit=400)
xb = vals(ml.x)
h.fixed = 0
# `TangentRefine` calls solver! first; with the primal converged that is a no-op up to round-off, so run the refinement body directly
p = ml.levels[1]
WaterLily.residual!(p)
zt = maximum(h.tmax, ml.z)
m0, _ = WaterLily.active_demeaned(h, p.r)
h.aux.levels[1].z .= (h.tan_of.(p.r) .- m0) .* h.mask; fill!(h.aux.levels[1].x, 0)
n_ref = WaterLily.aux_solve!(h.aux, 1e-12 * zt, 400, 0)
ml.x .= h.add_tan.(ml.x, h.aux.levels[1].x)
active = Array(ml.levels[1].iD) .!= 0
demean(a) = a .- sum(a[active]) / count(active)
out["limit_equivalence"] = Dict("cycles" => n_ref, "tangent_rel_error_vs_converged_dual_modulo_constant" => maxabs((demean(tans(ml.x)) .- demean(dx_star))[active]) / maxabs(demean(dx_star)[active]),
    "primal_bytes_unchanged" => vals(ml.x) == xb)

# (2) residual evaluator: partials of the Dual residual == central finite difference of the value-only residual
hfd = 1e-6
sim_p, mlp, _ = fixture_system(V; radius_shift=+hfd); sim_m, mlm, _ = fixture_system(V; radius_shift=-hfd)
sim0, ml0, _ = fixture_system(V)
zloc = vals(ml.levels[1].z); ztan = tans(ml.levels[1].z)
simt, mt, _ = fixture_system(V); fixture_load!(mt, z, t, DT); solver!(mt; tol=0.0, itmx=1)   # a truncated iterate: O(1) residual
xv = vals(mt.x); tv = tans(mt.x)
function resid_values(m, zv, xv)
    q = m.levels[1]
    q.z .= DT.(zv, FD.Partials.(tuple.(zeros(V, size(zv)))))
    q.x .= DT.(xv, FD.Partials.(tuple.(zeros(V, size(xv)))))
    WaterLily.residual!(q)
    return vals(q.r)
end
rp = resid_values(mlp, zloc .+ hfd .* ztan, xv .+ hfd .* tv)
rm = resid_values(mlm, zloc .- hfd .* ztan, xv .- hfd .* tv)
fd_dr = (rp .- rm) ./ (2hfd)
q0 = ml0.levels[1]; q0.z .= DT.(zloc, FD.Partials.(tuple.(ztan))); q0.x .= DT.(xv, FD.Partials.(tuple.(tv)))
WaterLily.residual!(q0)
# the same residual with the tangent of L stripped (dA = 0): the difference is the dA x term, which the finite difference must (and does) contain
simn, mn, _ = fixture_system(V)
qn = mn.levels[1]
qn.L .= DT.(vals(qn.L), FD.Partials.(tuple.(zeros(V, size(qn.L)))))
WaterLily.update!(mn)
qn.z .= DT.(zloc, FD.Partials.(tuple.(ztan))); qn.x .= DT.(xv, FD.Partials.(tuple.(tv)))
WaterLily.residual!(qn)
out["residual_evaluator"] = Dict("tangent_residual_rel_diff_vs_finite_difference" => relerr(tans(q0.r), fd_dr), "max_tangent_residual" => maxabs(tans(q0.r)),
    "max_primal_residual" => maxabs(vals(q0.r)), "dA_x_term_relative_to_tangent_residual" => maxabs(tans(q0.r) .- tans(qn.r)) / maxabs(tans(q0.r)),
    "finite_difference_would_miss_dA_x_by" => relerr(tans(qn.r), fd_dr))

# (3) k tangent-only cycles == k Dual cycles when the primal is converged (omega = 1 in both; the V-cycle/smoother operators agree)
function dual_cycles(k)
    sim, m, _ = fixture_system(V); fixture_load!(m, z, t, DT)
    m.x .= DT.(x_star, FD.Partials.(tuple.(zeros(V, size(x_star)))))
    q = m.levels[1]; WaterLily.residual!(q)
    for _ in 1:k
        WaterLily.Vcycle!(m; ω=V(1)); WaterLily.smooth!(q; ω=V(1))
    end
    return m
end
function aux_cycles(k)
    sim, m, _ = fixture_system(V); fixture_load!(m, z, t, DT)
    m.x .= DT.(x_star, FD.Partials.(tuple.(zeros(V, size(x_star)))))
    hh = make_refiner(m, DT)
    q = m.levels[1]; WaterLily.residual!(q)
    m0, _ = WaterLily.active_demeaned(hh, q.r)
    hh.aux.levels[1].z .= (hh.tan_of.(q.r) .- m0) .* hh.mask; fill!(hh.aux.levels[1].x, 0)
    n = WaterLily.aux_solve!(hh.aux, 0.0, 0, k)
    return n, hh.aux.levels[1].x
end
cyc = Dict{String,Any}()
for k in (1, 2, 3, 5)
    md = dual_cycles(k); n, e = aux_cycles(k)
    cyc[string(k)] = Dict("cycles_run" => n, "tangent_rel_diff_dual_vs_tangent_only" => relerr(tans(md.x), e), "primal_change_in_dual" => maxabs(vals(md.x) .- x_star))
end
out["k_cycles_equal"] = cyc

# (4) the REAL hook on a loosely solved primal (small right-hand side: the primal stop test passes after one cycle, as in the production flow)
trunc = Dict{String,Any}()
z1, t1 = fixture_rhs(V, ml; scale=1e-5)
for (name, kw) in (("tau1e-3", (fixed=0, tau=1e-3, maxit=64)), ("tau1e-6", (fixed=0, tau=1e-6, maxit=64)), ("tau1e-12_cap5", (fixed=0, tau=1e-12, maxit=5)), ("fixed7", (fixed=7, tau=1e-6, maxit=64)))
    _, m, _ = fixture_system(V); fixture_load!(m, z1, t1, DT)
    _, mp, _ = fixture_system(V); fixture_load!(mp, z1, t1, DT); solver!(mp)          # the plain primal-only solve (what the hook must leave untouched)
    hh = make_refiner(m, DT; kw...)
    hh(m)
    st = hh.stats[1]
    ghost_same = all(tans(m.x)[1, :, :] .== tans(mp.x)[1, :, :]) && all(tans(m.x)[:, :, end] .== tans(mp.x)[:, :, end])
    trunc[name] = Dict("cycles" => st[1], "rel_before" => st[2], "rel_after_demeaned" => st[6], "primal_bytes_unchanged" => vals(m.x) == vals(mp.x), "ghost_tangent_unchanged" => ghost_same,
        "primal_cycles" => Int(m.n[end]), "aux_operator_matches" => aux_operator_matches(m, hh))
end
out["truncated_case"] = trunc

# (4b) the Dual-stop hook uses the same active-demeaned tangent stop
_, md, _ = fixture_system(V); fixture_load!(md, z1, t1, DT)
ds = make_dual_stop(md, DT; tau=1e-6, maxit=64); ds(md)
out["dual_stop"] = Dict("cycles" => ds.stats[1][1], "rel_after_demeaned" => ds.stats[1][6], "primal_cycles" => Int(md.n[end]))

# (5) the hook itself end to end (primal solve + refinement) and the primal-bytes guarantee
sim, m, _ = fixture_system(V); fixture_load!(m, z, t, DT)
hh = make_refiner(m, DT; tau=1e-6, maxit=64)
sim2, m2, _ = fixture_system(V); fixture_load!(m2, z, t, DT)
solver!(m2)
hh(m)
out["hook"] = Dict("primal_equals_plain_solver" => vals(m.x) == vals(m2.x), "cycles" => hh.stats[1][1], "rel_before" => hh.stats[1][2], "rel_after" => hh.stats[1][3],
    "iterations_of_primal_solve" => Int(m.n[end]))

# (6) gauge: tangent RHS with a nonzero mean while the primal mean is ~0 -> Dual `residual!` skips the mean correction (|s| <= 2eps), the aux system removes it
function gauge_case()
    sim, mg, _ = fixture_system(V)
    zg, tg = fixture_rhs(V, mg; vmean=0.0, tmean=0.5)
    fixture_load!(mg, zg, tg, DT)
    q = mg.levels[1]
    WaterLily.residual!(q)
    tmean_before = sum(tans(q.r)) / length(inside(q.r))
    smean = abs(sum(vals(q.r)) / length(inside(q.r)))
    for _ in 1:30
        WaterLily.Vcycle!(mg; ω=V(1)); WaterLily.smooth!(q; ω=V(1))
    end
    WaterLily.residual!(q)
    tmean_after = sum(tans(q.r)) / length(inside(q.r))
    simg2, mg2, _ = fixture_system(V); fixture_load!(mg2, zg, tg, DT)
    hg = make_refiner(mg2, DT; tau=1e-8, maxit=200)
    hg(mg2)
    st = hg.stats[1]
    return Dict("primal_mean_abs" => smean, "2eps" => 2eps(V), "tangent_mean_of_residual_before" => tmean_before, "tangent_mean_of_residual_after_30_dual_cycles" => tmean_after,
        "refine_cycles" => st[1], "refine_rel_after_raw" => st[3], "refine_rel_after_active_demeaned" => st[6], "refine_active_mean_removed" => st[4])
end
out["gauge"] = gauge_case()

open(ARGS[1], "w") do io
    write(io, json(out), "\n")
end
println("FIXTURE_DONE ", ARGS[1])
