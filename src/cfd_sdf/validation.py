from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pyvista as pv

from .config import ProjectConfig


REQUIRED_REPORT_KEYS = {
    "ok",
    "rule_violation_cells",
    "forbidden_intersection_cells",
    "nominal_components",
    "nominal_unrooted_components",
    "eroded_components",
    "eroded_unrooted_components",
    "eroded_cell_count",
}

REQUIRED_VTI_ARRAYS = {
    "design_phi",
    "design_narrow_band",
    "design_nearest_distance",
    "design_second_distance",
    "design_nearest_component_id",
    "design_second_nearest_component_id",
    "design_nearest_patch_id",
    "design_second_nearest_patch_id",
    "design_normal_x",
    "design_normal_y",
    "design_normal_z",
    "allowed_phi",
    "allowed_narrow_band",
    "forbidden_phi",
    "forbidden_narrow_band",
    "root_phi",
    "root_narrow_band",
    "violation_rule",
    "violation_forbidden",
    "connectivity_components",
    "connectivity_unrooted",
    "eroded_solid",
    "eroded_unrooted",
}


@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    missing_files: list[str]
    missing_report_keys: list[str]
    missing_vti_arrays: list[str]
    report_ok: bool | None
    point_count: int

    def to_dict(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "missing_files": self.missing_files,
            "missing_report_keys": self.missing_report_keys,
            "missing_vti_arrays": self.missing_vti_arrays,
            "report_ok": self.report_ok,
            "point_count": self.point_count,
        }


def validate_outputs(config: ProjectConfig, expect_ok: bool | None = True) -> ValidationResult:
    out_dir = config.resolved_output_dir
    report_path = out_dir / "report.json"
    vti_path = out_dir / "sdf_fields.vti"
    surface_path = out_dir / "zero_surface.ply"

    missing_files = [
        str(path)
        for path in (report_path, vti_path, surface_path)
        if not path.exists()
    ]

    report_data: dict[str, object] = {}
    missing_report_keys = sorted(REQUIRED_REPORT_KEYS)
    report_ok: bool | None = None
    if report_path.exists():
        report_data = json.loads(report_path.read_text(encoding="utf-8"))
        missing_report_keys = sorted(REQUIRED_REPORT_KEYS - set(report_data))
        report_ok = bool(report_data.get("ok")) if "ok" in report_data else None

    missing_vti_arrays = sorted(REQUIRED_VTI_ARRAYS)
    point_count = 0
    if vti_path.exists():
        grid = pv.read(vti_path)
        point_count = int(grid.n_points)
        missing_vti_arrays = sorted(REQUIRED_VTI_ARRAYS - set(grid.point_data.keys()))

    expected_state_ok = True
    if expect_ok is not None:
        expected_state_ok = report_ok is expect_ok

    ok = (
        not missing_files
        and not missing_report_keys
        and not missing_vti_arrays
        and point_count > 0
        and expected_state_ok
    )
    return ValidationResult(
        ok=ok,
        missing_files=missing_files,
        missing_report_keys=missing_report_keys,
        missing_vti_arrays=missing_vti_arrays,
        report_ok=report_ok,
        point_count=point_count,
    )
