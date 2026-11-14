"""Demo: backend wide table -> engine -> `similarity_scores` for the backend.

Usage (from the package root):

    python examples/backend_bridge/run_backend_bridge.py [wide.csv] [mission_type]

Writes examples/backend_bridge/output_<mission>.json. The `similarity_scores`
dict in it is what `backend.integration.run_assessment(...)` expects (0-100).
All data here is SYNTHETIC; column metadata, tau and weights are placeholders.

In the backend the call would look like this:

    from analogue_engine import rank, sites_from_wide_records, backend_payload
    sites = sites_from_wide_records(df.to_dict("records"), cfg["column_specs"],
                                    cfg["feature_definitions"], data_mode="synthetic")
    result = rank(sites[target_id], [s for k, s in sites.items() if k != target_id and s.body == "Earth"],
                  cfg["profiles"][mission_type], cfg["feature_definitions"])
    payload = backend_payload(result)
    results = run_assessment(target_id, mission_type, payload["similarity_scores"])
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "src"))

from analogue_engine import backend_payload, rank, sites_from_wide_records, to_json  # noqa: E402


def main(csv_path: Path, mission: str) -> None:
    cfg = json.loads((HERE / "bridge_config.json").read_text(encoding="utf-8"))
    with csv_path.open(newline="", encoding="utf-8") as handle:
        records = list(csv.DictReader(handle))

    sites = sites_from_wide_records(
        records, cfg["column_specs"], cfg["feature_definitions"], data_mode="synthetic"
    )
    profile = cfg["profiles"][mission]
    target = sites[profile["target_id"]]
    candidates = [s for sid, s in sorted(sites.items()) if sid != target.id and s.body == "Earth"]

    result = rank(target, candidates, profile, cfg["feature_definitions"])
    payload = backend_payload(result)

    print(f"Mission profile: {mission}  target: {target.id} ({target.body})")
    print("similarity_scores for run_assessment (0-100):")
    for cid in payload["ranked_order"]:
        dims = ", ".join(f"{d}={v:.1f}" for d, v in payload["dimension_scores"][cid].items() if v is not None)
        print(f"  {cid}: {payload['similarity_scores'][cid]:.1f}   [{dims}]")
    for cid, info in payload["not_ranked"].items():
        print(f"  {cid}: NOT RANKED ({info['category']}, coverage {info['coverage']:.2f})")
        for reason in info["reasons"]:
            print(f"      {reason}")
    for item in payload["declared_limitations"]:
        print(f"  declared limitation: {item}")

    out = HERE / f"output_{mission}.json"
    out.write_text(to_json(payload) + "\n", encoding="utf-8")
    print(f"\nPayload written to {out}")


if __name__ == "__main__":
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "wide_locations_synthetic.csv"
    main(path, sys.argv[2] if len(sys.argv) > 2 else "rover_testing")
