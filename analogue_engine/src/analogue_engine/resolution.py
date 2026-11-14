"""Profile resolution: validate a profile against definitions and target,
and compute the effective weights *before* looking at any candidate.

Effective weights (two levels, both normalised):

    w_j = (W_g / sum_g W_g) * (a_j / sum_{k in g} a_k)

* a dimension with W_g > 0 must have a positive internal sum;
* a dimension with W_g = 0 contributes nothing (its features get w_j = 0);
* the global sum of dimension weights must be positive.

With a single dimension and no explicit ``dimension_weights`` the dimension
gets W = 1. With several dimensions, ``dimension_weights`` is mandatory: the
engine refuses to guess, because a flat default would let a dimension gain
importance simply by having more variables.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from .comparators import TAU_CANONICAL, TAU_DECADE, ComparatorSpec, get_comparator_spec
from .errors import AnalogueEngineError, ProfileError
from .models import (
    NUMERIC_CONSTRAINT_TYPES,
    Constraint,
    FeatureDefinition,
    Measurement,
    Profile,
    ProfileFeature,
    Site,
    feature_definitions_by_id,
    value_matches_kind,
)


def _check_scale(where: str, pf: ProfileFeature, definition: FeatureDefinition, spec: ComparatorSpec) -> None:
    fid = pf.feature_id
    if spec.tau is None:
        if pf.tau is not None or pf.tau_unit is not None:
            raise ProfileError(
                f"{where}: comparator '{spec.id}' for '{fid}' takes no tau/range; remove it to avoid "
                "suggesting a scale that is not used",
                code="tau_not_used",
                feature_id=fid,
            )
        return
    if pf.tau is None:
        raise ProfileError(
            f"{where}: comparator '{spec.id}' for '{fid}' needs 'tau' (or a fixed 'range')",
            code="tau_required",
            feature_id=fid,
        )
    expected_unit = definition.canonical_unit if spec.tau == TAU_CANONICAL else "decade"
    if pf.tau_unit != expected_unit:
        raise ProfileError(
            f"{where}: tau for '{fid}' is in '{pf.tau_unit}' but comparator '{spec.id}' expects "
            f"'{expected_unit}'",
            code="tau_unit_mismatch",
            feature_id=fid,
        )
    if spec.tau == TAU_DECADE and pf.range_min is not None:
        raise ProfileError(
            f"{where}: a min-max 'range' is only meaningful for linear comparators ('{fid}')",
            code="range_not_supported",
            feature_id=fid,
        )


def _check_constraint(where: str, c: Constraint, definition: FeatureDefinition) -> None:
    if c.type in NUMERIC_CONSTRAINT_TYPES:
        if definition.kind != "scalar":
            raise ProfileError(
                f"{where}: constraint '{c.id}' ({c.type}) needs a scalar feature; "
                f"'{c.feature_id}' is {definition.kind}",
                code="constraint_kind_mismatch",
            )
        if c.unit != definition.canonical_unit:
            raise ProfileError(
                f"{where}: constraint '{c.id}' limit is in '{c.unit}' but the canonical unit of "
                f"'{c.feature_id}' is '{definition.canonical_unit}'",
                code="constraint_unit_mismatch",
            )
        return
    # equals
    if definition.kind == "boolean" and isinstance(c.value, bool):
        return
    if definition.kind == "categorical" and isinstance(c.value, str) and c.value in (definition.categories or ()):
        return
    raise ProfileError(
        f"{where}: constraint '{c.id}' (equals {c.value!r}) does not fit feature '{c.feature_id}' "
        f"of kind '{definition.kind}'",
        code="constraint_kind_mismatch",
    )


@dataclass(frozen=True)
class ResolvedFeature:
    feature_id: str
    dimension: str
    definition: FeatureDefinition
    tau: float | None  # None for comparators without a scale
    raw_weight: float  # a_j as given
    effective_weight: float  # w_j, fixed for the whole search
    required: bool  # listed in required_features
    used_by_constraint: bool
    target_measurement: Measurement

    @property
    def counts_for_completeness(self) -> bool:
        """Whether a missing/incompatible value blocks ranking."""
        return self.effective_weight > 0 or self.required or self.used_by_constraint


@dataclass(frozen=True)
class ResolvedProfile:
    profile: Profile
    target: Site
    features: tuple[ResolvedFeature, ...]
    dimension_weights: dict[str, float]  # normalised W_g
    total_weight: float  # fsum of effective weights (== 1 up to rounding)

    def effective_weights(self) -> dict[str, float]:
        return {f.feature_id: f.effective_weight for f in self.features}


def compute_effective_weights(
    features: tuple[ProfileFeature, ...],
    dimension_of: dict[str, str],
    dimension_weights: dict[str, float] | None,
    where: str = "profile",
) -> tuple[dict[str, float], dict[str, float]]:
    """Return (effective weight per feature, normalised weight per dimension)."""
    dims: list[str] = []
    for f in features:
        d = dimension_of[f.feature_id]
        if d not in dims:
            dims.append(d)

    if dimension_weights is None:
        if len(dims) > 1:
            raise ProfileError(
                f"{where}: active features span several dimensions {dims}; "
                "'dimension_weights' must be given explicitly",
                code="dimension_weights_required",
                dimensions=dims,
            )
        dimension_weights = {dims[0]: 1.0}

    missing = [d for d in dims if d not in dimension_weights]
    extra = [d for d in dimension_weights if d not in dims]
    if missing or extra:
        raise ProfileError(
            f"{where}: dimension_weights must cover exactly the active dimensions; "
            f"missing {missing}, without active features {extra}",
            code="dimension_weights_mismatch",
            missing=missing,
            extra=extra,
        )
    for d, w in dimension_weights.items():
        if not math.isfinite(w):
            raise ProfileError(f"{where}: dimension weight for '{d}' is not finite", code="non_finite_number")
        if w < 0:
            raise ProfileError(
                f"{where}: negative dimension weight for '{d}' ({w})", code="negative_weight", dimension=d
            )
    try:
        total_dim = math.fsum(dimension_weights[d] for d in dims)
        internal_sums = {
            d: math.fsum(f.weight for f in features if dimension_of[f.feature_id] == d) for d in dims
        }
    except OverflowError:
        raise ProfileError(
            f"{where}: weights are too large to sum; rescale them (only ratios matter)",
            code="weight_overflow",
        ) from None
    if not math.isfinite(total_dim) or not all(math.isfinite(v) for v in internal_sums.values()):
        raise ProfileError(
            f"{where}: weights are too large to sum; rescale them (only ratios matter)",
            code="weight_overflow",
        )
    if total_dim <= 0:
        raise ProfileError(f"{where}: dimension weights sum to zero", code="zero_weight_sum")

    effective: dict[str, float] = {}
    normalised_dims: dict[str, float] = {}
    for d in dims:
        members = [f for f in features if dimension_of[f.feature_id] == d]
        internal = internal_sums[d]
        W = dimension_weights[d] / total_dim
        normalised_dims[d] = W
        if W > 0 and internal <= 0:
            raise ProfileError(
                f"{where}: dimension '{d}' has positive weight but its features' weights sum to zero",
                code="zero_internal_weight_sum",
                dimension=d,
            )
        for f in members:
            effective[f.feature_id] = W * (f.weight / internal) if W > 0 else 0.0
    if math.fsum(effective.values()) <= 0:
        raise ProfileError(f"{where}: effective weights sum to zero", code="zero_weight_sum")
    return effective, normalised_dims


def resolve_profile(profile: Profile, feature_definitions: Any, target: Site) -> ResolvedProfile:
    """Validate everything that does not depend on a candidate."""
    where = f"profile[{profile.id}@{profile.version}]"
    definitions = feature_definitions_by_id(feature_definitions)

    if profile.target_id != target.id:
        raise ProfileError(
            f"{where}: profile is for target '{profile.target_id}', got target '{target.id}'",
            code="target_mismatch",
        )

    seen: set[str] = set()
    for pf in profile.features:
        if pf.feature_id in seen:
            raise ProfileError(
                f"{where}: feature '{pf.feature_id}' listed twice; the engine never duplicates "
                "descriptors implicitly",
                code="duplicate_active_feature",
                feature_id=pf.feature_id,
            )
        seen.add(pf.feature_id)
        if pf.feature_id not in definitions:
            raise ProfileError(
                f"{where}: active feature '{pf.feature_id}' has no feature definition",
                code="unknown_feature",
                feature_id=pf.feature_id,
            )
        definition = definitions[pf.feature_id]
        _check_scale(where, pf, definition, get_comparator_spec(definition.comparator_id))

    active = set(seen)
    unknown_required = [r for r in profile.required_features if r not in active]
    if unknown_required:
        raise ProfileError(
            f"{where}: required features {unknown_required} are not active features",
            code="required_not_active",
        )
    constraint_ids: set[str] = set()
    for c in profile.constraints:
        if c.id in constraint_ids:
            raise ProfileError(f"{where}: duplicate constraint id '{c.id}'", code="duplicate_constraint")
        constraint_ids.add(c.id)
        if c.feature_id not in active:
            raise ProfileError(
                f"{where}: constraint '{c.id}' refers to non-active feature '{c.feature_id}'",
                code="constraint_not_active",
            )
        _check_constraint(where, c, definitions[c.feature_id])

    # The target must provide every active feature (any weight, including 0).
    for pf in profile.features:
        definition = definitions[pf.feature_id]
        m = target.measurements.get(pf.feature_id)
        if m is None or m.status != "valid":
            raise ProfileError(
                f"{where}: target '{target.id}' has no valid value for active feature "
                f"'{pf.feature_id}'. Remove the feature explicitly (new profile version) or "
                "supply the target value; the engine does not deactivate it automatically.",
                code="target_missing_feature",
                feature_id=pf.feature_id,
            )
        if m.unit != definition.canonical_unit:
            raise ProfileError(
                f"{where}: target unit '{m.unit}' for '{pf.feature_id}' is not the canonical unit "
                f"'{definition.canonical_unit}'",
                code="target_unit_mismatch",
                feature_id=pf.feature_id,
            )
        absent = [n for n in definition.protocol.required_metadata if m.metadata(n) is None]
        if absent:
            raise ProfileError(
                f"{where}: target measurement for '{pf.feature_id}' lacks protocol metadata {absent}",
                code="target_metadata_missing",
                feature_id=pf.feature_id,
            )
        problem = value_matches_kind(m.value, definition.kind, definition.categories)
        if problem:
            raise ProfileError(
                f"{where}: target value for '{pf.feature_id}' does not fit kind '{definition.kind}': {problem}",
                code="target_value_type_mismatch",
                feature_id=pf.feature_id,
            )
        # The target must be comparable with itself (e.g. log needs x > 0,
        # cosine needs a non-zero vector); otherwise no candidate can be.
        try:
            get_comparator_spec(definition.comparator_id).fn(m.value, m.value, pf.tau, definition)
        except AnalogueEngineError as exc:
            raise ProfileError(
                f"{where}: target value for '{pf.feature_id}' cannot be compared: {exc.message}",
                code="target_value_not_comparable",
                feature_id=pf.feature_id,
            ) from None

    dimension_of = {pf.feature_id: definitions[pf.feature_id].dimension for pf in profile.features}
    effective, dims = compute_effective_weights(
        profile.features, dimension_of, dict(profile.dimension_weights) if profile.dimension_weights else None, where
    )
    constrained = {c.feature_id for c in profile.constraints}
    resolved = tuple(
        ResolvedFeature(
            feature_id=pf.feature_id,
            dimension=dimension_of[pf.feature_id],
            definition=definitions[pf.feature_id],
            tau=pf.tau,
            raw_weight=pf.weight,
            effective_weight=effective[pf.feature_id],
            required=pf.feature_id in profile.required_features,
            used_by_constraint=pf.feature_id in constrained,
            target_measurement=target.measurements[pf.feature_id],
        )
        for pf in profile.features
    )
    return ResolvedProfile(
        profile=profile,
        target=target,
        features=resolved,
        dimension_weights=dims,
        total_weight=math.fsum(effective.values()),
    )
