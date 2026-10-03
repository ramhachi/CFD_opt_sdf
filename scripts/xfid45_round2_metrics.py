"""Geometry-only measurement helpers; no extraction algorithms."""

from itertools import product
import json
import numpy as np
from scipy.interpolate import RegularGridInterpolator
import trimesh

CASES = (
    "baseline",
    "D0_interface_offset_minus",
    "D0_interface_offset_plus",
    "D1_filtered_seed11_minus",
    "D1_filtered_seed11_plus",
    "D2_filtered_seed2026_minus",
    "D2_filtered_seed2026_plus",
)
BARY = np.array(
    [(i / 3, j / 3, (3 - i - j) / 3) for i in range(4) for j in range(4 - i)]
)
DELTAS = (0.02, 0.05, 0.1)


def load_field(path):
    with np.load(path) as z:
        m = json.loads(str(z["metadata"]))
        return z["phi"].copy(), np.array(m["origin_m"]), float(m["spacing_m"])


def interpolator(phi, o, h):
    return RegularGridInterpolator(
        tuple(o[i] + h * np.arange(phi.shape[i]) for i in range(3)),
        phi,
        bounds_error=True,
    )


def gradient(phi, o, h, p):
    q = (p - o) / h
    cell = np.minimum(np.maximum(np.floor(q).astype(int), 0), np.array(phi.shape) - 2)
    t = q - cell
    g = np.zeros_like(p, dtype=float)
    for b in product((0, 1), repeat=3):
        vals = phi[tuple((cell + np.array(b)).T)]
        for a in range(3):
            w = np.ones(len(p)) * (1 if b[a] else -1) / h
            for d in range(3):
                if d != a:
                    w *= t[:, d] if b[d] else 1 - t[:, d]
            g[:, a] += w * vals
    return g


def components(f):
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components

    e = np.sort(np.concatenate((f[:, [0, 1]], f[:, [1, 2]], f[:, [2, 0]])), axis=1)
    ids = np.tile(np.arange(len(f)), 3)
    order = np.lexsort((e[:, 1], e[:, 0]))
    e = e[order]
    ids = ids[order]
    same = np.all(e[1:] == e[:-1], axis=1)
    a = ids[:-1][same]
    b = ids[1:][same]
    return connected_components(
        coo_matrix((np.ones(len(a)), (a, b)), shape=(len(f), len(f))), directed=False
    )[1]


def sidedness(v, f, phi, o, h):
    p = v[f]
    c = p.mean(1)
    cross = np.cross(p[:, 1] - p[:, 0], p[:, 2] - p[:, 0])
    norm = np.linalg.norm(cross, axis=1)
    keep = norm > 0
    f = f[keep]
    c = c[keep]
    n = cross[keep] / norm[keep, None]
    area = norm[keep] / 2
    labels = components(f)
    interp = interpolator(phi, o, h)
    votes = []
    tol = 64 * np.finfo(float).eps * h
    for delta in DELTAS:
        plus = interp(c + delta * h * n)
        minus = interp(c - delta * h * n)
        votes.append(
            np.where(
                (plus > tol) & (minus < -tol),
                1,
                np.where((plus < -tol) & (minus > tol), -1, 0),
            )
        )
    dot = np.einsum("ij,ij->i", n, gradient(phi, o, h, c))
    out = []
    for k in np.unique(labels):
        sel = labels == k
        total = area[sel].sum()
        fractions = []
        polar = []
        for vote in votes:
            fractions.append(
                {
                    str(s): float(area[sel & (vote == s)].sum() / total)
                    for s in (-1, 0, 1)
                }
            )
            polar.append(
                1
                if fractions[-1]["1"] > 0.5
                else -1
                if fractions[-1]["-1"] > 0.5
                else 0
            )
        stable = len(set(polar)) == 1 and polar[0] != 0
        vol = float(
            np.einsum(
                "ij,ij->i", v[f[sel, 0]], np.cross(v[f[sel, 1]], v[f[sel, 2]])
            ).sum()
            / 6
        )
        oriented = vol * polar[0] if stable else None
        out.append(
            {
                "component": int(k),
                "faces": int(sel.sum()),
                "area_m2": float(total),
                "delta_area_fractions": fractions,
                "delta_polarity": polar,
                "delta_invariant": stable,
                "raw_signed_volume_m3": vol,
                "oriented_signed_volume_m3": oriented,
                "boundary_classification": "solid_boundary"
                if oriented and oriented > 0
                else "void_boundary"
                if oriented and oriented < 0
                else "ambiguous",
                "gradient_dot_positive": int((dot[sel] > tol).sum()),
                "gradient_dot_negative": int((dot[sel] < -tol).sum()),
            }
        )
    return out


def mesh_stats(v, f):
    # Exact coordinate identity is measured again after serialization.
    v, inv = np.unique(v, axis=0, return_inverse=True)
    f = inv[f]
    mesh = trimesh.Trimesh(v, f, process=False)
    edges = np.sort(np.concatenate((f[:, [0, 1]], f[:, [1, 2]], f[:, [2, 0]])), axis=1)
    unique, counts = np.unique(edges, axis=0, return_counts=True)
    dup = len(f) - len(np.unique(np.sort(f, axis=1), axis=0))
    deg = (
        np.linalg.norm(
            np.cross(v[f[:, 1]] - v[f[:, 0]], v[f[:, 2]] - v[f[:, 0]]), axis=1
        )
        == 0
    )
    # The link of every vertex of a closed 2-manifold is one cycle.
    links = [[] for _ in v]
    for a, b, c in f:
        links[a].append((int(b), int(c)))
        links[b].append((int(c), int(a)))
        links[c].append((int(a), int(b)))
    bad = 0
    for link in links:
        if not link:
            continue
        adj = {}
        for a, b in link:
            adj.setdefault(a, []).append(b)
            adj.setdefault(b, []).append(a)
        seen = set()
        stack = [next(iter(adj))]
        while stack:
            a = stack.pop()
            if a not in seen:
                seen.add(a)
                stack.extend(adj[a])
        bad += int(len(seen) != len(adj) or any(len(x) != 2 for x in adj.values()))
    bounds = mesh.bounds
    clearance = float(
        np.minimum(bounds[0] - [-2.5, -1.2, -0.9], [2.5, 1.2, 0.9] - bounds[1]).min()
    )
    return {
        "vertices": len(v),
        "faces": len(f),
        "components": len(np.unique(components(f))),
        "euler": len(np.unique(f)) - len(unique) + len(f),
        "area_m2": float(mesh.area),
        "signed_volume_m3": float(mesh.volume),
        "unsigned_volume_m3": abs(float(mesh.volume)) if mesh.is_watertight else None,
        "watertight": bool(mesh.is_watertight),
        "winding_consistent": bool(mesh.is_winding_consistent),
        "nonmanifold_edges": int((counts != 2).sum()),
        "nonmanifold_vertex_links": bad,
        "duplicate_faces": dup,
        "zero_area_faces": int(deg.sum()),
        "bounds_m": bounds.tolist(),
        "clearance_m": clearance,
    }


def displacement(v, f, phi, o, h):
    """Sampled upper distance certificates to exact piecewise-linear axis roots.

    Newton only finds a nearby search center; final witnesses are roots of the
    original trilinear field along axis segments. No vertices are changed.
    This certifies fixed samples, not a continuous surface Hausdorff bound.
    """
    pts = np.einsum("bk,fkj->fbj", BARY, v[f]).reshape(-1, 3)
    interp = interpolator(phi, o, h)
    hi = o + h * (np.array(phi.shape) - 1)
    center = pts.copy()
    for _ in range(20):
        val = interp(center)
        g = gradient(phi, o, h, center)
        denom = np.einsum("ij,ij->i", g, g)
        step = val[:, None] * g / np.maximum(denom[:, None], 1e-30)
        norm = np.linalg.norm(step, axis=1)
        step *= np.minimum(1, h / np.maximum(norm, 1e-30))[:, None]
        center = np.clip(center - step, o, hi)
    best = np.full(len(pts), np.inf)
    witnesses = np.zeros_like(pts)
    # Search both original points and projected centers; four axis intervals.
    for base in (pts, center):
        for axis in range(3):
            idx = np.floor((base[:, axis] - o[axis]) / h)
            coordinates = np.stack(
                (
                    base[:, axis] - h,
                    o[axis] + idx * h,
                    o[axis] + (idx + 1) * h,
                    base[:, axis] + h,
                ),
                axis=1,
            )
            coordinates = np.sort(np.clip(coordinates, o[axis], hi[axis]), axis=1)
            samples = np.repeat(base[:, None, :], 4, axis=1)
            samples[:, :, axis] = coordinates
            vals = interp(samples.reshape(-1, 3)).reshape(-1, 4)
            for j in range(3):
                a = vals[:, j]
                b = vals[:, j + 1]
                crosses = ((a == 0) | (b == 0) | (np.signbit(a) != np.signbit(b))) & (
                    a != b
                )
                t = np.clip(
                    np.divide(a, a - b, out=np.zeros_like(a), where=a != b), 0, 1
                )
                root = samples[:, j] + t[:, None] * (samples[:, j + 1] - samples[:, j])
                residual = np.abs(interp(root))
                dist = np.linalg.norm(root - pts, axis=1)
                take = crosses & (residual <= h * 1e-10) & (dist < best)
                best[take] = dist[take]
                witnesses[take] = root[take]
        exact = np.abs(interp(base)) <= h * 1e-12
        # Approximate Newton zeros alone are never distance witnesses.
        exact &= interp(base) == 0
        dist = np.linalg.norm(base - pts, axis=1)
        take = exact & (dist < best)
        best[take] = dist[take]
        witnesses[take] = base[take]
    # Global Lipschitz constant from maxima of bilinear derivative corner values.
    maxima = np.array(
        [np.abs(np.diff(phi.astype(float), axis=a)).max() / h for a in range(3)]
    )
    lower = np.abs(interp(pts)) / max(
        float(np.hypot.reduce(maxima)), np.finfo(float).tiny
    )
    worst = int(np.argmax(best))
    finite = np.isfinite(best)
    return {
        "sample_count": len(pts),
        "sample_barycentric": BARY.tolist(),
        "unresolved_sample_count": int((~finite).sum()),
        "maximum_certified_upper_distance_m": float(best[finite].max())
        if finite.any()
        else None,
        "maximum_lipschitz_lower_distance_m": float(lower.max()),
        "within_displacement_limit": bool(
            finite.all() and best.max() <= 0.0005 and lower.max() <= 0.0005
        ),
        "certified_exceeds_limit": bool(lower.max() > 0.0005),
        "worst_sample_m": pts[worst].tolist(),
        "worst_witness_m": witnesses[worst].tolist(),
        "scope": "fixed triangle samples; no continuous Hausdorff claim",
    }, np.stack((best, lower), axis=1).reshape(len(f), len(BARY), 2)
