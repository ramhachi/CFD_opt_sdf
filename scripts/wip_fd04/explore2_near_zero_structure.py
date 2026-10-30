import numpy as np
from scipy import ndimage as ndi
from cfd_sdf.design.sdf_state import SDFDesignState
s=SDFDesignState.load('/Users/sota/projects/FomulaTMU/CFD2026_09/work/sdf_native_genesis_v16/sdf_design_state.npz')
phi=s.phi.astype(np.float64)
a=np.abs(phi)
near=a<1e-7
neg=phi<0
print('negatives >1e-7 magnitude:', (neg&~near).sum(), np.unique(np.round(phi[neg&~near],4)))
print('near-zero sign counts: pos',(near&(phi>0)).sum(),'neg',(near&(phi<0)).sum(),'zero',(phi==0).sum())
lab,n=ndi.label(near,structure=np.ones((3,3,3)))
print('near components',n,[int((lab==i).sum()) for i in range(1,n+1)][:10])
idx=np.argwhere(near)
print('bbox near', idx.min(0), idx.max(0))
# thickness per axis: extents
for ax in range(3):
    print(ax,'extent',np.bincount(idx[:,ax]).nonzero()[0].min(),np.bincount(idx[:,ax]).nonzero()[0].max())
# fluid neighbors of near-zero: value 0.05?
# is phi == EDT(dist to nearest near-zero node)?
edt=ndi.distance_transform_edt(~near,sampling=0.05)
m=~near
print('max |phi-EDT| on non-near:',np.abs(phi[m]-edt[m]).max(), 'median',np.median(np.abs(phi[m]-edt[m])))
# neg nodes not near: where?
ii=np.argwhere(neg&~near)
print(ii[:10])
# design mask overlap with near
print('near in design',(near&s.design_mask).sum())
# print a slice for orientation
k=np.bincount(idx[:,2]).nonzero()[0]
print('z-layers with near',k)
for kk in k[:3]:
    sl=near[:,:,kk]
    print('z',kk,sl.sum())
