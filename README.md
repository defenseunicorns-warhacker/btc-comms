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

# Local demo (mock Bitcoin confirmation, tamper endpoint enabled)
# Use `python3 -m uvicorn` so it works even when the uvicorn script isn't on PATH.
DEMO_MODE=true MOCK_ANCHOR=true python3 -m uvicorn src.api:app --reload

open http://localhost:8000
```

One command with Docker (`--build` ensures you don't run a stale cached image):

```bash
docker compose up --build
```

Run the simulated AI agent in a second terminal:

```bash
python3 examples/demo_agent.py
```

**Presenting?** See [DEMO.md](DEMO.md) for a rehearsed 3-minute runbook and
[PITCH.md](PITCH.md) for the judge-facing pitch mapped to the scoring criteria.

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
| `GET` | `/entries/{seq}/proof` | MMR inclusion proof for one entry (O(log n)) |
| `GET` | `/anchors` | Anchor list with pending/confirmed status |
| `GET` | `/keys` | Registered public keys (metadata only) |
| `GET` | `/stream` | Live SSE feed (dashboard) |
| `POST` | `/anchor/now` | Stamp immediately |
| `POST` | `/tamper` | **DEMO ONLY** — break the chain for the live demo |

Mutating endpoints honor `API_TOKEN`; `/events` honors `STRICT_SIGNING` (see Configuration).

---

## Configuration

| Env var | Default | Effect |
|---|---|---|
| `DEMO_MODE` | `false` | Enables `/tamper` and `/seed` for the live demo |
| `MOCK_ANCHOR` | `false` | Local mock Bitcoin confirmation (no network) |
| `STRICT_SIGNING` | `false` | **Reject any event without a valid, registered signature** |
| `API_TOKEN` | _(unset)_ | When set, mutating endpoints require `Authorization: Bearer <token>` or `X-API-Key` |
| `DB_PATH` | `ledger.db` | SQLite path |
| `STAMP_INTERVAL` | `30` | Seconds between anchor stamps |

Hardened deployment: `STRICT_SIGNING=true API_TOKEN=$(openssl rand -hex 32)`.

---

## Running tests

```bash
python3 -m pytest tests/ -v
```

160+ tests across 7 files:

- **Hash chain** — tamper detection at every entry, sequence gaps, broken links
- **MMR** — append, inclusion proofs for all sizes/positions, root recompute, tamper
- **Signing** — sign/verify roundtrip, payload tamper, unknown key, and **impersonation rejection** (a key enrolled to one identity cannot sign as another)
- **Ledger store** — genesis, chain links, MMR persistence across reopen, logarithmic node growth
- **API (end-to-end)** — seed→verify, tamper→verify-fails, MMR proof endpoint, strict-signing enforcement, token auth, impersonation rejection at ingest
- **DDIL** — local buffering during outage, ordered flush on reconnect, signatures survive buffering
- **ROE schema** — required-field validation, autonomous (`human_authorized=false`) records

---

## What this proves (and what it doesn't)

**Proves:** a record existed at time T and has not been altered since.

**Does not prove:** the record was true when written. The system is tamper-evident, not tamper-proof. Garbage in, garbage out — but the garbage is now permanently recorded.

**Trust model:** the recorder runs in a separate trust domain from the agents it audits. Agents have write-only access. No agent can modify or delete its own entries. With `STRICT_SIGNING=true`, every event must carry a signature from a key whose registered `source_id` matches the claimed sender — a key enrolled as agent A cannot sign as agent B.

**Residual trust assumption:** key *enrollment* is the trust anchor. In this demo keys self-enroll on first use (TOFU). In production, enrollment must be gated by a provisioning authority (CAC/PIV, an enrollment CA, or HSM attestation) so that an attacker cannot pre-register a victim's `source_id`. The signing/verification path is unchanged — only the key-issuance step hardens.

---

## Production upgrade path

| This demo | Production |
|---|---|
| File-based Ed25519 keys | TPM / HSM / CAC-backed keys |
| Self-enrolled keys (TOFU) | Provisioning authority / enrollment CA |
| GPS time via system clock | GPS-disciplined clock (GPSD) |
| SQLite with WAL mode | Replicated append-only store (Litestream / Kafka) |
| Mock Bitcoin confirmation | Real OpenTimestamps mainnet (public, free) |
| Single recorder process | Raft-replicated recorder cluster |
| Shared-token API auth | mTLS / SPIFFE workload identity |

The cryptographic construction — hash chain, MMR, Bitcoin anchor — does not change between demo and production.

---

## Air-gapped deployment (UDS / Zarf)

STABLE ships as a [UDS](https://github.com/defenseunicorns/uds-cli) bundle /
[Zarf](https://zarf.dev) package — the image and a software bill of materials
(SBOM) are bundled into a single tarball that deploys into a **fully
disconnected Kubernetes cluster** with no internet access.

```bash
# 1. Build the container image
docker build -t stable:latest .

# 2. Build the air-gap package (image + manifests + SBOM, one tarball)
uds zarf package create . --confirm
#   → zarf-package-stable-<arch>-0.1.0.tar.zst

# 3. On the air-gapped cluster: initialize Zarf, then deploy
uds zarf init --confirm
uds zarf package deploy zarf-package-stable-*.tar.zst --confirm
```

The deploy runs hardened by default (`STRICT_SIGNING=true`, a random
`API_TOKEN` Secret, non-root read-only container, health probes). Manifests live
in [k8s/](k8s/); package definitions are [zarf.yaml](zarf.yaml) and
[uds-bundle.yaml](uds-bundle.yaml).

---

## File layout

```
src/
  ledger.py          hash chain, SQLite store, MMR persistence
  verify.py          verify() — chain + signatures + MMR + anchors
  anchor.py          OpenTimestamps stamping loop
  mmr.py             Merkle Mountain Range — O(log n) append + proofs
  merkle.py          legacy full-tree Merkle (reference implementation)
  signing.py         Ed25519 keypairs, sign, verify, identity binding
  roe_schema.py      ROE decision schema for JAG compliance
  api.py             HTTP endpoints (FastAPI) + STRICT_SIGNING + API_TOKEN
  adapters/
    client.py        DDIL-resilient signed HTTP client
    logging_handler.py  drop-in Python logging integration
    audit_decorator.py  @audit_log function decorator
web/
  index.html         live dashboard
examples/
  demo_agent.py      simulated AI agent using all three adapters
tests/                163 tests — see "Running tests"
  test_verify.py  test_mmr.py  test_merkle.py  test_signing.py
  test_ledger_store.py  test_api.py  test_ddil.py  test_roe.py
k8s/                 Kubernetes manifests (Deployment, Service, PVC)
zarf.yaml            Zarf package definition (air-gap)
uds-bundle.yaml      UDS bundle definition
docs/
  MISSION_IMPACT.md  DoDD 3000.09 + Responsible AI mapping
  THREAT_SCENARIO.md "the AI that tried to cover its tracks"
DEMO.md              rehearsed 3-minute live-demo runbook
PITCH.md             judge-facing pitch mapped to scoring criteria
```
