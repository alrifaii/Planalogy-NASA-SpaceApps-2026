"""
Planalogy - NASA Space Apps Challenge 2026

Module: Web Export
Purpose: Export what a static web page needs to rank every Earth cell against
any Mars cell in the browser, for any weights, preset or year.

The browser reproduces the engine exactly for this grid:
  * per-feature similarity with the engine's comparators and the fixed scales
    listed in the manifest (clipped linear: s = 1 - min(1, |x - t| / tau);
    categorical / boolean: 1 if equal else 0);
  * score = sum_j w_j s_j / sum_j w_j with the engine's effective weights,
    requirements and ordering (web/app/js/scoring.js).
Derived features (regional relief over 3x3 cells, thermal-inertia percentile
within each planet) are computed here, once per planet table, exactly as in
backend/grid_data.py. Values are exported unrounded so the browser gives the
engine's numbers bit for bit; a test checks it under Node.js.

Output (default web/app/data/planalogy/, read by the Planalogy web app):
  manifest.json              features (comparator, tau), categories, targets, presets, years, files
  earth.json                 every Earth land cell: id, lat, lon, feature values, dry_bare flag
  earth_<year>.json          per year: id + only the climate-dependent columns (YEAR_COLUMNS);
                             terrain, rock type and craters come from earth.json
  mars.json                  every Mars cell: lat, lon, feature values

    python -m backend.web_export [--data data/grid_1deg] [--out web/app/data/planalogy] [--no-calibration]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from analogue_engine import to_json

from backend import engine_service as es
from backend import grid_data as g
from backend.analog_presets import CELLS, EARTH, PRESETS, cell_id

FEATURES = ["regional_relief_m", "surface_temp_swing_K", "surface_temp_min_K", "ati_percentile",
            "albedo", "rock_group", "inside_impact_structure", "ground_ice_flag"]
LABELS = {
    "regional_relief_m": "Regional relief", "surface_temp_swing_K": "Day–night ground temperature swing",
    "surface_temp_min_K": "Coldest ground temperature", "ati_percentile": "Thermal inertia (rank within planet)",
    "albedo": "Albedo", "rock_group": "Rock type", "inside_impact_structure": "Impact structure",
    "ground_ice_flag": "Ground ice",
}
CATEGORY_LABELS = {"terrain": "Terrain", "thermal": "Day–night temperature", "thermophysical": "Thermal inertia",
                   "optical": "Albedo", "geology": "Rock type", "craters": "Impact structure", "water": "Ground ice"}
# Columns that change with climate (Science: "Future Mars analogs under climate change").
# Yearly files carry only these, so each year adds about a third of the base size.
YEAR_COLUMNS = ["surface_temp_swing_K", "surface_temp_min_K", "ati_percentile", "ground_ice_flag", "dry_bare"]

TARGET_KEYS = {"Gale Crater (Curiosity)": "gale", "Jezero Crater (Perseverance)": "jezero",
               "Arcadia Planitia (approx.)": "arcadia"}


def _feature_specs() -> list[dict[str, Any]]:
    defs = {d["id"]: d for d in g.feature_definitions()}
    out = []
    for f in FEATURES:
        d = defs[f]
        spec = {"id": f, "label": LABELS[f], "category": g.DIMENSION_OF[f], "kind": d["kind"],
                "comparator": d["comparator_id"], "unit": d["canonical_unit"]}
        if f in g.TAUS:
            spec["tau"] = g.TAUS[f][0]
        out.append(spec)
    return out


def _values(site: dict) -> list:
    vals = {m["feature_id"]: m["value"] for m in site["measurements"]}
    return [vals[f] for f in FEATURES]


def _earth_rows(data: dict) -> list[list]:
    """Every Earth land cell, with the dry/bare pre-filter as a flag (not a cut)."""
    rows = []
    for key, r in data["earth"].items():
        if r.get("is_land") != "1.0":
            continue
        site = g.cell_site("earth", data["earth"], key, data["earth_ati"])
        rows.append([site["id"], key[0], key[1]] + _values(site) + [g.passes_earth_filter(r)])
    return rows


def _mars_rows(data: dict) -> list[list]:
    rows = []
    for key in data["mars"]:
        site = g.cell_site("mars", data["mars"], key, data["mars_ati"])
        vals = _values(site)
        if any(v is not None for v in vals):
            rows.append([key[0], key[1]] + vals)
    return rows


def _write(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, allow_nan=False, separators=(",", ":")), encoding="utf-8")


def _preset_entry(preset: dict, data_dir: Path, calibrate: bool) -> dict[str, Any]:
    profile, info = es.preset_profile(preset["id"], data_dir, calibrate=calibrate)
    if not isinstance(profile, dict):
        from analogue_engine import profile_to_dict
        profile = profile_to_dict(profile)
    return {
        "id": preset["id"], "name": preset["name"], "mission": preset["mission"], "why": preset["why"],
        "target": TARGET_KEYS[preset["target"]],
        "category_weights": profile["dimension_weights"],
        "feature_weights": {f["feature_id"]: f["weight"] for f in profile["features"]},
        "requirements": [{"feature": c["feature_id"], "equals": c["value"], "id": c["id"]}
                         for c in profile.get("constraints", []) if c["type"] == "equals"],
        "required_features": profile.get("required_features", []),
        "weights_used": info.get("weights_used"), "verdict": info.get("verdict"),
        "verdict_reason": info.get("verdict_reason"),
        "known_analogs": [{"name": n, "id": cell_id("earth", *EARTH[n])} for n in preset["known_analogs"]],
        "declared_limitations": profile.get("declared_limitations", []),
    }


def export(data_dir: Path, out_dir: Path, calibrate: bool = True) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    years = [None] + [y for y, _ in es.yearly_files(data_dir)]
    base = es.load_grid(str(data_dir))
    files: dict[str, Any] = {"earth": {}, "mars": "mars.json"}
    _write(out_dir / "mars.json", {"columns": ["lat", "lon"] + FEATURES, "rows": _mars_rows(base)})
    full_cols = ["id", "lat", "lon"] + FEATURES + ["dry_bare"]
    for year in years:
        data = base if year is None else es.load_grid(str(data_dir), f"earth_1deg_{year}.csv")
        rows = _earth_rows(data)
        if year is None:
            name, payload = "earth.json", {"columns": full_cols, "rows": rows}
        else:
            keep = [full_cols.index(c) for c in ["id"] + YEAR_COLUMNS]
            name, payload = f"earth_{year}.json", {"columns": ["id"] + YEAR_COLUMNS, "base": "earth.json",
                                                   "rows": [[r[i] for i in keep] for r in rows]}
        _write(out_dir / name, payload)
        files["earth"][str(year or "now")] = name
    targets = []
    for n, (lat, lon) in CELLS.items():
        site = g.cell_site("mars", base["mars"], (lat, lon), base["mars_ati"])
        targets.append({"key": TARGET_KEYS[n], "name": n, "lat": lat, "lon": lon,
                        "values": dict(zip(FEATURES, _values(site)))})
    manifest = {
        "schema": "planalogy.web.v2",
        "model": "analogue_engine.adapted_gower@0.2.0",
        "data_mode": "real",
        "grid_deg": 1,
        "features": _feature_specs(),
        "categories": [{"id": c, "label": l} for c, l in CATEGORY_LABELS.items()],
        "targets": targets,
        "presets": [_preset_entry(p, data_dir, calibrate) for p in PRESETS],
        "years": ["now"] + [y for y in years if y is not None],
        "year_columns": YEAR_COLUMNS,
        "files": files,
        "dry_bare_rule": "precipitation < 500 mm/yr, NDVI < 0.2 (or unknown), not ice or water (provisional, Science)",
        "thresholds": {"strong_at_least": 75, "weak_at_most": 40},
        "common_limitations": g.COMMON_LIMITATIONS,
    }
    (out_dir / "manifest.json").write_text(to_json(manifest) + "\n", encoding="utf-8")
    for stale in out_dir.glob("sims_*.json"):
        stale.unlink()
    for stale in out_dir.glob("cells*.json"):
        stale.unlink()
    return manifest


def main(argv: list[str]) -> None:
    args = list(argv)
    data_dir, out_dir = es.GRID_DIR, es.PROJECT_ROOT / "web" / "app" / "data" / "planalogy"
    if "--data" in args:
        i = args.index("--data"); data_dir = Path(args[i + 1]); del args[i:i + 2]
    if "--out" in args:
        i = args.index("--out"); out_dir = Path(args[i + 1]); del args[i:i + 2]
    m = export(data_dir, out_dir, calibrate="--no-calibration" not in args)
    sizes = {p.name: p.stat().st_size for p in sorted(out_dir.glob("*.json"))}
    print(f"exported to {out_dir}: years {m['years']}; files {sizes}")


if __name__ == "__main__":
    main(sys.argv[1:])
