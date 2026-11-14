"""Site cards (explain)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from analogue_engine import InvalidRequestError, compare, explain

MIXED = Path(__file__).resolve().parents[1] / "examples" / "fixture_mixed_synthetic.json"


def test_card_groups_categories_and_keeps_numbers(fx):
    r = compare(fx.target, fx.site("A"), fx.p1, fx.defs)
    card = explain(r)
    assert card["score_0_100"] == pytest.approx(82.0)
    assert card["coverage_pct"] == 100.0 and card["status"] == "complete"
    # single dimension 'terrain' scored (0.8*0.8+0.1*0.9+0.1*0.9)/1 = 0.82 -> strong match
    assert [m["category"] for m in card["matches"]] == ["terrain"]
    feats = {f["feature"]: f for f in card["matches"][0]["features"]}
    assert feats["slope_deg"]["similarity_0_100"] == pytest.approx(80.0)
    assert feats["slope_deg"]["target_value"] == 10.0 and feats["slope_deg"]["site_value"] == 12.0
    assert card["missing"] == [] and card["headline"].startswith("Strong match in terrain")


def test_card_for_partial_site_lists_missing_data(fx):
    card = explain(compare(fx.target, fx.site("C"), fx.p1, fx.defs))
    assert card["status"] == "partial" and not card["rankable"]
    assert {m["feature"] for m in card["missing"]} == {"vrm", "relief_m"}
    assert all(m["blocks_ranking"] for m in card["missing"])
    assert "missing data" in card["headline"]


def test_card_mismatch_and_thresholds(fx):
    card = explain(compare(fx.target, fx.site("D"), fx.p1, fx.defs))
    assert [m["category"] for m in card["mismatches"]] == ["terrain"]
    assert card["thresholds"]["strong_at_least"] == 0.75
    with pytest.raises(InvalidRequestError):
        explain(compare(fx.target, fx.site("D"), fx.p1, fx.defs), strong=0.3, weak=0.5)


def test_card_mixed_kinds_requirements_and_limitations():
    raw = json.loads(MIXED.read_text(encoding="utf-8"))
    sites = {s["id"]: s for s in raw["sites"]}
    profile = next(p for p in raw["profiles"] if p["id"] == "synthetic_mixed_ice_required")
    card = explain(compare(sites["synthetic_mars_reference"], sites["synthetic_earth_E1"], profile, raw["feature_definitions"]))
    assert card["status"] == "requirement_not_met"
    assert card["requirements"][0]["status"] == "violated"
    assert "fails requirement" in card["headline"]
    assert any("Gravity" in x for x in card["earth_cannot_reproduce"])
    groups = card["matches"] + card["partial_matches"] + card["mismatches"]
    assert {g["category"] for g in groups} == {"terrain", "thermal", "optical", "mineralogy", "water", "craters"}
    json.loads(json.dumps(card, allow_nan=False))


def test_zero_weight_dimension_is_reported_as_not_scored():
    raw = json.loads(MIXED.read_text(encoding="utf-8"))
    sites = {s["id"]: s for s in raw["sites"]}
    profile = raw["profiles"][0]
    profile["dimension_weights"]["craters"] = 0
    card = explain(compare(sites["synthetic_mars_reference"], sites["synthetic_earth_E1"], profile, raw["feature_definitions"]))
    assert [x["category"] for x in card["not_scored"]] == ["craters"]
