"""Long-format CSV loader for the data team (v0.2)."""

from __future__ import annotations

from pathlib import Path

import pytest

from analogue_engine import InvalidRequestError, load_bundle, load_sites_csv, rank, write_sites_csv

ROOT = Path(__file__).resolve().parents[1]
MIXED = ROOT / "examples" / "fixture_mixed_synthetic.json"
TEMPLATE = ROOT / "examples" / "templates" / "measurements_template.csv"


def test_csv_round_trip_gives_identical_ranking(tmp_path):
    bundle = load_bundle(MIXED)
    path = tmp_path / "sites.csv"
    write_sites_csv(bundle.sites.values(), path)
    sites = load_sites_csv(path, bundle.feature_definitions)
    assert sites == bundle.sites
    profile = bundle.profiles["synthetic_mixed_rover"]
    target = sites["synthetic_mars_reference"]
    others = [s for k, s in sorted(sites.items()) if k != target.id]
    from_csv = rank(target, others, profile, bundle.feature_definitions).to_json()
    from_json = rank(
        bundle.sites[target.id], [s for k, s in sorted(bundle.sites.items()) if k != target.id],
        profile, bundle.feature_definitions,
    ).to_json()
    assert from_csv == from_json


def test_shipped_template_loads():
    bundle = load_bundle(MIXED)
    sites = load_sites_csv(TEMPLATE, bundle.feature_definitions)
    assert "synthetic_mars_reference" in sites


def _write(tmp_path, rows):
    header = "site_id,body,data_mode,feature_id,value,status,unit,method_id,method_version,spatial_support\n"
    p = tmp_path / "x.csv"
    p.write_text(header + "\n".join(rows) + "\n", encoding="utf-8")
    return p


def test_csv_rejects_bad_number_and_unknown_feature(tmp_path):
    defs = load_bundle(MIXED).feature_definitions
    with pytest.raises(InvalidRequestError):
        load_sites_csv(_write(tmp_path, ["s1,earth,real,slope_deg,abc,valid,deg,m,0,sup"]), defs)
    with pytest.raises(InvalidRequestError):
        load_sites_csv(_write(tmp_path, ["s1,earth,real,nope,1,valid,deg,m,0,sup"]), defs)
    with pytest.raises(InvalidRequestError):
        load_sites_csv(_write(tmp_path, ["s1,earth,real,slope_deg,nan,valid,deg,m,0,sup"]), defs)


def test_csv_empty_value_is_missing_not_zero(tmp_path):
    defs = load_bundle(MIXED).feature_definitions
    sites = load_sites_csv(_write(tmp_path, ["s1,earth,real,slope_deg,,missing,deg,m,0,sup"]), defs)
    m = sites["s1"].measurements["slope_deg"]
    assert m.value is None and m.status == "missing"


def test_csv_inconsistent_site_columns_rejected(tmp_path):
    defs = load_bundle(MIXED).feature_definitions
    rows = ["s1,earth,real,slope_deg,1,valid,deg,m,0,sup", "s1,mars,real,vrm,0.1,valid,1,m,0,sup"]
    with pytest.raises(InvalidRequestError) as e:
        load_sites_csv(_write(tmp_path, rows), defs)
    assert e.value.code == "inconsistent_site"
