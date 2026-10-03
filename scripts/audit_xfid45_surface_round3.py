#!/usr/bin/env python3
"""Execute preregistered Round3; solver-free, all factors and failures retained."""

import gzip
import hashlib
import io
import json
import subprocess
from pathlib import Path
import numpy as np
import trimesh
from xfid45_round3_export import extract, orient, topology
from xfid45_round3_measure import distance, fidelity, volume

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/evidence/xfid45_surface_round3_2026_10_03"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dump(path, obj):
    path.write_text(json.dumps(obj, indent=2, sort_keys=True, allow_nan=False) + "\n")


def load(path):
    with np.load(path) as z:
        m = json.loads(str(z["metadata"]))
        return z["phi"].copy(), np.array(m["origin_m"]), float(m["spacing_m"])


def array_sha(v, f):
    return hashlib.sha256(
        v.astype("<f8").tobytes() + f.astype("<i8").tobytes()
    ).hexdigest()


def surface(path):
    with np.load(path / "surface.npz") as z:
        return z["vertices"], z["faces"]


def stl_surface(path):
    mesh = trimesh.load(
        io.BytesIO(gzip.decompress((path / "surface.stl.gz").read_bytes())),
        file_type="stl",
        process=False,
    )
    return np.asarray(mesh.vertices), np.asarray(mesh.faces)


def stored_orientation(v, f, phi, o, h):
    """Read-only assessment: a hypothetical component flip is never accepted."""
    _, audit = orient(v, f, phi, o, h)
    if audit["status"] != "N/A":
        already_outward = all(
            c["delta_votes"] == ["outward"] * 3 for c in audit["components"]
        )
        audit["status"] = (
            "PASS"
            if already_outward and topology(v, f)["signed_volume_m3"] > 0
            else "FAIL"
        )
        audit["stored_all_components_outward"] = already_outward
    return audit


def defect_mapping(v, f, phi, o, h):
    """Localize audit defects on immutable original nodes, without repair."""
    from itertools import product

    u, inverse = np.unique(v, axis=0, return_inverse=True)
    faces = inverse[f]
    edges = np.sort(
        np.concatenate([faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]]), axis=1
    )
    unique_edges, counts = np.unique(edges, axis=0, return_counts=True)
    stats = topology(v, f)
    points = [
        ("edge_incidence_not_two", u[e].mean(0), e.tolist(), int(count))
        for e, count in zip(unique_edges, counts)
        if count != 2
    ]
    points += [
        ("vertex_link", u[k], [int(k)], None) for k in stats["vertex_link_bad_vertices"]
    ]
    rows = []
    for kind, p, indices, count in points:
        cells = []
        q = (p - o) / h
        choices = []
        for a in range(3):
            ix = int(np.floor(q[a]))
            valid = [ix]
            nearest = int(np.rint(q[a]))
            if abs(q[a] - nearest) <= 1e-9:
                valid = [nearest - 1, nearest]
            choices.append([j for j in valid if 0 <= j < phi.shape[a] - 1])
        for cell in product(*choices):
            nodes = [list(np.array(cell) + b) for b in product((0, 1), repeat=3)]
            values = [float(phi[tuple(node)]) for node in nodes]
            cells.append(
                dict(
                    cell=list(cell),
                    nodes=nodes,
                    phi_m=values,
                    exact_zero_count=sum(x == 0 for x in values),
                    nearzero_nonzero_count=sum(
                        0 < abs(x) <= h * np.finfo(np.float32).eps for x in values
                    ),
                )
            )
        incident = np.flatnonzero(np.any(np.isin(faces, indices), axis=1))
        rows.append(
            dict(
                kind=kind,
                position_m=p.tolist(),
                exact_coordinate_indices=indices,
                edge_incidence=count,
                incident_original_face_ids=incident.tolist(),
                possible_original_cells=cells,
            )
        )
    return dict(
        scope="original-cell localization, not proof of inherent source singularity",
        defects=rows,
    )


def statuses(stats, orientation, identity, lineage):
    return {
        "lineage": bool(lineage),
        "edge_manifold": stats["edge_incidence_not_two_count"] == 0,
        "vertex_link_manifold": stats["vertex_link_bad_count"] == 0,
        "watertight": stats["watertight"],
        "winding": stats["winding_consistent"],
        "duplicate_free": stats["duplicate_face_count"] == 0,
        "degenerate_free": stats["zero_area_face_count"] == 0
        and stats["repeated_index_face_count"] == 0,
        "orientation": orientation["status"],
        "positive_total_volume": stats["signed_volume_m3"] > 0
        if orientation["status"] == "PASS"
        else "N/A",
        "absolute_geometry": identity["within_limit"],
        "clearance": stats["minimum_stage_v_clearance_m"] >= 0.25,
    }


def allpass(gates):
    return all(value is True or value == "PASS" for value in gates.values())


def main():
    reg = json.loads((OUT / "preregistration.json").read_text())
    head = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    remote = subprocess.check_output(
        ["git", "ls-remote", "origin", reg["branch"]], cwd=ROOT, text=True
    ).split()[0]
    assert head == remote, "preregistration HEAD not pushed"
    assert (
        subprocess.check_output(
            [
                "git",
                "show",
                f"{head}:{(OUT / 'preregistration.json').relative_to(ROOT)}",
            ],
            cwd=ROOT,
        )
        == (OUT / "preregistration.json").read_bytes()
    )
    for group in ("inputs", "sources", "runtime_files"):
        for spec in reg[group].values():
            path = Path(spec["path"])
            path = path if path.is_absolute() else ROOT / path
            assert sha(path) == spec["sha256"], f"changed frozen file {path}"
    ledger = {
        "evidence_class": "solver_free_registered_surface_refinement_screen",
        "registration_commit": head,
        "registration_sha256": sha(OUT / "preregistration.json"),
        "qualification_flags": reg["qualification_flags"],
        "cases": [],
        "fidelity_pairs": [],
        "source_volume_quadrature": {},
        "selected_r": None,
    }
    # Original-field diagnostics measured only after registration; no thresholds fitted.
    for case, spec in reg["inputs"].items():
        phi, o, h = load(ROOT / spec["path"])
        corners = np.stack(
            [
                phi[
                    i : phi.shape[0] - 1 + i,
                    j : phi.shape[1] - 1 + j,
                    k : phi.shape[2] - 1 + k,
                ]
                for i in (0, 1)
                for j in (0, 1)
                for k in (0, 1)
            ],
            axis=-1,
        )
        ledger["source_volume_quadrature"][case] = {
            "gauss_xy_exact_linear_z": {
                str(n): volume(phi, o, h, n) for n in (16, 32, 64)
            },
            "all_zero_original_cells": int(np.all(corners == 0, axis=-1).sum()),
            "exact_zero_original_nodes": int((phi == 0).sum()),
            "nearzero_nonzero_original_nodes": int(
                ((phi != 0) & (np.abs(phi) <= h * np.finfo(np.float32).eps)).sum()
            ),
            "scope": "approximate volume ladder; no exact quadrature error bound",
        }
    dump(OUT / "source_field_diagnostics.json", ledger["source_volume_quadrature"])
    for r in (1, 2, 4, 8):
        for case, spec in reg["inputs"].items():
            phi, o, h = load(ROOT / spec["path"])
            v, raw_f, audit = extract(phi, o, h, r)
            f, pre_ori = orient(v, raw_f, phi, o, h)
            rv, rf, _ = extract(phi, o, h, r)
            rf, _ = orient(rv, rf, phi, o, h)
            repeat_hash = array_sha(rv, rf)
            deterministic = array_sha(v, f) == repeat_hash
            del rv, rf
            folder = OUT / "surfaces" / f"r{r}" / case
            folder.mkdir(parents=True, exist_ok=True)
            np.savez_compressed(folder / "surface.npz", vertices=v, faces=f)
            stl = trimesh.Trimesh(v, f, process=False).export(file_type="stl")
            (folder / "surface.stl.gz").write_bytes(gzip.compress(stl, mtime=0))
            sv, sf = stl_surface(folder)
            stats = topology(v, f)
            serialized = topology(sv, sf)
            ori = stored_orientation(v, f, phi, o, h)
            stl_ori = stored_orientation(sv, sf, phi, o, h)
            mapping = defect_mapping(v, f, phi, o, h)
            (folder / "defect_to_original_grid.json.gz").write_bytes(
                gzip.compress(
                    json.dumps(mapping, sort_keys=True, allow_nan=False).encode(),
                    mtime=0,
                )
            )
            identity, bounds = distance(v, f, phi, o, h)
            stl_identity, stl_bounds = distance(sv, sf, phi, o, h)
            np.savez_compressed(
                folder / "sample_certificates.npz",
                double_triangle_bounds=bounds,
                float32_triangle_bounds=stl_bounds,
            )
            # Lineage field construction is fixed; independent source hashes bind original snapshots.
            lineage = (
                audit["source_phi_unmodified"]
                and audit["float32_cast_lineage_pass"]
                and deterministic
            )
            audit.update(
                native_orientation=pre_ori,
                stored_orientation=ori,
                serialized_orientation=stl_ori,
            )
            (folder / "lineage_orientation.json.gz").write_bytes(
                gzip.compress(
                    json.dumps(audit, sort_keys=True, allow_nan=False).encode(), mtime=0
                )
            )
            row = {
                "r": r,
                "case": case,
                "lineage": lineage,
                "deterministic_repeat_match": deterministic,
                "repeat_array_sha256": repeat_hash,
                "statistics": stats,
                "serialized_statistics": serialized,
                "orientation": ori,
                "serialized_orientation": stl_ori,
                "identity": identity,
                "serialized_identity": stl_identity,
                "double_gates": statuses(stats, ori, identity, lineage),
                "float32_gates": statuses(serialized, stl_ori, stl_identity, lineage),
                "raw_array_sha256": array_sha(v, f),
                "surface_npz_sha256": sha(folder / "surface.npz"),
                "raw_stl_sha256": hashlib.sha256(stl).hexdigest(),
                "stl_gzip_sha256": sha(folder / "surface.stl.gz"),
            }
            row["surface_gates_pass"] = allpass(row["double_gates"]) and allpass(
                row["float32_gates"]
            )
            ledger["cases"].append(row)
            dump(OUT / "result.json", ledger)
            print(r, case, "PASS" if row["surface_gates_pass"] else "FAIL", flush=True)
        basefolder = OUT / "surfaces" / f"r{r}" / "baseline"
        bv, bf = surface(basefolder)
        basephi, o, h = load(ROOT / reg["inputs"]["baseline"]["path"])
        base_record = next(
            c for c in ledger["cases"] if c["r"] == r and c["case"] == "baseline"
        )
        for case in reg["fidelity_target_cases"]:
            folder = OUT / "surfaces" / f"r{r}" / case
            tv, tf = surface(folder)
            targetphi, _, _ = load(ROOT / reg["inputs"][case]["path"])
            target_record = next(
                c for c in ledger["cases"] if c["r"] == r and c["case"] == case
            )
            fid, values = fidelity(bv, bf, tv, tf, basephi, targetphi, o, h)
            sv, sf = stl_surface(basefolder)
            stv, stf = stl_surface(folder)
            sfid, svalues = fidelity(sv, sf, stv, stf, basephi, targetphi, o, h)
            np.savez_compressed(
                folder / "normal_correspondence.npz",
                double_samples=values,
                float32_samples=svalues,
            )
            prerequisite = (
                base_record["surface_gates_pass"]
                and target_record["surface_gates_pass"]
            )
            pair = {
                "r": r,
                "case": case,
                "double": fid,
                "float32": sfid,
                "status": "PASS"
                if prerequisite and fid["within_limit"] and sfid["within_limit"]
                else "FAIL"
                if prerequisite
                else "N/A",
                "reason": None
                if prerequisite
                else "surface prerequisites failed; correspondence diagnostic only",
                "SDF_volume_difference_from_baseline_m3": {
                    str(n): ledger["source_volume_quadrature"][case][
                        "gauss_xy_exact_linear_z"
                    ][str(n)]
                    - ledger["source_volume_quadrature"]["baseline"][
                        "gauss_xy_exact_linear_z"
                    ][str(n)]
                    for n in (16, 32, 64)
                },
                "mesh_signed_volume_difference_from_baseline_m3": target_record[
                    "statistics"
                ]["signed_volume_m3"]
                - base_record["statistics"]["signed_volume_m3"],
                "STL_signed_volume_difference_from_baseline_m3": target_record[
                    "serialized_statistics"
                ]["signed_volume_m3"]
                - base_record["serialized_statistics"]["signed_volume_m3"],
            }
            ledger["fidelity_pairs"].append(pair)
            dump(OUT / "result.json", ledger)
            print(r, case, "fidelity", pair["status"], flush=True)
    ledger["candidate_pass_before_independent_verification"] = {
        str(r): all(c["surface_gates_pass"] for c in ledger["cases"] if c["r"] == r)
        and all(c["status"] == "PASS" for c in ledger["fidelity_pairs"] if c["r"] == r)
        for r in (1, 2, 4, 8)
    }
    dump(OUT / "result.json", ledger)


if __name__ == "__main__":
    main()
