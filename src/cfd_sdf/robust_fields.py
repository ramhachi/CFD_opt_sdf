"""Robust three-field (eroded/intermediate/dilated) formulation support (DF6).

The architecture plan requires the robust formulation only after the minimal
nonlinear loop is qualified, and requires its caveats to be explicit:

- the minimum-length-scale guarantee holds only while the three thresholded
  designs share one topology, which is checked a posteriori (``same_topology``);
- simultaneous solid/void length-scale control requires the volume restriction
  to be applied to the dilated design (Trillet, Duysinx & Fernández 2021,
  arXiv:2101.08605);
- filter radius and projection thresholds are related to the target length
  scales by the analytic relations of Qian & Sigmund 2013 / Trillet et al.
  2021; this module reports the declared parameters instead of re-deriving
  them numerically.

Every field shares the filter/interpolation stack of the parent
``DesignTransform``, so there is still exactly one transform hash owner; the
three fields differ only in the projection threshold.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from .design_transform import (
    DesignTransform,
    DesignTransformState,
    TanhProjection,
)
from .shape_feature_metrics import occupancy_metrics


class RobustFieldError(ValueError):
    """Fail-closed robust-formulation contract violation."""


FIELD_NAMES = ("eroded", "intermediate", "dilated")


def _as3d(values: np.ndarray, shape: tuple[int, int, int]) -> np.ndarray:
    return np.asarray(values).reshape(shape, order="F")


@dataclass
class RobustThreeField:
    """The same filter and interpolation at three projection thresholds."""

    transform: DesignTransform
    eta_eroded: float = 0.7
    eta_dilated: float = 0.3

    def __post_init__(self) -> None:
        eta_intermediate = self.transform.projection.eta
        if not self.eta_dilated < eta_intermediate < self.eta_eroded:
            raise RobustFieldError(
                "projection thresholds must satisfy eta_dilated < eta_intermediate "
                "< eta_eroded"
            )
        if self.transform.projection.sharpness <= 0.0:
            raise RobustFieldError(
                "the robust formulation requires a non-identity projection "
                "(sharpness > 0) so the three fields differ"
            )

    def fields(self, rho: np.ndarray) -> dict[str, DesignTransformState]:
        base = self.transform.forward(rho)
        states: dict[str, DesignTransformState] = {"intermediate": base}
        for name, eta in (
            ("eroded", self.eta_eroded),
            ("dilated", self.eta_dilated),
        ):
            projected = np.clip(
                TanhProjection(self.transform.projection.sharpness, eta).forward(
                    base.rho_filtered
                ),
                0.0,
                1.0,
            )
            states[name] = DesignTransformState(
                rho_design=base.rho_design,
                rho_filtered=base.rho_filtered,
                rho_projected=projected,
                beta=self.transform.ramp.forward(projected),
            )
        return states

    def volume_fraction(self, state: DesignTransformState) -> float:
        return self.transform.projected_volume_fraction(state)

    def dilated_volume_constraint_value(
        self, rho: np.ndarray, *, limit: float
    ) -> float:
        """``V_occ(dilated) - limit``; the registered robust volume definition."""

        fields = self.fields(rho)
        return self.volume_fraction(fields["dilated"]) - float(limit)

    def worst_case_objective(
        self,
        values_by_field: dict[str, float],
        *,
        sense: str,
    ) -> float:
        """Worst of the three fields for the declared objective sense."""

        missing = [name for name in FIELD_NAMES if name not in values_by_field]
        if missing:
            raise RobustFieldError(f"missing field values for {missing}")
        if sense == "minimize":
            return max(float(values_by_field[name]) for name in FIELD_NAMES)
        if sense == "maximize":
            return min(float(values_by_field[name]) for name in FIELD_NAMES)
        raise RobustFieldError(f"unknown objective sense {sense!r}")

    def backward(
        self, field_name: str, rho: np.ndarray, g_beta: np.ndarray
    ) -> np.ndarray:
        """Exact chain gradient for one of the three fields."""

        if field_name not in FIELD_NAMES:
            raise RobustFieldError(f"unknown field {field_name!r}")
        state = self.fields(rho)[field_name]
        eta = {
            "eroded": self.eta_eroded,
            "intermediate": self.transform.projection.eta,
            "dilated": self.eta_dilated,
        }[field_name]
        projection = TanhProjection(self.transform.projection.sharpness, eta)
        derivative = projection.derivative(state.rho_filtered) * self.transform.ramp.derivative(
            state.rho_projected
        )
        return self.transform.filter.HT(derivative * np.asarray(g_beta, dtype=np.float64))

    def same_topology(
        self, rho: np.ndarray, *, threshold: float = 0.5
    ) -> dict[str, Any]:
        """A posteriori topology-consistency check of the three designs."""

        fields = self.fields(rho)
        masks = {
            name: _as3d(fields[name].rho_projected, self.transform.shape) > threshold
            for name in FIELD_NAMES
        }
        components = {
            name: (
                occupancy_metrics(masks[name], self.transform.spacing_m).get(
                    "n_components_26", 0
                )
                if masks[name].any()
                else 0
            )
            for name in FIELD_NAMES
        }
        inclusions = {
            "eroded_subset_intermediate": bool(
                np.all(masks["eroded"] <= masks["intermediate"])
            ),
            "intermediate_subset_dilated": bool(
                np.all(masks["intermediate"] <= masks["dilated"])
            ),
        }
        consistent = (
            all(inclusions.values())
            and components["eroded"] == components["intermediate"]
            and components["intermediate"] == components["dilated"]
            and components["intermediate"] > 0
        )
        return {
            "consistent": consistent,
            "components": components,
            "inclusions": inclusions,
            "caveat": (
                "robust length-scale control is guaranteed only while the three "
                "thresholded designs share one topology; this check is a "
                "necessary condition, not a proof"
            ),
        }

    def production_status(self) -> dict[str, Any]:
        """PQ6 gate: this prototype is not part of the production registry."""

        return {
            "production_ready": False,
            "reason": (
                "PQ6 pending: the dilated-volume constraint gradient, the worst-case "
                "active-set rule, and the closed-loop integration are not qualified; "
                "do not connect this module to the production path"
            ),
        }

    def parameter_report(self) -> dict[str, Any]:
        return {
            "kind": "robust_three_field_parameters",
            "filter_radius_m": self.transform.filter.meta.get("filter_radius_m"),
            "eta_eroded": self.eta_eroded,
            "eta_intermediate": self.transform.projection.eta,
            "eta_dilated": self.eta_dilated,
            "sharpness_b": self.transform.projection.sharpness,
            "ramp_q": self.transform.ramp.q,
            "volume_constraint_field": "dilated",
            "analytic_relations": (
                "minimum length scales follow the analytic filter/projection "
                "relations of Qian & Sigmund 2013 and Trillet, Duysinx & "
                "Fernández 2021 (arXiv:2101.08605); parameters are declared, "
                "not tuned against observed results"
            ),
            "cost": "three primal/adjoint re-evaluations per outer iteration",
        }


__all__ = ["FIELD_NAMES", "RobustFieldError", "RobustThreeField"]
