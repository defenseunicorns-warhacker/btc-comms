"""
Anchoring loop: periodically stamps the current ledger head to Bitcoin via
OpenTimestamps, persists the raw calendar proof, and upgrades pending proofs
to confirmed once Bitcoin mines them.

Guarantee framing (accurate, not overstated):
  "Continuous tamper-evidence in real time; externally verifiable, irreversible
   proof up to the most recent confirmed anchor."
Bitcoin confirmation latency is ~10 min first block, ~60 min strong confirmation.

Mock mode (MOCK_ANCHOR=true):
  Stamps return instantly with a local proof blob. After MOCK_CONFIRM_DELAY
  seconds (default 30) the anchor "confirms" at a fake block height so the
  full pending→confirmed flow runs entirely offline.
"""

import io
import json
import logging
import os
import threading
import time
from datetime import datetime, timezone
from typing import Optional

log = logging.getLogger(__name__)

MOCK_CONFIRM_DELAY = int(os.getenv("MOCK_CONFIRM_DELAY", "30"))
# Fake block height base so the demo looks realistic
_MOCK_BLOCK_BASE = 895_000

# When set, _stamp/_upgrade use the real OTS protocol against this calendar URL.
# Point at the mock-calendar service for local dev, or a real OTS calendar for production.
OTS_CALENDAR_URL = os.getenv("OTS_CALENDAR_URL", "").strip()


# ---------------------------------------------------------------------------
# Mock anchor (local demo — no Bitcoin network required)
# ---------------------------------------------------------------------------

def _stamp_mock(hash_hex: str) -> bytes:
    """Return a local mock proof blob immediately. No network required."""
    proof = {
        "mock": True,
        "confirmed": False,
        "stamped_at": time.time(),
        "hash": hash_hex,
        "confirm_after": MOCK_CONFIRM_DELAY,
    }
    log.info("MOCK stamp for %s… (confirms in %ds)", hash_hex[:16], MOCK_CONFIRM_DELAY)
    return json.dumps(proof).encode()


def _upgrade_mock(proof_bytes: bytes, head_hash: str) -> tuple:
    """Confirm the mock proof once MOCK_CONFIRM_DELAY seconds have elapsed."""
    try:
        proof = json.loads(proof_bytes)
        if not proof.get("mock"):
            return proof_bytes, False, None, None
        elapsed = time.time() - proof["stamped_at"]
        if elapsed >= proof.get("confirm_after", MOCK_CONFIRM_DELAY):
            block_height = _MOCK_BLOCK_BASE + (int(proof["stamped_at"]) % 5000)
            proof["confirmed"] = True
            proof["block_height"] = block_height
            log.info("MOCK anchor confirmed at simulated block %d", block_height)
            return json.dumps(proof).encode(), True, block_height, None
        remaining = proof.get("confirm_after", MOCK_CONFIRM_DELAY) - elapsed
        log.debug("MOCK anchor not yet confirmed (%.0fs remaining)", remaining)
        return proof_bytes, False, None, None
    except Exception as exc:
        log.warning("Mock upgrade parse error: %s", exc)
        return proof_bytes, False, None, None


# ---------------------------------------------------------------------------
# OTS helpers (production integration points — wire in the OTS client here)
# ---------------------------------------------------------------------------

def _stamp(hash_hex: str) -> Optional[bytes]:
    """
    Submit hash_hex to an OTS calendar and return serialized proof bytes.

    Uses OTS_CALENDAR_URL when set (point at the local mock-calendar service for dev,
    or a real calendar such as https://alice.btc.calendar.opentimestamps.org for prod).
    Returns None if OTS_CALENDAR_URL is unset or the submission fails — the loop
    will retry on the next stamp interval.

    Proof format stored in the DB:
      {"ots": true, "v": 1, "digest": "<hex>", "calendar_url": "<url>", "timestamp_hex": "<hex>"}
    """
    if not OTS_CALENDAR_URL:
        log.warning("OTS stamp skipped — OTS_CALENDAR_URL not set (set MOCK_ANCHOR=true for simple demo)")
        return None

    try:
        import httpx
        from opentimestamps.core.timestamp import Timestamp
        from opentimestamps.core.serialize import BytesSerializationContext, BytesDeserializationContext

        digest = bytes.fromhex(hash_hex)
        resp = httpx.post(OTS_CALENDAR_URL, content=digest, timeout=10)
        if resp.status_code != 200:
            log.warning("Calendar POST %s returned HTTP %d", OTS_CALENDAR_URL, resp.status_code)
            return None

        calendar_ts = Timestamp.deserialize(BytesDeserializationContext(resp.content), digest)

        ctx = BytesSerializationContext()
        calendar_ts.serialize(ctx)

        proof = {
            "ots": True,
            "v": 1,
            "digest": hash_hex,
            "calendar_url": OTS_CALENDAR_URL,
            "timestamp_hex": ctx.getbytes().hex(),
        }
        log.info("OTS stamp submitted for %s… (pending Bitcoin confirmation)", hash_hex[:16])
        return json.dumps(proof).encode()
    except Exception as exc:
        log.warning("OTS stamp error: %s", exc)
        return None


def _upgrade(proof_bytes: bytes, head_hash: str) -> tuple[Optional[bytes], bool, Optional[int], Optional[str]]:
    """
    Poll the calendar for a confirmed Bitcoin attestation.
    Returns (new_proof_bytes, is_confirmed, block_height, block_time).
    """
    try:
        proof = json.loads(proof_bytes)
    except Exception:
        return proof_bytes, False, None, None

    if not proof.get("ots"):
        return proof_bytes, False, None, None

    try:
        import httpx
        from opentimestamps.core.timestamp import Timestamp
        from opentimestamps.core.notary import BitcoinBlockHeaderAttestation
        from opentimestamps.core.serialize import BytesSerializationContext, BytesDeserializationContext

        digest = bytes.fromhex(proof["digest"])
        calendar_url = proof["calendar_url"]

        ts = Timestamp.deserialize(
            BytesDeserializationContext(bytes.fromhex(proof["timestamp_hex"])), digest
        )

        upgrade_url = f"{calendar_url}/timestamp/{digest.hex()}"
        resp = httpx.get(upgrade_url, timeout=10)
        if resp.status_code != 200:
            log.debug("Calendar upgrade %s returned HTTP %d (not yet confirmed)", upgrade_url, resp.status_code)
            return proof_bytes, False, None, None

        upgraded_ts = Timestamp.deserialize(BytesDeserializationContext(resp.content), digest)
        ts.merge(upgraded_ts)

        for _msg, attestation in ts.all_attestations():
            if isinstance(attestation, BitcoinBlockHeaderAttestation):
                ctx = BytesSerializationContext()
                ts.serialize(ctx)
                proof["timestamp_hex"] = ctx.getbytes().hex()
                log.info("OTS anchor confirmed at block %d", attestation.height)
                return json.dumps(proof).encode(), True, attestation.height, None

        # Updated proof bytes (may have additional partial attestations) but not yet confirmed
        ctx = BytesSerializationContext()
        ts.serialize(ctx)
        proof["timestamp_hex"] = ctx.getbytes().hex()
        return json.dumps(proof).encode(), False, None, None
    except Exception as exc:
        log.warning("OTS upgrade error: %s", exc)
        return proof_bytes, False, None, None


# ---------------------------------------------------------------------------
# Anchoring loop
# ---------------------------------------------------------------------------

class AnchorLoop:
    """
    Background thread that:
      1. Stamps the current head every `stamp_interval` seconds.
      2. Attempts to upgrade pending proofs every `upgrade_interval` seconds.
    """

    def __init__(self, store, stamp_interval: int = 30, upgrade_interval: int = 120,
                 stamp_fn=None, upgrade_fn=None):
        self._store = store
        self._stamp_interval = stamp_interval
        self._upgrade_interval = upgrade_interval
        self._stamp_fn = stamp_fn or _stamp
        self._upgrade_fn = upgrade_fn or _upgrade
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._last_stamped_seq: Optional[int] = None

    def start(self):
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="anchor-loop")
        self._thread.start()
        log.info("Anchor loop started (stamp every %ds, upgrade every %ds)",
                 self._stamp_interval, self._upgrade_interval)

    def stop(self):
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=15)

    def stamp_now(self) -> Optional[dict]:
        """Immediately stamp the current head. Returns the new anchor dict or None."""
        return self._do_stamp()

    def upgrade_now(self):
        """Immediately attempt upgrades on all pending anchors."""
        self._do_upgrades()

    def reset_tracking(self):
        """Forget the last-stamped seq so a wiped ledger can be re-stamped from
        scratch. Without this, after a demo reset the head seq collides with the
        previous run's stamped seq and stamp_now() becomes a no-op."""
        self._last_stamped_seq = None

    # ------------------------------------------------------------------

    def _run(self):
        last_upgrade = 0.0
        while not self._stop_event.is_set():
            try:
                self._do_stamp()
            except Exception:
                log.exception("Stamp iteration failed")

            now = time.monotonic()
            if now - last_upgrade >= self._upgrade_interval:
                try:
                    self._do_upgrades()
                except Exception:
                    log.exception("Upgrade iteration failed")
                last_upgrade = time.monotonic()

            self._stop_event.wait(timeout=self._stamp_interval)

    def _do_stamp(self) -> Optional[dict]:
        head = self._store.get_head()
        if head is None:
            return None

        head_seq = head["seq"]
        if head_seq == self._last_stamped_seq:
            return None

        # MMR root is maintained incrementally — O(log n) lookup, no rebuild
        mmr_root = self._store.get_mmr_root()
        mmr_leaf_count = self._store.leaf_count()

        # Stamp the MMR root — inclusion proofs against this root are O(log n)
        log.info("Stamping MMR root for seq=%d (leaf_count=%d) root=%s…",
                 head_seq, mmr_leaf_count, (mmr_root or "")[:16])
        proof_bytes = self._stamp_fn(mmr_root or head["entry_hash"])

        anchor_id = self._store.insert_anchor(
            head_seq, head["entry_hash"], proof_bytes,
            merkle_root=mmr_root, mmr_leaf_count=mmr_leaf_count,
        )
        self._last_stamped_seq = head_seq

        anchor = {
            "id": anchor_id,
            "head_seq": head_seq,
            "head_hash": head["entry_hash"],
            "merkle_root": mmr_root,
            "mmr_leaf_count": mmr_leaf_count,
            "status": "pending",
            "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
        }
        if proof_bytes:
            log.info("OTS proof obtained for MMR root at seq=%d (pending Bitcoin confirmation)", head_seq)
        else:
            log.warning("OTS stamp returned no proof for seq=%d", head_seq)
        return anchor

    def _do_upgrades(self):
        pending = self._store.get_pending_anchors()
        if not pending:
            return
        log.info("Checking %d pending anchor(s) for Bitcoin confirmation…", len(pending))
        for anchor in pending:
            proof_bytes = anchor.get("ots_proof")
            if not proof_bytes:
                continue
            new_proof, confirmed, block_height, block_time = self._upgrade_fn(
                proof_bytes, anchor["head_hash"]
            )
            if confirmed:
                log.info(
                    "Anchor id=%d (seq=%d) CONFIRMED at block %s!",
                    anchor["id"], anchor["head_seq"], block_height
                )
                self._store.update_anchor(
                    anchor["id"], new_proof, "confirmed", block_height, block_time
                )
            else:
                # Store upgraded (possibly unchanged) proof bytes
                if new_proof != proof_bytes:
                    self._store.update_anchor(anchor["id"], new_proof, "pending")
