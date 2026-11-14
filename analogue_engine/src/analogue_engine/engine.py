"""Public engine: ``compare`` and ``rank``.

    compare(target, candidate, profile, feature_definitions) -> ComparisonResult
    rank(target, candidates, profile, feature_definitions)   -> RankingResult

Arguments may be model objects or plain dicts (parsed with ``from_dict``).
Nothing here downloads data, calls an LLM, or branches on site/body names.
"""

from __future__ import annotations

import math
from typing import Any, Iterable, Sequence

from .comparability import COMPARED, INCOMPATIBLE as C_INCOMPATIBLE, INSUFFICIENT_STATUSES, check_comparability
from .comparators import get_comparator
from .errors import AnalogueEngineError, DataModeError, InvalidRequestError
from .models import Constraint, Profile, Site, as_profile, as_site, value_matches_kind
from .resolution import ResolvedFeature, ResolvedProfile, resolve_profile
from .results import (
    COMPLETE,
    INCOMPATIBLE,
    PARTIAL,
    REQUIREMENT_NOT_MET,
    ComparisonResult,
    ComponentResult,
    ConstraintResult,
    DimensionResult,
    RankedEntry,
    RankingResult,
)

MODEL_ID = "analogue_engine.adapted_gower"
MODEL_VERSION = "0.2.0"

# Scores are rounded to this many decimals *only* to build the ordering key
# and detect ties, so floating-point noise (~1e-16) cannot decide an order.
SCORE_ORDER_DECIMALS = 12

# A value within this tolerance of a constraint limit counts as on the limit
# (satisfied), so e.g. |0.4 - 0.1| = 0.30000000000000004 satisfies <= 0.3.
CONSTRAINT_REL_TOL = 1e-9
CONSTRAINT_ABS_TOL = 1e-12


def _within(observed: float, limit: float, *, upper: bool) -> bool:
    if math.isclose(observed, limit, rel_tol=CONSTRAINT_REL_TOL, abs_tol=CONSTRAINT_ABS_TOL):
        return True
    return observed <= limit if upper else observed >= limit


# --------------------------------------------------------------------------- helpers


def _check_data_modes(target: Site, candidates: Iterable[Site]) -> None:
    mixed = sorted({c.id for c in candidates if c.data_mode != target.data_mode})
    if mixed:
        raise DataModeError(
            f"target '{target.id}' is '{target.data_mode}' but candidates {mixed} are not; "
            "synthetic and real records cannot be mixed in one search",
            target_data_mode=target.data_mode,
            candidates=mixed,
        )


def _evaluate_constraint(
    constraint: Constraint, component: ComponentResult
) -> ConstraintResult:
    if component.status != COMPARED:
        return ConstraintResult(
            id=constraint.id,
            feature_id=constraint.feature_id,
            type=constraint.type,
            limit=constraint.limit if constraint.type != "equals" else constraint.value,
            status="unevaluable",
            observed=None,
            message=f"cannot evaluate: component '{component.feature_id}' is {component.status}",
        )
    unit = f"[{component.unit}]"
    if constraint.type == "equals":
        observed = component.candidate_value
        ok = observed == constraint.value
        rel = "==" if ok else "!="
        text = f"value = {observed!r} {rel} required {constraint.value!r}"
    elif constraint.type == "max_abs_difference":
        observed = component.abs_difference
        ok = _within(observed, constraint.limit, upper=True)
        rel = "<=" if ok else ">"
        text = f"|delta| = {observed:.12g} {rel} {constraint.limit:.12g} {unit}"
    elif constraint.type == "min_value":
        observed = component.candidate_value
        ok = _within(observed, constraint.limit, upper=False)
        rel = ">=" if ok else "<"
        text = f"value = {observed:.12g} {rel} {constraint.limit:.12g} {unit}"
    else:  # max_value
        observed = component.candidate_value
        ok = _within(observed, constraint.limit, upper=True)
        rel = "<=" if ok else ">"
        text = f"value = {observed:.12g} {rel} {constraint.limit:.12g} {unit}"
    return ConstraintResult(
        id=constraint.id,
        feature_id=constraint.feature_id,
        type=constraint.type,
        limit=constraint.limit if constraint.type != "equals" else constraint.value,
        status="satisfied" if ok else "violated",
        observed=observed,
        message=text,
    )


def _limitations(resolved: ResolvedProfile, category: str) -> tuple[str, ...]:
    items = [
        "similarity_is_not_operational_suitability",
        "measurement_uncertainty_not_propagated",
    ]
    if resolved.target.data_mode == "synthetic":
        items.append("synthetic_data_not_real_measurements")
    if resolved.profile.calibration_status != "science_reviewed":
        items.append(f"parameters_{resolved.profile.calibration_status}")
    if category != COMPLETE:
        items.append("score_observed_uses_reduced_basis_not_comparable_with_complete_scores")
    return tuple(items)


def _check_candidate_values(resolved: ResolvedProfile, candidate: Site) -> None:
    """A value of the wrong shape (e.g. text for a numeric feature) is a
    malformed record, not a scientific incompatibility: reject the request."""
    for rf in resolved.features:
        m = candidate.measurements.get(rf.feature_id)
        if m is None or m.value is None:
            continue
        problem = value_matches_kind(m.value, rf.definition.kind, rf.definition.categories)
        if problem:
            raise InvalidRequestError(
                f"site[{candidate.id}] value for '{rf.feature_id}' does not fit kind "
                f"'{rf.definition.kind}': {problem}",
                code="value_type_mismatch",
                site_id=candidate.id,
                feature_id=rf.feature_id,
            )


def _dimension_results(
    resolved: ResolvedProfile, components: list[ComponentResult]
) -> tuple[DimensionResult, ...]:
    """Per-dimension weighted mean using internal weights a_j.

    Within a dimension with W_g > 0, a_j is proportional to w_j, so this is
    the same weighting as the overall score; it also works for W_g = 0
    (informational dimensions).
    """
    order: list[str] = []
    for rf in resolved.features:
        if rf.dimension not in order:
            order.append(rf.dimension)
    out = []
    for dim in order:
        members = [(rf, c) for rf, c in zip(resolved.features, components) if rf.dimension == dim]
        total = math.fsum(rf.raw_weight for rf, _ in members)
        compared = [(rf, c) for rf, c in members if c.status == COMPARED]
        covered = math.fsum(rf.raw_weight for rf, _ in compared)
        score = (
            math.fsum(rf.raw_weight * c.similarity for rf, c in compared) / covered if covered > 0 else None
        )
        out.append(
            DimensionResult(
                dimension=dim,
                dimension_weight=resolved.dimension_weights[dim],
                score_observed=score,
                coverage=covered / total if total > 0 else None,
                features=tuple(rf.feature_id for rf, _ in members),
                compared_features=tuple(rf.feature_id for rf, _ in compared),
            )
        )
    return tuple(out)


def _compare_resolved(resolved: ResolvedProfile, candidate: Site) -> ComparisonResult:
    _check_candidate_values(resolved, candidate)
    target = resolved.target
    raw: list[tuple[ResolvedFeature, str, str | None, str | None, Any]] = []
    for rf in resolved.features:
        cm = candidate.measurements.get(rf.feature_id)
        outcome = check_comparability(rf.definition, target, rf.target_measurement, candidate, cm)
        status, reason, message = outcome.status, outcome.reason_code, outcome.message
        comparison = None
        if status == COMPARED:
            comparator = get_comparator(rf.definition.comparator_id)
            try:
                comparison = comparator(rf.target_measurement.value, cm.value, rf.tau, rf.definition)
            except AnalogueEngineError as exc:
                # A per-candidate numeric failure must not abort the whole search.
                status, reason, message = C_INCOMPATIBLE, f"comparison_failed:{exc.code}", exc.message
        raw.append((rf, status, reason, message, comparison))

    compared = [(rf, c) for rf, status, _, _, c in raw if status == COMPARED]
    covered_weight = math.fsum(rf.effective_weight for rf, _ in compared)
    coverage = covered_weight / resolved.total_weight
    if covered_weight > 0:
        # fsum is exactly rounded, so the result does not depend on feature order.
        score = math.fsum(rf.effective_weight * c.similarity for rf, c in compared) / covered_weight
    else:
        score = None

    components: list[ComponentResult] = []
    for rf, status, reason, message, c in raw:
        cm = candidate.measurements.get(rf.feature_id)
        contribution = None
        if c is not None and covered_weight > 0:
            contribution = rf.effective_weight * c.similarity / covered_weight
        components.append(
            ComponentResult(
                feature_id=rf.feature_id,
                dimension=rf.dimension,
                status=status,
                reason_code=reason,
                message=message,
                unit=rf.definition.canonical_unit,
                target_value=rf.target_measurement.value,
                candidate_value=cm.value if (cm is not None and c is not None) else None,
                delta=c.delta if c else None,
                abs_difference=c.abs_difference if c else None,
                normalized_discrepancy=c.normalized_discrepancy if c else None,
                similarity=c.similarity if c else None,
                detail=dict(c.detail) if c else {},
                comparator_id=rf.definition.comparator_id,
                tau=rf.tau,
                raw_weight=rf.raw_weight,
                effective_weight=rf.effective_weight,
                contribution=contribution,
                blocking=status != COMPARED and rf.counts_for_completeness,
                required=rf.required,
            )
        )

    dimensions = _dimension_results(resolved, components)
    by_feature = {comp.feature_id: comp for comp in components}
    constraint_results = tuple(
        _evaluate_constraint(con, by_feature[con.feature_id]) for con in resolved.profile.constraints
    )

    reasons: list[str] = []
    for comp, rf in zip(components, resolved.features):
        if comp.status == COMPARED:
            continue
        if comp.blocking:
            why = []
            if rf.effective_weight > 0:
                why.append("positive weight")
            if rf.required:
                why.append("required feature")
            if rf.used_by_constraint:
                why.append("used by a constraint")
            reasons.append(f"{comp.status}:{comp.feature_id} ({', '.join(why)}): {comp.message}")
        else:
            reasons.append(f"informational:{comp.status}:{comp.feature_id} (zero weight, not required)")
    for cr in constraint_results:
        if cr.status == "violated":
            reasons.append(f"requirement_not_met:{cr.id}: {cr.message}")

    blocking = [comp for comp in components if comp.blocking]
    if any(cr.status == "violated" for cr in constraint_results):
        category = REQUIREMENT_NOT_MET
    elif any(comp.status == C_INCOMPATIBLE for comp in blocking):
        category = INCOMPATIBLE
    elif any(comp.status in INSUFFICIENT_STATUSES for comp in blocking):
        category = PARTIAL
    else:
        category = COMPLETE

    return ComparisonResult(
        target_id=target.id,
        candidate_id=candidate.id,
        profile_id=resolved.profile.id,
        profile_version=resolved.profile.version,
        model_id=MODEL_ID,
        model_version=MODEL_VERSION,
        data_mode=target.data_mode,
        calibration_status=resolved.profile.calibration_status,
        category=category,
        rankable=category == COMPLETE,
        score_observed=score,
        coverage=coverage,
        components=tuple(components),
        dimensions=dimensions,
        constraints=constraint_results,
        reasons=tuple(reasons),
        limitations=_limitations(resolved, category),
        declared_limitations=resolved.profile.declared_limitations,
    )


# --------------------------------------------------------------------------- public API


def compare(target: Any, candidate: Any, profile: Any, feature_definitions: Any) -> ComparisonResult:
    """Compare one candidate with the target under ``profile``."""
    target, candidate, profile = as_site(target), as_site(candidate), as_profile(profile)
    _check_data_modes(target, [candidate])
    resolved = resolve_profile(profile, feature_definitions, target)
    return _compare_resolved(resolved, candidate)


def rank(
    target: Any, candidates: Sequence[Any], profile: Any, feature_definitions: Any
) -> RankingResult:
    """Rank complete candidates; return partial and excluded ones separately."""
    target, profile = as_site(target), as_profile(profile)
    if isinstance(candidates, (str, bytes)) or not isinstance(candidates, Iterable):
        raise InvalidRequestError("candidates must be a list", code="invalid_type")
    sites = [as_site(c) for c in candidates]
    ids = [s.id for s in sites]
    duplicates = sorted({i for i in ids if ids.count(i) > 1})
    if duplicates:
        raise InvalidRequestError(
            f"duplicate candidate ids {duplicates}", code="duplicate_candidate", candidates=duplicates
        )
    _check_data_modes(target, sites)
    # Weights are fixed here, before any candidate is inspected.
    resolved = resolve_profile(profile, feature_definitions, target)
    results = [_compare_resolved(resolved, s) for s in sites]

    complete = sorted(
        (r for r in results if r.category == COMPLETE),
        key=lambda r: (-round(r.score_observed, SCORE_ORDER_DECIMALS), r.candidate_id),
    )
    ranked: list[RankedEntry] = []
    for position, r in enumerate(complete, start=1):
        key = round(r.score_observed, SCORE_ORDER_DECIMALS)
        tied = tuple(
            o.candidate_id
            for o in complete
            if o is not r and round(o.score_observed, SCORE_ORDER_DECIMALS) == key
        )
        ranked.append(RankedEntry(position=position, tied_with=tied, result=r))

    partial = tuple(sorted((r for r in results if r.category == PARTIAL), key=lambda r: r.candidate_id))
    excluded = tuple(
        sorted(
            (r for r in results if r.category in (INCOMPATIBLE, REQUIREMENT_NOT_MET)),
            key=lambda r: r.candidate_id,
        )
    )

    warnings: list[str] = []
    if not sites:
        warnings.append("no_candidates: the request contained no candidates")
    elif not ranked:
        warnings.append(
            "no_complete_candidates: no candidate has comparable values for every blocking feature "
            "while satisfying all requirements; see 'partial' and 'excluded'. Reducing the profile "
            "requires an explicit new profile version applied to all candidates."
        )
    if target.id in ids:
        warnings.append(f"target_in_candidates: '{target.id}' is also listed as a candidate")
    if target.data_mode == "synthetic":
        warnings.append("synthetic_data: results exercise the engine, not real sites")
    if profile.calibration_status != "science_reviewed":
        warnings.append(f"calibration_status={profile.calibration_status}: weights and tau are not scientifically reviewed")
    if any(r.tied_with for r in ranked):
        warnings.append("ties_present: tied scores are ordered by candidate_id only, which implies no scientific preference")

    return RankingResult(
        target_id=target.id,
        profile_id=profile.id,
        profile_version=profile.version,
        model_id=MODEL_ID,
        model_version=MODEL_VERSION,
        data_mode=target.data_mode,
        calibration_status=profile.calibration_status,
        active_features=profile.active_feature_ids,
        effective_weights=resolved.effective_weights(),
        dimension_weights=dict(resolved.dimension_weights),
        ranked=tuple(ranked),
        partial=partial,
        excluded=excluded,
        warnings=tuple(warnings),
        declared_limitations=profile.declared_limitations,
    )
