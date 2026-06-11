"""
Tests for Ed25519 per-agent signing and the identity-binding anti-impersonation
check. These cover the core security claim: source_id is cryptographically
attributable, not just a string.
"""

import importlib
import json

import pytest


@pytest.fixture
def signing(tmp_path, monkeypatch):
    """Fresh signing module with an isolated key directory per test."""
    monkeypatch.setenv("KEYS_DIR", str(tmp_path / "keys"))
    import signing as signing_mod
    importlib.reload(signing_mod)
    return signing_mod


@pytest.fixture
def canonical():
    from ledger import canonical_json
    return canonical_json


def test_roundtrip_verifies(signing, canonical):
    key, key_id = signing.get_or_create_keypair("agent-a")
    payload = canonical({"event": "x", "v": 1})
    sig = signing.sign(key, "agent-a", payload)
    assert signing.verify_signature(sig, key_id, "agent-a", payload) is True


def test_tampered_payload_rejected(signing, canonical):
    key, key_id = signing.get_or_create_keypair("agent-a")
    sig = signing.sign(key, "agent-a", canonical({"event": "x"}))
    # Verify against a different payload
    assert signing.verify_signature(sig, key_id, "agent-a", canonical({"event": "y"})) is False


def test_unknown_key_rejected(signing, canonical):
    key, _ = signing.get_or_create_keypair("agent-a")
    sig = signing.sign(key, "agent-a", canonical({"event": "x"}))
    assert signing.verify_signature(sig, "deadbeef" * 4, "agent-a", canonical({"event": "x"})) is False


def test_impersonation_rejected(signing, canonical):
    """
    An attacker enrols their OWN key (as 'attacker'), then signs a message
    claiming to be 'victim' and submits source_id='victim'. The math is valid
    for the attacker's key, but the registry binds that key to 'attacker',
    so verification MUST fail.
    """
    attacker_key, attacker_kid = signing.get_or_create_keypair("attacker")
    signing.get_or_create_keypair("victim")  # victim has their own separate key

    payload = canonical({"event": "fire", "action": "ENGAGE"})
    forged_sig = signing.sign(attacker_key, "victim", payload)   # sign as 'victim'

    # Submit with attacker's key_id but claiming to be victim
    assert signing.verify_signature(forged_sig, attacker_kid, "victim", payload) is False


def test_key_id_is_stable(signing):
    _, kid1 = signing.get_or_create_keypair("agent-a")
    _, kid2 = signing.get_or_create_keypair("agent-a")   # reload existing
    assert kid1 == kid2


def test_registry_has_no_private_material(signing, tmp_path):
    signing.get_or_create_keypair("agent-a")
    registry = json.loads((tmp_path / "keys" / "registry.json").read_text())
    for entry in registry.values():
        assert "private" not in json.dumps(entry).lower()
        assert "public_key_pem" in entry
