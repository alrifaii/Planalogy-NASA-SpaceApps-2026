"""Site cards for the top sites of every mission preset.

    python examples/real_data/site_cards.py <data_dir> [top_n]

Uses each preset's recommended profile (calibrated only if it passed the
validation gate, otherwise Science's weights), ranks the dry, bare Earth
cells and writes examples/real_data/output_site_cards.json. For every preset
it lists the top_n cards (score, coverage, matches, partial matches,
mismatches, missing data, requirements, what Earth cannot reproduce), each
with the cell's lat/lon. This is what the map's "click a site" panel can show.
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "src"))
sys.path.insert(0, str(HERE))

from analogue_engine import calibrate_weights, explain, rank, to_json  # noqa: E402
import grid_1deg as g  # noqa: E402
from presets import CELLS, EARTH, PRESETS, build_profile, cell_id  # noqa: E402


def main(data_dir: Path, top_n: int) -> None:
    base = g.build(data_dir)
    defs = g.feature_definitions()
    known_cells = {cell_id("earth", *v): k for k, v in EARTH.items()}
    out = {"presets": []}
    for preset in PRESETS:
        lat, lon = CELLS[preset["target"]]
        target = g.cell_site("mars", base["mars"], (lat, lon), base["mars_ati"])
        profile = build_profile(preset)
        known = [cell_id("earth", *EARTH[n]) for n in preset["known_analogs"]]
        cal = calibrate_weights(target, base["earth_sites"], profile, defs, known)
        result = rank(target, base["earth_sites"], cal.recommended_profile, defs)
        cards = []
        for e in result.ranked[:top_n]:
            card = explain(e.result)
            _, la, lo = e.result.candidate_id.split("_")
            card.update({"position": e.position, "lat": float(la), "lon": float(lo),
                         "known_analog": known_cells.get(e.result.candidate_id)})
            cards.append(card)
        out["presets"].append({
            "id": preset["id"], "name": preset["name"], "mission": preset["mission"], "target": preset["target"],
            "weights_used": "calibrated" if cal.verdict == "accepted" else "science (start)",
            "verdict_reason": cal.verdict_reason, "n_ranked": len(result.ranked), "cards": cards,
        })
        print(f"{preset['name']}: {len(cards)} cards; #1 {cards[0]['lat']},{cards[0]['lon']} -> {cards[0]['headline']}")
    path = HERE / "output_site_cards.json"
    path.write_text(to_json(out) + "\n", encoding="utf-8")
    print(f"written {path.name}")


if __name__ == "__main__":
    main(Path(sys.argv[1]), int(sys.argv[2]) if len(sys.argv) > 2 else 5)
