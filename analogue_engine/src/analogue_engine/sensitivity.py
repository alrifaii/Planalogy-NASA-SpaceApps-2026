"""One-at-a-time sensitivity of the ranking to weights and tau.

For each active feature with positive weight: multiply its internal weight
a_j by (1 +/- r) and renormalise. For each active feature: multiply tau_j by
(1 +/- r). If there are several dimensions, also perturb each W_g.

This measures *stability of the ranking under assumption changes*. It is not
a probability that a site is a valid analogue, and stability does not prove
scientific correctness.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from typing import Any, Sequence

from .engine import rank
from .errors import InvalidRequestError
from .models import Profile, as_profile, as_site, feature_definitions_by_id
from .results import RankingResult, to_json


@dataclass(frozen=True)
class Perturbation:
    parameter: str  # e.g. "weight:slope_deg", "tau:vrm", "dimension_weight:terrain"
    factor: float
    order: tuple[str, ...]
    order_changed: bool
    moved: tuple[dict, ...]  # {"candidate_id", "baseline_position", "new_position"}
    membership_changed: bool  # a candidate entered/left the ranked list
    score_changes: dict[str, float]  # new - baseline score for ranked candidates


@dataclass(frozen=True)
class SensitivityReport:
    profile_id: str
    profile_version: str
    relative_change: float
    baseline_order: tuple[str, ...]
    baseline_scores: dict[str, float]
    perturbations: tuple[Perturbation, ...]
    note: str = (
        "One-at-a-time stability check of the ranking under +/- changes of weights and tau. "
        "Not a probability of site validity; stability does not imply scientific correctness."
    )

    @property
    def unstable_parameters(self) -> list[str]:
        return sorted({p.parameter for p in self.perturbations if p.order_changed or p.membership_changed})

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self, **kwargs: Any) -> str:
        return to_json(self.to_dict(), **kwargs)


def _scores(result: RankingResult) -> dict[str, float]:
    return {e.result.candidate_id: e.result.score_observed for e in result.ranked}


def _variants(profile: Profile, factor: float, dimension_of: dict[str, str]) -> list[tuple[str, Profile]]:
    """Perturbations that can change something. Skipped by construction:
    the weight of a feature that is the only positive-weight member of its
    dimension (renormalisation cancels it) and tau of zero-weight features
    (they never enter the score; constraints use physical differences)."""
    positive_in_dim: dict[str, int] = {}
    for pf in profile.features:
        if pf.weight > 0:
            d = dimension_of[pf.feature_id]
            positive_in_dim[d] = positive_in_dim.get(d, 0) + 1
    out: list[tuple[str, Profile]] = []
    for i, pf in enumerate(profile.features):
        if pf.weight > 0 and positive_in_dim[dimension_of[pf.feature_id]] > 1:
            features = list(profile.features)
            features[i] = replace(pf, weight=pf.weight * factor)
            out.append((f"weight:{pf.feature_id}", replace(profile, features=tuple(features))))
    if profile.dimension_weights and len(profile.dimension_weights) > 1:
        for dim, w in profile.dimension_weights.items():
            if w > 0:
                dims = dict(profile.dimension_weights)
                dims[dim] = w * factor
                out.append((f"dimension_weight:{dim}", replace(profile, dimension_weights=dims)))
    for i, pf in enumerate(profile.features):
        if pf.weight == 0 or pf.tau is None:  # no scale, or never enters the score
            continue
        features = list(profile.features)
        features[i] = replace(pf, tau=pf.tau * factor)
        out.append((f"tau:{pf.feature_id}", replace(profile, features=tuple(features))))
    return out


def sensitivity_analysis(
    target: Any,
    candidates: Sequence[Any],
    profile: Any,
    feature_definitions: Any,
    relative_change: float = 0.2,
) -> SensitivityReport:
    if isinstance(relative_change, bool) or not isinstance(relative_change, (int, float)) or not (
        0 < relative_change < 1
    ):
        raise InvalidRequestError(
            f"relative_change must be a number in (0, 1), got {relative_change!r}",
            code="invalid_number",
        )
    target, profile = as_site(target), as_profile(profile)
    sites = [as_site(c) for c in candidates]
    baseline = rank(target, sites, profile, feature_definitions)  # validates everything first
    definitions = feature_definitions_by_id(feature_definitions)
    dimension_of = {pf.feature_id: definitions[pf.feature_id].dimension for pf in profile.features}
    base_order = tuple(baseline.order())
    base_scores = _scores(baseline)
    base_pos = {cid: i + 1 for i, cid in enumerate(base_order)}

    perturbations: list[Perturbation] = []
    for factor in (1 - relative_change, 1 + relative_change):
        for name, variant in _variants(profile, factor, dimension_of):
            result = rank(target, sites, variant, feature_definitions)
            order = tuple(result.order())
            pos = {cid: i + 1 for i, cid in enumerate(order)}
            moved = tuple(
                {"candidate_id": cid, "baseline_position": base_pos[cid], "new_position": pos[cid]}
                for cid in base_order
                if cid in pos and pos[cid] != base_pos[cid]
            )
            scores = _scores(result)
            perturbations.append(
                Perturbation(
                    parameter=name,
                    factor=factor,
                    order=order,
                    order_changed=order != base_order,
                    moved=moved,
                    membership_changed=set(order) != set(base_order),
                    score_changes={c: scores[c] - base_scores[c] for c in base_order if c in scores},
                )
            )
    perturbations.sort(key=lambda p: (p.parameter, p.factor))
    return SensitivityReport(
        profile_id=profile.id,
        profile_version=profile.version,
        relative_change=relative_change,
        baseline_order=base_order,
        baseline_scores=base_scores,
        perturbations=tuple(perturbations),
    )
