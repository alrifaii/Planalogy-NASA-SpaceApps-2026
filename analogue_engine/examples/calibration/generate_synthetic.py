"""Generate a SYNTHETIC calibration bundle (deterministic, seed 2026).

Scenario: 6 invented "known analogs" resemble the reference site in terrain
and mineralogy but are random in thermal, optical, water and craters; 120
other invented Earth sites are random everywhere. A working calibration
should learn that terrain and mineralogy matter more, and should still find
a hidden known analog (leave-one-out).

Nothing here is a measurement of a real place.

    python examples/calibration/generate_synthetic.py
"""

from __future__ import annotations

import json
import math
import random
from pathlib import Path

HERE = Path(__file__).resolve().parent
MIXED = HERE.parent / "fixture_mixed_synthetic.json"
MINERALS = ["basalt", "clay", "salts", "iron_oxides"]
ROCKS = ["basaltic_sediment", "evaporite", "volcanic_basalt", "mudstone"]


def clamp(x, lo, hi):
    return max(lo, min(hi, x))


def random_site(rng):
    comp = [rng.random() + 0.01 for _ in MINERALS]
    total = sum(comp)
    return {
        "relief_m": rng.uniform(0, 1500),
        "slope_deg": rng.uniform(0, 35),
        "vrm": rng.uniform(0, 0.2),
        "surface_temp_day_k": rng.uniform(220, 330),
        "surface_temp_night_k": rng.uniform(180, 300),
        "thermal_inertia_tiu": rng.uniform(50, 1200),
        "albedo": rng.uniform(0.05, 0.5),
        "mineral_composition": {m: round(c / total, 4) for m, c in zip(MINERALS, comp)},
        "minerals_present": sorted(rng.sample(MINERALS, rng.randint(1, 4))),
        "rock_type": rng.choice(ROCKS),
        "ground_ice_present": rng.random() < 0.5,
        "hydrogen_wt_pct": 10 ** rng.uniform(-1.3, 1.0),
        "crater_density_per_km2": 10 ** rng.uniform(-4, -1),
    }


def analog_site(rng, target):
    site = random_site(rng)  # random everywhere ...
    # ... except terrain and mineralogy, which resemble the reference
    site["relief_m"] = clamp(target["relief_m"] + rng.gauss(0, 60), 0, None or 5000)
    site["slope_deg"] = clamp(target["slope_deg"] + rng.gauss(0, 2), 0, 60)
    site["vrm"] = clamp(target["vrm"] + rng.gauss(0, 0.01), 0, 1)
    comp = {m: max(0.01, v + rng.gauss(0, 0.05)) for m, v in target["mineral_composition"].items()}
    total = sum(comp.values())
    site["mineral_composition"] = {m: round(v / total, 4) for m, v in comp.items()}
    present = set(target["minerals_present"])
    if rng.random() < 0.4:
        present ^= {rng.choice(MINERALS)}
    site["minerals_present"] = sorted(present) or ["basalt"]
    site["rock_type"] = target["rock_type"] if rng.random() < 0.85 else rng.choice(ROCKS)
    return site


def main() -> None:
    rng = random.Random(2026)
    mixed = json.loads(MIXED.read_text(encoding="utf-8"))
    defs = [d for d in mixed["feature_definitions"] if d["id"] != "dust_cover_index"]  # P6 out (team decision)
    units = {d["id"]: d["canonical_unit"] for d in defs}
    ref_site = next(s for s in mixed["sites"] if s["id"] == "synthetic_mars_reference")
    target_values = {m["feature_id"]: m["value"] for m in ref_site["measurements"] if m["feature_id"] in units}

    def site(sid, body, values):
        return {
            "id": sid, "body": body, "data_mode": "synthetic", "name": None, "area_ref": f"synthetic_area:{sid}",
            "measurements": [
                {"feature_id": f, "value": round(v, 6) if isinstance(v, float) else v, "status": "valid",
                 "unit": units[f], "method_id": f"synthetic_method_{f}", "method_version": "0",
                 "spatial_support": "synthetic_support_v0",
                 "source_ref": "SYNTHETIC: invented for calibration tests, not a measurement"}
                for f, v in values.items()
            ],
        }

    sites = [site("synthetic_mars_reference", "mars", target_values)]
    known = []
    for i in range(1, 7):
        sid = f"synthetic_known_analog_{i}"
        known.append(sid)
        sites.append(site(sid, "earth", analog_site(rng, target_values)))
    for i in range(1, 121):
        sites.append(site(f"synthetic_earth_{i:03d}", "earth", random_site(rng)))

    base = next(p for p in mixed["profiles"] if p["id"] == "synthetic_mixed_rover")
    features = [dict(f, weight=1) for f in base["features"] if f["feature_id"] in units]
    dims = sorted({d["dimension"] for d in defs})
    profile = {
        "id": "synthetic_start_profile", "version": "0.1.0", "target_id": "synthetic_mars_reference",
        "calibration_status": "uncalibrated",
        "description": "Uninformed starting profile (all categories and features equal), as an AI or a person might propose before calibration.",
        "dimension_weights": {d: 1 for d in dims},
        "features": features, "required_features": [], "constraints": [],
        "declared_limitations": base.get("declared_limitations", []),
    }
    bundle = {
        "schema_version": "analogue_engine.bundle.v0",
        "note": "SYNTHETIC calibration scenario: invented known analogs resemble the reference in terrain and mineralogy only. No real places or measurements.",
        "known_analogs": known,
        "feature_definitions": defs, "sites": sites, "profiles": [profile],
    }
    out = HERE / "calibration_synthetic.json"
    out.write_text(json.dumps(bundle, indent=1, allow_nan=False) + "\n", encoding="utf-8")
    print(f"wrote {out} ({len(sites)} sites, known analogs: {known})")


if __name__ == "__main__":
    main()
