import sys, numpy as np
sys.path.insert(0,"src")
from cfd_sdf.design.sdf_state import SDFDesignState
from cfd_sdf.design.volume_semantics import _corner_mean
I="docs/evidence/p22_v17_volume_semantics_bridge_2026_10_11/inputs/"
for name in ("v17_baseline.npz","lowdim03_parent.npz"):
    s=SDFDesignState.load(I+name); c=_corner_mean(s.phi).astype(np.float64); a=np.abs(c)
    print(name,"cells",c.size,"solid",int((c<0).sum()),"exact-zero centres",int((c==0).sum()),"min|centre| (m)",a.min())
    for r in (0.625e-3,1.25e-3,1.875e-3,2.5e-3,3.125e-3,3.2e-3,5e-3,12.5e-3):
        print(f"   cells with |centre|<{r*1e3:g} mm: {int((a<r).sum())}")
