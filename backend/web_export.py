"""
Planalogy - NASA Space Apps Challenge 2026

Module: Web Export
Purpose: Precompute everything a static web page needs to rank every Earth
cell in the browser, for any weights, preset or year.

The engine score of a complete cell is linear in the effective weights:
    score = sum_j w_j * s_j / sum_j w_j
The per-feature similarities s_j do not depend on the weights, so they are
computed here once per (Mars target, Earth cell, year) and the browser only
multiplies and adds (see web/app/js/scoring.js). Scales, comparators and data stay
fixed by the engine; the browser cannot change them.

Output (default web/app/data/planalogy/, read by the Planalogy web app):
  manifest.json            features, categories, targets, presets, years, files
  cells[_<year>].json      one row per dry, bare Earth cell: id, lat, lon, raw values
  sims_<target>[_<year>].json   per-cell similarity to that Mars target, per feature

    python -m backend.web_export [--data data/grid_1deg] [--out web/app/data/planalogy] [--no-calibration]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from analogue_engine import rank, to_json

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
TARGET_KEYS = {"Gale Crater (Curiosity)": "gale", "Jezero Crater (Perseverance)": "jezero",
               "Arcadia Planitia (approx.)": "arcadia"}
DECIMALS = 8


def _all_features_profile(target_id: str) -> dict[str, Any]:
    """Every feature active with weight 1, so every similarity is computed."""
    return g.make_profile("export_all_features", target_id, {d: 1 for d in set(g.DIMENSION_OF.values())},
                          {f: 1 for f in FEATURES}, description="Export: all features active.")


def _similarities(target: dict, sites: list[dict]) -> dict[str, list]:
    result = rank(target, sites, _all_features_profile(target["id"]), g.feature_definitions())
    out = {}
    for r in [e.result for e in result.ranked] + list(result.partial) + list(result.excluded):
        by = {c.feature_id: c.similarity for c in r.components}
        out[r.candidate_id] = [None if by[f] is None else round(by[f], DECIMALS) for f in FEATURES]
    return out


def _cells(sites: list[dict]) -> list[list]:
    rows = []
    for s in sites:
        _, la, lo = s["id"].split("_")
        vals = {m["feature_id"]: m["value"] for m in s["measurements"]}
        rows.append([s["id"], float(la), float(lo)] + [
            (round(v, 4) if isinstance(v, float) else v) for v in (vals[f] for f in FEATURES)])
    return rows


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
    files: dict[str, Any] = {"cells": {}, "sims": {}}
    years = [None] + [y for y, _ in es.yearly_files(data_dir)]
    base = es.load_grid(str(data_dir))
    targets = []
    for name, (lat, lon) in CELLS.items():
        key = TARGET_KEYS[name]
        t = g.cell_site("mars", base["mars"], (lat, lon), base["mars_ati"])
        targets.append({"key": key, "name": name, "lat": lat, "lon": lon, "id": t["id"],
                        "values": {m["feature_id"]: m["value"] for m in t["measurements"]}})
    for year in years:
        earth_file = "earth_1deg.csv" if year is None else f"earth_1deg_{year}.csv"
        data = es.load_grid(str(data_dir), earth_file)
        suffix = "" if year is None else f"_{year}"
        cells_name = f"cells{suffix}.json"
        (out_dir / cells_name).write_text(json.dumps({"columns": ["id", "lat", "lon"] + FEATURES,
                                                      "rows": _cells(data["earth_sites"])}, allow_nan=False,
                                                     separators=(",", ":")), encoding="utf-8")
        files["cells"][str(year or "now")] = cells_name
        for t in targets:
            target = g.cell_site("mars", data["mars"], (t["lat"], t["lon"]), data["mars_ati"])
            sims = _similarities(target, data["earth_sites"])
            sims_name = f"sims_{t['key']}{suffix}.json"
            (out_dir / sims_name).write_text(json.dumps({"columns": FEATURES, "by_id": sims}, allow_nan=False,
                                                        separators=(",", ":")), encoding="utf-8")
            files["sims"].setdefault(t["key"], {})[str(year or "now")] = sims_name
    manifest = {
        "schema": "planalogy.web.v1",
        "model": "analogue_engine.adapted_gower@0.2.0",
        "data_mode": "real",
        "note": "Similarities precomputed by the analogue engine; the browser only applies weights.",
        "features": [{"id": f, "label": LABELS[f], "category": g.DIMENSION_OF[f]} for f in FEATURES],
        "categories": [{"id": c, "label": l} for c, l in CATEGORY_LABELS.items()],
        "targets": targets,
        "presets": [_preset_entry(p, data_dir, calibrate) for p in PRESETS],
        "years": ["now"] + [y for y in years if y is not None],
        "files": files,
        "thresholds": {"strong_at_least": 75, "weak_at_most": 40},
        "common_limitations": g.COMMON_LIMITATIONS,
    }
    (out_dir / "manifest.json").write_text(to_json(manifest) + "\n", encoding="utf-8")
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
