"""Per-feature comparators.

A comparator turns a (target, candidate) pair of *comparable* values into a
similarity s in [0, 1] (1 = identical in this feature). Every comparator is
registered with:

* ``kind``  - the value type it accepts (scalar, boolean, categorical, set,
  composition);
* ``tau``   - whether it needs a scale and in which unit: ``"canonical"``
  (the feature's canonical unit), ``"decade"`` (log10 units) or ``None``.

The aggregation code never looks inside a comparator, so new comparators can
be added without touching weights, coverage or ranking (Gower's idea of a
general coefficient built from per-character scores).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping

from .errors import InvalidRequestError

TAU_CANONICAL = "canonical"
TAU_DECADE = "decade"


@dataclass(frozen=True)
class ComponentComparison:
    similarity: float  # s_j in [0, 1]
    normalized_discrepancy: float  # d_j = 1 - s_j
    delta: float | None = None  # candidate - target (scalar kinds only)
    abs_difference: float | None = None  # |delta| (scalar kinds only)
    detail: Mapping[str, Any] = field(default_factory=dict)  # explanation for humans


# Backwards-compatible name used in v0.1 docs.
ScalarComparison = ComponentComparison


def _fail(message: str, code: str = "comparison_undefined") -> InvalidRequestError:
    return InvalidRequestError(message, code=code)


def _scalar_delta(target: float, candidate: float) -> tuple[float, float]:
    delta = candidate - target
    if not math.isfinite(delta):
        raise _fail("difference between values overflowed to a non-finite number", "non_finite_number")
    return delta, abs(delta)


# --------------------------------------------------------------------------- scalar


def clipped_linear(target: float, candidate: float, tau: float, definition: Any = None) -> ComponentComparison:
    """Absolute difference scaled by a fixed tau and clipped (adapted Gower).

    d = min(1, |x - t| / tau),  s = 1 - d.

    Also covers "normalised absolute difference", "density difference" and
    min-max scaling with *fixed* bounds (tau = max - min; the min cancels:
    (x-min)/(max-min) - (t-min)/(max-min) = (x-t)/(max-min)).
    """
    if not (isinstance(tau, (int, float)) and tau > 0):
        raise _fail(f"tau must be > 0 (got {tau!r})", "non_positive_tau")
    delta, abs_difference = _scalar_delta(target, candidate)
    d = min(1.0, abs_difference / tau)
    return ComponentComparison(1.0 - d, d, delta, abs_difference)


def log_ratio(target: float, candidate: float, tau: float, definition: Any = None) -> ComponentComparison:
    """Logarithmic difference for quantities spanning orders of magnitude.

    d = min(1, |log10(x / t)| / tau),  s = 1 - d,  tau in decades.
    Example: tau = 2 decades, x = 10 t  ->  d = 0.5.
    Both values must be strictly positive.
    """
    if not (isinstance(tau, (int, float)) and tau > 0):
        raise _fail(f"tau must be > 0 (got {tau!r})", "non_positive_tau")
    if target <= 0 or candidate <= 0:
        raise _fail(
            f"log comparison needs strictly positive values (target={target}, candidate={candidate})",
            "non_positive_value",
        )
    delta, abs_difference = _scalar_delta(target, candidate)
    decades = abs(math.log10(candidate) - math.log10(target))
    d = min(1.0, decades / tau)
    return ComponentComparison(1.0 - d, d, delta, abs_difference, {"abs_log10_ratio": decades})


# --------------------------------------------------------------------------- qualitative


def categorical_match(target: str, candidate: str, tau: Any = None, definition: Any = None) -> ComponentComparison:
    """Gower (1971) §2.2(b): s = 1 if the categories agree, 0 otherwise."""
    s = 1.0 if target == candidate else 0.0
    return ComponentComparison(s, 1.0 - s)


def boolean_match(target: bool, candidate: bool, tau: Any = None, definition: Any = None) -> ComponentComparison:
    """Simple matching of two-level variables ('alternatives' in Gower §2.1):
    true/true and false/false both count as agreement.

    If joint absence should *not* count as a match (Gower's 'dichotomous'
    treatment), model the variable as a set and use ``jaccard_v1``.
    """
    s = 1.0 if target == candidate else 0.0
    return ComponentComparison(s, 1.0 - s)


def jaccard(target: tuple, candidate: tuple, tau: Any = None, definition: Any = None) -> ComponentComparison:
    """Jaccard index on presence sets: |A ∩ B| / |A ∪ B|.

    Joint absences are ignored (Gower 1971 §2.3, coefficient S_J = a/(a+b+c)).
    Convention: two empty sets -> s = 1 (nothing present in either); flagged
    in ``detail`` because it is a convention, not a measurement.
    """
    a, b = set(target), set(candidate)
    union = a | b
    if not union:
        return ComponentComparison(1.0, 0.0, detail={"shared": 0, "union": 0, "convention": "both_empty_is_1"})
    shared = a & b
    s = len(shared) / len(union)
    return ComponentComparison(
        s, 1.0 - s, detail={"shared": sorted(shared), "only_target": sorted(a - b), "only_candidate": sorted(b - a)}
    )


def cosine(target: Mapping[str, float], candidate: Mapping[str, float], tau: Any = None, definition: Any = None) -> ComponentComparison:
    """Cosine similarity of two non-negative composition vectors (same keys).

    s = (a · b) / (|a| |b|), in [0, 1] for non-negative vectors. It compares
    *proportions*, not amounts: (0.2, 0.1) and (0.4, 0.2) give s = 1.
    Undefined if either vector is all zeros (reported as a failed comparison).
    """
    keys = sorted(target)
    a = [target[k] for k in keys]
    b = [candidate[k] for k in keys]
    max_a, max_b = max(a, default=0.0), max(b, default=0.0)
    if max_a <= 0 or max_b <= 0:
        raise _fail("cosine similarity is undefined for an all-zero composition vector")
    # Cosine is scale invariant: rescale each vector to max 1 so squares can
    # neither overflow (huge amounts) nor underflow to 0 (tiny amounts).
    a = [x / max_a for x in a]
    b = [x / max_b for x in b]
    na = math.sqrt(math.fsum(x * x for x in a))
    nb = math.sqrt(math.fsum(x * x for x in b))
    s = math.fsum(x * y for x, y in zip(a, b)) / (na * nb)
    if not math.isfinite(s):
        raise _fail("cosine similarity produced a non-finite value", "non_finite_number")
    s = min(1.0, max(0.0, s))  # rounding noise only: non-negative inputs give [0, 1]
    return ComponentComparison(s, 1.0 - s, detail={"cosine_distance": 1.0 - s})


# --------------------------------------------------------------------------- registry


@dataclass(frozen=True)
class ComparatorSpec:
    id: str
    kind: str
    tau: str | None
    fn: Callable[..., ComponentComparison]
    description: str


COMPARATORS: dict[str, ComparatorSpec] = {
    spec.id: spec
    for spec in (
        ComparatorSpec("clipped_linear_v1", "scalar", TAU_CANONICAL, clipped_linear,
                       "1 - min(1, |x-t|/tau); also fixed-bound min-max (tau = max - min)"),
        ComparatorSpec("log_ratio_v1", "scalar", TAU_DECADE, log_ratio,
                       "1 - min(1, |log10(x/t)|/tau), tau in decades; positive values only"),
        ComparatorSpec("categorical_match_v1", "categorical", None, categorical_match,
                       "1 if same category else 0 (Gower §2.2b)"),
        ComparatorSpec("boolean_match_v1", "boolean", None, boolean_match,
                       "1 if equal (true/true or false/false) else 0"),
        ComparatorSpec("jaccard_v1", "set", None, jaccard,
                       "|A∩B|/|A∪B| on presence sets; joint absences ignored"),
        ComparatorSpec("cosine_v1", "composition", None, cosine,
                       "cosine similarity of non-negative proportion vectors"),
    )
}


def get_comparator_spec(comparator_id: str) -> ComparatorSpec:
    try:
        return COMPARATORS[comparator_id]
    except KeyError:
        raise InvalidRequestError(
            f"unknown comparator_id '{comparator_id}'; available: {sorted(COMPARATORS)}",
            code="unknown_comparator",
            comparator_id=comparator_id,
        ) from None


def get_comparator(comparator_id: str) -> Callable[..., ComponentComparison]:
    return get_comparator_spec(comparator_id).fn
