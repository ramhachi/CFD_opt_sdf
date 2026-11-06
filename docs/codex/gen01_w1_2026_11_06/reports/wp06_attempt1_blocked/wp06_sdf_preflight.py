"""Reproduce the WP6 exact-distance conflict; successful exit confirms a blocker.

This calls the existing v18 field, not a new scene implementation. The
one-node adapter supplies precisely the lattice attributes read by axes().
All samples avoid chord ends, span tips, and the cross-section medial axis.
No registered fixture, source, solver, or qualification flag is changed.
"""
from __future__ import annotations

import hashlib
import json
import math
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np

ROOT = Path(__file__).resolve().parents[4]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]
import v18_plate as V  # noqa: E402


def value(point: np.ndarray, parameters: dict) -> float:
    lattice = SimpleNamespace(origin_m=tuple(point), spacing_m=0.01, shape=(1, 1, 1))
    return float(V.plate_phi(lattice, parameters).item())


def main() -> None:
    parameters = dict(xc=0.0, zc=0.0, alpha=0.0, L=1.0, t=0.1,
                      y_tip=0.5, camber=0.0, reflex=0.0)
    delta = 1e-6  # m; central differences compared with the independent derivative
    cases = (
        ("flat_control", 0.0, 0.0, 0.25, 0.1),
        ("camber", 0.1, 0.0, 0.25, 0.1),
        ("reflex", 0.0, 0.1, 0.0, 0.1),
        ("combined", 0.1, 0.1, 0.25, 0.1),
        ("camber_on_surface", 0.1, 0.0, 0.25, 0.1 / 2 + 0.1 / 12),
    )
    records = []
    for name, camber, reflex, x, z in cases:
        p = dict(parameters, camber=camber, reflex=reflex)
        point = np.array([x, 0.0, z])
        gradient = np.array([
            (value(point + delta * axis, p) - value(point - delta * axis, p)) / (2 * delta)
            for axis in np.eye(3)
        ])
        s = 2 * x / p["L"]
        slope = 4 * camber * s / p["L"] + 2 * reflex * (3 * s * s - 0.6) / p["L"]
        expected_gradient = np.array([slope, 0.0, 1.0])
        if not np.allclose(gradient, expected_gradient, atol=1e-8, rtol=0.0):
            raise RuntimeError(f"{name}: source field differs from the derivation")
        norm = float(np.linalg.norm(gradient))
        if name == "flat_control":
            if abs(norm - 1.0) > 1e-8:
                raise RuntimeError("flat stadium control failed")
        elif norm <= 1.0001:
            raise RuntimeError(f"{name}: the expected distance conflict was not reproduced")
        records.append(dict(name=name, parameters=p, point_m=point.tolist(), phi_m=value(point, p),
                            gradient=gradient.tolist(), gradient_norm=norm,
                            analytic_gradient_norm=math.hypot(slope, 1.0)))

    # A boundary witness suffices: if any boundary point is closer than phi,
    # phi cannot be the shortest distance. No nearest-point solver is needed.
    p = dict(parameters, camber=0.1)
    point = np.array([0.25, 0.0, 0.1])
    u = 0.242
    surface_z = p["t"] / 2 - p["camber"] * ((2 * u / p["L"]) ** 2 - 1 / 3)
    witness = np.array([u, 0.0, surface_z])
    witness_phi = value(witness, p)
    distance_upper_bound = float(np.linalg.norm(point - witness))
    if abs(witness_phi) > 1e-12 or not distance_upper_bound < value(point, p) - 1e-4:
        raise RuntimeError("closer boundary witness failed")

    result = dict(
        evidence_class="solver_free_development_diagnostic",
        status="CONTRACT_CONFLICT_CONFIRMED",
        source_path="scripts/v18_plate.py",
        source_sha256=hashlib.sha256((ROOT / "scripts/v18_plate.py").read_bytes()).hexdigest(),
        probe_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        numpy_version=np.__version__,
        finite_difference_step_m=delta,
        samples=records,
        boundary_witness=dict(point_m=point.tolist(), boundary_point_m=witness.tolist(),
                              boundary_phi_m=witness_phi, distance_upper_bound_m=distance_upper_bound,
                              source_phi_m=value(point, p)),
        scope="negative preflight only; neither scene acceptance nor topology/physics qualification",
    )
    print(json.dumps(result, sort_keys=True, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
