"""Round3 original-trilinear distance certificates and surface correspondence."""

from itertools import product
import numpy as np
from scipy.interpolate import RegularGridInterpolator
from scipy.special import roots_legendre
import trimesh

BARY = np.array(
    [(i / 3, j / 3, (3 - i - j) / 3) for i in range(4) for j in range(4 - i)]
)
LIMIT = 0.0005


class Field:
    def __init__(self, phi, origin, h):
        self.phi = np.asarray(phi)
        self.o = np.asarray(origin)
        self.h = float(h)
        self.axes = tuple(
            self.o[a] + self.h * np.arange(phi.shape[a]) for a in range(3)
        )
        self.hi = np.array([a[-1] for a in self.axes])
        self.f = RegularGridInterpolator(self.axes, self.phi, bounds_error=True)
        self.L = float(
            np.hypot.reduce(
                [
                    np.abs(np.diff(phi.astype(float), axis=a)).max()
                    / np.diff(self.axes[a]).min()
                    for a in range(3)
                ]
            )
        ) * (1 + 64 * np.finfo(float).eps)

    def value_error_grad(self, p, grad=False):
        cell = np.column_stack(
            [
                np.clip(
                    np.searchsorted(self.axes[a], p[:, a], side="right") - 1,
                    0,
                    len(self.axes[a]) - 2,
                )
                for a in range(3)
            ]
        )
        lower = np.column_stack([self.axes[a][cell[:, a]] for a in range(3)])
        widths = np.column_stack(
            [self.axes[a][cell[:, a] + 1] - self.axes[a][cell[:, a]] for a in range(3)]
        )
        t = (p - lower) / widths
        absolute = np.zeros(len(p))
        g = np.zeros_like(p)
        for b in product((0, 1), repeat=3):
            vals = self.phi[tuple((cell + np.array(b)).T)].astype(float)
            weights = np.ones(len(p))
            for a in range(3):
                weights *= t[:, a] if b[a] else 1 - t[:, a]
            absolute += np.abs(weights * vals)
            if grad:
                for a in range(3):
                    w = np.ones(len(p)) * (1 if b[a] else -1) / widths[:, a]
                    for j in range(3):
                        if a != j:
                            w *= t[:, j] if b[j] else 1 - t[:, j]
                    g[:, a] += w * vals
        return self.f(p), 64 * np.finfo(float).eps * absolute, g


def axis_witness(field, points, base, best):
    h = field.h
    for axis in range(3):
        idx = np.floor((base[:, axis] - field.o[axis]) / h)
        node = np.sort(
            np.clip(
                np.stack(
                    (
                        base[:, axis] - h,
                        field.o[axis] + idx * h,
                        field.o[axis] + (idx + 1) * h,
                        base[:, axis] + h,
                    ),
                    axis=1,
                ),
                field.o[axis],
                field.hi[axis],
            ),
            axis=1,
        )
        probes = np.repeat(base[:, None, :], 4, axis=1)
        probes[:, :, axis] = node
        val, err, _ = field.value_error_grad(probes.reshape(-1, 3))
        val = val.reshape(-1, 4)
        err = err.reshape(-1, 4)
        for k in range(3):
            a = val[:, k]
            b = val[:, k + 1]
            ea = err[:, k]
            eb = err[:, k + 1]
            crossing = ((a - ea > 0) & (b + eb < 0)) | ((a + ea < 0) & (b - eb > 0))
            ratios = []
            for sa, sb in product((-1, 1), repeat=2):
                av = a + sa * ea
                bv = b + sb * eb
                ratios.append(
                    np.divide(av, av - bv, out=np.zeros_like(a), where=av != bv)
                )
            fractions = np.clip(np.stack(ratios), 0, 1)
            low = fractions.min(0)
            high = fractions.max(0)
            x = probes[:, k]
            d = probes[:, k + 1] - x
            bound = (
                np.maximum(
                    np.linalg.norm(x + low[:, None] * d - points, axis=1),
                    np.linalg.norm(x + high[:, None] * d - points, axis=1),
                )
                + h * 1e-9
            )
            best = np.minimum(best, np.where(crossing, bound, np.inf))
            for j in (k, k + 1):
                structural = (val[:, j] == 0) & (err[:, j] == 0)
                best = np.minimum(
                    best,
                    np.where(
                        structural,
                        np.linalg.norm(probes[:, j] - points, axis=1) + h * 1e-9,
                        np.inf,
                    ),
                )
    return best


def distance(v, f, phi, o, h):
    field = Field(phi, o, h)
    rows = []
    unresolved = 0
    maximum_lower = 0.0
    maximum_upper = 0.0
    exceeds_samples = 0
    for start in range(0, len(f), 5000):
        chunk = f[start : start + 5000]
        points = np.einsum("bk,fkj->fbj", BARY, v[chunk]).reshape(-1, 3)
        value, error, _ = field.value_error_grad(points)
        lower = np.maximum(np.abs(value) - error, 0) / max(
            field.L, np.finfo(float).tiny
        )
        center = points.copy()
        best = axis_witness(field, points, points, np.full(len(points), np.inf))
        for _ in range(20):
            ids = np.flatnonzero(best > LIMIT)
            if not len(ids):
                break
            val, _, g = field.value_error_grad(center[ids], True)
            denom = np.einsum("ij,ij->i", g, g)
            step = val[:, None] * g / np.maximum(denom[:, None], 1e-300)
            length = np.linalg.norm(step, axis=1)
            step *= np.minimum(1, h / np.maximum(length, 1e-300))[:, None]
            center[ids] = np.clip(center[ids] - step, field.o, field.hi)
            best[ids] = axis_witness(field, points[ids], center[ids], best[ids])
        upper_face = best.reshape(len(chunk), 10).max(1)
        lower_face = lower.reshape(len(chunk), 10).max(1)
        unknown = (~np.isfinite(best)).reshape(len(chunk), 10).sum(1)
        rows.append(np.column_stack((upper_face, lower_face, unknown)))
        unresolved += int(unknown.sum())
        maximum_lower = max(maximum_lower, float(lower.max()))
        finite = best[np.isfinite(best)]
        if len(finite):
            maximum_upper = max(maximum_upper, float(finite.max()))
        exceeds_samples += int((lower > LIMIT).sum())
    array = np.vstack(rows)
    summary = {
        "sample_count": 10 * len(f),
        "unresolved_sample_count": unresolved,
        "maximum_certified_upper_distance_m": maximum_upper,
        "maximum_certified_lower_distance_m": maximum_lower,
        "certified_exceeds_limit": maximum_lower > LIMIT,
        "within_limit": unresolved == 0
        and maximum_upper <= LIMIT
        and maximum_lower <= LIMIT,
        "sample_count_certified_over_limit": exceeds_samples,
        "triangle_count_without_certificate": int((array[:, 0] > LIMIT).sum()),
        "triangle_count_certified_over_limit": int((array[:, 1] > LIMIT).sum()),
        "per_triangle_bounds_columns": [
            "maximum_upper_m",
            "maximum_lower_m",
            "unresolved_samples",
        ],
        "scope": "10 fixed triangle samples, numerically guarded interval root witnesses; no continuous Hausdorff claim",
    }
    return summary, array


def volume(phi, o, h, n):
    corners = np.stack(
        [
            phi[
                i : phi.shape[0] - 1 + i,
                j : phi.shape[1] - 1 + j,
                k : phi.shape[2] - 1 + k,
            ]
            for i, j, k in product((0, 1), repeat=3)
        ],
        axis=-1,
    ).astype(float)
    low = corners.min(-1)
    high = corners.max(-1)
    active = np.argwhere((low <= 0) & (high >= 0))
    total = float((high < 0).sum())
    ab, w = roots_legendre(n)
    ab = (ab + 1) / 2
    w = w / 2
    uv = np.array(list(product(ab, repeat=2)))
    quadrature = np.outer(w, w).ravel()
    weights = np.stack(
        [
            (uv[:, 0] if a else 1 - uv[:, 0]) * (uv[:, 1] if b else 1 - uv[:, 1])
            for a, b in product((0, 1), repeat=2)
        ],
        axis=1,
    )
    for start in range(0, len(active), 128):
        vals = corners[tuple(active[start : start + 128].T)]
        a = vals[:, [0, 2, 4, 6]] @ weights.T
        b = vals[:, [1, 3, 5, 7]] @ weights.T
        frac = np.zeros_like(a)
        frac[(a < 0) & (b < 0)] = 1
        cross = (a < 0) != (b < 0)
        root = np.divide(a, a - b, out=np.zeros_like(a), where=a != b)
        frac[cross] = np.where(a < 0, root, 1 - root)[cross]
        total += float((frac @ quadrature).sum())
    return total * h**3


def line_roots(field, point, normal, span):
    # Exact cubic on each original cell segment of the normal ray.
    breaks = [-span, span]
    for a in range(3):
        if abs(normal[a]) < 64 * np.finfo(float).eps:
            continue
        cuts = (field.axes[a] - point[a]) / normal[a]
        breaks.extend(cuts[(cuts > -span) & (cuts < span)])
    breaks = np.unique(breaks)
    roots = []
    zero_interval = False
    fractions = np.array([0, 1 / 3, 2 / 3, 1])
    vand = np.polynomial.polynomial.polyvander(fractions, 3)
    for lo, hi in zip(breaks[:-1], breaks[1:]):
        probes = point + (lo + (hi - lo) * fractions)[:, None] * normal
        if np.any(probes < field.o) or np.any(probes > field.hi):
            continue
        values = field.f(probes)
        coeff = np.linalg.solve(vand, values)
        if np.all(values == 0):
            zero_interval = True
            continue
        for root in np.polynomial.polynomial.polyroots(coeff):
            if abs(root.imag) > 1e-9 or root.real < -1e-9 or root.real > 1 + 1e-9:
                continue
            t = lo + (hi - lo) * np.clip(root.real, 0, 1)
            res = abs(float(field.f((point + t * normal)[None, :])[0]))
            if res <= field.h * 1e-10:
                roots.append(t)
    roots = sorted(roots)
    unique = []
    for t in roots:
        if not unique or abs(t - unique[-1]) > field.h * 1e-9:
            unique.append(float(t))
    if not unique or zero_interval:
        return None, {"zero_interval": zero_interval, "roots_m": unique}
    order = np.argsort(np.abs(unique))
    first = unique[order[0]]
    tied = len(unique) > 1 and abs(abs(first) - abs(unique[order[1]])) <= field.h * 1e-9
    guard = field.h * 1e-8
    positions = point + np.array([first - guard, first + guard])[:, None] * normal
    if np.any(positions < field.o) or np.any(positions > field.hi):
        return None, {
            "roots_m": unique,
            "reason": "root certificate outside source grid",
        }
    value, error, _ = field.value_error_grad(positions)
    crossed = bool(
        ((value[0] - error[0] > 0) & (value[1] + error[1] < 0))
        | ((value[0] + error[0] < 0) & (value[1] - error[1] > 0))
    )
    valid = not tied and crossed
    return first if valid else None, {
        "zero_interval": False,
        "roots_m": unique,
        "nearest_absolute_root_tied": tied,
        "crossing_certificate": crossed,
        "root_position_uncertainty_m": guard,
    }


def mesh_hits(v, f, points, normals, span):
    mesh = trimesh.Trimesh(v, f, process=False)
    locations, ray_ids, _ = mesh.ray.intersects_location(
        points - span * normals, normals, multiple_hits=True
    )
    values = np.einsum("ij,ij->i", locations - points[ray_ids], normals[ray_ids])
    groups = [[] for _ in points]
    for ray, t in zip(ray_ids, values):
        if abs(t) <= span:
            groups[int(ray)].append(float(t))
    results = []
    for hits in groups:
        hits = sorted(hits)
        unique = []
        for t in hits:
            if not unique or abs(t - unique[-1]) > 2.5e-11:
                unique.append(t)
        order = np.argsort(np.abs(unique))
        if not len(order) or (
            len(order) > 1
            and abs(abs(unique[order[0]]) - abs(unique[order[1]])) <= 2.5e-11
        ):
            results.append(np.nan)
        else:
            results.append(unique[order[0]])
    return np.array(results)


def fidelity(base_v, base_f, target_v, target_f, base_phi, target_phi, o, h):
    # Area-stratified centroid surface samples; no target-informed choice.
    triangles = base_v[base_f]
    areas = (
        np.linalg.norm(
            np.cross(
                triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0]
            ),
            axis=1,
        )
        / 2
    )
    cdf = np.cumsum(areas)
    face_ids = np.unique(np.searchsorted(cdf, (np.arange(1024) + 0.5) / 1024 * cdf[-1]))
    points = triangles[face_ids].mean(1)
    base = Field(base_phi, o, h)
    target = Field(target_phi, o, h)
    _, _, grad = base.value_error_grad(points, True)
    length = np.linalg.norm(grad, axis=1)
    normals = grad / np.maximum(length[:, None], 1e-300)
    sdf_delta = np.full(len(points), np.nan)
    details = []
    for i, (p, n) in enumerate(zip(points, normals)):
        if length[i] <= 64 * np.finfo(float).eps:
            details.append({"reason": "gradient normal undefined"})
            continue
        a, da = line_roots(base, p, n, 2 * h)
        b, db = line_roots(target, p, n, 2 * h)
        if a is not None and b is not None:
            sdf_delta[i] = b - a
        details.append(
            {"baseline": da, "target": db, "baseline_root_m": a, "target_root_m": b}
        )
    mesh_delta = np.full(len(points), np.nan)
    nonzero = length > 64 * np.finfo(float).eps
    if nonzero.any():
        mesh_delta[nonzero] = mesh_hits(
            target_v, target_f, points[nonzero], normals[nonzero], 2 * h
        )
    error = np.abs(mesh_delta - sdf_delta) + 2 * h * 1e-8 + h * 1e-9
    valid = np.isfinite(error)
    maximum = float(error[valid].max()) if valid.any() else None
    return {
        "sample_count": len(points),
        "unresolved_samples": int((~valid).sum()),
        "maximum_normal_displacement_difference_m": maximum,
        "within_limit": bool(valid.all() and maximum is not None and maximum <= LIMIT),
        "tolerance_m": LIMIT,
        "baseline_face_ids": face_ids.tolist(),
        "surface_correspondence": "baseline triangle centroids area-stratified; original baseline grad-phi ray normal; nearest unique root in +/-2h; mesh baseline ray displacement is zero",
        "root_diagnostics": details,
    }, np.column_stack((points, normals, sdf_delta, mesh_delta, error))
