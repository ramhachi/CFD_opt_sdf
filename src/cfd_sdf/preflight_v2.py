"""PQ3.3b preflight v2 measurement core.

The v1 preflight (docs/evidence/pq3_3b_preflight_2026_09.json) used an ad-hoc
phi(kappa) replica of the OC step instead of the registered backend, and left
the mask-drift field as ``None`` whenever the registered target was not
bracketed. v2 fixes both:

- every kappa evaluation goes through ``ProjectedVolumeTargetBackend`` itself
  (``propose`` for the bracket decision and the probe bisection,
  ``_projected_volume`` for the kappa sweep), so the non-active restore is the
  tested contract path from Work C.1;
- the non-active / forbidden / fixed-solid drift is always measured, and
  ``masks_invariant`` is always a verdict (never ``None``), regardless of the
  bracket outcome;
- the volume basis is ``mean(rho_projection[active])`` compared against the
  projected V_max. The raw design mean is never used as infeasibility evidence.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from cfd_sdf.stage_t_loop import ProjectedVolumeTargetBackend

MASK_DRIFT_TOLERANCE = 1e-12
MAX_KAPPA_DOUBLINGS = 30


def _max_drift(stepped: np.ndarray, values: np.ndarray, mask: np.ndarray) -> float:
    if not bool(mask.any()):
        return 0.0
    return float(np.max(np.abs(stepped[mask] - values[mask])))


def measure_level(
    *,
    transform,
    rho: np.ndarray,
    gradient: np.ndarray,
    forbidden_mask: np.ndarray,
    fixed_solid_mask: np.ndarray,
    move_limit: float,
    registered_target: float,
    v_max_projected: float,
    tolerance: float = 1e-4,
    eta: float = 0.5,
) -> dict[str, Any]:
    """Measure one continuation level through the registered backend.

    All arrays (``rho``, ``gradient``, masks) are flat F-order arrays of
    ``math.prod(transform.shape)`` entries, matching the fixed-grid artifacts.

    ``registered_target`` is judged in the projected basis
    (``mean(rho_projection[active])``). The sweep travels the backend's own
    kappa family, so drift is logged for every kappa (including the endpoints
    of the move box) whether or not the registered target is bracketed.
    """
    values = np.asarray(rho, dtype=np.float64)
    grad = np.asarray(gradient, dtype=np.float64)
    active = np.asarray(transform.active, dtype=bool)
    non_active = ~active
    forbidden = np.asarray(forbidden_mask, dtype=bool)
    fixed = np.asarray(fixed_solid_mask, dtype=bool)
    for name, mask in (("forbidden", forbidden), ("fixed_solid", fixed)):
        if mask.shape != values.shape:
            raise ValueError(f"{name} mask shape {mask.shape} != design shape {values.shape}")
        if bool((mask & active).any()):
            raise ValueError(f"{name} cells must not overlap the joint active mask")

    backend = ProjectedVolumeTargetBackend(
        transform=transform, target=registered_target, tolerance=tolerance, eta=eta
    )
    base = np.maximum(-grad, 0.0) ** eta
    lower = np.clip(values - move_limit, 0.0, 1.0)
    upper = np.clip(values + move_limit, 0.0, 1.0)

    def projected_volume(kappa: float):
        return backend._projected_volume(kappa, values, base, lower, upper)

    # 1) registered target: bracket decision through the backend's own propose()
    bracketed = False
    propagate_error: str | None = None
    try:
        backend.propose(
            rho=values,
            objective_gradient=grad,
            constraint_gradients={},
            constraint_values={},
            move_radius=move_limit,
            backend_state={},
        )
        bracketed = True
    except ValueError as exc:
        propagate_error = str(exc)

    # 2) kappa sweep on the backend's contract path: phi frontier + drift logs
    samples: list[dict[str, Any]] = []
    phi_previous = -np.inf
    monotone = True
    kappa = 0.0
    for step in range(MAX_KAPPA_DOUBLINGS + 1):
        phi, stepped = projected_volume(kappa)
        drifts = {
            "non_active": _max_drift(stepped, values, non_active),
            "forbidden": _max_drift(stepped, values, forbidden),
            "fixed_solid": _max_drift(stepped, values, fixed),
        }
        if step > 0 and phi < phi_previous - MASK_DRIFT_TOLERANCE:
            monotone = False
        phi_previous = phi
        samples.append(
            {
                "kappa": kappa,
                "phi": phi,
                "mask_drift": drifts,
                "mask_drift_max": max(drifts.values()),
            }
        )
        kappa = 1.0 if kappa == 0.0 else min(kappa * 2.0, float(2.0**MAX_KAPPA_DOUBLINGS))
        if step == MAX_KAPPA_DOUBLINGS:
            break
    phi_low = samples[0]["phi"]
    phi_frontier = max(sample["phi"] for sample in samples)
    kappa_frontier = samples[-1]["kappa"]

    # 3) a reachable sub-target exercises the full propose() bisection path
    probe_target = 0.5 * (phi_low + phi_frontier)
    probe: dict[str, Any] | None = None
    if phi_frontier > phi_low + tolerance:
        probe_backend = ProjectedVolumeTargetBackend(
            transform=transform, target=probe_target, tolerance=tolerance, eta=eta
        )
        try:
            proposal = probe_backend.propose(
                rho=values,
                objective_gradient=grad,
                constraint_gradients={},
                constraint_values={},
                move_radius=move_limit,
                backend_state={},
            )
            probe_kappa = float(proposal.metadata["kappa"])
            phi_probe, stepped_probe = projected_volume(probe_kappa)
            drifts = {
                "non_active": _max_drift(stepped_probe, values, non_active),
                "forbidden": _max_drift(stepped_probe, values, forbidden),
                "fixed_solid": _max_drift(stepped_probe, values, fixed),
            }
            probe = {
                "target": probe_target,
                "kappa": probe_kappa,
                "phi_after": phi_probe,
                "residual": abs(phi_probe - probe_target),
                "within_tolerance": abs(phi_probe - probe_target) <= tolerance,
                "mask_drift": drifts,
            }
        except (ValueError, KeyError) as exc:
            probe = {"error": str(exc)}

    # drift is always a float: take the worst over the whole measured path
    seen: list[dict[str, float]] = [sample["mask_drift"] for sample in samples]
    if probe is not None and "mask_drift" in probe:
        seen.append(probe["mask_drift"])
    mask_drift_max = {
        register: max(entry[register] for entry in seen) for register in seen[0]
    }

    projected_now = float(
        np.asarray(transform.forward(values).rho_projected, dtype=np.float64)[active].mean()
    )
    target_le_vmax = bool(float(registered_target) <= float(v_max_projected))

    return {
        "registered_target": registered_target,
        "move_limit": move_limit,
        "bracketed": bracketed,
        "bracket_error": propagate_error,
        "phi_design": projected_now,
        "phi_kappa0": phi_low,
        "phi_frontier": phi_frontier,
        "kappa_frontier": kappa_frontier,
        "frontier_growth": phi_frontier - projected_now,
        "monotone_nondecreasing": monotone,
        "mask_drift_max": mask_drift_max,
        "masks_invariant": bool(max(mask_drift_max.values()) <= MASK_DRIFT_TOLERANCE),
        "target_feasible_in_projected_basis": target_le_vmax,
        "probe": probe,
        "samples": samples,
    }
