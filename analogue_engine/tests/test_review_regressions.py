"""Regression tests for the findings of the independent code review
(v0.1)."""

from __future__ import annotations

import copy

import pytest

from analogue_engine import (
    AnalogueEngineError,
    InvalidRequestError,
    Profile,
    ProfileError,
    compare,
    loads_strict,
    parse_bundle,
    rank,
    restrict_profile,
    sensitivity_analysis,
)


def test_known_mismatch_wins_over_absent_metadata(fx):
    """R1: a must-match field that differs is decisive even if another field is absent."""
    m = fx.measurement(fx.site("A"), "slope_deg")
    m["method_id"] = "totally_different_method"
    m["method_version"] = None
    r = compare(fx.target, fx.site("A"), fx.p1, fx.defs)
    assert r.components[0].status == "incompatible"
    assert r.components[0].reason_code == "protocol_mismatch:method_id"
    assert r.category == "incompatible"


def _two_dimension_bundle(fx):
    for d in fx.defs:
        if d["id"] == "relief_m":
            d["dimension"] = "relief"
    fx.p1["dimension_weights"] = {"terrain": 0.5, "relief": 0.5}
    return fx


def test_restrict_profile_can_drop_a_whole_dimension(fx):
    """R2: restricting away every feature of a dimension yields a usable profile."""
    _two_dimension_bundle(fx)
    p = Profile.from_dict(fx.p1)
    reduced = restrict_profile(p, ["slope_deg", "vrm"], "0.2.0", fx.defs)
    assert reduced.dimension_weights == {"terrain": 0.5}
    result = rank(fx.target, fx.candidates(), reduced, fx.defs)
    assert result.effective_weights == pytest.approx({"slope_deg": 0.8 / 0.9, "vrm": 0.1 / 0.9})


@pytest.mark.parametrize(
    "mutate",
    [
        lambda fx: [f.__setitem__("weight", 1e308) for f in fx.p1["features"]],
        lambda fx: (_two_dimension_bundle(fx), fx.p1.__setitem__("dimension_weights", {"terrain": 1e308, "relief": 1e308})),
        lambda fx: fx.p1.__setitem__("constraints", 5),
    ],
)
def test_bad_profiles_raise_engine_errors_only(fx, mutate):
    """R3: malformed input never escapes as a non-AnalogueEngineError."""
    mutate(fx)
    with pytest.raises(AnalogueEngineError):
        rank(fx.target, fx.candidates(), fx.p1, fx.defs)


@pytest.mark.parametrize("bundle", [[], {"schema_version": "analogue_engine.bundle.v0", "sites": 5}])
def test_bad_bundles_raise_engine_errors(bundle):
    with pytest.raises(InvalidRequestError):
        parse_bundle(bundle)


def test_invalid_json_text_raises_engine_error():
    with pytest.raises(InvalidRequestError) as e:
        loads_strict("{")
    assert e.value.code == "invalid_json"


@pytest.mark.parametrize("bad", [1.5, 0, "0.2", True])
def test_sensitivity_rejects_bad_relative_change(fx, bad):
    with pytest.raises(InvalidRequestError):
        sensitivity_analysis(fx.target, fx.candidates(), fx.p1, fx.defs, bad)


def test_constraint_boundary_is_not_decided_by_float_noise(fx):
    """R4: |0.4 - 0.1| = 0.30000000000000004 must satisfy |delta| <= 0.3."""
    fx.measurement(fx.target, "vrm")["value"] = 0.1
    fx.measurement(fx.site("A"), "vrm")["value"] = 0.4
    fx.p1["constraints"] = [
        {"id": "vrm_gap", "feature_id": "vrm", "type": "max_abs_difference", "limit": 0.3, "unit": "1"}
    ]
    r = compare(fx.target, fx.site("A"), fx.p1, fx.defs)
    assert r.constraints[0].status == "satisfied"
    # A real excess is still caught.
    fx.measurement(fx.site("A"), "vrm")["value"] = 0.4001
    assert compare(fx.target, fx.site("A"), fx.p1, fx.defs).constraints[0].status == "violated"


def test_overflowing_candidate_does_not_abort_ranking(fx):
    """R5: one candidate whose difference overflows is excluded; others rank."""
    fx.measurement(fx.target, "relief_m")["value"] = 1e308
    bad = fx.new_site("synthetic_bad", {"relief_m": -1e308})
    result = rank(fx.target, fx.candidates() + [bad], fx.p1, fx.defs)
    [ex] = [r for r in result.excluded if r.candidate_id == "synthetic_bad"]
    assert ex.category == "incompatible"
    assert ex.components[2].reason_code == "comparison_failed:non_finite_number"
    assert len(result.ranked) == 3  # A, B, D still ranked
    result.to_json()  # still strictly serialisable


def test_constraint_unit_must_be_canonical(fx):
    """R6: constraint limits carry a unit that is checked."""
    fx.p1["constraints"] = [
        {"id": "relief_gap", "feature_id": "relief_m", "type": "max_abs_difference", "limit": 0.02, "unit": "km"}
    ]
    with pytest.raises(ProfileError) as e:
        rank(fx.target, fx.candidates(), fx.p1, fx.defs)
    assert e.value.code == "constraint_unit_mismatch"
    del fx.p1["constraints"][0]["unit"]
    with pytest.raises(InvalidRequestError):
        rank(fx.target, fx.candidates(), fx.p1, fx.defs)


def test_sensitivity_skips_no_op_perturbations(fx):
    """Minor: a sole feature in its dimension and zero-weight taus are skipped."""
    _two_dimension_bundle(fx)
    fx.pfeature(fx.p1, "vrm")["weight"] = 0
    report = sensitivity_analysis(fx.target, fx.candidates(), fx.p1, fx.defs, 0.2)
    params = {p.parameter for p in report.perturbations}
    assert params == {"dimension_weight:terrain", "dimension_weight:relief", "tau:slope_deg", "tau:relief_m"}
