"""Weight calibration against known analog sites.

Idea
----
For a *complete* candidate i the engine score is linear in the effective
weights:  S_i(w) = sum_j w_j s_ij,  with w on the simplex (w_j >= 0, sum = 1).
Given a few sites that experts already accept as analogs of the target
("known analogs", e.g. well-studied deserts or impact craters), we look for
weights that rank those sites above the other candidates, while staying close
to the starting profile (written by Science or proposed by an AI from the
mission description).

Objective (minimised over the simplex)::

    L(w) = mean_{p in known, n in others} softplus( -(S_p(w) - S_n(w)) / T )
           + lambda * KL(w || w0)

* the first term is a smooth pairwise ranking loss: it is large when a known
  analog p scores below another candidate n;
* T (temperature) sets how sharp "below" is, in score units;
* KL(w || w0) = sum_j w_j log(w_j / w0_j) anchors w to the prior weights w0.
  With few known analogs this is what prevents the weights from simply
  memorising them.

It is optimised with exponentiated gradient (multiplicative updates, a mirror
descent step) in which the KL anchor is solved exactly at each step, so the
update stays stable for any prior strength. w stays positive and sums to 1 at
every step, and the result is fully deterministic.

What is tuned / not tuned
-------------------------
* Only weights of features with a positive starting weight are tuned. Zero
  weights stay 0, so the set of complete candidates never changes.
* Scales (tau / range), comparators, requirements and data are not touched.
* "Other candidates" are *unlabelled*, not known bad sites: the purpose is a
  relative ordering, and the best-ranked unlabelled sites are exactly the
  "new analog" suggestions.

Validation
----------
Leave-one-out: each known analog is hidden in turn (treated as an ordinary
unlabelled candidate), weights are re-tuned on the others, and we record
where the hidden site lands. If calibration only memorised its examples, the
hidden site would not improve. Every reported rank comes from re-running the
real engine with the calibrated profile, not from the internal surrogate.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, replace
from typing import Any, Sequence

from .engine import rank
from .errors import InvalidRequestError
from .models import Profile, ProfileFeature, as_profile, as_site, feature_definitions_by_id
from .profiles import profile_to_dict
from .results import RankingResult, to_json


@dataclass(frozen=True)
class CalibrationSettings:
    prior_strength: float = 1.0  # lambda: higher = stay closer to the starting weights
    temperature: float = 0.05  # T, in score units (0-1)
    iterations: int = 400
    step: float = 0.05  # exponentiated-gradient step size


@dataclass(frozen=True)
class RankSummary:
    ranks: dict[str, int | None]  # known analog -> position among ranked (1 = best), None if not ranked
    n_ranked: int
    mean_top_percent: float | None  # mean of rank / n_ranked * 100 (lower is better)
    in_top_10_percent: int  # how many known analogs are in the top 10 %


@dataclass(frozen=True)
class LeaveOneOut:
    held_out: str
    rank_with_start_weights: int
    rank_with_calibrated_weights: int
    n_ranked: int


@dataclass(frozen=True)
class CalibrationResult:
    profile_id: str
    start_version: str
    calibrated_version: str
    known_analogs_used: tuple[str, ...]
    known_analogs_unusable: dict[str, str]  # id -> why it cannot be used (partial, excluded...)
    start_feature_weights: dict[str, float]
    calibrated_feature_weights: dict[str, float]
    start_dimension_weights: dict[str, float]
    calibrated_dimension_weights: dict[str, float]
    start_summary: RankSummary
    calibrated_summary: RankSummary
    leave_one_out: tuple[LeaveOneOut, ...]
    new_candidates: tuple[dict[str, Any], ...]  # best-ranked sites that are not known analogs
    calibrated_profile: dict[str, Any]  # ready to pass to rank()
    settings: CalibrationSettings
    warnings: tuple[str, ...]
    note: str = (
        "Weights tuned so that known analogs rank high, anchored to the starting weights. "
        "Unlabelled candidates are not assumed to be bad sites. Scales, requirements and data "
        "are unchanged. Calibration against a handful of known analogs is evidence of consistency, "
        "not scientific validation."
    )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self, **kwargs: Any) -> str:
        return to_json(self.to_dict(), **kwargs)


# --------------------------------------------------------------------------- helpers


def _sigmoid(x: float) -> float:
    if x >= 0:
        z = math.exp(-x)
        return 1.0 / (1.0 + z)
    z = math.exp(x)
    return z / (1.0 + z)


def _softplus(x: float) -> float:
    return max(x, 0.0) + math.log1p(math.exp(-abs(x)))


def _optimise(
    sims: dict[str, list[float]], positives: Sequence[str], w0: list[float], settings: CalibrationSettings
) -> list[float]:
    """Exponentiated gradient on the pairwise logistic loss + lambda * KL(w || w0)."""
    pos = [sims[p] for p in positives]
    neg = [v for cid, v in sims.items() if cid not in set(positives)]
    if not pos or not neg:
        return list(w0)
    k = len(w0)
    w = list(w0)
    T, lam = settings.temperature, settings.prior_strength
    n_pairs = len(pos) * len(neg)
    for _ in range(settings.iterations):
        sp = [math.fsum(wj * sj for wj, sj in zip(w, s)) for s in pos]
        sn = [math.fsum(wj * sj for wj, sj in zip(w, s)) for s in neg]
        # c_pn = d softplus(-(sp - sn)/T) / d margin = -sigmoid(-(sp - sn)/T) / T
        cp = [0.0] * len(pos)
        cn = [0.0] * len(neg)
        for a, spa in enumerate(sp):
            for b, snb in enumerate(sn):
                c = _sigmoid(-(spa - snb) / T) / T
                cp[a] += c
                cn[b] += c
        grad = [0.0] * k
        for a, s in enumerate(pos):
            for j in range(k):
                grad[j] -= cp[a] * s[j]
        for b, s in enumerate(neg):
            for j in range(k):
                grad[j] += cn[b] * s[j]
        grad = [g / n_pairs for g in grad]
        # Proximal mirror step: the KL anchor is solved exactly,
        #   w <- argmin <grad, w> + KL(w || w_t)/eta + lambda * KL(w || w0)
        #   => log w ∝ (log w_t - eta*grad + eta*lambda*log w0) / (1 + eta*lambda),
        # which stays stable for any lambda (a plain gradient step diverges when eta*lambda is large).
        eta = settings.step
        logits = [
            (math.log(w[j]) - eta * grad[j] + eta * lam * math.log(w0[j])) / (1 + eta * lam) for j in range(k)
        ]
        top = max(logits)
        expd = [math.exp(x - top) for x in logits]
        total = math.fsum(expd)
        w = [x / total for x in expd]
    return w


def _summary(result: RankingResult, known: Sequence[str]) -> RankSummary:
    order = result.order()
    pos = {cid: i + 1 for i, cid in enumerate(order)}
    n = len(order)
    ranks = {k: pos.get(k) for k in known}
    tops = [r / n * 100 for r in ranks.values() if r is not None]
    return RankSummary(
        ranks=ranks,
        n_ranked=n,
        mean_top_percent=(math.fsum(tops) / len(tops)) if tops else None,
        in_top_10_percent=sum(1 for t in tops if t <= 10),
    )


def _profile_with_weights(
    profile: Profile, tuned: dict[str, float], dimension_of: dict[str, str], version: str, note: str
) -> Profile:
    """Profile whose effective weights equal ``tuned`` exactly.

    Internal weights a_j = w_j and dimension weights W_g = sum_{j in g} w_j,
    so W_g * a_j / sum_{k in g} a_k = w_j.
    """
    features = tuple(replace(f, weight=tuned.get(f.feature_id, 0.0)) for f in profile.features)
    dims: dict[str, float] = {}
    for f in profile.features:
        d = dimension_of[f.feature_id]
        dims[d] = dims.get(d, 0.0) + tuned.get(f.feature_id, 0.0)
    return replace(
        profile,
        version=version,
        calibration_status="provisional",
        features=features,
        dimension_weights=dims,
        description=((profile.description or "") + " " + note).strip(),
    )


# --------------------------------------------------------------------------- public API


def calibrate_weights(
    target: Any,
    candidates: Sequence[Any],
    profile: Any,
    feature_definitions: Any,
    known_analogs: Sequence[str],
    *,
    settings: CalibrationSettings | None = None,
    leave_one_out: bool = True,
    top_new: int = 10,
) -> CalibrationResult:
    settings = settings or CalibrationSettings()
    if not (settings.temperature > 0 and settings.step > 0 and settings.prior_strength >= 0 and settings.iterations >= 0):
        raise InvalidRequestError("invalid calibration settings", code="invalid_settings")
    target, profile = as_site(target), as_profile(profile)
    sites = [as_site(c) for c in candidates]
    ids = {s.id for s in sites}
    known = list(dict.fromkeys(known_analogs))
    unknown = [k for k in known if k not in ids]
    if unknown:
        raise InvalidRequestError(f"known analogs {unknown} are not among the candidates", code="unknown_candidate")
    if not known:
        raise InvalidRequestError("at least one known analog is needed", code="no_known_analogs")

    start = rank(target, sites, profile, feature_definitions)  # validates everything
    definitions = feature_definitions_by_id(feature_definitions)
    dimension_of = {f.feature_id: definitions[f.feature_id].dimension for f in profile.features}

    ranked = {e.result.candidate_id: e.result for e in start.ranked}
    unusable = {}
    for k in known:
        if k not in ranked:
            r = next(x for x in start.partial + start.excluded if x.candidate_id == k)
            unusable[k] = f"{r.category}: " + "; ".join(r.reasons)
    used = [k for k in known if k in ranked]

    tunable = [fid for fid, w in start.effective_weights.items() if w > 0]
    w0 = [start.effective_weights[f] for f in tunable]
    total0 = math.fsum(w0)
    w0 = [x / total0 for x in w0]
    sims = {
        cid: [next(c.similarity for c in r.components if c.feature_id == f) for f in tunable]
        for cid, r in ranked.items()
    }

    warnings: list[str] = []
    if len(used) < 5:
        warnings.append(
            f"only {len(used)} usable known analog(s): calibration is weak evidence; keep prior_strength high"
        )
    if unusable:
        warnings.append(f"known analogs not usable (not complete under this profile): {sorted(unusable)}")

    w = _optimise(sims, used, w0, settings) if used else list(w0)
    tuned = dict(zip(tunable, w))
    version = f"{profile.version}-cal"
    note = f"[weights calibrated on known analogs {used}]"
    calibrated_profile = _profile_with_weights(profile, tuned, dimension_of, version, note)
    calibrated = rank(target, sites, calibrated_profile, feature_definitions)

    loo: list[LeaveOneOut] = []
    if leave_one_out:
        if len(used) < 2:
            warnings.append("leave-one-out needs at least 2 usable known analogs; skipped")
        else:
            start_pos = {cid: i + 1 for i, cid in enumerate(start.order())}
            for held in used:
                others = [k for k in used if k != held]
                w_h = _optimise(sims, others, w0, settings)
                p_h = _profile_with_weights(profile, dict(zip(tunable, w_h)), dimension_of, f"{version}-loo", note)
                r_h = rank(target, sites, p_h, feature_definitions)
                pos_h = {cid: i + 1 for i, cid in enumerate(r_h.order())}
                loo.append(LeaveOneOut(held, start_pos[held], pos_h[held], len(start_pos)))

    new = []
    for e in calibrated.ranked:
        if e.result.candidate_id in known:
            continue
        new.append({
            "candidate_id": e.result.candidate_id,
            "position": e.position,
            "score": e.result.score_observed,
            "dimension_scores": {d.dimension: d.score_observed for d in e.result.dimensions},
        })
        if len(new) >= top_new:
            break

    def dim_weights(weights: dict[str, float]) -> dict[str, float]:
        out: dict[str, float] = {}
        for fid, wt in weights.items():
            out[dimension_of[fid]] = out.get(dimension_of[fid], 0.0) + wt
        return out

    return CalibrationResult(
        profile_id=profile.id,
        start_version=profile.version,
        calibrated_version=version,
        known_analogs_used=tuple(used),
        known_analogs_unusable=unusable,
        start_feature_weights=dict(start.effective_weights),
        calibrated_feature_weights=dict(calibrated.effective_weights),
        start_dimension_weights=dim_weights(start.effective_weights),
        calibrated_dimension_weights=dim_weights(calibrated.effective_weights),
        start_summary=_summary(start, known),
        calibrated_summary=_summary(calibrated, known),
        leave_one_out=tuple(loo),
        new_candidates=tuple(new),
        calibrated_profile=profile_to_dict(calibrated_profile),
        settings=settings,
        warnings=tuple(warnings),
    )
