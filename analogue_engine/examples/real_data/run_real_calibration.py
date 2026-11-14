"""Calibrate the Gale profile on known analogs using the Data team's 1-degree grid.

    python examples/real_data/run_real_calibration.py <data_dir>

Known analogs are the Gale-appropriate ones from the Science P1-P10 analysis
(Atacama, Arizaro, Kara-Kul). Polar sites are left out on purpose: Gale has
no ground ice, so training on them would teach the opposite.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "src"))
sys.path.insert(0, str(HERE))

from analogue_engine import calibrate_weights  # noqa: E402
import grid_1deg as g  # noqa: E402

KNOWN = {"Atacama": (-24.5, -69.5), "Arizaro": (-24.5, -67.5), "Kara-Kul": (39.5, 73.5)}


def main(data_dir: Path) -> None:
    t0 = time.time()
    data = g.build(data_dir)
    target = g.cell_site("mars", data["mars"], (-5.5, 137.5), data["mars_ati"])
    known_ids = [f"earth_{la:+05.1f}_{lo:+06.1f}" for la, lo in KNOWN.values()]
    res = calibrate_weights(target, data["earth_sites"], g.profile(target["id"]), g.feature_definitions(), known_ids)
    n = res.start_summary.n_ranked
    print(f"Gale, {n} ranked Earth cells, known analogs {list(KNOWN)} ({time.time() - t0:.0f}s)\n")
    print("Category weights      start  calibrated")
    for d, w in sorted(res.start_dimension_weights.items(), key=lambda kv: -res.calibrated_dimension_weights[kv[0]]):
        print(f"  {d:18s} {w:6.3f}  {res.calibrated_dimension_weights[d]:6.3f}")
    print("\nKnown analogs         start   calibrated")
    for name, cid in zip(KNOWN, known_ids):
        print(f"  {name:18s} #{res.start_summary.ranks[cid]:<6} #{res.calibrated_summary.ranks[cid]}")
    print("\nLeave-one-out (hidden from tuning):")
    for name, r in zip(KNOWN, res.leave_one_out):
        print(f"  {name:18s} start #{r.rank_with_start_weights:<6} -> #{r.rank_with_calibrated_weights}")
    print("\nTop new candidates after calibration:")
    for c in res.new_candidates[:8]:
        print(f"  #{c['position']:<4} {c['candidate_id']:22s} {100 * c['score']:.1f}")
    for w in res.warnings:
        print("warning:", w)
    (HERE / "output_gale_calibration.json").write_text(res.to_json() + "\n", encoding="utf-8")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
