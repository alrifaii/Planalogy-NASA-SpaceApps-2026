"""Rankings over years (year slider). All yearly data here is SYNTHETIC."""

from __future__ import annotations

import copy
import json

import pytest

from analogue_engine import InvalidRequestError, rank, rank_over_years


def _with_slope(fx, site_letter, slope, new_id=None):
    s = copy.deepcopy(fx.site(site_letter))
    if new_id:
        s["id"] = new_id
    fx.measurement(s, "slope_deg")["value"] = slope
    return s


@pytest.fixture
def years(fx):
    """A drifts away from the target over time, B drifts closer, C appears only later."""
    return {
        2025: [_with_slope(fx, "A", 12), _with_slope(fx, "B", 14), fx.site("D")],
        2050: [_with_slope(fx, "A", 16), _with_slope(fx, "B", 12), fx.site("D")],
        2075: [_with_slope(fx, "A", 19), _with_slope(fx, "B", 10), fx.site("D"),
               fx.new_site("synthetic_E", {"slope_deg": 10, "vrm": 0.04, "relief_m": 100})],
    }


def test_trajectories_gaining_losing_entering(fx, years):
    r = rank_over_years(fx.target, years, fx.p1, fx.defs, watch=["synthetic_A", "synthetic_B", "synthetic_E"], top_k=2)
    t = {x.candidate_id: x for x in r.watched}
    assert t["synthetic_A"].status == "losing" and t["synthetic_A"].trend_per_decade < 0
    assert t["synthetic_B"].status == "gaining" and t["synthetic_B"].trend_per_decade > 0
    assert t["synthetic_E"].status == "entering" and t["synthetic_E"].scores[2025] is None
    assert r.years == (2025, 2050, 2075)
    assert "synthetic_E" in r.emerging
    assert "synthetic_A" in r.fading or r.top_by_year[2075][0] != "synthetic_A"
    json.loads(r.to_json())


def test_each_year_score_equals_a_plain_rank(fx, years):
    """The timeline adds nothing to the math: each year is an ordinary ranking."""
    r = rank_over_years(fx.target, years, fx.p1, fx.defs, watch=["synthetic_B"])
    for y, sites in years.items():
        plain = rank(fx.target, sites, fx.p1, fx.defs)
        b = next(e.result for e in plain.ranked if e.result.candidate_id == "synthetic_B")
        assert r.watched[0].scores[y] == b.score_observed


def test_score_in_a_year_does_not_depend_on_other_sites(fx, years):
    """Adding a site in one year must not move anyone else's score (fixed scales)."""
    base = rank_over_years(fx.target, years, fx.p1, fx.defs, watch=["synthetic_B"])
    more = copy.deepcopy(years)
    more[2050].append(fx.new_site("synthetic_X", {"slope_deg": 80, "vrm": 0.9, "relief_m": 5000}))
    again = rank_over_years(fx.target, more, fx.p1, fx.defs, watch=["synthetic_B"])
    assert base.watched[0].scores == again.watched[0].scores


def test_stable_within_threshold(fx):
    ys = {2025: [fx.site("A")], 2030: [fx.site("A")]}
    r = rank_over_years(fx.target, ys, fx.p1, fx.defs, watch=["synthetic_A"])
    assert r.watched[0].status == "stable" and r.watched[0].change == 0.0


def test_input_errors(fx):
    with pytest.raises(InvalidRequestError):
        rank_over_years(fx.target, {}, fx.p1, fx.defs)
    with pytest.raises(InvalidRequestError):
        rank_over_years(fx.target, {"2025": [fx.site("A")]}, fx.p1, fx.defs)
    with pytest.raises(InvalidRequestError):
        rank_over_years(fx.target, {2025: [fx.site("A")]}, fx.p1, fx.defs, top_k=0)
