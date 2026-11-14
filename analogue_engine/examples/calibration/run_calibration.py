"""Calibrate weights on known analogs and show what changed.

    python examples/calibration/run_calibration.py [bundle.json]

Prints category weights before/after, where the known analogs rank, the
leave-one-out check and the best "new" candidates. Writes
examples/calibration/output_calibration.json (includes the calibrated
profile, ready for rank()). All data is SYNTHETIC.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "src"))

from analogue_engine import calibrate_weights, parse_bundle  # noqa: E402


def main(path: Path) -> None:
    raw = json.loads(path.read_text(encoding="utf-8"))
    bundle = parse_bundle(raw)
    profile = next(iter(bundle.profiles.values()))
    target = bundle.sites[profile.target_id]
    candidates = [s for sid, s in sorted(bundle.sites.items()) if sid != target.id]

    result = calibrate_weights(target, candidates, profile, bundle.feature_definitions, raw["known_analogs"])

    print(f"Calibrating '{profile.id}' on {len(result.known_analogs_used)} known analogs, "
          f"{result.start_summary.n_ranked} ranked candidates\n")
    print("Category weights        start   calibrated")
    for dim, w in sorted(result.start_dimension_weights.items(), key=lambda kv: -result.calibrated_dimension_weights[kv[0]]):
        print(f"  {dim:20s} {w:7.3f}   {result.calibrated_dimension_weights[dim]:7.3f}")
    print("\nKnown analogs: position (of %d)    start  calibrated" % result.start_summary.n_ranked)
    for k in result.known_analogs_used:
        print(f"  {k:28s} {result.start_summary.ranks[k]:6d}  {result.calibrated_summary.ranks[k]:9d}")
    print(f"  mean 'top %':  {result.start_summary.mean_top_percent:.1f}%  ->  {result.calibrated_summary.mean_top_percent:.1f}%")
    if result.leave_one_out:
        print("\nLeave-one-out (hide one, calibrate on the rest, where does the hidden one land?)")
        for r in result.leave_one_out:
            print(f"  {r.held_out:28s} start #{r.rank_with_start_weights:<4d} -> calibrated without it #{r.rank_with_calibrated_weights}")
    print("\nBest new candidates (not in the known list):")
    for c in result.new_candidates[:5]:
        print(f"  #{c['position']:<3d} {c['candidate_id']:24s} score {c['score']:.3f}")
    for w in result.warnings:
        print(f"\nwarning: {w}")

    out = HERE / "output_calibration.json"
    out.write_text(result.to_json() + "\n", encoding="utf-8")
    print(f"\nWritten {out}")


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "calibration_synthetic.json")
