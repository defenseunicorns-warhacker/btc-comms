"""
End-to-end API tests via FastAPI TestClient.

Covers the HTTP surface that nothing else tested: event ingest, signature
enforcement (STRICT_SIGNING), token auth (API_TOKEN), tamper→verify-fails,
the MMR proof endpoint, and the /keys metadata-only guarantee.
"""

import importlib

import pytest

try:
    from fastapi.testclient import TestClient
    _HAVE_TESTCLIENT = True
except Exception:
    _HAVE_TESTCLIENT = False

pytestmark = pytest.mark.skipif(not _HAVE_TESTCLIENT, reason="httpx/TestClient not installed")


def _make_app(tmp_path, monkeypatch, **env):
    """Reload the module chain with fresh env + isolated DB/keys, return (client, modules)."""
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


def _signed_body(source_id, payload, keys_dir):
    import signing
    from ledger import canonical_json
    key, key_id = signing.get_or_create_keypair(source_id)
    sig = signing.sign(key, source_id, canonical_json(payload))
    return {"source_id": source_id, "payload": payload, "signature": sig, "key_id": key_id}


# ---------------------------------------------------------------------------
# Basic ingest + verify
# ---------------------------------------------------------------------------

def test_seed_and_verify_ok(client):
    r = client.post("/seed?n=10")
    assert r.status_code == 200
    assert r.json()["seeded"] == 10

    v = client.get("/verify").json()
    assert v["ok"] is True
    assert v["verified_entries"] >= 11   # genesis + 10


def test_unsigned_event_accepted_by_default(client):
    r = client.post("/events", json={"source_id": "anon", "payload": {"event": "x"}})
    assert r.status_code == 201
    assert "entry_hash" in r.json()


def test_tamper_breaks_verify(client):
    client.post("/seed?n=5")
    assert client.get("/verify").json()["ok"] is True

    client.post("/tamper", json={"seq": 3, "field": "payload", "new_value": "HACKED"})
    v = client.get("/verify").json()
    assert v["ok"] is False
    assert v["broken_at"] == 3


def test_proof_endpoint_valid(client):
    client.post("/seed?n=6")
    r = client.get("/entries/3/proof")
    assert r.status_code == 200
    body = r.json()
    assert body["valid"] is True
    assert body["proof"]["type"] == "mmr"
    assert body["mmr_root"] is not None


def test_proof_404_for_missing(client):
    assert client.get("/entries/999/proof").status_code == 404


# ---------------------------------------------------------------------------
# Signature handling
# ---------------------------------------------------------------------------

def test_signed_event_accepted(client, tmp_path):
    body = _signed_body("agent-a", {"event": "x"}, tmp_path / "keys")
    r = client.post("/events", json=body)
    assert r.status_code == 201


def test_forged_signature_rejected(client, tmp_path):
    body = _signed_body("agent-a", {"event": "x"}, tmp_path / "keys")
    body["payload"] = {"event": "DIFFERENT"}   # signature no longer matches payload
    r = client.post("/events", json=body)
    assert r.status_code == 403


def test_impersonation_rejected_at_api(client, tmp_path):
    import signing
    from ledger import canonical_json
    attacker_key, attacker_kid = signing.get_or_create_keypair("attacker")
    signing.get_or_create_keypair("victim")
    payload = {"event": "fire"}
    forged = signing.sign(attacker_key, "victim", canonical_json(payload))
    r = client.post("/events", json={
        "source_id": "victim", "payload": payload,
        "signature": forged, "key_id": attacker_kid,
    })
    assert r.status_code == 403


def test_keys_endpoint_strips_pem(client, tmp_path):
    _signed_body("agent-a", {"event": "x"}, tmp_path / "keys")  # enrol a key
    r = client.get("/keys").json()
    for info in r.values():
        assert "public_key_pem" not in info


# ---------------------------------------------------------------------------
# Strict signing
# ---------------------------------------------------------------------------

def test_strict_signing_rejects_unsigned(tmp_path, monkeypatch):
    api = _make_app(tmp_path, monkeypatch, STRICT_SIGNING="true")
    with TestClient(api.app) as c:
        r = c.post("/events", json={"source_id": "anon", "payload": {"event": "x"}})
        assert r.status_code == 403


def test_strict_signing_accepts_signed(tmp_path, monkeypatch):
    api = _make_app(tmp_path, monkeypatch, STRICT_SIGNING="true")
    with TestClient(api.app) as c:
        body = _signed_body("agent-a", {"event": "x"}, tmp_path / "keys")
        r = c.post("/events", json=body)
        assert r.status_code == 201


# ---------------------------------------------------------------------------
# Token auth
# ---------------------------------------------------------------------------

def test_token_required_when_set(tmp_path, monkeypatch):
    api = _make_app(tmp_path, monkeypatch, API_TOKEN="s3cret")
    with TestClient(api.app) as c:
        # No token → 401
        assert c.post("/events", json={"source_id": "a", "payload": {"x": 1}}).status_code == 401
        # Wrong token → 401
        assert c.post("/events", json={"source_id": "a", "payload": {"x": 1}},
                      headers={"X-API-Key": "wrong"}).status_code == 401
        # Correct token → 201
        assert c.post("/events", json={"source_id": "a", "payload": {"x": 1}},
                      headers={"Authorization": "Bearer s3cret"}).status_code == 201


def test_readonly_endpoints_open_without_token(tmp_path, monkeypatch):
    api = _make_app(tmp_path, monkeypatch, API_TOKEN="s3cret")
    with TestClient(api.app) as c:
        assert c.get("/verify").status_code == 200
        assert c.get("/entries").status_code == 200
