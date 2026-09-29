"""SDF genesis v17 (#43): the v16 source surface resampled on an h/2 design lattice.

v16 samples the registered surface STL on the h=0.05 m point lattice.  The surface
has 1-cell-thick plates whose faces lie on lattice nodes, so every corner of 66
force-band cells samples phi = 0 and the trilinear gradient vanishes (#36).  v17
keeps the same source surface, design box, origin and sign convention and samples
the exact signed distance at h/2.  Masks are the v16 source cell masks refined
2x per axis and projected with the unchanged genesis policies.

Reproduction gate: the same resampling code at refine=1 must reproduce the v16 phi
bit-for-bit, proving v17 differs from v16 only by lattice spacing.

usage: python scripts/sdf_native_genesis_v17_2026_09.py [--register]
Without --register only the work/ state is written (no evidence file).
"""

from __future__ import annotations

import hashlib
import json
import platform
import sys
from pathlib import Path
from typing import Any

import numpy as np
import trimesh

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cfd_sdf.design.genesis import (  # noqa: E402
    GENESIS_MASK_PROJECTION_POLICY,
    _project_design_strict,
    _project_mask_any_adjacent,
    _read_cell_grid,
    _read_json_object,
    _resolve_artifact_path,
)
from cfd_sdf.design.sdf_state import SDFDesignState  # noqa: E402
from cfd_sdf.sdf import signed_distance  # noqa: E402

V16_EVIDENCE = ROOT / "docs/evidence/sdf_native_genesis_v16_2026_09.json"
HANDOFF_MANIFEST = ROOT / "work/pq4_1_v16_state_v2/sweep/threshold_0.5/handoff_manifest.json"
V16_STATE = ROOT / "work/sdf_native_genesis_v16/sdf_design_state.npz"
OUTPUT_DIR = ROOT / "work/sdf_native_genesis_v17"
EVIDENCE_PATH = ROOT / "docs/evidence/sdf_native_genesis_v17_2026_09.json"
REFINE = 2
# Registered before any v17 value is seen: a force-band cell (|phi(center)| <= FORCE_BAND_M)
# fails when its trilinear center gradient magnitude is below FLAT_GRADIENT_THRESHOLD.
FORCE_BAND_M = 0.05
FLAT_GRADIENT_THRESHOLD = 0.25


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_immutable(path: Path, payload: bytes) -> None:
    if path.exists():
        if path.read_bytes() == payload:
            return
        raise SystemExit(f"refusing to overwrite immutable artifact: {path.relative_to(ROOT)}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


def resample(mesh, origin, spacing, point_shape) -> np.ndarray:
    axes = [origin[a] + spacing * np.arange(point_shape[a]) for a in range(3)]
    points = np.stack(np.meshgrid(*axes, indexing="ij"), axis=-1).reshape(-1, 3)
    return signed_distance(mesh, points).reshape(point_shape).astype(np.float32)


def refine_cells(mask: np.ndarray, factor: int) -> np.ndarray:
    for axis in range(3):
        mask = np.repeat(mask, factor, axis=axis)
    return mask


def gradient_census(phi: np.ndarray, spacing: float) -> dict[str, Any]:
    """Trilinear value/gradient at every cell center (same polynomial as the bridge)."""
    p = phi.astype(np.float64)
    n = [s - 1 for s in p.shape]
    c = {(i, j, k): p[i:n[0] + i, j:n[1] + j, k:n[2] + k] for i in (0, 1) for j in (0, 1) for k in (0, 1)}
    center = sum(c.values()) / 8.0
    gx = sum(c[(1, j, k)] - c[(0, j, k)] for j in (0, 1) for k in (0, 1)) / (4.0 * spacing)
    gy = sum(c[(i, 1, k)] - c[(i, 0, k)] for i in (0, 1) for k in (0, 1)) / (4.0 * spacing)
    gz = sum(c[(i, j, 1)] - c[(i, j, 0)] for i in (0, 1) for j in (0, 1)) / (4.0 * spacing)
    g = np.sqrt(gx * gx + gy * gy + gz * gz)[np.abs(center) <= FORCE_BAND_M]
    flat = int((g < FLAT_GRADIENT_THRESHOLD).sum())
    return {
        "force_band_m": FORCE_BAND_M,
        "flat_gradient_threshold": FLAT_GRADIENT_THRESHOLD,
        "force_band_cells": int(g.size),
        "cells_gradient_below_1e-6": int((g < 1e-6).sum()),
        "cells_gradient_below_threshold": flat,
        "gradient_quantiles": {q: float(np.quantile(g, float(q))) for q in ("0.01", "0.05", "0.5", "0.95")},
        "near_zero_nodes_abs_phi_below_1e-7": int((np.abs(phi) < 1e-7).sum()),
        "verdict": "pass" if flat == 0 else "fail",
    }


def build(register: bool) -> dict[str, Any]:
    v16 = json.loads(V16_EVIDENCE.read_text())
    manifest_sha = sha256_path(HANDOFF_MANIFEST)
    if manifest_sha != v16["lineage"]["handoff_manifest"]["sha256"]:
        raise SystemExit("handoff manifest hash differs from the v16 genesis lineage")
    manifest = _read_json_object(HANDOFF_MANIFEST, field_name="handoff manifest")
    artifacts = manifest["artifacts"]
    stl_path = _resolve_artifact_path(HANDOFF_MANIFEST, artifacts, "surface_stl", suffix=".stl")
    density_path = _resolve_artifact_path(HANDOFF_MANIFEST, artifacts, "source_density_vti", suffix=".vti")
    stl_sha = sha256_path(stl_path)
    if stl_sha != v16["lineage"]["surface_stl_sha256"] or stl_sha != artifacts["surface_stl"]["sha256"]:
        raise SystemExit("surface STL hash differs from the v16 lineage")
    if sha256_path(density_path) != artifacts["source_density_vti"]["sha256"]:
        raise SystemExit("source density VTI hash differs from the handoff manifest")

    mesh = trimesh.load(stl_path, force="mesh")
    origin = tuple(v16["grid_identity"]["origin_m"])
    h16 = float(v16["grid_identity"]["spacing_m"])
    shape16 = tuple(v16["grid_identity"]["point_shape"])
    v16_state = SDFDesignState.load(V16_STATE)
    if v16_state.state_sha256 != v16["state"]["state_sha256"]:
        raise SystemExit("v16 state file does not match its genesis evidence")

    phi16 = resample(mesh, origin, h16, shape16)
    reproduction = {
        "bitwise_equal": bool(np.array_equal(phi16, v16_state.phi)),
        "max_abs_difference_m": float(np.max(np.abs(phi16.astype(np.float64) - v16_state.phi))),
    }
    if not reproduction["bitwise_equal"]:
        raise SystemExit(f"refine=1 resampling does not reproduce v16 phi: {reproduction}")

    cell_origin, cell_spacing, cell_shape, masks, _ = _read_cell_grid(density_path)
    if tuple(round(v, 12) for v in cell_origin) != tuple(round(v, 12) for v in origin):
        raise SystemExit("source cell grid origin drifted")
    h17 = h16 / REFINE
    shape17 = tuple(REFINE * (s - 1) + 1 for s in shape16)
    fine = {name: refine_cells(mask, REFINE) for name, mask in masks.items()}
    phi17 = resample(mesh, origin, h17, shape17)
    state = SDFDesignState.create(
        phi=phi17,
        origin_m=origin,
        spacing_m=h17,
        design_mask=_project_design_strict(fine["active_design_mask"]),
        fixed_solid_mask=_project_mask_any_adjacent(fine["fixed_solid_mask"]),
        forbidden_mask=_project_mask_any_adjacent(fine["forbidden_mask"]),
        root_mask=_project_mask_any_adjacent(fine["root_mask"]),
        narrow_band_width_m=h17,
        generation=0,
        source_sha256=stl_sha,
    )
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    state_path = OUTPUT_DIR / "sdf_design_state.npz"
    state.save(state_path)
    phi_f = OUTPUT_DIR / "canonical_v17_phi_f4_fortran.raw"
    phi_f.write_bytes(np.asfortranarray(phi17).tobytes(order="F"))

    census16 = gradient_census(v16_state.phi, h16)
    census17 = gradient_census(phi17, h17)
    return {
        "schema_version": 1,
        "kind": "sdf_native_genesis_v17",
        "genesis_id": "sdf_native_genesis_v17_2026_09",
        "issue": "#43",
        "evidence_class": "contract_and_capability",
        "immutable": True,
        "solver_started": False,
        "existing_evidence_modified": False,
        "supersedes_for_fd": "sdf_native_genesis_v16_2026_09 (v16 is unchanged and remains valid history)",
        "motivation": "#36: v16 has 66 force-band cells with near-zero trilinear gradient from 1-cell-thick plates whose faces lie on h=0.05 nodes",
        "mask_projection_policy": GENESIS_MASK_PROJECTION_POLICY,
        "mask_refinement": f"source cell masks repeated {REFINE}x per axis, then projected with the v16 genesis policies",
        "environment": {"python": sys.version.split()[0], "platform": platform.platform(),
                        "numpy": np.__version__, "trimesh": trimesh.__version__},
        "lineage": {
            "v16_genesis_evidence": {"path": V16_EVIDENCE.relative_to(ROOT).as_posix(), "sha256": sha256_path(V16_EVIDENCE)},
            "handoff_manifest_sha256": manifest_sha,
            "surface_stl_sha256": stl_sha,
            "source_density_vti_sha256": artifacts["source_density_vti"]["sha256"],
        },
        "reproduction_gate_refine_1_vs_v16": reproduction,
        "grid_identity": {"location": "point", "origin_m": list(origin), "spacing_m": h17,
                          "point_shape": list(shape17), "cell_shape": [s - 1 for s in shape17]},
        "state": {
            "state_sha256": state.state_sha256,
            "phi_sha256": state.phi_sha256(),
            "state_path": state_path.relative_to(ROOT).as_posix(),
            "state_file_sha256": sha256_path(state_path),
            "phi_f4_fortran_path": phi_f.relative_to(ROOT).as_posix(),
            "phi_f4_fortran_sha256": sha256_path(phi_f),
        },
        "mask_point_counts": {
            "design": int(state.design_mask.sum()), "fixed_solid": int(state.fixed_solid_mask.sum()),
            "forbidden": int(state.forbidden_mask.sum()), "root": int(state.root_mask.sum()),
        },
        "force_band_gradient_gate": {"v16_reference": census16, "v17": census17},
        "claims_supported": [
            "v17 is the registered v16 source surface sampled at h/2 with the same resampling code that reproduces v16 bit-for-bit at h",
            "the force-band trilinear gradient census of v16 and v17 at design-cell centers",
        ],
        "claims_not_supported": [
            "no WaterLily primal, FD oracle, SDF gradient, optimizer or physical qualification",
            "the census is at design-cell centers, not at WaterLily flow sample points",
            "v16 qualification evidence (W1-W4, FD rounds) does not transfer to v17",
        ],
        "flags": {"shape_update_allowed": False, "sdf_gradient_qualified": False,
                  "topology_birth_qualified": False, "registered": register},
    }


def main() -> None:
    register = "--register" in sys.argv[1:]
    evidence = build(register)
    summary = {k: evidence[k] for k in ("reproduction_gate_refine_1_vs_v16", "grid_identity", "mask_point_counts")}
    summary["census"] = {k: {x: v[x] for x in ("force_band_cells", "cells_gradient_below_1e-6", "cells_gradient_below_threshold", "verdict")}
                         for k, v in evidence["force_band_gradient_gate"].items()}
    summary["state_sha256"] = evidence["state"]["state_sha256"]
    if register:
        payload = (json.dumps(evidence, indent=2, ensure_ascii=False, sort_keys=True) + "\n").encode()
        write_immutable(EVIDENCE_PATH, payload)
        write_immutable(EVIDENCE_PATH.with_suffix(".json.sha256"), (sha256_path(EVIDENCE_PATH) + "\n").encode())
        summary["evidence_sha256"] = sha256_path(EVIDENCE_PATH)
    print(json.dumps(summary, indent=1, sort_keys=True))


if __name__ == "__main__":
    main()
