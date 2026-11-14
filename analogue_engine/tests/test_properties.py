"""Checks 5, 6, 7 and 9 of the brief: catalogue independence, monotonicity,
descriptor duplication, determinism and ties; plus weight normalisation."""

from __future__ import annotations

import copy
import itertools
import random

import pytest

from analogue_engine import ProfileError, compare, rank, restrict_profile, Profile
from analogue_engine.comparators import clipped_linear
from analogue_engine.resolution import compute_effective_weights
from analogue_engine.models import ProfileFeature


def score_map(result):
    out = {e.result.candidate_id: (e.result.score_observed, e.result.coverage) for e in result.ranked}
    out.update({r.candidate_id: (r.score_observed, r.coverage) for r in result.partial + result.excluded})
    return out


# ----------------------------------------------------------------- check 5: catalogue independence


@pytest.mark.parametrize("profile_name", ["p1", "p2"])
def test_adding_candidates_does_not_change_existing_scores(fx, profile_name):
    profile = getattr(fx, profile_name)
    before = score_map(rank(fx.target, fx.candidates(), profile, fx.defs))
    extremes = [
        fx.new_site("synthetic_E", {"slope_deg": 89.0, "vrm": 0.99, "relief_m": 9000.0}),
        fx.new_site("synthetic_F", {"slope_deg": 0.0, "vrm": 0.0, "relief_m": 0.0}),
        fx.new_site("synthetic_G", {"slope_deg": None, "vrm": 0.04, "relief_m": None}),
    ]
    after = score_map(rank(fx.target, fx.candidates() + extremes, profile, fx.defs))
    for cid, value in before.items():
        assert after[cid] == value  # exact equality: no catalogue-dependent scaling


def test_filtering_candidates_does_not_change_scores(fx):
    full = score_map(rank(fx.target, fx.candidates(), fx.p1, fx.defs))
    only_a = score_map(rank(fx.target, [fx.site("A")], fx.p1, fx.defs))
    assert only_a["synthetic_A"] == full["synthetic_A"]


def test_compare_equals_rank_entry(fx):
    single = compare(fx.target, fx.site("B"), fx.p2, fx.defs)
    ranked = rank(fx.target, fx.candidates(), fx.p2, fx.defs)
    entry = next(e.result for e in ranked.ranked if e.result.candidate_id == "synthetic_B")
    assert single == entry


# ----------------------------------------------------------------- check 6: monotonicity


def test_larger_discrepancy_never_improves_similarity():
    tau = 0.7
    t = 3.0
    offsets = [i * 0.05 for i in range(0, 60)]
    for sign in (+1, -1):
        sims = [clipped_linear(t, t + sign * o, tau).similarity for o in offsets]
        assert all(a >= b for a, b in zip(sims, sims[1:]))
        assert sims[0] == 1.0 and sims[-1] == 0.0
    # symmetric in sign of the difference
    assert clipped_linear(t, t + 0.3, tau).similarity == clipped_linear(t, t - 0.3, tau).similarity


def test_increasing_one_discrepancy_does_not_improve_component_or_score(fx):
    prev_s, prev_score = 2.0, 2.0
    for slope in [12, 13, 15, 18, 20, 25, 40, 100]:
        site = fx.new_site("synthetic_M", {"slope_deg": slope})
        r = compare(fx.target, site, fx.p1, fx.defs)
        s = r.components[0].similarity
        assert s <= prev_s and r.score_observed <= prev_score
        prev_s, prev_score = s, r.score_observed


def test_saturation_keeps_physical_difference(fx):
    a = compare(fx.target, fx.new_site("x", {"slope_deg": 25}), fx.p1, fx.defs).components[0]
    b = compare(fx.target, fx.new_site("y", {"slope_deg": 80}), fx.p1, fx.defs).components[0]
    assert a.similarity == b.similarity == 0.0
    assert a.abs_difference == 15 and b.abs_difference == 70


# ----------------------------------------------------------------- check 7: duplicated descriptor


def test_duplicating_descriptor_with_split_weight_preserves_score_and_coverage(fx):
    base = rank(fx.target, fx.candidates(), fx.p1, fx.defs)

    raw = copy.deepcopy(fx.raw)
    slope_def = copy.deepcopy(raw["feature_definitions"][0])
    slope_def["id"] = "slope_deg_copy"
    raw["feature_definitions"].append(slope_def)
    for s in raw["sites"]:
        m = copy.deepcopy(next(x for x in s["measurements"] if x["feature_id"] == "slope_deg"))
        m["feature_id"] = "slope_deg_copy"
        s["measurements"].append(m)
    p = next(p for p in raw["profiles"] if p["id"] == "synthetic_slope_priority")
    slope = next(f for f in p["features"] if f["feature_id"] == "slope_deg")
    slope["weight"] = 0.4
    p["features"].append({"feature_id": "slope_deg_copy", "weight": 0.4, "tau": 10, "tau_unit": "deg"})

    sites = {s["id"]: s for s in raw["sites"]}
    dup = rank(sites["synthetic_target"], [sites[f"synthetic_{x}"] for x in "ABCD"], p, raw["feature_definitions"])
    assert dup.order() == base.order()
    b, d = score_map(base), score_map(dup)
    for cid in b:
        assert d[cid][0] == pytest.approx(b[cid][0], abs=1e-12)
        assert d[cid][1] == pytest.approx(b[cid][1], abs=1e-12)


def test_engine_never_duplicates_a_feature_implicitly(fx):
    fx.p1["features"].append(copy.deepcopy(fx.p1["features"][0]))
    with pytest.raises(ProfileError) as e:
        rank(fx.target, fx.candidates(), fx.p1, fx.defs)
    assert e.value.code == "duplicate_active_feature"


def test_duplicate_feature_definitions_rejected(fx):
    fx.defs.append(copy.deepcopy(fx.defs[0]))
    with pytest.raises(Exception) as e:
        rank(fx.target, fx.candidates(), fx.p1, fx.defs)
    assert getattr(e.value, "code", "") == "duplicate_feature_definition"


# ----------------------------------------------------------------- check 9: determinism and ties


def test_repeated_request_gives_identical_output(fx):
    outputs = {rank(fx.target, fx.candidates(), fx.p1, fx.defs).to_json() for _ in range(5)}
    assert len(outputs) == 1


def test_candidate_input_order_does_not_change_ranking(fx):
    reference = rank(fx.target, fx.candidates(), fx.p2, fx.defs).to_json()
    for perm in itertools.permutations("ABCD"):
        assert rank(fx.target, fx.candidates("".join(perm)), fx.p2, fx.defs).to_json() == reference


def test_feature_order_in_profile_does_not_change_scores(fx):
    base = score_map(rank(fx.target, fx.candidates(), fx.p1, fx.defs))
    fx.p1["features"].reverse()
    rev = score_map(rank(fx.target, fx.candidates(), fx.p1, fx.defs))
    assert rev == base  # math.fsum is exactly rounded -> order independent


def test_ties_are_broken_by_id_and_reported(fx):
    twins = [
        fx.new_site("synthetic_twin_b", {}, base="A"),
        fx.new_site("synthetic_twin_a", {}, base="A"),
    ]
    result = rank(fx.target, [fx.site("A")] + twins, fx.p1, fx.defs)
    assert result.order() == ["synthetic_A", "synthetic_twin_a", "synthetic_twin_b"]
    assert set(result.ranked[0].tied_with) == {"synthetic_twin_a", "synthetic_twin_b"}
    assert any(w.startswith("ties_present") for w in result.warnings)


def test_floating_point_noise_does_not_break_ties(fx):
    # Mathematically equal similarity reached through different float paths.
    x = fx.new_site("synthetic_x", {"vrm": 0.04 + 0.03, "slope_deg": 10, "relief_m": 100})
    y = fx.new_site("synthetic_w", {"vrm": 0.04 - 0.03, "slope_deg": 10, "relief_m": 100})
    result = rank(fx.target, [x, y], fx.p1, fx.defs)
    assert result.order() == ["synthetic_w", "synthetic_x"]
    assert result.ranked[0].tied_with == ("synthetic_x",)


# ----------------------------------------------------------------- weights (section 4.3)


def _pf(fid, w):
    return ProfileFeature(fid, w, 1.0, "u")


def test_two_level_weights_normalise_within_each_level():
    feats = (_pf("a", 2), _pf("b", 2), _pf("c", 5))
    dims = {"a": "terrain", "b": "terrain", "c": "thermal"}
    w, W = compute_effective_weights(feats, dims, {"terrain": 3, "thermal": 1})
    assert W == {"terrain": 0.75, "thermal": 0.25}
    assert w == pytest.approx({"a": 0.375, "b": 0.375, "c": 0.25})


def test_dimension_with_more_variables_does_not_gain_weight():
    feats = tuple(_pf(f"t{i}", 1) for i in range(10)) + (_pf("h", 1),)
    dims = {**{f"t{i}": "terrain" for i in range(10)}, "h": "thermal"}
    w, _ = compute_effective_weights(feats, dims, {"terrain": 1, "thermal": 1})
    assert sum(v for k, v in w.items() if k.startswith("t")) == pytest.approx(0.5)
    assert w["h"] == pytest.approx(0.5)


def test_multiple_dimensions_require_explicit_dimension_weights():
    with pytest.raises(ProfileError) as e:
        compute_effective_weights((_pf("a", 1), _pf("c", 1)), {"a": "x", "c": "y"}, None)
    assert e.value.code == "dimension_weights_required"


def test_positive_dimension_with_zero_internal_sum_rejected():
    with pytest.raises(ProfileError) as e:
        compute_effective_weights((_pf("a", 0), _pf("c", 1)), {"a": "x", "c": "y"}, {"x": 1, "y": 1})
    assert e.value.code == "zero_internal_weight_sum"


def test_zero_weight_dimension_contributes_nothing():
    w, _ = compute_effective_weights((_pf("a", 0), _pf("c", 1)), {"a": "x", "c": "y"}, {"x": 0, "y": 1})
    assert w == {"a": 0.0, "c": 1.0}


def test_dimension_weights_must_match_active_dimensions():
    with pytest.raises(ProfileError) as e:
        compute_effective_weights((_pf("a", 1),), {"a": "x"}, {"x": 1, "ghost": 1})
    assert e.value.code == "dimension_weights_mismatch"


def test_unnormalised_weights_give_same_result_as_normalised(fx):
    base = score_map(rank(fx.target, fx.candidates(), fx.p1, fx.defs))
    for f, w in zip(fx.p1["features"], (8, 1, 1)):
        f["weight"] = w
    fx.p1["dimension_weights"] = {"terrain": 42}
    scaled = score_map(rank(fx.target, fx.candidates(), fx.p1, fx.defs))
    for cid in base:
        assert scaled[cid][0] == pytest.approx(base[cid][0], abs=1e-12)


def test_weights_are_fixed_before_candidate_availability(fx):
    """C's missing values must not renormalise the weights used for others."""
    result = rank(fx.target, fx.candidates(), fx.p1, fx.defs)
    assert result.effective_weights == pytest.approx({"slope_deg": 0.8, "vrm": 0.1, "relief_m": 0.1})
    for r in [e.result for e in result.ranked] + list(result.partial):
        assert [c.effective_weight for c in r.components] == pytest.approx([0.8, 0.1, 0.1])


# ----------------------------------------------------------------- explicit profile reduction


def test_restrict_profile_is_explicit_and_versioned(fx):
    p = Profile.from_dict(fx.p1)
    reduced = restrict_profile(p, ["slope_deg"], "0.1.0-slope-only", fx.defs)
    result = rank(fx.target, fx.candidates(), reduced, fx.defs)
    assert result.profile_version == "0.1.0-slope-only"
    assert result.order() == ["synthetic_B", "synthetic_C", "synthetic_A", "synthetic_D"]
    with pytest.raises(ProfileError):
        restrict_profile(p, ["slope_deg"], p.version, fx.defs)
    with pytest.raises(ProfileError) as e:
        restrict_profile(p, ["slope_deg"], "0.3")  # dimension_weights present, no definitions
    assert e.value.code == "feature_definitions_required"


def test_restrict_profile_cannot_drop_requirements(fx):
    fx.p1["required_features"] = ["vrm"]
    p = Profile.from_dict(fx.p1)
    with pytest.raises(ProfileError) as e:
        restrict_profile(p, ["slope_deg"], "0.2", fx.defs)
    assert e.value.code == "cannot_drop_requirement"


# ----------------------------------------------------------------- randomized invariants


def test_random_invariants(fx):
    rng = random.Random(20261114)
    for _ in range(300):
        values = {
            "slope_deg": rng.choice([None, rng.uniform(0, 60)]),
            "vrm": rng.choice([None, rng.uniform(0, 0.5)]),
            "relief_m": rng.choice([None, rng.uniform(0, 1000)]),
        }
        r = compare(fx.target, fx.new_site("rnd", values), fx.p2, fx.defs)
        assert 0.0 <= r.coverage <= 1.0
        if r.score_observed is not None:
            assert 0.0 <= r.score_observed <= 1.0
            assert sum(c.contribution or 0 for c in r.components) == pytest.approx(r.score_observed)
        else:
            assert r.coverage == 0.0
        assert r.rankable == all(v is not None for v in values.values())
