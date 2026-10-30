#!/usr/bin/env python3
"""Rebuild and audit the exact seven #45 GridSDF zero-level surfaces."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sys
from pathlib import Path

import numpy as np
import pyvista
import trimesh
import vtk

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cfd_sdf.design.sdf_state import SDFDesignState  # noqa: E402
from cfd_sdf.export_vtk import export_zero_surface  # noqa: E402
from cfd_sdf.gradients.directional_fd import (  # noqa: E402
    DIRECTION_IDS,
    direction_sha256,
    generate_directions,
    perturbed_state,
    phi_sha256,
)
from cfd_sdf.grid import UniformGrid  # noqa: E402
from cfd_sdf.sdf import FieldBundle  # noqa: E402

EXPECTED_STATE_FILE_SHA256 = "7a972b330c11d6580c49de4cba9b5f4a0b2cb664dda67e4f7053c280655feb31"
EXPECTED_STATE_SHA256 = "02f48f6488be4f5d772c3ec515d4860b00e0e4a84d38aa56b187c82c1a615dcb"
EXPECTED_PHI_FORTRAN_SHA256 = "e3966d87c0ddb0d3ff9a6ee096c94221d0d4cccff77221ba84987ef5faa04431"
EPSILON_M = 0.005
FLOW_DOMAIN = ((-2.5, -1.2, -0.9), (2.5, 1.2, 0.9))
MINIMUM_STAGE_V_CLEARANCE_M = 0.25


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def audit_surface(path: Path) -> dict:
    mesh = trimesh.load_mesh(path, process=False, force="mesh")
    if not isinstance(mesh, trimesh.Trimesh) or mesh.is_empty:
        raise ValueError(f"invalid or empty surface: {path}")
    # Merge coincident STL vertices only in this in-memory topology inspection.
    # The retained source STL bytes and geometry are never changed.
    mesh.merge_vertices()
    edge_counts = np.unique(np.sort(mesh.edges_sorted, axis=1), axis=0, return_counts=True)[1]
    unique_faces = np.unique(np.sort(mesh.faces, axis=1), axis=0).shape[0]
    bounds = np.asarray(mesh.bounds, dtype=np.float64)
    lower, upper = (np.asarray(row, dtype=np.float64) for row in FLOW_DOMAIN)
    clearances = np.minimum(bounds[0] - lower, upper - bounds[1])
    checks = {
        "watertight": bool(mesh.is_watertight),
        "winding_consistent": bool(mesh.is_winding_consistent),
        "non_manifold_edge_count": int(np.count_nonzero(edge_counts != 2)),
        "duplicate_face_count": int(len(mesh.faces) - unique_faces),
        "positive_signed_volume": bool(mesh.volume > 0.0),
        "inside_stage_v_domain": bool(np.all(clearances >= 0.0)),
        "stage_v_clearance_at_least_0p25_m": bool(np.min(clearances) >= MINIMUM_STAGE_V_CLEARANCE_M),
    }
    return {
        "stl_sha256": sha256_bytes(path.read_bytes()),
        "vertex_count_after_coincident_vertex_merge_for_audit_only": int(len(mesh.vertices)),
        "triangle_count": int(len(mesh.faces)),
        "checks": checks,
        "status": "pass" if all(checks.values()) else "fail",
        "watertight": bool(mesh.is_watertight),
        "winding_consistent": bool(mesh.is_winding_consistent),
        "non_manifold_edge_count": int(np.count_nonzero(edge_counts != 2)),
        "boundary_edge_count": int(np.count_nonzero(edge_counts == 1)),
        "edges_used_by_more_than_two_faces": int(np.count_nonzero(edge_counts > 2)),
        "duplicate_face_count": int(len(mesh.faces) - unique_faces),
        "signed_volume_m3": float(mesh.volume),
        "bounds_m": bounds.tolist(),
        "stage_v_clearances_by_axis_m": clearances.tolist(),
        "minimum_stage_v_clearance_m": float(np.min(clearances)),
        "topology_audit_note": "Coincident STL vertices are merged in memory for edge-incidence inspection only; no repair, reorientation, smoothing, or source-file rewrite is applied.",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", type=Path, required=True, help="registered canonical v17 state NPZ")
    parser.add_argument("--output", type=Path, required=True, help="new evidence output directory")
    args = parser.parse_args()
    state_path = args.state.resolve()
    out_dir = args.output.resolve()
    if not state_path.is_file():
        raise SystemExit(f"missing canonical state: {state_path}")
    if out_dir.exists() and any(out_dir.iterdir()):
        raise SystemExit(f"refusing to overwrite non-empty output: {out_dir}")
    out_dir.mkdir(parents=True, exist_ok=True)

    state_file_sha = sha256_bytes(state_path.read_bytes())
    if state_file_sha != EXPECTED_STATE_FILE_SHA256:
        raise SystemExit("canonical v17 state file hash mismatch")
    state = SDFDesignState.load(state_path)
    if state.state_sha256 != EXPECTED_STATE_SHA256 or phi_sha256(state.phi, order="F") != EXPECTED_PHI_FORTRAN_SHA256:
        raise SystemExit("canonical v17 state or Fortran phi identity mismatch")
    state_copy = out_dir / "canonical_state.npz"
    state_copy.write_bytes(state_path.read_bytes())

    cases: dict[str, tuple[SDFDesignState, dict | None]] = {"baseline": (state, None)}
    direction_rows = {}
    for direction_id, direction in generate_directions(state).items():
        direction_rows[direction_id] = {"raw_sha256_float32_c_order": direction_sha256(direction)}
        for sign, label in ((-1, "minus"), (1, "plus")):
            child, identity = perturbed_state(state, direction, epsilon_m=EPSILON_M, sign=sign)
            case_id = f"{direction_id}_{label}"
            cases[case_id] = (child, identity)
            direction_rows[direction_id][label] = identity

    surface_rows = {}
    for case_id, (case_state, perturbation) in cases.items():
        case_dir = out_dir / "surfaces" / case_id
        ply = export_zero_surface(
            FieldBundle(
                grid=UniformGrid(np.asarray(case_state.origin_m), case_state.spacing_m, case_state.shape),
                arrays={"design_phi": case_state.phi},
                component_labels={},
            ),
            case_dir / "canonical_export",
        )
        if ply is None:
            raise SystemExit(f"canonical zero-level exporter returned no surface for {case_id}")
        # Save the exact project PLY output, then serialize its triangles as STL
        # without processing, cleanup, reorientation, or smoothing.
        mesh = trimesh.load_mesh(ply, process=False, force="mesh")
        if not isinstance(mesh, trimesh.Trimesh) or mesh.is_empty:
            raise SystemExit(f"canonical PLY is not a nonempty triangle mesh: {case_id}")
        stl = case_dir / "design_candidate.stl"
        stl.write_bytes(mesh.export(file_type="stl"))
        audit = audit_surface(stl)
        surface_rows[case_id] = {
            "state_sha256": case_state.state_sha256,
            "phi_c_order_sha256": phi_sha256(case_state.phi, order="C"),
            "phi_fortran_order_sha256": phi_sha256(case_state.phi, order="F"),
            "perturbation": perturbation,
            "ply_relative_path": ply.relative_to(ROOT).as_posix(),
            "ply_sha256": sha256_bytes(ply.read_bytes()),
            "stl_relative_path": stl.relative_to(ROOT).as_posix(),
            **audit,
        }

    source_paths = (
        "scripts/audit_xfid45_geometry_preflight_2026_10_03.py",
        "src/cfd_sdf/gradients/directional_fd.py",
        "src/cfd_sdf/design/sdf_state.py",
        "src/cfd_sdf/grid.py",
        "src/cfd_sdf/sdf.py",
        "src/cfd_sdf/export_vtk.py",
    )
    payload = {
        "schema_version": 1,
        "kind": "xfid01_geometry_preflight",
        "issue": 45,
        "date": "2026-10-03",
        "evidence_class": "solver_free_geometry_input_preflight",
        "formal_criteria_registered": False,
        "solver_started": False,
        "verdict": "UNRESOLVED",
        "stop_reason": "The required baseline GridSDF zero-level surface fails watertightness, winding/manifold, and positive-volume checks. No candidate direction is substituted; no solver or mesh run is started.",
        "canonical_state": {
            "path": state_copy.relative_to(ROOT).as_posix(),
            "file_sha256": state_file_sha,
            "state_sha256": state.state_sha256,
            "phi_fortran_sha256": phi_sha256(state.phi, order="F"),
            "phi_c_order_sha256": phi_sha256(state.phi, order="C"),
            "shape": list(state.shape),
            "origin_m": list(state.origin_m),
            "spacing_m": state.spacing_m,
            "narrow_band_width_m": state.narrow_band_width_m,
        },
        "direction_contract": {
            "source": "src/cfd_sdf/gradients/directional_fd.py::generate_directions",
            "direction_ids": list(DIRECTION_IDS),
            "normalization": "Float32; unconstrained nodes zero; max absolute magnitude normalized to 1",
            "narrow_band": "metadata-declared canonical state narrow_band_width_m, with cosine taper",
            "primary_epsilon_m": EPSILON_M,
            "primary_epsilon_over_h": EPSILON_M / state.spacing_m,
            "filter": "PCG64 seeds 11 and 2026; two passes over each axis with reflect padding and [1,4,6,4,1]/16; subtract weighted mean",
            "directions": direction_rows,
        },
        "surface_export": {
            "project_exporter": "cfd_sdf.export_vtk.export_zero_surface",
            "algorithm": "PyVista ImageData.contour(isosurfaces=[0.0], scalars='design_phi')",
            "stl_serialization": "trimesh export of the PLY triangles with process=False",
            "smoothing": False,
            "manual_repair": False,
            "reorientation": False,
            "mesh_cleanup": False,
            "domain_bounds_m": [list(FLOW_DOMAIN[0]), list(FLOW_DOMAIN[1])],
            "clearance_profile_id": "stage_v_clearance_v1",
            "clearance_profile_minimum_m": MINIMUM_STAGE_V_CLEARANCE_M,
            "cases": surface_rows,
        },
        "runtime": {
            "python": platform.python_version(),
            "numpy": np.__version__,
            "pyvista": pyvista.__version__,
            "vtk": vtk.vtkVersion.GetVTKVersion(),
            "trimesh": trimesh.__version__,
        },
        "source_sha256": {path: sha256_bytes((ROOT / path).read_bytes()) for path in source_paths},
        "qualification_flags": {
            "shape_update_allowed": False,
            "fd_oracle": False,
            "field_gradient": False,
            "reverse": False,
            "optimizer": False,
            "topology": False,
        },
    }
    audit_path = out_dir / "geometry_audit.json"
    audit_path.write_text(json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n")
    print(json.dumps({"audit_path": audit_path.as_posix(), "baseline_status": surface_rows["baseline"]["status"], "direction_statuses": {key: value["status"] for key, value in surface_rows.items()}, "verdict": payload["verdict"]}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
