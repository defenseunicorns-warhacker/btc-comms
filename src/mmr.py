"""
Merkle Mountain Range (MMR) — append-only, O(log n) per operation.

Why MMR instead of full-tree rebuild:
  Full rebuild: O(n) at every anchor — rebuilds the entire tree each time.
  MMR append:   O(log n) per entry — each new entry creates at most log2(n)
                new internal nodes, then stops. No rebuild ever needed.

Structure:
  An MMR with n leaves has "peaks" — roots of complete power-of-2 subtrees.
  The peaks correspond exactly to the set bits of n in binary.

  n=6 (binary 110) → two peaks: height-2 subtree (leaves 0–3) and
                                 height-1 subtree (leaves 4–5)

        peak2              peak1
       /     \\            /    \\
    [0,1]  [2,3]        [4]   [5]

  MMR root = bag_peaks(peak2, peak1) = SHA256( "\x01" || peak2 || peak1 )

  Adding leaf 6: merges peak1 (height 1) and new leaf → new peak of height 1.
  The height-2 peak is untouched. Only two new nodes created.

Inclusion proof for leaf i:
  1. Sibling hashes up to the subtree peak (standard binary path).
  2. All peak hashes (including the subtree's) for the final bagging step.

  Verification: walk the path to reach peak_hashes[peak_index],
                then verify bag_peaks(peak_hashes) == root.

Node identity: (height, start_leaf_index) is the canonical key.
  height=0 → leaf node for entry at that seq.
  height=k → root of the complete subtree covering leaves [start, start+2^k).
"""

import hashlib
from typing import Callable, Optional


# Same domain-separation prefixes as merkle.py for consistency
def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def leaf_hash(entry_hash: str) -> str:
    return _sha256(b"\x00" + bytes.fromhex(entry_hash))

def internal_hash(left: str, right: str) -> str:
    return _sha256(b"\x01" + bytes.fromhex(left) + bytes.fromhex(right))

def bag_peaks(peaks: list[str]) -> Optional[str]:
    """Fold peaks right-to-left into one root hash. Returns None if empty."""
    if not peaks:
        return None
    result = peaks[-1]
    for p in reversed(peaks[:-1]):
        result = internal_hash(p, result)
    return result


# ---------------------------------------------------------------------------
# Peak structure helpers
# ---------------------------------------------------------------------------

def peaks_for_count(n: int) -> list[int]:
    """Heights of current peaks (descending, left to right) for n leaves."""
    return [bit for bit in range(n.bit_length() - 1, -1, -1) if n & (1 << bit)]


def peak_ranges(n: int) -> list[tuple[int, int, int]]:
    """
    For each peak left to right: (height, first_leaf_idx, last_leaf_idx).
    Together they partition [0, n).
    """
    result = []
    start = 0
    for h in peaks_for_count(n):
        size = 1 << h
        result.append((h, start, start + size - 1))
        start += size
    return result


# ---------------------------------------------------------------------------
# Append
# ---------------------------------------------------------------------------

def append(entry_hash_hex: str, leaf_count_before: int,
           get_node: Callable[[int, int], str],
           set_node: Callable[[int, int, str], None]) -> str:
    """
    Append a new leaf (entry at seq == leaf_count_before).
    Creates at most ceil(log2(n)) new nodes.
    Returns the new MMR root.

    get_node(height, start) → hash string
    set_node(height, start, hash) → None
    """
    leaf_idx = leaf_count_before
    lh = leaf_hash(entry_hash_hex)
    set_node(0, leaf_idx, lh)

    # Reconstruct current peaks from storage before this append
    current_peaks: list[tuple[int, int, str]] = []  # (height, start, hash)
    for h, start, _ in peak_ranges(leaf_count_before):
        current_peaks.append((h, start, get_node(h, start)))

    # Merge upward: while the new node matches the height of the top peak,
    # create their parent (one new node per merge, at most log2(n) merges).
    cur_h = lh
    cur_height = 0
    cur_start = leaf_idx

    while current_peaks and current_peaks[-1][0] == cur_height:
        left_height, left_start, left_hash_val = current_peaks.pop()
        parent_hash = internal_hash(left_hash_val, cur_h)
        cur_height += 1
        cur_start = left_start          # parent's start = left child's start
        set_node(cur_height, cur_start, parent_hash)
        cur_h = parent_hash

    current_peaks.append((cur_height, cur_start, cur_h))
    return bag_peaks([h for _, _, h in current_peaks])


# ---------------------------------------------------------------------------
# Root
# ---------------------------------------------------------------------------

def root(leaf_count: int, get_node: Callable[[int, int], str]) -> Optional[str]:
    """Compute the MMR root for leaf_count leaves."""
    if leaf_count == 0:
        return None
    peaks = [get_node(h, start) for h, start, _ in peak_ranges(leaf_count)]
    return bag_peaks(peaks)


# ---------------------------------------------------------------------------
# Inclusion proof
# ---------------------------------------------------------------------------

def inclusion_proof(leaf_idx: int, leaf_count: int,
                    get_node: Callable[[int, int], str]) -> dict:
    """
    Build an O(log n) inclusion proof for the leaf at leaf_idx.

    Returns:
      {
        type:        "mmr",
        leaf_hash:   str,
        path:        [{hash, side}, ...],   # from leaf up to subtree peak
        peak_hashes: [str, ...],            # all peaks in left-to-right order
        peak_index:  int,                   # which peak is this leaf's subtree
        leaf_index:  int,
        leaf_count:  int,
      }

    Verification: walk path from leaf_hash → should reach peak_hashes[peak_index].
                  Then bag_peaks(peak_hashes) should equal the MMR root.
    """
    if leaf_idx < 0 or leaf_idx >= leaf_count:
        raise IndexError(f"leaf_idx {leaf_idx} out of range [0, {leaf_count})")

    ranges = peak_ranges(leaf_count)

    # Find the subtree containing this leaf
    sub_h = sub_start = sub_idx = None
    for i, (h, start, end) in enumerate(ranges):
        if start <= leaf_idx <= end:
            sub_h, sub_start, sub_idx = h, start, i
            break

    # Build sibling path within the subtree
    path = []
    for level in range(sub_h):
        block = 1 << level
        pos_at_level = (leaf_idx - sub_start) >> level
        if pos_at_level % 2 == 0:                          # left child
            sib_start = sub_start + (pos_at_level + 1) * block
            path.append({"hash": get_node(level, sib_start), "side": "right"})
        else:                                               # right child
            sib_start = sub_start + (pos_at_level - 1) * block
            path.append({"hash": get_node(level, sib_start), "side": "left"})

    return {
        "type": "mmr",
        "leaf_hash": get_node(0, leaf_idx),
        "path": path,
        "peak_hashes": [get_node(h, s) for h, s, _ in ranges],
        "peak_index": sub_idx,
        "leaf_index": leaf_idx,
        "leaf_count": leaf_count,
    }


# ---------------------------------------------------------------------------
# Proof verification
# ---------------------------------------------------------------------------

def verify_proof(entry_hash_hex: str, proof: dict) -> tuple[bool, Optional[str]]:
    """
    Verify an MMR inclusion proof.
    Returns (valid, mmr_root_if_valid).
    """
    try:
        if proof.get("type") != "mmr":
            return False, None

        lh = leaf_hash(entry_hash_hex)
        if lh != proof["leaf_hash"]:
            return False, None

        current = lh
        for step in proof["path"]:
            if step["side"] == "right":
                current = internal_hash(current, step["hash"])
            elif step["side"] == "left":
                current = internal_hash(step["hash"], current)
            else:
                return False, None

        peak_hashes = proof["peak_hashes"]
        if current != peak_hashes[proof["peak_index"]]:
            return False, None

        computed_root = bag_peaks(peak_hashes)
        return True, computed_root
    except Exception:
        return False, None
