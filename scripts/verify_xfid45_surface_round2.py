#!/usr/bin/env python3
"""Independent stored-surface verifier; never imports any extractor/metrics."""

import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
import numpy as np
from scipy.interpolate import RegularGridInterpolator
import trimesh

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/evidence/xfid45_surface_round2_2026_10_03"


def inspect_mesh(vertices, faces):
    vertices, back = np.unique(vertices, axis=0, return_inverse=True)
    faces = back[faces]
    mesh = trimesh.Trimesh(vertices, faces, process=False)
    incidence = Counter()
    links = defaultdict(list)
    for a, b, c in faces:
        for u, v in ((a, b), (b, c), (c, a)):
            incidence[tuple(sorted((int(u), int(v))))] += 1
        for u, v, w in ((a, b, c), (b, c, a), (c, a, b)):
            links[int(u)].append((int(v), int(w)))
    invalid = 0
    for link in links.values():
        g = defaultdict(list)
        for a, b in link:
            g[a].append(b)
            g[b].append(a)
        visited = set()
        todo = [next(iter(g))]
        while todo:
            a = todo.pop()
            if a not in visited:
                visited.add(a)
                todo.extend(g[a])
        invalid += int(
            len(visited) != len(g)
            or any(len(neighbors) != 2 for neighbors in g.values())
        )
    return {
        "watertight": bool(mesh.is_watertight),
        "winding_consistent": bool(mesh.is_winding_consistent),
        "nonmanifold_edges": sum(c != 2 for c in incidence.values()),
        "nonmanifold_vertex_links": invalid,
        "duplicate_faces": len(faces)
        - len({tuple(sorted(map(int, f))) for f in faces}),
        "zero_area_faces": int((mesh.area_faces == 0).sum()),
        "signed_volume_m3": float(mesh.volume),
        "area_m2": float(mesh.area),
        "clearance_m": float(
            np.minimum(
                mesh.bounds[0] - np.array([-2.5, -1.2, -0.9]),
                np.array([2.5, 1.2, 0.9]) - mesh.bounds[1],
            ).min()
        ),
    }, mesh


def independent_identity(v, f, phi, origin, h):
    """Different projection: finite-difference Newton + exact axis root witness."""
    bary = np.array(
        [(i / 3, j / 3, (3 - i - j) / 3) for i in range(4) for j in range(4 - i)]
    )
    points = np.concatenate(
        [
            ((b[0] * v[f[:, 0]]) + (b[1] * v[f[:, 1]]) + (b[2] * v[f[:, 2]]))[
                :, None, :
            ]
            for b in bary
        ],
        axis=1,
    ).reshape(-1, 3)
    axes = tuple(origin[a] + h * np.arange(phi.shape[a]) for a in range(3))
    func = RegularGridInterpolator(axes, phi, bounds_error=True)
    lo = origin
    hi = origin + h * (np.array(phi.shape) - 1)
    center = points.copy()
    for _ in range(20):
        value = func(center)
        derivative = []
        for a in range(3):
            left = center.copy()
            right = center.copy()
            left[:, a] = np.maximum(lo[a], center[:, a] - h * 1e-5)
            right[:, a] = np.minimum(hi[a], center[:, a] + h * 1e-5)
            derivative.append((func(right) - func(left)) / (right[:, a] - left[:, a]))
        g = np.stack(derivative, axis=1)
        step = value[:, None] * g / np.maximum((g * g).sum(1)[:, None], 1e-30)
        step *= np.minimum(1, h / np.maximum(np.linalg.norm(step, axis=1), 1e-30))[
            :, None
        ]
        center = np.clip(center - step, lo, hi)
    distance = np.full(len(points), np.inf)
    for base in (points, center):
        for axis in range(3):
            cell = np.floor((base[:, axis] - origin[axis]) / h)
            nodes = np.sort(
                np.clip(
                    np.stack(
                        [
                            base[:, axis] - h,
                            origin[axis] + cell * h,
                            origin[axis] + (cell + 1) * h,
                            base[:, axis] + h,
                        ],
                        axis=1,
                    ),
                    lo[axis],
                    hi[axis],
                ),
                axis=1,
            )
            positions = np.broadcast_to(base[:, None, :], (len(base), 4, 3)).copy()
            positions[:, :, axis] = nodes
            values = func(positions.reshape(-1, 3)).reshape(-1, 4)
            for k in range(3):
                a = values[:, k]
                b = values[:, k + 1]
                valid = ((a == 0) | (b == 0) | (np.signbit(a) != np.signbit(b))) & (
                    a != b
                )
                fraction = np.clip(
                    np.divide(a, a - b, out=np.zeros_like(a), where=a != b), 0, 1
                )
                root = positions[:, k] + fraction[:, None] * (
                    positions[:, k + 1] - positions[:, k]
                )
                residual = np.abs(func(root))
                candidate = np.linalg.norm(points - root, axis=1)
                distance = np.minimum(
                    distance,
                    np.where(valid & (residual <= h * 1e-10), candidate, np.inf),
                )
        exact = func(base) == 0
        distance = np.minimum(
            distance, np.where(exact, np.linalg.norm(base - points, axis=1), np.inf)
        )
    lipschitz = np.hypot.reduce(
        [np.abs(np.diff(phi.astype(float), axis=a)).max() / h for a in range(3)]
    )
    lower = np.abs(func(points)) / max(float(lipschitz), np.finfo(float).tiny)
    return {
        "within_displacement_limit": bool(
            np.all(distance <= 0.0005) and lower.max() <= 0.0005
        ),
        "maximum_certified_upper_distance_m": float(
            distance[np.isfinite(distance)].max()
        )
        if np.isfinite(distance).any()
        else None,
        "maximum_lipschitz_lower_distance_m": float(lower.max()),
        "unresolved_sample_count": int(np.count_nonzero(~np.isfinite(distance))),
        "certified_exceeds_limit": bool(lower.max() > 0.0005),
        "sample_count": len(points),
    }


def independent_orientation(mesh, phi, o, h):
    interp = RegularGridInterpolator(
        tuple(o[a] + h * np.arange(phi.shape[a]) for a in range(3)), phi
    )
    out = []
    tol = 64 * np.finfo(float).eps * h
    groups = trimesh.graph.connected_components(
        mesh.face_adjacency, nodes=np.arange(len(mesh.faces)), min_len=1
    )
    for ids in groups:
        part = trimesh.Trimesh(mesh.vertices, mesh.faces[ids], process=False)
        weights = part.area_faces
        total = weights.sum()
        votes = []
        for fraction in (0.02, 0.05, 0.1):
            plus = interp(part.triangles_center + fraction * h * part.face_normals)
            minus = interp(part.triangles_center - fraction * h * part.face_normals)
            votes.append(
                float(weights[(plus > tol) & (minus < -tol)].sum() / total) > 0.5
            )
        out.append(
            {
                "faces": len(part.faces),
                "outward_at_all_delta": all(votes),
                "boundary": "solid_boundary"
                if part.volume > 0
                else "void_boundary"
                if part.volume < 0
                else "ambiguous",
            }
        )
    return out


def main():
    reg = json.loads((OUT / "preregistration.json").read_text())
    result = json.loads((OUT / "result.json").read_text())
    rows = []
    for row in result["cases"]:
        case = row["case"]
        name = row["candidate"]
        folder = OUT / "surfaces" / name / case
        z = np.load(folder / "surface.npz")
        v = z["vertices"]
        f = z["faces"]
        field_path = ROOT / reg["input_files"][case]["path"]
        state = np.load(field_path)
        meta = json.loads(str(state["metadata"]))
        phi = state["phi"]
        o = np.array(meta["origin_m"])
        h = meta["spacing_m"]
        stats, mesh = inspect_mesh(v, f)
        stl = trimesh.load_mesh(folder / "surface.stl", process=False)
        serialized, stl_mesh = inspect_mesh(stl.vertices, stl.faces)
        identity = independent_identity(v, f, phi, o, h)
        stl_identity = independent_identity(
            np.asarray(stl.vertices), np.asarray(stl.faces), phi, o, h
        )
        ori = independent_orientation(mesh, phi, o, h)
        serialized_ori = independent_orientation(stl_mesh, phi, o, h)
        agreement = all(
            stats[k] == row["statistics"][k]
            for k in (
                "watertight",
                "winding_consistent",
                "nonmanifold_edges",
                "nonmanifold_vertex_links",
                "duplicate_faces",
                "zero_area_faces",
            )
        )
        agreement &= all(
            np.isclose(stats[k], row["statistics"][k], rtol=1e-10, atol=1e-12)
            for k in ("area_m2", "signed_volume_m3", "clearance_m")
        )
        for data, expected in (
            (identity, row["identity"]),
            (stl_identity, row["serialized_identity"]),
        ):
            agreement &= all(
                data[k] == expected[k]
                for k in (
                    "within_displacement_limit",
                    "certified_exceeds_limit",
                    "sample_count",
                )
            )
            agreement &= np.isclose(
                data["maximum_lipschitz_lower_distance_m"],
                expected["maximum_lipschitz_lower_distance_m"],
                atol=1e-12,
            )
        gates = {
            k: all(s[k] for s in (stats, serialized))
            for k in ("watertight", "winding_consistent")
        }
        gates.update(
            {
                k: all(s[k] == 0 for s in (stats, serialized))
                for k in (
                    "nonmanifold_edges",
                    "nonmanifold_vertex_links",
                    "duplicate_faces",
                    "zero_area_faces",
                )
            }
        )
        gates.update(
            positive_volume=stats["signed_volume_m3"] > 0
            and serialized["signed_volume_m3"] > 0,
            clearance=stats["clearance_m"] >= 0.25
            and serialized["clearance_m"] >= 0.25,
            orientation=bool(ori)
            and all(c["outward_at_all_delta"] for c in ori)
            and bool(serialized_ori)
            and all(c["outward_at_all_delta"] for c in serialized_ori),
            identity=identity["within_displacement_limit"]
            and stl_identity["within_displacement_limit"],
            determinism=row["gates"]["determinism"],
        )
        agreement &= gates == row["gates"]
        rows.append(
            {
                "candidate": name,
                "case": case,
                "agreement": bool(agreement),
                "gates": gates,
                "statistics": stats,
                "serialized_statistics": serialized,
                "identity": identity,
                "serialized_identity": stl_identity,
                "orientation": ori,
                "serialized_orientation": serialized_ori,
                "surface_sha256": hashlib.sha256(
                    (folder / "surface.npz").read_bytes()
                ).hexdigest(),
            }
        )
        print(name, case, "agreement", bool(agreement), flush=True)
    report = {
        "evidence_class": "independent_solver_free_stored_surface_recomputation",
        "imports_extractor": False,
        "all_agree": all(r["agreement"] for r in rows),
        "cases": rows,
        "qualification_flags": result["qualification_flags"],
    }
    (OUT / "independent_verification.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n"
    )
    if not report["all_agree"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
