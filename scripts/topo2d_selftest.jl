# Short CPU capability test; the compact domain is explicitly not the registered
# aerodynamic domain. Run: julia --project=julia/CFDSDFWaterLily scripts/topo2d_selftest.jl [OUTPUT_DIR]
using Test
include(joinpath(@__DIR__, "..", "julia", "topo2d", "Topo2D.jl"))
using .Topo2D
using WaterLily

function wp1_integration(scene,source)
    fixture()=Topo2D.setup(scene;reynolds=200.0,dims=(320,160),smoke=true,start=0.003,stop=0.015,sample_every=1,batches=4)
    split=fixture();rows=Vector{Float64}[]
    step=Topo2D.advance!(split,rows,0;stop_after_steps=3)
    result=mktempdir() do temp
        path=joinpath(temp,"wp1.bin")
        Topo2D.save_checkpoint(path,split.sim,step,rows;fingerprint=split.fingerprint)
        fresh=fixture()
        @test_throws ErrorException Topo2D.load_checkpoint(path;fingerprint="wrong",sim=fresh.sim)
        saved=Topo2D.load_checkpoint(path;fingerprint=split.fingerprint,sim=fresh.sim)
        @test isequal(rows,saved.rows)
        @test all(all(isnan,row[19:28]) for row in saved.rows)
        resumed=merge(fresh,(;sim=saved.sim))
        full_step=Topo2D.advance!(split,rows,step)
        resumed_step=Topo2D.advance!(resumed,saved.rows,saved.step)
        @test full_step==resumed_step
        means=[Topo2D.window_mean(rows,c,0.003,0.015) for c in (6,7)]
        restored=[Topo2D.window_mean(saved.rows,c,0.003,0.015) for c in (6,7)]
        @test all(isapprox(a,b;rtol=1e-6,atol=1e-10) for (a,b) in zip(means,restored))
        @test all(isfinite,resumed.sim.flow.u) && all(isfinite,resumed.sim.flow.p)
        Dict("passed"=>true,"source_path"=>source,"source_sha256"=>Topo2D.file_sha(source),"missing_columns_restored_as_nan"=>true,
             "provider"=>"WP1_DATA_ONLY_FINITE_COLUMN_ADAPTER","window_means"=>means,"restored_window_means"=>restored,"checkpoint_sha256"=>Topo2D.file_sha(path))
    end
    result
end

function wp2_integration(scene,source,out)
    started=time()
    run=Topo2D.setup(scene;reynolds=200.0,dims=(320,160),smoke=true,start=0.003,stop=0.015,sample_every=1,batches=4)
    @test all(values(run.available))
    @test first(run.box[2])-2-run.ground.z>=4
    rows=Vector{Float64}[]
    step=Topo2D.advance!(run,rows,0)
    @test step>=4 && all(all(isfinite,row) for row in rows)
    @test 0 < first(rows)[2] < run.contract.start
    actual=Topo2D.force_readouts(run.sim,run.box;body=run.wing)
    @test isapprox(rows[end][14],actual.cur[1];rtol=1e-6,atol=1e-10)
    @test isapprox(rows[end][19],actual.nds[1];rtol=1e-6,atol=1e-10)
    @test isapprox(rows[end][24],actual.cv[1];rtol=1e-6,atol=1e-10)
    dest=joinpath(out,"wp2_integration");mkpath(dest)
    summary=Topo2D.write_outputs(run,rows,step,dest;wall_seconds=time()-started)
    scene_path=joinpath(Topo2D.ROOT,"docs","harness","topo2d00_scenes",scene.configuration*".json")
    code="import json,sys; sys.path.insert(0,sys.argv[1]); from cfd_harness import scene_campaign as S; s=json.load(open(sys.argv[2])); g=json.load(open(sys.argv[3])); print(json.dumps(S.host_readouts(sys.argv[4],start=s['window_t_u_l'][0],end=s['window_t_u_l'][1],solver_length=s['solver_length'],force_scale=s['force_scale_n_per_m'],available=s['readout_available'],batches=s['batch_count'],element_names=[e['name'] for e in g['elements']]),sort_keys=True))"
    result=read(`$(Topo2D.PYTHON) -c $code $(joinpath(Topo2D.ROOT,"src")) $(joinpath(dest,"topo2d.summary.json")) $scene_path $(joinpath(dest,"topo2d.forces.csv"))`,String)
    write(joinpath(dest,"host_readouts.json"),result)
    @test !isempty(result)
    Dict("passed"=>true,"source_path"=>source,"source_sha256"=>Topo2D.file_sha(source),"wing_only_body"=>true,"validated_box_bounds"=>[[first(r),last(r)] for r in run.box],"finite_cur_nds_cv"=>true,"host_readouts_verified"=>true,"force_csv_sha256"=>summary["force_csv_sha256"])
end

function selftest(out)
    mkpath(out)
    isempty(readdir(out)) || error("selftest output directory already contains files")
    started=time()
    @test_throws Topo2D.NumericalFailure Topo2D.provider_readouts(()->throw(ArgumentError("non-finite CV momentum term")))
    @test_throws ArgumentError Topo2D.provider_readouts(()->throw(ArgumentError("box violates the physical-domain inset")))
    summaries=Dict{String,Any}()
    for config in ("E1","E2")
        path=joinpath(Topo2D.ROOT,"docs","harness","topo2d00_scenes",config*".json")
        scene=Topo2D.load_scene(path,Topo2D.file_sha(path))
        @test_throws ErrorException Topo2D.setup(scene;reynolds=Inf,smoke=true,start=0.003,stop=0.015)
        @test_throws ErrorException Topo2D.setup(scene;reynolds=200.0,smoke=true,start=0.003,stop=Inf)
        run=Topo2D.setup(scene;reynolds=200.0,dims=(320,160),smoke=true,start=0.003,stop=0.015,sample_every=1,batches=4)
        @test isbitstype(typeof(run.sim.body))
        println("TOPO2D_SELFTEST_BUILT ",config," seconds=",time()-started);flush(stdout)
        rows=Vector{Float64}[]
        step=0
        if config=="E1"
            mktempdir() do temp
                checkpoint=joinpath(temp,"saved.bin")
                step=Topo2D.advance!(run,rows,step;stop_after_steps=3)
                Topo2D.save_checkpoint(checkpoint,run.sim,step,rows;fingerprint=run.fingerprint)
                @test_throws ErrorException Topo2D.load_checkpoint(checkpoint;fingerprint="wrong")
                fresh=Topo2D.setup(scene;reynolds=200.0,dims=(320,160),smoke=true,start=0.003,stop=0.015,sample_every=1,batches=4)
                saved=Topo2D.load_checkpoint(checkpoint;fingerprint=run.fingerprint,sim=fresh.sim)
                resumed=merge(run,(;sim=saved.sim))
                full_step=Topo2D.advance!(run,rows,step)
                resumed_step=Topo2D.advance!(resumed,saved.rows,saved.step)
                @test full_step==resumed_step
                @test isequal(rows,saved.rows)
                @test run.sim.flow.u==resumed.sim.flow.u
                @test run.sim.flow.p==resumed.sim.flow.p
                for col in (6,7)
                    @test isequal(Topo2D.window_mean(rows,col,0.003,0.015),Topo2D.window_mean(saved.rows,col,0.003,0.015))
                end
                step=full_step
                summaries["checkpoint"]=Dict("passed"=>true,"saved_step"=>saved.step,"final_step"=>full_step,"checkpoint_sha256"=>Topo2D.file_sha(checkpoint),"field_bit_equal"=>true,"window_bit_equal"=>true)
            end
        else
            step=Topo2D.advance!(run,rows,step)
        end
        @test step>=4
        @test all(isfinite,run.sim.flow.u)
        @test all(isfinite,run.sim.flow.p)
        @test all(all(isfinite,r[1:18]) && all(isfinite,r[29:end]) for r in rows)
        # The streamwise face at j=8 lies 1.5 cells inside the ground's
        # BDIM core; this is actual evolved velocity, not just body metadata.
        near_ground=Float64(run.sim.flow.u[20,8,1])
        @test isapprox(near_ground,1.0;atol=1e-5,rtol=0)
        @test WaterLily.measure(run.ground,WaterLily.SVector(20.0f0,7.0f0),0)[3][1]==1

        # Direct analytic scene probes show that the wing and ground share
        # both components of the phase; the physical gap/ride height stays fixed.
        shift=(0.23scene.dx_mm/1000,0.0,0.37scene.dx_mm/1000)
        shifted=Topo2D.setup(scene;reynolds=200.0,phase_shift_m=shift,dims=(320,160),smoke=true,start=0.003,stop=0.015,sample_every=1,batches=4)
        delta=WaterLily.SVector(0.23f0,0.37f0)
        @test isapprox(shifted.ground.z-run.ground.z,0.37;atol=2e-6)
        for (a,b) in zip(run.bodies,shifted.bodies)
            probe=WaterLily.SVector(80.31f0,80.47f0)
            @test isapprox(a.sdf(probe,0),b.sdf(probe+delta,0);atol=2e-5)
        end
        @test isapprox(WaterLily.measure(run.ground,WaterLily.SVector(20.0f0,7.0f0),0)[1],WaterLily.measure(shifted.ground,WaterLily.SVector(20.0f0,7.0f0)+delta,0)[1];atol=2e-6)
        dest=joinpath(out,config)
        mkpath(dest)
        run_summary=Topo2D.write_outputs(run,rows,step,dest;wall_seconds=time()-started)
        summaries[config]=Dict("passed"=>true,"steps"=>step,"finite_forces"=>true,"ground_nearby_u"=>near_ground,"phase_common_translation"=>true,
            "force_csv_sha256"=>run_summary["force_csv_sha256"],"scene_sha256"=>scene.sha256,"flow_dims"=>[320,160],"reynolds"=>200.0,"window_t_u_l"=>[0.003,0.015])
        println("TOPO2D_SELFTEST_DONE ",config," seconds=",time()-started);flush(stdout)
    end
    cores=Dict{String,Any}()
    for config in ("E1","E2","E3")
        path=joinpath(Topo2D.ROOT,"docs","harness","topo2d00_scenes",config*".json")
        scene=Topo2D.load_scene(path,Topo2D.file_sha(path))
        cores[config]=Topo2D.phase_core_checks(scene)
        @test cores[config]["passed"]
    end
    summaries["phase_core_checks"]=cores
    # Optional read-only integration against actual sibling source paths. They
    # are never copied into this checkout or promoted to pinned formal inputs.
    scene_path=joinpath(Topo2D.ROOT,"docs","harness","topo2d00_scenes","E1.json")
    scene=Topo2D.load_scene(scene_path,Topo2D.file_sha(scene_path))
    entry_dir=joinpath(out,"job_entrypoint")
    entry=withenv("W4_JOB_SHA256"=>Topo2D.file_sha(joinpath(Topo2D.ROOT,"scripts","waterlily_topo2d_job.jl")),
        "W4_SCENE_SHA256"=>scene.sha256,"TOPO2D_BACKEND"=>"cpu","TOPO2D_SMOKE"=>"1","TOPO2D_REYNOLDS"=>"200",
        "TOPO2D_WINDOW_START"=>"0.003","TOPO2D_WINDOW_END"=>"0.015","TOPO2D_DIMS"=>"320,160",
        "TOPO2D_SAMPLE_EVERY"=>"1","TOPO2D_BATCHES"=>"4","W4_CANONICAL_ORIGIN_M"=>"0,0,0",
        "TOPO2D_PHASE"=>"0","TOPO2D_GRID"=>"main","TOPO2D_ROLE"=>"primary","TOPO2D_CASE_ID"=>"entrypoint",
        "TOPO2D_CHECKPOINT"=>nothing,"TOPO2D_RESUME"=>nothing) do
        Topo2D.main([scene_path,entry_dir])
    end
    @test isfile(joinpath(entry_dir,"job_preflight.json")) && isfile(joinpath(entry_dir,"W4_JOB_DONE"))
    @test entry["finite_forces"]
    summaries["job_entrypoint"]=Dict("passed"=>true,"force_csv_sha256"=>entry["force_csv_sha256"],"preflight_sha256"=>Topo2D.file_sha(joinpath(entry_dir,"job_preflight.json")))
    if haskey(ENV,"TOPO2D_WP1_TEST_SOURCE")
        source=abspath(ENV["TOPO2D_WP1_TEST_SOURCE"])
        before=Topo2D.file_sha(source)
        Base.include(Topo2D,source)
        Topo2D.CHECKPOINT_SOURCE[]=source
        summaries["wp1_integration"]=Base.invokelatest(wp1_integration,scene,source)
        summaries["wp1_integration"]["source_origin_path"]=get(ENV,"TOPO2D_WP1_TEST_ORIGIN",source)
        @test before==Topo2D.file_sha(source)
    end
    if haskey(ENV,"TOPO2D_WP2_TEST_SOURCE")
        source=abspath(ENV["TOPO2D_WP2_TEST_SOURCE"])
        before=Topo2D.file_sha(source)
        Base.include(Topo2D,source)
        Topo2D.FORCE_SOURCE[]=source
        path=joinpath(Topo2D.ROOT,"docs","harness","topo2d00_scenes","E2.json")
        scene=Topo2D.load_scene(path,Topo2D.file_sha(path))
        summaries["wp2_integration"]=Base.invokelatest(wp2_integration,scene,source,out)
        summaries["wp2_integration"]["source_origin_path"]=get(ENV,"TOPO2D_WP2_TEST_ORIGIN",source)
        @test before==Topo2D.file_sha(source)
    end
    summaries["schema"]="topo2d-cpu-selftest-v1"
    summaries["evidence_class"]="CPU_CAPABILITY_ONLY"
    summaries["smoke"]=true
    summaries["runtime"]=Topo2D.runtime_identity()
    summaries["selftest_source_sha256"]=Topo2D.file_sha(@__FILE__)
    summaries["source_sha256"]=Topo2D.source_hashes()
    if haskey(ENV,"TOPO2D_PROVIDER_ORIGIN_RECORD")
        path=ENV["TOPO2D_PROVIDER_ORIGIN_RECORD"]
        summaries["provider_origin_record"]=Dict("path"=>path,"sha256"=>Topo2D.file_sha(path))
    end
    summaries["cuda_module_loaded"]=any(id.name=="CUDA" for id in keys(Base.loaded_modules))
    @test !summaries["cuda_module_loaded"]
    summaries["wall_seconds"]=time()-started
    toml=joinpath(out,"selftest.toml")
    open(toml,"w") do io
        Topo2D.TOML.print(io,summaries;sorted=true)
    end
    Base.run(`$(Topo2D.PYTHON) $(Topo2D.BRIDGE) summary-json $toml $(joinpath(out,"selftest.json"))`)
    println("TOPO2D_SELFTEST_PASS ",out)
end

@testset "TOPO-2D CPU scene, force, moving-ground and resume" begin
    selftest(isempty(ARGS) ? mktempdir(prefix="topo2d-selftest-") : abspath(ARGS[1]))
end
