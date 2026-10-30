import numpy as np
from cfd_sdf.design.sdf_state import SDFDesignState
s=SDFDesignState.load('/Users/sota/projects/FomulaTMU/CFD2026_09/work/sdf_native_genesis_v16/sdf_design_state.npz')
phi=s.phi
print(phi.dtype,phi.shape,s.narrow_band_width_m,s.origin_m,s.spacing_m)
print('min max',phi.min(),phi.max())
print('neg',(phi<0).sum(),'pos',(phi>0).sum(),'zero',(phi==0).sum())
a=np.abs(phi)
for t in [1e-12,1e-9,1e-8,1e-7,1e-6,1e-5,1e-4,1e-3,1e-2,0.05]:
    print(t,(a<t).sum())
v=np.unique(phi)
print(len(v), v[np.argsort(np.abs(v))][:15])
print(np.unique(np.round(np.abs(phi),3))[:30])
print(s.design_mask.shape, s.design_mask.sum())
