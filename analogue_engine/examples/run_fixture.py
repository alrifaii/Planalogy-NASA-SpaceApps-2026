"""Rank every profile of a bundle and write JSON outputs.

Usage (from the package root):

    python examples/run_fixture.py                                   # brief §6 fixture
    python examples/run_fixture.py examples/fixture_mixed_synthetic.json

For each profile the target is ``profile.target_id`` and the candidates are
all other sites of the bundle. Writes examples/output/<profile_id>.*.json.
All bundled data is SYNTHETIC and UNCALIBRATED.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))  # allow running without installation

from analogue_engine import compare, load_bundle, rank, sensitivity_analysis  # noqa: E402


def fmt(x) -> str:
    if x is None:
        return "null"
    return f"{x:.4f}" if isinstance(x, float) else str(x)


def main(bundle_path: Path) -> None:
    bundle = load_bundle(bundle_path)
    out_dir = Path(__file__).with_name("output")
    out_dir.mkdir(exist_ok=True)
    print(f"Bundle: {bundle_path.name}")

    for profile in bundle.profiles.values():
        target = bundle.sites[profile.target_id]
        candidates = [s for sid, s in sorted(bundle.sites.items()) if sid != target.id]
        result = rank(target, candidates, profile, bundle.feature_definitions)
        print(f"\nProfile {profile.id}@{profile.version}  target={target.id}")
        print("  effective weights: " + ", ".join(f"{f}={w:.3f}" for f, w in result.effective_weights.items()))
        print("  ranked:")
        for e in result.ranked:
            r = e.result
            tie = f"  tied_with={list(e.tied_with)}" if e.tied_with else ""
            print(f"    {e.position}. {r.candidate_id:24s} score={fmt(r.score_observed)} coverage={fmt(r.coverage)}{tie}")
            if len(r.dimensions) > 1:
                dims = ", ".join(f"{d.dimension}={fmt(d.score_observed)}" for d in r.dimensions)
                print(f"         by dimension: {dims}")
            for c in r.components:
                print(f"         {c.feature_id:24s} {c.comparator_id:21s} s={fmt(c.similarity)}")
        for label, group in (("partial", result.partial), ("excluded", result.excluded)):
            if group:
                print(f"  {label} (not ranked):")
                for r in group:
                    print(f"    - {r.candidate_id:24s} S_obs={fmt(r.score_observed)} coverage={fmt(r.coverage)} category={r.category}")
                    for reason in r.reasons:
                        print(f"        {reason}")
        print("  order:", ", ".join(result.order()) or "(none)")
        for item in result.declared_limitations:
            print(f"  declared limitation: {item}")
        (out_dir / f"{profile.id}.ranking.json").write_text(result.to_json() + "\n", encoding="utf-8")

        sens = sensitivity_analysis(target, candidates, profile, bundle.feature_definitions, 0.2)
        changed = sens.unstable_parameters
        print(f"  sensitivity +/-20%: {len(sens.perturbations)} perturbations, "
              f"order changes from: {changed if changed else 'none'}")
        (out_dir / f"{profile.id}.sensitivity.json").write_text(sens.to_json() + "\n", encoding="utf-8")

        identity = compare(target, target, profile, bundle.feature_definitions)
        print(f"  identity check: score={fmt(identity.score_observed)} coverage={fmt(identity.coverage)} "
              f"category={identity.category}")
    print(f"\nJSON written to {out_dir}")


if __name__ == "__main__":
    default = Path(__file__).with_name("fixture_synthetic.json")
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else default)
