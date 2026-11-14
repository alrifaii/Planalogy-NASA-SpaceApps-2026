"""Site cards: turn a ComparisonResult into a readable summary.

    card = explain(result)

A card answers, for one candidate: how similar overall, how much of the
evidence was available, which categories match well, which only partly,
which do not, what data is missing, which requirements pass, and what Earth
cannot reproduce. Nothing is recomputed: the card only re-arranges what the
engine already produced, so every number on it can be traced back.

The strong/weak thresholds are presentation choices for grouping categories,
not scientific cut-offs. They are reported in the card.
"""

from __future__ import annotations

from typing import Any

from .comparability import COMPARED
from .errors import InvalidRequestError
from .results import ComparisonResult


def _pct(x: float | None) -> float | None:
    return None if x is None else round(100 * x, 1)


def explain(result: ComparisonResult, *, strong: float = 0.75, weak: float = 0.4) -> dict[str, Any]:
    if not (0 <= weak < strong <= 1):
        raise InvalidRequestError("thresholds must satisfy 0 <= weak < strong <= 1", code="invalid_settings")

    components = {c.feature_id: c for c in result.components}
    matches, partial, mismatches, not_scored = [], [], [], []
    for d in result.dimensions:
        features = [
            {
                "feature": fid,
                "similarity_0_100": _pct(components[fid].similarity),
                "target_value": components[fid].target_value,
                "site_value": components[fid].candidate_value,
                "unit": components[fid].unit,
            }
            for fid in d.compared_features
        ]
        item = {"category": d.dimension, "score_0_100": _pct(d.score_observed), "weight": round(d.dimension_weight, 4),
                "features": features}
        if d.dimension_weight == 0:
            not_scored.append(item)
        elif d.score_observed is None:
            continue  # nothing comparable: reported under "missing"
        elif d.score_observed >= strong:
            matches.append(item)
        elif d.score_observed > weak:
            partial.append(item)
        else:
            mismatches.append(item)
    for group in (matches, partial, mismatches):
        group.sort(key=lambda x: (-x["score_0_100"], x["category"]))

    missing = [
        {"feature": c.feature_id, "category": c.dimension, "status": c.status, "reason": c.reason_code,
         "blocks_ranking": c.blocking}
        for c in result.components if c.status != COMPARED
    ]
    requirements = [
        {"id": r.id, "feature": r.feature_id, "status": r.status, "detail": r.message} for r in result.constraints
    ]

    def names(group):
        return ", ".join(f"{x['category']} ({x['score_0_100']:.0f})" for x in group)

    parts = []
    if matches:
        parts.append(f"Strong match in {names(matches)}")
    if partial:
        parts.append(f"partial in {names(partial)}")
    if mismatches:
        parts.append(f"weak in {names(mismatches)}")
    if missing:
        parts.append("missing data: " + ", ".join(m["feature"] for m in missing))
    failed = [r for r in requirements if r["status"] == "violated"]
    if failed:
        parts.append("fails requirement: " + ", ".join(r["id"] for r in failed))
    headline = "; ".join(parts) + "." if parts else "No comparable data."

    return {
        "site_id": result.candidate_id,
        "target_id": result.target_id,
        "profile": f"{result.profile_id}@{result.profile_version}",
        "score_0_100": _pct(result.score_observed),
        "coverage_pct": _pct(result.coverage),
        "status": result.category,  # complete | partial | incompatible | requirement_not_met
        "rankable": result.rankable,
        "headline": headline,
        "matches": matches,
        "partial_matches": partial,
        "mismatches": mismatches,
        "not_scored": not_scored,
        "missing": missing,
        "requirements": requirements,
        "earth_cannot_reproduce": list(result.declared_limitations),
        "caveats": [x for x in result.limitations],
        "thresholds": {"strong_at_least": strong, "weak_at_most": weak,
                       "note": "presentation thresholds for grouping, not scientific cut-offs"},
        "data_mode": result.data_mode,
        "calibration_status": result.calibration_status,
    }
