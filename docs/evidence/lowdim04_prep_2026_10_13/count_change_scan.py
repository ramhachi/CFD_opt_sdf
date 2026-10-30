import sys, json, numpy as np
from pathlib import Path
sys.path.insert(0,"src"); sys.path.insert(0,"scripts")
import step01_states as S
from cfd_sdf.design.sdf_state import SDFDesignState
from cfd_sdf.design.volume_semantics import _corner_mean
inv=json.load(open("docs/evidence/step01_finite_step_secant_2026_10_09/inventory.json"))
dirs={n:S.read_f4(Path("docs/evidence/grad03_gpu_dual_spike_2026_10_08/inputs")/e["file"]) for n,e in inv["directions"].items()}
prop=S.read_f4(Path("docs/evidence/lowdim01_four_direction_capability_2026_10_09/inputs/proposal_downforce.dir_f4_fortran.raw")) if Path("docs/evidence/lowdim01_four_direction_capability_2026_10_09/inputs/proposal_downforce.dir_f4_fortran.raw").exists() else None
print("proposal file found:",prop is not None)
for nm in ("v17_baseline.npz","lowdim03_parent.npz"):
    base=SDFDesignState.load("docs/evidence/p22_v17_volume_semantics_bridge_2026_10_11/inputs/"+nm).phi
    print("==",nm)
    fields=dict(dirs); 
    if prop is not None: fields["proposal_downforce"]=prop
    for n,d in fields.items():
        row=[]
        for sign in (+1,-1):
            first=None
            for mm in np.arange(0.5,15.01,0.25):
                N=int((_corner_mean(S.perturb(base,d,mm,sign))<0).sum())
                if N!=8272: first=(float(mm),N); break
            row.append(first)
        print(f"  {n:24s} first count change +: {row[0]}  -: {row[1]}")
