"""Regression tests for findings of the independent code review of v0.2."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from analogue_engine import AnalogueEngineError, InvalidRequestError, compare, load_bundle, load_sites_csv, rank
from analogue_engine.comparators import cosine
from analogue_engine.models import parse_value

MIXED = Path(__file__).resolve().parents[1] / "examples" / "fixture_mixed_synthetic.json"
BASE = {"basalt": 0.5, "clay": 0.2, "salts": 0.05, "iron_oxides": 0.25}


@pytest.mark.parametrize("scale", [1e-200, 1e-170, 1.0, 1e154, 1e200, 1e300])
def test_cosine_is_scale_invariant_without_overflow_or_underflow(scale):
    """V1-V3: huge or tiny amounts must neither raise nor break identity."""
    scaled = {k: v * scale for k, v in BASE.items()}
    assert cosine(BASE, scaled).similarity == pytest.approx(1.0)
    assert cosine(scaled, scaled).similarity == pytest.approx(1.0)


def test_cosine_huge_candidate_does_not_abort_ranking():
    raw = json.loads(MIXED.read_text(encoding="utf-8"))
    sites = {s["id"]: s for s in raw["sites"]}
    e1 = sites["synthetic_earth_E1"]
    m = next(x for x in e1["measurements"] if x["feature_id"] == "mineral_composition")
    m["value"] = {"basalt": 1.3e154, "clay": 1.3e154, "salts": 0, "iron_oxides": 0}
    target = sites.pop("synthetic_mars_reference")
    profile = raw["profiles"][0]
    result = rank(target, list(sites.values()), profile, raw["feature_definitions"])
    json.loads(result.to_json())  # still strict JSON


def _csv(tmp_path, rows, header="site_id,body,data_mode,feature_id,value,status,unit,method_id,method_version,spatial_support,uncertainty"):
    p = tmp_path / "x.csv"
    p.write_text(header + "\n" + "\n".join(rows) + "\n", encoding="utf-8")
    return p


def test_csv_bad_uncertainty_is_engine_error(tmp_path):
    """V4."""
    defs = load_bundle(MIXED).feature_definitions
    with pytest.raises(InvalidRequestError):
        load_sites_csv(_csv(tmp_path, ["s1,earth,real,slope_deg,1,valid,deg,m,0,sup,abc"]), defs)


@pytest.mark.parametrize(
    "fid, value",
    [
        ("mineral_composition", "basalt=0.5;basalt=0.1;clay=0;salts=0;iron_oxides=0"),  # duplicate key
        ("minerals_present", ";"),  # lone separator
        ("minerals_present", "basalt;;clay"),  # empty item
        ("mineral_composition", "basalt=0.5;clay"),  # missing '='
    ],
)
def test_csv_rejects_ambiguous_cells(tmp_path, fid, value):
    """V5: ambiguous encodings are errors, not silent reinterpretations."""
    defs = load_bundle(MIXED).feature_definitions
    with pytest.raises(InvalidRequestError):
        load_sites_csv(_csv(tmp_path, [f's1,earth,real,{fid},"{value}",valid,fraction,m,0,sup,']), defs)


@pytest.mark.parametrize("bad", ["a;b", "x=y", "[]", " pad"])
def test_vocabulary_cannot_contain_csv_separators(bad):
    """V5 root cause: names that cannot round-trip through CSV are rejected up front."""
    raw = json.loads(MIXED.read_text(encoding="utf-8"))
    d = next(x for x in raw["feature_definitions"] if x["id"] == "minerals_present")
    d["categories"] = d["categories"] + [bad]
    target = next(s for s in raw["sites"] if s["id"] == "synthetic_mars_reference")
    with pytest.raises(InvalidRequestError) as e:
        compare(target, target, raw["profiles"][0], raw["feature_definitions"])
    assert e.value.code == "invalid_categories"


def test_mixed_key_types_raise_engine_error():
    """V6."""
    with pytest.raises(AnalogueEngineError):
        parse_value({1: 0.5, "a": 0.2}, "x")
