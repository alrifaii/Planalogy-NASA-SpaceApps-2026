"""
Planeology - NASA Space Apps Challenge 2026

Module: Engine Service
Purpose: Connect the analogue engine (similarity model) to the app. Run a
mission preset on the Data team's 1-degree grid and return everything the
frontend needs in one JSON payload: ranked sites with site cards, a heat map
of every scored cell, map points, the calibration verdict, declared
limitations and, when yearly Earth files exist, the year slider.

Data: data/grid_1deg/ (earth_1deg.csv, mars_1deg.csv, parameters.csv).
Yearly files for the slider: data/grid_1deg/earth_1deg_<year>.csv.

Command line:
    python -m backend.engine_service                  # all presets
    python -m backend.engine_service rover_navigation --top 20
    python -m backend.engine_service --data <folder> --years
Writes data/results/<preset>.json (and <preset>_years.json).
"""

from __future__ import annotations

import json
import re
import sys
import time
from functools import lru_cache
from pathlib import Path
from typing import Any

from analogue_engine import calibrate_weights, explain, rank, rank_over_years, to_json

from backend import grid_data as g
from backend.analog_presets import CELLS, EARTH, PRESETS, build_profile, cell_id

PROJECT_ROOT = Path(__file__).resolve().parents[1]
GRID_DIR = PROJECT_ROOT / "data" / "grid_1deg"
PROFILE_CACHE = PROJECT_ROOT / "data" / "preset_profiles.json"
RESULTS_DIR = PROJECT_ROOT / "data" / "results"


class DataNotFound(RuntimeError):
    """The grid files are not where the service expects them."""


# --------------------------------------------------------------------------- data


def _check_dir(data_dir: Path) -> None:
    missing = [f for f in ("earth_1deg.csv", "mars_1deg.csv") if not (data_dir / f).exists()]
    if missing:
        raise DataNotFound(
            f"{missing} not found in {data_dir}. Put the Data team's grid in data/grid_1deg/ "
            "(branch data-grid-1deg) or pass --data <folder>."
        )


@lru_cache(maxsize=8)
def load_grid(data_dir: str, earth_file: str = "earth_1deg.csv") -> dict[str, Any]:
    """Load and prepare the grid once per (folder, Earth file); about 3 s."""
    path = Path(data_dir)
    _check_dir(path)
    return g.build(path, earth_file)


def yearly_files(data_dir: Path) -> list[tuple[int, str]]:
    found = []
    for p in data_dir.glob("earth_1deg_*.csv"):
        m = re.fullmatch(r"earth_1deg_(\d{4})\.csv", p.name)
        if m:
            found.append((int(m.group(1)), p.name))
    return sorted(found)


# --------------------------------------------------------------------------- presets


def list_presets() -> list[dict[str, Any]]:
    """Metadata for the preset buttons."""
    return [
        {"id": p["id"], "name": p["name"], "mission": p["mission"], "target": p["target"],
         "target_cell": dict(zip(("lat", "lon"), CELLS[p["target"]])), "why": p["why"],
         "known_analogs": p["known_analogs"]}
        for p in PRESETS
    ]


def _preset(preset_id: str) -> dict[str, Any]:
    for p in PRESETS:
        if p["id"] == preset_id:
            return p
    raise ValueError(f"Unknown preset '{preset_id}'. Available: {[p['id'] for p in PRESETS]}")


def _target(preset: dict[str, Any], data: dict[str, Any]) -> dict[str, Any]:
    lat, lon = CELLS[preset["target"]]
    return g.cell_site("mars", data["mars"], (lat, lon), data["mars_ati"])


def preset_profile(
    preset_id: str,
    data_dir: Path = GRID_DIR,
    *,
    calibrate: bool = True,
    cache_file: Path | None = PROFILE_CACHE,
    refresh: bool = False,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Profile to use for a preset, plus calibration info.

    Calibration (about 20 s) is cached in data/preset_profiles.json. The
    calibrated weights are used only if they pass the engine's validation gate
    (hidden known analogs must improve); otherwise Science's weights are used.
    """
    preset = _preset(preset_id)
    start = build_profile(preset)
    if not calibrate:
        return start, {"weights_used": "science (start)", "verdict": "not_run", "verdict_reason": "calibration off"}

    cache: dict[str, Any] = {}
    if cache_file is not None and cache_file.exists() and not refresh:
        cache = json.loads(cache_file.read_text(encoding="utf-8"))
        hit = cache.get(preset_id)
        if hit and hit.get("start_version") == start["version"]:
            return hit["profile"], hit["info"]

    data = load_grid(str(data_dir))
    target = _target(preset, data)
    ids = {s["id"] for s in data["earth_sites"]}
    known = [cell_id("earth", *EARTH[n]) for n in preset["known_analogs"]]
    present = [k for k in known if k in ids]
    if not present:
        info = {"weights_used": "science (start)", "verdict": "not_validated",
                "verdict_reason": "none of the known analogs are among the candidate cells"}
        return start, info
    cal = calibrate_weights(target, data["earth_sites"], start, g.feature_definitions(), present)
    names = {cell_id("earth", *v): k for k, v in EARTH.items()}
    info = {
        "weights_used": "calibrated" if cal.verdict == "accepted" else "science (start)",
        "verdict": cal.verdict, "verdict_reason": cal.verdict_reason,
        "start_category_weights": cal.start_dimension_weights,
        "calibrated_category_weights": cal.calibrated_dimension_weights,
        "known_analog_ranks_start": {names.get(c, c): r for c, r in cal.start_summary.ranks.items()},
        "known_analog_ranks_calibrated": {names.get(c, c): r for c, r in cal.calibrated_summary.ranks.items()},
        "leave_one_out": [{"held_out": names.get(r.held_out, r.held_out), "start": r.rank_with_start_weights,
                           "calibrated_without_it": r.rank_with_calibrated_weights} for r in cal.leave_one_out],
        "warnings": list(cal.warnings),
    }
    profile = cal.recommended_profile
    if cache_file is not None:
        cache[preset_id] = {"start_version": start["version"], "profile": profile, "info": info}
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(to_json(cache) + "\n", encoding="utf-8")
    return profile, info


# --------------------------------------------------------------------------- runs


def _latlon(cid: str) -> tuple[float, float]:
    _, la, lo = cid.split("_")
    return float(la), float(lo)


def run_preset(
    preset_id: str,
    *,
    data_dir: Path = GRID_DIR,
    top_n: int = 20,
    calibrate: bool = True,
    cache_file: Path | None = PROFILE_CACHE,
) -> dict[str, Any]:
    """Rank all dry, bare Earth cells for one mission preset."""
    preset = _preset(preset_id)
    data = load_grid(str(data_dir))
    target = _target(preset, data)
    profile, info = preset_profile(preset_id, data_dir, calibrate=calibrate, cache_file=cache_file)
    result = rank(target, data["earth_sites"], profile, g.feature_definitions())
    known = {cell_id("earth", *v): k for k, v in EARTH.items()}

    sites = []
    for e in result.ranked[:top_n]:
        card = explain(e.result)
        lat, lon = _latlon(e.result.candidate_id)
        card.update({"position": e.position, "lat": lat, "lon": lon, "known_analog": known.get(e.result.candidate_id)})
        sites.append(card)

    heatmap = [[*_latlon(e.result.candidate_id), round(100 * e.result.score_observed, 1)] for e in result.ranked]
    map_points = {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "geometry": {"type": "Point", "coordinates": [s["lon"], s["lat"]]},
             "properties": {"position": s["position"], "score": s["score_0_100"], "headline": s["headline"],
                            "known_analog": s["known_analog"]}}
            for s in sites
        ],
    }
    lat, lon = CELLS[preset["target"]]
    return {
        "project": "Planeology",
        "preset": {k: preset[k] for k in ("id", "name", "mission", "why")},
        "target": {"name": preset["target"], "body": "Mars", "lat": lat, "lon": lon},
        "calibration": info,
        "profile_used": profile,
        "counts": {"ranked": len(result.ranked), "partial": len(result.partial), "excluded": len(result.excluded)},
        "sites": sites,
        "heatmap": {"columns": ["lat", "lon", "score_0_100"], "cell_size_deg": 1, "rows": heatmap},
        "map_data": map_points,
        "declared_limitations": list(result.declared_limitations),
        "warnings": list(result.warnings),
        "data_mode": result.data_mode,
        "model": f"{result.model_id}@{result.model_version}",
        "validation_status": "Preliminary - requires validation",
    }


def run_preset_over_years(
    preset_id: str,
    *,
    data_dir: Path = GRID_DIR,
    top_k: int = 20,
    calibrate: bool = True,
    cache_file: Path | None = PROFILE_CACHE,
) -> dict[str, Any]:
    """Year slider: same preset and profile against each yearly Earth file."""
    years = yearly_files(data_dir)
    if len(years) < 2:
        return {"preset": preset_id, "years": [y for y, _ in years],
                "message": "Put at least two earth_1deg_<year>.csv files in the data folder to use the year slider."}
    preset = _preset(preset_id)
    profile, info = preset_profile(preset_id, data_dir, calibrate=calibrate, cache_file=cache_file)
    base = load_grid(str(data_dir))
    target = _target(preset, base)
    sites_by_year = {y: load_grid(str(data_dir), f)["earth_sites"] for y, f in years}
    watch = [cell_id("earth", *EARTH[n]) for n in preset["known_analogs"]]
    tl = rank_over_years(target, sites_by_year, profile, g.feature_definitions(), watch=watch, top_k=top_k)
    out = json.loads(tl.to_json())
    out["preset"] = preset_id
    out["calibration"] = info
    return out


def export(payload: dict[str, Any], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(to_json(payload) + "\n", encoding="utf-8")
    return path


# --------------------------------------------------------------------------- CLI


def main(argv: list[str]) -> None:
    args = list(argv)
    data_dir = GRID_DIR
    top_n = 20
    if "--data" in args:
        i = args.index("--data")
        data_dir = Path(args[i + 1])
        del args[i:i + 2]
    if "--top" in args:
        i = args.index("--top")
        top_n = int(args[i + 1])
        del args[i:i + 2]
    with_years = "--years" in args
    no_cal = "--no-calibration" in args
    ids = [a for a in args if not a.startswith("--")] or [p["id"] for p in PRESETS]

    for pid in ids:
        t0 = time.time()
        payload = run_preset(pid, data_dir=data_dir, top_n=top_n, calibrate=not no_cal)
        path = export(payload, RESULTS_DIR / f"{pid}.json")
        best = payload["sites"][0] if payload["sites"] else None
        print(f"{pid}: {payload['counts']['ranked']} ranked, weights {payload['calibration']['weights_used']}, "
              f"#1 {best['lat']:+.1f},{best['lon']:+.1f} score {best['score_0_100']} ({time.time() - t0:.0f}s) -> {path.name}")
        if with_years:
            yp = export(run_preset_over_years(pid, data_dir=data_dir, calibrate=not no_cal),
                        RESULTS_DIR / f"{pid}_years.json")
            print(f"  years -> {yp.name}")


if __name__ == "__main__":
    main(sys.argv[1:])
