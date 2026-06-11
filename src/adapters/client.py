"""
LedgerClient — signs events with Ed25519 and ships them to the ledger.

DDIL (Denied/Degraded/Intermittent/Limited) support:
  When the ledger is unreachable, events are persisted to a local SQLite
  buffer and automatically flushed when connectivity is restored. No events
  are lost during network outages.

Usage:
    client = LedgerClient("http://localhost:8000", source_id="nav-planner")
    client.emit("route_computed", {"waypoints": 4})   # non-blocking, signed
    result = client.emit_sync("decision", {"action": "HOLD"})  # blocking

curl equivalent (unsigned, from any language):
    curl -X POST http://localhost:8000/events \\
         -H 'Content-Type: application/json' \\
         -d '{"source_id":"nav-planner","payload":{"event":"route_computed"}}'
"""

import json
import logging
import os
import queue
import sqlite3
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

# Signing is optional — client works unsigned if Cryptodome is absent
try:
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from signing import get_or_create_keypair, sign
    from ledger import canonical_json as _canonical_json   # canonical_json lives in ledger
    _SIGNING_AVAILABLE = True
except Exception as _exc:                                   # pragma: no cover
    logging.getLogger(__name__).warning("Signing disabled in client: %s", _exc)
    _SIGNING_AVAILABLE = False


class LedgerClient:
    """
    Thread-safe, DDIL-resilient client for the accountability ledger.

    Signs every event with the agent's Ed25519 key before sending.
    Falls back to unsigned if signing is unavailable.
    Buffers to local SQLite when the server is unreachable.
    """

    def __init__(self, base_url: str = "http://localhost:8000",
                 source_id: str = "unknown",
                 timeout: int = 5,
                 async_mode: bool = True,
                 buffer_path: Optional[str] = None,
                 heartbeat_interval: float = 0.0):
        self.base_url = base_url.rstrip("/")
        self.source_id = source_id
        self.timeout = timeout
        self._async = async_mode
        self._heartbeat_interval = heartbeat_interval

        # Per-agent signing key
        self._private_key = None
        self._key_id = None
        if _SIGNING_AVAILABLE:
            try:
                self._private_key, self._key_id = get_or_create_keypair(source_id)
                log.info("Signing enabled for %s (key_id=%s…)", source_id, self._key_id[:8])
            except Exception as exc:
                log.warning("Signing unavailable: %s", exc)

        # DDIL local buffer
        buf = buffer_path or f".ddil_buffer_{source_id.replace('/', '_')}.db"
        self._buf_conn = sqlite3.connect(buf, check_same_thread=False)
        self._buf_conn.execute("""
            CREATE TABLE IF NOT EXISTS buffer (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                payload   TEXT NOT NULL,
                attempts  INTEGER DEFAULT 0,
                created   REAL DEFAULT (strftime('%s','now'))
            )
        """)
        self._buf_conn.commit()
        self._buf_lock = threading.Lock()

        if async_mode:
            self._worker = threading.Thread(
                target=self._drain_loop, daemon=True, name=f"ledger-{source_id}"
            )
            self._worker.start()

        # Optional connectivity heartbeat: report buffered-event count to the
        # recorder so a dashboard can show this agent's DDIL state in real time.
        if heartbeat_interval > 0:
            self._hb = threading.Thread(
                target=self._heartbeat_loop, daemon=True, name=f"hb-{source_id}"
            )
            self._hb.start()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def emit(self, event_type: str, payload: Optional[dict] = None) -> None:
        """Queue a signed event. Returns immediately. Never raises."""
        body = self._build_body(event_type, payload)
        if self._async:
            self._buffer_locally(body)
        else:
            try:
                self._post(body)
            except Exception:
                self._buffer_locally(body)

    def emit_sync(self, event_type: str, payload: Optional[dict] = None) -> dict:
        """Post synchronously. Returns {seq, entry_hash}. Raises on failure."""
        body = self._build_body(event_type, payload)
        return self._post(body)

    def flush(self, timeout: float = 30.0) -> None:
        """Block until the local buffer is empty (all events delivered)."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with self._buf_lock:
                count = self._buf_conn.execute("SELECT COUNT(*) FROM buffer").fetchone()[0]
            if count == 0:
                return
            time.sleep(0.2)
        log.warning("flush() timed out with %d events still buffered", count)

    def buffered_count(self) -> int:
        """Number of events waiting in the local DDIL buffer."""
        with self._buf_lock:
            return self._buf_conn.execute("SELECT COUNT(*) FROM buffer").fetchone()[0]

    def close(self):
        if self._async:
            self.flush()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _build_body(self, event_type: str, payload: Optional[dict]) -> dict:
        full_payload = {"event_type": event_type, **(payload or {})}
        body: dict = {"source_id": self.source_id, "payload": full_payload}

        if self._private_key and _SIGNING_AVAILABLE:
            try:
                canonical = _canonical_json(full_payload)
                body["signature"] = sign(self._private_key, self.source_id, canonical)
                body["key_id"] = self._key_id
            except Exception as exc:
                log.warning("Signing failed, sending unsigned: %s", exc)

        return body

    def _post(self, body: dict) -> dict:
        return self._post_json("/events", body)

    def _post_json(self, path: str, body: dict) -> dict:
        data = json.dumps(body).encode()
        req = urllib.request.Request(
            f"{self.base_url}{path}",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            return json.loads(resp.read())

    def _heartbeat_loop(self):
        """Report buffered-event count to the recorder on a fixed interval."""
        while True:
            try:
                self._post_json("/agent/heartbeat", {
                    "source_id": self.source_id,
                    "buffered": self.buffered_count(),
                    "key_id": self._key_id,
                })
            except Exception:
                pass  # recorder unreachable — nothing to report; try again next tick
            time.sleep(self._heartbeat_interval)

    def _buffer_locally(self, body: dict):
        """Persist to local SQLite so no event is lost during outages."""
        with self._buf_lock:
            self._buf_conn.execute(
                "INSERT INTO buffer (payload) VALUES (?)", (json.dumps(body),)
            )
            self._buf_conn.commit()

    def _drain_loop(self):
        """Background thread: flush local buffer to ledger when reachable."""
        backoff = 1.0
        while True:
            try:
                self._flush_buffer()
                backoff = 1.0
            except Exception:
                backoff = min(backoff * 2, 30.0)
            time.sleep(backoff)

    def _flush_buffer(self):
        with self._buf_lock:
            rows = self._buf_conn.execute(
                "SELECT id, payload FROM buffer ORDER BY id ASC LIMIT 50"
            ).fetchall()

        if not rows:
            return

        delivered = []
        for row_id, payload_json in rows:
            try:
                body = json.loads(payload_json)
                self._post(body)
                delivered.append(row_id)
            except Exception:
                # Server unreachable — stop trying this batch, wait for reconnect
                break

        if delivered:
            with self._buf_lock:
                self._buf_conn.execute(
                    f"DELETE FROM buffer WHERE id IN ({','.join('?'*len(delivered))})",
                    delivered,
                )
                self._buf_conn.commit()
            log.info("DDIL flush: delivered %d buffered events", len(delivered))
