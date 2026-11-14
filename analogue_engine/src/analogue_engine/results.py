"""Output records. Every record serialises to plain JSON (no NaN, no inf)."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any

# Candidate categories
COMPLETE = "complete"  # rankable: all blocking components compared, constraints satisfied
PARTIAL = "partial"  # insufficient information (missing / pending), no failure
INCOMPATIBLE = "incompatible"  # some blocking component must not be compared
REQUIREMENT_NOT_MET = "requirement_not_met"  # an explicit constraint failed


@dataclass(frozen=True)
class ComponentResult:
    feature_id: str
    dimension: str
    status: str  # compared | missing | comparability_pending | incompatible
    reason_code: str | None
    message: str | None
    unit: str
    comparator_id: str
    target_value: Any  # number, bool, category, list (set) or object (composition)
    candidate_value: Any  # null when not compared
    delta: float | None  # candidate - target (signed; scalar kinds only)
    abs_difference: float | None  # scalar kinds only
    normalized_discrepancy: float | None  # d_j = 1 - s_j
    similarity: float | None  # s_j; null when not compared, never 0 by default
    detail: dict  # comparator explanation (e.g. shared minerals, log ratio)
    tau: float | None  # null for comparators without a scale
    raw_weight: float  # a_j as given in the profile
    effective_weight: float  # w_j (original, kept even when not compared)
    contribution: float | None  # w_j*m_j*s_j / C  (sums to score_observed)
    blocking: bool  # True if a non-compared status prevents ranking
    required: bool


@dataclass(frozen=True)
class ConstraintResult:
    id: str
    feature_id: str
    type: str
    limit: Any  # number for numeric types, required value for 'equals'
    status: str  # satisfied | violated | unevaluable
    observed: Any  # |delta| or candidate value, depending on type
    message: str


@dataclass(frozen=True)
class DimensionResult:
    """Similarity within one dimension (e.g. 'mineralogy', 'thermal').

    Answers the challenge question "an excellent geological analog but a poor
    temperature analog": score_observed is the weighted mean of the compared
    components of this dimension, using the internal weights a_j.
    For a complete candidate, overall score = sum_g dimension_weight * score.
    """

    dimension: str
    dimension_weight: float  # normalised W_g used in the overall score
    score_observed: float | None  # null if nothing comparable in this dimension
    coverage: float | None  # share of the dimension's internal weight compared; null if it has none
    features: tuple[str, ...]
    compared_features: tuple[str, ...]


@dataclass(frozen=True)
class ComparisonResult:
    target_id: str
    candidate_id: str
    profile_id: str
    profile_version: str
    model_id: str
    model_version: str
    data_mode: str
    calibration_status: str
    category: str
    rankable: bool
    score_observed: float | None  # S_obs; null when coverage is 0
    coverage: float  # C, weighted share of compared components in [0, 1]
    components: tuple[ComponentResult, ...]
    dimensions: tuple[DimensionResult, ...]
    constraints: tuple[ConstraintResult, ...]
    reasons: tuple[str, ...]
    limitations: tuple[str, ...]
    declared_limitations: tuple[str, ...]  # from the profile: what Earth cannot reproduce

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self, **kwargs: Any) -> str:
        return to_json(self.to_dict(), **kwargs)


@dataclass(frozen=True)
class RankedEntry:
    position: int  # 1-based, after tie-breaking by candidate id
    tied_with: tuple[str, ...]  # other candidates with the same score (tie broken by id only)
    result: ComparisonResult


@dataclass(frozen=True)
class RankingResult:
    target_id: str
    profile_id: str
    profile_version: str
    model_id: str
    model_version: str
    data_mode: str
    calibration_status: str
    active_features: tuple[str, ...]
    effective_weights: dict[str, float]
    dimension_weights: dict[str, float]
    ranked: tuple[RankedEntry, ...]
    partial: tuple[ComparisonResult, ...]  # sorted by candidate id (no order implied)
    excluded: tuple[ComparisonResult, ...]  # incompatible / requirement_not_met, by id
    warnings: tuple[str, ...]
    declared_limitations: tuple[str, ...]
    ordering: str = field(
        default="score_observed descending (rounded to 12 decimals), then candidate_id ascending"
    )

    def order(self) -> list[str]:
        return [e.result.candidate_id for e in self.ranked]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self, **kwargs: Any) -> str:
        return to_json(self.to_dict(), **kwargs)


def to_json(data: Any, **kwargs: Any) -> str:
    """Strict JSON: raises ValueError instead of writing NaN/Infinity."""
    kwargs.setdefault("indent", 2)
    kwargs.setdefault("ensure_ascii", False)
    return json.dumps(data, allow_nan=False, **kwargs)
