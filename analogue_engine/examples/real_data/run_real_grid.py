"""Rank every dry, bare 1-degree Earth cell against a Mars target cell.

    python examples/real_data/run_real_grid.py <data_dir> [target_name]

<data_dir> holds earth_1deg.csv and mars_1deg.csv from the Data team (the
data is not stored in this repository). Targets: gale (default), jezero,
arcadia (approximate cell; confirm with Science).

Writes, next to this script:
  output_<target>_ranking.json   full engine result
  output_<target>_earth_scores.csv  lat, lon, score, coverage, category and dimension scores
                                    (for a heat map in the frontend)
"""

from __future__ import annotations

import csv
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "src"))
sys.path.insert(0, str(HERE))

from analogue_engine import rank, sensitivity_analysis  # noqa: E402
import grid_1deg as g  # noqa: E402

TARGETS = {"gale": (-5.5, 137.5), "jezero": (18.5, 77.5), "arcadia": (46.5, -167.5)}
KNOWN = {  # cells containing well-known analog sites named in the Science P1-P10 analysis
    "Atacama": (-24.5, -69.5), "Arizaro": (-24.5, -67.5), "Dry Valleys": (-77.5, 161.5),
    "Devon Is. (Haughton)": (75.5, -89.5), "Kara-Kul": (39.5, 73.5),
}


def sid(planet, lat, lon):
    return f"{planet}_{lat:+05.1f}_{lon:+06.1f}"


def main(data_dir: Path, target_name: str) -> None:
    t0 = time.time()
    data = g.build(data_dir)
    lat, lon = TARGETS[target_name]
    target = g.cell_site("mars", data["mars"], (lat, lon), data["mars_ati"])
    profile = g.profile(target["id"])
    defs = g.feature_definitions()
    sites = data["earth_sites"]
    print(f"Target {target_name} cell {target['id']}; Earth candidates after dry/bare filter: {len(sites)}")
    print("Target values:", {m["feature_id"]: m["value"] for m in target["measurements"]})

    result = rank(target, sites, profile, defs)
    print(f"ranked {len(result.ranked)}, partial {len(result.partial)}, excluded {len(result.excluded)} "
          f"({time.time() - t0:.1f}s)")

    print("\nTop 15:")
    for e in result.ranked[:15]:
        r = e.result
        dims = " ".join(f"{d.dimension[:5]}={d.score_observed:.2f}" for d in r.dimensions if d.score_observed is not None)
        print(f"  #{e.position:<4d} {r.candidate_id:22s} {100 * r.score_observed:5.1f}  {dims}")

    pos = {cid: i + 1 for i, cid in enumerate(result.order())}
    others = {r.candidate_id: r for r in result.partial + result.excluded}
    n = len(result.ranked)
    print(f"\nKnown analogs (of {n} ranked):")
    for name, (la, lo) in KNOWN.items():
        cid = sid("earth", la, lo)
        if cid in pos:
            r = result.ranked[pos[cid] - 1].result
            dims = " ".join(f"{d.dimension[:5]}={d.score_observed:.2f}" for d in r.dimensions if d.score_observed is not None)
            print(f"  {name:22s} #{pos[cid]:<5d} top {100 * pos[cid] / n:4.1f}%  score {100 * r.score_observed:5.1f}  {dims}")
        elif cid in others:
            print(f"  {name:22s} not ranked: {others[cid].category}; {'; '.join(others[cid].reasons)[:120]}")
        else:
            print(f"  {name:22s} removed by the dry/bare pre-filter")

    best = 100 * result.ranked[0].result.score_observed if result.ranked else None
    print(f"\nSanity: best score {best:.1f} (Science: no site should be near 100)")

    out_json = HERE / f"output_{target_name}_ranking.json"
    out_json.write_text(result.to_json() + "\n", encoding="utf-8")
    out_csv = HERE / f"output_{target_name}_earth_scores.csv"
    dims_order = [d.dimension for d in result.ranked[0].result.dimensions] if result.ranked else []
    with out_csv.open("w", newline="", encoding="utf-8") as h:
        w = csv.writer(h)
        w.writerow(["lat", "lon", "position", "score_0_100", "coverage", "category"] + [f"dim_{d}" for d in dims_order])
        for e in result.ranked:
            r = e.result
            la, lo = r.candidate_id.split("_")[1:]
            w.writerow([la, lo, e.position, round(100 * r.score_observed, 2), round(r.coverage, 3), r.category]
                       + [None if d.score_observed is None else round(100 * d.score_observed, 2) for d in r.dimensions])
        for r in result.partial + result.excluded:
            la, lo = r.candidate_id.split("_")[1:]
            w.writerow([la, lo, "", "", round(r.coverage, 3), r.category] + [""] * len(dims_order))
    print(f"written {out_json.name}, {out_csv.name}")

    if "--sensitivity" in sys.argv:
        top = [e.result.candidate_id for e in result.ranked[:200]]
        subset = [s for s in sites if s["id"] in set(top)]
        rep = sensitivity_analysis(target, subset, profile, defs, 0.2)
        print("sensitivity (top 200, +/-20%): order changes from", rep.unstable_parameters or "none")


if __name__ == "__main__":
    main(Path(sys.argv[1]), sys.argv[2] if len(sys.argv) > 2 and not sys.argv[2].startswith("--") else "gale")
