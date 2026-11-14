"""Weight calibration against known analogs (synthetic scenario)."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from analogue_engine import (
    CalibrationSettings,
    InvalidRequestError,
    calibrate_weights,
    parse_bundle,
    rank,
)

BUNDLE = Path(__file__).resolve().parents[1] / "examples" / "calibration" / "calibration_synthetic.json"


@pytest.fixture(scope="module")
def raw():
    return json.loads(BUNDLE.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def parts(raw):
    b = parse_bundle(raw)
    profile = next(iter(b.profiles.values()))
    target = b.sites[profile.target_id]
    cands = [s for k, s in sorted(b.sites.items()) if k != target.id]
    return target, cands, profile, b.feature_definitions, raw["known_analogs"]


@pytest.fixture(scope="module")
def result(parts):
    target, cands, profile, defs, known = parts
    return calibrate_weights(target, cands, profile, defs, known)


def test_known_analogs_move_up(result):
    assert result.calibrated_summary.mean_top_percent < result.start_summary.mean_top_percent
    assert result.calibrated_summary.in_top_10_percent >= result.start_summary.in_top_10_percent


def test_learns_the_planted_signal(result):
    """The synthetic analogs resemble the reference only in terrain and mineralogy."""
    start, cal = result.start_dimension_weights, result.calibrated_dimension_weights
    assert cal["terrain"] > start["terrain"] and cal["mineralogy"] > start["mineralogy"]
    top_two = sorted(cal, key=cal.get, reverse=True)[:2]
    assert set(top_two) == {"terrain", "mineralogy"}


def test_leave_one_out_improves_on_average(result):
    loo = result.leave_one_out
    assert len(loo) == len(result.known_analogs_used)
    mean_start = sum(r.rank_with_start_weights for r in loo) / len(loo)
    mean_cal = sum(r.rank_with_calibrated_weights for r in loo) / len(loo)
    assert mean_cal < mean_start


def test_calibrated_profile_reproduces_weights_in_the_engine(parts, result):
    target, cands, _, defs, _ = parts
    again = rank(target, cands, result.calibrated_profile, defs)
    assert again.effective_weights == pytest.approx(result.calibrated_feature_weights, abs=1e-12)
    assert result.calibrated_profile["calibration_status"] == "provisional"
    assert result.calibrated_profile["version"].endswith("-cal")
    assert sum(result.calibrated_feature_weights.values()) == pytest.approx(1.0)


def test_scales_and_requirements_unchanged(parts, result):
    _, _, profile, _, _ = parts
    for f in result.calibrated_profile["features"]:
        start = next(p for p in profile.features if p.feature_id == f["feature_id"])
        assert f.get("tau", start.tau) == start.tau
    assert result.calibrated_profile["constraints"] == []
    assert result.calibrated_profile["declared_limitations"] == list(profile.declared_limitations)


def test_strong_prior_keeps_start_weights(parts):
    target, cands, profile, defs, known = parts
    r = calibrate_weights(target, cands, profile, defs, known,
                          settings=CalibrationSettings(prior_strength=1e6, iterations=50), leave_one_out=False)
    assert r.calibrated_feature_weights == pytest.approx(r.start_feature_weights, abs=1e-4)


def test_zero_iterations_is_identity(parts):
    target, cands, profile, defs, known = parts
    r = calibrate_weights(target, cands, profile, defs, known,
                          settings=CalibrationSettings(iterations=0), leave_one_out=False)
    assert r.calibrated_feature_weights == pytest.approx(r.start_feature_weights, abs=1e-12)


def test_zero_weight_features_stay_zero(raw):
    raw = copy.deepcopy(raw)
    p = raw["profiles"][0]
    # vrm shares the 'terrain' dimension with relief and slope, so terrain keeps a positive internal sum
    next(f for f in p["features"] if f["feature_id"] == "vrm")["weight"] = 0
    b = parse_bundle(raw)
    profile = next(iter(b.profiles.values()))
    target = b.sites[profile.target_id]
    cands = [s for k, s in sorted(b.sites.items()) if k != target.id]
    r = calibrate_weights(target, cands, profile, b.feature_definitions, raw["known_analogs"], leave_one_out=False)
    assert r.calibrated_feature_weights["vrm"] == 0.0


def test_incomplete_known_analog_is_reported_not_used(raw):
    raw = copy.deepcopy(raw)
    site = next(s for s in raw["sites"] if s["id"] == "synthetic_known_analog_1")
    m = next(x for x in site["measurements"] if x["feature_id"] == "rock_type")
    m["value"], m["status"] = None, "missing"
    b = parse_bundle(raw)
    profile = next(iter(b.profiles.values()))
    target = b.sites[profile.target_id]
    cands = [s for k, s in sorted(b.sites.items()) if k != target.id]
    r = calibrate_weights(target, cands, profile, b.feature_definitions, raw["known_analogs"], leave_one_out=False)
    assert "synthetic_known_analog_1" in r.known_analogs_unusable
    assert "synthetic_known_analog_1" not in r.known_analogs_used
    assert any("not usable" in w for w in r.warnings)


def test_new_candidates_exclude_known_analogs(result):
    ids = [c["candidate_id"] for c in result.new_candidates]
    assert ids and not set(ids) & set(result.known_analogs_used)
    positions = [c["position"] for c in result.new_candidates]
    assert positions == sorted(positions)


def test_input_errors(parts):
    target, cands, profile, defs, _ = parts
    with pytest.raises(InvalidRequestError):
        calibrate_weights(target, cands, profile, defs, ["not_a_site"])
    with pytest.raises(InvalidRequestError):
        calibrate_weights(target, cands, profile, defs, [])
    with pytest.raises(InvalidRequestError):
        calibrate_weights(target, cands, profile, defs, ["synthetic_known_analog_1"],
                          settings=CalibrationSettings(temperature=0))


def test_single_known_analog_skips_leave_one_out(parts):
    target, cands, profile, defs, _ = parts
    r = calibrate_weights(target, cands, profile, defs, ["synthetic_known_analog_1"])
    assert r.leave_one_out == ()
    assert any("leave-one-out needs" in w for w in r.warnings)


def test_validation_gate_accepts_when_hidden_analogs_improve(result):
    assert result.verdict == "accepted"
    assert result.recommended_profile == result.calibrated_profile
    assert "hidden analogs" in result.verdict_reason


def test_validation_gate_rejects_and_keeps_start_weights(parts):
    target, cands, profile, defs, known = parts
    r = calibrate_weights(target, cands, profile, defs, known,
                          settings=CalibrationSettings(min_loo_improvement=1.0))  # impossible bar
    assert r.verdict == "rejected"
    assert r.recommended_profile["version"] == profile.version  # starting profile, not "-cal"
    again = rank(target, cands, r.recommended_profile, defs)
    assert again.effective_weights == pytest.approx(r.start_feature_weights, abs=1e-12)


def test_validation_gate_not_validated_with_one_analog(parts):
    target, cands, profile, defs, _ = parts
    r = calibrate_weights(target, cands, profile, defs, ["synthetic_known_analog_1"])
    assert r.verdict == "not_validated"
    assert r.recommended_profile["version"] == profile.version


def test_deterministic_and_strict_json(parts, result):
    target, cands, profile, defs, known = parts
    again = calibrate_weights(target, cands, profile, defs, known)
    assert again.to_json() == result.to_json()
    json.loads(result.to_json())
