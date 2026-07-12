from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import ndimage

from .config import ProjectConfig
from .sdf import FieldBundle


@dataclass(frozen=True)
class ConstraintReport:
    ok: bool
    rule_violation_cells: int
    forbidden_intersection_cells: int
    nominal_components: int
    nominal_unrooted_components: int
    eroded_components: int
    eroded_unrooted_components: int
    eroded_cell_count: int

    def to_dict(self) -> dict[str, int | bool]:
        return {
            "ok": self.ok,
            "rule_violation_cells": self.rule_violation_cells,
            "forbidden_intersection_cells": self.forbidden_intersection_cells,
            "nominal_components": self.nominal_components,
            "nominal_unrooted_components": self.nominal_unrooted_components,
            "eroded_components": self.eroded_components,
            "eroded_unrooted_components": self.eroded_unrooted_components,
            "eroded_cell_count": self.eroded_cell_count,
        }


def check_constraints(config: ProjectConfig, bundle: FieldBundle) -> tuple[ConstraintReport, dict[str, np.ndarray]]:
    arrays = bundle.arrays
    if "design_phi" not in arrays:
        raise ValueError("Constraint checks require design_geometry.")

    design_phi = arrays["design_phi"]
    rule_margin = config.constraints.rule_margin_m
    design_dilated = design_phi < rule_margin

    if "allowed_phi" in arrays:
        rule_violation = design_dilated & (arrays["allowed_phi"] > 0.0)
    else:
        rule_violation = np.zeros(design_phi.shape, dtype=bool)

    if "forbidden_phi" in arrays:
        forbidden_intersection = design_dilated & (arrays["forbidden_phi"] < rule_margin)
    else:
        forbidden_intersection = np.zeros(design_phi.shape, dtype=bool)

    root_touch = _root_touch_mask(config, bundle)
    nominal = design_phi < 0.0
    nominal_result = _component_check(nominal, root_touch)

    eroded = design_phi < -config.constraints.erosion_radius_m
    eroded_result = _component_check(eroded, root_touch)

    ok = (
        int(rule_violation.sum()) == 0
        and int(forbidden_intersection.sum()) == 0
        and nominal_result["unrooted_components"] == 0
        and (
            not config.constraints.require_eroded_connectivity
            or eroded_result["unrooted_components"] == 0
        )
    )

    report = ConstraintReport(
        ok=ok,
        rule_violation_cells=int(rule_violation.sum()),
        forbidden_intersection_cells=int(forbidden_intersection.sum()),
        nominal_components=nominal_result["components"],
        nominal_unrooted_components=nominal_result["unrooted_components"],
        eroded_components=eroded_result["components"],
        eroded_unrooted_components=eroded_result["unrooted_components"],
        eroded_cell_count=int(eroded.sum()),
    )
    derived = {
        "violation_rule": rule_violation.astype(np.uint8),
        "violation_forbidden": forbidden_intersection.astype(np.uint8),
        "connectivity_components": nominal_result["labels"].astype(np.int32),
        "connectivity_unrooted": nominal_result["unrooted_mask"].astype(np.uint8),
        "eroded_solid": eroded.astype(np.uint8),
        "eroded_unrooted": eroded_result["unrooted_mask"].astype(np.uint8),
    }
    return report, derived


def _root_touch_mask(config: ProjectConfig, bundle: FieldBundle) -> np.ndarray:
    design_phi = bundle.arrays["design_phi"]
    if "root_phi" not in bundle.arrays:
        return np.zeros(design_phi.shape, dtype=bool)
    tolerance = np.sqrt(3.0) * bundle.grid.spacing
    return (design_phi < tolerance) & (bundle.arrays["root_phi"] < tolerance)


def _component_check(mask: np.ndarray, root_touch: np.ndarray) -> dict[str, np.ndarray | int]:
    structure = ndimage.generate_binary_structure(rank=3, connectivity=1)
    labels, count = ndimage.label(mask, structure=structure)
    if count == 0:
        return {
            "components": 0,
            "unrooted_components": 0,
            "labels": labels,
            "unrooted_mask": np.zeros(mask.shape, dtype=bool),
        }

    rooted_ids = set(np.unique(labels[root_touch & mask]).tolist())
    rooted_ids.discard(0)
    all_ids = set(range(1, count + 1))
    unrooted_ids = np.array(sorted(all_ids - rooted_ids), dtype=labels.dtype)
    unrooted_mask = np.isin(labels, unrooted_ids) if len(unrooted_ids) else np.zeros(mask.shape, dtype=bool)
    return {
        "components": int(count),
        "unrooted_components": int(len(unrooted_ids)),
        "labels": labels,
        "unrooted_mask": unrooted_mask,
    }
