"""Report on a finished stage_t_python_loop run: histogram, volume fraction, and
the 0.5 iso-surface of the final accepted canonical density.

Tries the real Stage-T-to-Stage-S handoff (``build_density_to_sdf_handoff``)
first -- that is the actual downstream consumer, so success there is the
strongest evidence the design is usable as Stage S input. It raises if the
surface is not watertight, so this also always extracts the iso-surface
directly (pyvista contour + trimesh, the same technique the handoff uses
internally) to report face count / bounds / volume / watertightness /
component count regardless of whether the strict handoff accepts it.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pyvista as pv
import trimesh

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cfd_sdf.fixed_grid_primal import load_fixed_grid_density_state
from cfd_sdf.handoff import build_density_to_sdf_handoff

DEGENERATE_SIGNATURE = {
    "face_count": 5120,
    "component_count": 6,
    "bounds_lower": (-1.0, -0.8, -0.6),
    "bounds_upper": (2.0, 0.8, 0.6),
}


def direct_isosurface(topology_state_json: Path, iso_value: float = 0.5) -> dict:
    density_state = load_fixed_grid_density_state(topology_state_json)
    grid = density_state.grid
    rho = np.asarray(density_state.arrays["rho"], dtype=np.float64)

    image = pv.ImageData(
        dimensions=grid.point_dimensions, spacing=grid.spacing, origin=grid.origin
    )
    image.cell_data["rho"] = np.ascontiguousarray(rho)
    point_image = image.cell_data_to_point_data(pass_cell_data=False)
    point_rho = np.asarray(point_image.point_data["rho"], dtype=np.float64)

    result = {
        "iso_value": iso_value,
        "point_rho_range": [float(point_rho.min()), float(point_rho.max())],
    }
    if not (point_rho.min() < iso_value < point_rho.max()):
        result["ok"] = False
        result["reason"] = "iso_value is outside the interpolated point-density range"
        return result

    surface = point_image.contour(isosurfaces=[iso_value], scalars="rho").triangulate()
    if surface.n_points == 0 or surface.n_cells == 0:
        result["ok"] = False
        result["reason"] = "empty iso-surface"
        return result

    mesh = trimesh.Trimesh(
        vertices=np.asarray(surface.points),
        faces=np.asarray(surface.faces).reshape(-1, 4)[:, 1:],
        process=False,
    )
    components = mesh.split(only_watertight=False)
    result.update(
        {
            "ok": True,
            "face_count": int(len(mesh.faces)),
            "vertex_count": int(len(mesh.vertices)),
            "watertight": bool(mesh.is_watertight),
            "volume": float(mesh.volume) if mesh.is_watertight else None,
            "bounds_lower": [float(v) for v in mesh.bounds[0]],
            "bounds_upper": [float(v) for v in mesh.bounds[1]],
            "component_count": int(len(components)),
        }
    )
    return result


def density_histogram(topology_state_json: Path) -> dict:
    density_state = load_fixed_grid_density_state(topology_state_json)
    active = (
        (np.asarray(density_state.arrays["active_design_mask"]) > 0)
        & (np.asarray(density_state.arrays["allowed_mask"]) > 0)
        & ~(np.asarray(density_state.arrays["forbidden_mask"]) > 0)
        & ~(np.asarray(density_state.arrays["fixed_solid_mask"]) > 0)
    )
    rho = np.asarray(density_state.arrays["rho"], dtype=np.float64)[active]
    counts, edges = np.histogram(rho, bins=10, range=(0.0, 1.0))
    return {
        "active_cell_count": int(rho.size),
        "volume_fraction": float(rho.mean()),
        "cells_above_0.5": int(np.count_nonzero(rho > 0.5)),
        "bin_edges": [float(v) for v in edges],
        "bin_counts": [int(v) for v in counts],
    }


def main(loop_out_dir: Path) -> None:
    history = json.loads((loop_out_dir / "history.json").read_text())
    accepted = [row for row in history if row.get("accepted")]
    if not accepted:
        print("no accepted iterations; nothing to report")
        return
    final_row = accepted[-1]
    final_iter = final_row["iteration"]
    final_attempt = final_row.get("attempt", 0)
    final_state_json = (
        loop_out_dir
        / f"iter_{final_iter:03d}_attempt_{final_attempt:02d}"
        / "canonical_state"
        / "topology_state.json"
    )

    report: dict = {
        "n_iterations_recorded": len(history),
        "n_accepted": len(accepted),
        "final_iteration": final_iter,
        "final_state_json": str(final_state_json),
        "density_histogram": density_histogram(final_state_json),
        "direct_isosurface": direct_isosurface(final_state_json),
        "degenerate_signature_for_comparison": DEGENERATE_SIGNATURE,
    }

    try:
        artifacts = build_density_to_sdf_handoff(
            final_state_json, output_dir=loop_out_dir / "stage_s_handoff"
        )
        report["stage_s_handoff"] = {"ok": artifacts.ok, "manifest": dict(artifacts.manifest)}
    except (OSError, ValueError, FileExistsError) as exc:
        report["stage_s_handoff"] = {"ok": False, "error": str(exc)}

    out_path = loop_out_dir / "final_report.json"
    out_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps(report, indent=2, default=str))


if __name__ == "__main__":
    main(ROOT / "work" / (sys.argv[1] if len(sys.argv) > 1 else "stage_t_python_loop"))
