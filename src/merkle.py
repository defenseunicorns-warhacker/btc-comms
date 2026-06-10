"""
Merkle tree over ledger entry hashes.

Enables selective disclosure: prove a single entry exists and is unmodified
without revealing any other entries. The Merkle root is anchored to Bitcoin
(via OpenTimestamps) so the proof is externally verifiable.

Tree construction:
  - Leaves are sha256(entry_hash) for each entry ordered by seq ascending.
  - If a level has an odd number of nodes, the last node is duplicated.
  - Internal nodes: sha256(left_child || right_child) — concatenation of raw hex bytes.
  - Root is the single node at the top.

Inclusion proof:
  - A list of {hash, side} steps. Starting from the leaf, apply each step:
      side="left"  → new_hash = sha256(step.hash + current)
      side="right" → new_hash = sha256(current + step.hash)
  - The result must equal the root.

Why this matters for classified contexts:
  An investigator can verify that AI decision #47 existed, was unmodified,
  and was committed to Bitcoin — without seeing any adjacent entries.
"""

import hashlib
from typing import Optional


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _hash_pair(left: str, right: str) -> str:
    return _sha256(bytes.fromhex(left) + bytes.fromhex(right))


def _leaf_hash(entry_hash: str) -> str:
    """Wrap entry_hash in one more hash so leaf ≠ internal node (second-preimage hardening)."""
    return _sha256(b"\x00" + bytes.fromhex(entry_hash))


def _internal_hash(left: str, right: str) -> str:
    return _sha256(b"\x01" + bytes.fromhex(left) + bytes.fromhex(right))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_root(entry_hashes: list[str]) -> Optional[str]:
    """
    Compute the Merkle root for a list of entry_hashes (in seq order).
    Returns None if the list is empty.
    """
    if not entry_hashes:
        return None
    nodes = [_leaf_hash(h) for h in entry_hashes]
    while len(nodes) > 1:
        nodes = _build_level(nodes)
    return nodes[0]


def inclusion_proof(entry_hashes: list[str], seq_index: int) -> dict:
    """
    Build an inclusion proof for the entry at seq_index (0-based position
    in the entry_hashes list, which is seq-ordered).

    Returns:
      {
        "leaf_hash":   str,   # sha256(entry_hash) — the leaf node
        "path":        list,  # [{hash, side}, …] from leaf to root
        "root":        str,
        "entry_count": int,
      }
    """
    if not entry_hashes:
        raise ValueError("Cannot build proof for empty ledger")
    if seq_index < 0 or seq_index >= len(entry_hashes):
        raise IndexError(f"seq_index {seq_index} out of range (0..{len(entry_hashes)-1})")

    nodes = [_leaf_hash(h) for h in entry_hashes]
    leaf = nodes[seq_index]
    path = []
    idx = seq_index

    while len(nodes) > 1:
        padded = _pad_level(nodes)
        # Sibling is the node paired with idx
        if idx % 2 == 0:
            sibling_idx = idx + 1
            path.append({"hash": padded[sibling_idx], "side": "right"})
        else:
            sibling_idx = idx - 1
            path.append({"hash": padded[sibling_idx], "side": "left"})
        nodes = _build_level(nodes)
        idx //= 2

    root = nodes[0]
    return {
        "leaf_hash": leaf,
        "path": path,
        "root": root,
        "entry_count": len(entry_hashes),
    }


def verify_proof(entry_hash: str, proof: dict) -> bool:
    """
    Verify that entry_hash is included in proof["root"] using the given path.
    Returns True if valid, False otherwise.
    """
    try:
        current = _leaf_hash(entry_hash)
        for step in proof["path"]:
            if step["side"] == "right":
                current = _internal_hash(current, step["hash"])
            elif step["side"] == "left":
                current = _internal_hash(step["hash"], current)
            else:
                return False
        return current == proof["root"]
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _pad_level(nodes: list[str]) -> list[str]:
    """Duplicate last node if level has odd length."""
    if len(nodes) % 2 == 1:
        return nodes + [nodes[-1]]
    return nodes


def _build_level(nodes: list[str]) -> list[str]:
    padded = _pad_level(nodes)
    return [
        _internal_hash(padded[i], padded[i + 1])
        for i in range(0, len(padded), 2)
    ]
