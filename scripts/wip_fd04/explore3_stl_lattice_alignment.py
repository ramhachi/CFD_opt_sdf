import numpy as np, trimesh
p='/Users/sota/projects/FomulaTMU/CFD2026_09/work/pq4_1_v16_state_v2/sweep/threshold_0.5/iso_surface.stl'
m=trimesh.load_mesh(p,force='mesh')
print(m.vertices.shape,m.faces.shape,m.is_watertight,m.bounds, m.volume)
o=np.array([-1.0,-0.8,-0.6]);h=0.05
r=(m.vertices-o)/h
frac=r-np.round(r)
print('vertex frac mod h (abs) quantiles per axis:',[np.quantile(np.abs(frac[:,a]),[0,.5,.9,1]).round(4).tolist() for a in range(3)])
print('vertices with all coords on lattice',(np.abs(frac).max(1)<1e-4).mean())
# frac==0.5 (cell centers)
half=np.abs(np.abs(frac)-0.5)<1e-4
print('coords at half offset frac',half.mean(0))
n=m.face_normals
ax=np.abs(n).max(1)
print('axis-aligned faces',(ax>0.999).mean())
# facets aligned to lattice planes: for axis aligned faces, plane coordinate frac
for a in range(3):
    sel=np.abs(n[:,a])>0.999
    c=m.triangles_center[sel,a]
    rr=(c-o[a])/h
    print('axis',a,'faces',sel.sum(),'plane offset mod 1 (0=on node plane) quantiles',np.quantile(np.abs(rr-np.round(rr)),[0,.5,.9,1]).round(4).tolist())
