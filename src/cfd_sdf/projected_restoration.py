"""Projected-volume OC backends for the PQ3.3b restoration policy.

Two-phase registered policy (see docs/evidence/pq3_3b_campaign_manifest_v2_2026_09.json):

- Phase 1 ``ProjectedVolumeRestorationBackend``: uniform design-space ascent on
  the transform-active cells; one scalar kappa is bisected so that
  ``mean(rho_projection(candidate)[active]) == V_target``, judged through the
  real ``DesignTransform.forward`` (filter, projection, RAMP), never through
  the raw design mean. When the target is outside the single-step move box,
  the proposal advances to the reachable frontier instead of failing;
  acceptance still requires the real primal, the projected-volume upper bound
  and the geometry gate.
- Phase 2 ``VolumeCorrectedObjectiveBackend``: downforce-gradient proposal,
  then a signed uniform offset whose scalar is bisected to bring the projected
  volume back to the target (residual <= tolerance). Objective improvement is
  an acceptance condition in the campaign loop, not inside this backend.

Non-active, forbidden and fixed-solid cells are bitwise unchanged by both
backends (restore-after-clip, the Work C.1 contract).
"""

from __future__ import annotations

from typing import Any

import numpy as np

from cfd_sdf.stage_t_loop import TrialProposal

MASK_DRIFT_TOLERANCE = 1e-12
MAX_KAPPA_DOUBLINGS = 30
MONOTONE_SLACK = 1e-12
BISECTION_STEPS = 60


def _box(values: np.ndarray, move_radius: float) -> tuple[np.ndarray, np.ndarray]:
    return (
        np.clip(values - move_radius, 0.0, 1.0),
        np.clip(values + move_radius, 0.0, 1.0),
    )


def _restore(stepped: np.ndarray, values: np.ndarray, active: np.ndarray) -> np.ndarray:
    stepped = np.asarray(stepped, dtype=np.float64).copy()
    stepped[~active] = values[~active]
    return stepped


class _MonotoneSweep:
    """Sorted-sample monotonicity ledger (kappa -> phi), fail-closed."""

    def __init__(self) -> None:
        self.samples: list[tuple[float, float]] = []

    def add(self, kappa: float, phi: float) -> None:
        entry = (float(kappa), float(phi))
        for existing_kappa, existing_phi in self.samples:
            if existing_kappa <= entry[0]:
                if existing_phi > entry[1] + MONOTONE_SLACK:
                    raise ValueError(
                        "projected volume phi(kappa) is not monotone non-decreasing"
                        f" (kappa {existing_kappa:.6g}: {existing_phi:.9f} > "
                        f"{entry[1]:.9f} at kappa {entry[0]:.6g}); fail-closed"
                    )
            elif existing_phi < entry[1] - MONOTONE_SLACK:
                raise ValueError(
                    "projected volume phi(kappa) is not monotone non-decreasing"
                    f" (kappa {entry[0]:.6g}: {entry[1]:.9f} < "
                    f"{existing_phi:.9f} at kappa {existing_kappa:.6g}); fail-closed"
                )
        self.samples.append(entry)


class ProjectedVolumeRestorationBackend:
    """Phase 1: bisect a scalar uniform-ascent coefficient onto V_target.

    The neighbourhood family is
    ``rho(kappa) = clip(values + kappa * move_radius, box)`` with the ascent
    applied uniformly on ``transform.active`` (kappa >= 0 only); per-cell
    monotonicity plus the monotone filter/projection chain make ``phi(kappa)``
    monotone non-decreasing, which is verified on every evaluated kappa.
    """

    backend_id = "projected-volume-restoration-oc"

    def __init__(self, *, transform, target: float, tolerance: float = 1e-4) -> None:
        if not 0.0 < float(target) < 1.0:
            raise ValueError("projected target must be within (0, 1)")
        if tolerance <= 0.0:
            raise ValueError("restoration tolerance must be positive")
        self.transform = transform
        self.target = float(target)
        self.tolerance = float(tolerance)

    def _phi(
        self,
        kappa: float,
        values: np.ndarray,
        move_radius: float,
        lower: np.ndarray,
        upper: np.ndarray,
    ) -> tuple[float, np.ndarray]:
        stepped = np.clip(values + kappa * move_radius, lower, upper)
        stepped = _restore(stepped, values, self.transform.active)
        state = self.transform.forward(stepped)
        phi = float(
            np.asarray(state.rho_projected, dtype=np.float64)[self.transform.active].mean()
        )
        return phi, stepped

    def propose(
        self,
        *,
        rho: np.ndarray,
        objective_gradient: np.ndarray | None,
        constraint_gradients: dict[str, np.ndarray],
        constraint_values: dict[str, float],
        move_radius: float,
        backend_state: dict[str, Any],
    ) -> TrialProposal:
        values = np.asarray(rho, dtype=np.float64)
        if objective_gradient is not None and np.asarray(objective_gradient).shape != values.shape:
            raise ValueError("gradient shape does not match the design shape")
        move_radius = float(move_radius)
        lower, upper = _box(values, move_radius)
        sweep = _MonotoneSweep()

        def sample(kappa: float):
            phi, stepped = self._phi(kappa, values, move_radius, lower, upper)
            sweep.add(kappa, phi)
            return phi, stepped

        phi0, stepped0 = sample(0.0)
        if phi0 >= self.target - self.tolerance:
            if phi0 > self.target + self.tolerance:
                raise ValueError(
                    "projected volume is above the target beyond tolerance and the "
                    "restoration family is ascent-only"
                )
            return TrialProposal(
                delta=stepped0 - values,
                backend=self.backend_id,
                metadata={
                    "target": self.target,
                    "kappa": 0.0,
                    "phi_after": phi0,
                    "residual": abs(phi0 - self.target),
                    "bracketed": True,
                    "frontier_step": False,
                    "maintained_without_step": True,
                },
            )

        hi = 1.0
        phi_hi, stepped_hi = sample(hi)
        doublings = 0
        while phi_hi < self.target and doublings < MAX_KAPPA_DOUBLINGS:
            hi *= 2.0
            phi_hi, stepped_hi = sample(hi)
            doublings += 1

        if phi_hi < self.target:
            phi_front, stepped_front = sample(hi)
            return TrialProposal(
                delta=stepped_front - values,
                backend=self.backend_id,
                metadata={
                    "target": self.target,
                    "kappa": hi,
                    "phi_after": phi_front,
                    "residual": self.target - phi_front,
                    "bracketed": False,
                    "frontier_step": True,
                    "maintained_without_step": False,
                },
            )

        low, high = 0.0, hi
        stepped = stepped_hi
        for _ in range(BISECTION_STEPS):
            mid = 0.5 * (low + high)
            phi_mid, stepped_mid = sample(mid)
            if phi_mid < self.target:
                low = mid
            else:
                high = mid
                stepped = stepped_mid
        phi_at_target, stepped = sample(high)
        return TrialProposal(
            delta=stepped - values,
            backend=self.backend_id,
            metadata={
                "target": self.target,
                "kappa": high,
                "phi_after": phi_at_target,
                "residual": abs(phi_at_target - self.target),
                "bracketed": True,
                "frontier_step": False,
                "maintained_without_step": False,
            },
        )


class VolumeCorrectedObjectiveBackend:
    """Phase 2: descent-sign proposal + signed uniform volume correction.

    ``kappa_objective=1`` (a full single move step on the descent-sign field)
    produces the candidate, then ``kappa_volume`` in ``[-1, 1]`` is bisected on
    the *uniform* ascent so that the corrected candidate sits on the
    projected-volume target. Every candidate is clipped inside the per-cell
    move box and the restore contract keeps the non-active, forbidden and
    fixed-solid cells bitwise fixed.
    """

    backend_id = "volume-corrected-objective-oc"

    def __init__(self, *, transform, target: float, tolerance: float = 1e-4) -> None:
        if not 0.0 < float(target) < 1.0:
            raise ValueError("projected volume target must be within (0, 1)")
        if tolerance <= 0.0:
            raise ValueError("volume-correction tolerance must be positive")
        self.transform = transform
        self.target = float(target)
        self.tolerance = float(tolerance)

    def _phi(
        self,
        kappa_vol: float,
        values: np.ndarray,
        grad: np.ndarray,
        move_radius: float,
        lower: np.ndarray,
        upper: np.ndarray,
    ) -> tuple[float, np.ndarray]:
        stepped = np.clip(
            values + move_radius * np.where(grad < 0.0, 1.0, -1.0), lower, upper
        )
        stepped = np.clip(stepped + kappa_vol * move_radius, lower, upper)
        stepped = _restore(stepped, values, self.transform.active)
        state = self.transform.forward(stepped)
        phi = float(
            np.asarray(state.rho_projected, dtype=np.float64)[self.transform.active].mean()
        )
        return phi, stepped

    def propose(
        self,
        *,
        rho: np.ndarray,
        objective_gradient: np.ndarray,
        constraint_gradients: dict[str, np.ndarray],
        constraint_values: dict[str, float],
        move_radius: float,
        backend_state: dict[str, Any],
    ) -> TrialProposal:
        values = np.asarray(rho, dtype=np.float64)
        grad = np.asarray(objective_gradient, dtype=np.float64)
        if grad.shape != values.shape:
            raise ValueError("gradient shape does not match the design shape")
        move_radius = float(move_radius)
        lower, upper = _box(values, move_radius)
        sweep = _MonotoneSweep()

        def sample(kappa_vol: float):
            phi, stepped = self._phi(kappa_vol, values, grad, move_radius, lower, upper)
            sweep.add(kappa_vol, phi)
            return phi, stepped

        phi_low, stepped_low = sample(-1.0)
        phi_high, stepped_high = sample(1.0)
        if phi_low > self.target + self.tolerance:
            raise ValueError(
                "descent-sign proposal raises the projected volume above the "
                "target beyond tolerance; uniform ascent cannot correct it"
            )
        if phi_high < self.target - self.tolerance:
            raise ValueError(
                "descent-sign proposal leaves the projected volume below the "
                "target beyond tolerance; uniform ascent cannot recover it"
            )
        low, high = -1.0, 1.0
        stepped = stepped_low
        for _ in range(BISECTION_STEPS):
            mid = 0.5 * (low + high)
            phi_mid, stepped_mid = sample(mid)
            if phi_mid < self.target:
                low = mid
            else:
                high = mid
                stepped = stepped_mid
        phi_after, stepped = sample(high)
        residual = abs(phi_after - self.target)
        if residual > self.tolerance:
            raise ValueError(
                f"volume-correction residual {residual:.9f} exceeds tolerance "
                f"{self.tolerance}"
            )
        return TrialProposal(
            delta=stepped - values,
            backend=self.backend_id,
            metadata={
                "target": self.target,
                "kappa_objective": 1.0,
                "kappa_volume": high,
                "phi_after": phi_after,
                "residual": residual,
                "objective_step_taken": True,
            },
        )


__all__ = [
    "ProjectedVolumeRestorationBackend",
    "VolumeCorrectedObjectiveBackend",
    "MASK_DRIFT_TOLERANCE",
]
