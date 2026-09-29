import numpy as np
from cfd_sdf.design.sdf_state import SDFDesignState
s=SDFDesignState.load('/Users/sota/projects/FomulaTMU/CFD2026_09/work/sdf_native_genesis_v16/sdf_design_state.npz')
phi=s.phi.astype(np.float64)
h=0.05
nx,ny,nz=phi.shape
# cell-center analytic gradient
def cellgrad(phi):
    c=lambda i,j,k: phi[i:nx-1+i,j:ny-1+j,k:nz-1+k]
    gx=(c(1,0,0)+c(1,1,0)+c(1,0,1)+c(1,1,1)-c(0,0,0)-c(0,1,0)-c(0,0,1)-c(0,1,1))/4/h
    gy=(c(0,1,0)+c(1,1,0)+c(0,1,1)+c(1,1,1)-c(0,0,0)-c(1,0,0)-c(0,0,1)-c(1,0,1))/4/h
    gz=(c(0,0,1)+c(1,0,1)+c(0,1,1)+c(1,1,1)-c(0,0,0)-c(1,0,0)-c(0,1,0)-c(1,1,0))/4/h
    return gx,gy,gz
gx,gy,gz=cellgrad(phi)
g=np.sqrt(gx**2+gy**2+gz**2)
val=(sum(phi[i:nx-1+i,j:ny-1+j,k:nz-1+k] for i in (0,1) for j in (0,1) for k in (0,1)))/8
print('cells',g.size)
# force support: |value|<=0.05
sup=np.abs(val)<=0.05
print('support cells',sup.sum())
bins=[0,1e-6,1e-3,1e-2,0.1,0.25,0.5,0.75,0.9,1.1,1.5,2,5,100]
hh,_=np.histogram(g[sup],bins)
for a,b,c in zip(bins[:-1],bins[1:],hh): print(f'{a}-{b}: {c}')
print('flat cells (all 8 corners |phi|<1e-7):',sum(1 for _ in [0]) and int(((np.stack([np.abs(phi[i:nx-1+i,j:ny-1+j,k:nz-1+k])<1e-7 for i in (0,1) for j in (0,1) for k in (0,1)])).all(0)).sum()))
print('sorted small g in support', np.sort(g[sup])[:60])
