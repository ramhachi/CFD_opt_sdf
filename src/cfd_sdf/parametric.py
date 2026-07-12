from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from pathlib import Path

import trimesh


@dataclass(frozen=True)
class FrontWingParameters:
    main_x_m: float = 0.88
    main_z_m: float = 0.19
    main_chord_m: float = 0.82
    span_m: float = 1.25
    main_thickness_m: float = 0.055
    flap_x_m: float = 0.65
    flap_z_m: float = 0.29
    flap_chord_m: float = 0.48
    flap_span_ratio: float = 0.92
    flap_thickness_m: float = 0.045
    endplate_height_m: float = 0.31
    endplate_thickness_m: float = 0.09
    mount_x_m: float = 0.56
    mount_y_m: float = 0.32
    mount_z_m: float = 0.25
    strut_x_m: float = 0.70
    strut_y_m: float = 0.42


PARAMETER_BOUNDS: dict[str, tuple[float, float]] = {
    "main_x_m": (0.74, 1.02),
    "main_z_m": (0.15, 0.24),
    "main_chord_m": (0.60, 0.98),
    "span_m": (1.05, 1.38),
    "main_thickness_m": (0.04, 0.08),
    "flap_x_m": (0.52, 0.80),
    "flap_z_m": (0.23, 0.36),
    "flap_chord_m": (0.30, 0.62),
    "flap_span_ratio": (0.78, 0.98),
    "flap_thickness_m": (0.035, 0.07),
    "endplate_height_m": (0.18, 0.40),
    "endplate_thickness_m": (0.06, 0.12),
    "strut_x_m": (0.60, 0.82),
    "strut_y_m": (0.34, 0.52),
}


OPTIMIZATION_VARIABLES: tuple[str, ...] = (
    "main_x_m",
    "main_chord_m",
    "span_m",
    "flap_x_m",
    "flap_z_m",
    "flap_chord_m",
    "flap_span_ratio",
    "endplate_height_m",
    "strut_x_m",
)


def default_parameters() -> FrontWingParameters:
    return FrontWingParameters()


def parameters_from_dict(data: dict[str, float]) -> FrontWingParameters:
    values = asdict(default_parameters())
    for key, value in data.items():
        if key not in values:
            raise ValueError(f"Unknown front-wing parameter: {key}")
        values[key] = float(value)
    return FrontWingParameters(**values)


def parameters_to_dict(params: FrontWingParameters) -> dict[str, float]:
    return {field.name: float(getattr(params, field.name)) for field in fields(params)}


def clamp_parameters(params: FrontWingParameters) -> FrontWingParameters:
    values = parameters_to_dict(params)
    for key, (lower, upper) in PARAMETER_BOUNDS.items():
        values[key] = min(max(values[key], lower), upper)
    return FrontWingParameters(**values)


def write_parametric_front_wing_stl(path: Path, params: FrontWingParameters) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    mesh = build_parametric_front_wing(params)
    mesh.export(path)
    return path


def build_parametric_front_wing(params: FrontWingParameters) -> trimesh.Trimesh:
    p = clamp_parameters(params)
    half_span = 0.5 * p.span_m
    flap_span = p.span_m * p.flap_span_ratio
    endplate_y = half_span

    main = _box((p.main_x_m, 0.0, p.main_z_m), (p.main_chord_m, p.span_m, p.main_thickness_m))
    flap = _box((p.flap_x_m, 0.0, p.flap_z_m), (p.flap_chord_m, flap_span, p.flap_thickness_m))
    endplate_l = _box((p.main_x_m, endplate_y, p.main_z_m + 0.04), (0.58, p.endplate_thickness_m, p.endplate_height_m))
    endplate_r = _box((p.main_x_m, -endplate_y, p.main_z_m + 0.04), (0.58, p.endplate_thickness_m, p.endplate_height_m))

    mount_l = _box((p.mount_x_m, p.mount_y_m, p.mount_z_m), (0.16, 0.08, 0.16))
    mount_r = _box((p.mount_x_m, -p.mount_y_m, p.mount_z_m), (0.16, 0.08, 0.16))

    strut_height = max(0.08, abs(p.flap_z_m - p.main_z_m) + 0.06)
    strut_z = 0.5 * (p.flap_z_m + p.main_z_m)
    strut_l = _box((p.strut_x_m, p.strut_y_m, strut_z), (0.08, 0.06, strut_height))
    strut_r = _box((p.strut_x_m, -p.strut_y_m, strut_z), (0.08, 0.06, strut_height))

    root_bridge_l = _box((0.59, p.mount_y_m, 0.225), (0.18, 0.09, 0.11))
    root_bridge_r = _box((0.59, -p.mount_y_m, 0.225), (0.18, 0.09, 0.11))

    return trimesh.util.concatenate(
        [main, flap, endplate_l, endplate_r, mount_l, mount_r, strut_l, strut_r, root_bridge_l, root_bridge_r]
    )


def mock_aero(params: FrontWingParameters, efficiency_min: float, x_split_m: float = 0.0) -> dict[str, float]:
    p = clamp_parameters(params)
    main_area = p.span_m * p.main_chord_m
    flap_area = p.span_m * p.flap_span_ratio * p.flap_chord_m
    gap = max(p.flap_z_m - p.main_z_m, 0.02)
    endplate_factor = 1.0 + 0.8 * p.endplate_height_m
    flap_gain = 1.0 + 0.45 * min(gap / 0.12, 1.5)
    downforce = 0.65 * main_area * endplate_factor + 0.85 * flap_area * flap_gain
    drag = 0.055 + 0.13 * main_area + 0.10 * flap_area + 0.18 * p.endplate_height_m * p.endplate_thickness_m
    efficiency = downforce / drag if abs(drag) > 1.0e-12 else 0.0
    main_downforce = 0.65 * main_area * endplate_factor
    flap_downforce = downforce - main_downforce
    main_is_front = p.main_x_m >= x_split_m
    flap_is_front = p.flap_x_m >= x_split_m
    front_downforce = (main_downforce if main_is_front else 0.0) + (flap_downforce if flap_is_front else 0.0)
    rear_downforce = downforce - front_downforce
    front_ratio = front_downforce / downforce if abs(downforce) > 1.0e-12 else 0.0
    return {
        "drag_coefficient": drag,
        "downforce_coefficient": downforce,
        "front_downforce_coefficient": front_downforce,
        "rear_downforce_coefficient": rear_downforce,
        "front_downforce_ratio": front_ratio,
        "efficiency": efficiency,
        "efficiency_constraint": efficiency_min * drag - downforce,
    }


def _box(center: tuple[float, float, float], extents: tuple[float, float, float]) -> trimesh.Trimesh:
    mesh = trimesh.creation.box(extents=extents)
    mesh.apply_translation(center)
    return mesh
