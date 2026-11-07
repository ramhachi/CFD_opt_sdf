# SYNTHETIC producer-contract test: no WaterLily simulation is constructed or stepped.
# Replaces only preflight/run_one inside a test module; main/save_run!/indices are the actual job.
# julia --project=julia/CFDSDFWaterLily --threads=1 scripts/grad00_orchestration_selftest.jl [OUTPUT_DIR]
using SHA
using Test

const TEST_ROOT = normpath(joinpath(@__DIR__, ".."))
const TEST_OUTPUT = isempty(ARGS) ? joinpath(mktempdir(; prefix="grad00_synthetic_"), "out") : abspath(only(ARGS))
ispath(TEST_OUTPUT) && error("refusing to overwrite synthetic output: $TEST_OUTPUT")
ENV["G2_BACKEND"] = "cpu"
ENV["GRAD00_ARM"] = get(ENV, "GRAD00_ARM", "quick_nobound")
ENV["GRAD00_T"] = get(ENV, "GRAD00_T", "Float32")
ENV["G2_DRYRUN_T_END"] = "1.0"
ENV["TA1_PREFLIGHT_ONLY"] = "0"
pop!(ENV, "TA1_BLOCK_LIMIT", nothing)

module SyntheticProducer
const ARGS = String[]
include(joinpath(@__DIR__, "waterlily_grad00_lambda_2026_11.jl"))

function preflight(phi32, d32, case, DT, outdir)
    # Synthetic pass exercises orchestration only; it is explicitly not a real preflight.
    return Dict{String,Any}("pass" => true, "steps" => 20, "synthetic_no_flow" => true,
        "evidence_class" => "SYNTHETIC_TEST_FIXTURE", "arm" => ARM)
end

function run_one(label, phi_host::AbstractArray, ::Type{T}, case, λ, outdir; wall_limit=Inf) where {T}
    λ === LAMBDA || error("orchestrator passed another convection scheme")
    case.case_id == "flow_24" || error("orchestrator selected another flow case")
    dual = T <: FD.Dual
    dual && !(isfinite(wall_limit) && wall_limit > 0) && error("Dual wall limit was not inherited from plain")
    rows = Vector{Vector{Float64}}()
    for (step, t) in zip((8, 16, 24, 32), (0.25, 0.5, 0.75, 1.0))
        cells = Float64[step, t, 0]
        for series in SERIES
            value = series in ("fx", "pfx") ? 10.0 : series in ("fz", "pfz") ? -20.0 : 0.0
            tangent = dual ? value / 10 : 0.0
            append!(cells, (value, tangent))
        end
        push!(rows, cells)
    end
    open(joinpath(outdir, "$label.history.csv"), "w") do io
        csv_line(io, history_header())
        for row in rows
            csv_line(io, row)
        end
    end
    summary = Dict{String,Any}("label" => label, "real_type" => string(T), "lambda_type" => string(typeof(λ)),
        "status" => "COMPLETE", "steps" => 32, "total_seconds" => 0.001, "loop_seconds" => 0.0,
        "peak_vram_bytes" => 0, "fields_finite_incl_partials" => true,
        "synthetic_no_flow" => true, "evidence_class" => "SYNTHETIC_TEST_FIXTURE")
    merge!(summary, summarize(rows))  # Actual endpoint-clipped producer summary helper.
    if dual
        open(io -> csv_line(io, WATCH_HEADER), joinpath(outdir, "$label.watchdog.csv"), "w")
        summary["watchdog_max_abs_tangent_u_finite"] = 1.0
        summary["watchdog_max_abs_tangent_p_finite"] = 0.5
        summary["terminal_tangent"] = Dict("tan_max_u" => 1.0, "tan_max_p" => 0.5,
                                            "tan_argmax_u" => "synthetic", "tan_argmax_p" => "synthetic")
        summary["watchdog_onset"] = nothing
    end
    return rows, summary, nothing
end
end

# Canonical raw pins from the frozen TA1 registration; epsilon below is synthetic.
const PHI_RAW = joinpath(TEST_ROOT, "docs/evidence/fd08_candidate_c_cpu_rehearsal_2026_10_05_retry1/inputs/cal_baseline_01.phi_f4_fortran.raw")
const PHI_SHA = "e3966d87c0ddb0d3ff9a6ee096c94221d0d4cccff77221ba84987ef5faa04431"
const DIRECTION_SHAS = (
    "d0af58bdc2bff55226ff911204ef42d05a6da4a4b52ec4c4521a09141fbf2549",
    "96fe6e62c5fcb7ad0108dd64d6fac68cc488ee49deb188be742530f828037a87",
    "2a22eb09407a14755f495fa07d4df8dee2d4632db41a0b75d1bf744fd3d1d5de",
    "24cc06aeb18e2a5729e560636f13ce78f8f19746268699783e8498921aec5dcc",
)
append!(SyntheticProducer.ARGS, (PHI_RAW, PHI_SHA, TEST_OUTPUT))
for (name, digest) in zip(SyntheticProducer.DIRECTIONS, DIRECTION_SHAS)
    path = joinpath(TEST_ROOT, "docs/evidence/grad03_gpu_dual_spike_2026_10_08/inputs", "$name.dir_f4_fortran.raw")
    append!(SyntheticProducer.ARGS, (path, digest))
end
append!(SyntheticProducer.ARGS, fill("0.001", 4))

@testset "report-only preflight tangent localization" begin
    P = SyntheticProducer
    case = only(c for c in P.w4_cases(P.ORIGIN, P.SPACING) if c.case_id == "flow_24")
    phi = P.RT.(P.load_raw(PHI_RAW, PHI_SHA))
    grid = P.GridSDF(phi, P.RT.(P.ORIGIN), P.RT.((P.SPACING, P.SPACING, P.SPACING)), P.SHAPE, P.RT(3), P.RT(0.15))
    tu = zeros(Float64, 5, 5, 5, 3)
    tu[3, 4, 2, 2] = -7.0
    u = P.preflight_tangent_location(tu, case, grid)
    @test u["selection"] == "max_abs_tangent"
    @test u["index"] == [3, 4, 2, 2]
    @test u["value"] == -7.0 && u["abs_value"] == 7.0 && u["finite"]
    @test u["solver_position"] == [1.5, 2.0, 0.5]  # WaterLily.loc at the y face, not the pressure center.
    @test !u["halo_cell"] && !u["inside_solid"]
    @test u["candidate_sdf_is_fluid_extension"] && u["candidate_sdf_m"] == 3.0
    @test u["ground_distance_m"] ≈ 0.5case.flow_spacing_m rtol=1e-6
    @test u["world_position_m"] ≈ collect(case.flow_origin_m) .+ case.flow_spacing_m .* u["solver_position"] rtol=1e-6
    tp = zeros(Float64, 5, 5, 5)
    tp[1, 2, 3] = NaN
    p = P.preflight_tangent_location(tp, case, grid)
    @test p["selection"] == "first_non_finite" && !p["finite"]
    @test p["index"] == [1, 2, 3] && isnan(p["value"])
    @test p["solver_position"] == [-0.5, 0.5, 1.5] && p["halo_cell"]
    @test occursin("\"value\":null", P.json(p))
    # A synthetic negative SDF at the same positive-ground point exercises
    # solid membership independently of the canonical geometry's thin edges.
    solid_grid = P.GridSDF(fill(P.RT(-1), 2, 2, 2), Tuple(P.RT.(u["world_position_m"])),
                           (P.RT(1), P.RT(1), P.RT(1)), (2, 2, 2), P.RT(3), P.RT(0))
    solid = P.preflight_tangent_location(tu, case, solid_grid)
    @test solid["inside_solid"] && solid["combined_sdf_m"] == -1
end

println("SYNTHETIC_NO_FLOW_BEGIN job_sha256=", bytes2hex(sha256(read(joinpath(@__DIR__, "waterlily_grad00_lambda_2026_11.jl")))))
SyntheticProducer.main()

# Python's existing JSON/NumPy readers independently check the real producer artifacts.
const CHECK = raw"""
import hashlib, json, math, sys
from pathlib import Path
import numpy as np
root, out = map(Path, sys.argv[1:])
sys.path.insert(0, str(root))
from scripts.analyze_grad00 import DIRECTIONS, INPUT_SHA256, REQUIRED_INDEX_KEYS
g2 = json.loads((out/'g2_run_index.json').read_text())
index = json.loads((out/'grad00_index.json').read_text())
directions = DIRECTIONS[:2]
expected = ['plain', *(label for d in directions for label in (d, d+'__plus', d+'__minus'))]
assert not (REQUIRED_INDEX_KEYS - index.keys())
assert index['status'] == g2['status'] == 'COMPLETE'
assert index['backend'] == 'cpu' and index['real_type'] in ('Float32','Float64')
assert index['directions'] == list(directions)
assert index['evidence_class'] == 'cpu_code_path_dryrun'
assert index['run_order'] == g2['run_order'] == expected
assert len(index['runs']) == len(g2['runs']) == 7
assert set(index['runs']) == set(expected)
assert index['input_sha256'] == INPUT_SHA256
assert all(value is False for value in index['qualification_flags'].values())
assert index['preflight']['synthetic_no_flow'] is True
assert index['wall_limit_s'] == 8*index['runs']['plain']['total_seconds']
base = np.fromfile(root/'docs/evidence/fd08_candidate_c_cpu_rehearsal_2026_10_05_retry1/inputs/cal_baseline_01.phi_f4_fortran.raw', dtype='<f4')
dirs = {d: np.fromfile(root/'docs/evidence/grad03_gpu_dual_spike_2026_10_08/inputs'/f'{d}.dir_f4_fortran.raw', dtype='<f4') for d in DIRECTIONS}
digest = lambda data: hashlib.sha256(data).hexdigest()
dtype = '<f4' if index['real_type'] == 'Float32' else '<f8'
for d in directions:
    assert index['by_direction'][d] == {'plain':'plain', 'dual':d, 'plus':d+'__plus', 'minus':d+'__minus', 'epsilon_m':0.001}
for label in expected:
    run = index['runs'][label]
    assert run['synthetic_no_flow'] is True and run['evidence_class'] == 'SYNTHETIC_TEST_FIXTURE'
    assert run['lambda_type'] == index['lambda_type']
    assert run['input_phi_storage_type'] == index['real_type']
    direction = next((d for d in directions if label.startswith(d)), None)
    sign = 1 if label.endswith('__plus') else -1 if label.endswith('__minus') else 0
    wanted = (base.astype('<f8') + sign*0.001*dirs[direction].astype('<f8')).astype(dtype) if sign else base.astype(dtype)
    assert run['input_phi_sha256'] == digest(wanted.tobytes()), label
    if label in directions:
        assert run['input_tangent_sha256'] == digest(dirs[label].astype(dtype).tobytes())
    for kind in ('summary', 'history', 'watchdog') if label in directions else ('summary', 'history'):
        assert run[kind+'_sha256'] == digest((out/run[kind+'_path']).read_bytes())
    for component in ('fx','fz'):
        for variant in ('dual_time','frozen_time'):
            assert all(math.isfinite(v) for v in run[f'window_mean_{component}_{variant}'].values())
    if label not in directions:
        assert 'watchdog_path' not in run
for document in (g2, index):
    document['producer_evidence_class'] = document['evidence_class']
    document['evidence_class'] = 'SYNTHETIC_TEST_FIXTURE'
    document['synthetic_no_flow'] = True
for name, document in (('g2_run_index.json',g2), ('grad00_index.json',index)):
    (out/name).write_text(json.dumps(document, indent=2, sort_keys=True)+'\n')
(out/'SYNTHETIC_NO_FLOW').write_text('Real main/save_run!/metadata; preflight and run_one were synthetic. No simulation or scientific labels.\n')
manifest = {'evidence_class':'SYNTHETIC_TEST_FIXTURE', 'solver_steps':0, 'run_count':7,
            'files':{p.name:digest(p.read_bytes()) for p in out.iterdir() if p.is_file()}}
(out/'synthetic_manifest.json').write_text(json.dumps(manifest, indent=2, sort_keys=True)+'\n')
print('SYNTHETIC_ORCHESTRATION_PASS runs=7 solver_steps=0 inputs_and_indices_verified')
"""
run(`$(joinpath(TEST_ROOT, ".venv", "bin", "python")) -c $CHECK $TEST_ROOT $TEST_OUTPUT`)
println("SYNTHETIC_NO_FLOW_OUTPUT ", TEST_OUTPUT)
