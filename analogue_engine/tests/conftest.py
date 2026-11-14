"""Shared helpers: load the synthetic fixture as plain dicts so each test can
mutate its own deep copy without affecting others."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

FIXTURE_PATH = Path(__file__).resolve().parents[1] / "examples" / "fixture_synthetic.json"


@pytest.fixture
def raw():
    """Deep copy of the fixture bundle as dicts."""
    return copy.deepcopy(json.loads(FIXTURE_PATH.read_text(encoding="utf-8")))


class Fx:
    """Convenience accessor over the raw fixture dicts."""

    def __init__(self, raw: dict):
        self.raw = raw
        self.defs = raw["feature_definitions"]
        self.sites = {s["id"]: s for s in raw["sites"]}
        self.profiles = {p["id"]: p for p in raw["profiles"]}

    @property
    def target(self):
        return self.sites["synthetic_target"]

    def site(self, letter: str):
        return self.sites[f"synthetic_{letter}"]

    def candidates(self, letters="ABCD"):
        return [self.site(x) for x in letters]

    @property
    def p1(self):
        return self.profiles["synthetic_slope_priority"]

    @property
    def p2(self):
        return self.profiles["synthetic_texture_priority"]

    def new_site(self, site_id: str, values: dict, base: str = "A"):
        """Clone candidate ``base`` with new id and overridden values (None -> missing)."""
        s = copy.deepcopy(self.site(base))
        s["id"] = site_id
        for m in s["measurements"]:
            if m["feature_id"] in values:
                v = values[m["feature_id"]]
                m["value"] = v
                m["status"] = "missing" if v is None else "valid"
        return s

    @staticmethod
    def measurement(site: dict, feature_id: str) -> dict:
        return next(m for m in site["measurements"] if m["feature_id"] == feature_id)

    @staticmethod
    def pfeature(profile: dict, feature_id: str) -> dict:
        return next(f for f in profile["features"] if f["feature_id"] == feature_id)


@pytest.fixture
def fx(raw):
    return Fx(raw)
