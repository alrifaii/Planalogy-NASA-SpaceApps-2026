"""Sensitivity analysis (section 8): +/-20% on each weight and each tau."""

from __future__ import annotations

import json

from analogue_engine import sensitivity_analysis


def test_fixture_rankings_are_stable_under_20_percent(fx):
    for profile in (fx.p1, fx.p2):
        report = sensitivity_analysis(fx.target, fx.candidates(), profile, fx.defs, 0.2)
        # 3 weights + 3 taus, each at 0.8 and 1.2
        assert len(report.perturbations) == 12
        assert report.unstable_parameters == []
        json.loads(report.to_json())


def test_detects_order_change_and_names_the_parameter(fx):
    # Two candidates built so the order hinges on the slope weight.
    e = fx.new_site("synthetic_E", {"slope_deg": 10, "vrm": 0.08, "relief_m": 160})  # s = 1, .6, .4
    f = fx.new_site("synthetic_F", {"slope_deg": 11.2, "vrm": 0.04, "relief_m": 100})  # s = .88, 1, 1
    # p1: E = .8 + .06 + .04 = .90 ; F = .704 + .1 + .1 = .904  -> F, E (close)
    report = sensitivity_analysis(fx.target, [e, f], fx.p1, fx.defs, 0.2)
    assert report.baseline_order == ("synthetic_F", "synthetic_E")
    flips = [p for p in report.perturbations if p.order_changed]
    assert flips, "expected at least one flip"
    assert all(p.moved for p in flips)
    assert "weight:slope_deg" in report.unstable_parameters
