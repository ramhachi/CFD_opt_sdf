"""Stage the exact sampled GridSDF and VTK/trimesh seed for #44 Round 8.

This geometry-only command does not import or run WaterLily. Each output
directory is exclusive and its manifest binds the Float32 field, VTK seed,
parsed mesh payload, grid map, and this source file.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import trimesh

from cfd_sdf.export_vtk import export_zero_surface
from cfd_sdf.grid import UniformGrid
from cfd_sdf.sdf import FieldBundle


ORIGIN = np.array((-1.0, -0.8, -0.6), dtype=np.float64)
SPACING = 0.05
SHAPE = (61, 33, 25)
CENTER = np.array((0.0, 0.0, -0.2), dtype=np.float64)
FIXTURES = {
    "sphere": ("sphere", (0.25, 0.25, 0.25)),
    "plate_1cell": ("box", (0.25, 0.025, 0.25)),
    "plate_2cell": ("box", (0.25, 0.05, 0.25)),
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sampled_phi(fixture_id: str) -> np.ndarray:
    shape, extents = FIXTURES[fixture_id]
    axes = [ORIGIN[d] + SPACING * np.arange(SHAPE[d]) for d in range(3)]
    x, y, z = np.meshgrid(*axes, indexing="ij")
    if shape == "sphere":
        phi = np.sqrt((x - CENTER[0]) ** 2 + (y - CENTER[1]) ** 2 + (z - CENTER[2]) ** 2) - extents[0]
    else:
        qx = np.abs(x - CENTER[0]) - extents[0]
        qy = np.abs(y - CENTER[1]) - extents[1]
        qz = np.abs(z - CENTER[2]) - extents[2]
        outside = np.sqrt(np.maximum(qx, 0) ** 2 + np.maximum(qy, 0) ** 2 + np.maximum(qz, 0) ** 2)
        inside = np.minimum(np.maximum(np.maximum(qx, qy), qz), 0)
        phi = outside + inside
    return np.asarray(phi, dtype=np.float32, order="F")


def write_table(path: Path, values: np.ndarray) -> None:
    with path.open("x", encoding="ascii", newline="\n") as stream:
        for row in values:
            stream.write(",".join(str(int(value)) for value in row) + "\n")


def prepare(fixture_id: str, output_dir: Path) -> dict[str, object]:
    if fixture_id not in FIXTURES:
        raise ValueError(f"unsupported body fixture: {fixture_id}")
    output_dir.mkdir(parents=True, exist_ok=False)
    phi = sampled_phi(fixture_id)
    phi_path = output_dir / "canonical_phi_f32_fortran.bin"
    with phi_path.open("xb") as stream:
        stream.write(phi.tobytes(order="F"))
    bundle = FieldBundle(
        UniformGrid(origin=ORIGIN.copy(), spacing=SPACING, shape=SHAPE),
        {"design_phi": phi}, {},
    )
    seed_path = export_zero_surface(bundle, output_dir)
    if seed_path is None or not seed_path.is_file():
        raise RuntimeError("VTK produced no zero-surface seed")
    mesh = trimesh.load_mesh(seed_path, process=False)
    if not isinstance(mesh, trimesh.Trimesh) or len(mesh.faces) == 0:
        raise RuntimeError("VTK seed did not load as a non-empty triangular mesh")
    if not mesh.is_watertight or not mesh.is_winding_consistent or mesh.volume == 0:
        raise RuntimeError("VTK seed must be closed, consistently wound, and nonzero-volume; no repair is applied")
    vertices = np.asarray(mesh.vertices, dtype=np.float64)
    faces = np.asarray(mesh.faces, dtype=np.int64)
    vertices_path = output_dir / "seed_vertices.csv"
    faces_path = output_dir / "seed_faces.csv"
    np.savetxt(vertices_path, vertices, delimiter=",", fmt="%.17g")
    np.savetxt(faces_path, faces + 1, delimiter=",", fmt="%d")
    files = (phi_path, seed_path, vertices_path, faces_path)
    manifest: dict[str, object] = {
        "schema": "candidate-c-round8-surface-input-v1",
        "fixture_id": fixture_id,
        "phi_dtype": "float32-little-endian",
        "phi_array_order": "Fortran/i-fastest",
        "phi_shape": list(SHAPE),
        "grid_origin_m": ORIGIN.tolist(),
        "grid_spacing_m": SPACING,
        "phi_sha256": sha256(phi_path),
        "seed_mesh_sha256": sha256(seed_path),
        "seed_vertices_sha256": sha256(vertices_path),
        "seed_faces_1based_sha256": sha256(faces_path),
        "seed_vertex_count": int(len(vertices)),
        "seed_face_count": int(len(faces)),
        "seed_watertight": bool(mesh.is_watertight),
        "seed_winding_consistent": bool(mesh.is_winding_consistent),
        "seed_signed_volume_m3": float(mesh.volume),
        "seed_winding_relative_to_positive_volume": "outward" if mesh.volume > 0 else "inward",
        "preparation_source_sha256": sha256(Path(__file__)),
    }
    manifest_path = output_dir / "input_manifest.json"
    with manifest_path.open("x", encoding="utf-8") as stream:
        json.dump(manifest, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")
    (output_dir / "input_manifest.json.sha256").write_text(
        f"{sha256(manifest_path)}  input_manifest.json\n", encoding="ascii")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("fixture_id", choices=tuple(FIXTURES))
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()
    print(json.dumps(prepare(args.fixture_id, args.output_dir), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
