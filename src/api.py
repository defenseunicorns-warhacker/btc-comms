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
import sys
import threading
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import AsyncIterator

# Local-dev fallback: add src/ to sys.path when launched via
# `uvicorn src.api:app` from the project root without PYTHONPATH set.
# Docker sets PYTHONPATH=/app/src; pyproject.toml handles pytest.
_src = os.path.dirname(os.path.abspath(__file__))
if _src not in sys.path:
    sys.path.insert(0, _src)

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from ledger import LedgerStore, canonical_json, sha256, payload_hash as _payload_hash
from verify import verify as run_verify
from anchor import AnchorLoop, _stamp_mock, _upgrade_mock
import mmr as _mmr
from roe_schema import validate_roe_payload
try:
    from signing import verify_signature, get_public_key, list_keys, get_or_create_keypair, sign
    _SIGNING_AVAILABLE = True
except ImportError:
    _SIGNING_AVAILABLE = False

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

def _flag(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).lower() in ("true", "1", "yes")

DEMO_MODE = _flag("DEMO_MODE")
MOCK_ANCHOR = _flag("MOCK_ANCHOR")
# When false, the background stamp/upgrade thread is not started — anchoring then
# happens only via explicit POST /anchor/now and /anchor/upgrade. Used by the
# visual demo so the "Anchor to Bitcoin" step is deterministic (no stale genesis
# anchor created at startup). Defaults true to preserve normal behavior.
AUTO_STAMP = _flag("AUTO_STAMP", "true")
DB_PATH = os.getenv("DB_PATH", "ledger.db")
STAMP_INTERVAL = int(os.getenv("STAMP_INTERVAL", "30"))
UPGRADE_INTERVAL = int(os.getenv("UPGRADE_INTERVAL", "30"))

# Enforcement knobs (off by default so the demo is frictionless).
#   STRICT_SIGNING=true           → reject any event without a valid registered signature.
#   REQUIRE_PROVISIONED_KEYS=true → additionally reject self-enrolled (TOFU) keys; only
#                                   authority-provisioned keys are honored. Implies signing.
#   API_TOKEN=<secret>            → require Bearer/X-API-Key on all mutating endpoints.
STRICT_SIGNING = _flag("STRICT_SIGNING")
REQUIRE_PROVISIONED_KEYS = _flag("REQUIRE_PROVISIONED_KEYS")
API_TOKEN = os.getenv("API_TOKEN", "").strip()
# Restrict in production: CORS_ORIGINS=https://dashboard.example.com
_cors_origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",")]

# ---------------------------------------------------------------------------
# Shared state
# ---------------------------------------------------------------------------

store: LedgerStore
anchor_loop: AnchorLoop
_sse_lock = threading.Lock()
_sse_queues: list[asyncio.Queue] = []
# Latest DDIL connectivity heartbeat per agent (in-memory telemetry, not ledger state).
_agent_status: dict[str, dict] = {}


def _require_auth(request: Request):
    """
    Gate mutating endpoints behind a shared token when API_TOKEN is set.
    Accepts either `Authorization: Bearer <token>` or `X-API-Key: <token>`.
    No-op when API_TOKEN is unset (demo default).
    """
    if not API_TOKEN:
        return
    header = request.headers.get("authorization", "")
    presented = ""
    if header.lower().startswith("bearer "):
        presented = header[7:].strip()
    if not presented:
        presented = request.headers.get("x-api-key", "").strip()
    # Constant-time compare to avoid token-length/timing leakage
    import hmac
    if not presented or not hmac.compare_digest(presented, API_TOKEN):
        raise HTTPException(status_code=401, detail="Missing or invalid API token")


def _broadcast(event: dict):
    """Push an event to all active SSE subscribers."""
    with _sse_lock:
        queues = list(_sse_queues)
    for q in queues:
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
    if AUTO_STAMP:
        anchor_loop.start()
    else:
        log.info("AUTO_STAMP=false — background stamper not started; "
                 "anchoring is manual via /anchor/now + /anchor/upgrade")

    yield

    if AUTO_STAMP:
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
    allow_origins=_cors_origins,
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


@app.get("/info")
async def info():
    """Runtime config for the dashboard (JSON). `/` serves the HTML dashboard,
    so the front-end reads its feature flags from here, not from `/`."""
    return {
        "status": "ok",
        "demo_mode": DEMO_MODE,
        "mock_anchor": MOCK_ANCHOR,
        "strict_signing": STRICT_SIGNING,
        "require_provisioned_keys": REQUIRE_PROVISIONED_KEYS,
    }


# ---------------------------------------------------------------------------
# Core endpoints
# ---------------------------------------------------------------------------

class EventRequest(BaseModel):
    source_id: str
    payload: dict
    signature: str | None = None   # hex Ed25519 signature over source_id:canonical_json(payload)
    key_id: str | None = None      # key fingerprint registered in keys/registry.json


@app.post("/events", status_code=201)
async def append_event(req: EventRequest, request: Request):
    _require_auth(request)

    # Strict / provisioned modes: every event MUST carry a valid, registered signature.
    if STRICT_SIGNING or REQUIRE_PROVISIONED_KEYS:
        if not _SIGNING_AVAILABLE:
            raise HTTPException(status_code=503, detail="Signature enforcement enabled but signing module unavailable")
        if not (req.signature and req.key_id):
            raise HTTPException(status_code=403, detail=(
                "Signature enforcement enabled — unsigned events are rejected. "
                "Provide signature + key_id."
            ))

    # Verify signature at ingest if provided — reject forged attribution. When
    # REQUIRE_PROVISIONED_KEYS is set, also reject self-enrolled (TOFU) keys: only
    # keys issued by the provisioning authority are honored.
    if req.signature and req.key_id and _SIGNING_AVAILABLE:
        payload_bytes = canonical_json(req.payload)
        if not verify_signature(req.signature, req.key_id, req.source_id, payload_bytes,
                                require_provisioned=REQUIRE_PROVISIONED_KEYS):
            raise HTTPException(status_code=403, detail=(
                f"Signature verification failed for source_id='{req.source_id}'. "
                "Event rejected — forged attribution or unprovisioned key."
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
    page = store.get_entries_range(min(limit, 1000), offset)
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
      entry            — the entry itself
      proof            — {type:"mmr", leaf_hash, path, peak_hashes, peak_index, leaf_index, leaf_count}
      anchor           — the most recent anchor whose MMR root covers this entry
      valid            — True only if payload integrity, entry_hash integrity, AND MMR inclusion all pass
      payload_hash_ok  — payload still matches its stored hash (detects payload tampering)
      entry_hash_ok    — entry_hash still matches the recomputed value (detects field tampering)
      mmr_inclusion_ok — entry_hash is present in the MMR tree
      mmr_root         — the root the proof computes to
    """
    entry = store.get_entry(seq)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"No entry at seq={seq}")

    try:
        proof = store.get_mmr_inclusion_proof(seq)
    except (IndexError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    # 1. Verify payload still matches its stored hash.
    #    A tampered payload leaves entry_hash intact, so MMR inclusion alone cannot
    #    catch this — the content check is what catches it.
    payload = entry["payload"]
    computed_ph = _payload_hash(payload) if isinstance(payload, dict) else sha256(payload.encode())
    payload_hash_ok = computed_ph == entry["payload_hash"]

    # 2. Verify entry_hash still matches what the stored fields hash to.
    recomputed_eh = sha256(canonical_json({
        "seq": entry["seq"],
        "timestamp": entry["timestamp"],
        "source_id": entry["source_id"],
        "payload_hash": entry["payload_hash"],
        "prev_hash": entry["prev_hash"],
    }))
    entry_hash_ok = recomputed_eh == entry["entry_hash"]

    # 3. Verify this entry_hash is present in the MMR tree.
    mmr_inclusion_ok, computed_root = _mmr.verify_proof(entry["entry_hash"], proof)

    valid = payload_hash_ok and entry_hash_ok and mmr_inclusion_ok

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
        "payload_hash_ok": payload_hash_ok,
        "entry_hash_ok": entry_hash_ok,
        "mmr_inclusion_ok": mmr_inclusion_ok,
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
    with _sse_lock:
        _sse_queues.append(queue)

    async def generator():
        try:
            # Send current snapshot on connect
            yield {"event": "snapshot", "data": json.dumps({
                "entries": [_sanitize(e) for e in store.get_all_entries()],
                "anchors": [_anchor_out(a) for a in store.get_all_anchors()],
                "agents": list(_agent_status.values()),
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
            with _sse_lock:
                try:
                    _sse_queues.remove(queue)
                except ValueError:
                    pass

    return EventSourceResponse(generator())


# ---------------------------------------------------------------------------
# Agent connectivity (DDIL telemetry — separate from the ledger)
# ---------------------------------------------------------------------------

class AgentHeartbeat(BaseModel):
    source_id: str
    buffered: int = 0
    key_id: str | None = None


@app.post("/agent/heartbeat")
async def agent_heartbeat(hb: AgentHeartbeat):
    """Agents report their local DDIL buffer depth so the dashboard can show
    connectivity in real time. In-memory telemetry only — never touches the ledger."""
    status = {
        "source_id": hb.source_id,
        "buffered": max(0, hb.buffered),
        "key_id": hb.key_id,
        "ts": time.time(),
    }
    _agent_status[hb.source_id] = status
    _broadcast({"type": "agent_status", "data": status})
    return {"ok": True}


@app.get("/agent/status")
async def agent_status():
    return list(_agent_status.values())


# ---------------------------------------------------------------------------
# Anchor convenience
# ---------------------------------------------------------------------------

@app.post("/anchor/now")
async def anchor_now(request: Request):
    _require_auth(request)
    result = anchor_loop.stamp_now()
    if result is None:
        head = store.get_head()
        return {"message": "Nothing new to stamp", "current_head": head["seq"] if head else None}
    _broadcast({"type": "anchor", "data": result})
    return result


@app.post("/anchor/upgrade")
async def upgrade_anchors(request: Request):
    _require_auth(request)
    anchor_loop.upgrade_now()
    # Broadcast updated anchor states so SSE clients see confirmed status.
    # Use _anchor_out to strip the raw ots_proof bytes (not JSON-serializable).
    for a in store.get_all_anchors():
        _broadcast({"type": "anchor", "data": _anchor_out(a)})
    return {"message": "Upgrade pass triggered"}


# ---------------------------------------------------------------------------
# DEMO ONLY endpoints
# ---------------------------------------------------------------------------

class TamperRequest(BaseModel):
    seq: int
    field: str = "payload"
    new_value: str


@app.post("/tamper")
async def tamper(req: TamperRequest, request: Request):
    _require_auth(request)
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


class DemoAppendRequest(BaseModel):
    source_id: str
    payload: dict


@app.post("/demo/append", status_code=201)
async def demo_append(req: DemoAppendRequest, request: Request):
    """DEMO ONLY — append an event signed server-side with the agent's enrolled
    key. In production each agent signs locally; the demo signs on its behalf so
    the scenario exercises the real Ed25519 attribution path (and so post-break
    entries stay individually attributable during recovery)."""
    _require_auth(request)
    if not DEMO_MODE:
        raise HTTPException(status_code=403, detail="Disabled outside DEMO_MODE")
    signature = key_id = None
    if _SIGNING_AVAILABLE:
        priv, key_id = get_or_create_keypair(req.source_id)
        signature = sign(priv, req.source_id, canonical_json(req.payload))
    entry = store.append(req.source_id, req.payload, signature=signature, key_id=key_id)
    _broadcast({"type": "entry", "data": _sanitize(entry)})
    return {"seq": entry["seq"], "entry_hash": entry["entry_hash"]}


class RebaselineRequest(BaseModel):
    broken_at: int
    reason: str | None = None
    checkpoint_seq: int
    checkpoint_hash: str | None = None
    block_height: int | None = None


@app.post("/demo/rebaseline")
async def demo_rebaseline(req: RebaselineRequest, request: Request):
    """DEMO ONLY — the operator's recovery action after a confirmed tamper.

    You do NOT fix a broken chain in place — that's just more tampering. Instead:
    seal the compromised chain as forensic evidence, then start a fresh chain
    whose genesis embeds the last clean Bitcoin-anchored checkpoint. New activity
    chains and anchors forward from a state the attacker could not rewrite."""
    _require_auth(request)
    if not DEMO_MODE:
        raise HTTPException(status_code=403, detail="Disabled outside DEMO_MODE")
    genesis = store.rebaseline(
        broken_at=req.broken_at, reason=req.reason,
        checkpoint_seq=req.checkpoint_seq, checkpoint_hash=req.checkpoint_hash,
        block_height=req.block_height,
    )
    # 'reset'-type event: clients re-fetch the (now fresh) chain and clear anchors.
    _broadcast({"type": "reset", "data": {"ok": True, "rebaselined": True}})
    return {"ok": True, "rebaselined": True, "checkpoint_seq": req.checkpoint_seq,
            "genesis": _sanitize(genesis)}


@app.post("/demo/reset")
async def demo_reset(request: Request):
    """DEMO ONLY — wipe the ledger back to genesis so the demo can re-run."""
    _require_auth(request)
    if not DEMO_MODE:
        raise HTTPException(status_code=403, detail="Disabled outside DEMO_MODE")
    store.reset()
    anchor_loop.reset_tracking()
    _broadcast({"type": "reset", "data": {"ok": True}})
    return {"ok": True, "reset": True}


@app.post("/seed")
async def seed_events(request: Request, n: int = 10):
    _require_auth(request)
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
    # Per-agent signing so the demo's primary populate path exercises the real
    # Ed25519 attribution flow (otherwise seeded entries show as unsigned).
    results = []
    for i in range(n):
        agent = agents[i % len(agents)]
        payload = actions[i % len(actions)]
        signature = key_id = None
        if _SIGNING_AVAILABLE:
            priv, key_id = get_or_create_keypair(agent)
            signature = sign(priv, agent, canonical_json(payload))
        entry = store.append(agent, payload, signature=signature, key_id=key_id)
        _broadcast({"type": "entry", "data": _sanitize(entry)})
        results.append({"seq": entry["seq"], "source_id": agent})
    return {"seeded": len(results), "entries": results}


@app.post("/demo/impersonate")
async def demo_impersonate(request: Request):
    """DEMO ONLY — attempt a forged-attribution event and show it rejected.

    Signs a payload AS the victim using the attacker's own enrolled key, then runs
    the exact check the /events ingest path runs (verify_signature). The registry
    binds key→identity, so a key enrolled to one agent cannot sign as another."""
    _require_auth(request)
    if not DEMO_MODE:
        raise HTTPException(status_code=403, detail="Disabled outside DEMO_MODE")
    if not _SIGNING_AVAILABLE:
        return {"available": False, "rejected": False, "reason": "Signing module unavailable"}
    from ledger import canonical_json
    attacker_sid, victim_sid = "nav-planner", "threat-classifier"
    attacker_priv, attacker_kid = get_or_create_keypair(attacker_sid)
    get_or_create_keypair(victim_sid)  # ensure victim is a real enrolled identity
    payload = {"event_type": "roe_decision", "final_action": "ENGAGE",
               "human_authorized": True, "note": "forged by adversary"}
    canonical = canonical_json(payload)
    # Forge: sign the message AS the victim, using the attacker's key.
    forged_sig = sign(attacker_priv, victim_sid, canonical)
    # The real ingest check — returns False because the key isn't enrolled to the victim.
    accepted = verify_signature(forged_sig, attacker_kid, victim_sid, canonical)
    return {
        "available": True,
        "attacker": attacker_sid,
        "victim": victim_sid,
        "attacker_key": attacker_kid,
        "rejected": not accepted,
        "reason": f"A key enrolled to '{attacker_sid}' cannot sign as '{victim_sid}'.",
    }


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
