"""
Tests for LedgerStore — append, genesis, hash-chain links, MMR persistence,
and that the persisted MMR root matches an independently-recomputed root.
These exercise the storage layer that the pure-crypto tests don't touch.
"""

import pytest


@pytest.fixture
def store(tmp_path):
    from ledger import LedgerStore
    s = LedgerStore(str(tmp_path / "ledger.db"))
    s.ensure_genesis()
    return s


def test_genesis_created(store):
    head = store.get_head()
    assert head["seq"] == 0
    assert head["source_id"] == "system"
    assert head["prev_hash"] == "0" * 64


def test_append_increments_seq(store):
    e1 = store.append("agent-a", {"event": "x"})
    e2 = store.append("agent-a", {"event": "y"})
    assert e1["seq"] == 1
    assert e2["seq"] == 2


def test_chain_links(store):
    e1 = store.append("agent-a", {"event": "x"})
    e2 = store.append("agent-a", {"event": "y"})
    assert e1["prev_hash"] == store.get_entry(0)["entry_hash"]
    assert e2["prev_hash"] == e1["entry_hash"]


def test_payload_hash_recorded(store):
    from ledger import payload_hash
    e = store.append("agent-a", {"event": "x", "n": 7})
    assert e["payload_hash"] == payload_hash({"event": "x", "n": 7})


def test_mmr_root_matches_independent_recompute(store):
    import mmr
    for i in range(20):
        store.append("agent-a", {"event": "x", "i": i})

    n = store.leaf_count()
    stored_root = store.get_mmr_root()

    # Independently rebuild an MMR from the entry hashes
    entries = store.get_all_entries()
    nodes = {}
    get = lambda h, s: nodes[(h, s)]
    set_ = lambda h, s, v: nodes.__setitem__((h, s), v)
    for e in entries:
        mmr.append(e["entry_hash"], e["seq"], get, set_)
    assert mmr.root(n, get) == stored_root


def test_mmr_inclusion_proof_via_store(store):
    import mmr
    for i in range(10):
        store.append("agent-a", {"event": "x", "i": i})
    for seq in range(store.leaf_count()):
        entry = store.get_entry(seq)
        proof = store.get_mmr_inclusion_proof(seq)
        valid, root = mmr.verify_proof(entry["entry_hash"], proof)
        assert valid, f"seq={seq} proof invalid"
        assert root == store.get_mmr_root()


def test_mmr_nodes_grow_logarithmically(store):
    """Each append should add O(log n) MMR nodes, not O(n)."""
    for i in range(64):
        store.append("agent-a", {"i": i})
    node_count = store._conn.execute("SELECT COUNT(*) FROM mmr_nodes").fetchone()[0]
    n = store.leaf_count()
    # An MMR over n leaves has 2n-1 nodes worst case; assert it's not quadratic
    assert node_count < 2 * n, f"{node_count} nodes for {n} leaves looks non-linear"


def test_reopen_persists_chain(tmp_path):
    from ledger import LedgerStore
    db = str(tmp_path / "ledger.db")
    s1 = LedgerStore(db)
    s1.ensure_genesis()
    s1.append("agent-a", {"event": "x"})
    head1 = s1.get_head()["entry_hash"]
    del s1

    s2 = LedgerStore(db)
    assert s2.get_head()["entry_hash"] == head1
    # MMR continues correctly after reopen
    s2.append("agent-a", {"event": "y"})
    assert s2.leaf_count() == 3
