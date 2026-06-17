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


# ---------------------------------------------------------------------------
# Provisioning gate — closes the TOFU (self-enrollment) trust gap.
# A self-enrolled key is fine for the demo, but a hardened recorder
# (require_provisioned=True) honors only authority-issued keys.
# ---------------------------------------------------------------------------

def test_provisioned_key_accepted_when_required(signing, canonical):
    """A key issued by the provisioning authority verifies under require_provisioned."""
    signing.provision_keypair("agent-prov")
    key, key_id = signing.get_or_create_keypair("agent-prov")   # loads the issued key
    payload = canonical({"event": "x"})
    sig = signing.sign(key, "agent-prov", payload)
    assert signing.verify_signature(sig, key_id, "agent-prov", payload,
                                    require_provisioned=True) is True


def test_auto_enrolled_key_rejected_when_provisioned_required(signing, canonical):
    """A self-enrolled (TOFU) key verifies normally but is rejected once the
    recorder requires provisioned keys — the gap the fix closes."""
    key, key_id = signing.get_or_create_keypair("agent-auto")   # TOFU enrollment
    payload = canonical({"event": "x"})
    sig = signing.sign(key, "agent-auto", payload)
    assert signing.verify_signature(sig, key_id, "agent-auto", payload) is True
    assert signing.verify_signature(sig, key_id, "agent-auto", payload,
                                    require_provisioned=True) is False


def test_auto_enroll_refused_when_disabled(signing, monkeypatch):
    """With ALLOW_AUTO_ENROLL=false a brand-new identity cannot self-enroll."""
    monkeypatch.setenv("ALLOW_AUTO_ENROLL", "false")
    with pytest.raises(signing.EnrollmentError):
        signing.get_or_create_keypair("unprovisioned-agent")


def test_provisioning_works_when_auto_enroll_disabled(signing, monkeypatch, canonical):
    """The authority path still issues keys when self-enrollment is disabled."""
    monkeypatch.setenv("ALLOW_AUTO_ENROLL", "false")
    signing.provision_keypair("authorized-agent")                    # authority action
    key, key_id = signing.get_or_create_keypair("authorized-agent")  # loads existing
    payload = canonical({"event": "x"})
    sig = signing.sign(key, "authorized-agent", payload)
    assert signing.verify_signature(sig, key_id, "authorized-agent", payload,
                                    require_provisioned=True) is True


def test_register_public_key_is_authority(signing, canonical):
    """register_public_key (HSM/CAC path) enrolls an externally-held key as
    authority-provisioned — the private key never leaves the holder."""
    from Cryptodome.PublicKey import ECC
    holder = ECC.generate(curve="Ed25519")                      # private key stays with holder
    pub_pem = holder.public_key().export_key(format="PEM")
    info = signing.register_public_key("hsm-agent", pub_pem)     # authority registers public key
    payload = canonical({"event": "x"})
    sig = signing.sign(holder, "hsm-agent", payload)
    assert signing.verify_signature(sig, info["key_id"], "hsm-agent", payload,
                                    require_provisioned=True) is True


def test_legacy_entry_without_marker_rejected_when_required(signing, canonical):
    """Pre-existing registry entries (no enrolled_via) are treated as un-provisioned."""
    key, key_id = signing.get_or_create_keypair("legacy-agent")
    reg = json.loads(signing.REGISTRY_FILE.read_text())
    reg[key_id].pop("enrolled_via", None)                       # simulate a legacy entry
    signing.REGISTRY_FILE.write_text(json.dumps(reg))
    payload = canonical({"event": "x"})
    sig = signing.sign(key, "legacy-agent", payload)
    assert signing.verify_signature(sig, key_id, "legacy-agent", payload,
                                    require_provisioned=True) is False
