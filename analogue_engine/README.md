# analogue_engine

Explainable similarity and ranking of terrestrial candidate areas against a
lunar or Martian reference ("target"), for the Planeology project (NASA Space
Apps 2026). It is the mathematical module only. There is no frontend, web API
or data download.

> **Similarity is not operational suitability.** All bundled data is
> synthetic and uncalibrated. Passing the tests is software verification, not
> scientific validation.

## What it does

Given processed feature values for a target and candidates, plus a versioned
profile (weights, scales τ, requirements), it:

1. checks per-feature comparability (canonical unit, method/version, spatial
   and temporal support, body policy);
2. computes a per-feature similarity in [0, 1] with the comparator declared
   for that feature: scaled absolute difference (τ or fixed min-max range),
   log ratio, boolean match, categorical match, Jaccard (presence sets) or
   cosine (compositions);
3. aggregates with two-level normalised weights into `S_obs` and a weighted
   coverage `C`;
4. ranks only complete candidates that satisfy all requirements, and returns
   partial and excluded candidates separately, with reasons;
5. reports a per-dimension breakdown (what is similar, how similar, what is
   not) and the profile's declared limitations (what Earth cannot reproduce);
6. can calibrate the weights so that known analogs rank high, with a
   leave-one-out check, and then suggest new candidates
   (`calibrate_weights`; demo: `python examples/calibration/run_calibration.py`);
7. can rank the same target year by year to show which sites gain or lose
   analogy over time (`rank_over_years`, for the year slider).

To run it on the Data team's 1° grid (the data is not in this repo):

```bash
python examples/real_data/run_real_grid.py <data_dir> gale
```

To run the four mission presets (rover, sample science, thermal, ice), with
calibration, the validation gate and yearly files if present:

```bash
python examples/real_data/run_presets.py <data_dir>
```

See [docs/math-model.md](docs/math-model.md) for the equations and
[docs/data-contract.md](docs/data-contract.md) for input/output and errors.

## Install

Requires Python ≥ 3.11 (tested on 3.12.10 and 3.11.9). The core has no
third-party dependencies.

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev]"
```

On macOS/Linux use `.venv/bin/python`. If you don't install, the tests still
run thanks to `pythonpath = ["src"]` in `pyproject.toml`. You only need
`pip install pytest` in that case.

## Run

```bash
python -m pytest -q
```

```bash
python examples/run_fixture.py
```

The example reproduces both fixture rankings (B,A,D and A,B,D), and writes
`examples/output/*.ranking.json` and `*.sensitivity.json`. For the mixed-kind
example inspired by the team's P1–P10 list, run this:

```bash
python examples/run_fixture.py examples/fixture_mixed_synthetic.json
```

The data team can deliver measurements as a long-format CSV
(`examples/templates/measurements_template.csv`) and load it with
`load_sites_csv`; see [docs/data-contract.md](docs/data-contract.md).

```python
from analogue_engine import load_bundle, rank

b = load_bundle("examples/fixture_synthetic.json")
result = rank(b.sites["synthetic_target"],
              [b.sites[i] for i in ("synthetic_A", "synthetic_B", "synthetic_C", "synthetic_D")],
              b.profiles["synthetic_slope_priority"],
              b.feature_definitions)
print(result.order())        # ['synthetic_B', 'synthetic_A', 'synthetic_D']
print(result.to_json())      # strict JSON, nulls instead of NaN
```

## Layout

```
src/analogue_engine/
  models.py         input records and strict parsing
  resolution.py     profile validation, effective weights (fixed per search)
  comparability.py  per-feature comparability protocol check
  comparators.py    comparator registry (linear, log, boolean, categorical, Jaccard, cosine)
  engine.py         compare(), rank()
  results.py        output records, strict JSON
  sensitivity.py    ±r one-at-a-time sensitivity of the ranking
  profiles.py       restrict_profile() for explicit, versioned reduction
  io.py             JSON bundle loader and long-format CSV loader/writer
  adapters.py       bridge to the backend wide table and its 0-100 similarity_scores
  calibration.py    weight calibration on known analogs (+ leave-one-out)
  timeline.py       rankings over years (gaining / losing analogs)
tests/              174 tests (fixture, validation, properties, sensitivity, comparators, CSV, dimensions, backend bridge, calibration, timeline, review regressions)
examples/           synthetic fixture, runner script, example outputs
docs/               math model, data contract, Spanish guide
```

## Limits (v0)

* Comparators: the six listed above. There is no unit conversion: units must
  be canonical. GeoJSON is not read directly (CSV and JSON are).
* Slope, VRM and similar quantities are inputs from the data team. They are
  not computed here.
* Uncertainty is carried through but not propagated.
* No real sites are selected or calibrated here. Feature choice, τ, weights,
  protocols and requirements belong to science/data and backend.
