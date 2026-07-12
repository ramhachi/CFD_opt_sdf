from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

from .sdf import FieldBundle


DESIGN_STATE_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class DensityDesignState:
    schema_version: int
    kind: str
    design_variable: str
    density_vti: Path
    density_array: str
    allowed_array: str
    grid: dict[str, object]
    bounds: dict[str, float]
    iso_value: float
    derived_geometry: Path
    source_project: Path
    created_by: str

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        for key in ("density_vti", "derived_geometry", "source_project"):
            data[key] = str(data[key])
        return data


def create_density_design_state(
    *,
    bundle: FieldBundle,
    density: np.ndarray,
    density_vti: Path,
    derived_geometry: Path,
    source_project: Path,
    iso_value: float = 0.5,
    created_by: str = "cfd_sdf.topology",
) -> DensityDesignState:
    return DensityDesignState(
        schema_version=DESIGN_STATE_SCHEMA_VERSION,
        kind="density_design_state",
        design_variable="density",
        density_vti=density_vti,
        density_array="density",
        allowed_array="allowed_mask",
        grid={
            "origin": bundle.grid.origin.tolist(),
            "spacing": float(bundle.grid.spacing),
            "shape": list(bundle.grid.shape),
            "bounds": bundle.grid.bounds.tolist(),
        },
        bounds={
            "lower": 0.0,
            "upper": 1.0,
            "min": float(np.min(density)) if density.size else 0.0,
            "max": float(np.max(density)) if density.size else 0.0,
        },
        iso_value=float(iso_value),
        derived_geometry=derived_geometry,
        source_project=source_project,
        created_by=created_by,
    )


def write_density_design_state(state: DensityDesignState, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state.to_dict(), indent=2), encoding="utf-8")
    return path


def read_density_design_state(path: Path) -> DensityDesignState:
    data = json.loads(path.read_text(encoding="utf-8"))
    required = {
        "schema_version",
        "kind",
        "design_variable",
        "density_vti",
        "density_array",
        "allowed_array",
        "grid",
        "bounds",
        "iso_value",
        "derived_geometry",
        "source_project",
        "created_by",
    }
    missing = sorted(required - set(data))
    if missing:
        raise ValueError(f"Design state is missing required fields: {', '.join(missing)}")
    if int(data["schema_version"]) != DESIGN_STATE_SCHEMA_VERSION:
        raise ValueError(f"Unsupported design state schema_version: {data['schema_version']}")
    if str(data["kind"]) != "density_design_state":
        raise ValueError(f"Unsupported design state kind: {data['kind']}")
    if str(data["design_variable"]) != "density":
        raise ValueError(f"Unsupported design variable: {data['design_variable']}")

    return DensityDesignState(
        schema_version=int(data["schema_version"]),
        kind=str(data["kind"]),
        design_variable=str(data["design_variable"]),
        density_vti=Path(str(data["density_vti"])),
        density_array=str(data["density_array"]),
        allowed_array=str(data["allowed_array"]),
        grid=dict(data["grid"]),
        bounds={str(key): float(value) for key, value in dict(data["bounds"]).items()},
        iso_value=float(data["iso_value"]),
        derived_geometry=Path(str(data["derived_geometry"])),
        source_project=Path(str(data["source_project"])),
        created_by=str(data["created_by"]),
    )


def resolve_design_state_path(
    design_state_json: Path,
    path_value: Path,
    *,
    local_fallback: Path | None = None,
) -> Path:
    """Resolve a path stored in design_state.json.

    Candidate directories are often copied to `best_*` folders. Prefer a local
    sibling fallback when it exists so copied candidates remain self-contained.
    """
    manifest_dir = design_state_json.parent
    candidates: list[Path] = []
    if local_fallback is not None:
        candidates.append(manifest_dir / local_fallback)
    if path_value.is_absolute():
        candidates.append(path_value)
    else:
        candidates.append(manifest_dir / path_value)
        candidates.append(Path.cwd() / path_value)

    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0] if candidates else path_value
