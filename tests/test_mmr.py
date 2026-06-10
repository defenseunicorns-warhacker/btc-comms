"""
Tests for the MMR (Merkle Mountain Range) implementation.

Coverage:
  - leaf_hash / internal_hash / bag_peaks primitives
  - peaks_for_count / peak_ranges structure
  - append correctness for sizes 1–16
  - root changes when a node is tampered
  - inclusion_proof and verify_proof for all leaf/count combinations (sizes 1–16)
  - verify_proof rejects wrong entry hash
  - verify_proof rejects tampered path
  - verify_proof rejects wrong peak_hashes
"""

import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import mmr


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fake_hash(i: int) -> str:
    """Return a deterministic 64-char hex string for test entry i."""
    return format(i + 1, "064x")


def _build_mmr(n: int) -> dict:
    """Build an in-memory MMR for n leaves. Returns the node store dict."""
    nodes: dict = {}

    def get(h, s): return nodes[(h, s)]
    def set_(h, s, v): nodes[(h, s)] = v

    for i in range(n):
        mmr.append(_fake_hash(i), i, get, set_)
    return nodes


def _get_fn(nodes: dict):
    def get(h, s): return nodes[(h, s)]
    return get


# ---------------------------------------------------------------------------
# Primitives
# ---------------------------------------------------------------------------

def test_leaf_hash_is_deterministic():
    h = mmr.leaf_hash(_fake_hash(0))
    assert h == mmr.leaf_hash(_fake_hash(0))
    assert h != mmr.leaf_hash(_fake_hash(1))


def test_internal_hash_order_matters():
    a, b = mmr.leaf_hash(_fake_hash(0)), mmr.leaf_hash(_fake_hash(1))
    assert mmr.internal_hash(a, b) != mmr.internal_hash(b, a)


def test_bag_peaks_single():
    h = mmr.leaf_hash(_fake_hash(0))
    assert mmr.bag_peaks([h]) == h


def test_bag_peaks_empty():
    assert mmr.bag_peaks([]) is None


def test_bag_peaks_two():
    a, b = mmr.leaf_hash(_fake_hash(0)), mmr.leaf_hash(_fake_hash(1))
    result = mmr.bag_peaks([a, b])
    # bag folds right-to-left: internal(a, b)
    assert result == mmr.internal_hash(a, b)


def test_bag_peaks_three():
    a = mmr.leaf_hash(_fake_hash(0))
    b = mmr.leaf_hash(_fake_hash(1))
    c = mmr.leaf_hash(_fake_hash(2))
    result = mmr.bag_peaks([a, b, c])
    # fold right-to-left: result = internal(a, internal(b, c))
    expected = mmr.internal_hash(a, mmr.internal_hash(b, c))
    assert result == expected


# ---------------------------------------------------------------------------
# Peak structure
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("n,expected_heights", [
    (1,  [0]),
    (2,  [1]),
    (3,  [1, 0]),
    (4,  [2]),
    (5,  [2, 0]),
    (6,  [2, 1]),
    (7,  [2, 1, 0]),
    (8,  [3]),
    (9,  [3, 0]),
    (15, [3, 2, 1, 0]),
    (16, [4]),
])
def test_peaks_for_count(n, expected_heights):
    assert mmr.peaks_for_count(n) == expected_heights


def test_peak_ranges_cover_all_leaves():
    for n in range(1, 17):
        ranges = mmr.peak_ranges(n)
        covered = set()
        for h, start, end in ranges:
            for i in range(start, end + 1):
                covered.add(i)
        assert covered == set(range(n)), f"n={n}: ranges don't cover all leaves"


def test_peak_ranges_no_overlap():
    for n in range(1, 17):
        ranges = mmr.peak_ranges(n)
        all_leaves = []
        for h, start, end in ranges:
            all_leaves.extend(range(start, end + 1))
        assert len(all_leaves) == len(set(all_leaves)), f"n={n}: ranges overlap"


# ---------------------------------------------------------------------------
# Append + root
# ---------------------------------------------------------------------------

def test_root_none_for_zero():
    nodes: dict = {}
    assert mmr.root(0, lambda h, s: nodes[(h, s)]) is None


def test_root_single_leaf():
    nodes: dict = {}
    def get(h, s): return nodes[(h, s)]
    def set_(h, s, v): nodes[(h, s)] = v
    mmr.append(_fake_hash(0), 0, get, set_)
    r = mmr.root(1, get)
    assert r == mmr.leaf_hash(_fake_hash(0))


def test_root_two_leaves():
    nodes: dict = {}
    def get(h, s): return nodes[(h, s)]
    def set_(h, s, v): nodes[(h, s)] = v
    mmr.append(_fake_hash(0), 0, get, set_)
    mmr.append(_fake_hash(1), 1, get, set_)
    r = mmr.root(2, get)
    expected = mmr.internal_hash(mmr.leaf_hash(_fake_hash(0)), mmr.leaf_hash(_fake_hash(1)))
    assert r == expected


def test_root_changes_on_each_append():
    nodes: dict = {}
    def get(h, s): return nodes[(h, s)]
    def set_(h, s, v): nodes[(h, s)] = v
    roots = set()
    for i in range(8):
        mmr.append(_fake_hash(i), i, get, set_)
        r = mmr.root(i + 1, get)
        roots.add(r)
    assert len(roots) == 8, "Each append must produce a unique root"


def test_root_deterministic():
    """Two identically-built MMRs must have the same root."""
    n = 7
    nodes_a: dict = {}
    nodes_b: dict = {}

    def get_a(h, s): return nodes_a[(h, s)]
    def set_a(h, s, v): nodes_a[(h, s)] = v
    def get_b(h, s): return nodes_b[(h, s)]
    def set_b(h, s, v): nodes_b[(h, s)] = v

    for i in range(n):
        mmr.append(_fake_hash(i), i, get_a, set_a)
        mmr.append(_fake_hash(i), i, get_b, set_b)

    assert mmr.root(n, get_a) == mmr.root(n, get_b)


def test_root_changes_on_tamper():
    """
    Overwriting the stored peak node changes the root immediately.
    (Leaf-level tamper detection requires a full rebuild from entry hashes —
    that's what verify.py does. The MMR stores pre-computed internal nodes for
    O(log n) reads; root() reads peaks, not leaves.)
    """
    nodes = _build_mmr(8)
    get = _get_fn(nodes)
    original_root = mmr.root(8, get)

    # n=8 → single peak at height 3, start 0 — overwrite the peak directly
    nodes[(3, 0)] = mmr.leaf_hash(_fake_hash(99))
    tampered_root = mmr.root(8, get)
    assert original_root != tampered_root


# ---------------------------------------------------------------------------
# Inclusion proofs — structure
# ---------------------------------------------------------------------------

def test_proof_out_of_range():
    nodes = _build_mmr(4)
    get = _get_fn(nodes)
    with pytest.raises(IndexError):
        mmr.inclusion_proof(4, 4, get)
    with pytest.raises(IndexError):
        mmr.inclusion_proof(-1, 4, get)


def test_proof_type_field():
    nodes = _build_mmr(4)
    get = _get_fn(nodes)
    proof = mmr.inclusion_proof(0, 4, get)
    assert proof["type"] == "mmr"


@pytest.mark.parametrize("n", range(1, 17))
def test_proof_has_correct_leaf_count(n):
    nodes = _build_mmr(n)
    get = _get_fn(nodes)
    for i in range(n):
        proof = mmr.inclusion_proof(i, n, get)
        assert proof["leaf_count"] == n
        assert proof["leaf_index"] == i


@pytest.mark.parametrize("n", range(1, 17))
def test_proof_peak_hashes_match_root(n):
    """bag_peaks(proof["peak_hashes"]) must equal mmr.root(n)."""
    nodes = _build_mmr(n)
    get = _get_fn(nodes)
    expected_root = mmr.root(n, get)
    for i in range(n):
        proof = mmr.inclusion_proof(i, n, get)
        assert mmr.bag_peaks(proof["peak_hashes"]) == expected_root


# ---------------------------------------------------------------------------
# verify_proof — valid cases
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("n", range(1, 17))
def test_verify_proof_all_leaves_all_sizes(n):
    """Every leaf in every MMR size should produce a valid proof."""
    nodes = _build_mmr(n)
    get = _get_fn(nodes)
    expected_root = mmr.root(n, get)
    for i in range(n):
        proof = mmr.inclusion_proof(i, n, get)
        valid, root = mmr.verify_proof(_fake_hash(i), proof)
        assert valid, f"n={n} i={i}: proof not valid"
        assert root == expected_root, f"n={n} i={i}: wrong root"


# ---------------------------------------------------------------------------
# verify_proof — invalid cases
# ---------------------------------------------------------------------------

def test_verify_proof_wrong_entry_hash():
    nodes = _build_mmr(4)
    get = _get_fn(nodes)
    proof = mmr.inclusion_proof(2, 4, get)
    valid, root = mmr.verify_proof(_fake_hash(99), proof)
    assert not valid


def test_verify_proof_tampered_path():
    nodes = _build_mmr(8)
    get = _get_fn(nodes)
    proof = mmr.inclusion_proof(3, 8, get)
    if proof["path"]:
        proof["path"][0]["hash"] = _fake_hash(99)
    valid, root = mmr.verify_proof(_fake_hash(3), proof)
    assert not valid


def test_verify_proof_tampered_peak_hashes():
    nodes = _build_mmr(8)
    get = _get_fn(nodes)
    proof = mmr.inclusion_proof(3, 8, get)
    proof["peak_hashes"][proof["peak_index"]] = _fake_hash(99)
    valid, root = mmr.verify_proof(_fake_hash(3), proof)
    assert not valid


def test_verify_proof_wrong_type():
    nodes = _build_mmr(4)
    get = _get_fn(nodes)
    proof = mmr.inclusion_proof(0, 4, get)
    proof["type"] = "merkle"
    valid, root = mmr.verify_proof(_fake_hash(0), proof)
    assert not valid


def test_verify_proof_returns_consistent_root():
    """All valid proofs from the same MMR must return the same root."""
    nodes = _build_mmr(6)
    get = _get_fn(nodes)
    expected = mmr.root(6, get)
    roots = set()
    for i in range(6):
        proof = mmr.inclusion_proof(i, 6, get)
        valid, r = mmr.verify_proof(_fake_hash(i), proof)
        assert valid
        roots.add(r)
    assert roots == {expected}
