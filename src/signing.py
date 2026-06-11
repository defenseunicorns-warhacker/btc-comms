"""
Per-agent Ed25519 signing for the accountability ledger.

Every source agent has a keypair. The agent signs its payload before
submitting; the recorder verifies the signature at ingest. This means
source_id is no longer just a string — it is a cryptographically
attributable identity.

Production upgrade path (same API, swap the key store):
  File keys (this implementation) → TPM-backed keys → HSM-backed keys → CAC/PIV
  The sign() / verify_signature() interface stays identical either way.

Key storage layout:
  keys/
    <source_id>.pem    private key  (recorder/agent side, keep secret)
    <source_id>.pub    public key   (recorder side, shared freely)

Key registry (keys/registry.json):
  Maps key_id (fingerprint) → {source_id, public_key_pem, created_at}
  In production this is a PKI / LDAP / CAC directory.
"""

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from Cryptodome.PublicKey import ECC
from Cryptodome.Signature import eddsa


KEYS_DIR = Path(os.getenv("KEYS_DIR", "keys"))
REGISTRY_FILE = KEYS_DIR / "registry.json"


# ---------------------------------------------------------------------------
# Key management
# ---------------------------------------------------------------------------

def generate_keypair(source_id: str) -> dict:
    """
    Generate a new Ed25519 keypair for source_id. Saves to KEYS_DIR.
    Returns {key_id, source_id, public_key_pem}.
    """
    KEYS_DIR.mkdir(parents=True, exist_ok=True)
    key = ECC.generate(curve="Ed25519")

    private_pem = key.export_key(format="PEM")
    public_pem = key.public_key().export_key(format="PEM")
    key_id = _key_id(key.public_key())

    priv_path = KEYS_DIR / f"{source_id}.pem"
    pub_path = KEYS_DIR / f"{source_id}.pub"
    priv_path.write_text(private_pem)
    pub_path.write_text(public_pem)
    priv_path.chmod(0o600)

    # Register in registry
    registry = _load_registry()
    registry[key_id] = {
        "source_id": source_id,
        "public_key_pem": public_pem,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    _save_registry(registry)

    return {"key_id": key_id, "source_id": source_id, "public_key_pem": public_pem}


def get_or_create_keypair(source_id: str) -> tuple[ECC.EccKey, str]:
    """
    Load existing keypair for source_id, generating one if it doesn't exist.
    Returns (private_key, key_id).
    """
    priv_path = KEYS_DIR / f"{source_id}.pem"
    if priv_path.exists():
        key = ECC.import_key(priv_path.read_text())
        return key, _key_id(key.public_key())
    info = generate_keypair(source_id)
    key = ECC.import_key((KEYS_DIR / f"{source_id}.pem").read_text())
    return key, info["key_id"]


def get_public_key(key_id: str) -> Optional[ECC.EccKey]:
    """Look up a public key by key_id. Returns None if unknown."""
    registry = _load_registry()
    entry = registry.get(key_id)
    if not entry:
        return None
    return ECC.import_key(entry["public_key_pem"])


def list_keys() -> dict:
    """Return the full key registry (public info only)."""
    return _load_registry()


# ---------------------------------------------------------------------------
# Sign / verify
# ---------------------------------------------------------------------------

def sign(private_key: ECC.EccKey, source_id: str, payload_canonical: bytes) -> str:
    """
    Sign (source_id + payload_canonical) with private_key.
    Returns hex-encoded signature.

    The message binds source_id so a valid signature for agent A
    cannot be replayed as agent B's signature.
    """
    message = source_id.encode("utf-8") + b":" + payload_canonical
    signer = eddsa.new(private_key, "rfc8032")
    return signer.sign(message).hex()


def verify_signature(signature_hex: str, key_id: str,
                     source_id: str, payload_canonical: bytes) -> bool:
    """
    Verify that signature_hex is a valid Ed25519 signature over
    (source_id + payload_canonical) by the key registered as key_id.
    Returns False (not raises) on any failure.

    Identity binding: the key_id must be registered to *this* source_id.
    Without this check an attacker could enrol their own key under any
    source_id and sign "victim:payload" — the math would verify but the
    attribution would be forged. The registry is the trust anchor.
    """
    registry = _load_registry()
    entry = registry.get(key_id)
    if entry is None:
        return False
    if entry.get("source_id") != source_id:
        # Key is registered to a different identity — reject (anti-impersonation)
        return False
    try:
        public_key = ECC.import_key(entry["public_key_pem"])
        message = source_id.encode("utf-8") + b":" + payload_canonical
        sig_bytes = bytes.fromhex(signature_hex)
        verifier = eddsa.new(public_key, "rfc8032")
        verifier.verify(message, sig_bytes)
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _key_id(public_key: ECC.EccKey) -> str:
    """SHA-256 fingerprint of the DER-encoded public key (first 16 hex chars)."""
    der = public_key.export_key(format="DER")
    return hashlib.sha256(der).hexdigest()[:32]


def _load_registry() -> dict:
    if REGISTRY_FILE.exists():
        return json.loads(REGISTRY_FILE.read_text())
    return {}


def _save_registry(registry: dict):
    REGISTRY_FILE.write_text(json.dumps(registry, indent=2))
