"""Independent Stage V verification of required candidate pairs (DF5).

DF5 compares baseline, Stage T and Stage S candidates on independent body-fitted
discretisations. This module owns the verdict algebra and its fail-closed rules:

- every candidate must carry its per-response numerical and extraction
  uncertainty; the combined uncertainty is the root-sum-square and the rule id
  is recorded;
- every candidate must report its qualification gates (mesh, residual,
  stationarity); a candidate that misses any gate never enters a ranking
  conclusion, and it is never silently dropped from the pair table;
- the Stage V reference measurements must declare
  ``used_in_optimization: false``; a reference that was used as an
  optimisation tuning signal invalidates the verdict;
- a required pair verdict is ``improved`` only when the sign-corrected
  improvement exceeds the combined uncertainty, ``unresolved`` when it does
  not, and ``regressed`` when the wrong direction exceeds the uncertainty.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Any

COMBINED_UNCERTAINTY_RULE = "root_sum_square(numerical, extraction)"
GATE_NAMES = ("mesh", "residual", "stationarity")
IMPROVEMENT_DIRECTIONS = ("increase", "decrease")


class IndependentVerificationError(ValueError):
    """Fail-closed verification contract violation."""


@dataclass(frozen=True)
class CandidateMeasurement:
    candidate_id: str
    role: str  # baseline | stage_t | stage_s
    responses: dict[str, float]
    improvement_direction: dict[str, str]
    numerical_uncertainty: dict[str, float]
    extraction_uncertainty: dict[str, float]
    gates: dict[str, bool]
    grid_levels: tuple[str, ...] = ()
    used_in_optimization: bool = False
    extraction_status: str = "measured"

    def validate_extraction_status(self) -> None:
        if self.extraction_status not in {"measured", "not_measured"}:
            raise IndependentVerificationError(
                f"candidate {self.candidate_id!r} has unknown extraction_status "
                f"{self.extraction_status!r}"
            )

    def combined_uncertainty(self, response: str) -> float:
        numerical = float(self.numerical_uncertainty.get(response, 0.0))
        extraction = float(self.extraction_uncertainty.get(response, 0.0))
        if numerical < 0.0 or extraction < 0.0:
            raise IndependentVerificationError("uncertainties must be non-negative")
        return math.sqrt(numerical**2 + extraction**2)

    def missing_gates(self) -> list[str]:
        return [name for name in GATE_NAMES if not bool(self.gates.get(name, False))]

    def validate(self) -> None:
        if not self.candidate_id:
            raise IndependentVerificationError("candidate_id is required")
        if not self.responses:
            raise IndependentVerificationError("at least one response is required")
        for response in self.responses:
            if response not in self.improvement_direction:
                raise IndependentVerificationError(
                    f"response {response!r} must declare its improvement direction"
                )
            if self.improvement_direction[response] not in IMPROVEMENT_DIRECTIONS:
                raise IndependentVerificationError(
                    f"response {response!r} has unknown improvement direction "
                    f"{self.improvement_direction[response]!r}"
                )
            self.combined_uncertainty(response)


@dataclass(frozen=True)
class RequiredPair:
    from_role: str
    to_role: str
    label: str


@dataclass(frozen=True)
class PairVerdict:
    pair: str
    from_candidate: str
    to_candidate: str
    response: str
    improvement: float
    combined_uncertainty: float
    verdict: str
    gate_failures: dict[str, list[str]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def verify_required_pairs(
    measurements: list[CandidateMeasurement],
    required_pairs: list[RequiredPair],
    *,
    responses: list[str] | None = None,
) -> dict[str, Any]:
    """Verdict every required pair against candidate-specific combined uncertainty."""

    if not measurements:
        raise IndependentVerificationError("measurements must not be empty")
    if not required_pairs:
        raise IndependentVerificationError("at least one required pair is required")
    by_role: dict[str, CandidateMeasurement] = {}
    for measurement in measurements:
        measurement.validate()
        measurement.validate_extraction_status()
        if measurement.role in by_role:
            raise IndependentVerificationError(f"duplicate candidate role {measurement.role!r}")
        by_role[measurement.role] = measurement

    reference_failures = [
        measurement.candidate_id
        for measurement in measurements
        if measurement.role in {"baseline", "stage_s", "stage_v"}
        and measurement.used_in_optimization
    ]
    if reference_failures:
        raise IndependentVerificationError(
            "reference measurements were used as optimisation tuning signal: "
            + ", ".join(reference_failures)
        )

    verdicts: list[PairVerdict] = []
    for pair in required_pairs:
        source = by_role.get(pair.from_role)
        target = by_role.get(pair.to_role)
        if source is None or target is None:
            missing = [
                role
                for role, item in ((pair.from_role, source), (pair.to_role, target))
                if item is None
            ]
            raise IndependentVerificationError(
                f"required pair {pair.label!r} references missing roles {missing}"
            )
        gate_failures = {
            source.candidate_id: source.missing_gates(),
            target.candidate_id: target.missing_gates(),
        }
        gate_failures = {key: value for key, value in gate_failures.items() if value}
        pair_responses = responses or sorted(source.responses)
        for response in pair_responses:
            if response not in source.responses or response not in target.responses:
                raise IndependentVerificationError(
                    f"pair {pair.label!r} requires response {response!r} on both candidates"
                )
            if gate_failures:
                verdicts.append(
                    PairVerdict(
                        pair=pair.label,
                        from_candidate=source.candidate_id,
                        to_candidate=target.candidate_id,
                        response=response,
                        improvement=float(target.responses[response] - source.responses[response]),
                        combined_uncertainty=max(
                            source.combined_uncertainty(response),
                            target.combined_uncertainty(response),
                        ),
                        verdict="gate_failed",
                        gate_failures=gate_failures,
                    )
                )
                continue
            if "not_measured" in {
                source.extraction_status,
                target.extraction_status,
            }:
                verdicts.append(
                    PairVerdict(
                        pair=pair.label,
                        from_candidate=source.candidate_id,
                        to_candidate=target.candidate_id,
                        response=response,
                        improvement=float(target.responses[response] - source.responses[response]),
                        combined_uncertainty=math.nan,
                        verdict="unresolved_extraction_not_measured",
                    )
                )
                continue
            direction = source.improvement_direction[response]
            raw = float(target.responses[response] - source.responses[response])
            improvement = raw if direction == "increase" else -raw
            combined = max(
                source.combined_uncertainty(response),
                target.combined_uncertainty(response),
            )
            if abs(improvement) <= combined:
                verdict = "unresolved"
            elif improvement > 0.0:
                verdict = "improved"
            else:
                verdict = "regressed"
            verdicts.append(
                PairVerdict(
                    pair=pair.label,
                    from_candidate=source.candidate_id,
                    to_candidate=target.candidate_id,
                    response=response,
                    improvement=improvement,
                    combined_uncertainty=combined,
                    verdict=verdict,
                )
            )

    unresolved = [item for item in verdicts if item.verdict != "improved"]
    return {
        "kind": "independent_required_pair_verification",
        "schema_version": 1,
        "combined_uncertainty_rule": COMBINED_UNCERTAINTY_RULE,
        "gates_required": list(GATE_NAMES),
        "pairs": [item.to_dict() for item in verdicts],
        "passed": not unresolved,
        "unresolved_or_failed": [
            {
                "pair": item.pair,
                "response": item.response,
                "verdict": item.verdict,
            }
            for item in unresolved
        ],
        "claims_not_made": [
            "no claim outside the measured candidate set and grids",
            "a gate failure suppresses the conclusion; it never removes the candidate row",
        ],
    }


__all__ = [
    "COMBINED_UNCERTAINTY_RULE",
    "GATE_NAMES",
    "CandidateMeasurement",
    "IndependentVerificationError",
    "PairVerdict",
    "RequiredPair",
    "verify_required_pairs",
]
