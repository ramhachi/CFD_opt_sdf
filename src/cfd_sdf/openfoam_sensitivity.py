from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class OpenFoamSurfaceSensitivityExport:
    source_sensitivity: Path
    output_csv: Path
    patches: list[str]
    point_count: int
    min_sensitivity: float
    max_sensitivity: float
    downforce_sensitivity_mode: str = "negative-of-objective-faceSensNormal"
    drag_sensitivity_mode: str = "zero-filled-not-provided-by-faceSensNormal"

    def to_dict(self) -> dict[str, object]:
        return {
            "source_sensitivity": str(self.source_sensitivity),
            "output_csv": str(self.output_csv),
            "patches": self.patches,
            "point_count": self.point_count,
            "min_sensitivity": self.min_sensitivity,
            "max_sensitivity": self.max_sensitivity,
            "downforce_sensitivity_mode": self.downforce_sensitivity_mode,
            "drag_sensitivity_mode": self.drag_sensitivity_mode,
            "constraint_sensitivity_note": (
                "OpenFOAM faceSensNormal is parsed as a scalar negative-lift "
                "objective sensitivity; drag sensitivity is not available from "
                "this field and is zero-filled."
            ),
        }


def export_openfoam_surface_sensitivity_to_csv(
    *,
    case_dir: Path,
    sensitivity_file: Path,
    output_csv: Path,
    patches: list[str],
) -> OpenFoamSurfaceSensitivityExport:
    """Convert OpenFOAM faceSensNormal volScalarField output to normalized CSV."""
    boundary = _read_boundary(case_dir / "constant" / "polyMesh" / "boundary")
    selected = [patch for patch in patches if patch in boundary]
    if not selected:
        raise ValueError(f"No requested sensitivity patches found in boundary file: {patches}")

    points = _read_points(case_dir / "constant" / "polyMesh" / "points")
    face_ranges = [(boundary[patch]["startFace"], boundary[patch]["nFaces"]) for patch in selected]
    faces = _read_selected_faces(case_dir / "constant" / "polyMesh" / "faces", face_ranges)
    sensitivity_by_patch = _read_boundary_scalar_values(sensitivity_file, boundary)

    output_csv.parent.mkdir(parents=True, exist_ok=True)
    values_written: list[float] = []
    with output_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "x",
                "y",
                "z",
                "objective_surface_sensitivity",
                "downforce_surface_sensitivity",
                "drag_surface_sensitivity",
                "source_patch",
                "source_face",
            ],
        )
        writer.writeheader()
        for patch in selected:
            start = int(boundary[patch]["startFace"])
            n_faces = int(boundary[patch]["nFaces"])
            values = sensitivity_by_patch.get(patch)
            if values is None:
                raise ValueError(f"Sensitivity field does not contain patch values for {patch}")
            if len(values) != n_faces:
                raise ValueError(f"Patch {patch} has {n_faces} faces but {len(values)} sensitivity values")
            for local_face, sens in enumerate(values):
                face_index = start + local_face
                center = _face_center(points, faces[face_index])
                values_written.append(sens)
                writer.writerow(
                    {
                        "x": f"{center[0]:.12g}",
                        "y": f"{center[1]:.12g}",
                        "z": f"{center[2]:.12g}",
                        "objective_surface_sensitivity": f"{sens:.12g}",
                        "downforce_surface_sensitivity": f"{-sens:.12g}",
                        "drag_surface_sensitivity": "0",
                        "source_patch": patch,
                        "source_face": face_index,
                    }
                )

    if not values_written:
        raise ValueError("No OpenFOAM surface sensitivity values were exported")
    return OpenFoamSurfaceSensitivityExport(
        source_sensitivity=sensitivity_file,
        output_csv=output_csv,
        patches=selected,
        point_count=len(values_written),
        min_sensitivity=min(values_written),
        max_sensitivity=max(values_written),
    )


def _read_boundary(path: Path) -> dict[str, dict[str, int]]:
    lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    result: dict[str, dict[str, int]] = {}
    i = 0
    while i < len(lines):
        name = lines[i].strip()
        if not name or name.startswith(("//", "/*", "*")) or name in {"(", ")", "{"}:
            i += 1
            continue
        if i + 1 < len(lines) and lines[i + 1].strip() == "{":
            depth = 0
            block: list[str] = []
            i += 1
            while i < len(lines):
                stripped = lines[i].strip()
                depth += stripped.count("{")
                depth -= stripped.count("}")
                block.append(stripped)
                i += 1
                if depth <= 0:
                    break
            text = "\n".join(block)
            n_faces = _extract_int_entry(text, "nFaces")
            start_face = _extract_int_entry(text, "startFace")
            if n_faces is not None and start_face is not None:
                result[name] = {"nFaces": n_faces, "startFace": start_face}
            continue
        i += 1
    return result


def _read_points(path: Path) -> list[tuple[float, float, float]]:
    lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    start, count = _find_openfoam_list_start(lines)
    points: list[tuple[float, float, float]] = []
    vector_re = re.compile(r"\(([-+0-9.eE]+)\s+([-+0-9.eE]+)\s+([-+0-9.eE]+)\)")
    for line in lines[start:]:
        match = vector_re.search(line)
        if match:
            points.append((float(match.group(1)), float(match.group(2)), float(match.group(3))))
            if len(points) == count:
                break
    if len(points) != count:
        raise ValueError(f"Expected {count} points in {path}, found {len(points)}")
    return points


def _read_selected_faces(path: Path, ranges: list[tuple[int, int]]) -> dict[int, list[int]]:
    required: set[int] = set()
    for start, count in ranges:
        required.update(range(start, start + count))
    lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    start_line, face_count = _find_openfoam_list_start(lines)
    faces: dict[int, list[int]] = {}
    face_re = re.compile(r"^\s*\d+\(([^)]*)\)")
    face_index = 0
    for line in lines[start_line:]:
        match = face_re.match(line)
        if not match:
            continue
        if face_index in required:
            faces[face_index] = [int(item) for item in match.group(1).split()]
            if len(faces) == len(required):
                break
        face_index += 1
        if face_index >= face_count:
            break
    missing = sorted(required.difference(faces))
    if missing:
        raise ValueError(f"Missing {len(missing)} selected faces from {path}")
    return faces


def _read_boundary_scalar_values(path: Path, boundary: dict[str, dict[str, int]]) -> dict[str, list[float]]:
    lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    result: dict[str, list[float]] = {}
    for patch, info in boundary.items():
        block = _extract_named_block(lines, patch)
        if block is None:
            continue
        uniform = _extract_uniform_value(block)
        if uniform is not None:
            result[patch] = [uniform] * int(info["nFaces"])
            continue
        values = _extract_nonuniform_scalar_values(block)
        if values is not None:
            result[patch] = values
    return result


def _extract_named_block(lines: list[str], name: str) -> list[str] | None:
    for i, line in enumerate(lines):
        if line.strip() != name:
            continue
        if i + 1 >= len(lines) or lines[i + 1].strip() != "{":
            continue
        block: list[str] = []
        depth = 0
        for j in range(i + 1, len(lines)):
            stripped = lines[j].strip()
            depth += stripped.count("{")
            depth -= stripped.count("}")
            block.append(stripped)
            if depth <= 0:
                return block
    return None


def _extract_uniform_value(block: list[str]) -> float | None:
    text = "\n".join(block)
    match = re.search(r"value\s+uniform\s+([-+0-9.eE]+)\s*;", text)
    return float(match.group(1)) if match else None


def _extract_nonuniform_scalar_values(block: list[str]) -> list[float] | None:
    for i, line in enumerate(block):
        if "nonuniform" not in line or "List<scalar>" not in line:
            continue
        count_index = _next_numeric_line(block, i + 1)
        if count_index is None:
            return None
        count = int(block[count_index].strip())
        values: list[float] = []
        for value_line in block[count_index + 1 :]:
            stripped = value_line.strip()
            if stripped in {"(", ""}:
                continue
            if stripped.startswith(")"):
                break
            values.append(float(stripped.rstrip(";")))
            if len(values) == count:
                break
        if len(values) != count:
            raise ValueError(f"Expected {count} nonuniform sensitivity values, found {len(values)}")
        return values
    return None


def _find_openfoam_list_start(lines: list[str]) -> tuple[int, int]:
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.isdigit():
            count = int(stripped)
            for j in range(i + 1, len(lines)):
                if lines[j].strip() == "(":
                    return j + 1, count
    raise ValueError("Could not find OpenFOAM list start")


def _extract_int_entry(text: str, key: str) -> int | None:
    match = re.search(rf"\b{re.escape(key)}\s+([0-9]+)\s*;", text)
    return int(match.group(1)) if match else None


def _next_numeric_line(lines: list[str], start: int) -> int | None:
    for i in range(start, len(lines)):
        if lines[i].strip().isdigit():
            return i
    return None


def _face_center(points: list[tuple[float, float, float]], face: list[int]) -> tuple[float, float, float]:
    inv = 1.0 / len(face)
    x = sum(points[index][0] for index in face) * inv
    y = sum(points[index][1] for index in face) * inv
    z = sum(points[index][2] for index in face) * inv
    return x, y, z
