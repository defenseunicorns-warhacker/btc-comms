"""
Tests for the demo/clarity features added on top of the core ledger:

  - the /seed path now signs each event (visible-signing demo)
  - /demo/impersonate exercises the real anti-impersonation ingest check
  - /agent/heartbeat + /agent/status DDIL connectivity telemetry
  - the example agent scripts compile

Shares the reload-with-isolated-env pattern from test_api.py.
"""

import importlib
import os
import py_compile

import pytest

try:
    from fastapi.testclient import TestClient
    _HAVE_TESTCLIENT = True
except Exception:
    _HAVE_TESTCLIENT = False

pytestmark = pytest.mark.skipif(not _HAVE_TESTCLIENT, reason="httpx/TestClient not installed")


def _make_app(tmp_path, monkeypatch, **env):
    monkeypatch.setenv("KEYS_DIR", str(tmp_path / "keys"))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "ledger.db"))
    monkeypatch.setenv("MOCK_ANCHOR", "true")
    monkeypatch.setenv("MOCK_CONFIRM_DELAY", "1")
    monkeypatch.setenv("DEMO_MODE", "true")
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    import signing, verify, anchor, ledger, api
    for mod in (ledger, signing, verify, anchor, api):
        importlib.reload(mod)
    return api


@pytest.fixture
def client(tmp_path, monkeypatch):
    api = _make_app(tmp_path, monkeypatch)
    with TestClient(api.app) as c:
        yield c


# ---------------------------------------------------------------------------
# Seeded events are signed (visible-signing demo path)
# ---------------------------------------------------------------------------

def test_seeded_events_are_signed(client):
    client.post("/seed?n=10")
    v = client.get("/verify").json()
    assert v["ok"] is True
    # Only genesis (seq 0, source "system") should be unsigned; the 10 seeded are signed.
    assert v["unsigned_entries"] == 1
    assert v["invalid_signatures"] == []

    entries = client.get("/entries").json()
    seeded = [e for e in entries if e["seq"] > 0]
    assert len(seeded) == 10
    assert all(e.get("signature") and e.get("key_id") for e in seeded)


# ---------------------------------------------------------------------------
# /info JSON endpoint (the dashboard reads feature flags from here, since
# `/` serves the HTML dashboard — regression guard for that bug)
# ---------------------------------------------------------------------------

def test_info_returns_json_flags(client):
    r = client.get("/info")
    assert r.status_code == 200
    body = r.json()
    assert body["demo_mode"] is True       # fixture sets DEMO_MODE=true
    assert body["mock_anchor"] is True
    assert "strict_signing" in body


def test_info_reflects_non_demo(tmp_path, monkeypatch):
    api = _make_app(tmp_path, monkeypatch, DEMO_MODE="false")
    with TestClient(api.app) as c:
        assert c.get("/info").json()["demo_mode"] is False


# ---------------------------------------------------------------------------
# Impersonation is rejected by the real ingest check
# ---------------------------------------------------------------------------

def test_impersonation_rejected(client):
    client.post("/seed?n=10")  # enroll the demo identities
    r = client.post("/demo/impersonate")
    assert r.status_code == 200
    body = r.json()
    assert body["available"] is True
    assert body["rejected"] is True
    assert body["attacker"] != body["victim"]
    assert body["attacker"] in body["reason"] and body["victim"] in body["reason"]


def test_impersonation_disabled_outside_demo(tmp_path, monkeypatch):
    api = _make_app(tmp_path, monkeypatch, DEMO_MODE="false")
    with TestClient(api.app) as c:
        assert c.post("/demo/impersonate").status_code == 403
        assert c.post("/seed?n=3").status_code == 403
        assert c.post("/tamper", json={"seq": 1, "new_value": "x"}).status_code == 403


def test_legitimate_signature_accepted(client):
    """Positive control: a key signing as its own enrolled identity is accepted —
    proving the impersonation rejection isn't just verify_signature always failing."""
    import signing
    from ledger import canonical_json
    payload = {"event": "ok"}
    key, key_id = signing.get_or_create_keypair("agent-self")
    sig = signing.sign(key, "agent-self", canonical_json(payload))
    r = client.post("/events", json={
        "source_id": "agent-self", "payload": payload, "signature": sig, "key_id": key_id,
    })
    assert r.status_code == 201


# ---------------------------------------------------------------------------
# REQUIRE_PROVISIONED_KEYS — the recorder honors only authority-provisioned keys
# (the hardening that closes the self-enrollment / TOFU trust gap)
# ---------------------------------------------------------------------------

def test_info_reflects_require_provisioned_keys(tmp_path, monkeypatch):
    api = _make_app(tmp_path, monkeypatch, REQUIRE_PROVISIONED_KEYS="true")
    with TestClient(api.app) as c:
        assert c.get("/info").json()["require_provisioned_keys"] is True


def test_provisioned_required_rejects_self_enrolled(tmp_path, monkeypatch):
    """A valid signature from a self-enrolled (TOFU) key is rejected at ingest."""
    api = _make_app(tmp_path, monkeypatch, REQUIRE_PROVISIONED_KEYS="true")
    import signing
    from ledger import canonical_json
    with TestClient(api.app) as c:
        payload = {"event": "x"}
        key, key_id = signing.get_or_create_keypair("tofu-agent")     # self-enrolled
        sig = signing.sign(key, "tofu-agent", canonical_json(payload))
        r = c.post("/events", json={
            "source_id": "tofu-agent", "payload": payload, "signature": sig, "key_id": key_id,
        })
        assert r.status_code == 403


def test_provisioned_required_accepts_authority_key(tmp_path, monkeypatch):
    """A key issued by the provisioning authority is accepted under the gate."""
    api = _make_app(tmp_path, monkeypatch, REQUIRE_PROVISIONED_KEYS="true")
    import signing
    from ledger import canonical_json
    with TestClient(api.app) as c:
        signing.provision_keypair("authorized-agent")                 # authority enrollment
        key, key_id = signing.get_or_create_keypair("authorized-agent")
        payload = {"event": "x"}
        sig = signing.sign(key, "authorized-agent", canonical_json(payload))
        r = c.post("/events", json={
            "source_id": "authorized-agent", "payload": payload, "signature": sig, "key_id": key_id,
        })
        assert r.status_code == 201


def test_provisioned_required_rejects_unsigned(tmp_path, monkeypatch):
    """The gate implies signing: unsigned events are rejected outright."""
    api = _make_app(tmp_path, monkeypatch, REQUIRE_PROVISIONED_KEYS="true")
    with TestClient(api.app) as c:
        r = c.post("/events", json={"source_id": "x", "payload": {"event": "y"}})
        assert r.status_code == 403


# ---------------------------------------------------------------------------
# DDIL connectivity heartbeat telemetry
# ---------------------------------------------------------------------------

def test_agent_heartbeat_and_status(client):
    assert client.get("/agent/status").json() == []

    client.post("/agent/heartbeat", json={"source_id": "edge-sensor", "buffered": 5, "key_id": "abc123"})
    client.post("/agent/heartbeat", json={"source_id": "doc-agent", "buffered": 0})

    status = client.get("/agent/status").json()
    by_id = {a["source_id"]: a for a in status}
    assert by_id["edge-sensor"]["buffered"] == 5
    assert by_id["doc-agent"]["buffered"] == 0
    assert "ts" in by_id["edge-sensor"]

    # A later heartbeat overwrites the prior state for that agent.
    client.post("/agent/heartbeat", json={"source_id": "edge-sensor", "buffered": 0})
    status = client.get("/agent/status").json()
    by_id = {a["source_id"]: a for a in status}
    assert by_id["edge-sensor"]["buffered"] == 0


def test_negative_buffered_is_clamped(client):
    client.post("/agent/heartbeat", json={"source_id": "x", "buffered": -7})
    by_id = {a["source_id"]: a for a in client.get("/agent/status").json()}
    assert by_id["x"]["buffered"] == 0


# ---------------------------------------------------------------------------
# Example agent scripts compile (guards against syntax errors)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("script", [
    "demo_agent.py", "file_agent.py", "llm_agent.py", "ddil_demo.py",
])
def test_example_agents_compile(script):
    path = os.path.join(os.path.dirname(__file__), "..", "examples", script)
    py_compile.compile(path, doraise=True)
