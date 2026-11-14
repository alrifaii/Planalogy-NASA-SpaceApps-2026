"""Bridge to the backend wide table and its 0-100 `similarity_scores`."""

from __future__ import annotations

import csv
import json
import math
from pathlib import Path

import pytest

from analogue_engine import InvalidRequestError, backend_payload, rank, sites_from_wide_records

BRIDGE = Path(__file__).resolve().parents[1] / "examples" / "backend_bridge"


@pytest.fixture
def cfg():
    return json.loads((BRIDGE / "bridge_config.json").read_text(encoding="utf-8"))


@pytest.fixture
def records():
    with (BRIDGE / "wide_locations_synthetic.csv").open(newline="", encoding="utf-8") as h:
        return list(csv.DictReader(h))


def _run(cfg, sites):
    profile = cfg["profiles"]["rover_testing"]
    target = sites[profile["target_id"]]
    others = [s for k, s in sorted(sites.items()) if k != target.id and s.body == "Earth"]
    return rank(target, others, profile, cfg["feature_definitions"])


def test_wide_csv_to_backend_scores(cfg, records):
    sites = sites_from_wide_records(records, cfg["column_specs"], cfg["feature_definitions"], data_mode="synthetic")
    payload = backend_payload(_run(cfg, sites))
    assert payload["ranked_order"] == ["E001", "E002", "E003"]
    assert payload["similarity_scores"]["E001"] == pytest.approx(100 * (0.7 * (0.8 + 0.9) / 2 + 0.3 * 1.0))
    assert all(0 <= v <= 100 for v in payload["similarity_scores"].values())
    # E004 has no geology: not in the scores dict, but reported with its reason.
    assert "E004" not in payload["similarity_scores"]
    assert payload["not_ranked"]["E004"]["category"] == "partial"
    assert payload["dimension_scores"]["E001"] == pytest.approx({"terrain": 85.0, "geology": 100.0})
    json.loads(json.dumps(payload, allow_nan=False))


def test_pandas_style_records_nan_is_missing_not_zero(cfg, records):
    """pandas gives float NaN for empty cells and numbers instead of strings."""
    pandas_like = []
    for r in records:
        row = dict(r)
        for col in ("terrain_slope", "surface_roughness", "latitude", "longitude", "temperature"):
            row[col] = float(row[col])
        if row["geology"] == "":
            row["geology"] = float("nan")
        pandas_like.append(row)
    sites = sites_from_wide_records(pandas_like, cfg["column_specs"], cfg["feature_definitions"], data_mode="synthetic")
    m = sites["E004"].measurements["rock_type"]
    assert m.value is None and m.status == "missing"
    from_csv = sites_from_wide_records(records, cfg["column_specs"], cfg["feature_definitions"], data_mode="synthetic")
    assert backend_payload(_run(cfg, sites)) == backend_payload(_run(cfg, from_csv))


def test_numeric_looking_category_stays_text(cfg, records):
    """Cells are decoded by feature kind, not guessed."""
    cfg["feature_definitions"][2]["categories"].append("1")
    records[0]["geology"] = "1"
    sites = sites_from_wide_records(records, cfg["column_specs"], cfg["feature_definitions"], data_mode="synthetic")
    assert sites["E001"].measurements["rock_type"].value == "1"


def test_missing_column_and_unknown_feature_rejected(cfg, records):
    bad = dict(cfg["column_specs"])
    bad["not_a_column"] = {"feature_id": "slope_deg", "unit": "deg"}
    with pytest.raises(InvalidRequestError):
        sites_from_wide_records(records, bad, cfg["feature_definitions"], data_mode="synthetic")
    bad = {"terrain_slope": {"feature_id": "nope", "unit": "deg"}}
    with pytest.raises(InvalidRequestError):
        sites_from_wide_records(records, bad, cfg["feature_definitions"], data_mode="synthetic")


def test_duplicate_location_rejected(cfg, records):
    records.append(dict(records[0]))
    with pytest.raises(InvalidRequestError):
        sites_from_wide_records(records, cfg["column_specs"], cfg["feature_definitions"], data_mode="synthetic")


def test_non_numeric_text_in_numeric_column_rejected(cfg, records):
    records[0]["terrain_slope"] = "steep"
    with pytest.raises(InvalidRequestError):
        sites_from_wide_records(records, cfg["column_specs"], cfg["feature_definitions"], data_mode="synthetic")
