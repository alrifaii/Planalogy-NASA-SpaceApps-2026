"""Checks 3, 4, 8 and 10 of the brief: invalid inputs, unit/protocol
incompatibility, zero weights, required features, target without an active
feature, constraints, data-mode mixing, strict JSON."""

from __future__ import annotations

import json
import math

import pytest

from analogue_engine import (
    DataModeError,
    InvalidRequestError,
    ProfileError,
    compare,
    loads_strict,
    rank,
)


# ----------------------------------------------------------------- check 3: invalid numbers


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf, True, "12"])
def test_rejects_non_finite_or_non_numeric_measurement(fx, bad):
    fx.measurement(fx.site("A"), "slope_deg")["value"] = bad
    with pytest.raises(InvalidRequestError) as e:
        rank(fx.target, fx.candidates(), fx.p1, fx.defs)
    # NaN/inf are rejected when parsing; bool/str parse fine but do not fit a scalar feature.
    assert e.value.code in ("non_finite_number", "invalid_number", "value_type_mismatch")


@pytest.mark.parametrize("field, bad", [("weight", math.nan), ("weight", math.inf), ("tau", math.nan), ("tau", math.inf)])
def test_rejects_non_finite_profile_numbers(fx, field, bad):
    fx.pfeature(fx.p1, "vrm")[field] = bad
    with pytest.raises(InvalidRequestError):
        rank(fx.target, fx.candidates(), fx.p1, fx.defs)


def test_rejects_negative_weight(fx):
    fx.pfeature(fx.p1, "vrm")["weight"] = -0.1
    with pytest.raises(ProfileError) as e:
        rank(fx.target, fx.candidates(), fx.p1, fx.defs)
    assert e.value.code == "negative_weight"


def test_rejects_zero_weight_sum(fx):
    for f in fx.p1["features"]:
        f["weight"] = 0
    with pytest.raises(ProfileError) as e:
        rank(fx.target, fx.candidates(), fx.p1, fx.defs)
    assert e.value.code == "zero_internal_weight_sum"


def test_rejects_zero_dimension_weight_sum(fx):
    fx.p1["dimension_weights"] = {"terrain": 0}
    with pytest.raises(ProfileError) as e:
        rank(fx.target, fx.candidates(), fx.p1, fx.defs)
    assert e.value.code == "zero_weight_sum"


@pytest.mark.parametrize("tau", [0, -1, -0.0])
def test_rejects_non_positive_tau(fx, tau):
    fx.pfeature(fx.p1, "slope_deg")["tau"] = tau
    with pytest.raises(ProfileError) as e:
        rank(fx.target, fx.candidates(), fx.p1, fx.defs)
    assert e.value.code == "non_positive_tau"


def test_strict_json_loader_rejects_nan_literal():
    with pytest.raises(InvalidRequestError):
        loads_strict('{"value": NaN}')


def test_inconsistent_measurement_status_rejected(fx):
    m = fx.measurement(fx.site("A"), "vrm")
    m["status"] = "missing"  # but value 0.05 still present
    with pytest.raises(InvalidRequestError) as e:
        rank(fx.target, fx.candidates(), fx.p1, fx.defs)
    assert e.value.code == "inconsistent_measurement"


# ----------------------------------------------------------------- check 4: units and protocols


def test_candidate_unit_mismatch_is_incompatible_with_reason(fx):
    fx.measurement(fx.site("A"), "slope_deg")["unit"] = "rad"
    result = rank(fx.target, fx.candidates(), fx.p1, fx.defs)
    assert "synthetic_A" not in result.order()
    [a] = [r for r in result.excluded if r.candidate_id == "synthetic_A"]
    assert a.category == "incompatible"
    comp = a.components[0]
    assert comp.status == "incompatible" and comp.reason_code == "unit_mismatch"
    assert "rad" in comp.message and "deg" in comp.message


def test_target_unit_mismatch_is_request_error(fx):
    fx.measurement(fx.target, "relief_m")["unit"] = "km"
    with pytest.raises(ProfileError) as e:
        rank(fx.target, fx.candidates(), fx.p1, fx.defs)
    assert e.value.code == "target_unit_mismatch"


def test_tau_unit_must_be_canonical(fx):
    fx.pfeature(fx.p1, "relief_m")["tau_unit"] = "km"
    with pytest.raises(ProfileError) as e:
        rank(fx.target, fx.candidates(), fx.p1, fx.defs)
    assert e.value.code == "tau_unit_mismatch"


def test_method_mismatch_is_incompatible(fx):
    fx.measurement(fx.site("B"), "vrm")["method_id"] = "other_vrm_method"
    r = compare(fx.target, fx.site("B"), fx.p1, fx.defs)
    assert r.category == "incompatible"
    vrm = r.components[1]
    assert vrm.reason_code == "protocol_mismatch:method_id"
    assert vrm.similarity is None
    # The other components are still reported, with observed score over them.
    assert r.score_observed == pytest.approx((0.8 * 1.0 + 0.1 * 0.5) / 0.9)


def test_spatial_support_mismatch_is_incompatible_even_if_numerically_similar(fx):
    fx.measurement(fx.site("A"), "slope_deg")["spatial_support"] = "dem_5m_window3"
    r = compare(fx.target, fx.site("A"), fx.p1, fx.defs)
    assert r.components[0].reason_code == "protocol_mismatch:spatial_support"


def test_declared_equivalence_is_accepted(fx):
    fx.measurement(fx.site("A"), "slope_deg")["spatial_support"] = "synthetic_support_v0_alias"
    fx.defs[0]["comparability_protocol"]["equivalent_values"] = {
        "spatial_support": [["synthetic_support_v0", "synthetic_support_v0_alias"]]
    }
    r = compare(fx.target, fx.site("A"), fx.p1, fx.defs)
    assert r.category == "complete" and r.score_observed == pytest.approx(0.82)


def test_missing_metadata_means_comparability_pending(fx):
    fx.measurement(fx.site("A"), "vrm")["method_version"] = None
    result = rank(fx.target, fx.candidates(), fx.p1, fx.defs)
    [a] = [r for r in result.partial if r.candidate_id == "synthetic_A"]
    assert a.components[1].status == "comparability_pending"


def test_body_policy_is_configured_per_feature_not_hardcoded(fx):
    for d in fx.defs:
        d["comparability_protocol"]["cross_body_comparable"] = False
    r = compare(fx.target, fx.site("A"), fx.p1, fx.defs)
    assert r.category == "incompatible"
    assert all(c.reason_code == "body_not_comparable" for c in r.components)
    # Same data, bodies equal -> comparable again (no name-based logic).
    fx.site("A")["body"] = fx.target["body"]
    assert compare(fx.target, fx.site("A"), fx.p1, fx.defs).category == "complete"


def test_quality_flagged_value_is_not_used(fx):
    fx.measurement(fx.site("A"), "vrm")["status"] = "flagged"
    r = compare(fx.target, fx.site("A"), fx.p1, fx.defs)
    assert r.category == "partial" and r.components[1].reason_code == "quality_flagged"


# ----------------------------------------------------------------- check 8: zero weight, required, target


def test_zero_weight_feature_does_not_block_ranking(fx):
    fx.pfeature(fx.p1, "vrm")["weight"] = 0
    fx.pfeature(fx.p1, "relief_m")["weight"] = 0
    result = rank(fx.target, fx.candidates(), fx.p1, fx.defs)
    # Only slope counts now: C becomes complete (slope identical), D still 0.
    assert result.order()[:2] == ["synthetic_B", "synthetic_C"]  # tie at 1.0, broken by id
    c = next(e.result for e in result.ranked if e.result.candidate_id == "synthetic_C")
    info = [comp for comp in c.components if comp.status != "compared"]
    assert all(not comp.blocking for comp in info)
    assert any(r.startswith("informational:") for r in c.reasons)
    a = next(e.result for e in result.ranked if e.result.candidate_id == "synthetic_A")
    # Zero-weight components are still computed and shown, contributing 0.
    assert a.components[1].similarity == pytest.approx(0.9) and a.components[1].contribution == 0.0


def test_required_feature_with_zero_weight_still_required(fx):
    fx.pfeature(fx.p1, "vrm")["weight"] = 0
    fx.pfeature(fx.p1, "relief_m")["weight"] = 0
    fx.p1["required_features"] = ["vrm"]
    result = rank(fx.target, fx.candidates(), fx.p1, fx.defs)
    assert "synthetic_C" not in result.order()
    [c] = result.partial
    assert c.candidate_id == "synthetic_C"
    assert any("required feature" in r for r in c.reasons)
    # Coverage counts weight only; C has full weighted coverage but is not rankable.
    assert c.coverage == 1.0 and not c.rankable


def test_target_without_active_feature_is_profile_error(fx):
    m = fx.measurement(fx.target, "vrm")
    m["value"], m["status"] = None, "missing"
    with pytest.raises(ProfileError) as e:
        rank(fx.target, fx.candidates(), fx.p1, fx.defs)
    assert e.value.code == "target_missing_feature"
    assert "does not deactivate it automatically" in e.value.message


def test_target_without_zero_weight_active_feature_is_still_error(fx):
    fx.pfeature(fx.p1, "vrm")["weight"] = 0
    fx.target["measurements"] = [m for m in fx.target["measurements"] if m["feature_id"] != "vrm"]
    with pytest.raises(ProfileError):
        rank(fx.target, fx.candidates(), fx.p1, fx.defs)


def test_constraint_violation_cannot_be_compensated(fx):
    fx.p1["constraints"] = [
        {"id": "max_relief_gap", "feature_id": "relief_m", "type": "max_abs_difference", "limit": 20, "unit": "m"}
    ]
    result = rank(fx.target, fx.candidates(), fx.p1, fx.defs)
    # B has the best weighted score (0.91) but relief differs by 50 m > 20 m.
    assert result.order() == ["synthetic_A"]
    excluded = {r.candidate_id: r for r in result.excluded}
    assert excluded["synthetic_B"].category == "requirement_not_met"
    assert excluded["synthetic_B"].score_observed == pytest.approx(0.91)
    assert excluded["synthetic_D"].category == "requirement_not_met"
    # C cannot be evaluated (relief missing): insufficient info, not failure.
    [c] = result.partial
    assert c.constraints[0].status == "unevaluable"


def test_constraint_on_zero_weight_feature_blocks_when_missing(fx):
    fx.pfeature(fx.p1, "relief_m")["weight"] = 0
    fx.pfeature(fx.p1, "vrm")["weight"] = 0
    fx.p1["constraints"] = [{"id": "relief_max", "feature_id": "relief_m", "type": "max_value", "limit": 500, "unit": "m"}]
    result = rank(fx.target, fx.candidates(), fx.p1, fx.defs)
    assert "synthetic_C" not in result.order()


def test_no_complete_candidates_is_reported(fx):
    result = rank(fx.target, [fx.site("C")], fx.p1, fx.defs)
    assert result.ranked == ()
    assert any(w.startswith("no_complete_candidates") for w in result.warnings)


def test_unknown_feature_and_required_not_active(fx):
    fx.p1["required_features"] = ["albedo"]
    with pytest.raises(ProfileError) as e:
        rank(fx.target, fx.candidates(), fx.p1, fx.defs)
    assert e.value.code == "required_not_active"


def test_profile_target_must_match(fx):
    fx.p1["target_id"] = "another_target"
    with pytest.raises(ProfileError) as e:
        rank(fx.target, fx.candidates(), fx.p1, fx.defs)
    assert e.value.code == "target_mismatch"


def test_duplicate_candidate_ids_rejected(fx):
    with pytest.raises(InvalidRequestError):
        rank(fx.target, [fx.site("A"), fx.site("A")], fx.p1, fx.defs)


# ----------------------------------------------------------------- check 10: data mode, JSON


def test_mixing_real_and_synthetic_is_rejected(fx):
    fx.site("B")["data_mode"] = "real"
    with pytest.raises(DataModeError) as e:
        rank(fx.target, fx.candidates(), fx.p1, fx.defs)
    assert e.value.details["candidates"] == ["synthetic_B"]
    with pytest.raises(DataModeError):
        compare(fx.target, fx.site("B"), fx.p1, fx.defs)


def test_results_serialise_to_strict_json_with_nulls(fx):
    result = rank(fx.target, fx.candidates(), fx.p1, fx.defs)
    text = result.to_json()

    def no_constants(name):
        raise AssertionError(f"non-standard JSON constant {name}")

    data = json.loads(text, parse_constant=no_constants)
    c = data["partial"][0]
    vrm = c["components"][1]
    assert vrm["similarity"] is None and vrm["delta"] is None
    assert data["data_mode"] == "synthetic" and data["calibration_status"] == "uncalibrated"
    assert "NaN" not in text and "Infinity" not in text
