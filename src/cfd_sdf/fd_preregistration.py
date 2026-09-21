"""Pre-registration contracts for finite-difference gradient campaigns (DF2).

Architecture-plan section 6.2 requires every experiment to be registered before
the solver runs. This module owns the FD-specific manifest and its fail-closed
validation: the qualified FD profile (5% central-difference relative error,
sign agreement, at least four epsilons, at least one gradient-aligned direction
plus two random seeds) is versioned here, and a manifest that does not match the
profile is rejected rather than silently weakened.

The manifest is immutable-by-hash: ``manifest_hash`` covers every field, so a
campaign that was changed after the fact no longer matches what was registered.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

FD_QUALIFICATION_PROFILE_V1: dict[str, Any] = {
    "profile_id": "fd_gradient_v1",
    "relative_error_max": 0.05,
    "require_sign_agreement": True,
    "min_epsilons": 4,
    "min_random_seeds": 2,
    "require_gradient_aligned_direction": True,
    "near_zero_rule": "directions with a near-zero reference derivative are "
    "judged by a pre-registered absolute error from the response scale, never "
    "by a relative error",
    "scope": "reduced laminar fixture; not a target-physics universal threshold",
}

MANIFEST_SCHEMA_VERSION = 1


class FdPreregistrationError(ValueError):
    """Fail-closed FD manifest contract violation."""


@dataclass(frozen=True)
class FdDirection:
    name: str
    role: str  # gradient_aligned | random | custom
    seed: int | None
    sign_convention: str
    description: str = ""


@dataclass(frozen=True)
class FdCampaignManifest:
    campaign_id: str
    hypothesis: str
    decision: str
    fixture: dict[str, Any]
    responses: tuple[str, ...]
    epsilons: tuple[float, ...]
    directions: tuple[FdDirection, ...]
    uncertainty_rule: str
    gates: dict[str, Any]
    stop_conditions: tuple[str, ...]
    fallback_conditions: tuple[str, ...]
    profile_id: str = FD_QUALIFICATION_PROFILE_V1["profile_id"]
    random_seeds: tuple[int, ...] = ()
    environment: dict[str, Any] = field(default_factory=dict)
    code_commit: str | None = None
    created: str = field(default_factory=lambda: date.today().isoformat())
    schema_version: int = MANIFEST_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def manifest_hash(self) -> str:
        payload = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def build_fd_campaign_manifest(
    *,
    campaign_id: str,
    hypothesis: str,
    decision: str,
    fixture: dict[str, Any],
    responses: list[str] | tuple[str, ...],
    epsilons: list[float] | tuple[float, ...],
    directions: list[FdDirection] | tuple[FdDirection, ...],
    uncertainty_rule: str,
    gates: dict[str, Any],
    stop_conditions: list[str] | tuple[str, ...],
    fallback_conditions: list[str] | tuple[str, ...] = (),
    environment: dict[str, Any] | None = None,
    code_commit: str | None = None,
) -> FdCampaignManifest:
    random_seeds = tuple(sorted(d.seed for d in directions if d.seed is not None))
    manifest = FdCampaignManifest(
        campaign_id=campaign_id,
        hypothesis=hypothesis,
        decision=decision,
        fixture=dict(fixture),
        responses=tuple(responses),
        epsilons=tuple(float(e) for e in epsilons),
        directions=tuple(directions),
        uncertainty_rule=uncertainty_rule,
        gates=dict(gates),
        stop_conditions=tuple(stop_conditions),
        fallback_conditions=tuple(fallback_conditions),
        random_seeds=random_seeds,
        environment={
            "registered_at_utc": datetime.now(timezone.utc).isoformat(),
            **(environment or {}),
        },
        code_commit=code_commit,
    )
    validate_fd_campaign_manifest(manifest)
    return manifest


def validate_fd_campaign_manifest(manifest: FdCampaignManifest) -> None:
    """Fail-closed validation against the registered FD qualification profile."""

    profile = FD_QUALIFICATION_PROFILE_V1
    if manifest.profile_id != profile["profile_id"]:
        raise FdPreregistrationError(
            f"unknown FD profile {manifest.profile_id!r}; registered profile is "
            f"{profile['profile_id']!r}"
        )
    if manifest.schema_version != MANIFEST_SCHEMA_VERSION:
        raise FdPreregistrationError("unsupported FD manifest schema_version")
    if not manifest.responses:
        raise FdPreregistrationError("a campaign must declare at least one response")
    if len(manifest.epsilons) < int(profile["min_epsilons"]):
        raise FdPreregistrationError(
            f"at least {profile['min_epsilons']} epsilons are required, "
            f"got {len(manifest.epsilons)}"
        )
    if any(e <= 0.0 for e in manifest.epsilons):
        raise FdPreregistrationError("epsilons must be positive")
    if not any(d.role == "gradient_aligned" for d in manifest.directions):
        raise FdPreregistrationError("a gradient-aligned direction is required")
    random_seeds = {d.seed for d in manifest.directions if d.role == "random"}
    if len(random_seeds) < int(profile["min_random_seeds"]):
        raise FdPreregistrationError(
            f"at least {profile['min_random_seeds']} random seeds are required"
        )
    for direction in manifest.directions:
        if not direction.sign_convention.strip():
            raise FdPreregistrationError(
                f"direction {direction.name!r} must declare its sign convention"
            )
    gates = manifest.gates
    for key in (
        "convergence",
        "stationarity",
        "mesh",
        "geometry",
        "required_pairs",
        "resolvability",
    ):
        if key not in gates:
            raise FdPreregistrationError(f"gates.{key} is required")
    if not manifest.stop_conditions:
        raise FdPreregistrationError("stop_conditions must not be empty")
    if not manifest.fixture.get("candidate_binding"):
        raise FdPreregistrationError("fixture.candidate_binding is required")
    for key in ("problem_spec_sha256", "grid_family", "refinement_ratio"):
        if key not in manifest.fixture:
            raise FdPreregistrationError(f"fixture.{key} is required")


def write_fd_campaign_manifest(manifest: FdCampaignManifest, path: str | Path) -> Path:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    document = {"manifest": manifest.to_dict(), "manifest_hash": manifest.manifest_hash()}
    output.write_text(json.dumps(document, indent=2), encoding="utf-8")
    return output


def read_fd_campaign_manifest(path: str | Path) -> tuple[FdCampaignManifest, str]:
    document = json.loads(Path(path).read_text(encoding="utf-8"))
    raw = document.get("manifest")
    if not isinstance(raw, dict):
        raise FdPreregistrationError("manifest document must contain a 'manifest' object")
    directions = tuple(
        FdDirection(
            name=str(item["name"]),
            role=str(item["role"]),
            seed=item.get("seed"),
            sign_convention=str(item.get("sign_convention", "")),
            description=str(item.get("description", "")),
        )
        for item in raw.pop("directions", [])
    )
    manifest = FdCampaignManifest(
        directions=directions,
        **{key: value for key, value in raw.items() if key in FdCampaignManifest.__dataclass_fields__},
    )
    validate_fd_campaign_manifest(manifest)
    registered = document.get("manifest_hash")
    actual = manifest.manifest_hash()
    if registered != actual:
        raise FdPreregistrationError(
            f"manifest hash mismatch: registered={registered!r}, recomputed={actual!r}"
        )
    return manifest, actual


def evaluate_fd_campaign_rows(
    manifest: FdCampaignManifest,
    rows: list[dict[str, Any]],
    *,
    near_zero_relative: float = 1e-3,
) -> dict[str, Any]:
    """Verdict the registered FD table against the qualification profile.

    Every registered ``(direction, epsilon)`` pair must be present exactly once
    and must declare convergence. Rows with ``|analytic|`` below
    ``near_zero_relative * response_scale`` are judged by the pre-registered
    absolute error ``near_zero_absolute_error`` instead of a relative error.
    """

    profile = FD_QUALIFICATION_PROFILE_V1
    scale = manifest.fixture.get("response_scale")
    if scale is None:
        raise FdPreregistrationError(
            "fixture.response_scale is required to judge near-zero rows"
        )
    absolute_floor = manifest.fixture.get(
        "near_zero_absolute_error", float(scale) * near_zero_relative
    )
    expected = {
        (direction.name, float(epsilon))
        for direction in manifest.directions
        for epsilon in manifest.epsilons
    }
    seen: dict[tuple[str, float], dict[str, Any]] = {}
    for row in rows:
        key = (str(row.get("direction")), float(row.get("epsilon", 0.0)))
        if key in seen:
            raise FdPreregistrationError(f"duplicate FD row {key!r}")
        if key not in expected:
            raise FdPreregistrationError(f"unregistered FD row {key!r}")
        seen[key] = row
    missing = sorted(expected - set(seen))
    if missing:
        raise FdPreregistrationError(f"missing FD rows: {missing}")

    checks = []
    failures = []
    for direction in manifest.directions:
        for epsilon in manifest.epsilons:
            row = seen[(direction.name, float(epsilon))]
            if not bool(row.get("converged")):
                checks.append(
                    {
                        "direction": direction.name,
                        "epsilon": float(epsilon),
                        "status": "unconverged",
                    }
                )
                failures.append((direction.name, float(epsilon), "unconverged"))
                continue
            fd = float(row["fd"])
            analytic = float(row["analytic"])
            if abs(analytic) < near_zero_relative * abs(float(scale)):
                error = abs(fd - analytic)
                passed = error <= float(absolute_floor)
                checks.append(
                    {
                        "direction": direction.name,
                        "epsilon": float(epsilon),
                        "status": "absolute_rule",
                        "absolute_error": error,
                        "absolute_floor": float(absolute_floor),
                        "passed": passed,
                    }
                )
                if not passed:
                    failures.append((direction.name, float(epsilon), "absolute_error"))
                continue
            relative = abs(fd - analytic) / abs(analytic)
            sign_ok = (fd >= 0.0) == (analytic >= 0.0)
            passed = relative <= float(profile["relative_error_max"]) and (
                sign_ok or not profile["require_sign_agreement"]
            )
            checks.append(
                {
                    "direction": direction.name,
                    "epsilon": float(epsilon),
                    "status": "relative_rule",
                    "relative_error": relative,
                    "ratio": fd / analytic,
                    "sign_agreement": sign_ok,
                    "passed": passed,
                }
            )
            if not passed:
                failures.append((direction.name, float(epsilon), "relative_error"))
    return {
        "campaign_id": manifest.campaign_id,
        "manifest_hash": manifest.manifest_hash(),
        "profile_id": manifest.profile_id,
        "n_rows": len(seen),
        "n_failures": len(failures),
        "failures": [
            {"direction": d, "epsilon": e, "reason": r} for d, e, r in failures
        ],
        "passed": not failures,
        "checks": checks,
    }


# --- PQ1 campaign semantics v2 -------------------------------------------------
#
# The v1 manifest demanded an adjoint gate on every perturbation row while the
# runner only runs the primal there. The v2 semantics separate the roles:
# the base evaluation owns the adjoint and the analytic derivative; the
# +/-epsilon perturbations only need primal values under the same mesh/spec/
# solver profile. Near-zero analytic derivatives may not support a ratio-pass.

FD_V2_REQUIRED_BASE_GATES = (
    "mesh",
    "primal_residual",
    "primal_stationarity",
    "adjoint_residual",
    "final_time_binding",
    "response_hash",
)
FD_V2_REQUIRED_PERTURBATION_GATES = (
    "mesh",
    "spec_binding",
    "solver_profile",
    "primal_residual",
    "primal_stationarity",
    "response_hash",
)


@dataclass(frozen=True)
class FdDirectionV2:
    name: str
    role: str  # gradient_aligned | orthogonal | random
    seed: int | None
    analytic_reference: float
    sign_convention: str
    description: str = ""


@dataclass(frozen=True)
class FdCampaignManifestV2:
    campaign_id: str
    hypothesis: str
    decision: str
    fixture: dict[str, Any]
    responses: tuple[str, ...]
    epsilons: tuple[float, ...]
    directions: tuple[FdDirectionV2, ...]
    base_gates: dict[str, bool]
    perturbation_gate_template: dict[str, bool]
    noise_floor: float
    uncertainty_rule: str
    stop_conditions: tuple[str, ...]
    fallback_conditions: tuple[str, ...] = ()
    environment: dict[str, Any] = field(default_factory=dict)
    code_commit: str | None = None
    created: str = field(default_factory=lambda: date.today().isoformat())
    schema_version: int = 2

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def manifest_hash(self) -> str:
        payload = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def build_fd_campaign_manifest_v2(
    *,
    campaign_id: str,
    hypothesis: str,
    decision: str,
    fixture: dict[str, Any],
    responses: list[str] | tuple[str, ...],
    epsilons: list[float] | tuple[float, ...],
    directions: list[FdDirectionV2] | tuple[FdDirectionV2, ...],
    base_gates: dict[str, bool],
    perturbation_gate_template: dict[str, bool],
    noise_floor: float,
    uncertainty_rule: str,
    stop_conditions: list[str] | tuple[str, ...],
    fallback_conditions: list[str] | tuple[str, ...] = (),
    environment: dict[str, Any] | None = None,
    code_commit: str | None = None,
) -> FdCampaignManifestV2:
    manifest = FdCampaignManifestV2(
        campaign_id=campaign_id,
        hypothesis=hypothesis,
        decision=decision,
        fixture=dict(fixture),
        responses=tuple(responses),
        epsilons=tuple(float(e) for e in epsilons),
        directions=tuple(directions),
        base_gates=dict(base_gates),
        perturbation_gate_template=dict(perturbation_gate_template),
        noise_floor=float(noise_floor),
        uncertainty_rule=uncertainty_rule,
        stop_conditions=tuple(stop_conditions),
        fallback_conditions=tuple(fallback_conditions),
        environment={
            "registered_at_utc": datetime.now(timezone.utc).isoformat(),
            **(environment or {}),
        },
        code_commit=code_commit,
    )
    validate_fd_campaign_manifest_v2(manifest)
    return manifest


def validate_fd_campaign_manifest_v2(manifest: FdCampaignManifestV2) -> None:
    if manifest.schema_version != 2:
        raise FdPreregistrationError("v2 manifest schema_version must be 2")
    if not manifest.responses:
        raise FdPreregistrationError("a campaign must declare at least one response")
    if len(manifest.epsilons) < int(FD_QUALIFICATION_PROFILE_V1["min_epsilons"]):
        raise FdPreregistrationError(
            f"at least {FD_QUALIFICATION_PROFILE_V1['min_epsilons']} epsilons are required"
        )
    if any(epsilon <= 0.0 for epsilon in manifest.epsilons):
        raise FdPreregistrationError("epsilons must be positive")
    if not any(direction.role == "gradient_aligned" for direction in manifest.directions):
        raise FdPreregistrationError("a gradient-aligned direction is required")
    random_seeds = {direction.seed for direction in manifest.directions if direction.role == "random"}
    if len(random_seeds) < int(FD_QUALIFICATION_PROFILE_V1["min_random_seeds"]):
        raise FdPreregistrationError(
            f"at least {FD_QUALIFICATION_PROFILE_V1['min_random_seeds']} random seeds are required"
        )
    for direction in manifest.directions:
        if not direction.sign_convention.strip():
            raise FdPreregistrationError(
                f"direction {direction.name!r} must declare its sign convention"
            )
        if direction.role == "gradient_aligned" and direction.analytic_reference == 0.0:
            raise FdPreregistrationError(
                "the gradient-aligned direction must register a non-zero analytic reference"
            )
    for gate in FD_V2_REQUIRED_BASE_GATES:
        if gate not in manifest.base_gates:
            raise FdPreregistrationError(f"base_gates.{gate} is required")
    for gate in FD_V2_REQUIRED_PERTURBATION_GATES:
        if gate not in manifest.perturbation_gate_template:
            raise FdPreregistrationError(f"perturbation_gate_template.{gate} is required")
    if manifest.base_gates.get("adjoint_residual") is not True:
        raise FdPreregistrationError("the base evaluation must require the adjoint gate")
    if "adjoint_residual" in manifest.perturbation_gate_template:
        raise FdPreregistrationError(
            "perturbation rows must not require an adjoint gate; they are primal-only"
        )
    if manifest.noise_floor <= 0.0:
        raise FdPreregistrationError("noise_floor must be positive")
    if not manifest.stop_conditions:
        raise FdPreregistrationError("stop_conditions must not be empty")
    for key in ("candidate_binding", "problem_spec_sha256", "grid_family", "refinement_ratio", "response_scale"):
        if key not in manifest.fixture:
            raise FdPreregistrationError(f"fixture.{key} is required")


def evaluate_fd_campaign_v2(
    manifest: FdCampaignManifestV2,
    *,
    base_gates: dict[str, bool],
    base_analytic: dict[str, float],
    rows: list[dict[str, Any]],
    tolerance: float | None = None,
) -> dict[str, Any]:
    """Verdict the v2 table: role gates, noise floor, epsilon plateau, ratios."""

    profile = FD_QUALIFICATION_PROFILE_V1
    tolerance = float(profile["relative_error_max"] if tolerance is None else tolerance)
    scale = float(manifest.fixture["response_scale"])
    noise_floor = float(manifest.noise_floor) * abs(scale)

    base_failures = [
        gate for gate, passed in base_gates.items() if not bool(passed)
    ]
    expected = {
        (direction.name, float(epsilon))
        for direction in manifest.directions
        for epsilon in manifest.epsilons
    }
    seen: dict[tuple[str, float], dict[str, Any]] = {}
    for row in rows:
        key = (str(row.get("direction")), float(row.get("epsilon", 0.0)))
        if key not in expected:
            raise FdPreregistrationError(f"unregistered FD row {key!r}")
        if key in seen:
            raise FdPreregistrationError(f"duplicate FD row {key!r}")
        seen[key] = row
    missing = sorted(expected - set(seen))
    if missing:
        raise FdPreregistrationError(f"missing FD rows: {missing}")

    checks: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    below_noise: list[str] = []
    for direction in manifest.directions:
        analytic = float(base_analytic[direction.name])
        direction_rows = [
            seen[(direction.name, float(epsilon))] for epsilon in manifest.epsilons
        ]
        if abs(analytic) < noise_floor:
            below_noise.append(direction.name)
            checks.append(
                {
                    "direction": direction.name,
                    "status": "below_noise_floor",
                    "analytic": analytic,
                    "noise_floor": noise_floor,
                }
            )
            continue
        ratios: list[float] = []
        for row in direction_rows:
            gate_failures = [
                gate
                for gate, passed in (row.get("gates") or {}).items()
                if not bool(passed)
            ]
            if not bool(row.get("converged")) or gate_failures:
                failures.append(
                    {
                        "direction": direction.name,
                        "epsilon": float(row["epsilon"]),
                        "reason": "gate_failure",
                        "gate_failures": gate_failures,
                    }
                )
                continue
            fd = float(row["fd"])
            ratio = fd / analytic
            ratios.append(ratio)
            relative = abs(ratio - 1.0)
            checks.append(
                {
                    "direction": direction.name,
                    "epsilon": float(row["epsilon"]),
                    "status": "relative_rule",
                    "ratio": ratio,
                    "relative_error": relative,
                    "passed": relative <= tolerance,
                }
            )
            if relative > tolerance:
                failures.append(
                    {
                        "direction": direction.name,
                        "epsilon": float(row["epsilon"]),
                        "reason": "relative_error",
                        "relative_error": relative,
                    }
                )
        if ratios:
            plateau = max(ratios) - min(ratios)
            checks.append(
                {
                    "direction": direction.name,
                    "status": "epsilon_plateau",
                    "spread": plateau,
                    "plateau_ok": plateau <= tolerance,
                }
            )
            if plateau > tolerance:
                failures.append(
                    {
                        "direction": direction.name,
                        "reason": "epsilon_not_plateau",
                        "spread": plateau,
                    }
                )
    passed = not failures and not base_failures
    return {
        "campaign_id": manifest.campaign_id,
        "manifest_hash": manifest.manifest_hash(),
        "base_gate_failures": base_failures,
        "below_noise_floor_directions": below_noise,
        "n_failures": len(failures),
        "failures": failures,
        "checks": checks,
        "passed": passed,
    }


__all__ = [
    "FD_QUALIFICATION_PROFILE_V1",
    "FdCampaignManifest",
    "FdDirection",
    "FdPreregistrationError",
    "FD_V2_REQUIRED_BASE_GATES",
    "FD_V2_REQUIRED_PERTURBATION_GATES",
    "FdCampaignManifestV2",
    "FdDirectionV2",
    "build_fd_campaign_manifest",
    "build_fd_campaign_manifest_v2",
    "evaluate_fd_campaign_rows",
    "evaluate_fd_campaign_v2",
    "read_fd_campaign_manifest",
    "validate_fd_campaign_manifest",
    "validate_fd_campaign_manifest_v2",
    "write_fd_campaign_manifest",
]
