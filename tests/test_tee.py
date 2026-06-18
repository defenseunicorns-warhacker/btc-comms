"""
Tests for TEE attestation integration (src/tee.py).
"""

import importlib
import os

import pytest


@pytest.fixture
def tee(monkeypatch):
    """Fresh tee module with MOCK_TEE=true."""
    monkeypatch.setenv("MOCK_TEE", "true")
    import tee as tee_mod
    importlib.reload(tee_mod)
    return tee_mod


@pytest.fixture
def tee_no_mock(monkeypatch):
    """Fresh tee module with MOCK_TEE=false (no hardware available in tests)."""
    monkeypatch.setenv("MOCK_TEE", "false")
    import tee as tee_mod
    importlib.reload(tee_mod)
    return tee_mod


def test_mock_attestation_returns_tee_attestation(tee):
    att = tee.collect_attestation()
    assert att.tee_type == "MOCK"


def test_mock_attestation_has_measurement(tee):
    att = tee.collect_attestation()
    assert att.measurement
    assert len(att.measurement) == 64   # sha256 hex


def test_mock_attestation_binds_report_data(tee):
    att = tee.collect_attestation(report_data=b"sha256:abc123")
    assert att.report_data == b"sha256:abc123".hex()


def test_mock_attestation_empty_report_data(tee):
    att = tee.collect_attestation(report_data=b"")
    assert att.report_data == ""


def test_mock_attestation_measurement_stable_within_call(tee):
    a1 = tee.collect_attestation()
    a2 = tee.collect_attestation()
    assert a1.measurement == a2.measurement


def test_mock_attestation_different_report_data_same_measurement(tee):
    a1 = tee.collect_attestation(report_data=b"data-a")
    a2 = tee.collect_attestation(report_data=b"data-b")
    # measurement depends on host/pid/hour, not on report_data
    assert a1.measurement == a2.measurement
    assert a1.report_data != a2.report_data


def test_no_tee_raises_when_no_hardware(tee_no_mock):
    # No /dev/tdx_guest or /dev/sev-guest in the test environment
    # and MOCK_TEE is off — must raise TeeError.
    with pytest.raises(tee_no_mock.TeeError, match="No TEE available"):
        tee_no_mock.collect_attestation()


def test_build_attestation_payload_drops_nones(tee):
    att = tee.collect_attestation()
    payload = tee.build_attestation_payload(att)
    assert payload["tee_type"] == "MOCK"
    assert payload["_schema"] == "tee_attestation_v1"
    assert "measurement" in payload
    assert "report_data" in payload
    # platform is "mock" (not None) so it should be present
    assert payload.get("platform") == "mock"


def test_build_attestation_payload_schema(tee):
    att = tee.collect_attestation(report_data=b"model-hash")
    payload = tee.build_attestation_payload(att)
    required = {"_schema", "tee_type", "measurement", "report_data", "quote"}
    assert required.issubset(payload.keys())


def test_tee_error_is_runtime_error(tee):
    assert issubclass(tee.TeeError, RuntimeError)
