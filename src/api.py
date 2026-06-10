"""
FastAPI application: the HTTP surface for the accountability layer.

Endpoints:
  POST /events                  append an event
  GET  /verify                  run full verification
  GET  /entries                 list all ledger entries
  GET  /entries/{seq}/proof     Merkle inclusion proof for one entry (selective disclosure)
  GET  /anchors                 list all anchors with status
  GET  /stream                  SSE stream of new entries (dashboard live feed)
  POST /tamper                  DEMO ONLY (requires DEMO_MODE=true)
  POST /seed                    DEMO ONLY: populate sample events
  POST /anchor/now              trigger an immediate stamp (demo convenience)
"""

import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import AsyncIterator

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from ledger import LedgerStore
from verify import verify as run_verify
from anchor import AnchorLoop, _stamp_mock, _upgrade_mock
import mmr as _mmr
from roe_schema import validate_roe_payload
try:
    from signing import verify_signature, get_public_key, list_keys
    _SIGNING_AVAILABLE = True
except ImportError:
    _SIGNING_AVAILABLE = False

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

DEMO_MODE = os.getenv("DEMO_MODE", "false").lower() in ("true", "1", "yes")
MOCK_ANCHOR = os.getenv("MOCK_ANCHOR", "false").lower() in ("true", "1", "yes")
DB_PATH = os.getenv("DB_PATH", "ledger.db")
STAMP_INTERVAL = int(os.getenv("STAMP_INTERVAL", "30"))
UPGRADE_INTERVAL = int(os.getenv("UPGRADE_INTERVAL", "15"))  # check more often in mock mode

# ---------------------------------------------------------------------------
# Shared state
# ---------------------------------------------------------------------------

store: LedgerStore
anchor_loop: AnchorLoop
_sse_queues: list[asyncio.Queue] = []


def _broadcast(event: dict):
    """Push an event to all active SSE subscribers."""
    for q in list(_sse_queues):
        try:
            q.put_nowait(event)
        except asyncio.QueueFull:
            pass


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    global store, anchor_loop
    store = LedgerStore(DB_PATH)
    store.ensure_genesis()

    if MOCK_ANCHOR:
        log.info("MOCK_ANCHOR=true — using local proof simulation (no Bitcoin network needed)")
        anchor_loop = AnchorLoop(
            store,
            stamp_interval=STAMP_INTERVAL,
            upgrade_interval=UPGRADE_INTERVAL,
            stamp_fn=_stamp_mock,
            upgrade_fn=_upgrade_mock,
        )
    else:
        anchor_loop = AnchorLoop(
            store,
            stamp_interval=STAMP_INTERVAL,
            upgrade_interval=UPGRADE_INTERVAL,
        )
    anchor_loop.start()

    yield

    anchor_loop.stop()


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Immutable Accountability Layer",
    description="Hash-chained event ledger with Bitcoin anchoring via OpenTimestamps",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve the dashboard from web/
_web_dir = os.path.join(os.path.dirname(__file__), "..", "web")
if os.path.isdir(_web_dir):
    app.mount("/static", StaticFiles(directory=_web_dir), name="static")


@app.get("/", include_in_schema=False)
async def root():
    index = os.path.join(_web_dir, "index.html")
    if os.path.isfile(index):
        return FileResponse(index)
    return {"status": "ok", "demo_mode": DEMO_MODE, "mock_anchor": MOCK_ANCHOR}


# ---------------------------------------------------------------------------
# Core endpoints
# ---------------------------------------------------------------------------

class EventRequest(BaseModel):
    source_id: str
    payload: dict
    signature: str | None = None   # hex Ed25519 signature over source_id:canonical_json(payload)
    key_id: str | None = None      # key fingerprint registered in keys/registry.json


@app.post("/events", status_code=201)
async def append_event(req: EventRequest):
    # Verify signature at ingest if provided — reject forged attribution
    if req.signature and req.key_id and _SIGNING_AVAILABLE:
        from ledger import canonical_json
        payload_bytes = canonical_json(req.payload)
        if not verify_signature(req.signature, req.key_id, req.source_id, payload_bytes):
            raise HTTPException(status_code=403, detail=(
                f"Signature verification failed for source_id='{req.source_id}'. "
                "Event rejected — forged attribution detected."
            ))

    # ROE schema validation — warn but don't reject (backwards-compatible)
    roe_ok, roe_missing = validate_roe_payload(req.payload)
    roe_warning = None
    if not roe_ok:
        roe_warning = f"ROE schema incomplete, missing: {roe_missing}"
        log.warning("ROE validation: %s", roe_warning)

    entry = store.append(req.source_id, req.payload,
                         signature=req.signature, key_id=req.key_id)
    _broadcast({"type": "entry", "data": _sanitize(entry)})
    resp: dict = {"seq": entry["seq"], "entry_hash": entry["entry_hash"]}
    if roe_warning:
        resp["roe_warning"] = roe_warning
    return resp


@app.get("/keys")
async def list_registered_keys():
    """Return all registered public keys (no private material)."""
    if not _SIGNING_AVAILABLE:
        return {"available": False}
    keys = list_keys()
    # Strip PEM bodies from API response — expose only metadata
    return {kid: {k: v for k, v in info.items() if k != "public_key_pem"}
            for kid, info in keys.items()}


@app.get("/verify")
async def verify_chain():
    entries = store.get_all_entries()
    anchors = store.get_all_anchors()
    result = run_verify(entries, anchors)
    _broadcast({"type": "verify", "data": result.to_dict()})
    return result.to_dict()


@app.get("/entries")
async def list_entries(limit: int = 200, offset: int = 0):
    all_entries = store.get_all_entries()
    page = all_entries[offset: offset + limit]
    return [_sanitize(e) for e in page]


@app.get("/entries/{seq}/proof")
async def get_mmr_proof(seq: int):
    """
    Return an MMR inclusion proof for entry `seq`.

    The proof lets a third party verify that this specific entry existed and
    was unmodified at the time of the latest anchor — without revealing any
    other entries. Relevant for classified contexts where selective disclosure
    is required.

    Response includes:
      entry        — the entry itself (share only this + the proof, not the full ledger)
      proof        — {type:"mmr", leaf_hash, path, peak_hashes, peak_index, leaf_index, leaf_count}
      anchor       — the most recent anchor whose MMR root covers this entry
      valid        — whether the proof verifies locally right now
      mmr_root     — the root the proof computes to
    """
    entry = store.get_entry(seq)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"No entry at seq={seq}")

    try:
        proof = store.get_mmr_inclusion_proof(seq)
    except (IndexError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    valid, computed_root = _mmr.verify_proof(entry["entry_hash"], proof)

    # Find the best anchor (highest confirmed, else highest pending) that covers this seq
    anchors = store.get_all_anchors()
    covering = [a for a in anchors if a["head_seq"] >= seq]
    covering.sort(key=lambda a: (a["status"] == "confirmed", a["head_seq"]), reverse=True)
    best_anchor = _anchor_out(covering[0]) if covering else None

    anchor_root = covering[0].get("merkle_root") if covering else None
    root_matches = (anchor_root == computed_root) if anchor_root else None

    return {
        "entry": _sanitize(entry),
        "proof": proof,
        "anchor": best_anchor,
        "valid": valid,
        "mmr_root": computed_root,
        "root_matches_anchor": root_matches,
    }


@app.get("/anchors")
async def list_anchors():
    anchors = store.get_all_anchors()
    return [_anchor_out(a) for a in anchors]


# ---------------------------------------------------------------------------
# SSE stream
# ---------------------------------------------------------------------------

@app.get("/stream")
async def event_stream(request: Request):
    queue: asyncio.Queue = asyncio.Queue(maxsize=100)
    _sse_queues.append(queue)

    async def generator():
        try:
            # Send current snapshot on connect
            yield {"event": "snapshot", "data": json.dumps({
                "entries": [_sanitize(e) for e in store.get_all_entries()],
                "anchors": [_anchor_out(a) for a in store.get_all_anchors()],
            })}

            while True:
                if await request.is_disconnected():
                    break
                try:
                    evt = await asyncio.wait_for(queue.get(), timeout=15)
                    yield {"event": evt["type"], "data": json.dumps(evt["data"])}
                except asyncio.TimeoutError:
                    yield {"event": "heartbeat", "data": "{}"}
        finally:
            _sse_queues.remove(queue)

    return EventSourceResponse(generator())


# ---------------------------------------------------------------------------
# Anchor convenience
# ---------------------------------------------------------------------------

@app.post("/anchor/now")
async def anchor_now():
    result = anchor_loop.stamp_now()
    if result is None:
        head = store.get_head()
        return {"message": "Nothing new to stamp", "current_head": head["seq"] if head else None}
    _broadcast({"type": "anchor", "data": result})
    return result


@app.post("/anchor/upgrade")
async def upgrade_anchors():
    anchor_loop.upgrade_now()
    return {"message": "Upgrade pass triggered"}


# ---------------------------------------------------------------------------
# DEMO ONLY endpoints
# ---------------------------------------------------------------------------

class TamperRequest(BaseModel):
    seq: int
    field: str = "payload"
    new_value: str


@app.post("/tamper")
async def tamper(req: TamperRequest):
    if not DEMO_MODE:
        raise HTTPException(
            status_code=403,
            detail="Tamper endpoint disabled. Set DEMO_MODE=true to enable. DEMO USE ONLY."
        )
    # ----------------------------------------------------------------
    # DEMO ONLY: deliberately breaks chain integrity for live demo.
    # This endpoint exists solely to show that tampering is detectable.
    # ----------------------------------------------------------------
    entry = store.get_entry(req.seq)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"No entry at seq={req.seq}")
    store._tamper_entry(req.seq, req.field, req.new_value)
    _broadcast({"type": "tamper", "data": {"seq": req.seq, "field": req.field}})
    return {"ok": True, "tampered_seq": req.seq, "field": req.field}


@app.post("/seed")
async def seed_events(n: int = 10):
    if not DEMO_MODE:
        raise HTTPException(status_code=403, detail="Seed endpoint disabled outside DEMO_MODE")
    agents = ["nav-planner", "threat-classifier", "comms-router", "logistics-ai", "sensor-fusion"]
    actions = [
        {"type": "route_computed", "waypoints": 4, "fuel_pct": 87},
        {"type": "threat_detected", "confidence": 0.94, "class": "UAS", "bearing": 142},
        {"type": "comms_relay", "freq_mhz": 243.0, "encrypted": True},
        {"type": "supply_request", "item": "ammunition", "qty": 500, "priority": "HIGH"},
        {"type": "sensor_ping", "sensor_id": "FLIR-7", "azimuth": 315, "elevation": -5},
        {"type": "decision_log", "action": "HOLD_FIRE", "authority": "human-in-loop"},
        {"type": "position_report", "lat": 34.0522, "lon": -118.2437, "alt_m": 120},
        {"type": "comms_blackout", "duration_s": 45, "reason": "jamming_detected"},
        {"type": "target_acquired", "target_id": "T-0091", "confidence": 0.88},
        {"type": "mission_phase_change", "from": "ingress", "to": "on_station"},
    ]
    import random
    random.seed(42)
    results = []
    for i in range(n):
        agent = agents[i % len(agents)]
        payload = actions[i % len(actions)]
        entry = store.append(agent, payload)
        _broadcast({"type": "entry", "data": _sanitize(entry)})
        results.append({"seq": entry["seq"], "source_id": agent})
    return {"seeded": len(results), "entries": results}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sanitize(entry: dict) -> dict:
    """Return a JSON-safe version of a ledger entry."""
    d = dict(entry)
    if "payload" in d and isinstance(d["payload"], bytes):
        d["payload"] = d["payload"].decode("utf-8", errors="replace")
    return d


def _anchor_out(anchor: dict) -> dict:
    d = dict(anchor)
    # Don't send raw proof bytes over JSON — they're binary
    if "ots_proof" in d and d["ots_proof"] is not None:
        d["ots_proof_size_bytes"] = len(d["ots_proof"])
        d["ots_proof_available"] = True
    else:
        d["ots_proof_size_bytes"] = 0
        d["ots_proof_available"] = False
    del d["ots_proof"]
    return d
