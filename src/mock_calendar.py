"""
Mock OpenTimestamps calendar server for local development.

Speaks the real OTS calendar HTTP protocol but uses a simulated Bitcoin chain
instead of submitting to real calendars or mining real blocks.

  POST /              — accept a 32-byte digest, return pending attestation bytes
  GET  /timestamp/<hex> — return Bitcoin attestation bytes once the delay has elapsed
  GET  /healthz       — liveness probe

Run standalone:
  uvicorn src.mock_calendar:app --host 0.0.0.0 --port 14788 --log-level info

Or via docker-compose (see compose service "mock-calendar").

Environment variables:
  MOCK_CONFIRM_DELAY   seconds until a submission "confirms" (default: 30)
  MOCK_BLOCK_BASE      base block height for simulated confirmations (default: 895000)
  CALENDAR_URL         URL this calendar advertises in PendingAttestation proofs
                       (must be reachable by the client — use the docker service URL)
"""

import io
import logging
import os
import time

from fastapi import FastAPI, Request, Response

log = logging.getLogger(__name__)

CONFIRM_DELAY = int(os.getenv("MOCK_CONFIRM_DELAY", "30"))
BLOCK_BASE = int(os.getenv("MOCK_BLOCK_BASE", "895000"))
# The URL embedded in PendingAttestation so clients know where to poll for upgrades.
SELF_URL = os.getenv("CALENDAR_URL", "http://mock-calendar:14788")

app = FastAPI(title="Mock OTS Calendar", docs_url=None, redoc_url=None)

# digest_hex -> {"submitted_at": float}
_store: dict[str, dict] = {}


# ---------------------------------------------------------------------------
# OTS serialization helpers
# ---------------------------------------------------------------------------

def _pending_ts_bytes(digest: bytes) -> bytes:
    """Serialize a Timestamp with a PendingAttestation pointing back at this calendar."""
    from opentimestamps.core.timestamp import Timestamp
    from opentimestamps.core.notary import PendingAttestation
    from opentimestamps.core.serialize import BytesSerializationContext
    ts = Timestamp(digest)
    ts.attestations.add(PendingAttestation(SELF_URL))
    ctx = BytesSerializationContext()
    ts.serialize(ctx)
    return ctx.getbytes()


def _confirmed_ts_bytes(digest: bytes, block_height: int) -> bytes:
    """Serialize a Timestamp with a BitcoinBlockHeaderAttestation at the given height."""
    from opentimestamps.core.timestamp import Timestamp
    from opentimestamps.core.notary import BitcoinBlockHeaderAttestation
    from opentimestamps.core.serialize import BytesSerializationContext
    ts = Timestamp(digest)
    ts.attestations.add(BitcoinBlockHeaderAttestation(block_height))
    ctx = BytesSerializationContext()
    ts.serialize(ctx)
    return ctx.getbytes()


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.post("/")
async def submit(request: Request) -> Response:
    """Accept a raw digest and return a pending OTS attestation."""
    body = await request.body()
    if not body:
        return Response(status_code=400, content=b"empty body")

    digest_hex = body.hex()
    if digest_hex not in _store:
        _store[digest_hex] = {"submitted_at": time.time()}
        log.info("New commitment: %s… (confirms in %ds)", digest_hex[:16], CONFIRM_DELAY)

    try:
        ts_bytes = _pending_ts_bytes(body)
        return Response(content=ts_bytes, media_type="application/octet-stream")
    except Exception as exc:
        log.error("Failed to create pending timestamp: %s", exc)
        return Response(status_code=500, content=str(exc).encode())


@app.get("/timestamp/{digest_hex}")
async def get_timestamp(digest_hex: str) -> Response:
    """Return a confirmed attestation once MOCK_CONFIRM_DELAY seconds have elapsed."""
    entry = _store.get(digest_hex)
    if entry is None:
        return Response(status_code=404, content=b"Unknown commitment")

    elapsed = time.time() - entry["submitted_at"]
    if elapsed < CONFIRM_DELAY:
        log.debug("Commitment %s… not confirmed yet (%.0fs remaining)",
                  digest_hex[:16], CONFIRM_DELAY - elapsed)
        return Response(status_code=404, content=b"Pending")

    block_height = BLOCK_BASE + (int(entry["submitted_at"]) % 5000)
    log.info("Confirming %s… at simulated block %d", digest_hex[:16], block_height)

    try:
        digest = bytes.fromhex(digest_hex)
        ts_bytes = _confirmed_ts_bytes(digest, block_height)
        return Response(content=ts_bytes, media_type="application/octet-stream")
    except Exception as exc:
        log.error("Failed to create confirmed timestamp: %s", exc)
        return Response(status_code=500, content=str(exc).encode())


@app.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok", "pending_commitments": len(_store)}
