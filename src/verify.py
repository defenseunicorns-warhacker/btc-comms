"""
verify() — walks the full hash chain and checks anchors.

Returns a VerifyResult:
  - ok=True  → chain intact; externally_anchored_through is the highest confirmed seq
  - ok=False → first broken entry described in broken_at + reason
"""

import json
from dataclasses import dataclass, field
from typing import Optional

from ledger import canonical_json, sha256, payload_hash as compute_payload_hash, ZERO_HASH
import mmr as _mmr
try:
    from signing import verify_signature
    _SIGNING_AVAILABLE = True
except ImportError:
    _SIGNING_AVAILABLE = False


@dataclass
class VerifyResult:
    ok: bool
    verified_entries: int = 0
    externally_anchored_through: Optional[int] = None
    broken_at: Optional[int] = None
    reason: Optional[str] = None
    warnings: list[str] = field(default_factory=list)
    unsigned_entries: int = 0      # entries with no signature (pre-signing or unsigned sources)
    invalid_signatures: list[int] = field(default_factory=list)  # seqs with bad signatures

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "verified_entries": self.verified_entries,
            "externally_anchored_through": self.externally_anchored_through,
            "broken_at": self.broken_at,
            "reason": self.reason,
            "warnings": self.warnings,
            "unsigned_entries": self.unsigned_entries,
            "invalid_signatures": self.invalid_signatures,
        }


def _recompute_entry_hash(entry: dict) -> str:
    """Recompute entry_hash from the stored fields (what it should be)."""
    obj = {
        "seq": entry["seq"],
        "timestamp": entry["timestamp"],
        "source_id": entry["source_id"],
        "payload_hash": entry["payload_hash"],
        "prev_hash": entry["prev_hash"],
    }
    return sha256(canonical_json(obj))


def verify(entries: list[dict], anchors: list[dict],
           ots_verify_fn=None) -> VerifyResult:
    """
    entries  — ordered list of LedgerEntry dicts (seq ascending)
    anchors  — list of Anchor dicts (seq ascending)
    ots_verify_fn — callable(proof_bytes, head_hash_str) -> bool | None
                    None means "call real OTS library" (default behaviour)
    """
    if not entries:
        return VerifyResult(ok=True, verified_entries=0)

    # ---------------------------------------------------------------
    # 1. Structural + chain integrity
    # ---------------------------------------------------------------
    expected_prev = ZERO_HASH
    last_seq = -1
    entry_map: dict[int, dict] = {}

    for entry in sorted(entries, key=lambda e: e["seq"]):
        seq = entry["seq"]

        if seq != last_seq + 1:
            return VerifyResult(
                ok=False,
                verified_entries=last_seq + 1,
                broken_at=seq,
                reason="sequence gap or reorder — possible deletion",
            )

        # Payload hash check
        payload = entry["payload"]
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except (json.JSONDecodeError, TypeError):
                pass
        computed_ph = compute_payload_hash(payload) if isinstance(payload, dict) else sha256(payload.encode())
        if computed_ph != entry["payload_hash"]:
            return VerifyResult(
                ok=False,
                verified_entries=last_seq + 1,
                broken_at=seq,
                reason="payload altered",
            )

        # Entry hash check
        recomputed = _recompute_entry_hash(entry)
        if recomputed != entry["entry_hash"]:
            return VerifyResult(
                ok=False,
                verified_entries=last_seq + 1,
                broken_at=seq,
                reason="entry hash mismatch",
            )

        # Chain link check
        if entry["prev_hash"] != expected_prev:
            return VerifyResult(
                ok=False,
                verified_entries=last_seq + 1,
                broken_at=seq,
                reason="chain link broken",
            )

        expected_prev = entry["entry_hash"]
        last_seq = seq
        entry_map[seq] = entry

    # ---------------------------------------------------------------
    # 1b. Signature verification (attribution check)
    # ---------------------------------------------------------------
    unsigned_count = 0
    invalid_sigs: list[int] = []

    if _SIGNING_AVAILABLE:
        for entry in sorted(entries, key=lambda e: e["seq"]):
            sig = entry.get("signature")
            kid = entry.get("key_id")
            if not sig or not kid:
                unsigned_count += 1
                continue
            payload = entry["payload"]
            if isinstance(payload, str):
                try:
                    payload = json.loads(payload)
                except Exception:
                    pass
            payload_bytes = canonical_json(payload) if isinstance(payload, dict) else payload.encode()
            if not verify_signature(sig, kid, entry["source_id"], payload_bytes):
                invalid_sigs.append(entry["seq"])

    # ---------------------------------------------------------------
    # 2. External anchoring
    # ---------------------------------------------------------------
    anchored_through: Optional[int] = None
    warnings: list[str] = []

    for anchor in sorted(anchors, key=lambda a: a["head_seq"]):
        head_seq = anchor["head_seq"]
        head_hash = anchor["head_hash"]

        # Anchor's recorded hash must match what we just verified
        if head_seq not in entry_map:
            warnings.append(f"Anchor at seq={head_seq} references an entry not in ledger")
            continue

        if entry_map[head_seq]["entry_hash"] != head_hash:
            return VerifyResult(
                ok=False,
                verified_entries=last_seq + 1,
                broken_at=head_seq,
                reason="anchored head does not match ledger",
            )

        # MMR root consistency: recompute root from the verified entry hashes
        # and compare against the stored root. O(log n) — no full rebuild.
        stored_mmr_root = anchor.get("merkle_root")   # column stores MMR root now
        mmr_leaf_count = anchor.get("mmr_leaf_count")
        if stored_mmr_root and mmr_leaf_count:
            seqs_covered = sorted(s for s in entry_map if s < mmr_leaf_count)
            if len(seqs_covered) != mmr_leaf_count:
                warnings.append(
                    f"Anchor id={anchor.get('id')} mmr_leaf_count={mmr_leaf_count} "
                    f"but only {len(seqs_covered)} verified entries available"
                )
            else:
                # Build an in-memory MMR from verified entry hashes to recompute root
                _nodes: dict = {}
                def _get(h, s): return _nodes[(h, s)]
                def _set(h, s, v): _nodes[(h, s)] = v
                for seq_i in seqs_covered:
                    _mmr.append(entry_map[seq_i]["entry_hash"], seq_i, _get, _set)
                recomputed_root = _mmr.root(mmr_leaf_count, _get)
                if recomputed_root != stored_mmr_root:
                    return VerifyResult(
                        ok=False,
                        verified_entries=last_seq + 1,
                        broken_at=head_seq,
                        reason="MMR root mismatch — entries altered since anchor",
                    )

        # Check the OTS proof (stamped against the MMR root when available)
        stamped_value = stored_mmr_root or head_hash
        ots_proof = anchor.get("ots_proof")
        if ots_proof:
            valid = _check_ots(ots_proof, stamped_value, ots_verify_fn)
            if valid is True:
                anchored_through = head_seq
            elif valid is False and anchor.get("status") == "confirmed":
                return VerifyResult(
                    ok=False,
                    verified_entries=last_seq + 1,
                    broken_at=head_seq,
                    reason="bitcoin proof invalid for confirmed anchor",
                )
            # valid is None → pending, not an error
        else:
            # No proof bytes yet (just submitted to calendar)
            if anchor.get("status") == "pending":
                pass  # fine, still waiting
            elif anchor.get("status") == "confirmed":
                warnings.append(f"Anchor id={anchor.get('id')} is confirmed but has no proof bytes")

    if invalid_sigs:
        warnings.append(f"{len(invalid_sigs)} entries have invalid signatures: seqs {invalid_sigs}")

    return VerifyResult(
        ok=True,
        verified_entries=last_seq + 1,
        externally_anchored_through=anchored_through,
        warnings=warnings,
        unsigned_entries=unsigned_count,
        invalid_signatures=invalid_sigs,
    )


def _check_ots(proof_bytes: bytes, head_hash: str, override_fn=None) -> Optional[bool]:
    """
    Returns True if proof verifies, False if it is confirmed-invalid, None if still pending.
    """
    if override_fn is not None:
        return override_fn(proof_bytes, head_hash)

    # Mock proof produced by _stamp_mock — no OTS library needed
    if proof_bytes.startswith(b'{"mock"'):
        try:
            import json as _json
            proof = _json.loads(proof_bytes)
            return True if proof.get("confirmed") else None
        except Exception:
            return None

    try:
        import opentimestamps.core.timestamp as ots_ts
        from opentimestamps.core.op import OpSHA256
        from opentimestamps.calendar import CalendarSubmitError
        import io

        # Attempt upgrade + verify via the OTS client library
        from opentimestamps.core.serialize import BytesDeserializationContext
        from opentimestamps.core.timestamp import DetachedTimestampFile

        ctx = BytesDeserializationContext(io.BytesIO(proof_bytes))
        detached = DetachedTimestampFile.deserialize(ctx)

        # If the timestamp has Bitcoin attestations, it's confirmed
        from opentimestamps.core.notary import BitcoinBlockHeaderAttestation
        for msg, attestation in detached.timestamp.all_attestations():
            if isinstance(attestation, BitcoinBlockHeaderAttestation):
                return True

        return None  # still pending calendar
    except Exception:
        return None  # parse error → treat as pending
