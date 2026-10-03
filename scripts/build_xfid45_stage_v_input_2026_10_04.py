"""Derive the XFID Stage V STL inputs from saved Round 3 r=8 surfaces.

Practical (not certified) gate, per docs/issues/45_next_steps_plan_2026_10_04.md:
remove sub-resolution components, require watertight/manifold/positive-volume,
and report (never certify) geometry error. Round 3 evidence is read, not changed.
"""

import gzip
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import xfid45_round3_export as ex  # noqa: E402
from xfid45_surface_round2_candidates import sample_phi, sample_phi_gradient  # noqa: E402

R3 = ROOT / "docs/evidence/xfid45_surface_round3_2026_10_03/surfaces/r8"
PRE = ROOT / "docs/evidence/xfid01_geometry_preflight_2026_10_03"
OUT = ROOT / "docs/evidence/xfid45_stage_v_input_2026_10_04"
CASES = {
    "baseline": PRE / "canonical_state.npz",
    **{
        c: PRE / f"state_snapshots/{c}.npz"
        for c in (
            "D0_interface_offset_minus",
            "D0_interface_offset_plus",
            "D1_filtered_seed11_minus",
            "D1_filtered_seed11_plus",
            "D2_filtered_seed2026_minus",
            "D2_filtered_seed2026_plus",
        )
    },
}
H = 0.025  # design lattice spacing = rule threshold: smaller than one lattice cell
EPS = 0.005
LIMIT = 0.0005  # descriptive reference only: not a gate


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def split_components(v, f):
    """Exact-coordinate edge components as (labels, unique vertices, remapped faces)."""
    u, inv = np.unique(v, axis=0, return_inverse=True)
    uf = inv[f]
    labels, _ = ex._edge_components(uf)
    return labels, u, uf


def remove_small_components(v, f, h=H):
    """Drop components whose bounding-box diagonal is below one lattice cell."""
    labels, u, uf = split_components(v, f)
    removed, keep = [], np.ones(len(f), bool)
    for k in range(labels.max() + 1 if len(f) else 0):
        m = labels == k
        pts = u[np.unique(uf[m])]
        diag = float(np.linalg.norm(pts.max(0) - pts.min(0)))
        if diag < h:
            keep &= ~m
            vol = float(np.einsum("ij,ij->i", u[uf[m, 0]], np.cross(u[uf[m, 1]], u[uf[m, 2]])).sum() / 6)
            removed.append(
                {"faces": int(m.sum()), "bbox_diagonal_m": diag, "signed_volume_m3": vol,
                 "center_m": ((pts.max(0) + pts.min(0)) / 2).tolist()}
            )
    used = np.unique(uf[keep])
    remap = np.full(len(u), -1)
    remap[used] = np.arange(len(used))
    return u[used], remap[uf[keep]], removed


def stl_bytes(v, f):
    tri = v[f].astype(np.float32)
    n = np.cross(tri[:, 1].astype(np.float64) - tri[:, 0], tri[:, 2].astype(np.float64) - tri[:, 0])
    n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-300)
    rec = np.zeros(len(f), dtype=[("n", "<f4", 3), ("t", "<f4", (3, 3)), ("a", "<u2")])
    rec["n"], rec["t"] = n.astype(np.float32), tri
    return b"\0" * 80 + np.uint32(len(f)).tobytes() + rec.tobytes()


def read_stl(blob):
    n = int(np.frombuffer(blob[80:84], "<u4")[0])
    rec = np.frombuffer(blob[84:], dtype=[("n", "<f4", 3), ("t", "<f4", (3, 3)), ("a", "<u2")], count=n)
    return rec["t"].reshape(-1, 3).astype(np.float64), np.arange(3 * n).reshape(n, 3)


def gates(v, f, phi, origin):
    """Practical gate on one surface; orient() must need no flips."""
    t = ex.topology(v, f)
    _, o = ex.orient(v, f, phi, origin, H)
    flipped = [c for c in o["components"] if c["whole_component_flipped"]]
    g = {
        "watertight": t["watertight"],
        "winding_consistent": t["winding_consistent"],
        "edge_manifold": t["nonmanifold_edge_count"] == 0 and t["boundary_edge_count"] == 0,
        "vertex_link_manifold": t["vertex_link_bad_count"] == 0,
        "no_duplicate_or_degenerate_faces": t["duplicate_face_count"] == 0
        and t["repeated_index_face_count"] == 0 and t["zero_area_face_count"] == 0,
        "positive_signed_volume": t["signed_volume_m3"] > 0,
        "stage_v_clearance": t["stage_v_clearance_pass"],
        "orientation_pass_without_flip": o["status"] == "PASS" and not flipped,
    }
    g["practical_gate_pass"] = all(g.values())
    return g, {"components": t["component_face_counts"], "signed_volume_m3": t["signed_volume_m3"],
               "triangles": t["triangle_count"], "min_clearance_m": t["minimum_stage_v_clearance_m"]}


def stats(x):
    x = np.abs(x)
    return {"median_m": float(np.median(x)), "p99_m": float(np.percentile(x, 99)),
            "max_m": float(x.max()), "fraction_over_0p5mm": float((x > LIMIT).mean())}


def main(out_stl_dir):
    out_stl_dir = Path(out_stl_dir)
    out_stl_dir.mkdir(parents=True, exist_ok=True)
    states = {}
    for c, p in CASES.items():
        z = np.load(p)
        meta = json.loads(str(z["metadata"]))
        assert meta["spacing_m"] == H
        states[c] = (z["phi"], np.array(meta["origin_m"]))
    res = {
        "evidence_class": "solver_free_practical_stage_v_input_derivation_uncertified_geometry",
        "git_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "git_status_clean": not subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True).strip(),
        "cases": {},
    }
    base_phi, base_o = states["baseline"]
    for c in CASES:
        phi, o = states[c]
        src = R3 / c / "surface.npz"
        z = np.load(src)
        v, f, removed = remove_small_components(z["vertices"], z["faces"])
        gd, md = gates(v, f, phi, o)
        blob = stl_bytes(v, f)
        (out_stl_dir / f"{c}.stl").write_bytes(blob)
        v32, f32 = read_stl(blob)
        g32, m32 = gates(v32, f32, phi, o)
        d = sample_phi(phi, o, H, v) / np.linalg.norm(sample_phi_gradient(phi, o, H, v), axis=1)
        row = {
            "source_surface_sha256": sha(src),
            "input_state_sha256": sha(CASES[c]),
            "derived_stl_sha256": hashlib.sha256(blob).hexdigest(),
            "removed_components": removed,
            "double_gates": gd, "double_measures": md,
            "float32_stl_gates": g32, "float32_stl_measures": m32,
            "own_field_first_order_distance_double": stats(d),
        }
        if c != "baseline":  # realized displacement from baseline, in units of nominal epsilon
            r = sample_phi(base_phi, base_o, H, v) / np.linalg.norm(sample_phi_gradient(base_phi, base_o, H, v), axis=1)
            row["displacement_from_baseline_over_epsilon"] = {
                "median": float(np.median(np.abs(r)) / EPS),
                "p05": float(np.percentile(np.abs(r), 5) / EPS),
                "p95": float(np.percentile(np.abs(r), 95) / EPS),
            }
        res["cases"][c] = row
        print(c, gd["practical_gate_pass"], g32["practical_gate_pass"], len(removed), flush=True)
    res["all_practical_gates_pass"] = all(
        r["double_gates"]["practical_gate_pass"] and r["float32_stl_gates"]["practical_gate_pass"]
        for r in res["cases"].values()
    )
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "result.json").write_text(json.dumps(res, indent=1, allow_nan=False) + "\n")
    print("ALL PASS" if res["all_practical_gates_pass"] else "NOT ALL PASS")


if __name__ == "__main__":
    main(sys.argv[1])
