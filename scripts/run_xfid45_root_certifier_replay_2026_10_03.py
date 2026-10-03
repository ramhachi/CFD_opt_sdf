#!/usr/bin/env python3
"""Fresh solver-free replay of saved #45 Round 3 surfaces under CERT-01."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import time

import numpy as np
import trimesh

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import verify_xfid45_round3 as frozen_independent  # noqa: E402
from scripts import xfid45_round3_measure as frozen_parent  # noqa: E402
from scripts.verify_xfid45_root_certifier_2026_10_03 import (  # noqa: E402
    enumerate_ray_roots as sturm_roots,
    nearest_root as sturm_nearest,
)
from scripts.xfid45_root_certifier_2026_10_03 import (  # noqa: E402
    enumerate_ray_roots,
    nearest_root,
    position_tolerance,
)

ROUND3 = ROOT / "docs/evidence/xfid45_surface_round3_2026_10_03"
EVIDENCE = ROOT / "docs/evidence/xfid45_root_certifier_2026_10_03"
PREREGISTRATION = EVIDENCE / "preregistration.json"
PREREGISTRATION_AMENDMENT = EVIDENCE / "preregistration_amendment_01.json"
AMENDABLE_SOURCE = "scripts/run_xfid45_root_certifier_replay_2026_10_03.py"
AMENDABLE_TEST = "tests/test_xfid45_root_certifier_2026_10_03.py"
LIMIT_M = 5.0e-4
CASES = (
    "D0_interface_offset_minus",
    "D0_interface_offset_plus",
    "D1_filtered_seed11_minus",
    "D1_filtered_seed11_plus",
    "D2_filtered_seed2026_minus",
    "D2_filtered_seed2026_plus",
    "baseline",
    "heldout_R3_eccentric_void",
    "heldout_R3_torus",
    "heldout_R3_two_ellipsoids",
)
PAIRS = tuple(case for case in CASES if case.startswith(("D0_", "D1_", "D2_")))
STORAGE = ("double", "float32")
FALSE_FLAGS = {
    "fd_oracle": False,
    "field_gradient": False,
    "optimizer": False,
    "reverse": False,
    "shape_update_allowed": False,
    "solver_qualification": False,
    "topology": False,
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def load_field(path: Path) -> tuple[np.ndarray, np.ndarray, float, dict]:
    with np.load(path) as data:
        phi = data["phi"].copy()
        meta = json.loads(str(data["metadata"]))
    return (
        phi,
        np.asarray(meta["origin_m"], dtype=np.float64),
        float(meta["spacing_m"]),
        meta,
    )


def read_surface(
    case: str, r: int
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, Path]:
    directory = ROUND3 / "surfaces" / f"r{r}" / case
    with np.load(directory / "surface.npz") as data:
        vertices = np.asarray(data["vertices"], dtype=np.float64)
        faces = np.asarray(data["faces"], dtype=np.int64)
    stl_path = directory / "surface.stl.gz"
    if not stl_path.exists():
        stl_path = directory / "surface.stl"
    raw = stl_path.read_bytes()
    if stl_path.suffix == ".gz":
        raw = gzip.decompress(raw)
    mesh = trimesh.load(io.BytesIO(raw), file_type="stl", process=False)
    return (
        vertices,
        faces,
        np.asarray(mesh.vertices, dtype=np.float64),
        np.asarray(mesh.faces, dtype=np.int64),
        stl_path,
    )


def _geometry_class(summary: dict) -> str:
    lower = float(summary["maximum_certified_lower_distance_m"])
    upper = summary["maximum_certified_upper_distance_m"]
    if lower > LIMIT_M:
        return "FAIL"
    if (
        summary["unresolved_sample_count"] == 0
        and upper is not None
        and float(upper) <= LIMIT_M
    ):
        return "PASS"
    return "UNRESOLVED"


def _old_nongeometry_gates(gates: dict) -> bool:
    return (
        all(
            gates[key] is True
            for key in (
                "lineage",
                "clearance",
                "degenerate_free",
                "duplicate_free",
                "positive_total_volume",
                "vertex_link_manifold",
                "edge_manifold",
                "watertight",
                "winding",
            )
        )
        and gates["orientation"] == "PASS"
    )


def _surface_replay(
    r: int, case: str, prior_case: dict, phi: np.ndarray, origin: np.ndarray, h: float
) -> tuple[dict, dict]:
    vertices, faces, vertices_f32, faces_f32, stl_path = read_surface(case, r)
    with np.load(
        ROUND3 / "surfaces" / f"r{r}" / case / "sample_certificates.npz"
    ) as saved:
        old_double = saved["double_triangle_bounds"].copy()
        old_float32 = saved["float32_triangle_bounds"].copy()
    new_values = {}
    for label, v, f, old, gate_key in (
        ("double", vertices, faces, old_double, "double_gates"),
        ("float32", vertices_f32, faces_f32, old_float32, "float32_gates"),
    ):
        parent, parent_bounds = frozen_parent.distance(v, f, phi, origin, h)
        independent, independent_bounds = frozen_independent.distance(
            v, f, phi, origin, h
        )
        p_class = _geometry_class(parent)
        i_class = _geometry_class(independent)
        old_summary = (
            prior_case["identity"]
            if label == "double"
            else prior_case["serialized_identity"]
        )
        old_class = _geometry_class(old_summary)
        max_delta = float(
            np.max(
                np.abs(parent_bounds[:, :2] - independent_bounds[:, :2]), initial=0.0
            )
        )
        same_old = bool(np.array_equal(parent_bounds, old))
        gates = prior_case[gate_key]
        new_values[label] = {
            "parent": parent,
            "independent": independent,
            "classification": p_class if p_class == i_class else "UNRESOLVED",
            "round3_saved_absolute_geometry_classification": old_class,
            "round3_saved_absolute_geometry_gate": bool(gates["absolute_geometry"]),
            "parent_classification": p_class,
            "independent_classification": i_class,
            "other_round3_gates_pass": _old_nongeometry_gates(gates),
            "surface_classification": (
                "UNRESOLVED"
                if p_class != i_class
                else p_class
                if _old_nongeometry_gates(gates)
                else "FAIL"
            ),
            "independent_gate_agreement": p_class == i_class,
            "max_parent_independent_bound_delta_m": max_delta,
            "round3_saved_triangle_bounds_exact_match": same_old,
            "round3_saved_triangle_bounds_sha256": hashlib.sha256(
                old.tobytes()
            ).hexdigest(),
            "fresh_parent_triangle_bounds_sha256": hashlib.sha256(
                parent_bounds.tobytes()
            ).hexdigest(),
            "fresh_independent_triangle_bounds_sha256": hashlib.sha256(
                independent_bounds.tobytes()
            ).hexdigest(),
            "triangle_count": int(len(f)),
            "surface_npz_sha256": sha256(
                ROUND3 / "surfaces" / f"r{r}" / case / "surface.npz"
            ),
            "surface_stl_sha256": sha256(stl_path),
        }
        if not same_old:
            filename = f"r{r}_{case}_{label}_triangle_bounds.npz"
            np.savez_compressed(
                EVIDENCE / "target" / filename,
                parent=parent_bounds,
                independent=independent_bounds,
            )
            new_values[label]["changed_bounds_artifact"] = f"target/{filename}"
    return new_values, {
        "case": case,
        "r": r,
        "double": new_values["double"],
        "float32": new_values["float32"],
    }


def _mesh_roots(
    mesh: trimesh.Trimesh,
    points: np.ndarray,
    normals: np.ndarray,
    h: float,
    span: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    values = np.full(len(points), np.nan, dtype=np.float64)
    tied = np.zeros(len(points), dtype=bool)
    counts = np.zeros(len(points), dtype=np.int32)
    intersector = trimesh.ray.ray_triangle.RayMeshIntersector(mesh)
    locations, ray_ids, _ = intersector.intersects_location(
        points - span * normals, normals, multiple_hits=True
    )
    grouped: list[list[float]] = [[] for _ in points]
    if len(locations):
        t = np.einsum("ij,ij->i", locations - points[ray_ids], normals[ray_ids])
        for ray_id, root in zip(ray_ids, t, strict=True):
            if abs(root) <= span + position_tolerance(h, 2 * span, root):
                grouped[int(ray_id)].append(float(root))
    for i, roots in enumerate(grouped):
        roots.sort()
        unique = []
        for root in roots:
            tol = position_tolerance(h, 2 * span, root)
            if not unique or abs(root - unique[-1]) > tol:
                unique.append(root)
        counts[i] = len(unique)
        ordered = sorted(unique, key=abs)
        if not ordered:
            continue
        if len(ordered) > 1 and abs(
            abs(ordered[1]) - abs(ordered[0])
        ) <= position_tolerance(h, 2 * span, ordered[0], ordered[1]):
            tied[i] = True
        else:
            values[i] = ordered[0]
    return values, tied, counts


def _root_agreement(primary, independent, h: float, span: float) -> dict:
    result = {
        "comparisons": 1,
        "status_mismatch": int(primary.status != independent.status),
        "zero_interval_mismatch": int(
            bool(primary.zero_intervals) != bool(independent.zero_intervals)
        ),
        "root_count_mismatch": int(len(primary.roots) != len(independent.roots)),
        "root_kind_mismatch": 0,
        "root_position_mismatch": 0,
        "nearest_status_mismatch": 0,
        "nearest_identity_mismatch": 0,
        "nearest_position_mismatch": 0,
        "max_root_position_delta_m": 0.0,
        "max_nearest_position_delta_m": 0.0,
        "position_tolerance_max_m": position_tolerance(h, 2 * span),
    }
    p_roots = sorted(primary.roots, key=lambda x: x.t_m)
    i_roots = sorted(independent.roots, key=lambda x: x.t_m)
    if len(p_roots) == len(i_roots):
        for p, q in zip(p_roots, i_roots, strict=True):
            delta = abs(p.t_m - q.t_m)
            tol = position_tolerance(h, 2 * span, p.t_m, q.t_m)
            result["max_root_position_delta_m"] = max(
                result["max_root_position_delta_m"], delta
            )
            result["position_tolerance_max_m"] = max(
                result["position_tolerance_max_m"], tol
            )
            result["root_kind_mismatch"] += int(p.kind != q.kind)
            result["root_position_mismatch"] += int(delta > tol)
    p_near, p_status = nearest_root(primary, h, span)
    i_near, i_status = sturm_nearest(independent, h, span)
    result["nearest_status_mismatch"] = int(p_status != i_status)
    if p_near is not None and i_near is not None:
        delta = abs(p_near.t_m - i_near.t_m)
        tol = position_tolerance(h, 2 * span, p_near.t_m, i_near.t_m)
        result["max_nearest_position_delta_m"] = delta
        result["position_tolerance_max_m"] = max(
            result["position_tolerance_max_m"], tol
        )
        result["nearest_position_mismatch"] = int(delta > tol)
        # Sorted root counts and positions determine root identity. A nearest
        # root at the same ordinal must be selected by both implementations.
        p_index = min(range(len(p_roots)), key=lambda n: abs(p_roots[n].t_m))
        i_index = min(range(len(i_roots)), key=lambda n: abs(i_roots[n].t_m))
        result["nearest_identity_mismatch"] = int(p_index != i_index)
    else:
        result["nearest_identity_mismatch"] = int(
            p_near is not None or i_near is not None
        )
    return result


def _add_agreement(total: dict, one: dict) -> None:
    total["comparisons"] += one["comparisons"]
    for key in (
        "status_mismatch",
        "zero_interval_mismatch",
        "root_count_mismatch",
        "root_kind_mismatch",
        "nearest_status_mismatch",
        "nearest_identity_mismatch",
        "root_position_mismatch",
        "nearest_position_mismatch",
    ):
        total[key] += one[key]
    total["max_root_position_delta_m"] = max(
        total["max_root_position_delta_m"], one["max_root_position_delta_m"]
    )
    total["max_nearest_position_delta_m"] = max(
        total["max_nearest_position_delta_m"], one["max_nearest_position_delta_m"]
    )
    total["position_tolerance_max_m"] = max(
        total["position_tolerance_max_m"], one["position_tolerance_max_m"]
    )


def _root_detail(result) -> dict:
    return {
        "status": result.status,
        "reasons": list(result.reasons),
        "zero_intervals_m": [list(x) for x in result.zero_intervals],
        "roots": [
            {
                "t_m": root.t_m,
                "bracket_m": list(root.bracket_m),
                "kind": root.kind,
                "cell": list(root.cell),
            }
            for root in result.roots
        ],
    }


def _fidelity_replay(
    r: int,
    case: str,
    prereg: dict,
    surface_results: dict,
    prior_fidelity: dict,
    root_stream,
    agreement: dict,
) -> dict:
    with np.load(
        ROUND3 / "surfaces" / f"r{r}" / case / "normal_correspondence.npz"
    ) as data:
        samples_by_storage = {name: data[f"{name}_samples"].copy() for name in STORAGE}
    original_fields = _registered_inventory(prereg)["files"]["original_fields"]
    base_path = ROOT / original_fields["baseline"]["path"]
    case_path = ROOT / original_fields[case]["path"]
    base_phi, origin, h, _ = load_field(base_path)
    target_phi, target_origin, target_h, _ = load_field(case_path)
    if h != target_h or not np.array_equal(origin, target_origin):
        raise RuntimeError("registered source grids differ")
    # Both storage contracts use the same saved baseline samples, but their
    # point/normal arrays differ because float32 STL vertices are rounded.
    double_v, double_f, float_v, float_f, stl_path = read_surface(case, r)
    pair_out = {}
    for storage, mesh_v, mesh_f in (
        ("double", double_v, double_f),
        ("float32", float_v, float_f),
    ):
        rows = samples_by_storage[storage]
        points = rows[:, :3]
        normals = rows[:, 3:6]
        norm = np.linalg.norm(normals, axis=1)
        normal_ok = np.isfinite(norm) & (norm > 64 * np.finfo(float).eps)
        normals = normals.copy()
        normals[normal_ok] /= norm[normal_ok, None]
        normals[~normal_ok] = 0.0
        span = 2.0 * h
        baseline_t = np.full(len(points), np.nan)
        target_t = np.full(len(points), np.nan)
        baseline_status = np.full(len(points), "UNRESOLVED_NORMAL", dtype=object)
        target_status = np.full(len(points), "UNRESOLVED_NORMAL", dtype=object)
        unresolved_reason = np.full(
            len(points), "baseline gradient undefined", dtype=object
        )
        root_counts = {"baseline": [], "target": []}
        max_roots = 0
        # The per-ray JSONL stream is append-only and deterministic. Root sets
        # from both numerical algorithms are recorded before nearest selection.
        for i in range(len(points)):
            record = {"r": r, "case": case, "storage": storage, "sample": i}
            if normal_ok[i]:
                for role, phi in (("baseline", base_phi), ("target", target_phi)):
                    primary = enumerate_ray_roots(
                        phi, origin, h, points[i], normals[i], span
                    )
                    independent = sturm_roots(
                        phi, origin, h, points[i], normals[i], span
                    )
                    comparison = _root_agreement(primary, independent, h, span)
                    _add_agreement(agreement, comparison)
                    max_roots = max(
                        max_roots, len(primary.roots), len(independent.roots)
                    )
                    root_counts[role].append(len(primary.roots))
                    p_root, p_class = nearest_root(primary, h, span)
                    i_root, i_class = sturm_nearest(independent, h, span)
                    root_sets_agree = not any(
                        comparison[key]
                        for key in (
                            "status_mismatch",
                            "zero_interval_mismatch",
                            "root_count_mismatch",
                            "root_kind_mismatch",
                            "root_position_mismatch",
                            "nearest_status_mismatch",
                            "nearest_identity_mismatch",
                            "nearest_position_mismatch",
                        )
                    )
                    classification_agrees = root_sets_agree and (
                        primary.status == independent.status
                        and bool(primary.zero_intervals)
                        == bool(independent.zero_intervals)
                        and p_class == i_class
                    )
                    selected = p_root if classification_agrees else None
                    if role == "baseline":
                        baseline_status[i] = (
                            p_class
                            if classification_agrees
                            else "INDEPENDENT_DISAGREEMENT"
                        )
                        if selected is not None:
                            baseline_t[i] = selected.t_m
                    else:
                        target_status[i] = (
                            p_class
                            if classification_agrees
                            else "INDEPENDENT_DISAGREEMENT"
                        )
                        if selected is not None:
                            target_t[i] = selected.t_m
                    record[role] = {
                        "primary": _root_detail(primary),
                        "independent": _root_detail(independent),
                        "nearest_primary": p_class,
                        "nearest_independent": i_class,
                    }
                if np.isfinite(baseline_t[i]) and np.isfinite(target_t[i]):
                    unresolved_reason[i] = ""
                else:
                    unresolved_reason[i] = ";".join(
                        x
                        for x in (str(baseline_status[i]), str(target_status[i]))
                        if x != "UNIQUE_NEAREST_ROOT"
                    )
            record["sample_point_m"] = points[i].tolist()
            record["normal"] = normals[i].tolist()
            root_detail_line = json.dumps(
                record, sort_keys=True, separators=(",", ":"), allow_nan=False
            )
            root_stream.write(root_detail_line + "\n")

        valid_sdf = np.isfinite(baseline_t) & np.isfinite(target_t)
        sdf_delta = target_t - baseline_t
        mesh = trimesh.Trimesh(vertices=mesh_v, faces=mesh_f, process=False)
        mesh_t, mesh_tied, mesh_counts = _mesh_roots(
            mesh, points[normal_ok], normals[normal_ok], h, span
        )
        mesh_delta = np.full(len(points), np.nan)
        mesh_delta[normal_ok] = mesh_t
        ties = np.zeros(len(points), dtype=bool)
        ties[normal_ok] = mesh_tied
        hit_counts = np.zeros(len(points), dtype=np.int32)
        hit_counts[normal_ok] = mesh_counts
        errors = np.full(len(points), np.nan)
        valid = valid_sdf & np.isfinite(mesh_delta) & ~ties
        coordinate_guard = 2.0 * h * 1e-8 + h * 1e-9
        errors[valid] = np.abs(mesh_delta[valid] - sdf_delta[valid]) + coordinate_guard
        unresolved = ~valid
        maximum = float(np.nanmax(errors)) if np.any(np.isfinite(errors)) else None
        prereq = all(
            surface_results[other][surface_storage]["surface_classification"] == "PASS"
            for other in ("baseline", case)
            for surface_storage in STORAGE
        )
        qualified = (
            prereq
            and not unresolved.any()
            and maximum is not None
            and maximum <= LIMIT_M
        )
        output = {
            "round3_parent_result": {
                "pair_status": prior_fidelity["status"],
                "pair_reason": prior_fidelity["reason"],
                "maximum_normal_displacement_difference_m": prior_fidelity[storage][
                    "maximum_normal_displacement_difference_m"
                ],
                "unresolved_samples": prior_fidelity[storage]["unresolved_samples"],
                "within_limit": prior_fidelity[storage]["within_limit"],
            },
            "sample_count": int(len(points)),
            "unresolved_samples": int(unresolved.sum()),
            "maximum_normal_displacement_difference_m": maximum,
            "tolerance_m": LIMIT_M,
            "coordinate_guard_m": coordinate_guard,
            "primary_independent_root_agreement": {
                key: agreement[key] for key in agreement
            },
            "primary_root_count_distribution": {
                role: {
                    str(n): int(root_counts[role].count(n))
                    for n in sorted(set(root_counts[role]))
                }
                for role in root_counts
            },
            "maximum_roots_on_one_ray": max_roots,
            "mesh_intersection_count_distribution": {
                str(n): int(np.count_nonzero(hit_counts == n))
                for n in np.unique(hit_counts)
            },
            "mesh_root_tie_count": int(ties.sum()),
            "surface_prerequisite_status": "PASS" if prereq else "FAIL",
            "qualification": (
                "PASS"
                if qualified
                else "UNRESOLVED"
                if prereq
                else "NOT_QUALIFIED_SURFACE_PREREQUISITE"
            ),
            "within_limit_descriptive": bool(
                not unresolved.any() and maximum is not None and maximum <= LIMIT_M
            ),
            "unresolved_reason_counts": {
                str(reason): int(np.count_nonzero(unresolved_reason == reason))
                for reason in np.unique(unresolved_reason[unresolved])
            },
            "sample_recording": "all source root sets and nearest classifications in correspondence_roots.jsonl.gz",
            "mesh_stl_sha256": sha256(stl_path) if storage == "float32" else None,
        }
        pair_out[storage] = output
    return {
        "r": r,
        "case": case,
        "double": pair_out["double"],
        "float32": pair_out["float32"],
    }


def _verify_prereg(prereg: dict, paths: list[dict]) -> None:
    for entry in paths:
        path = ROOT / entry["path"]
        if (
            not path.is_file()
            or path.stat().st_size != entry["bytes"]
            or sha256(path) != entry["sha256"]
        ):
            raise RuntimeError(f"registered input changed: {entry['path']}")
    for name, expected in prereg["effective_source_sha256"].items():
        path = ROOT / name
        if sha256(path) != expected:
            raise RuntimeError(f"registered source changed: {name}")


def _registered_inventory(prereg: dict) -> dict:
    """Read the inventory field frozen by the CERT-01 registration schema."""
    return prereg["target_replay_inventory"]


def _load_registration() -> tuple[dict, str, str | None]:
    prereg = json.loads(PREREGISTRATION.read_text())
    preregistration_sha256 = sha256(PREREGISTRATION)
    amendment_sha256 = None
    effective_hashes = dict(prereg["source_sha256"])
    if PREREGISTRATION_AMENDMENT.exists():
        amendment = json.loads(PREREGISTRATION_AMENDMENT.read_text())
        if amendment["parent_preregistration_sha256"] != preregistration_sha256:
            raise RuntimeError("preregistration amendment parent hash mismatch")
        if amendment.get("target_evaluation_started") is not False:
            raise RuntimeError("amendment must precede target evaluation")
        overrides = amendment["source_sha256_overrides"]
        if set(overrides) != {AMENDABLE_SOURCE, AMENDABLE_TEST}:
            raise RuntimeError(
                "amendment may update only runner and regression test hashes"
            )
        effective_hashes.update(overrides)
        amendment_sha256 = sha256(PREREGISTRATION_AMENDMENT)
    prereg["effective_source_sha256"] = effective_hashes
    return prereg, preregistration_sha256, amendment_sha256


def _verify_registered_branch(prereg: dict) -> tuple[str, str]:
    branch = subprocess.check_output(
        ["git", "branch", "--show-current"], cwd=ROOT, text=True
    ).strip()
    head = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    dirty = subprocess.check_output(
        ["git", "status", "--porcelain"], cwd=ROOT, text=True
    ).strip()
    remote = subprocess.check_output(
        ["git", "ls-remote", "origin", f"refs/heads/{branch}"],
        cwd=ROOT,
        text=True,
    ).split()
    remote_head = remote[0] if remote else ""
    if branch != prereg["branch"] or dirty or remote_head != head:
        raise RuntimeError(
            "target replay requires the registered clean feature branch at the same pushed HEAD"
        )
    return head, remote_head


def run(r_values: list[int]) -> Path:
    prereg, preregistration_sha256, amendment_sha256 = _load_registration()
    prereg_commit, remote_head = _verify_registered_branch(prereg)
    inventory = _registered_inventory(prereg)
    _verify_prereg(prereg, inventory["files"]["files"])
    out_dir = EVIDENCE / "target" / ("r" + "_".join(map(str, r_values)))
    out_dir.mkdir(parents=True, exist_ok=False)
    all_results = json.loads((ROUND3 / "result.json").read_text())
    by_case = {(c["r"], c["case"]): c for c in all_results["cases"]}
    by_fidelity = {(c["r"], c["case"]): c for c in all_results["fidelity_pairs"]}
    input_hashes = {
        case: inventory["files"]["original_fields"][case]["sha256"] for case in CASES
    }
    primary_cases = []
    independent_cases = []
    primary_pairs = []
    independent_pairs = []
    agreement = {
        "comparisons": 0,
        "status_mismatch": 0,
        "zero_interval_mismatch": 0,
        "root_count_mismatch": 0,
        "root_kind_mismatch": 0,
        "root_position_mismatch": 0,
        "nearest_status_mismatch": 0,
        "nearest_identity_mismatch": 0,
        "nearest_position_mismatch": 0,
        "max_root_position_delta_m": 0.0,
        "max_nearest_position_delta_m": 0.0,
        "position_tolerance_max_m": 0.0,
    }
    root_path = out_dir / "correspondence_roots.jsonl.gz.partial"
    started = time.time()
    with root_path.open("wb") as compressed_file:
        with gzip.GzipFile(
            filename="", fileobj=compressed_file, mode="wb", mtime=0
        ) as compressed:
            with io.TextIOWrapper(compressed, encoding="utf-8") as root_stream:
                for r in r_values:
                    fields = {
                        case: load_field(
                            ROOT / inventory["files"]["original_fields"][case]["path"]
                        )
                        for case in CASES
                    }
                    for case in CASES:
                        phi, origin, h, _ = fields[case]
                        parent_values, entry = _surface_replay(
                            r, case, by_case[(r, case)], phi, origin, h
                        )
                        primary_cases.append(entry)
                        independent_cases.append(
                            {
                                "case": case,
                                "r": r,
                                **{
                                    storage: {
                                        "classification": parent_values[storage][
                                            "independent_classification"
                                        ],
                                        "summary": parent_values[storage][
                                            "independent"
                                        ],
                                        "round3_saved_triangle_bounds_exact_match": parent_values[
                                            storage
                                        ]["round3_saved_triangle_bounds_exact_match"],
                                    }
                                    for storage in STORAGE
                                },
                            }
                        )
                    surface_index = {(c["r"], c["case"]): c for c in primary_cases}
                    for case in PAIRS:
                        pair = _fidelity_replay(
                            r,
                            case,
                            prereg,
                            surface_index,
                            by_fidelity[(r, case)],
                            root_stream,
                            agreement,
                        )
                        primary_pairs.append(pair)
                        independent_pairs.append(
                            {
                                "r": r,
                                "case": case,
                                "double": pair["double"][
                                    "primary_independent_root_agreement"
                                ],
                                "float32": pair["float32"][
                                    "primary_independent_root_agreement"
                                ],
                            }
                        )
                    print(f"r={r} complete", flush=True)
    root_final = out_dir / "correspondence_roots.jsonl.gz"
    root_path.rename(root_final)
    common = {
        "evidence_class": "solver_free_successor_root_certifier_replay",
        "certifier_identity": "XFID45-CERT-01",
        "preregistration_sha256": preregistration_sha256,
        "preregistration_amendment_sha256": amendment_sha256,
        "preregistration_branch_head": prereg_commit,
        "preregistration_remote_head": remote_head,
        "registration_start_head": prereg["authoritative_start_head"],
        "round3_source_and_evidence_unchanged": True,
        "surface_extraction_rerun": False,
        "r_values": r_values,
        "input_hashes": input_hashes,
        "source_sha256": prereg["effective_source_sha256"],
        "runtime_identity": prereg["runtime_identity"],
        "qualification_flags": FALSE_FLAGS,
        "elapsed_seconds": time.time() - started,
    }
    primary = {
        **common,
        "geometry_cases": primary_cases,
        "fidelity_pairs": primary_pairs,
        "root_diagnostic_path": str(root_final.relative_to(EVIDENCE)),
        "root_diagnostic_sha256": sha256(root_final),
    }
    independent = {
        **common,
        "absolute_geometry_cases": independent_cases,
        "fidelity_root_set_agreement": agreement,
        "fidelity_pairs": independent_pairs,
        "agreement_pass": not any(
            agreement[key]
            for key in (
                "status_mismatch",
                "zero_interval_mismatch",
                "root_count_mismatch",
                "root_kind_mismatch",
                "root_position_mismatch",
                "nearest_status_mismatch",
                "nearest_identity_mismatch",
                "nearest_position_mismatch",
            )
        ),
    }
    comparison = {
        "evidence_class": "immutable_round3_vs_xfid45_cert01_comparison",
        "round3_result_sha256": sha256(ROUND3 / "result.json"),
        "absolute_geometry": [
            {
                "case": entry["case"],
                "r": entry["r"],
                **{
                    storage: {
                        "round3_classification": entry[storage][
                            "round3_saved_absolute_geometry_classification"
                        ],
                        "cert01_classification": entry[storage]["classification"],
                        "round3_gate": entry[storage][
                            "round3_saved_absolute_geometry_gate"
                        ],
                        "round3_bounds_exactly_reproduced": entry[storage][
                            "round3_saved_triangle_bounds_exact_match"
                        ],
                    }
                    for storage in STORAGE
                },
            }
            for entry in primary_cases
        ],
        "normal_correspondence": [
            {
                "case": entry["case"],
                "r": entry["r"],
                **{
                    storage: {
                        "round3_parent": entry[storage]["round3_parent_result"],
                        "cert01": {
                            "qualification": entry[storage]["qualification"],
                            "unresolved_samples": entry[storage]["unresolved_samples"],
                            "maximum_normal_displacement_difference_m": entry[storage][
                                "maximum_normal_displacement_difference_m"
                            ],
                            "tolerance_m": entry[storage]["tolerance_m"],
                        },
                    }
                    for storage in STORAGE
                },
            }
            for entry in primary_pairs
        ],
    }
    (out_dir / "primary_result.json").write_text(
        json.dumps(primary, indent=2, sort_keys=True, allow_nan=False) + "\n"
    )
    (out_dir / "independent_result.json").write_text(
        json.dumps(independent, indent=2, sort_keys=True, allow_nan=False) + "\n"
    )
    (out_dir / "round3_comparison.json").write_text(
        json.dumps(comparison, indent=2, sort_keys=True, allow_nan=False) + "\n"
    )
    manifest = {
        "evidence_class": "target_replay_sha256_manifest",
        "manifest_excludes_self": True,
        "files": [
            {
                "path": str(path.relative_to(EVIDENCE)),
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
            }
            for path in sorted(out_dir.rglob("*"))
            if path.is_file()
        ],
    }
    (out_dir / "sha256_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True, allow_nan=False) + "\n"
    )
    return out_dir


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--r", nargs="+", type=int, choices=(1, 2, 4, 8), required=True)
    args = parser.parse_args()
    values = sorted(set(args.r))
    print(run(values))


if __name__ == "__main__":
    main()
