"""
Append-only, hash-chained event ledger backed by SQLite.

Trust domain: the recorder (this module) assigns seq, timestamp, prev_hash,
and computes all hashes. The caller only supplies source_id and payload.
"""

import hashlib
import json
import sqlite3
import threading
from datetime import datetime, timezone
import mmr as _mmr
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Hashing + canonicalization
# ---------------------------------------------------------------------------

def canonical_json(obj: dict) -> bytes:
    """Stable, deterministic JSON bytes: keys sorted, no extra whitespace, UTF-8."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def payload_hash(payload: dict) -> str:
    return sha256(canonical_json(payload))


def entry_hash(seq: int, timestamp: str, source_id: str, ph: str, prev_hash: str) -> str:
    obj = {
        "seq": seq,
        "timestamp": timestamp,
        "source_id": source_id,
        "payload_hash": ph,
        "prev_hash": prev_hash,
    }
    return sha256(canonical_json(obj))


ZERO_HASH = "0" * 64

# ---------------------------------------------------------------------------
# Store (SQLite)
# ---------------------------------------------------------------------------

class LedgerStore:
    def __init__(self, db_path: str = "ledger.db"):
        self._db_path = db_path
        # Reentrant: a single shared connection is used from request handlers
        # AND the background anchor thread. Every method that touches the
        # connection holds this lock, so reads can't interleave with a writer's
        # cursor (which otherwise corrupts results, e.g. COUNT(*) -> no row).
        # RLock allows locked methods to call other locked methods (e.g.
        # get_mmr_root -> leaf_count) without deadlocking.
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self):
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS ledger (
                seq          INTEGER PRIMARY KEY,
                timestamp    TEXT    NOT NULL,
                source_id    TEXT    NOT NULL,
                payload      TEXT    NOT NULL,
                payload_hash TEXT    NOT NULL,
                prev_hash    TEXT    NOT NULL,
                entry_hash   TEXT    NOT NULL,
                signature    TEXT,
                key_id       TEXT
            );
            CREATE TABLE IF NOT EXISTS anchors (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                head_seq        INTEGER NOT NULL,
                head_hash       TEXT    NOT NULL,
                merkle_root     TEXT,
                mmr_leaf_count  INTEGER,
                ots_proof       BLOB,
                created_at      TEXT    NOT NULL,
                status          TEXT    NOT NULL DEFAULT 'pending',
                block_height    INTEGER,
                block_time      TEXT
            );
            CREATE TABLE IF NOT EXISTS mmr_nodes (
                height  INTEGER NOT NULL,
                start   INTEGER NOT NULL,
                hash    TEXT    NOT NULL,
                PRIMARY KEY (height, start)
            );
        """)
        # Migrate existing DBs — add columns introduced after initial schema
        ledger_cols = {r[1] for r in self._conn.execute("PRAGMA table_info(ledger)")}
        for col in ("signature TEXT", "key_id TEXT"):
            if col.split()[0] not in ledger_cols:
                self._conn.execute(f"ALTER TABLE ledger ADD COLUMN {col}")
        anchor_cols = {r[1] for r in self._conn.execute("PRAGMA table_info(anchors)")}
        for col in ("merkle_root TEXT", "mmr_leaf_count INTEGER"):
            if col.split()[0] not in anchor_cols:
                self._conn.execute(f"ALTER TABLE anchors ADD COLUMN {col}")

        # WAL mode: allows concurrent readers while a writer is active
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.commit()

    # ------------------------------------------------------------------
    # Ledger operations
    # ------------------------------------------------------------------

    def append(self, source_id: str, payload: dict,
               signature: Optional[str] = None, key_id: Optional[str] = None) -> dict:
        """Append a new entry and update the MMR incrementally (O(log n))."""
        with self._lock:
            cur = self._conn.execute("SELECT COUNT(*) FROM ledger")
            count = cur.fetchone()[0]

            if count == 0:
                self._insert_genesis()
                count = 1

            last = self._conn.execute(
                "SELECT seq, entry_hash FROM ledger ORDER BY seq DESC LIMIT 1"
            ).fetchone()
            next_seq = last["seq"] + 1
            prev = last["entry_hash"]

            ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
            ph = payload_hash(payload)
            eh = entry_hash(next_seq, ts, source_id, ph, prev)

            self._conn.execute(
                "INSERT INTO ledger (seq,timestamp,source_id,payload,payload_hash,prev_hash,entry_hash,signature,key_id) VALUES (?,?,?,?,?,?,?,?,?)",
                (next_seq, ts, source_id, json.dumps(payload), ph, prev, eh, signature, key_id),
            )
            # Extend MMR with this entry — O(log n), not O(n)
            _mmr.append(eh, next_seq, self._get_mmr_node, self._set_mmr_node)
            self._conn.commit()
            return self._row_to_dict(self._conn.execute(
                "SELECT * FROM ledger WHERE seq=?", (next_seq,)
            ).fetchone())

    def _insert_genesis(self):
        payload = {"type": "genesis"}
        ph = payload_hash(payload)
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
        eh = entry_hash(0, ts, "system", ph, ZERO_HASH)
        self._conn.execute(
            "INSERT OR IGNORE INTO ledger (seq,timestamp,source_id,payload,payload_hash,prev_hash,entry_hash) VALUES (?,?,?,?,?,?,?)",
            (0, ts, "system", json.dumps(payload), ph, ZERO_HASH, eh),
        )
        # Genesis is leaf 0 in the MMR
        _mmr.append(eh, 0, self._get_mmr_node, self._set_mmr_node)

    def ensure_genesis(self):
        with self._lock:
            count = self._conn.execute("SELECT COUNT(*) FROM ledger").fetchone()[0]
            if count == 0:
                self._insert_genesis()
                self._conn.commit()

    def get_all_entries(self) -> list[dict]:
        with self._lock:
            rows = self._conn.execute("SELECT * FROM ledger ORDER BY seq ASC").fetchall()
        return [self._row_to_dict(r) for r in rows]

    def get_entries_up_to(self, head_seq: int) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM ledger WHERE seq <= ? ORDER BY seq ASC", (head_seq,)
            ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def get_entry(self, seq: int) -> Optional[dict]:
        with self._lock:
            row = self._conn.execute("SELECT * FROM ledger WHERE seq=?", (seq,)).fetchone()
        return self._row_to_dict(row) if row else None

    def get_head(self) -> Optional[dict]:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM ledger ORDER BY seq DESC LIMIT 1"
            ).fetchone()
        return self._row_to_dict(row) if row else None

    def leaf_count(self) -> int:
        """Number of entries in the ledger = number of MMR leaves."""
        with self._lock:
            row = self._conn.execute("SELECT COUNT(*) FROM ledger").fetchone()
        return row[0] if row else 0

    def get_mmr_root(self) -> Optional[str]:
        """Current MMR root over all entries."""
        with self._lock:
            n = self.leaf_count()
            if n == 0:
                return None
            return _mmr.root(n, self._get_mmr_node)

    def get_mmr_inclusion_proof(self, seq: int) -> dict:
        """Build an MMR inclusion proof for entry at seq."""
        with self._lock:
            n = self.leaf_count()
            return _mmr.inclusion_proof(seq, n, self._get_mmr_node)

    # ------------------------------------------------------------------
    # MMR node storage
    # ------------------------------------------------------------------

    def _get_mmr_node(self, height: int, start: int) -> str:
        row = self._conn.execute(
            "SELECT hash FROM mmr_nodes WHERE height=? AND start=?", (height, start)
        ).fetchone()
        if row is None:
            raise KeyError(f"MMR node not found: height={height}, start={start}")
        return row[0]

    def _set_mmr_node(self, height: int, start: int, hash_val: str):
        self._conn.execute(
            "INSERT OR REPLACE INTO mmr_nodes (height, start, hash) VALUES (?,?,?)",
            (height, start, hash_val),
        )

    # ------------------------------------------------------------------
    # Anchor operations
    # ------------------------------------------------------------------

    def insert_anchor(self, head_seq: int, head_hash: str, ots_proof: Optional[bytes],
                      merkle_root: Optional[str] = None, mmr_leaf_count: Optional[int] = None) -> int:
        with self._lock:
            ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
            cur = self._conn.execute(
                "INSERT INTO anchors (head_seq, head_hash, merkle_root, mmr_leaf_count, ots_proof, created_at, status) VALUES (?,?,?,?,?,?,?)",
                (head_seq, head_hash, merkle_root, mmr_leaf_count, ots_proof, ts, "pending"),
            )
            self._conn.commit()
            return cur.lastrowid

    def update_anchor(self, anchor_id: int, ots_proof: Optional[bytes], status: str,
                      block_height: Optional[int] = None, block_time: Optional[str] = None):
        with self._lock:
            self._conn.execute(
                "UPDATE anchors SET ots_proof=?, status=?, block_height=?, block_time=? WHERE id=?",
                (ots_proof, status, block_height, block_time, anchor_id),
            )
            self._conn.commit()

    def get_all_anchors(self) -> list[dict]:
        with self._lock:
            rows = self._conn.execute("SELECT * FROM anchors ORDER BY head_seq ASC").fetchall()
        return [dict(r) for r in rows]

    def get_pending_anchors(self) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM anchors WHERE status='pending' ORDER BY head_seq ASC"
            ).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Paginated read
    # ------------------------------------------------------------------

    def get_entries_range(self, limit: int, offset: int) -> list[dict]:
        """Return up to `limit` entries starting at `offset`, ordered by seq."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM ledger ORDER BY seq ASC LIMIT ? OFFSET ?", (limit, offset)
            ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    # ------------------------------------------------------------------
    # DEMO ONLY — direct mutation for the tamper demonstration
    # ------------------------------------------------------------------

    # Explicit SQL statements keyed by field name — avoids dynamic column
    # interpolation while keeping the allowlist machine-checkable.
    _TAMPER_SQL: dict = {
        "payload":      "UPDATE ledger SET payload=? WHERE seq=?",
        "payload_hash": "UPDATE ledger SET payload_hash=? WHERE seq=?",
        "entry_hash":   "UPDATE ledger SET entry_hash=? WHERE seq=?",
        "prev_hash":    "UPDATE ledger SET prev_hash=? WHERE seq=?",
        "source_id":    "UPDATE ledger SET source_id=? WHERE seq=?",
        "timestamp":    "UPDATE ledger SET timestamp=? WHERE seq=?",
    }

    def _tamper_entry(self, seq: int, field: str, new_value: str):
        """Directly mutate a stored entry. DEMO USE ONLY."""
        sql = self._TAMPER_SQL.get(field)
        if sql is None:
            raise ValueError(f"Cannot tamper field: {field}")
        with self._lock:
            self._conn.execute(sql, (new_value, seq))
            self._conn.commit()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_dict(row) -> dict:
        d = dict(row)
        if "payload" in d and isinstance(d["payload"], str):
            try:
                d["payload"] = json.loads(d["payload"])
            except (json.JSONDecodeError, TypeError):
                pass
        return d
