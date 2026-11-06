# Execute the frozen Float32 plain build; remove only the trailing CLI main() in memory.
using WaterLily, SHA
const ROOT = "/Users/sota/projects/FomulaTMU/CFD2026_09-wp-03-grad00"
const PATH = joinpath(ROOT, "scripts/waterlily_grad_ta1_2026_10_15.jl")
const OUT = "/tmp/grad00-validation/ta1_plain_reference"
ispath(OUT) && error("plain reference output already exists")
mkdir(OUT)
module TA1PlainReference end
src = read(PATH, String)
endswith(src, "main()\n") || error("frozen TA1 trailing CLI call changed")
Base.include_string(TA1PlainReference, src[1:end-length("main()\n")], PATH)
const R = TA1PlainReference
const FD = WaterLily.ForwardDiff
const PHI_PATH = joinpath(ROOT, "docs/evidence/fd08_candidate_c_cpu_rehearsal_2026_10_05_retry1/inputs/cal_baseline_01.phi_f4_fortran.raw")
const PHI_SHA = "e3966d87c0ddb0d3ff9a6ee096c94221d0d4cccff77221ba84987ef5faa04431"
phi = R.load_raw(PHI_PATH, PHI_SHA)
case = only(c for c in R.w4_cases(R.ORIGIN,R.SPACING) if c.case_id == "flow_24")
sim,bodies,owner = R.build(phi,Float32,case,WaterLily.quick)
GC.@preserve phi sim bodies owner begin
    for _ in 1:R.PREFLIGHT_STEPS
        WaterLily.sim_step!(sim)
    end
    sha(a) = bytes2hex(sha256(reinterpret(UInt8,vec(a))))
    finite_u, finite_p = all(isfinite,sim.flow.u), all(isfinite,sim.flow.p)
    record = Dict("steps"=>R.PREFLIGHT_STEPS,"lambda_type"=>string(typeof(sim.flow.λ)),
        "real_type"=>string(eltype(sim.flow.u)),"primal_u_finite"=>finite_u,"primal_p_finite"=>finite_p,
        "primal_u_sha256"=>sha(Array(sim.flow.u)),"primal_p_sha256"=>sha(Array(sim.flow.p)),
        "source_sha256"=>bytes2hex(sha256(read(PATH))),"wrapper_sha256"=>bytes2hex(sha256(read(@__FILE__))),
        "project_sha256"=>bytes2hex(sha256(read(joinpath(ROOT,"julia/CFDSDFWaterLily/Project.toml")))),
        "manifest_sha256"=>bytes2hex(sha256(read(joinpath(ROOT,"julia/CFDSDFWaterLily/Manifest.toml")))),
        "input_phi_sha256"=>PHI_SHA,"input_phi_actual_array_sha256"=>sha(phi),
        "julia"=>string(VERSION),"waterlily"=>string(pkgversion(WaterLily)),"forwarddiff"=>string(pkgversion(FD)),
        "evidence_class"=>"cpu_frozen_ta1_plain_quick_capture","fields_finite"=>finite_u && finite_p)
    R.write_json(joinpath(OUT,"quick_plain_control.json"),record)
    finite_u && finite_p || error("frozen TA1 Float32 plain fields are not finite")
end
println("TA1_PLAIN_REFERENCE_CAPTURE_PASS ",OUT)
