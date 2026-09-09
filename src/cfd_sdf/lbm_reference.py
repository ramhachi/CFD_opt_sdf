"""Small, deterministic D2Q9 BGK reference solver.

This module is deliberately a bounded numerical reference for the P1 LBM
forward-calculation experiment.  It uses lattice units, periodic streaming,
and FP64 NumPy arrays so a later backend can reproduce the same discrete
update.  It does not implement walls, forces, geometry, or derivatives.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from math import pi
from typing import Any

import numpy as np


# q=0, axial directions, then diagonals.  Population arrays use (q, y, x).
DIRECTIONS = np.asarray(
    (
        (0, 0),
        (1, 0),
        (0, 1),
        (-1, 0),
        (0, -1),
        (1, 1),
        (-1, 1),
        (-1, -1),
        (1, -1),
    ),
    dtype=np.int64,
)
WEIGHTS = np.asarray(
    (4.0 / 9.0, 1.0 / 9.0, 1.0 / 9.0, 1.0 / 9.0, 1.0 / 9.0, 1.0 / 36.0, 1.0 / 36.0, 1.0 / 36.0, 1.0 / 36.0),
    dtype=np.float64,
)
CS2 = 1.0 / 3.0
Q = 9
MASS_RELATIVE_TOLERANCE = 1.0e-12
MOMENTUM_ABSOLUTE_TOLERANCE = 1.0e-12
DECAY_RELATIVE_TOLERANCE = 5.0e-2


@dataclass(frozen=True)
class LBMConfig:
    """Controls for a periodic lattice-unit D2Q9 BGK run.

    ``nx`` and ``ny`` are cell counts, ``steps`` is the number of lattice
    time steps, ``viscosity`` is the kinematic viscosity in lattice units, and
    ``velocity`` is the Taylor--Green characteristic velocity in lattice
    units.  The BGK relaxation time is ``tau = 0.5 + 3*viscosity``.
    """

    nx: int = 32
    ny: int = 32
    steps: int = 100
    viscosity: float = 0.1
    velocity: float = 0.01

    def __post_init__(self) -> None:
        for name in ("nx", "ny", "steps"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, np.integer)):
                raise ValueError(f"{name} must be an integer")
            object.__setattr__(self, name, int(value))
        if self.nx < 4 or self.ny < 4:
            raise ValueError("nx and ny must be at least 4 cells")
        if self.steps < 0:
            raise ValueError("steps must be non-negative")
        if isinstance(self.viscosity, bool):
            raise ValueError("viscosity must be finite and positive")
        try:
            viscosity = float(self.viscosity)
        except (TypeError, ValueError) as exc:
            raise ValueError("viscosity must be finite and positive") from exc
        object.__setattr__(self, "viscosity", viscosity)
        if not np.isfinite(viscosity) or viscosity <= 0.0:
            raise ValueError("viscosity must be finite and positive")
        tau = self.tau
        if tau >= 2.0:
            raise ValueError("viscosity must keep BGK tau below 2")
        if isinstance(self.velocity, bool):
            raise ValueError("velocity must be finite and non-negative")
        try:
            velocity = float(self.velocity)
        except (TypeError, ValueError) as exc:
            raise ValueError("velocity must be finite and non-negative") from exc
        object.__setattr__(self, "velocity", velocity)
        if not np.isfinite(velocity) or velocity < 0.0:
            raise ValueError("velocity must be finite and non-negative")
        # The characteristic velocity is expected to be low Mach.  The
        # rectangular Taylor--Green initializer additionally checks its
        # transverse component after applying the aspect-ratio factor.
        if self.velocity >= 0.1:
            raise ValueError("velocity must be below 0.1 lattice units")

    @property
    def tau(self) -> float:
        """BGK relaxation time in lattice units."""

        return 0.5 + 3.0 * float(self.viscosity)

    @property
    def omega(self) -> float:
        """BGK relaxation frequency ``1/tau``."""

        return 1.0 / self.tau


def _velocity_components(rho: np.ndarray, u: Any) -> tuple[np.ndarray, np.ndarray]:
    """Normalize either canonical ``(2, ...)`` or trailing ``(..., 2)`` u."""

    velocity = np.asarray(u, dtype=np.float64)
    if velocity.ndim >= 1 and velocity.shape[0] == 2 and velocity.shape[1:] == rho.shape:
        ux, uy = velocity[0], velocity[1]
    elif velocity.ndim >= 1 and velocity.shape[-1] == 2 and velocity.shape[:-1] == rho.shape:
        ux, uy = velocity[..., 0], velocity[..., 1]
    else:
        raise ValueError(
            "u must have shape (2, ...rho.shape) or (...rho.shape, 2)"
        )
    if not np.all(np.isfinite(velocity)):
        raise ValueError("u must contain only finite values")
    return ux, uy


def equilibrium(rho: Any, u: Any) -> np.ndarray:
    """Return the D2Q9 second-order isothermal equilibrium populations.

    ``rho`` may be scalar or any array shape.  The canonical velocity shape
    is ``(2, *rho.shape)``.  For convenience, the equivalent trailing-vector
    shape ``(*rho.shape, 2)`` is also accepted.  The returned array always
    places the population axis first: ``(9, *rho.shape)``.
    """

    density = np.asarray(rho, dtype=np.float64)
    if not np.all(np.isfinite(density)):
        raise ValueError("rho must contain only finite values")
    if np.any(density <= 0.0):
        raise ValueError("rho must be strictly positive")
    ux, uy = _velocity_components(density, u)
    cx = DIRECTIONS[:, 0].reshape((Q,) + (1,) * density.ndim)
    cy = DIRECTIONS[:, 1].reshape((Q,) + (1,) * density.ndim)
    weights = WEIGHTS.reshape((Q,) + (1,) * density.ndim)
    cu = cx * ux + cy * uy
    speed_squared = ux * ux + uy * uy
    return weights * density * (
        1.0 + cu / CS2 + 0.5 * (cu / CS2) ** 2 - 0.5 * speed_squared / CS2
    )


def macroscopic(f: Any) -> tuple[np.ndarray, np.ndarray]:
    """Recover density and velocity from populations shaped ``(9, ...)``."""

    populations = np.asarray(f, dtype=np.float64)
    if populations.ndim < 1 or populations.shape[0] != Q:
        raise ValueError("f must have population shape (9, ...)")
    if not np.all(np.isfinite(populations)):
        raise ValueError("f must contain only finite values")
    rho = np.sum(populations, axis=0, dtype=np.float64)
    if np.any(rho <= 0.0) or not np.all(np.isfinite(rho)):
        raise ValueError("macroscopic density must be finite and strictly positive")
    ux = np.sum(populations * DIRECTIONS[:, 0].reshape((Q,) + (1,) * (rho.ndim)), axis=0)
    uy = np.sum(populations * DIRECTIONS[:, 1].reshape((Q,) + (1,) * (rho.ndim)), axis=0)
    u = np.stack((ux / rho, uy / rho), axis=0)
    return rho, u


def one_step(f: Any, config: LBMConfig) -> np.ndarray:
    """Advance one periodic BGK lattice step without mutating ``f``.

    The input and output arrays use the canonical FP64 shape ``(9, ny, nx)``.
    Collision is local BGK relaxation followed by exact periodic streaming.
    """

    if not isinstance(config, LBMConfig):
        raise TypeError("config must be an LBMConfig")
    populations = np.asarray(f, dtype=np.float64)
    expected_shape = (Q, config.ny, config.nx)
    if populations.shape != expected_shape:
        raise ValueError(f"f must have shape {expected_shape}")
    rho, u = macroscopic(populations)
    post_collision = populations - config.omega * (
        populations - equilibrium(rho, u)
    )
    streamed = np.empty_like(post_collision, dtype=np.float64)
    for q, (cx, cy) in enumerate(DIRECTIONS):
        streamed[q] = np.roll(post_collision[q], shift=(int(cy), int(cx)), axis=(0, 1))
    return streamed


def taylor_green_initial_state(config: LBMConfig) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Build the analytic, divergence-free low-Mach Taylor--Green state.

    The lattice domain is ``x=0..nx-1`` and ``y=0..ny-1`` with periodic
    lengths ``Lx=nx`` and ``Ly=ny``.  For a rectangular grid the transverse
    velocity is scaled by ``kx/ky`` so the discrete trigonometric field stays
    divergence-free.  The density includes the corresponding isothermal
    pressure correction at ``O(U**2)`` and is normalized to unit mean.
    """

    if not isinstance(config, LBMConfig):
        raise TypeError("config must be an LBMConfig")
    kx = 2.0 * pi / config.nx
    ky = 2.0 * pi / config.ny
    ratio = kx / ky
    x = np.arange(config.nx, dtype=np.float64)[None, :]
    y = np.arange(config.ny, dtype=np.float64)[:, None]
    phase_x = kx * x
    phase_y = ky * y
    ux = config.velocity * np.sin(phase_x) * np.cos(phase_y)
    uy = -config.velocity * ratio * np.cos(phase_x) * np.sin(phase_y)
    u = np.stack((ux, uy), axis=0)
    density = 1.0 + (config.velocity**2 / (4.0 * CS2)) * (
        np.cos(2.0 * phase_x) + ratio**2 * np.cos(2.0 * phase_y)
    )
    density += 1.0 - float(np.mean(density))
    max_component = float(np.max(np.abs(u)))
    if max_component >= 0.1:
        raise ValueError(
            "the rectangular Taylor--Green initializer exceeds 0.1 lattice units; "
            "reduce velocity or aspect ratio"
        )
    return density, u, equilibrium(density, u)


def _vector_rms(u: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.sum(u * u, axis=0), dtype=np.float64)))


def _json_float(value: Any) -> float:
    """Convert NumPy scalars to plain Python floats for JSON serialization."""

    return float(value)


def run_taylor_green(config: LBMConfig | None = None) -> dict[str, object]:
    """Run the periodic Taylor--Green benchmark and return JSON-safe metrics.

    The returned evidence is intentionally bounded: it qualifies numerical
    conservation and low-Mach viscous decay for this reference stencil only.
    It is explicitly not target-aerodynamics or shape-gradient evidence.
    """

    if config is None:
        config = LBMConfig()
    if not isinstance(config, LBMConfig):
        raise TypeError("config must be an LBMConfig")
    rho_initial, u_initial, populations = taylor_green_initial_state(config)
    initial_mass = float(np.sum(rho_initial, dtype=np.float64))
    initial_momentum = np.sum(rho_initial[None, ...] * u_initial, axis=(1, 2), dtype=np.float64)
    for _ in range(config.steps):
        populations = one_step(populations, config)
    rho_final, u_final = macroscopic(populations)
    final_mass = float(np.sum(rho_final, dtype=np.float64))
    final_momentum = np.sum(rho_final[None, ...] * u_final, axis=(1, 2), dtype=np.float64)

    k_squared = (2.0 * pi / config.nx) ** 2 + (2.0 * pi / config.ny) ** 2
    analytic_decay_factor = float(np.exp(-config.viscosity * k_squared * config.steps))
    analytic_velocity = u_initial * analytic_decay_factor
    velocity_error = u_final - analytic_velocity
    velocity_error_rms = _vector_rms(velocity_error)
    analytic_velocity_rms = _vector_rms(analytic_velocity)
    velocity_relative_error = (
        velocity_error_rms / analytic_velocity_rms if analytic_velocity_rms > 0.0 else velocity_error_rms
    )
    mass_absolute_error = abs(final_mass - initial_mass)
    mass_relative_error = mass_absolute_error / abs(initial_mass)
    momentum_error = final_momentum - initial_momentum
    momentum_absolute_error = float(np.linalg.norm(momentum_error))
    momentum_pass = momentum_absolute_error <= MOMENTUM_ABSOLUTE_TOLERANCE
    mass_pass = mass_relative_error <= MASS_RELATIVE_TOLERANCE
    decay_pass = velocity_relative_error <= DECAY_RELATIVE_TOLERANCE
    numerical_pass = mass_pass and momentum_pass and decay_pass

    config_dict = asdict(config)
    summary: dict[str, object] = {
        "schema_version": 1,
        "benchmark": "taylor_green_vortex",
        "backend": "numpy_cpu",
        "precision": "float64",
        "deterministic": True,
        "status": "pass" if numerical_pass else "fail",
        "overall_status": "pass" if numerical_pass else "fail",
        "evidence_status": "NUMERICAL_REFERENCE_ONLY",
        "evidence_scope": "NOT_TARGET_AERO_OR_SHAPE_GRADIENT_EVIDENCE",
        "target_aero_evidence": "NOT_AVAILABLE",
        "shape_gradient_evidence": "NOT_AVAILABLE",
        "config": config_dict,
        "lattice": {
            "model": "D2Q9_BGK",
            "population_shape": [Q, config.ny, config.nx],
            "population_axis_order": ["q", "y", "x"],
            "directions": DIRECTIONS.tolist(),
            "weights": WEIGHTS.tolist(),
            "cs2": CS2,
            "tau": config.tau,
            "omega": config.omega,
            "units": "lattice_units_dx_eq_dt_eq_1",
            "boundary": "periodic",
        },
        "initial_condition": {
            "type": "taylor_green_vortex",
            "kx": 2.0 * pi / config.nx,
            "ky": 2.0 * pi / config.ny,
            "characteristic_velocity": config.velocity,
            "pressure_correction": "isothermal_O(U^2)_density",
        },
        "initial": {
            "mass": initial_mass,
            "momentum": [_json_float(value) for value in initial_momentum],
            "rho_min": _json_float(np.min(rho_initial)),
            "rho_max": _json_float(np.max(rho_initial)),
            "velocity_rms": _vector_rms(u_initial),
            "max_speed": _json_float(np.max(np.sqrt(np.sum(u_initial * u_initial, axis=0)))),
        },
        "final": {
            "mass": final_mass,
            "momentum": [_json_float(value) for value in final_momentum],
            "rho_min": _json_float(np.min(rho_final)),
            "rho_max": _json_float(np.max(rho_final)),
            "velocity_rms": _vector_rms(u_final),
            "max_speed": _json_float(np.max(np.sqrt(np.sum(u_final * u_final, axis=0)))),
        },
        "conservation": {
            "mass_absolute_error": mass_absolute_error,
            "mass_relative_error": mass_relative_error,
            "mass_tolerance": MASS_RELATIVE_TOLERANCE,
            "mass_pass": mass_pass,
            "momentum_absolute_error": momentum_absolute_error,
            "momentum_tolerance": MOMENTUM_ABSOLUTE_TOLERANCE,
            "momentum_pass": momentum_pass,
        },
        "analytic_decay": {
            "wave_number_squared": k_squared,
            "time": config.steps,
            "factor": analytic_decay_factor,
            "simulated_velocity_rms": _vector_rms(u_final),
            "analytic_velocity_rms": analytic_velocity_rms,
            "rms_error": velocity_error_rms,
            "relative_rms_error": velocity_relative_error,
            "relative_tolerance": DECAY_RELATIVE_TOLERANCE,
            "pass": decay_pass,
        },
        "checks": {
            "mass_conservation": mass_pass,
            "momentum_conservation": momentum_pass,
            "analytic_decay": decay_pass,
            "numerical_pass": numerical_pass,
        },
    }
    return summary


__all__ = [
    "CS2",
    "DECAY_RELATIVE_TOLERANCE",
    "DIRECTIONS",
    "LBMConfig",
    "MASS_RELATIVE_TOLERANCE",
    "MOMENTUM_ABSOLUTE_TOLERANCE",
    "Q",
    "WEIGHTS",
    "equilibrium",
    "macroscopic",
    "one_step",
    "run_taylor_green",
    "taylor_green_initial_state",
]
