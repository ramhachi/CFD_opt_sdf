# Read frozen TA1 bytes; suppress only its trailing CLI call in memory, as prior TA1 tau-sensitivity tooling does.
using WaterLily, SHA
const ROOT = "/Users/sota/projects/FomulaTMU/CFD2026_09-wp-03-grad00"
const PATH = joinpath(ROOT, "scripts/waterlily_grad_ta1_2026_10_15.jl")
const OUT = "/Users/sota/projects/FomulaTMU/CFD2026_09-wp-03-grad00/docs/codex/gen01_w1_2026_11_06/reports/wp03_validation/amendment3/ta1_reference"
mkpath(OUT)
module TA1Reference end
src = read(PATH, String)
endswith(src, "main()\n") || error("frozen TA1 trailing CLI call changed")
Base.include_string(TA1Reference, src[1:end-length("main()\n")], PATH)
const R = TA1Reference
const FD = WaterLily.ForwardDiff
phi = R.load_raw(joinpath(ROOT, "docs/evidence/fd08_candidate_c_cpu_rehearsal_2026_10_05_retry1/inputs/cal_baseline_01.phi_f4_fortran.raw"), "e3966d87c0ddb0d3ff9a6ee096c94221d0d4cccff77221ba84987ef5faa04431")
d = R.load_raw(joinpath(ROOT, "docs/evidence/grad03_gpu_dual_spike_2026_10_08/inputs/D0_interface_offset.dir_f4_fortran.raw"), "d0af58bdc2bff55226ff911204ef42d05a6da4a4b52ec4c4521a09141fbf2549")
case = only(c for c in R.w4_cases(R.ORIGIN,R.SPACING) if c.case_id == "flow_24")
tag = FD.Tag(R.run_one, Float32)
DT = FD.Dual{typeof(tag),Float32,1}
phi_dual = DT.(phi, FD.Partials.(tuple.(d)))
sim,bodies,owner = R.build(phi_dual,DT,case,WaterLily.quick)
GC.@preserve phi_dual sim bodies owner begin
    for _ in 1:R.PREFLIGHT_STEPS
        WaterLily.sim_step!(sim)
    end
    all(isfinite,FD.value.(sim.flow.u)) && all(isfinite,FD.value.(sim.flow.p)) &&
        all(isfinite,FD.partials.(sim.flow.u,1)) && all(isfinite,FD.partials.(sim.flow.p,1)) || error("TA1 control not finite incl partials")
    sha(a) = bytes2hex(sha256(reinterpret(UInt8,vec(a))))
    record = Dict("steps"=>R.PREFLIGHT_STEPS,"lambda_type"=>string(typeof(sim.flow.λ)),"fields_finite_incl_partials"=>true,"primal_u_sha256"=>sha(FD.value.(Array(sim.flow.u))),"primal_p_sha256"=>sha(FD.value.(Array(sim.flow.p))),
        "source_sha256"=>bytes2hex(sha256(read(PATH))),"wrapper_sha256"=>bytes2hex(sha256(read(@__FILE__))),
        "project_sha256"=>bytes2hex(sha256(read(joinpath(ROOT,"julia/CFDSDFWaterLily/Project.toml")))),
        "manifest_sha256"=>bytes2hex(sha256(read(joinpath(ROOT,"julia/CFDSDFWaterLily/Manifest.toml")))),
        "julia"=>string(VERSION),"waterlily"=>string(pkgversion(WaterLily)),"forwarddiff"=>string(pkgversion(FD)),"evidence_class"=>"cpu_frozen_ta1_quick_control_capture")
    R.write_json(joinpath(OUT,"quick_control.json"),record)
end
println("TA1_REFERENCE_CAPTURE_PASS ",OUT)
