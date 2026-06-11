"""
DDIL resilience tests for LedgerClient.

Verifies that events are buffered locally when the recorder is unreachable
and flush — in order — when connectivity returns. This is the air-gap /
jamming survival claim.
"""

import importlib

import pytest


@pytest.fixture
def client_mod(tmp_path, monkeypatch):
    monkeypatch.setenv("KEYS_DIR", str(tmp_path / "keys"))
    monkeypatch.chdir(tmp_path)   # buffer DBs land here
    import signing
    importlib.reload(signing)
    from adapters import client as client_mod
    importlib.reload(client_mod)
    return client_mod


def test_buffers_when_server_unreachable(client_mod):
    # Point at a dead port; async_mode=False so emit tries direct then buffers
    c = client_mod.LedgerClient("http://127.0.0.1:9", source_id="agent-a", async_mode=False)
    c.emit("event", {"x": 1})
    c.emit("event", {"x": 2})
    assert c.buffered_count() == 2


def test_async_mode_buffers_then_drains(client_mod, monkeypatch):
    c = client_mod.LedgerClient("http://127.0.0.1:9", source_id="agent-b", async_mode=True)

    delivered = []

    def fake_post(body):
        delivered.append(body)
        return {"seq": len(delivered), "entry_hash": "x"}

    c.emit("event", {"x": 1})
    c.emit("event", {"x": 2})
    c.emit("event", {"x": 3})
    assert c.buffered_count() == 3

    # "Reconnect": swap in a working transport and let the drain loop run
    monkeypatch.setattr(c, "_post", fake_post)
    c.flush(timeout=5)

    assert c.buffered_count() == 0
    assert len(delivered) == 3
    # Order preserved
    assert [b["payload"]["x"] for b in delivered] == [1, 2, 3]


def test_events_are_signed_when_signing_available(client_mod):
    c = client_mod.LedgerClient("http://127.0.0.1:9", source_id="agent-c", async_mode=False)
    body = c._build_body("event", {"x": 1})
    if client_mod._SIGNING_AVAILABLE:
        assert "signature" in body and "key_id" in body
        # And the signature actually verifies
        import signing
        from ledger import canonical_json
        assert signing.verify_signature(
            body["signature"], body["key_id"], "agent-c", canonical_json(body["payload"])
        )
    else:
        pytest.skip("signing not available in this environment")
