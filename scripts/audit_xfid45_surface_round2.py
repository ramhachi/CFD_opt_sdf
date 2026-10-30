#!/usr/bin/env python3
"""Execute frozen geometry-only candidates, refusing changed preregistration inputs."""

import hashlib
import json
import subprocess
from pathlib import Path
import numpy as np
import trimesh
from xfid45_round2_metrics import load_field, mesh_stats, displacement, sidedness
from xfid45_surface_round2_candidates import extract_candidate

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/evidence/xfid45_surface_round2_2026_10_03"


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def dump(p, obj):
    p.write_text(json.dumps(obj, indent=2, sort_keys=True, allow_nan=False) + "\n")


def array_hash(v, f):
    return hashlib.sha256(
        np.asarray(v, dtype="<f8").tobytes() + np.asarray(f, dtype="<i8").tobytes()
    ).hexdigest()


def main():
    regpath = OUT / "preregistration.json"
    reg = json.loads(regpath.read_text())
    # Registration must already be in the current commit AND its remote branch.
    head = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    remote = subprocess.check_output(
        ["git", "ls-remote", "origin", reg["experiment_branch"]], cwd=ROOT, text=True
    ).split()[0]
    if remote != head:
        raise RuntimeError("registration commit has not been pushed as current HEAD")
    committed = subprocess.check_output(
        ["git", "show", f"{head}:{regpath.relative_to(ROOT)}"], cwd=ROOT
    )
    if committed != regpath.read_bytes():
        raise RuntimeError("uncommitted preregistration")
    for group in ("input_files", "source_files", "runtime_files"):
        for spec in reg[group].values():
            p = Path(spec["path"])
            p = p if p.is_absolute() else ROOT / p
            if sha(p) != spec["sha256"]:
                raise RuntimeError(f"changed frozen file: {p}")
    rows = []
    for name in ("A", "B", "C"):
        for case, spec in reg["input_files"].items():
            phi, o, h = load_field(ROOT / spec["path"])
            source = phi.copy()
            v, f, audit = extract_candidate(name, phi, o, h)
            v2, f2, _ = extract_candidate(name, phi, o, h)
            if not np.array_equal(source, phi):
                raise RuntimeError("canonical field mutated")
            folder = OUT / "surfaces" / name / case
            folder.mkdir(parents=True, exist_ok=True)
            np.savez_compressed(folder / "surface.npz", vertices=v, faces=f)
            trimesh.Trimesh(v, f, process=False).export(folder / "surface.stl")
            dump(folder / "extraction_orientation_audit.json", audit)
            stats = mesh_stats(v, f)
            identity, samples = displacement(v, f, phi, o, h)
            np.savez_compressed(
                folder / "sample_distances.npz", distance_upper_lower_m=samples
            )
            stl = trimesh.load_mesh(folder / "surface.stl", process=False)
            serialized = mesh_stats(stl.vertices, stl.faces)
            stl_identity, stl_samples = displacement(stl.vertices, stl.faces, phi, o, h)
            np.savez_compressed(
                folder / "serialized_sample_distances.npz",
                distance_upper_lower_m=stl_samples,
            )
            ori = sidedness(v, f, phi, o, h)
            sv, si = np.unique(stl.vertices, axis=0, return_inverse=True)
            serialized_ori = sidedness(sv, si[stl.faces], phi, o, h)
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
                and all(c["delta_polarity"] == [1, 1, 1] for c in ori)
                and bool(serialized_ori)
                and all(c["delta_polarity"] == [1, 1, 1] for c in serialized_ori),
                identity=identity["within_displacement_limit"]
                and stl_identity["within_displacement_limit"],
                determinism=array_hash(v, f) == array_hash(v2, f2),
            )
            row = {
                "candidate": name,
                "case": case,
                "statistics": stats,
                "serialized_statistics": serialized,
                "identity": identity,
                "serialized_identity": stl_identity,
                "orientation": ori,
                "serialized_orientation": serialized_ori,
                "raw_surface_array_sha256": array_hash(v, f),
                "surface_npz_sha256": sha(folder / "surface.npz"),
                "surface_stl_sha256": sha(folder / "surface.stl"),
                "gates": gates,
                "pass": all(gates.values()),
            }
            rows.append(row)
            print(
                name,
                case,
                "PASS" if row["pass"] else "FAIL",
                [k for k, p in gates.items() if not p],
                flush=True,
            )
    results = {
        name: all(r["pass"] for r in rows if r["candidate"] == name)
        for name in ("A", "B", "C")
    }
    dump(
        OUT / "result.json",
        {
            "evidence_class": "solver_free_successor_surface_export_candidate_screen",
            "registration_commit": head,
            "registration_sha256": sha(regpath),
            "candidate_all_cases_pass": results,
            "selected_candidate": next((n for n, p in results.items() if p), None),
            "selection_is_production_adoption": False,
            "formal_XFID_executed": False,
            "solver_executed": False,
            "cases": rows,
            "qualification_flags": reg["qualification_flags"],
        },
    )


if __name__ == "__main__":
    main()
