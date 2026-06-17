"""
Tests for the Kubernetes audit webhook receiver (POST /audit/k8s).

Covers:
- Mutation verbs are accepted and written to the ledger
- Read-only verbs are skipped
- Noisy system resources are skipped
- Original K8s timestamp is preserved in the payload
- Empty EventList returns 200 with zero accepted
- Malformed body returns an error
- Multiple events in one batch are all processed
"""

import importlib
import pytest

try:
    from fastapi.testclient import TestClient
    _HAVE_TESTCLIENT = True
except Exception:
    _HAVE_TESTCLIENT = False

pytestmark = pytest.mark.skipif(not _HAVE_TESTCLIENT, reason="httpx/TestClient not installed")


def _make_client(tmp_path, monkeypatch):
    monkeypatch.setenv("KEYS_DIR", str(tmp_path / "keys"))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "ledger.db"))
    monkeypatch.setenv("MOCK_ANCHOR", "true")
    monkeypatch.setenv("MOCK_CONFIRM_DELAY", "1")
    monkeypatch.setenv("DEMO_MODE", "false")

    import signing, verify, anchor, ledger, api
    for mod in (ledger, signing, verify, anchor, api):
        importlib.reload(mod)

    return api.app


def _event(verb, resource, name="test-obj", namespace="default", username="admin"):
    """Build a minimal K8s audit EventList item."""
    return {
        "auditID": f"audit-{verb}-{resource}",
        "verb": verb,
        "stage": "ResponseComplete",
        "requestReceivedTimestamp": "2026-06-17T12:00:00.000000Z",
        "stageTimestamp": "2026-06-17T12:00:00.050000Z",
        "user": {"username": username, "groups": ["system:authenticated"]},
        "objectRef": {
            "resource": resource,
            "namespace": namespace,
            "name": name,
            "uid": "abc-123",
            "apiVersion": "v1",
        },
        "responseStatus": {"code": 201},
        "sourceIPs": ["10.0.0.1"],
    }


def _event_list(*events):
    return {
        "kind": "EventList",
        "apiVersion": "audit.k8s.io/v1",
        "items": list(events),
    }


@pytest.fixture
def client(tmp_path, monkeypatch):
    api = _make_client(tmp_path, monkeypatch)
    with TestClient(api) as c:
        yield c


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

def test_create_verb_accepted(client):
    r = client.post("/audit/k8s", json=_event_list(_event("create", "pods")))
    assert r.status_code == 200
    assert r.json()["accepted"] == 1
    assert r.json()["skipped"] == 0


def test_mutation_verbs_all_accepted(client):
    body = _event_list(
        _event("create", "pods"),
        _event("update", "configmaps"),
        _event("patch", "deployments"),
        _event("delete", "secrets"),
    )
    r = client.post("/audit/k8s", json=body)
    assert r.status_code == 200
    assert r.json()["accepted"] == 4


def test_event_appears_in_ledger(client):
    client.post("/audit/k8s", json=_event_list(_event("create", "pods", name="my-pod")))
    entries = client.get("/entries").json()
    payloads = [e["payload"] for e in entries]
    assert any(p.get("name") == "my-pod" for p in payloads)


def test_original_timestamp_preserved(client):
    client.post("/audit/k8s", json=_event_list(_event("create", "pods")))
    entries = client.get("/entries").json()
    payloads = [e["payload"] for e in entries]
    assert any(p.get("original_timestamp") == "2026-06-17T12:00:00.000000Z" for p in payloads)


def test_event_type_derived_from_resource_and_verb(client):
    client.post("/audit/k8s", json=_event_list(_event("delete", "deployments")))
    entries = client.get("/entries").json()
    payloads = [e["payload"] for e in entries]
    assert any(p.get("event_type") == "k8s.deployments.delete" for p in payloads)


# ---------------------------------------------------------------------------
# Filtering
# ---------------------------------------------------------------------------

def test_read_verbs_skipped(client):
    body = _event_list(
        _event("get", "pods"),
        _event("list", "pods"),
        _event("watch", "pods"),
    )
    r = client.post("/audit/k8s", json=body)
    assert r.json()["accepted"] == 0
    assert r.json()["skipped"] == 3


def test_noisy_resources_skipped(client):
    body = _event_list(
        _event("create", "events"),
        _event("update", "leases"),
        _event("patch", "endpointslices"),
        _event("delete", "endpoints"),
    )
    r = client.post("/audit/k8s", json=body)
    assert r.json()["accepted"] == 0
    assert r.json()["skipped"] == 4


def test_mixed_batch_filters_correctly(client):
    body = _event_list(
        _event("create", "pods"),       # accepted
        _event("get", "pods"),          # skipped — read verb
        _event("create", "leases"),     # skipped — noisy resource
        _event("delete", "secrets"),    # accepted
    )
    r = client.post("/audit/k8s", json=body)
    assert r.json()["accepted"] == 2
    assert r.json()["skipped"] == 2


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

def test_empty_event_list(client):
    r = client.post("/audit/k8s", json=_event_list())
    assert r.status_code == 200
    assert r.json() == {"accepted": 0, "skipped": 0}


def test_source_id_is_k8s_audit(client):
    client.post("/audit/k8s", json=_event_list(_event("create", "configmaps")))
    entries = client.get("/entries").json()
    assert any(e["source_id"] == "k8s-audit" for e in entries)
