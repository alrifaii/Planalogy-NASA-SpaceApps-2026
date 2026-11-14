"""Comparators beyond the scalar one (v0.2): categorical, boolean, log,
Jaccard, cosine, fixed-range min-max; and the mixed-kind fixture."""

from __future__ import annotations

import copy
import json
import math
from pathlib import Path

import pytest

from analogue_engine import (
    InvalidRequestError,
    ProfileError,
    compare,
    load_bundle,
    rank,
    sensitivity_analysis,
)
from analogue_engine.comparators import (
    COMPARATORS,
    boolean_match,
    categorical_match,
    clipped_linear,
    cosine,
    jaccard,
    log_ratio,
)

MIXED = Path(__file__).resolve().parents[1] / "examples" / "fixture_mixed_synthetic.json"


# ----------------------------------------------------------------- unit level


def test_every_comparator_returns_similarity_in_unit_interval_and_identity_one():
    samples = {
        "clipped_linear_v1": (3.0, 1.0),
        "log_ratio_v1": (3.0, 1.0),
        "categorical_match_v1": ("a", None),
        "boolean_match_v1": (True, None),
        "jaccard_v1": (("a", "b"), None),
        "cosine_v1": ({"a": 0.3, "b": 0.7}, None),
    }
    assert set(samples) == set(COMPARATORS)
    for cid, (value, tau) in samples.items():
        r = COMPARATORS[cid].fn(value, value, tau)
        assert r.similarity == 1.0 and r.normalized_discrepancy == 0.0, cid


def test_categorical_match():
    assert categorical_match("basalt", "basalt").similarity == 1.0
    assert categorical_match("basalt", "evaporite").similarity == 0.0


@pytest.mark.parametrize("t, c, s", [(True, True, 1.0), (False, False, 1.0), (True, False, 0.0), (False, True, 0.0)])
def test_boolean_match_counts_joint_absence_as_agreement(t, c, s):
    assert boolean_match(t, c).similarity == s


def test_log_ratio_is_symmetric_in_ratio_and_uses_decades():
    up = log_ratio(1.0, 10.0, 2.0)
    down = log_ratio(1.0, 0.1, 2.0)
    assert up.similarity == pytest.approx(0.5) and down.similarity == pytest.approx(0.5)
    assert up.detail["abs_log10_ratio"] == pytest.approx(1.0)
    assert log_ratio(1.0, 1000.0, 2.0).similarity == 0.0  # clipped
    assert up.delta == 9.0  # physical difference is still reported


@pytest.mark.parametrize("t, c", [(0.0, 1.0), (1.0, 0.0), (-1.0, 1.0)])
def test_log_ratio_rejects_non_positive_values(t, c):
    with pytest.raises(InvalidRequestError):
        log_ratio(t, c, 1.0)


def test_jaccard_ignores_joint_absence():
    r = jaccard(("basalt", "clay"), ("clay", "salts"))
    assert r.similarity == pytest.approx(1 / 3)
    assert r.detail["shared"] == ["clay"]
    assert jaccard((), ()).similarity == 1.0  # documented convention


def test_cosine_compares_proportions_not_amounts():
    a = {"basalt": 0.2, "clay": 0.1}
    assert cosine(a, {"basalt": 0.4, "clay": 0.2}).similarity == pytest.approx(1.0)
    assert cosine({"basalt": 1.0, "clay": 0.0}, {"basalt": 0.0, "clay": 1.0}).similarity == 0.0
    with pytest.raises(InvalidRequestError):
        cosine({"basalt": 0.0, "clay": 0.0}, a)


def test_fixed_range_minmax_equals_tau_and_min_cancels(fx):
    """(x-min)/(max-min) - (t-min)/(max-min) = (x-t)/(max-min): only the width matters."""
    fx.pfeature(fx.p1, "relief_m").pop("tau")
    fx.pfeature(fx.p1, "relief_m")["range"] = {"min": 0, "max": 100}
    a = compare(fx.target, fx.site("A"), fx.p1, fx.defs)
    fx.pfeature(fx.p1, "relief_m")["range"] = {"min": -500, "max": -400}
    b = compare(fx.target, fx.site("A"), fx.p1, fx.defs)
    assert a.score_observed == pytest.approx(0.82) and b.score_observed == a.score_observed


def test_tau_and_range_together_rejected(fx):
    fx.pfeature(fx.p1, "relief_m")["range"] = {"min": 0, "max": 100}
    with pytest.raises(ProfileError) as e:
        rank(fx.target, fx.candidates(), fx.p1, fx.defs)
    assert e.value.code == "tau_and_range"


# ----------------------------------------------------------------- mixed fixture


@pytest.fixture
def mixed():
    raw = json.loads(MIXED.read_text(encoding="utf-8"))
    return copy.deepcopy(raw)


def _parts(raw, profile_id="synthetic_mixed_rover"):
    sites = {s["id"]: s for s in raw["sites"]}
    target = sites.pop("synthetic_mars_reference")
    profile = next(p for p in raw["profiles"] if p["id"] == profile_id)
    return target, [sites[k] for k in sorted(sites)], profile, raw["feature_definitions"]


def test_mixed_fixture_ranks_and_separates(mixed):
    target, cands, profile, defs = _parts(mixed)
    result = rank(target, cands, profile, defs)
    assert result.order() == ["synthetic_earth_E1", "synthetic_earth_E4", "synthetic_earth_E2"]
    assert [r.candidate_id for r in result.partial] == ["synthetic_earth_E3"]
    e1 = result.ranked[0].result
    by = {c.feature_id: c for c in e1.components}
    assert by["mineral_composition"].similarity == pytest.approx(0.36 / math.sqrt(0.355 * 0.375))
    assert by["minerals_present"].similarity == pytest.approx(0.75)
    assert by["hydrogen_wt_pct"].similarity == pytest.approx(1 - math.log10(4) / 2)
    assert by["relief_m"].tau == 1000  # from range {0, 1000}
    assert by["rock_type"].delta is None  # no signed difference for categories
    json.loads(result.to_json())


def test_mixed_identity_is_one(mixed):
    target, _, profile, defs = _parts(mixed)
    r = compare(target, target, profile, defs)
    assert r.score_observed == 1.0 and r.coverage == 1.0


def test_equals_constraint_excludes_without_ice(mixed):
    target, cands, profile, defs = _parts(mixed, "synthetic_mixed_ice_required")
    result = rank(target, cands, profile, defs)
    assert result.order() == ["synthetic_earth_E4"]
    excluded = {r.candidate_id: r for r in result.excluded}
    assert excluded["synthetic_earth_E1"].category == "requirement_not_met"
    # E1 is more similar overall, but the requirement is not compensable.
    assert excluded["synthetic_earth_E1"].score_observed > result.ranked[0].result.score_observed


def test_mixed_catalogue_independence(mixed):
    target, cands, profile, defs = _parts(mixed)
    full = {e.result.candidate_id: e.result.score_observed for e in rank(target, cands, profile, defs).ranked}
    alone = rank(target, [cands[0]], profile, defs).ranked[0].result
    assert alone.score_observed == full[alone.candidate_id]


def test_sensitivity_skips_scale_free_comparators(mixed):
    target, cands, profile, defs = _parts(mixed)
    report = sensitivity_analysis(target, cands, profile, defs, 0.2)
    params = {p.parameter for p in report.perturbations}
    assert "tau:rock_type" not in params and "tau:mineral_composition" not in params
    assert "tau:hydrogen_wt_pct" in params


# ----------------------------------------------------------------- contract errors


def _def(mixed, fid):
    return next(d for d in mixed["feature_definitions"] if d["id"] == fid)


def _meas(site, fid):
    return next(m for m in site["measurements"] if m["feature_id"] == fid)


def test_category_outside_vocabulary_rejected(mixed):
    target, cands, profile, defs = _parts(mixed)
    _meas(cands[0], "rock_type")["value"] = "granite"
    with pytest.raises(InvalidRequestError) as e:
        rank(target, cands, profile, defs)
    assert e.value.code == "value_type_mismatch"


def test_composition_keys_must_match_vocabulary(mixed):
    target, cands, profile, defs = _parts(mixed)
    _meas(cands[0], "mineral_composition")["value"] = {"basalt": 1.0}
    with pytest.raises(InvalidRequestError) as e:
        rank(target, cands, profile, defs)
    assert "write 0 explicitly" in e.value.message


def test_negative_composition_rejected(mixed):
    target, cands, profile, defs = _parts(mixed)
    _meas(cands[0], "mineral_composition")["value"] = {"basalt": -0.1, "clay": 0, "salts": 0, "iron_oxides": 1}
    with pytest.raises(InvalidRequestError):
        rank(target, cands, profile, defs)


def test_tau_on_scale_free_comparator_rejected(mixed):
    target, cands, profile, defs = _parts(mixed)
    next(f for f in profile["features"] if f["feature_id"] == "rock_type").update(tau=1, tau_unit="category")
    with pytest.raises(ProfileError) as e:
        rank(target, cands, profile, defs)
    assert e.value.code == "tau_not_used"


def test_log_tau_must_be_in_decades(mixed):
    target, cands, profile, defs = _parts(mixed)
    next(f for f in profile["features"] if f["feature_id"] == "hydrogen_wt_pct")["tau_unit"] = "wt%"
    with pytest.raises(ProfileError) as e:
        rank(target, cands, profile, defs)
    assert e.value.code == "tau_unit_mismatch"


def test_comparator_must_match_kind(mixed):
    target, cands, profile, defs = _parts(mixed)
    _def(mixed, "rock_type")["comparator_id"] = "clipped_linear_v1"
    with pytest.raises(InvalidRequestError) as e:
        rank(target, cands, profile, defs)
    assert e.value.code == "comparator_kind_mismatch"


def test_zero_candidate_log_value_excludes_only_that_candidate(mixed):
    target, cands, profile, defs = _parts(mixed)
    _meas(cands[1], "crater_density_per_km2")["value"] = 0.0  # E2
    result = rank(target, cands, profile, defs)
    [e2] = [r for r in result.excluded if r.candidate_id == "synthetic_earth_E2"]
    comp = next(c for c in e2.components if c.feature_id == "crater_density_per_km2")
    assert comp.reason_code == "comparison_failed:non_positive_value"
    assert len(result.ranked) == 2


def test_target_value_that_cannot_be_compared_is_profile_error(mixed):
    target, cands, profile, defs = _parts(mixed)
    _meas(target, "mineral_composition")["value"] = {"basalt": 0, "clay": 0, "salts": 0, "iron_oxides": 0}
    with pytest.raises(ProfileError) as e:
        rank(target, cands, profile, defs)
    assert e.value.code == "target_value_not_comparable"


def test_equals_constraint_needs_matching_kind(mixed):
    target, cands, profile, defs = _parts(mixed)
    profile["constraints"] = [{"id": "bad", "feature_id": "relief_m", "type": "equals", "value": True}]
    with pytest.raises(ProfileError) as e:
        rank(target, cands, profile, defs)
    assert e.value.code == "constraint_kind_mismatch"
