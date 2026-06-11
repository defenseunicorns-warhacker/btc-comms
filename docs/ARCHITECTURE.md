# Architecture & Technical Reference

STABLE — *Signed, Tamper-evident, Anchored Blockchain Ledger of Events.*

This is the engineer's reference: the data model, the cryptographic
construction, the API, configuration, the trust model, and the production
upgrade path. For the plain-language mission framing see the
[README](../README.md); for the live demo see [DEMO.md](DEMO.md).

---

## Trust model (read this first)

- **The recorder runs in a separate trust domain from the agents it audits.**
  Agents have *write-only* access — there is no modify or delete path exposed to
  a source. The process that holds the ledger assigns `seq`, `timestamp`, and
  computes every hash; the source supplies only `payload` and `source_id`.
- **Capture as close to the source as possible** to shrink the window before an
  event is hashed.
- **Monotonic sequence numbers make deletion detectable** — a gap is evidence.

**What it proves:** a record existed at time *T* and has not been altered since.
**What it does not prove:** that the record was *true* when written. The system
is tamper-**evident**, attributable, and non-repudiable — never tamper-*proof*.
Garbage in is now *permanently recorded* garbage, which is exactly what an
investigation needs.

**Residual trust assumption:** key *enrollment* is the trust anchor. In the demo
keys self-enroll on first use (TOFU). In production, enrollment must be gated by
a provisioning authority (CAC/PIV, an enrollment CA, or HSM attestation) so an
attacker cannot pre-register a victim's `source_id`. The signing/verification
path is unchanged — only the key-issuance step hardens.

**Registry integrity:** `keys/registry.json` is the trust anchor for key–identity
binding. In production it must be write-protected at the OS/deployment level
(read-only mount, file ACL, or replaced by an external PKI/LDAP directory) so an
attacker who gains filesystem access cannot enrol a new key under an existing
identity.

---

## The two layered guarantees

STABLE is *near*-real-time, and it is important to state that accurately. There
are two guarantees with different latencies:

- **Local tamper-evidence — real-time.** The moment an entry is appended, any
  later edit to any prior entry is detectable. No network required.
- **External proof — near-real-time.** Every `STAMP_INTERVAL` seconds the current
  chain head is stamped to Bitcoin via OpenTimestamps. Once a block confirms
  (~10 minutes), that stamp is externally verifiable and irreversible by anyone.

> "Continuous tamper-evidence in real time. Externally verifiable, irreversible
> proof up to the most recent confirmed anchor."

Do not claim instant Bitcoin finality — it does not exist, and reviewers know it.

---

## Core data model

Every event becomes one immutable entry:

```
LedgerEntry
  seq            integer    monotonic, starts at 0 (genesis), no gaps
  timestamp      string     RFC3339 UTC, set by the RECORDER at append time
  source_id      string     identity of the emitting system/agent (attribution)
  payload        object     event content (JSON); store opaque if classified
  payload_hash   string     SHA-256 hex of the canonicalized payload
  prev_hash      string     entry_hash of entry (seq-1); genesis uses 64 zeros
  entry_hash     string     SHA-256 hex over the canonical record (the chain link)
  signature      string?    hex Ed25519 signature over source_id:canonical(payload)
  key_id         string?    fingerprint of the signing key (registry lookup)
```

Genesis entry: `seq=0`, `prev_hash = "0"*64`, `payload = {"type":"genesis"}`.

```
Anchor (one per stamp)
  head_seq       integer    seq of the entry whose hash was stamped
  head_hash      string     entry_hash at head_seq
  merkle_root    string     MMR root stamped to Bitcoin (enables O(log n) proofs)
  mmr_leaf_count integer    number of leaves at stamp time
  ots_proof      bytes      OpenTimestamps proof (.ots), upgraded over time
  created_at     string     RFC3339 UTC
  status         enum       pending | confirmed
  block_height   integer?   set once confirmed on Bitcoin
  block_time     string?    set once confirmed
```

---

## Hashing and canonicalization rules

These are the gotchas that silently break verification — specified once and
reused everywhere ([src/ledger.py](../src/ledger.py)):

- Hash function: **SHA-256**, lowercase hex.
- Canonicalization: serialize objects as **canonical JSON** — keys sorted, no
  insignificant whitespace, UTF-8 — before hashing.
- `payload_hash = sha256(canonical_json(payload))`
- `entry_hash   = sha256(canonical_json({seq, timestamp, source_id, payload_hash, prev_hash}))`
  — hash the structured object, never a naive string concatenation.

Change one byte anywhere in history and every subsequent hash breaks. Deleting an
entry leaves a sequence gap that `verify()` reports immediately.

---

## Cryptographic construction

### Hash chain

Each entry commits to the one before it (`prev_hash`), so the head hash is a
commitment to all of history. This is the real-time, no-network tamper-evidence.

### Merkle Mountain Range + selective disclosure

A Merkle Mountain Range ([src/mmr.py](../src/mmr.py)) is built incrementally over
all entry hashes — **O(log n) append and O(log n) inclusion proofs**, no
full-tree rebuild per anchor. The MMR root (not just the chain head) is what gets
stamped to Bitcoin.

This enables **selective disclosure**: you can prove a single AI decision is
authentic without revealing any other entries. Hand an investigator the entry, a
short proof path, and the anchored root; they verify it independently. Nothing
else needs to be declassified. (A legacy full-tree implementation lives in
[src/merkle.py](../src/merkle.py) as a reference.)

### Bitcoin anchor (OpenTimestamps)

The MMR root is submitted to OpenTimestamps ([src/anchor.py](../src/anchor.py)),
which aggregates thousands of hashes into a single Bitcoin transaction. Once
confirmed, the block header is an immutable timestamp that no one — including the
system operators — can rewrite. OpenTimestamps mainnet is public and free.

In local/demo mode (`MOCK_ANCHOR=true`) a mock confirmation simulates the Bitcoin
round-trip with no network, confirming after `MOCK_CONFIRM_DELAY` seconds.

### Per-agent signing & identity binding

Every agent has an Ed25519 keypair ([src/signing.py](../src/signing.py)). Events
are signed before submission; the recorder verifies the signature at ingest and
rejects anything with a mismatched attribution. The signed message binds the
`source_id` (`source_id : canonical_json(payload)`), and the key registry binds
each `key_id` to one `source_id` — so **a key enrolled to agent A cannot sign as
agent B**. `source_id` is cryptographically enforced, not just a string.

### DDIL resilience

Agents buffer events to a local SQLite queue when the recorder is unreachable
([src/adapters/client.py](../src/adapters/client.py)). When connectivity
returns, buffered events flush automatically *in order*. No events are lost during
denied/jammed/air-gapped outages. Agents can optionally heartbeat their buffer
depth so a dashboard shows DDIL state in real time.

### ROE event schema

Rules-of-Engagement decisions are structured
([src/roe_schema.py](../src/roe_schema.py)) with mandatory fields a JAG officer
or investigator can interpret without engineering support: what was decided and
why, whether a human authorized it (and who), the AI's confidence, the
information available at decision time, detection→authorization latency, and which
ROE rule applied.

---

## verify()

`verify()` ([src/verify.py](../src/verify.py)) answers two questions: is the
chain internally intact, and how far is it externally proven on Bitcoin? It
pinpoints the *first* broken entry.

**Complexity note:** for each anchor, `verify()` rebuilds an independent in-memory
MMR from the raw entry hashes to recompute the stored root — deliberately not
reusing the persisted `mmr_nodes` table, which is part of what's being verified.
This is O(n) per anchor, O(n×a) total. It is correct and appropriate for
on-demand audit runs; it is not designed for high-frequency polling on very large
ledgers.

```
function verify(ledger, anchors):
    # 1. Structural + chain integrity (real-time guarantee)
    expected_prev = "0"*64; last_seq = -1
    for entry in ledger ordered by seq ascending:
        if entry.seq != last_seq + 1:
            return BROKEN(at=entry.seq, reason="sequence gap or reorder — possible deletion")
        if sha256(canonical_json(entry.payload)) != entry.payload_hash:
            return BROKEN(at=entry.seq, reason="payload altered")
        recomputed = sha256(canonical_json({seq, timestamp, source_id, payload_hash, prev_hash}))
        if recomputed != entry.entry_hash:
            return BROKEN(at=entry.seq, reason="entry hash mismatch")
        if entry.prev_hash != expected_prev:
            return BROKEN(at=entry.seq, reason="chain link broken")
        expected_prev = entry.entry_hash; last_seq = entry.seq

    # 2. Signatures — reject forged attribution (a key cannot sign as another identity)
    # 3. External anchoring — recompute the MMR root and check it against each anchor;
    #    a confirmed OTS proof commits to everything at or below that head_seq.
    return OK(verified_entries, externally_anchored_through)
```

---

## API

| Method | Path | What it does |
|---|---|---|
| `POST` | `/events` | Append a signed event |
| `GET` | `/verify` | Full chain + signature + Merkle verification |
| `GET` | `/entries` | List all ledger entries |
| `GET` | `/entries/{seq}/proof` | MMR inclusion proof for one entry (O(log n)) |
| `GET` | `/anchors` | Anchor list with pending/confirmed status |
| `GET` | `/keys` | Registered public keys (metadata only) |
| `GET` | `/stream` | Live SSE feed (dashboard) |
| `POST` | `/agent/heartbeat` | Agent reports its DDIL buffer depth (telemetry) |
| `GET` | `/agent/status` | Latest connectivity/buffer state per agent |
| `POST` | `/anchor/now` | Stamp the head immediately |
| `POST` | `/anchor/upgrade` | Force a pending-anchor upgrade check |
| `POST` | `/events` | (signing) honors `STRICT_SIGNING` |
| `POST` | `/tamper` | **DEMO ONLY** — break the chain for the live demo |
| `POST` | `/seed` | **DEMO ONLY** — seed realistic signed events |
| `POST` | `/demo/impersonate` | **DEMO ONLY** — attempt forged attribution, show it rejected |

Mutating endpoints honor `API_TOKEN`.

---

## Integration — wiring into an existing system

Three patterns ([src/adapters/](../src/adapters/)) — pick the one that fits:

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

See [DEMO.md](DEMO.md) for runnable example apps built on these adapters.

---

## Configuration

| Env var | Default | Effect |
|---|---|---|
| `DEMO_MODE` | `false` | Enables `/tamper`, `/seed`, `/demo/impersonate` |
| `MOCK_ANCHOR` | `false` | Local mock Bitcoin confirmation (no network) |
| `MOCK_CONFIRM_DELAY` | `30` | Seconds until a mock anchor "confirms" |
| `STRICT_SIGNING` | `false` | **Reject any event without a valid, registered signature** |
| `API_TOKEN` | _(unset)_ | When set, mutating endpoints require `Authorization: Bearer <token>` or `X-API-Key` |
| `DB_PATH` | `ledger.db` | SQLite path |
| `STAMP_INTERVAL` | `30` | Seconds between anchor stamps |
| `UPGRADE_INTERVAL` | `30` | Seconds between pending-anchor upgrade checks (docker-compose demo uses `10`) |

---

## Production upgrade path

The cryptographic construction — hash chain, MMR, Bitcoin anchor — does not
change between demo and production. Only the key store and replication harden.

| This demo | Production |
|---|---|
| File-based Ed25519 keys | TPM / HSM / CAC-backed keys |
| Self-enrolled keys (TOFU) | Provisioning authority / enrollment CA |
| GPS time via system clock | GPS-disciplined clock (GPSD) |
| SQLite with WAL mode | Replicated append-only store (Litestream / Kafka) |
| Mock Bitcoin confirmation | Real OpenTimestamps mainnet (public, free) |
| Single recorder process | Raft-replicated recorder cluster |
| Shared-token API auth | mTLS / SPIFFE workload identity |

---

## File layout

```
src/
  ledger.py          hash chain, SQLite store, MMR persistence
  verify.py          verify() — chain + signatures + MMR + anchors
  anchor.py          OpenTimestamps stamping loop (+ mock mode)
  mmr.py             Merkle Mountain Range — O(log n) append + proofs
  merkle.py          legacy full-tree Merkle (reference implementation)
  signing.py         Ed25519 keypairs, sign, verify, identity binding
  roe_schema.py      ROE decision schema for JAG compliance
  api.py             HTTP endpoints (FastAPI) + STRICT_SIGNING + API_TOKEN
  adapters/
    client.py        DDIL-resilient signed HTTP client (+ heartbeat)
    logging_handler.py  drop-in Python logging integration
    audit_decorator.py  @audit_log function decorator
web/
  index.html         live dashboard
examples/
  demo_agent.py      multi-agent defense AI simulation (all adapters)
  file_agent.py      file-writing agent — watch actions get anchored
  llm_agent.py       AI chat assistant (real Claude or offline) hooked up
  ddil_demo.py       network-outage / buffer-and-recover demonstration
tests/               160+ tests across 8 files
k8s/                 Kubernetes manifests (Deployment, Service, PVC)
zarf.yaml            Zarf package definition (air-gap)
uds-bundle.yaml      UDS bundle definition
docs/                ARCHITECTURE.md · DEMO.md · DEPLOYMENT.md · PITCH.md
```
