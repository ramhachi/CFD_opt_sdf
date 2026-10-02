#!/usr/bin/env python3
"""Bounded CPU surface observables; no physical acceptance or qualification."""
from __future__ import annotations
import argparse, csv, hashlib, json, math, platform, subprocess, sys
from collections import defaultdict
from pathlib import Path
import numpy as np
from verify_candidate_c_grid_sdf_long_cpu_diagnostic_round7 import _window_mean

ROOT=Path(__file__).resolve().parents[1]
PLAN=ROOT/"docs/evidence/candidate_c_surface_flux_round8/plan.json"
JOB=ROOT/"scripts/candidate_c_surface_flux_round8.jl"
GEOMETRY=ROOT/"work/candidate_c_surface_flux_round8_geometry"
OUTPUT=ROOT/"work/candidate_c_surface_flux_round8"
FIXTURES=("sphere","plate_1cell","plate_2cell","moving_ground_only")
MODES=("native","grid_upstream","candidate_c")
DIMS=(102,50,38)
FLAGS={key:False for key in ("shape_update_allowed","fd_oracle","field_gradient","reverse","optimizer","topology")}

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def write_new(path,value):
    with path.open("x") as f: json.dump(value,f,indent=2,sort_keys=True,allow_nan=False);f.write("\n")
def check_inventory(path,base):
    for line in path.read_text().splitlines():
        expected,relative=line.split("  ",1)
        p=Path(relative[9:]) if relative.startswith("external:") else base/relative
        if not p.is_file() or sha(p)!=expected: raise ValueError(f"inventory drift: {relative}")
def registration():
    plan=json.loads(PLAN.read_text())
    if PLAN.with_suffix(".json.sha256").read_text().strip()!=sha(PLAN): raise ValueError("plan sidecar drift")
    if plan.get("immutable") is not True or plan.get("registered_before_measurement") is not True: raise ValueError("not preregistered")
    if plan.get("qualification_flags")!=FLAGS or any(value is not False for value in plan["qualification_flags"].values()): raise ValueError("flags drift")
    if plan.get("fixture_ids")!=list(FIXTURES) or plan.get("modes")!=list(MODES): raise ValueError("matrix drift")
    if plan.get("time_window_t_u_over_l")!=[.10,.25] or plan.get("target_time_t_u_over_l")!=.25: raise ValueError("time contract drift")
    if plan.get("pressure_array_dims")!=list(DIMS) or plan.get("force_scale_n")!=.0025: raise ValueError("unit/grid drift")
    if sha(Path(__file__))!=plan["runner_sha256"] or sha(JOB)!=plan["job_sha256"]: raise ValueError("source drift")
    sources=PLAN.parent/"sources.sha256"; inputs=GEOMETRY/"inputs.sha256"
    if sha(sources)!=plan["source_inventory_sha256"] or sha(inputs)!=plan["geometry_inventory_sha256"]: raise ValueError("inventory hash drift")
    check_inventory(sources,ROOT);check_inventory(inputs,GEOMETRY)
    return plan

def rows(path):
    with path.open() as f: return list(csv.DictReader(f))
def numeric(row,key):
    value=float(row[key])
    if not math.isfinite(value): raise ValueError(f"nonfinite {key}")
    return value

def runtime_record(stdout):
    lines=[line for line in stdout.splitlines() if line.startswith("CANDIDATE_C_SURFACE_RUNTIME ")]
    if len(lines)!=1: raise ValueError("runtime identity missing")
    fields=dict(item.split("=",1) for item in lines[0].split()[1:])
    if fields!={"julia":"1.12.6","waterlily":"1.8.0","threads":fields.get("threads"),"backend":"Array","precision":"Float32","job_sha256":sha(JOB),"criteria_sha256":sha(PLAN)} or int(fields["threads"])<1: raise ValueError("runtime identity drift")
    return lines[0]

def verify(directory):
    history=rows(directory/"surface_history.csv"); points=rows(directory/"final_point_values.csv")
    grouped=defaultdict(list); pointgroups=defaultdict(list)
    for row in history:
        key=(row["fixture"],row["mode"],row["surface"],int(row["level"]))
        if key[0] not in FIXTURES or key[1] not in MODES: raise ValueError("unknown arm")
        for field in row:
            if field not in ("fixture","mode","surface"): numeric(row,field)
        for axis in ("x","y","z"):
            total=numeric(row,f"candidate_total_f{axis}_n")
            expect=-(numeric(row,f"candidate_raw_pressure_f{axis}")+numeric(row,f"candidate_raw_viscous_f{axis}"))*.0025
            if not math.isclose(total,expect,rel_tol=0,abs_tol=1e-12): raise ValueError("raw-force sign/scale drift")
        grouped[key].append(row)
    expected={(fixture,mode,kind,level) for fixture in FIXTURES for mode in MODES
              for kind in (("ground",) if fixture=="moving_ground_only" else ("body","ground")) for level in range(3)}
    if set(grouped)!=expected: raise ValueError("incomplete surface/time matrix")
    for row in points:
        key=(row["fixture"],row["mode"],row["surface"],int(row["level"]))
        for field in row:
            if field not in ("fixture","mode","surface"): numeric(row,field)
        normal=[numeric(row,f"n{axis}_geom") for axis in "xyz"]
        rel=[numeric(row,f"u{axis}_solver")-numeric(row,f"v{axis}_body_solver") for axis in "xyz"]
        if row["surface"]=="ground" and (normal!=[0.,0.,1.] or [numeric(row,f"v{axis}_body_solver") for axis in "xyz"]!=[1.,0.,0.]): raise ValueError("moving-ground identity drift")
        for prefix,reported in (("geom","geom_slip_m_s"),("operator","operator_slip_m_s")):
            n=[numeric(row,f"n{axis}_{prefix}") for axis in "xyz"]
            if not math.isclose(math.fsum(a*b for a,b in zip(n,rel)),numeric(row,reported),rel_tol=0,abs_tol=1e-12): raise ValueError("point dot product drift")
        if not math.isclose(math.fsum(x*x for x in normal),1,rel_tol=0,abs_tol=1e-12) or numeric(row,"weight_m2")<=0: raise ValueError("invalid geometric weight/normal")
        pointgroups[key].append(row)
    if set(pointgroups)!=expected: raise ValueError("incomplete final point matrix")
    result={}
    for key,data in grouped.items():
        times=[numeric(r,"t_u_over_l") for r in data]
        if sorted(set(times))!=times or times[0]>.10 or times[-1]<.25: raise ValueError("missing exact-window bracket")
        final=data[-1]; raw=pointgroups[key]
        if len(raw)!=int(final["points"]) or [int(r["point_id"]) for r in raw]!=list(range(1,len(raw)+1)): raise ValueError("point coverage mismatch")
        source_points=rows(GEOMETRY/key[0]/f"{key[2]}_level{key[3]}_quadrature.csv")
        if len(source_points)!=len(raw): raise ValueError("registered quadrature coverage mismatch")
        for observed,registered in zip(raw,source_points):
            for observed_key,source_key in (("x_world_m","x_m"),("y_world_m","y_m"),("z_world_m","z_m"),("nx_geom","nx_geom"),("ny_geom","ny_geom"),("nz_geom","nz_geom"),("weight_m2","weight_m2")):
                if numeric(observed,observed_key)!=numeric(registered,source_key): raise ValueError("registered quadrature payload drift")
            for d,(axis,origin) in enumerate(zip("xyz",(-2.5,-1.2,-.9))):
                x=numeric(observed,f"{axis}_solver_f32")
                if x!=float(np.float32((numeric(observed,f"{axis}_world_m")-origin)/.05)) or x<0 or x+.5>DIMS[d]-2: raise ValueError("coordinate mapping or unclamped-domain drift")
        if any(numeric(r,"t_u_over_l")!=times[-1] for r in raw): raise ValueError("final point time mismatch")
        weights=[numeric(r,"weight_m2") for r in raw];slips=[numeric(r,"geom_slip_m_s") for r in raw];op=[numeric(r,"operator_slip_m_s") for r in raw]
        area=math.fsum(weights)
        calculated={"area_m2":area,"signed_body_outward_kg_s":math.fsum(w*s for w,s in zip(weights,slips)),"absolute_kg_s":math.fsum(w*abs(s) for w,s in zip(weights,slips)),"geom_slip_rms_m_s":math.sqrt(math.fsum(w*s*s for w,s in zip(weights,slips))/area),"geom_slip_max_m_s":max(map(abs,slips)),"operator_signed_kg_s":math.fsum(w*s for w,s in zip(weights,op)),"operator_absolute_kg_s":math.fsum(w*abs(s) for w,s in zip(weights,op))}
        for field,value in calculated.items():
            if not math.isclose(value,numeric(final,field),rel_tol=0,abs_tol=1e-10): raise ValueError(f"final quadrature reduction mismatch: {key}/{field}")
        result["/".join(map(str,key))]={"final_observables":calculated,"window_means":{field:_window_mean(data,field,.10,.25) for field in ("signed_body_outward_kg_s","absolute_kg_s","geom_slip_rms_m_s","operator_signed_kg_s","candidate_total_fx_n","candidate_total_fz_n")}}
    for fixture in FIXTURES:
        maskbytes=np.frombuffer((GEOMETRY/fixture/"fixed_fluid_transition_masks.bin").read_bytes(),dtype=np.uint8)
        n=math.prod(DIMS)
        for mode in MODES:
            prefix=f"{fixture}__{mode}__"
            u=np.fromfile(directory/(prefix+"u_f32_fortran.bin"),dtype="<f4").reshape((*DIMS,3),order="F")
            p=np.fromfile(directory/(prefix+"p_f32_fortran.bin"),dtype="<f4").reshape(DIMS,order="F")
            cached=np.fromfile(directory/(prefix+"cached_scaled_residual_f32_fortran.bin"),dtype="<f4").reshape(DIMS,order="F")
            if not all(np.isfinite(a).all() for a in (u,p,cached)): raise ValueError("nonfinite final raw field")
            div=np.zeros(DIMS,dtype=np.float64)
            interior=tuple(slice(1,-1) for _ in DIMS)
            for axis in range(3):
                shifted=list(interior);shifted[axis]=slice(2,None)
                div[interior]+=u[(*shifted,axis)].astype(np.float64)-u[(*interior,axis)].astype(np.float64)
            div*=20.
            final=grouped[(fixture,mode,"ground",0)][-1]
            for index,label in enumerate(("fluid","transition")):
                mask=maskbytes[index*n:(index+1)*n].reshape(DIMS,order="F").astype(bool)
                vals=div[mask];residual=cached[mask].astype(np.float64)
                checks={f"{label}_nodes":len(vals),f"{label}_div_rms_s_inv":float(np.sqrt(np.mean(vals**2))),f"{label}_div_max_s_inv":float(np.max(np.abs(vals))),f"{label}_cached_residual_rms_solver":float(np.sqrt(np.mean(residual**2))),f"{label}_cached_residual_max_solver":float(np.max(np.abs(residual)))}
                for field,value in checks.items():
                    if not math.isclose(value,numeric(final,field),rel_tol=0,abs_tol=1e-10): raise ValueError(f"final field norm mismatch: {fixture}/{mode}/{field}")
    return {"status":"diagnostic_data_integrity_ok","evidence_class":"bounded_CPU_surface_observables_not_physical_qualification","surface_groups":result,"qualification_flags":FLAGS,"limitations":["refinement differences are indicators only, not uncertainty bounds or resolution floors","ground patch is open and does not close a fluid control volume","cached scaled-system residual is not recomputed against unscaled pressure","intermediate field norms are source-produced; final raw fields are independently recomputed","no mass/no-through/stationarity/accuracy criterion or production qualification"]}

def main():
    parser=argparse.ArgumentParser();parser.add_argument("--preflight-only",action="store_true");parser.add_argument("--parent-reviewed",action="store_true");args=parser.parse_args()
    plan=registration()
    if not args.parent_reviewed: raise ValueError("parent source review required before initialization or steps")
    OUTPUT.mkdir(exist_ok=True);runid="init-001" if args.preflight_only else "run-001";claim=OUTPUT/(runid+".claim");claim.mkdir();directory=OUTPUT/runid
    if directory.exists(): raise FileExistsError("existing run directory")
    command=["julia","--startup-file=no","--threads=auto",f"--project={ROOT/'julia/CFDSDFWaterLily'}",str(JOB),str(PLAN),str(GEOMETRY),str(directory)]
    if args.preflight_only: command.append("--preflight-only")
    try:
        completed=subprocess.run(command,capture_output=True,text=True,cwd=ROOT,timeout=1800)
        directory.mkdir(exist_ok=True);(directory/"solver.stdout.txt").write_text(completed.stdout);(directory/"solver.stderr.txt").write_text(completed.stderr)
        if completed.returncode: raise ValueError(f"Julia exit {completed.returncode}: {completed.stderr[-2000:]}")
        runtime=runtime_record(completed.stdout)
        marker="CANDIDATE_C_SURFACE_INITIALIZATION_PASS no_sim_step" if args.preflight_only else "CANDIDATE_C_SURFACE_DONE raw_observables_only_no_physical_qualification"
        if marker not in completed.stdout: raise ValueError("completion marker missing")
        result={"status":"initialization_capability_only_no_sim_step","qualification_flags":FLAGS} if args.preflight_only else verify(directory)
        result.update({"criteria_sha256":sha(PLAN),"runner_sha256":sha(Path(__file__)),"job_sha256":sha(JOB),"runtime_line":runtime,"host_python":sys.version,"host_platform":platform.platform(),"command":command,"artifact_sha256":{p.name:sha(p) for p in directory.iterdir() if p.is_file()}})
        write_new(directory/"result.json",result);print(json.dumps({"status":result["status"],"result_path":str(directory/"result.json"),"result_sha256":sha(directory/"result.json")}))
        if not args.preflight_only: (directory/"DONE").write_text("diagnostic_integrity_only\n")
    except Exception as exc:
        directory.mkdir(exist_ok=True)
        if isinstance(exc,subprocess.TimeoutExpired):
            for stream in ("stdout","stderr"):
                text=getattr(exc,stream) or "";text=text.decode(errors="replace") if isinstance(text,bytes) else text;(directory/("solver."+stream+".txt")).write_text(text)
        write_new(directory/"ERROR.json",{"status":"ERROR","detail":repr(exc),"criteria_sha256":sha(PLAN),"partial_artifacts":{p.name:sha(p) for p in directory.iterdir() if p.is_file()},"qualification_flags":FLAGS});raise

if __name__=="__main__": main()
