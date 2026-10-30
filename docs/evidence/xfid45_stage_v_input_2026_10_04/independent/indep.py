import json, hashlib, sys, numpy as np, scipy.sparse as sp
from scipy.sparse.csgraph import connected_components
R = "/Users/sota/projects/FomulaTMU/CFD2026_09/.claude/worktrees/cert02/"
OUT = "/private/tmp/claude-501/-Users-sota-projects-FomulaTMU-CFD2026-09/c963c69b-7105-4be7-ace5-c74641e07de7/scratchpad/indep_stagev/"
H = 0.025; ORG = np.array([-1.0, -0.8, -0.6]); TOL = 64 * np.finfo(float).eps * H
LO = np.array([-2.5, -1.2, -0.9]); HI = np.array([2.5, 1.2, 0.9])
prereg = json.load(open(R + "docs/evidence/xfid45_stage_v_input_2026_10_04/preregistration.json"))
CASES = ["baseline", "D0_interface_offset_minus", "D0_interface_offset_plus", "D1_filtered_seed11_minus",
         "D1_filtered_seed11_plus", "D2_filtered_seed2026_minus", "D2_filtered_seed2026_plus"]
sha = lambda b: hashlib.sha256(b).hexdigest()

def merge(V, F):
    u, inv = np.unique(V, axis=0, return_inverse=True)
    return u, inv.reshape(-1)[F]

def edge_components(F):
    """edge-connected face components on merged-index faces"""
    M = len(F)
    e = np.stack([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]], 1).reshape(-1, 2)
    e = np.sort(e, axis=1); fid = np.repeat(np.arange(M), 3)
    k = e[:, 0].astype(np.int64) * (F.max() + 1) + e[:, 1]
    o = np.argsort(k, kind="stable"); ks, fs = k[o], fid[o]
    same = ks[1:] == ks[:-1]
    a, b = fs[:-1][same], fs[1:][same]   # chain consecutive faces sharing the edge
    g = sp.coo_matrix((np.ones(len(a)), (a, b)), shape=(M, M))
    return connected_components(g, directed=False)[1]

def tri_phi(phi, P, grad=False):
    g = (P - ORG) / H; sh = np.array(phi.shape) - 2
    i = np.clip(np.floor(g).astype(int), 0, sh); f = g - i
    x, y, z = f[:, 0], f[:, 1], f[:, 2]
    c = lambda dx, dy, dz: phi[i[:, 0] + dx, i[:, 1] + dy, i[:, 2] + dz].astype(float)
    c000, c100, c010, c110, c001, c101, c011, c111 = [c(a, b, d) for d in (0, 1) for b in (0, 1) for a in (0, 1)]
    v = (c000*(1-x)*(1-y)*(1-z) + c100*x*(1-y)*(1-z) + c010*(1-x)*y*(1-z) + c110*x*y*(1-z)
         + c001*(1-x)*(1-y)*z + c101*x*(1-y)*z + c011*(1-x)*y*z + c111*x*y*z)
    if not grad: return v
    gx = ((c100-c000)*(1-y)*(1-z) + (c110-c010)*y*(1-z) + (c101-c001)*(1-y)*z + (c111-c011)*y*z) / H
    gy = ((c010-c000)*(1-x)*(1-z) + (c110-c100)*x*(1-z) + (c011-c001)*(1-x)*z + (c111-c101)*x*z) / H
    gz = ((c001-c000)*(1-x)*(1-y) + (c101-c100)*x*(1-y) + (c011-c010)*(1-x)*y + (c111-c110)*x*y) / H
    return v, np.stack([gx, gy, gz], 1)

def gates(V, F, phi):
    """V,F: unmerged coords (float64 values) and faces; merged exactly inside."""
    Vm, Fm = merge(V, F); r = {}
    N = len(Vm); M = len(Fm)
    rep = (Fm[:, 0] == Fm[:, 1]) | (Fm[:, 1] == Fm[:, 2]) | (Fm[:, 2] == Fm[:, 0])
    de = np.concatenate([Fm[:, [0, 1]], Fm[:, [1, 2]], Fm[:, [2, 0]]])
    kd = de[:, 0].astype(np.int64) * N + de[:, 1]
    ud, cd = np.unique(kd, return_counts=True)
    ue = np.sort(de, 1); ku = ue[:, 0].astype(np.int64) * N + ue[:, 1]
    uu, cu = np.unique(ku, return_counts=True)
    r["watertight"] = bool(np.all(cu == 2))
    rev = (ud % N) * N + ud // N
    r["winding_consistent"] = bool(np.all(cd == 1) and np.all(np.isin(rev, ud)))
    r["edge_manifold"] = bool(np.all(cu == 2))
    r["n_boundary_edges"] = int((cu == 1).sum()); r["n_nonmanifold_edges"] = int((cu > 2).sum())
    # vertex link: link edge (a,b) at v for each corner
    cv = np.concatenate([Fm[:, 0], Fm[:, 1], Fm[:, 2]])
    ca = np.concatenate([Fm[:, 1], Fm[:, 2], Fm[:, 0]]); cb = np.concatenate([Fm[:, 2], Fm[:, 0], Fm[:, 1]])
    na = cv.astype(np.int64) * N + ca; nb = cv.astype(np.int64) * N + cb
    nodes, inv = np.unique(np.concatenate([na, nb]), return_inverse=True)
    ia, ib = inv[:len(na)], inv[len(na):]
    deg = np.bincount(ia, minlength=len(nodes)) + np.bincount(ib, minlength=len(nodes))
    g = sp.coo_matrix((np.ones(len(ia)), (ia, ib)), shape=(len(nodes),) * 2)
    _, lab = connected_components(g, directed=False)
    nv = nodes // N
    # components per vertex: unique (vertex, label) pairs
    pairs = np.unique(np.stack([nv, lab], 1), axis=0)
    ncomp = np.bincount(pairs[:, 0], minlength=N)
    used = np.unique(cv)
    r["vertex_link_manifold"] = bool(np.all(deg == 2) and np.all(ncomp[used] == 1))
    r["n_bad_link_vertices"] = int(len(np.unique(nv[deg != 2])) + (ncomp[used] != 1).sum())
    srt = np.sort(Fm, 1); r["n_duplicate_faces"] = int(M - len(np.unique(srt, axis=0)))
    r["n_repeated_index_faces"] = int(rep.sum())
    p0, p1, p2 = Vm[Fm[:, 0]], Vm[Fm[:, 1]], Vm[Fm[:, 2]]
    cr = np.cross(p1 - p0, p2 - p0); area2 = np.linalg.norm(cr, axis=1)
    r["n_zero_area_faces"] = int((np.all(cr == 0, 1)).sum())
    r["no_dup_repeated_zero"] = bool(r["n_duplicate_faces"] == 0 and r["n_repeated_index_faces"] == 0 and r["n_zero_area_faces"] == 0)
    sv = float(np.sum(np.einsum("ij,ij->i", p0, np.cross(p1, p2))) / 6); r["signed_volume"] = sv
    r["positive_volume"] = sv > 0
    lo, hi = Vm[np.unique(Fm)].min(0), Vm[np.unique(Fm)].max(0)
    cl = float(min((lo - LO).min(), (HI - hi).min())); r["clearance_m"] = cl; r["clearance_ok"] = cl >= 0.25
    # orientation
    comp = edge_components(Fm); ncp = comp.max() + 1; r["n_components"] = int(ncp)
    with np.errstate(all="ignore"):
        n = cr / area2[:, None]
    cen = (p0 + p1 + p2) / 3; area = area2 / 2
    comps = []; allout = True
    for c in range(ncp):
        s = comp == c; out_ok = True; rec = {"faces": int(s.sum()), "area": float(area[s].sum())}
        for d in (0.02, 0.05, 0.1):
            dl = d * H
            pp = tri_phi(phi, cen[s] + dl * n[s]); pm = tri_phi(phi, cen[s] - dl * n[s])
            w = area[s]; W = w.sum()
            fo = w[(pp > TOL) & (pm < -TOL)].sum() / W; fi = w[(pp < -TOL) & (pm > TOL)].sum() / W
            rec[f"out_{d}"] = float(fo); rec[f"in_{d}"] = float(fi)
            out_ok &= bool(fo > 0.5)
        rec["outward"] = out_ok; allout &= out_ok; comps.append(rec)
    r["components_orientation"] = comps; r["orientation_all_outward"] = bool(allout)
    r["PASS_all"] = bool(all(r[k] for k in ["watertight", "winding_consistent", "edge_manifold", "vertex_link_manifold",
                          "no_dup_repeated_zero", "positive_volume", "clearance_ok", "orientation_all_outward"]))
    return r

res = {}
for cs in CASES:
    p = prereg["inputs"][cs]
    for k in ("state", "surface"):
        h = sha(open(R + p[k], "rb").read())
        if h != p[k + "_sha256"]: sys.exit(f"SHA MISMATCH {cs} {k}")
    d = np.load(R + p["surface"]); V = np.asarray(d["vertices"], float); F = np.asarray(d["faces"]).astype(np.int64)
    phi = np.load(R + p["state"])["phi"]; assert phi.shape == (121, 65, 49)
    Vm, Fm = merge(V, F)  # merged for components only
    comp = edge_components(Fm); ncp = comp.max() + 1
    P = V[F]  # (M,3,3) original coords
    fmin, fmax = P.min(1), P.max(1)
    o = np.argsort(comp, kind="stable"); cs_ = comp[o]; st = np.r_[0, np.flatnonzero(np.diff(cs_)) + 1]
    cmin = np.minimum.reduceat(fmin[o], st); cmax = np.maximum.reduceat(fmax[o], st)
    cnt = np.diff(np.r_[st, len(o)]); diag = np.linalg.norm(cmax - cmin, axis=2 - 1)
    tv = np.einsum("ij,ij->i", P[:, 0], np.cross(P[:, 1], P[:, 2])) / 6
    cvol = np.bincount(comp, weights=tv, minlength=ncp)[cs_[st]]
    rem = diag < H; rem_set = cs_[st][rem]
    removed = [{"faces": int(cnt[i]), "bbox_diag_m": float(diag[i]), "signed_volume_m3": float(cvol[i]),
                "bbox_center": ((cmin[i] + cmax[i]) / 2).tolist()} for i in np.flatnonzero(rem)]
    keep = ~np.isin(comp, rem_set); Fk = F[keep]
    # STL
    Pk = V[Fk]; cr = np.cross(Pk[:, 1] - Pk[:, 0], Pk[:, 2] - Pk[:, 0])
    with np.errstate(all="ignore"): nn = cr / np.linalg.norm(cr, axis=1)[:, None]
    dt = np.dtype([("n", "<f4", 3), ("v", "<f4", (3, 3)), ("a", "<u2")]); assert dt.itemsize == 50
    rec = np.zeros(len(Fk), dt); rec["n"] = nn.astype("<f4"); rec["v"] = Pk.astype("<f4")
    blob = bytes(80) + np.uint32(len(Fk)).tobytes() + rec.tobytes()
    open(OUT + f"{cs}.stl", "wb").write(blob)
    # read back
    cntb = int(np.frombuffer(blob[80:84], "<u4")[0]); rb = np.frombuffer(blob[84:], dt, count=cntb)
    V32 = rb["v"].reshape(-1, 3).astype(float); F32 = np.arange(len(V32)).reshape(-1, 3)
    gd = gates(Vm[np.unique(Fm[keep])] if False else V, Fk, phi)  # double kept surface
    g32 = gates(V32, F32, phi)
    # descriptive
    vk = V[np.unique(Fk)]; ph, gr = tri_phi(phi, vk, True)
    with np.errstate(all="ignore"): dist = np.abs(ph) / np.linalg.norm(gr, axis=1)
    desc = {"median": float(np.nanmedian(dist)), "p99": float(np.nanpercentile(dist, 99)), "max": float(np.nanmax(dist)),
            "frac_gt_0.5mm": float(np.mean(dist > 0.0005)), "n_nan": int(np.isnan(dist).sum()), "n_kept_vertices": len(vk)}
    pts = P.reshape(-1, 3); outside = int((((pts - ORG) / H < 0) | ((pts - ORG) / H > np.array(phi.shape) - 1)).any(1).sum())
    res[cs] = {"faces_in": int(len(F)), "faces_kept": int(len(Fk)), "n_components_input": int(ncp), "removed": removed,
               "double": gd, "float32": g32, "stl_sha256": sha(blob), "stl_bytes": len(blob), "distance_desc": desc,
               "pts_outside_phi_grid": outside}
    print(cs, len(Fk), len(removed), "dbl", gd["PASS_all"], "f32", g32["PASS_all"], res[cs]["stl_sha256"], flush=True)
json.dump(res, open(OUT + "independent_result.json", "w"), indent=1)
