"""Rankings over time: which sites gain or lose analogy as Earth changes.

The Earth side can come from yearly observations or projections (one table
per year; the same site ids every year). The target and the profile stay
fixed, so every year is measured with the same yardstick: tau, weights and
requirements do not move, and a site's score never depends on the other
sites. A change in a site's score therefore comes only from a change in its
own data. That is what makes a year slider meaningful. Min-max scaling per
year would invent changes.

    rank_over_years(target, {2025: sites_2025, 2050: sites_2050, ...}, profile, defs)

A site may be absent in some years (e.g. it no longer passes a "dry, bare
land" pre-filter); its trajectory then has nulls for those years.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any, Mapping, Sequence

from .engine import rank
from .errors import InvalidRequestError
from .models import as_profile, as_site
from .results import RankingResult, to_json


@dataclass(frozen=True)
class Trajectory:
    candidate_id: str
    scores: dict[int, float | None]  # year -> score 0-1 (null: not ranked / absent that year)
    positions: dict[int, int | None]  # year -> rank position
    change: float | None  # last available score - first available score
    trend_per_decade: float | None  # least-squares slope of score vs year, x10
    status: str  # gaining | losing | stable | entering | leaving | insufficient


@dataclass(frozen=True)
class TimelineResult:
    target_id: str
    profile_id: str
    profile_version: str
    years: tuple[int, ...]
    top_k: int
    top_by_year: dict[int, tuple[str, ...]]
    emerging: tuple[str, ...]  # in the top k in the last year, not in the first
    fading: tuple[str, ...]  # in the top k in the first year, not in the last
    watched: tuple[Trajectory, ...]  # trajectories of the requested sites (e.g. known analogs)
    biggest_gainers: tuple[Trajectory, ...]
    biggest_losers: tuple[Trajectory, ...]
    change_threshold: float
    note: str = (
        "Same target, profile, scales and weights for every year; a score change comes only from the "
        "site's own data. Projections carry their own uncertainty, which is not propagated here."
    )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self, **kwargs: Any) -> str:
        return to_json(self.to_dict(), **kwargs)


def _slope(points: list[tuple[int, float]]) -> float | None:
    if len(points) < 2:
        return None
    xs = [x for x, _ in points]
    ys = [y for _, y in points]
    mx, my = math.fsum(xs) / len(xs), math.fsum(ys) / len(ys)
    sxx = math.fsum((x - mx) ** 2 for x in xs)
    if sxx == 0:
        return None
    return math.fsum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx


def _trajectory(cid: str, years: Sequence[int], results: Mapping[int, RankingResult], threshold: float) -> Trajectory:
    scores: dict[int, float | None] = {}
    positions: dict[int, int | None] = {}
    for y in years:
        entry = next((e for e in results[y].ranked if e.result.candidate_id == cid), None)
        scores[y] = entry.result.score_observed if entry else None
        positions[y] = entry.position if entry else None
    present = [(y, s) for y, s in scores.items() if s is not None]
    slope = _slope(present)
    change = present[-1][1] - present[0][1] if len(present) >= 2 else None
    first, last = scores[years[0]], scores[years[-1]]
    if first is None and last is not None:
        status = "entering"
    elif first is not None and last is None:
        status = "leaving"
    elif change is None:
        status = "insufficient"
    elif change >= threshold:
        status = "gaining"
    elif change <= -threshold:
        status = "losing"
    else:
        status = "stable"
    return Trajectory(cid, scores, positions, change, None if slope is None else slope * 10, status)


def rank_over_years(
    target: Any,
    sites_by_year: Mapping[int, Sequence[Any]],
    profile: Any,
    feature_definitions: Any,
    *,
    watch: Sequence[str] = (),
    top_k: int = 20,
    change_threshold: float = 0.02,
    n_movers: int = 10,
) -> TimelineResult:
    """Rank the same target against each year's Earth sites with one fixed profile."""
    if not sites_by_year:
        raise InvalidRequestError("sites_by_year is empty", code="no_years")
    if any(isinstance(y, bool) or not isinstance(y, int) for y in sites_by_year):
        raise InvalidRequestError("years must be integers", code="invalid_year")
    if top_k < 1 or change_threshold < 0:
        raise InvalidRequestError("top_k must be >= 1 and change_threshold >= 0", code="invalid_settings")
    target, profile = as_site(target), as_profile(profile)
    years = sorted(sites_by_year)
    results = {y: rank(target, [as_site(s) for s in sites_by_year[y]], profile, feature_definitions) for y in years}

    top = {y: tuple(results[y].order()[:top_k]) for y in years}
    first, last = set(top[years[0]]), set(top[years[-1]])
    all_ids = sorted({e.result.candidate_id for y in years for e in results[y].ranked})
    trajectories = {cid: _trajectory(cid, years, results, change_threshold) for cid in all_ids}
    for cid in watch:
        if cid not in trajectories:
            trajectories[cid] = _trajectory(cid, years, results, change_threshold)
    movers = [t for t in trajectories.values() if t.change is not None]
    gainers = sorted(movers, key=lambda t: (-t.change, t.candidate_id))[:n_movers]
    losers = sorted(movers, key=lambda t: (t.change, t.candidate_id))[:n_movers]

    return TimelineResult(
        target_id=target.id,
        profile_id=profile.id,
        profile_version=profile.version,
        years=tuple(years),
        top_k=top_k,
        top_by_year=top,
        emerging=tuple(c for c in top[years[-1]] if c not in first),
        fading=tuple(c for c in top[years[0]] if c not in last),
        watched=tuple(trajectories[c] for c in watch),
        biggest_gainers=tuple(gainers),
        biggest_losers=tuple(losers),
        change_threshold=change_threshold,
    )
