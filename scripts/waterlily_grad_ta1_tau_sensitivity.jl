# GRAD-TA1 C4: disclosed, NON-GATING CPU sensitivity of the one-step tie-averaged JVP to tau, on the stored DIAG5 states S900 and S1000.
# Reuses the DIAG5 harness unchanged: its source (scripts/waterlily_grad_g2_diag5_one_step_gain_2026_10_09.jl, frozen by the DIAG5 freeze) is read and evaluated
# with only its trailing `main()` call removed; the group-E3 comparison (one-step JVP vs the central finite difference of the same map, eps scan) is repeated with
# lambda = QuickTie(tau) from scripts/quick_tie.jl (the code the TA1 run uses; its methods supersede the DIAG5 copy for Dual width 1) for tau in TAUS.
# Reproduction gate: the tau = 1f-5 rows must equal the recorded DIAG5 E3 `tie1e-5` rows (run_output/<state>_E3/e3_rows.csv).
# usage: julia -t 1 --project=julia/CFDSDFWaterLily scripts/waterlily_grad_ta1_tau_sensitivity.jl <snapdir> <state: S900|S1000> <out.json>
const DIAG5 = joinpath(@__DIR__, "waterlily_grad_g2_diag5_one_step_gain_2026_10_09.jl")
const SRC = read(DIAG5, String)
endswith(SRC, "\nmain()\n") || error("the DIAG5 job no longer ends with a bare main() call")
include_string(Main, SRC[1:end-length("main()\n")], DIAG5)          # defines Ctx, load_state, direction, perturbed, effective, fd_sim, dual_sim, set_dual!, step_dual!, relerr, ...
Base.include(WaterLily, joinpath(@__DIR__, "quick_tie.jl"))

const TAUS = (3f-6, 1f-5, 3f-5)
const EVIDENCE = joinpath(ROOT, "docs/evidence/grad03_g2_diag1_d0_nonfinite_2026_10_08/kernel_output")
const PHI = joinpath(ROOT, "docs/evidence/fd08_candidate_c_cpu_rehearsal_2026_10_05_retry1/inputs/cal_baseline_01.phi_f4_fortran.raw")
const PHI_SHA = "e3966d87c0ddb0d3ff9a6ee096c94221d0d4cccff77221ba84987ef5faa04431"
const D0 = joinpath(ROOT, "docs/evidence/grad03_gpu_dual_spike_2026_10_08/inputs/D0_interface_offset.dir_f4_fortran.raw")
const D0_SHA = "d0af58bdc2bff55226ff911204ef42d05a6da4a4b52ec4c4521a09141fbf2549"

function main_tau()
    length(ARGS) == 3 || error("usage: <snapdir> <state> <out.json>")
    snapdir, state, out = ARGS
    state in ("S900", "S1000") || error("state must be S900 or S1000")
    isfile(out) && error("refusing to overwrite $out")
    phi32 = load_raw(PHI, PHI_SHA); d32 = load_raw(D0, D0_SHA)
    case = only(c for c in w4_cases(ORIGIN, SPACING) if c.case_id == "flow_24")
    ctx = Ctx(phi32, d32, case)
    prefix, step = STATES[state]
    s = load_state(snapdir, joinpath(EVIDENCE, "snapshot_index.json"), joinpath(EVIDENCE, "instrumented_checksums.csv"), prefix, step)
    tu, tp, m = direction(s)
    lams = [("quick", WaterLily.quick), [("tie_tau=$(τ)", WaterLily.QuickTie(τ)) for τ in TAUS]...]
    rows = Any[]
    primal_equal = true
    for eps in EPS_E3
        plus, minus = perturbed(s, tu, tp, eps)
        te_u, te_p = effective(plus, minus, eps)
        outs = [begin
                    sim = fd_sim(ctx, uv, pv); step_plain!(sim); Float64.(uval(sim))
                end for (uv, pv) in (plus, minus)]
        Du = Float32.((outs[1] .- outs[2]) ./ (2eps))
        bits = nothing
        for (lname, λ) in lams
            sim = dual_sim(ctx); set_dual!(sim, s.uv, te_u, s.pv, te_p)
            step_dual!(sim; λ=λ)
            b = value_checksum(value_of(sim.flow.u)); bits === nothing && (bits = b); primal_equal &= (b == bits)
            tu_out = tangent_of(sim.flow.u)
            for (rname, region) in (("box", BOX4), ("interior", INT4))
                r = relerr(tu_out, Du, region)
                gj = maximum(abs, view(tu_out, BOX4...)) / maximum(abs, view(te_u, BOX4...)); gf = maximum(abs, view(Du, BOX4...)) / maximum(abs, view(te_u, BOX4...))
                push!(rows, Dict("eps" => eps, "lambda" => lname, "region" => rname, "rel" => r.rel, "cos" => r.cos, "ratio" => r.ratio, "gain_jvp_box_max" => Float64(gj), "gain_fd_box_max" => Float64(gf)))
            end
        end
        println("eps ", eps, " done"); flush(stdout)
    end
    res = Dict{String,Any}("kind" => "grad_ta1_tau_sensitivity_one_step_cpu", "state" => state, "taus" => collect(Float64.(TAUS)), "eps" => collect(EPS_E3), "rows" => rows,
        "primal_bits_equal_across_lambda" => primal_equal, "julia" => string(VERSION), "waterlily" => string(pkgversion(WaterLily)), "forwarddiff" => string(pkgversion(FD)),
        "diag5_job_sha256" => bytes2hex(sha256(read(DIAG5))), "quick_tie_sha256" => bytes2hex(sha256(read(joinpath(@__DIR__, "quick_tie.jl")))),
        "non_gating" => true, "meaning" => "disclosed sensitivity of the one-step JVP vs central FD to tau; far-field corner-box states of D0 only; not force-level, not used for the verdict")
    write_json(out, res)
end
main_tau()
