"""Run every mission preset: rank, calibrate on its known analogs, and (if
yearly Earth files exist) track gaining/losing analogs over the years.

    python examples/real_data/run_presets.py <data_dir> [--no-calibration]

Yearly files: put earth_1deg_<year>.csv (same columns and grid) next to
earth_1deg.csv; they are detected automatically and ranked with each
preset's calibrated profile.

Writes examples/real_data/output_presets.json: for each preset the target,
start and calibrated weights, known-analog ranks, leave-one-out check, top
sites (lat/lon, score, per-category scores), the calibrated profile, and the
per-year results when available. This is what a "mission preset" button in
the app can load.
"""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "src"))
sys.path.insert(0, str(HERE))

from analogue_engine import calibrate_weights, rank, rank_over_years, to_json  # noqa: E402
import grid_1deg as g  # noqa: E402
from presets import CELLS, EARTH, PRESETS, build_profile, cell_id  # noqa: E402


def latlon(cid: str) -> tuple[float, float]:
    _, la, lo = cid.split("_")
    return float(la), float(lo)


def top_sites(result, n=10):
    out = []
    for e in result.ranked[:n]:
        la, lo = latlon(e.result.candidate_id)
        out.append({"position": e.position, "id": e.result.candidate_id, "lat": la, "lon": lo,
                    "score_0_100": round(100 * e.result.score_observed, 1),
                    "by_category": {d.dimension: (None if d.score_observed is None else round(100 * d.score_observed, 1))
                                    for d in e.result.dimensions}})
    return out


def main(data_dir: Path, calibrate: bool) -> None:
    t0 = time.time()
    base = g.build(data_dir)
    defs = g.feature_definitions()
    yearly = sorted((int(m.group(1)), p.name) for p in data_dir.glob("earth_1deg_*.csv")
                    if (m := re.fullmatch(r"earth_1deg_(\d{4})\.csv", p.name)))
    report = {"data_dir_files": sorted(p.name for p in data_dir.glob("*.csv")), "years_found": [y for y, _ in yearly],
              "presets": []}

    for preset in PRESETS:
        lat, lon = CELLS[preset["target"]]
        target = g.cell_site("mars", base["mars"], (lat, lon), base["mars_ati"])
        profile = build_profile(preset)
        known = {name: cell_id("earth", *EARTH[name]) for name in preset["known_analogs"]}
        start = rank(target, base["earth_sites"], profile, defs)
        entry = {
            "id": preset["id"], "name": preset["name"], "mission": preset["mission"], "target": preset["target"],
            "target_cell": {"lat": lat, "lon": lon}, "why": preset["why"],
            "n_ranked": len(start.ranked), "n_not_ranked": len(start.partial) + len(start.excluded),
            "start_category_weights": start.dimension_weights,
            "declared_limitations": list(start.declared_limitations),
        }
        print(f"\n=== {preset['name']}  (target {preset['target']}; {len(start.ranked)} ranked)")

        final_profile, final = profile, start
        if calibrate:
            cal = calibrate_weights(target, base["earth_sites"], profile, defs, list(known.values()))
            # Validation gate: learned weights are used only if hidden analogs improve.
            final_profile = cal.recommended_profile
            final = rank(target, base["earth_sites"], final_profile, defs)
            name_of = {v: k for k, v in known.items()}
            entry["calibration"] = {
                "known_analogs_used": [name_of[c] for c in cal.known_analogs_used],
                "known_analogs_unusable": {name_of[c]: why for c, why in cal.known_analogs_unusable.items()},
                "calibrated_category_weights": cal.calibrated_dimension_weights,
                "ranks_start": {name_of[c]: r for c, r in cal.start_summary.ranks.items()},
                "ranks_calibrated": {name_of[c]: r for c, r in cal.calibrated_summary.ranks.items()},
                "leave_one_out": [{"held_out": name_of[r.held_out], "start": r.rank_with_start_weights,
                                   "calibrated_without_it": r.rank_with_calibrated_weights} for r in cal.leave_one_out],
                "warnings": list(cal.warnings),
                "verdict": cal.verdict,
                "verdict_reason": cal.verdict_reason,
                "weights_used": "calibrated" if cal.verdict == "accepted" else "science (start)",
            }
            print(f"  VERDICT: {cal.verdict.upper()} -> using {entry['calibration']['weights_used']} weights ({cal.verdict_reason})")
            print("  weights:", {d: f"{start.dimension_weights[d]:.2f}->{cal.calibrated_dimension_weights[d]:.2f}"
                                 for d in start.dimension_weights})
            for name, cid in known.items():
                print(f"  {name:24s} start #{cal.start_summary.ranks[cid]}  calibrated #{cal.calibrated_summary.ranks[cid]}")
            for r in cal.leave_one_out:
                print(f"  hidden {name_of[r.held_out]:17s} #{r.rank_with_start_weights} -> #{r.rank_with_calibrated_weights}")
            for w in cal.warnings:
                print("  warning:", w)
        entry["profile_used"] = final_profile if isinstance(final_profile, dict) else None
        entry["top_sites"] = top_sites(final)
        for s in entry["top_sites"][:5]:
            print(f"  #{s['position']:<4} ({s['lat']:+.1f}, {s['lon']:+.1f})  {s['score_0_100']}")

        if len(yearly) >= 2:
            sites_by_year = {y: g.build(data_dir, f)["earth_sites"] for y, f in yearly}
            tl = rank_over_years(target, sites_by_year, final_profile, defs, watch=list(known.values()), top_k=20)
            entry["years"] = json.loads(tl.to_json())
            print("  years:", tl.years, "emerging:", tl.emerging[:5], "fading:", tl.fading[:5])
        report["presets"].append(entry)

    out = HERE / "output_presets.json"
    out.write_text(to_json(report) + "\n", encoding="utf-8")
    print(f"\nwritten {out.name} ({time.time() - t0:.0f}s); yearly files found: {report['years_found'] or 'none yet'}")


if __name__ == "__main__":
    main(Path(sys.argv[1]), calibrate="--no-calibration" not in sys.argv)
