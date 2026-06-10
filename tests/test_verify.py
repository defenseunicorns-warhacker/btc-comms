"""
Unit tests for the hash-chain verification logic.

Covers every broken-entry case the verify() spec requires:
  - clean chain passes
  - payload altered → fails at the right seq
  - entry_hash altered → fails at the right seq
  - chain link broken → fails at the right seq
  - sequence gap (simulated deletion) → fails at the right seq
  - anchor head mismatch → fails
  - confirmed anchor with invalid proof → fails
  - pending anchor with no proof → ok (just pending)
"""

import copy
import json
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from ledger import LedgerStore, ZERO_HASH, payload_hash, entry_hash, sha256, canonical_json
from verify import verify, VerifyResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_store(tmp_path: str = ":memory:") -> LedgerStore:
    store = LedgerStore(tmp_path)
    store.ensure_genesis()
    return store


def seed(store: LedgerStore, n: int = 5) -> list[dict]:
    """Append n events after genesis and return all entries."""
    for i in range(n):
        store.append("test-agent", {"action": f"event_{i}", "value": i})
    return store.get_all_entries()


def run_verify(store: LedgerStore, ots_fn=None) -> VerifyResult:
    return verify(store.get_all_entries(), store.get_all_anchors(), ots_verify_fn=ots_fn)


# ---------------------------------------------------------------------------
# Phase 1 tests — chain integrity
# ---------------------------------------------------------------------------

class TestCleanChain:
    def test_genesis_only(self):
        store = make_store()
        result = run_verify(store)
        assert result.ok
        assert result.verified_entries == 1

    def test_five_events(self):
        store = make_store()
        seed(store)
        result = run_verify(store)
        assert result.ok
        assert result.verified_entries == 6  # genesis + 5

    def test_no_anchors(self):
        store = make_store()
        seed(store)
        result = run_verify(store)
        assert result.externally_anchored_through is None


class TestPayloadTamper:
    def test_payload_change_detected(self):
        store = make_store()
        seed(store)
        # Tamper seq=3's payload directly in the DB
        store._tamper_entry(3, "payload", json.dumps({"action": "EVIL", "value": 999}))
        result = run_verify(store)
        assert not result.ok
        assert result.broken_at == 3
        assert "payload altered" in result.reason

    def test_payload_change_at_seq1(self):
        store = make_store()
        seed(store)
        store._tamper_entry(1, "payload", json.dumps({"action": "TAMPERED"}))
        result = run_verify(store)
        assert not result.ok
        assert result.broken_at == 1

    def test_payload_change_at_last(self):
        store = make_store()
        seed(store, 3)
        store._tamper_entry(3, "payload", json.dumps({"x": "y"}))
        result = run_verify(store)
        assert not result.ok
        assert result.broken_at == 3


class TestEntryHashTamper:
    def test_entry_hash_change_detected(self):
        store = make_store()
        seed(store)
        # Change entry_hash without changing payload → hash mismatch
        store._tamper_entry(2, "entry_hash", "a" * 64)
        result = run_verify(store)
        assert not result.ok
        assert result.broken_at == 2
        assert "entry hash mismatch" in result.reason


class TestChainLinkBroken:
    def test_prev_hash_change_detected(self):
        store = make_store()
        seed(store)
        # Change prev_hash on seq=4 so it no longer matches seq=3's entry_hash
        store._tamper_entry(4, "prev_hash", "b" * 64)
        result = run_verify(store)
        assert not result.ok
        assert result.broken_at == 4
        # either chain link broken or entry hash mismatch (prev_hash is in the hash input)
        assert result.reason in ("chain link broken", "entry hash mismatch")


class TestSequenceGap:
    def test_deletion_detected(self):
        store = make_store()
        seed(store, 5)
        # Delete seq=3; verify detects the gap at seq=4 (first entry where seq != last+1)
        store._conn.execute("DELETE FROM ledger WHERE seq=3")
        store._conn.commit()
        result = run_verify(store)
        assert not result.ok
        assert result.broken_at == 4  # gap detected at the entry *after* the deleted one
        assert "sequence gap" in result.reason or "deletion" in result.reason


class TestMultipleTampers:
    def test_reports_first_break(self):
        store = make_store()
        seed(store, 6)
        # Two tampers — verify should stop at the first
        store._tamper_entry(2, "payload", json.dumps({"evil": True}))
        store._tamper_entry(5, "payload", json.dumps({"also": "evil"}))
        result = run_verify(store)
        assert not result.ok
        assert result.broken_at == 2


# ---------------------------------------------------------------------------
# Phase 2 tests — anchor verification
# ---------------------------------------------------------------------------

class TestAnchorVerification:
    def test_confirmed_anchor_accepted(self):
        store = make_store()
        seed(store, 3)
        head = store.get_head()
        store.insert_anchor(head["seq"], head["entry_hash"], b"fake_proof")
        store.update_anchor(1, b"fake_proof", "confirmed", block_height=850000)

        # Provide an ots_verify_fn that says "yes, confirmed"
        result = verify(
            store.get_all_entries(),
            store.get_all_anchors(),
            ots_verify_fn=lambda proof, hsh: True,
        )
        assert result.ok
        assert result.externally_anchored_through == head["seq"]

    def test_pending_anchor_not_error(self):
        store = make_store()
        seed(store, 2)
        head = store.get_head()
        store.insert_anchor(head["seq"], head["entry_hash"], b"pending_proof")

        result = verify(
            store.get_all_entries(),
            store.get_all_anchors(),
            ots_verify_fn=lambda proof, hsh: None,  # still pending
        )
        assert result.ok
        assert result.externally_anchored_through is None

    def test_anchor_head_mismatch_detected(self):
        store = make_store()
        seed(store, 3)
        head = store.get_head()
        # Insert anchor with wrong hash
        store.insert_anchor(head["seq"], "c" * 64, b"proof")

        result = verify(
            store.get_all_entries(),
            store.get_all_anchors(),
            ots_verify_fn=lambda proof, hsh: True,
        )
        assert not result.ok
        assert result.broken_at == head["seq"]
        assert "anchored head does not match ledger" in result.reason

    def test_confirmed_anchor_bad_proof_fails(self):
        store = make_store()
        seed(store, 2)
        head = store.get_head()
        store.insert_anchor(head["seq"], head["entry_hash"], b"bad_proof")
        store.update_anchor(1, b"bad_proof", "confirmed", block_height=850001)

        result = verify(
            store.get_all_entries(),
            store.get_all_anchors(),
            ots_verify_fn=lambda proof, hsh: False,  # explicitly invalid
        )
        assert not result.ok
        assert "bitcoin proof invalid" in result.reason

    def test_anchor_after_tamper_shows_both_failures(self):
        """If chain is broken AND anchor head mismatches, chain break wins (reported first)."""
        store = make_store()
        seed(store, 4)
        head = store.get_head()
        store.insert_anchor(head["seq"], head["entry_hash"], b"proof")
        # Tamper an entry BEFORE the anchor
        store._tamper_entry(2, "payload", json.dumps({"tampered": True}))

        result = verify(
            store.get_all_entries(),
            store.get_all_anchors(),
            ots_verify_fn=lambda proof, hsh: True,
        )
        assert not result.ok
        assert result.broken_at == 2


# ---------------------------------------------------------------------------
# Hashing unit tests — canonical_json and sha256
# ---------------------------------------------------------------------------

class TestHashingProperties:
    def test_canonical_json_sorts_keys(self):
        a = canonical_json({"z": 1, "a": 2})
        b = canonical_json({"a": 2, "z": 1})
        assert a == b

    def test_canonical_json_no_whitespace(self):
        result = canonical_json({"a": 1}).decode()
        assert " " not in result

    def test_sha256_hex_length(self):
        h = sha256(b"hello")
        assert len(h) == 64
        assert h == h.lower()

    def test_payload_hash_deterministic(self):
        p = {"action": "fire", "target": "X"}
        assert payload_hash(p) == payload_hash(p)

    def test_different_payloads_different_hashes(self):
        assert payload_hash({"a": 1}) != payload_hash({"a": 2})

    def test_genesis_prev_hash_is_zeros(self):
        store = make_store()
        entries = store.get_all_entries()
        genesis = next(e for e in entries if e["seq"] == 0)
        assert genesis["prev_hash"] == ZERO_HASH

    def test_entry_hash_covers_all_fields(self):
        """Changing any one field changes entry_hash."""
        # entry_hash(seq, timestamp, source_id, ph, prev_hash)
        args = (1, "2026-01-01T00:00:00.000Z", "s", "a"*64, "b"*64)
        h0 = entry_hash(*args)
        bad_variants = [
            (2, "2026-01-01T00:00:00.000Z", "s", "a"*64, "b"*64),        # seq changed
            (1, "2026-01-02T00:00:00.000Z", "s", "a"*64, "b"*64),        # timestamp changed
            (1, "2026-01-01T00:00:00.000Z", "t", "a"*64, "b"*64),        # source_id changed
            (1, "2026-01-01T00:00:00.000Z", "s", "c"*64, "b"*64),        # payload_hash changed
            (1, "2026-01-01T00:00:00.000Z", "s", "a"*64, "d"*64),        # prev_hash changed
        ]
        labels = ("seq", "timestamp", "source_id", "payload_hash", "prev_hash")
        for label, variant in zip(labels, bad_variants):
            assert entry_hash(*variant) != h0, f"Changing {label} should change entry_hash"
