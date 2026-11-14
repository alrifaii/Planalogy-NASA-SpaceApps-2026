"""The browser scoring (web/app/js/scoring.js) must give the engine's ranking.

Exports a small synthetic grid, ranks it in Python with each preset's profile,
ranks it again with web/app/js/scoring.js under Node, and compares order and scores.
Skipped if Node is not installed.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from analogue_engine import rank
from backend import engine_service as es
from backend import grid_data as g
from backend import web_export as we
from backend.tests.test_engine_service import _earth_rows, _mars_rows, _write

ROOT = Path(__file__).resolve().parents[2]
NODE = shutil.which("node")

RUNNER = r"""
const fs = require('fs'), path = require('path');
const S = require(process.argv[2]);
const dir = process.argv[3], presetId = process.argv[4];
const m = JSON.parse(fs.readFileSync(path.join(dir, 'manifest.json')));
const p = m.presets.find(x => x.id === presetId);
const cells = JSON.parse(fs.readFileSync(path.join(dir, m.files.cells.now)));
const sims = JSON.parse(fs.readFileSync(path.join(dir, m.files.sims[p.target].now)));
const r = S.scoreCells(m, cells, sims, {categoryWeights: p.category_weights, featureWeights: p.feature_weights,
  requirements: p.requirements, requiredFeatures: p.required_features});
process.stdout.write(JSON.stringify({ranked: r.ranked.map(x => [x.id, x.score]), partial: r.partial.length, excluded: r.excluded.length}));
"""


@pytest.fixture
def exported(tmp_path):
    data = tmp_path / "grid"
    data.mkdir()
    _write(data / "earth_1deg.csv", _earth_rows())
    _write(data / "mars_1deg.csv", _mars_rows())
    out = tmp_path / "web"
    we.export(data, out, calibrate=False)
    return data, out


def test_manifest_and_files(exported):
    _, out = exported
    m = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert [t["key"] for t in m["targets"]] == ["gale", "jezero", "arcadia"]
    assert len(m["presets"]) == 4 and m["years"] == ["now"]
    for f in [m["files"]["cells"]["now"]] + [v["now"] for v in m["files"]["sims"].values()]:
        assert (out / f).exists()


@pytest.mark.skipif(NODE is None, reason="Node.js not installed")
@pytest.mark.parametrize("preset_id", ["rover_navigation", "sample_science", "thermal_environment", "ice_prospecting"])
def test_js_scoring_matches_engine(exported, tmp_path, preset_id):
    data, out = exported
    runner = tmp_path / "run.js"
    runner.write_text(RUNNER, encoding="utf-8")
    res = subprocess.run([NODE, str(runner), str(ROOT / "web" / "app" / "js" / "scoring.js"), str(out), preset_id],
                         capture_output=True, text=True, check=True)
    js = json.loads(res.stdout)

    preset = next(p for p in es.PRESETS if p["id"] == preset_id)
    built = es.load_grid(str(data))
    target = es._target(preset, built)
    profile, _ = es.preset_profile(preset_id, data, calibrate=False, cache_file=None)
    py = rank(target, built["earth_sites"], profile, g.feature_definitions())

    assert [i for i, _ in js["ranked"]] == py.order()
    for (cid, s_js), e in zip(js["ranked"], py.ranked):
        assert s_js == pytest.approx(e.result.score_observed, abs=1e-5)
    assert js["partial"] == len(py.partial) and js["excluded"] == len(py.excluded)
