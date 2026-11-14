"""Check 1-2 of the brief (section 8): the acceptance fixture, identity,
C partial (null is never zero), D complete with real discrepancies."""

from __future__ import annotations

import pytest

from analogue_engine import compare, rank

APPROX = dict(abs=1e-12)


def scores(result):
    return {e.result.candidate_id: e.result.score_observed for e in result.ranked}


def test_profile_slope_priority_reproduces_B_A_D(fx):
    result = rank(fx.target, fx.candidates(), fx.p1, fx.defs)
    assert result.order() == ["synthetic_B", "synthetic_A", "synthetic_D"]
    s = scores(result)
    assert s["synthetic_A"] == pytest.approx(0.82, **APPROX)
    assert s["synthetic_B"] == pytest.approx(0.91, **APPROX)
    assert s["synthetic_D"] == 0.0


def test_profile_texture_priority_reproduces_A_B_D(fx):
    result = rank(fx.target, fx.candidates(), fx.p2, fx.defs)
    assert result.order() == ["synthetic_A", "synthetic_B", "synthetic_D"]
    s = scores(result)
    assert s["synthetic_A"] == pytest.approx(0.88, **APPROX)
    assert s["synthetic_B"] == pytest.approx(0.64, **APPROX)
    assert s["synthetic_D"] == 0.0


def test_component_similarities_match_hand_calculation(fx):
    expected = {
        "A": (0.8, 0.9, 0.9),
        "B": (1.0, 0.6, 0.5),
        "D": (0.0, 0.0, 0.0),
    }
    for letter, sims in expected.items():
        r = compare(fx.target, fx.site(letter), fx.p1, fx.defs)
        got = tuple(c.similarity for c in r.components)
        assert got == pytest.approx(sims, **APPROX), letter


def test_hand_example_A_slope(fx):
    """2 degrees of difference / tau 10 = 0.2 discrepancy -> similarity 0.8."""
    r = compare(fx.target, fx.site("A"), fx.p1, fx.defs)
    slope = r.components[0]
    assert slope.feature_id == "slope_deg"
    assert slope.delta == 2.0 and slope.abs_difference == 2.0
    assert slope.normalized_discrepancy == pytest.approx(0.2)
    assert slope.similarity == pytest.approx(0.8)
    assert slope.contribution == pytest.approx(0.64)
    assert sum(c.contribution for c in r.components) == pytest.approx(r.score_observed, **APPROX)


@pytest.mark.parametrize("profile_name, coverage", [("p1", 0.8), ("p2", 0.2)])
def test_C_is_partial_never_ranked_and_null_is_not_zero(fx, profile_name, coverage):
    profile = getattr(fx, profile_name)
    result = rank(fx.target, fx.candidates(), profile, fx.defs)
    assert "synthetic_C" not in result.order()
    [c] = result.partial
    assert c.candidate_id == "synthetic_C"
    assert c.category == "partial" and not c.rankable
    assert c.score_observed == 1.0
    assert c.coverage == pytest.approx(coverage, **APPROX)
    missing = [comp for comp in c.components if comp.status != "compared"]
    assert {m.feature_id for m in missing} == {"vrm", "relief_m"}
    for m in missing:
        assert m.similarity is None and m.contribution is None and m.candidate_value is None
        assert m.blocking and m.reason_code == "value_missing"
        assert m.effective_weight > 0  # original weight kept for transparency
    # C would have topped the list (S_obs = 1) if it were ranked.
    assert c.score_observed > max(scores(result).values())


def test_D_has_real_discrepancies_not_missing_data(fx):
    r = compare(fx.target, fx.site("D"), fx.p1, fx.defs)
    assert r.category == "complete" and r.rankable
    assert r.coverage == 1.0 and r.score_observed == 0.0
    deltas = {c.feature_id: c.delta for c in r.components}
    assert deltas["slope_deg"] == pytest.approx(20)
    assert deltas["vrm"] == pytest.approx(0.16)
    assert deltas["relief_m"] == pytest.approx(200)
    # Saturated similarity but distinct physical differences remain visible.
    assert all(c.normalized_discrepancy == 1.0 for c in r.components)


@pytest.mark.parametrize("profile_name", ["p1", "p2"])
def test_identity_has_score_and_coverage_exactly_one(fx, profile_name):
    r = compare(fx.target, fx.target, getattr(fx, profile_name), fx.defs)
    assert r.score_observed == 1.0
    assert r.coverage == 1.0
    assert all(c.delta == 0.0 for c in r.components)
