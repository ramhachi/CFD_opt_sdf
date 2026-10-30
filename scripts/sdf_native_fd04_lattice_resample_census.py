"""FD-04 (#36) solver-free check: is the near-zero gradient a sampling artifact?

Resample the source STL signed distance on candidate lattices and count force-band
cells (|phi(center)| <= 0.05 m) whose trilinear center gradient is near zero.
"""
import sys
import numpy as np
import trimesh

STL = sys.argv[1]
mesh = trimesh.load(STL)
H0, ORIGIN0, SHAPE0 = 0.05, np.array([-1.0, -0.8, -0.6]), np.array([61, 33, 25])


def sdf(points):
    # trimesh: positive inside -> repository convention phi < 0 solid
    return -trimesh.proximity.signed_distance(mesh, points)


def census(origin, h, shape):
    axes = [origin[a] + h * np.arange(shape[a]) for a in range(3)]
    pts = np.stack(np.meshgrid(*axes, indexing="ij"), -1).reshape(-1, 3)
    phi = sdf(pts).reshape(shape)
    c = [phi[i:shape[0] - 1 + i, j:shape[1] - 1 + j, k:shape[2] - 1 + k]
         for i in (0, 1) for j in (0, 1) for k in (0, 1)]
    center = sum(c) / 8
    gx = (sum(c[4:]) - sum(c[:4])) / (4 * h)
    gy = (c[2] + c[3] + c[6] + c[7] - c[0] - c[1] - c[4] - c[5]) / (4 * h)
    gz = (c[1] + c[3] + c[5] + c[7] - c[0] - c[2] - c[4] - c[6]) / (4 * h)
    g = np.sqrt(gx**2 + gy**2 + gz**2)
    band = np.abs(center) <= 0.05
    gb = g[band]
    return dict(h=h, band=int(band.sum()), lt_1e6=int((gb < 1e-6).sum()),
                lt_0p25=int((gb < 0.25).sum()), p5=float(np.percentile(gb, 5)),
                median=float(np.median(gb)), near_zero_nodes=int((np.abs(phi) < 1e-7).sum()))


for name, origin, h, shape in [
    ("canonical_lattice", ORIGIN0, H0, SHAPE0),
    ("half_cell_offset", ORIGIN0 + H0 / 2, H0, SHAPE0 - 1),
    ("quarter_cell_offset", ORIGIN0 + H0 / 4, H0, SHAPE0 - 1),
    ("h_over_2", ORIGIN0, H0 / 2, 2 * SHAPE0 - 1),
]:
    print(name, census(origin, h, shape), flush=True)
