import sys, json, numpy as np
from pathlib import Path
sys.path.insert(0,"src"); sys.path.insert(0,"scripts")
import step01_states as S
from cfd_sdf.design.sdf_state import SDFDesignState
from cfd_sdf.design.volume_semantics import sampled_solid_centers_count
inv=json.load(open("docs/evidence/step01_finite_step_secant_2026_10_09/inventory.json"))
dirs={n:S.read_f4(Path("docs/evidence/grad03_gpu_dual_spike_2026_10_08/inputs")/e["file"]) for n,e in inv["directions"].items()}
parent=SDFDesignState.load("docs/evidence/p22_v17_volume_semantics_bridge_2026_10_11/inputs/lowdim03_parent.npz")
rec=json.load(open("docs/evidence/lowdim04_dual_grid_local_model_2026_10_11/pre_registration_blocker.json"))["existing_lowdim_geometry_preflight"]["states"]
print("parent phi C/F raw sha:",S.sha256_bytes(S.to_raw(parent.phi))[:16])
ok=0
for r in rec:
    d=r["direction"]; sign=r["sign"]
    child=S.perturb(parent.phi,dirs[d],1.25,sign)
    sha=S.sha256_bytes(S.to_raw(child)); match=(sha==r["phi_fortran_sha256"]); ok+=match
    print(r["state_name"],"match" if match else "MISMATCH", "max|dphi| mm",float(np.max(np.abs(child.astype(np.float64)-parent.phi)))*1e3)
print("matched",ok,"of",len(rec))
