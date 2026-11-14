"""Per-dimension breakdown and declared limitations (challenge: "an excellent
geological analog but a poor temperature analog")."""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from analogue_engine import InvalidRequestError, compare, rank

MIXED = Path(__file__).resolve().parents[1] / "examples" / "fixture_mixed_synthetic.json"


@pytest.fixture
def mixed():
    raw = json.loads(MIXED.read_text(encoding="utf-8"))
    sites = {s["id"]: s for s in raw["sites"]}
    return raw, sites


def test_overall_score_is_weighted_sum_of_dimension_scores_for_complete(mixed):
    raw, sites = mixed
    profile = raw["profiles"][0]
    for cid in ("synthetic_earth_E1", "synthetic_earth_E2", "synthetic_earth_E4"):
        r = compare(sites["synthetic_mars_reference"], sites[cid], profile, raw["feature_definitions"])
        assert r.category == "complete"
        total = math.fsum(d.dimension_weight * d.score_observed for d in r.dimensions)
        assert total == pytest.approx(r.score_observed, abs=1e-12)
        assert math.fsum(d.dimension_weight for d in r.dimensions) == pytest.approx(1.0)


def test_dimension_scores_show_what_is_similar_and_what_is_not(mixed):
    raw, sites = mixed
    r = compare(sites["synthetic_mars_reference"], sites["synthetic_earth_E1"], raw["profiles"][0], raw["feature_definitions"])
    dims = {d.dimension: d for d in r.dimensions}
    assert list(dims) == ["terrain", "thermal", "optical", "mineralogy", "water", "craters"]
    # terrain: (0.95 + 0.8 + 0.9) / 3
    assert dims["terrain"].score_observed == pytest.approx((0.95 + 0.8 + 0.9) / 3)
    # thermal: weights 1, 1, 2 -> (0.4 + 0 + 2 * 0.8333) / 4
    assert dims["thermal"].score_observed == pytest.approx((0.4 + 0.0 + 2 * (1 - 50 / 300)) / 4)
    # E1 is a strong mineralogy analog but a weak thermal analog in this synthetic case.
    assert dims["mineralogy"].score_observed > 0.9 > 0.6 > dims["thermal"].score_observed


def test_partial_candidate_dimension_coverage(mixed):
    raw, sites = mixed
    r = compare(sites["synthetic_mars_reference"], sites["synthetic_earth_E3"], raw["profiles"][0], raw["feature_definitions"])
    mineral = next(d for d in r.dimensions if d.dimension == "mineralogy")
    # composition (a=2) and presence (a=1) missing, rock type (a=1) compared
    assert mineral.coverage == pytest.approx(1 / 4)
    assert mineral.compared_features == ("rock_type",)
    assert mineral.score_observed == 1.0


def test_dimension_with_zero_weight_is_still_reported(mixed):
    raw, sites = mixed
    profile = raw["profiles"][0]
    profile["dimension_weights"]["craters"] = 0
    r = compare(sites["synthetic_mars_reference"], sites["synthetic_earth_E1"], profile, raw["feature_definitions"])
    craters = next(d for d in r.dimensions if d.dimension == "craters")
    assert craters.dimension_weight == 0.0
    assert craters.score_observed == pytest.approx(1 - 1 / 3)  # informational


def test_declared_limitations_pass_through(mixed):
    raw, sites = mixed
    others = [s for k, s in sorted(sites.items()) if k != "synthetic_mars_reference"]
    result = rank(sites["synthetic_mars_reference"], others, raw["profiles"][0], raw["feature_definitions"])
    assert any("Gravity" in x for x in result.declared_limitations)
    assert result.ranked[0].result.declared_limitations == result.declared_limitations
    json.loads(result.to_json())


def test_declared_limitations_must_be_strings(mixed):
    raw, sites = mixed
    raw["profiles"][0]["declared_limitations"] = ["ok", ""]
    with pytest.raises(InvalidRequestError):
        compare(sites["synthetic_mars_reference"], sites["synthetic_earth_E1"], raw["profiles"][0], raw["feature_definitions"])
