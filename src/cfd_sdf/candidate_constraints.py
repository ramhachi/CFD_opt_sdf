from __future__ import annotations

from dataclasses import asdict, dataclass

from .config import ProjectConfig


@dataclass(frozen=True)
class ConstraintRecord:
    name: str
    value: float
    limit: float
    satisfied: bool
    enforced: bool
    category: str
    message: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def build_constraint_records(
    report: dict[str, object],
    aero: dict[str, float],
    config: ProjectConfig,
) -> list[ConstraintRecord]:
    records = [
        ConstraintRecord(
            name="rule_violation_cells",
            value=float(report.get("rule_violation_cells", 0)),
            limit=0.0,
            satisfied=float(report.get("rule_violation_cells", 0)) <= 0.0,
            enforced=True,
            category="geometry",
            message="Dilated design geometry must stay inside allowed region.",
        ),
        ConstraintRecord(
            name="forbidden_intersection_cells",
            value=float(report.get("forbidden_intersection_cells", 0)),
            limit=0.0,
            satisfied=float(report.get("forbidden_intersection_cells", 0)) <= 0.0,
            enforced=True,
            category="geometry",
            message="Dilated design geometry must not intersect forbidden regions.",
        ),
        ConstraintRecord(
            name="nominal_unrooted_components",
            value=float(report.get("nominal_unrooted_components", 0)),
            limit=0.0,
            satisfied=float(report.get("nominal_unrooted_components", 0)) <= 0.0,
            enforced=True,
            category="connectivity",
            message="Nominal solid must be connected to at least one root region.",
        ),
        ConstraintRecord(
            name="eroded_unrooted_components",
            value=float(report.get("eroded_unrooted_components", 0)),
            limit=0.0,
            satisfied=float(report.get("eroded_unrooted_components", 0)) <= 0.0,
            enforced=config.constraints.require_eroded_connectivity,
            category="connectivity",
            message="Eroded solid must remain connected to roots for minimum-thickness robustness.",
        ),
        ConstraintRecord(
            name="efficiency_constraint",
            value=float(aero["efficiency_constraint"]),
            limit=0.0,
            satisfied=float(aero["efficiency_constraint"]) <= 0.0,
            enforced=True,
            category="aero",
            message="E_min * C_D - C_DF must be <= 0.",
        ),
    ]
    if config.front_downforce_ratio.enabled:
        ratio = float(aero["front_downforce_ratio"])
        records.extend(
            [
                ConstraintRecord(
                    name="front_downforce_ratio_min",
                    value=ratio,
                    limit=float(config.front_downforce_ratio.min),
                    satisfied=ratio >= float(config.front_downforce_ratio.min),
                    enforced=bool(config.front_downforce_ratio.enforce),
                    category="aero_balance",
                    message="Front downforce ratio should be above configured minimum.",
                ),
                ConstraintRecord(
                    name="front_downforce_ratio_max",
                    value=ratio,
                    limit=float(config.front_downforce_ratio.max),
                    satisfied=ratio <= float(config.front_downforce_ratio.max),
                    enforced=bool(config.front_downforce_ratio.enforce),
                    category="aero_balance",
                    message="Front downforce ratio should be below configured maximum.",
                ),
            ]
        )
    return records


def constraint_penalty(records: list[ConstraintRecord]) -> float:
    penalty = 0.0
    for record in records:
        if record.satisfied:
            continue
        if record.name == "efficiency_constraint":
            penalty += max(0.0, record.value) * 10.0
        elif record.category == "geometry":
            penalty += abs(record.value - record.limit) * 0.5
        elif record.category == "connectivity":
            penalty += abs(record.value - record.limit) * 100.0
        elif record.enforced:
            penalty += abs(record.value - record.limit) * 100.0
    if any(record.enforced and not record.satisfied for record in records):
        penalty += 100.0
    return penalty
