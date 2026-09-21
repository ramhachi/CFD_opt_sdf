"""Cross-fidelity ranking qualification for the Gate 4 stop/go decision.

Compares the ranking of the same candidate set evaluated by two independent
fidelities (e.g. a coarse surrogate against body-fitted reference values)
with pre-declared per-response uncertainty bands.

Contract sources:

- ``docs/problem_resolution_plan_2026_09.md`` section 7 "Gate 4 —
  cross-fidelity ranking"
- pre-declared response bands echoed from
  ``docs/evidence/stage_v_fixed_domain_grid_study_2026_09.json``

Pair improvement follows the Gate 4 definition
``I = (J_b - J_c) / max(|J_b|, J_scale)`` and a pair is resolvable when
``|I| > 2 * max(S_b, S_c, S_extraction)`` (the Gate 4 rule is applied to the
improvement magnitude; the raw signed improvement is reported separately so
 adversaries only disagree on sign conventions, never on the band).

Verdict rules, evaluated per response:

- ``no_go``: any pair whose surrogate and reference improvements are both
  resolvable against uncertainty but carry opposite signs.
- ``pass``: reference and surrogate orders are identical AND at least one
  adjacent pair in the reference ranking is resolvable AND no required pair
  failed.
- ``unresolved``: anything else, including identical orders whose adjacent
  differences all sit below the noise band.

The module is deterministic and fail-closed: non-finite scores, candidate
set mismatches, unknown response ids, and non-positive ``J_scale`` are all
refused up front.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from math import isfinite
from typing import Any

try:
    from scipy import stats as _scipy_stats
except ImportError:  # pragma: no cover - scipy is a declared repo dependency
    _scipy_stats = None

MIN_CANDIDATES = 8
_VERDICT_PASS = "pass"
_VERDICT_UNRESOLVED = "unresolved"
_VERDICT_NO_GO = "no_go"

_RESPONSE_UNCERTAINTY_FIELDS: dict[str, str] = {
    "downforce": "downforce_abs",
    "downforce_coefficient": "downforce_abs",
    "drag": "drag_coefficient_rel",
    "drag_coefficient": "drag_coefficient_rel",
}


@dataclass(frozen=True)
class FidelityScores:
    fidelity_id: str
    values: Mapping[str, float]
    info: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.fidelity_id, str) or not self.fidelity_id:
            raise ValueError("fidelity_id must be a non-empty string")
        if not isinstance(self.values, Mapping):
            raise ValueError("values must be a mapping of candidate id to float")
        if not self.values:
            raise ValueError("values must contain at least one candidate")
        for candidate_id, value in self.values.items():
            if not isinstance(candidate_id, str):
                raise ValueError("candidate ids must be strings")
            _require_finite_score(candidate_id, value)
        if not isinstance(self.info, Mapping):
            raise ValueError("info must be a mapping")

    def to_dict(self) -> dict[str, Any]:
        return {
            "fidelity_id": self.fidelity_id,
            "values": dict(sorted(self.values.items())),
            "info": dict(sorted(self.info.items())),
        }


@dataclass(frozen=True)
class Uncertainty:
    downforce_abs: float
    drag_coefficient_rel: float

    def __post_init__(self) -> None:
        _require_finite_band("downforce_abs", self.downforce_abs)
        _require_finite_band("drag_coefficient_rel", self.drag_coefficient_rel)

    def to_dict(self) -> dict[str, float]:
        return {
            "downforce_abs": self.downforce_abs,
            "drag_coefficient_rel": self.drag_coefficient_rel,
        }


@dataclass(frozen=True)
class RankingPair:
    candidate_a: str
    candidate_b: str
    surrogate_improvement: float
    reference_improvement: float
    surrogate_sign: int
    reference_sign: int
    resolvable: bool
    verdict: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_a": self.candidate_a,
            "candidate_b": self.candidate_b,
            "surrogate_improvement": self.surrogate_improvement,
            "reference_improvement": self.reference_improvement,
            "surrogate_sign": self.surrogate_sign,
            "reference_sign": self.reference_sign,
            "resolvable": self.resolvable,
            "verdict": self.verdict,
        }


@dataclass(frozen=True)
class RankingReport:
    response_id: str
    verdict: str
    candidate_ids: tuple[str, ...]
    surrogate_fidelity_id: str
    reference_fidelity_id: str
    surrogate_order: tuple[str, ...]
    reference_order: tuple[str, ...]
    spearman_rho: float
    spearman_pvalue: float
    kendall_tau: float
    kendall_pvalue: float
    n_pairs: int
    n_signed_pairs: int
    n_sign_inversions: int
    pairs: tuple[RankingPair, ...]
    failed_required_pairs: tuple[tuple[str, str], ...]
    uncertainty: Uncertainty
    response_uncertainty: float
    j_scale: float
    extraction_sensitivity: Mapping[str, float]
    candidate_uncertainty: Mapping[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "response_id": self.response_id,
            "verdict": self.verdict,
            "candidate_ids": list(self.candidate_ids),
            "surrogate_fidelity_id": self.surrogate_fidelity_id,
            "reference_fidelity_id": self.reference_fidelity_id,
            "surrogate_order": list(self.surrogate_order),
            "reference_order": list(self.reference_order),
            "spearman": {"rho": self.spearman_rho, "pvalue": self.spearman_pvalue},
            "kendall": {"tau": self.kendall_tau, "pvalue": self.kendall_pvalue},
            "n_pairs": self.n_pairs,
            "n_signed_pairs": self.n_signed_pairs,
            "n_sign_inversions": self.n_sign_inversions,
            "pairs": [pair.to_dict() for pair in self.pairs],
            "failed_required_pairs": [list(pair) for pair in self.failed_required_pairs],
            "uncertainty": self.uncertainty.to_dict(),
            "response_uncertainty": self.response_uncertainty,
            "j_scale": self.j_scale,
            "extraction_sensitivity": dict(sorted(self.extraction_sensitivity.items())),
            "candidate_uncertainty": dict(sorted(self.candidate_uncertainty.items())),
        }


@dataclass(frozen=True)
class RankingQualification:
    surrogate: FidelityScores
    reference: FidelityScores
    uncertainty: Uncertainty

    def __post_init__(self) -> None:
        if set(self.surrogate.values) != set(self.reference.values):
            raise ValueError(
                "candidate sets differ between fidelities: "
                f"only in surrogate={sorted(set(self.surrogate.values) - set(self.reference.values))!r}, "
                f"only in reference={sorted(set(self.reference.values) - set(self.surrogate.values))!r}"
            )

    @classmethod
    def assess(
        cls,
        fidelity_a: FidelityScores,
        fidelity_b: FidelityScores,
        uncertainty: Uncertainty,
    ) -> "RankingQualification":
        return cls(surrogate=fidelity_a, reference=fidelity_b, uncertainty=uncertainty)

    def to_dict(self) -> dict[str, Any]:
        return {
            "surrogate": self.surrogate.to_dict(),
            "reference": self.reference.to_dict(),
            "uncertainty": self.uncertainty.to_dict(),
        }


def _require_finite_score(candidate_id: str, value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(
            f"score for candidate {candidate_id!r} must be a real number, got {value!r}"
        )
    if not isfinite(float(value)):
        raise ValueError(
            f"score for candidate {candidate_id!r} must be finite, got {value!r}"
        )
    return float(value)


def _require_finite_band(name: str, value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"uncertainty {name} must be a real number, got {value!r}")
    if not isfinite(float(value)):
        raise ValueError(f"uncertainty {name} must be finite, got {value!r}")
    if float(value) < 0.0:
        raise ValueError(f"uncertainty {name} must be non-negative, got {value!r}")
    return float(value)


def rank_values(values: Mapping[str, float]) -> list[str]:
    if not isinstance(values, Mapping):
        raise ValueError("values must be a mapping of candidate id to float")
    if not values:
        raise ValueError("values must contain at least one candidate")
    cleaned: dict[str, float] = {}
    for candidate_id, value in values.items():
        if not isinstance(candidate_id, str):
            raise ValueError("candidate ids must be strings")
        cleaned[candidate_id] = _require_finite_score(candidate_id, value)
    return [candidate_id for candidate_id, _ in sorted(cleaned.items(), key=lambda item: (item[1], item[0]))]


def pair_sign(value_b: float, value_c: float, j_scale: float = 1.0) -> float:
    _require_finite_score("b", value_b)
    _require_finite_score("c", value_c)
    _require_positive_j_scale(j_scale)
    return (float(value_b) - float(value_c)) / max(abs(float(value_b)), float(j_scale))


def pair_is_resolvable(
    improvement: float,
    uncertainty_b: float,
    uncertainty_c: float,
    extraction_b: float | None = None,
    extraction_c: float | None = None,
) -> bool:
    _require_finite_band("improvement band input S_b", uncertainty_b)
    _require_finite_band("improvement band input S_c", uncertainty_c)
    extraction_b = 0.0 if extraction_b is None else _require_finite_band("extraction_b", extraction_b)
    extraction_c = 0.0 if extraction_c is None else _require_finite_band("extraction_c", extraction_c)
    if isinstance(improvement, bool) or not isinstance(improvement, (int, float)) or not isfinite(float(improvement)):
        raise ValueError(f"improvement must be a finite real number, got {improvement!r}")
    threshold = 2.0 * max(uncertainty_b, uncertainty_c, extraction_b, extraction_c)
    return abs(float(improvement)) > threshold


def spearman_tau(values_a: Sequence[float], values_b: Sequence[float]) -> tuple[float, float]:
    _require_ranking_inputs(values_a, values_b)
    if _scipy_stats is None:
        raise RuntimeError(
            "scipy.stats is required for Spearman rank correlation but is not "
            "installed in the active environment"
        )
    result = _scipy_stats.spearmanr(list(values_a), list(values_b))
    return float(result[0]), float(result[1])


def kendall_tau(values_a: Sequence[float], values_b: Sequence[float]) -> tuple[float, float]:
    _require_ranking_inputs(values_a, values_b)
    if _scipy_stats is None:
        raise RuntimeError(
            "scipy.stats is required for Kendall rank correlation but is not "
            "installed in the active environment"
        )
    result = _scipy_stats.kendalltau(list(values_a), list(values_b))
    return float(result[0]), float(result[1])


def _require_ranking_inputs(values_a: Sequence[float], values_b: Sequence[float]) -> None:
    if len(values_a) != len(values_b) or len(values_a) < 2:
        raise ValueError(
            "rank correlation requires two equal-length sequences of at least 2 values"
        )
    for label, sequence in (("values_a", values_a), ("values_b", values_b)):
        for value in sequence:
            _require_finite_score(label, value)


def _require_positive_j_scale(j_scale: float) -> None:
    if isinstance(j_scale, bool) or not isinstance(j_scale, (int, float)) or not isfinite(float(j_scale)):
        raise ValueError(f"j_scale must be a positive finite number, got {j_scale!r}")
    if float(j_scale) <= 0.0:
        raise ValueError(f"j_scale must be a positive finite number, got {j_scale!r}")


def qualify_cross_fidelity_ranking(
    surrogate: FidelityScores,
    reference: FidelityScores,
    *,
    uncertainty: Uncertainty,
    response_id: str,
    j_scale: float = 1.0,
    extraction_sensitivity: Mapping[str, float] | None = None,
    required_pairs: Sequence[tuple[str, str]] = (),
    require_benchmark_coverage: bool = False,
    candidate_uncertainty: Mapping[str, float] | None = None,
) -> RankingReport:
    surrogate_values = dict(surrogate.values)
    reference_values = dict(reference.values)
    _require_positive_j_scale(j_scale)
    if not isinstance(response_id, str) or not response_id:
        raise ValueError("response_id must be a non-empty string")
    if set(surrogate_values) != set(reference_values):
        raise ValueError(
            "candidate sets differ between fidelities: "
            f"only in surrogate={sorted(set(surrogate_values) - set(reference_values))!r}, "
            f"only in reference={sorted(set(reference_values) - set(surrogate_values))!r}"
        )
    candidates = sorted(surrogate_values)
    if len(candidates) < 2:
        raise ValueError("cross-fidelity ranking requires at least 2 candidates")
    if require_benchmark_coverage and len(candidates) < MIN_CANDIDATES:
        raise ValueError(
            f"require_benchmark_coverage needs at least {MIN_CANDIDATES} candidates, "
            f"got {len(candidates)}"
        )
    response_uncertainty = _response_uncertainty(uncertainty, response_id)
    extraction = _validated_extraction(extraction_sensitivity, candidates)
    per_candidate = _validated_candidate_uncertainty(
        candidate_uncertainty, candidates, response_uncertainty
    )

    surrogate_order = tuple(rank_values(surrogate_values))
    reference_order = tuple(rank_values(reference_values))

    pairs: list[RankingPair] = []
    n_signed_pairs = 0
    n_sign_inversions = 0
    reference_resolvable_by_pair: dict[tuple[str, str], bool] = {}
    for index, candidate_a in enumerate(candidates):
        for candidate_b in candidates[index + 1 :]:
            extraction_a = extraction.get(candidate_a, 0.0)
            extraction_b = extraction.get(candidate_b, 0.0)
            surrogate_improvement = pair_sign(
                surrogate_values[candidate_a], surrogate_values[candidate_b], j_scale
            )
            reference_improvement = pair_sign(
                reference_values[candidate_a], reference_values[candidate_b], j_scale
            )
            surrogate_sign = _sign(surrogate_improvement)
            reference_sign = _sign(reference_improvement)
            band_a = per_candidate[candidate_a]
            band_b = per_candidate[candidate_b]
            surrogate_resolvable = pair_is_resolvable(
                surrogate_improvement,
                band_a,
                band_b,
                extraction_a,
                extraction_b,
            )
            reference_resolvable = pair_is_resolvable(
                reference_improvement,
                band_a,
                band_b,
                extraction_a,
                extraction_b,
            )
            key = (candidate_a, candidate_b)
            reference_resolvable_by_pair[key] = reference_resolvable
            resolvable = surrogate_resolvable and reference_resolvable
            if resolvable:
                n_signed_pairs += 1
                if surrogate_sign == reference_sign:
                    pair_verdict = "agree"
                else:
                    pair_verdict = "inverted"
                    n_sign_inversions += 1
            else:
                pair_verdict = "unresolved"
            pairs.append(
                RankingPair(
                    candidate_a=candidate_a,
                    candidate_b=candidate_b,
                    surrogate_improvement=surrogate_improvement,
                    reference_improvement=reference_improvement,
                    surrogate_sign=surrogate_sign,
                    reference_sign=reference_sign,
                    resolvable=resolvable,
                    verdict=pair_verdict,
                )
            )

    failed_required_pairs = _evaluate_required_pairs(
        required_pairs, candidates, reference_resolvable_by_pair, pairs
    )

    orders_identical = surrogate_order == reference_order
    adjacent_resolvable = any(
        pair_is_resolvable(
            pair_sign(reference_values[reference_order[index]], reference_values[reference_order[index + 1]], j_scale),
            per_candidate[reference_order[index]],
            per_candidate[reference_order[index + 1]],
            extraction.get(reference_order[index], 0.0),
            extraction.get(reference_order[index + 1], 0.0),
        )
        for index in range(len(reference_order) - 1)
    )
    if n_sign_inversions > 0:
        verdict = _VERDICT_NO_GO
    elif orders_identical and adjacent_resolvable and not failed_required_pairs:
        verdict = _VERDICT_PASS
    else:
        verdict = _VERDICT_UNRESOLVED

    surrogate_vector = [surrogate_values[candidate] for candidate in candidates]
    reference_vector = [reference_values[candidate] for candidate in candidates]
    spearman_rho, spearman_pvalue = spearman_tau(surrogate_vector, reference_vector)
    kendall_tau_value, kendall_pvalue = kendall_tau(surrogate_vector, reference_vector)

    return RankingReport(
        response_id=response_id,
        verdict=verdict,
        candidate_ids=tuple(candidates),
        surrogate_fidelity_id=surrogate.fidelity_id,
        reference_fidelity_id=reference.fidelity_id,
        surrogate_order=surrogate_order,
        reference_order=reference_order,
        spearman_rho=spearman_rho,
        spearman_pvalue=spearman_pvalue,
        kendall_tau=kendall_tau_value,
        kendall_pvalue=kendall_pvalue,
        n_pairs=len(pairs),
        n_signed_pairs=n_signed_pairs,
        n_sign_inversions=n_sign_inversions,
        pairs=tuple(pairs),
        failed_required_pairs=tuple(failed_required_pairs),
        uncertainty=uncertainty,
        response_uncertainty=response_uncertainty,
        j_scale=float(j_scale),
        extraction_sensitivity=dict(extraction),
        candidate_uncertainty=dict(per_candidate),
    )


def _response_uncertainty(uncertainty: Uncertainty, response_id: str) -> float:
    field_name = _RESPONSE_UNCERTAINTY_FIELDS.get(response_id)
    if field_name is None:
        raise ValueError(
            f"response_id {response_id!r} has no declared per-response uncertainty; "
            f"supported response ids: {sorted(_RESPONSE_UNCERTAINTY_FIELDS)!r}"
        )
    return float(getattr(uncertainty, field_name))


def _validated_candidate_uncertainty(
    candidate_uncertainty: Mapping[str, float] | None,
    candidates: Sequence[str],
    default: float,
) -> dict[str, float]:
    """Per-candidate bands, defaulting to the response-level band.

    The Gate-4 rule is applied to the pair as
    ``2 * max(band_a, band_b, extraction_a, extraction_b)``; candidate-specific
    bands therefore never make a pair easier to resolve than the flat band.
    """

    resolved = {candidate: float(default) for candidate in candidates}
    if candidate_uncertainty is None:
        return resolved
    if not isinstance(candidate_uncertainty, Mapping):
        raise ValueError(
            "candidate_uncertainty must be a mapping of candidate id to float"
        )
    for candidate_id, band in candidate_uncertainty.items():
        if candidate_id not in candidates:
            raise ValueError(
                f"candidate_uncertainty references unknown candidate {candidate_id!r}"
            )
        resolved[candidate_id] = _require_finite_band(
            f"candidate_uncertainty[{candidate_id!r}]", band
        )
    return resolved


def _validated_extraction(
    extraction_sensitivity: Mapping[str, float] | None, candidates: Sequence[str]
) -> dict[str, float]:
    if extraction_sensitivity is None:
        return {}
    if not isinstance(extraction_sensitivity, Mapping):
        raise ValueError("extraction_sensitivity must be a mapping of candidate id to float")
    resolved: dict[str, float] = {}
    for candidate_id, share in extraction_sensitivity.items():
        if candidate_id not in candidates:
            raise ValueError(
                f"extraction_sensitivity references unknown candidate {candidate_id!r}"
            )
        resolved[candidate_id] = _require_finite_band(
            f"extraction_sensitivity[{candidate_id!r}]", share
        )
    return resolved


def _evaluate_required_pairs(
    required_pairs: Sequence[tuple[str, str]],
    candidates: Sequence[str],
    reference_resolvable_by_pair: Mapping[tuple[str, str], bool],
    pairs: Sequence[RankingPair],
) -> list[tuple[str, str]]:
    pair_by_key = {(pair.candidate_a, pair.candidate_b): pair for pair in pairs}
    failed: list[tuple[str, str]] = []
    for required in required_pairs:
        if not isinstance(required, tuple) or len(required) != 2:
            raise ValueError(f"required pair must be a (candidate_a, candidate_b) tuple, got {required!r}")
        candidate_a, candidate_b = required
        if not isinstance(candidate_a, str) or not isinstance(candidate_b, str):
            raise ValueError(f"required pair members must be candidate ids, got {required!r}")
        if candidate_a == candidate_b:
            raise ValueError(f"required pair members must be distinct, got {required!r}")
        if candidate_a not in candidates or candidate_b not in candidates:
            raise ValueError(
                f"required pair {required!r} references candidates outside the candidate set"
            )
        key = (candidate_a, candidate_b) if candidate_a < candidate_b else (candidate_b, candidate_a)
        if key not in pair_by_key:
            raise ValueError(
                f"required pair {required!r} does not correspond to a generated pair table entry"
            )
        ordered = pair_by_key[key]
        reference_resolvable = reference_resolvable_by_pair[key]
        sign_matches = ordered.surrogate_sign == ordered.reference_sign
        if not (reference_resolvable and sign_matches):
            failed.append((candidate_a, candidate_b))
    return failed


def _sign(value: float) -> int:
    if value > 0.0:
        return 1
    if value < 0.0:
        return -1
    return 0
