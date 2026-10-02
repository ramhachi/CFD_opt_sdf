import csv, importlib.util, sys
from pathlib import Path
import numpy as np
import pytest

ROOT=Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location("surface_round9",ROOT/"scripts/run_candidate_c_surface_flux_round9.py")
module=importlib.util.module_from_spec(SPEC)
sys.path.insert(0,str(ROOT/"scripts"))
try: SPEC.loader.exec_module(module)
finally: sys.path.pop(0)

def write_csv(path,records):
    with path.open("w",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=list(records[0]));writer.writeheader();writer.writerows(records)

def synthetic_artifact(tmp_path,monkeypatch):
    geometry=tmp_path/"geometry";geometry.mkdir();artifact=tmp_path/"artifact";artifact.mkdir()
    monkeypatch.setattr(module,"GEOMETRY",geometry);monkeypatch.setattr(module,"DIMS",(4,4,4))
    histories=[];point_records=[]
    mask=np.zeros((4,4,4),dtype=np.uint8);mask[1:3,1:3,1:3]=1
    transition=np.zeros_like(mask);transition[1,1,1]=1
    for fixture in module.FIXTURES:
        directory=geometry/fixture;directory.mkdir();(directory/"fixed_fluid_transition_masks.bin").write_bytes(mask.tobytes(order="F")+transition.tobytes(order="F"))
        for kind in (("ground",) if fixture=="moving_ground_only" else ("body","ground")):
            normal=(0.,0.,1.) if kind=="ground" else (1.,0.,0.)
            for level in range(3):
                point={"point_id":1,"x_m":-2.45,"y_m":-1.15,"z_m":-.85,"nx_geom":normal[0],"ny_geom":normal[1],"nz_geom":normal[2],"weight_m2":1.}
                write_csv(directory/f"{kind}_level{level}_quadrature.csv",[point])
        for mode in module.MODES:
            u=np.zeros((4,4,4,3),dtype="<f4");u[:,:,:,0]=1.;zero=np.zeros((4,4,4),dtype="<f4")
            for name,data in (("u",u),("p",zero),("cached_scaled_residual",zero)):(artifact/f"{fixture}__{mode}__{name}_f32_fortran.bin").write_bytes(data.tobytes(order="F"))
            for kind in (("ground",) if fixture=="moving_ground_only" else ("body","ground")):
                normal=(0.,0.,1.) if kind=="ground" else (1.,0.,0.)
                V=(1.,0.,0.) if kind=="ground" else (0.,0.,0.)
                slip=0. if kind=="ground" else 1.;opslip=slip*.5
                for level in range(3):
                    for t in (.05,.15,.30):
                        row={"fixture":fixture,"mode":mode,"step":int(t*100),"t_u_over_l":t,"surface":kind,"level":level,"points":1,"area_m2":1.,"signed_body_outward_kg_s":slip,"absolute_kg_s":slip,"geom_slip_rms_m_s":slip,"geom_slip_max_m_s":slip,"operator_signed_kg_s":opslip,"operator_absolute_kg_s":opslip}
                        for axis in "xyz":
                            row[f"candidate_raw_pressure_f{axis}"]=-2. if axis=="x" else 0.
                            row[f"candidate_raw_viscous_f{axis}"]=.5 if axis=="x" else 0.
                            row[f"candidate_total_f{axis}_n"]=(2.-.5)*.0025 if axis=="x" else 0.
                        for label,count in (("fluid",8),("transition",1)):
                            row[f"{label}_nodes"]=count
                            for suffix in ("div_rms_s_inv","div_max_s_inv","cached_residual_rms_solver","cached_residual_max_solver"):row[f"{label}_{suffix}"]=0.
                        histories.append(row)
                    point={"fixture":fixture,"mode":mode,"surface":kind,"level":level,"t_u_over_l":.30,"point_id":1,"weight_m2":1.,"geom_slip_m_s":slip,"operator_slip_m_s":opslip}
                    for d,axis in enumerate("xyz"):
                        point[f"{axis}_world_m"]=(-2.45,-1.15,-.85)[d];point[f"{axis}_solver_f32"]=1.
                        point[f"n{axis}_geom"]=normal[d];point[f"n{axis}_operator"]=normal[d]*.5
                        point[f"u{axis}_solver"]=1. if d==0 else 0.;point[f"v{axis}_body_solver"]=V[d]
                    point_records.append(point)
    write_csv(artifact/"surface_history.csv",histories);write_csv(artifact/"final_point_values.csv",point_records)
    return artifact,histories,point_records

def test_independent_raw_flux_force_and_final_field_recomputation(tmp_path,monkeypatch):
    artifact,_,_=synthetic_artifact(tmp_path,monkeypatch);result=module.verify(artifact)
    assert result["status"]=="diagnostic_data_integrity_ok"
    assert all(value is False for value in result["qualification_flags"].values())
    body=result["surface_groups"]["sphere/candidate_c/body/0"]["final_observables"]
    assert body["signed_body_outward_kg_s"]==1. and body["operator_signed_kg_s"]==.5

@pytest.mark.parametrize("corruption",["force_sign","missing_point","field_divergence","ground_velocity"])
def test_corrupted_raw_evidence_fails_closed(tmp_path,monkeypatch,corruption):
    artifact,history,points=synthetic_artifact(tmp_path,monkeypatch)
    if corruption=="force_sign":history[0]["candidate_total_fx_n"]*=-1;write_csv(artifact/"surface_history.csv",history)
    elif corruption=="missing_point":write_csv(artifact/"final_point_values.csv",points[1:])
    elif corruption=="ground_velocity":
        point=next(p for p in points if p["surface"]=="ground");point["vx_body_solver"]=0.;write_csv(artifact/"final_point_values.csv",points)
    else:
        path=artifact/"sphere__native__u_f32_fortran.bin";u=np.fromfile(path,dtype="<f4").reshape((4,4,4,3),order="F");u[2,1,1,0]=2.;path.write_bytes(u.tobytes(order="F"))
    with pytest.raises(ValueError):module.verify(artifact)
