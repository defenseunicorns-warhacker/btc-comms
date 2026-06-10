# Immutable Accountability Layer

AI agents are making autonomous decisions in defense networks. If those agents can also modify or delete their own logs, accountability collapses. This system makes that impossible.

Every event an AI agent emits is cryptographically chained to the previous one and anchored to the Bitcoin blockchain. Altering, deleting, or backdating any record — even by the AI that created it — is immediately detectable.

*CODENAME:* STABLE -- Signed Tamper-evident Anchored Blockchain Ledger of Events
---

## The guarantee (stated accurately)

**Local tamper-evidence: real-time.** The moment an entry is appended, any later edit to any prior entry is detectable. No network required.

**External proof: near-real-time.** Every 30 seconds, the current chain head is stamped to Bitcoin via OpenTimestamps. Once a block confirms (~10 minutes), that stamp is externally verifiable and irreversible by anyone on earth.

> "Continuous tamper-evidence in real time. Externally verifiable, irreversible proof up to the most recent confirmed anchor."

---

## Quick start

```bash
pip install -r requirements.txt

# Local demo (mock Bitcoin confirmation in 30s, tamper endpoint enabled)
DEMO_MODE=true MOCK_ANCHOR=true uvicorn src.api:app --reload

open http://localhost:8000
```

One command with Docker:

```bash
docker compose up
```

Run the simulated AI agent in a second terminal:

```bash
python3 examples/demo_agent.py
```

---

## Demo script

1. Start the server. Open the dashboard.
2. Click **Seed 10 demo events** — realistic AI-agent events populate the ledger.
3. Click **Stamp head now** — anchor submitted (confirms in ~30s in mock mode).
4. Click **Run verify()** — banner goes green. Chain intact.
5. Enter a seq number and click **Tamper entry** — banner flips red. Exact broken entry named.
6. Click **Generate proof** on any entry — Merkle inclusion proof showing that single entry is authentic, without revealing any others.

---

## How it works

### Hash chain

Each entry commits to the one before it:

```
entry_hash = SHA-256(seq + timestamp + source_id + payload_hash + prev_hash)
```

Change one byte anywhere in history and every subsequent hash breaks. Deleting an entry leaves a sequence gap that `verify()` reports immediately.

### Merkle tree + selective disclosure

A Merkle tree is built over all entry hashes at each anchor point. The Merkle root — not just the chain head — is what gets stamped to Bitcoin.

This means you can prove a single AI decision is authentic without revealing any other entries. Hand an investigator the entry, a short proof path, and the anchored root. They verify it independently. Nothing else needs to be declassified.

### Bitcoin anchor

The Merkle root is submitted to OpenTimestamps, which aggregates it into a Bitcoin transaction. Once confirmed, the block header is an immutable timestamp that no one — including the system operators — can rewrite.

### Per-agent signing

Every agent has an Ed25519 keypair. Events are signed before submission. The recorder verifies the signature at ingest and rejects anything with a mismatched attribution. `source_id` is cryptographically enforced, not just a string.

In production: swap file-based keys for TPM or HSM keys. The signing interface is unchanged.

### DDIL resilience

Agents buffer events locally when the recorder is unreachable. When connectivity returns, buffered events flush automatically in order. No events are lost during network outages — including in air-gapped or jammed environments.

### ROE event schema

Rules of Engagement decisions are structured with mandatory fields that JAG officers and investigators can interpret without engineering support:

- What was decided and why
- Whether a human authorized it (and who)
- What the AI's confidence was
- What information was available at decision time
- Latency from detection to authorization
- Which ROE rule applied

---

## Wiring into an existing system

Three integration patterns — pick the one that fits:

**Two lines for any Python app using standard logging:**
```python
from adapters import LedgerLogHandler
logging.getLogger().addHandler(LedgerLogHandler("my-service"))
```

**One decorator for any function:**
```python
@audit_log(client)
def classify_threat(sensor_data):
    ...  # existing code unchanged
```

**One curl for anything else:**
```bash
curl -X POST http://localhost:8000/events \
     -H 'Content-Type: application/json' \
     -d '{"source_id":"my-service","payload":{"event":"decision","action":"HOLD"}}'
```

---

## API

| Method | Path | What it does |
|---|---|---|
| `POST` | `/events` | Append a signed event |
| `GET` | `/verify` | Run full chain + signature + Merkle verification |
| `GET` | `/entries` | List all ledger entries |
| `GET` | `/entries/{seq}/proof` | Merkle inclusion proof for one entry |
| `GET` | `/anchors` | Anchor list with pending/confirmed status |
| `GET` | `/keys` | Registered public keys |
| `GET` | `/stream` | Live SSE feed (dashboard) |
| `POST` | `/anchor/now` | Stamp immediately |
| `POST` | `/tamper` | **DEMO ONLY** — break the chain for the live demo |

---

## Running tests

```bash
python3 -m pytest tests/ -v
```

47 tests. Covers hash chain integrity, Merkle proofs for all tree sizes and positions, tamper detection at every entry, anchor verification, signature rejection, DDIL buffer, and ROE schema validation.

---

## What this proves (and what it doesn't)

**Proves:** a record existed at time T and has not been altered since.

**Does not prove:** the record was true when written. The system is tamper-evident, not tamper-proof. Garbage in, garbage out — but the garbage is now permanently recorded.

**Trust model:** the recorder runs in a separate trust domain from the agents it audits. Agents have write-only access. No agent can modify or delete its own entries.

---

## Production upgrade path

| This demo | Production |
|---|---|
| File-based Ed25519 keys | TPM / HSM / CAC-backed keys |
| GPS time via system clock | GPS-disciplined clock (GPSD) |
| SQLite with WAL mode | Replicated append-only store (Litestream / Kafka) |
| Mock Bitcoin confirmation | Real OpenTimestamps mainnet (public, free) |
| Single recorder process | Raft-replicated recorder cluster |

The cryptographic construction — hash chain, Merkle tree, Bitcoin anchor — does not change between demo and production.

---

## File layout

```
src/
  ledger.py          hash chain, SQLite store
  verify.py          verify() — chain + signatures + Merkle + anchors
  anchor.py          OpenTimestamps stamping loop
  merkle.py          Merkle tree, inclusion proofs, verify_proof
  signing.py         Ed25519 keypairs, sign, verify
  roe_schema.py      ROE decision schema for JAG compliance
  api.py             HTTP endpoints (FastAPI)
  adapters/
    client.py        DDIL-resilient signed HTTP client
    logging_handler.py  drop-in Python logging integration
    audit_decorator.py  @audit_log function decorator
web/
  index.html         live dashboard
examples/
  demo_agent.py      simulated AI agent using all three adapters
tests/
  test_verify.py     chain integrity tests
  test_merkle.py     Merkle tree tests
```
