"""
Tests for the ROE (Rules of Engagement) structured schema and validation.
"""

import pytest


def _full_decision_kwargs():
    return dict(
        decision_type="ENGAGE_READY",
        human_authorized=True,
        operator_id="OP-441",
        target_id="T-0091",
        ai_confidence=0.94,
        roe_reference="ROE-ALPHA-7",
        information_state={"threat_class": "UAS"},
        time_to_authorization_ms=4200,
        geo_location={"lat": 34.05, "lon": -118.24, "alt_m": 120},
        weapon_system_id="WPN-03",
        recommended_action="HOLD_FIRE",
        final_action="HOLD_FIRE",
    )


def test_build_roe_payload_tags_schema():
    from roe_schema import RoEDecision, build_roe_payload
    payload = build_roe_payload(RoEDecision(**_full_decision_kwargs()))
    assert payload["_schema"] == "roe_decision_v1"
    assert payload["_required_fields_present"] is True


def test_complete_payload_validates():
    from roe_schema import RoEDecision, build_roe_payload, validate_roe_payload
    payload = build_roe_payload(RoEDecision(**_full_decision_kwargs()))
    ok, missing = validate_roe_payload(payload)
    assert ok is True
    assert missing == []


def test_missing_field_detected():
    from roe_schema import validate_roe_payload
    payload = {"_schema": "roe_decision_v1", "decision_type": "ENGAGE_READY"}
    ok, missing = validate_roe_payload(payload)
    assert ok is False
    assert "operator_id" in missing
    assert "geo_location" in missing


def test_non_roe_payload_passes():
    from roe_schema import validate_roe_payload
    ok, missing = validate_roe_payload({"event_type": "route_computed", "waypoints": 4})
    assert ok is True
    assert missing == []


def test_human_authorized_false_is_not_missing():
    """human_authorized=False is a valid value, not a missing field."""
    from roe_schema import RoEDecision, build_roe_payload, validate_roe_payload
    kwargs = _full_decision_kwargs()
    kwargs["human_authorized"] = False
    kwargs["operator_id"] = "UNATTENDED"
    payload = build_roe_payload(RoEDecision(**kwargs))
    ok, missing = validate_roe_payload(payload)
    assert ok is True, f"unexpectedly missing: {missing}"


def test_result_payload_schema():
    from roe_schema import RoEEngagementResult, build_result_payload
    result = RoEEngagementResult(
        decision_seq=12, target_id="T-0091", outcome="NEUTRALIZED",
        bda_confidence=0.8, collateral_confirmed=False, duration_ms=3000,
        operator_id="OP-441",
    )
    payload = build_result_payload(result)
    assert payload["_schema"] == "roe_result_v1"
    assert payload["outcome"] == "NEUTRALIZED"
