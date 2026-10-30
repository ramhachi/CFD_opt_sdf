#!/usr/bin/env python3
"""Replay frozen P22 volume inputs only; never register a limit or run a solver."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import tempfile

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]
from cfd_sdf.design.sdf_state import SDFDesignState
from cfd_sdf.design import volume_semantics as V
from cfd_sdf.fd08_v2_campaign import construct_state
import build_lowdim01_inputs as G
import step01_states as S

E = ROOT / "docs/evidence/p22_v17_volume_semantics_bridge_2026_10_11"
EXPECTED = {
    "v16_reference": ("3d2cd6c1b4c6d03cc166eed8a9a46472ff697d95315dd8c22f6828bca59e43fe", "44507748807dfbff995eb146866776b4a292e2fa2ddfe6caa5c3a611c29f6de8"),
    "v17_baseline": ("7a972b330c11d6580c49de4cba9b5f4a0b2cb664dda67e4f7053c280655feb31", "02f48f6488be4f5d772c3ec515d4860b00e0e4a84d38aa56b187c82c1a615dcb"),
    "lowdim03_parent": ("0ce3256b0f3e5c919caeb2ac1b36f1a33838f34c767c091cb89bda0234ac750b", "81d24fe4a66704ed469f560b7396b4c0cbf6810ef8082e710f002145ca6e3a65"),
}
SURFACE_SHA = "5e6d210794b55a11f3dc76b8be37eeb39d27579b341212939a1c2a63d2fb8d11"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def canonical(value):
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()


def load_checked(label, path):
    file_hash, state_hash = EXPECTED[label]
    if sha(path) != file_hash:
        raise ValueError(f"{label}: NPZ identity mismatch")
    state = SDFDesignState.load(path)
    if state.state_sha256 != state_hash:
        raise ValueError(f"{label}: state identity mismatch")
    return state


def measure(label, state, path):
    hard = V.sharp_volume_m3(state)
    smooth = V.smoothed_volume_and_gradient(state)
    lowdim = G.geometry(state)
    if lowdim["sharp_volume_m3"] != hard or lowdim["smoothed_volume_m3"] != smooth.smoothed_volume_m3:
        raise ValueError("LOWDIM/P22 evaluator drift")
    centers = V._corner_mean(state.phi)
    return {
        "label": label, "input_path": path.relative_to(ROOT).as_posix(),
        "input_npz_sha256": sha(path), "state_sha256": state.state_sha256,
        "phi_c_order_sha256": state.phi_sha256(),
        "phi_fortran_sha256": hashlib.sha256(S.to_raw(state.phi)).hexdigest(),
        "source_surface_sha256": state.source_sha256,
        "point_shape": list(state.shape), "cell_shape": list(centers.shape),
        "origin_m": list(state.origin_m), "spacing_m": state.spacing_m,
        "phi_dtype": str(state.phi.dtype), "center_dtype": str(centers.dtype),
        "total_sampled_centers": int(centers.size),
        "solid_sampled_centers": V.sampled_solid_centers_count(state),
        "exact_zero_centers_fluid": int(np.count_nonzero(centers == 0)),
        "p22_hard_sharp_m3": hard, "p22_smooth": smooth.to_dict(),
        "lowdim_geometry": {k: lowdim[k] for k in ("sharp_volume_m3", "smoothed_volume_m3")},
        "node_occupancy_diagnostic": {"solid_nodes": int(np.count_nonzero(state.phi < 0)), "volume_m3": V.node_occupancy_volume_m3(state), "constraint_authority": False},
    }


def replay():
    inventory = json.loads((E / "measure_inventory.json").read_text())
    for record in inventory["source_files"]:
        if sha(ROOT / record["path"]) != record["sha256"]:
            raise ValueError(f"evaluator/source drift: {record['path']}")
    registration_path = ROOT / "docs/evidence/sdf_native_volume_semantics_v1_2026_09.json"
    if sha(registration_path) != V.SMOOTHED_VOLUME_LIMIT_SOURCE_SHA256:
        raise ValueError("original P22 registration identity mismatch")
    registration = json.loads(registration_path.read_text())
    a_path, b_path = (E / "inputs" / f"{name}.npz" for name in ("v16_reference", "v17_baseline"))
    a = load_checked("v16_reference", a_path)
    # Required fail-closed Q1 gate precedes any B/C measurement.
    if (V.sharp_volume_m3(a) != registration["measured"]["volume_m3"]
            or registration["measured"]["volume_m3"] != 0.12612500000000004
            or V.sampled_solid_centers_count(a) != registration["measured"]["sampled_solid_centers"]
            or a.state_sha256 != registration["measured"]["state_sha256"]
            or sha(a_path) != registration["input_lineage"]["genesis_state_npz"]["sha256"]):
        raise ValueError("INCONCLUSIVE: original P22 reference does not reproduce exactly")
    b = load_checked("v17_baseline", b_path)
    source = E / "inputs/reference_surface.stl"
    if sha(source) != SURFACE_SHA or a.source_sha256 != SURFACE_SHA or b.source_sha256 != SURFACE_SHA:
        raise ValueError("INCONCLUSIVE: physical reference source identity mismatch")
    inventory = json.loads((ROOT / "docs/evidence/lowdim03_dual_grid_primal_2026_10_10/inventory.json").read_text())
    proposal = ROOT / inventory["proposal"]["file"]
    if sha(proposal) != inventory["proposal"]["sha256_fortran_raw"]:
        raise ValueError("saved direction identity mismatch")
    c, audit = construct_state(b, S.read_f4(proposal), 1.25, 1)
    if c.state_sha256 != EXPECTED["lowdim03_parent"][1]:
        raise ValueError("selected parent identity mismatch")
    c_path = E / "inputs/lowdim03_parent.npz"
    with tempfile.TemporaryDirectory() as tmp:
        generated = Path(tmp) / "parent.npz"
        c.save(generated)
        load_checked("lowdim03_parent", generated)
        if generated.read_bytes() != c_path.read_bytes():
            raise ValueError("reconstruction differs from retained parent NPZ")
    load_checked("lowdim03_parent", c_path)
    rows = [measure(label, state, path) for label, state, path in (
        ("v16_reference", a, a_path), ("v17_baseline", b, b_path), ("lowdim03_parent", c, c_path))]
    masks = ("design_mask", "fixed_solid_mask", "forbidden_mask", "root_mask")
    return {
        "schema_version": 1, "evidence_class": "solver_free_contract_arithmetic_and_lineage",
        "integration_parent_sha": "0973f9efc7c7f469978d67c77a95fcfd365d58d5",
        "q1_exact_original_reference_reproduction": True, "states": rows,
        "parent_minus_v17_baseline_hard_m3": rows[2]["p22_hard_sharp_m3"] - rows[1]["p22_hard_sharp_m3"],
        "parent_minus_v17_baseline_smooth_m3": rows[2]["p22_smooth"]["smoothed_volume_m3"] - rows[1]["p22_smooth"]["smoothed_volume_m3"],
        "v17_baseline_minus_v16_reference_hard_m3": rows[1]["p22_hard_sharp_m3"] - rows[0]["p22_hard_sharp_m3"],
        "lattice_identity": {
            "same_origin": a.origin_m == b.origin_m,
            "same_physical_bounds": np.array_equal(np.asarray(a.origin_m) + (np.asarray(a.shape)-1)*a.spacing_m, np.asarray(b.origin_m) + (np.asarray(b.shape)-1)*b.spacing_m),
            "v17_spacing_is_v16_half": b.spacing_m == a.spacing_m / 2,
            "v17_common_nodes_bitwise_equal_v16": bool(np.array_equal(b.phi[::2, ::2, ::2].view("<u4"), a.phi.view("<u4"))),
            "same_source_surface_sha256": SURFACE_SHA,
            "v16_v17_identical_trilinear_zero_sets_claimed": False,
            "v16_v17_center_sets": "origin+(i+0.5)*h; h16=0.05, h17=0.025; disjoint center sets, 8x as many samples",
            "parent_masks_equal_baseline": all(np.array_equal(getattr(c, m), getattr(b, m)) for m in masks),
        },
        "parent_reconstruction": {"function": "cfd_sdf.fd08_v2_campaign.construct_state", "saved_direction_path": proposal.relative_to(ROOT).as_posix(), "saved_direction_sha256": sha(proposal), "step_mm": 1.25, "sign": 1, "audit": audit, "proposal_recomputed": False},
        "lowdim_geometry_sharp_callable_is_p22_callable": G.sharp_volume_m3 is V.sharp_volume_m3,
        "d_states_replayed": False,
        "d_omission_reason": "A-C plus the traced direct #51 evaluator resolve the bridge; eight retained D records remain unchanged.",
        "cfd_runs": 0, "threshold_changed": False, "shape_update_allowed": False,
    }


def check_source():
    """Re-use the genesis mapper; compare source replay to retained evidence."""
    import trimesh
    from sdf_native_genesis_v17_2026_09 import resample

    source = E / "inputs/reference_surface.stl"
    if sha(source) != SURFACE_SHA:
        raise ValueError("physical reference source identity mismatch")
    mesh = trimesh.load(source, force="mesh")
    diagnostic = json.loads((E / "source_surface_volume_diagnostic.json").read_text())
    if float(mesh.volume) != diagnostic["signed_mesh_volume_m3"]:
        raise ValueError("source mesh volume differs from saved diagnostic")
    observed = {}
    for label in ("v16_reference", "v17_baseline"):
        state = load_checked(label, E / "inputs" / f"{label}.npz")
        phi = resample(mesh, state.origin_m, state.spacing_m, state.shape)
        equal = bool(np.array_equal(phi.view("<u4"), state.phi.view("<u4")))
        if not equal:
            raise ValueError(f"INCONCLUSIVE: source replay differs for {label}")
        observed[label] = {
            "max_absolute_phi_difference_m": float(np.max(np.abs(phi.astype(np.float64) - state.phi))),
            "phi_bitwise_equal": equal,
            "phi_c_sha256": hashlib.sha256(phi.astype("<f4").tobytes()).hexdigest(),
        }
    expected = json.loads((E / "source_geometry_replay.json").read_text())
    if observed != expected["states"] or expected["source_stl_sha256"] != SURFACE_SHA:
        raise ValueError("source replay differs from saved evidence")
    print("Source geometry replay assertions PASS")


def check_history():
    """Verify executable hard semantics against the original Git registration."""
    import ast
    import subprocess

    record = json.loads((E / "hard_evaluator_history.json").read_text())
    original = subprocess.check_output(
        ["git", "show", f"{record['registration_commit']}:{record['source_path']}"],
        cwd=ROOT, text=True,
    )
    for source in (original, (ROOT / record["source_path"]).read_text()):
        observed = {}
        for node in ast.parse(source).body:
            if isinstance(node, ast.FunctionDef) and node.name in record["functions"]:
                if ast.get_docstring(node):
                    node.body = node.body[1:]
                observed[node.name] = hashlib.sha256(ast.dump(node, include_attributes=False).encode()).hexdigest()
        if observed != record["functions"]:
            raise ValueError("INCONCLUSIVE: registered hard evaluator implementation drift")
    print("Hard evaluator history assertions PASS")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--check-source", action="store_true", help="also resample the frozen STL on both lattices")
    parser.add_argument("--check-history", action="store_true", help="also compare hard functions to original Git registration")
    args = parser.parse_args()
    output = canonical(replay())
    target = E / "volume_semantics_comparison.json"
    if args.check:
        if target.read_bytes() != output:
            raise SystemExit("recomputed comparison differs from saved evidence")
    else:
        if target.exists():
            raise SystemExit("refusing to overwrite saved comparison")
        target.write_bytes(output)
    print("P22 replay assertions PASS", hashlib.sha256(output).hexdigest())
    if args.check_source:
        check_source()
    if args.check_history:
        check_history()


if __name__ == "__main__":
    main()
