from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .problem_spec import ProblemSpec, load_problem_spec


@dataclass(frozen=True)
class MeshRef:
    id: str
    file: Path


@dataclass(frozen=True)
class RootSpec:
    id: str
    type: str
    file: Path | None = None
    center_m: tuple[float, float, float] | None = None
    radius_m: float | None = None
    extents_m: tuple[float, float, float] | None = None


@dataclass(frozen=True)
class GridSpec:
    voxel_size_m: float = 0.025
    padding_m: float = 0.15
    band_width_m: float = 0.20
    max_points: int = 8_000_000


@dataclass(frozen=True)
class ConstraintSpec:
    min_thickness_mm: float = 10.0
    rule_margin_mm: float = 5.0
    require_eroded_connectivity: bool = True

    @property
    def min_thickness_m(self) -> float:
        return self.min_thickness_mm * 1.0e-3

    @property
    def erosion_radius_m(self) -> float:
        return 0.5 * self.min_thickness_m

    @property
    def rule_margin_m(self) -> float:
        return self.rule_margin_mm * 1.0e-3


@dataclass(frozen=True)
class FrontDownforceRatioSpec:
    enabled: bool = True
    enforce: bool = False
    x_split_m: float = 0.0
    min: float = 0.4
    max: float = 0.6


@dataclass(frozen=True)
class ObjectiveSpec:
    type: str = "maximize_downforce_with_efficiency_constraint"
    efficiency_min: float = 3.0


@dataclass(frozen=True)
class OperatingPointSpec:
    velocity_mps: float = 11.0
    density: float = 1.229
    viscosity: float = 1.73e-5


@dataclass(frozen=True)
class ProjectConfig:
    path: Path
    fixed_solids: list[MeshRef] = field(default_factory=list)
    design_geometry: list[MeshRef] = field(default_factory=list)
    design_domains: list[MeshRef] = field(default_factory=list)
    forbidden_regions: list[MeshRef] = field(default_factory=list)
    roots: list[RootSpec] = field(default_factory=list)
    grid: GridSpec = field(default_factory=GridSpec)
    constraints: ConstraintSpec = field(default_factory=ConstraintSpec)
    front_downforce_ratio: FrontDownforceRatioSpec = field(default_factory=FrontDownforceRatioSpec)
    objective: ObjectiveSpec = field(default_factory=ObjectiveSpec)
    operating_point: OperatingPointSpec = field(default_factory=OperatingPointSpec)
    output_dir: Path = Path("runs/front_wing_demo")
    problem_spec: ProblemSpec | None = None
    flow_case_id: str | None = None

    @property
    def base_dir(self) -> Path:
        return self.path.parent

    def resolve(self, path: Path) -> Path:
        return path if path.is_absolute() else (self.base_dir / path)

    @property
    def resolved_output_dir(self) -> Path:
        return self.resolve(self.output_dir)


def load_project(path: str | Path) -> ProjectConfig:
    config_path = Path(path).resolve()
    data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError("Project configuration root must be a mapping")
    try:
        schema_version = None if data.get("schema_version") is None else int(data["schema_version"])
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid schema_version: {data.get('schema_version')!r}") from exc
    if schema_version == 2:
        raise ValueError(
            "schema_version 2 is a generic problem specification; use load_problem_spec() "
            "instead of the legacy front-wing load_project() pipeline"
        )
    problem_spec = load_problem_spec(config_path)
    geometry = data.get("geometry", {})

    def mesh_refs(key: str) -> list[MeshRef]:
        refs = []
        for item in geometry.get(key, []) or []:
            refs.append(MeshRef(id=str(item["id"]), file=Path(item["file"])))
        return refs

    roots = []
    for item in data.get("roots", []) or []:
        roots.append(
            RootSpec(
                id=str(item["id"]),
                type=str(item.get("type", "stl")),
                file=Path(item["file"]) if item.get("file") else None,
                center_m=_tuple3(item.get("center_m")),
                radius_m=_optional_float(item.get("radius_m")),
                extents_m=_tuple3(item.get("extents_m")),
            )
        )

    constraints = data.get("constraints", {}) or {}
    front_ratio = constraints.get("front_downforce_ratio", {}) or {}

    return ProjectConfig(
        path=config_path,
        fixed_solids=mesh_refs("fixed_solids"),
        design_geometry=mesh_refs("design_geometry"),
        design_domains=mesh_refs("design_domains"),
        forbidden_regions=mesh_refs("forbidden_regions"),
        roots=roots,
        grid=GridSpec(**(data.get("grid", {}) or {})),
        constraints=ConstraintSpec(
            min_thickness_mm=float(constraints.get("min_thickness_mm", 10.0)),
            rule_margin_mm=float(constraints.get("rule_margin_mm", 5.0)),
            require_eroded_connectivity=bool(constraints.get("require_eroded_connectivity", True)),
        ),
        front_downforce_ratio=FrontDownforceRatioSpec(
            enabled=bool(front_ratio.get("enabled", True)),
            enforce=bool(front_ratio.get("enforce", False)),
            x_split_m=float(front_ratio.get("x_split_m", 0.0)),
            min=float(front_ratio.get("min", 0.4)),
            max=float(front_ratio.get("max", 0.6)),
        ),
        objective=ObjectiveSpec(**(data.get("objective", {}) or {})),
        operating_point=OperatingPointSpec(**(data.get("operating_point", {}) or {})),
        output_dir=Path(data.get("output_dir", "runs/front_wing_demo")),
        problem_spec=problem_spec,
    )


def _tuple3(value: Any) -> tuple[float, float, float] | None:
    if value is None:
        return None
    if len(value) != 3:
        raise ValueError(f"Expected 3 values, got {value!r}")
    return (float(value[0]), float(value[1]), float(value[2]))


def _optional_float(value: Any) -> float | None:
    return None if value is None else float(value)
