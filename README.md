# Planeology-NASA-SpaceApps-2026
A data-driven planetary analogue identification platform using NASA and partner space agency observations, geospatial analysis and mathematical modelling to identify Earth locations suitable for future lunar and Martian mission testing.

## Structure

| Folder | What it is |
|---|---|
| `analogue_engine/` | Similarity model (pure Python): comparators, weights, calibration on known analogs, year slider, site cards. See its README and `docs/`. |
| `backend/` | App backend: data interface, geospatial helpers, mission profiles, integration, and `engine_service.py`, which connects the engine to the data. |
| `data/grid_1deg/` | Data team's 1°×1° Earth/Mars grid (`earth_1deg.csv`, `mars_1deg.csv`, `parameters.csv`). It comes from branch `data-grid-1deg`. |

## Install

```bash
pip install -r requirements.txt
```

The requirements include the engine as `-e ./analogue_engine`.

## Run the mission presets

```bash
python -m backend.engine_service
```

This runs all four presets: rover navigation (Gale), sample science
(Jezero), thermal environment (Gale) and ground-ice prospecting (Arcadia).
To run one preset with more sites, or to point at another data folder:

```bash
python -m backend.engine_service rover_navigation --top 20 --data data/grid_1deg
```

Results go to `data/results/<preset>.json`. Each file contains the ranked
sites with site cards (score, coverage, what matches, what doesn't, what is
missing), a heat map of every scored cell, map points, the calibration
verdict and the declared limitations. The first run calibrates each preset
(about 20 s) and caches the result in `data/preset_profiles.json`.

**Year slider (climate change):** the Data team's projected Earth files are in
`data/grid_1deg/ssp245/` and `data/grid_1deg/ssp585/` (`earth_1deg_<year>.csv` for 2030, 2050, 2070,
2090; WorldClim 2.1 CMIP6, 6-model mean). Today's file is the baseline (1985 = middle of 1970-2000):

```bash
python -m backend.engine_service --years                    # SSP2-4.5
python -m backend.engine_service --years --scenario ssp585  # high emissions
```

This writes `data/results/<preset>_years_<scenario>.json` with the sites gaining or
losing analogy. What changes in the future files: air temperature (incl. the
day-night air swing, scored in P2), precipitation (dry/bare filter) and aridity;
see `data/grid_1deg/README.md`.

**Settings for a GUI:** `analogue_engine/examples/real_data/analysis_config.json`
switches every parameter on/off (`use` 1/0) and sets its weight; defaults are the
Science P1-P10 recommendation (`run_config.py`, data contract section 9).

## Web app (Planalogy)

`web/app/` is the static web app. It has two pages: the **Analog Finder** and
**About** (project, data sources, team). The Finder is one screen with five
steps: pick a target on Mars (a preset site or any point on the globe), switch
to Earth, choose a mission, move through the years (today to 2090, SSP2-4.5 or
SSP5-8.5), and switch the eight parameters on or off and set their weights.
Every Earth land cell is re-ranked in the browser. Against today, cells that
drop out of the candidates are outlined in red and cells that join in white.
The Moon is a third body as a preview (planned base sites, no scoring yet).
Sites with 1-km projections (`data/hires_sites/`) show an "Inside this cell"
block in their site card.

The earlier pages (Explore, Compare, Admin, detail pages) are still in
`web/app/js/` but are no longer loaded by `index.html`.

Optional sharper globes (8192 px, Solar System Scope, CC BY 4.0):
`python web/app/tex/get_textures.py`.

`backend/web_export.py` exports the raw feature values of every Earth land
cell and every Mars cell. `web/app/js/scoring.js` applies the engine's
comparators, scales, weights and ordering. A test under Node.js checks that
the similarities match the engine bit for bit and that the ranking is
identical. Yearly Earth files only carry the climate-dependent columns.
To refresh the data after new grid files, including yearly files for the
year slider, run:

```bash
python -m backend.web_export     # every scenario in data/grid_1deg/ and the 1-km site results
```

The app is published as a Claude artifact. Any static host also works:

```bash
python -m http.server --directory web/app
```

## Tests

```bash
python -m pytest backend/tests -q
```

```bash
cd analogue_engine
python -m pytest -q
```
