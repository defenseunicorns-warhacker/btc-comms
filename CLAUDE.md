# STABLE — Project Guide for Claude

## What this project is

STABLE (Signed, Tamper-evident, Anchored Blockchain Ledger of Events) is a cryptographic accountability layer for autonomous AI systems in defense networks. It ensures AI agents cannot alter, delete, or deny the record of their own actions.

Every event is hash-chained to the previous entry, Ed25519-signed with a per-agent keypair, and anchored to Bitcoin via OpenTimestamps.

## Tech stack

- **Backend:** FastAPI + SQLite, Python 3.11+
- **Crypto:** Ed25519 signing (pycryptodomex), OpenTimestamps (Bitcoin anchoring)
- **Tree:** Merkle Mountain Range for O(log n) inclusion proofs
- **Streaming:** SSE (sse-starlette) for live dashboard
- **Deployment:** Docker, Kubernetes, Zarf/UDS (air-gap ready)

## Key source files

| File | Purpose |
|------|---------|
| `src/api.py` | FastAPI app — all REST endpoints |
| `src/ledger.py` | Append-only SQLite store with hash chain |
| `src/signing.py` | Per-agent Ed25519 key management |
| `src/anchor.py` | Background Bitcoin anchoring loop |
| `src/verify.py` | Full chain integrity verification |
| `src/mmr.py` | Merkle Mountain Range |
| `src/roe_schema.py` | Rules of Engagement payload validation |
| `src/adapters/` | LedgerClient, LedgerLogHandler, @audit_log decorator |
| `web/index.html` | Single-page live dashboard |

## Running the demo

Start the server in demo mode (no real Bitcoin, no network required):

```bash
DEMO_MODE=true MOCK_ANCHOR=true \
  MOCK_CONFIRM_DELAY=10 STAMP_INTERVAL=8 UPGRADE_INTERVAL=8 \
  uv run uvicorn src.api:app --port 8001 --reload
```

Open <http://localhost:8001>. You should see the dark dashboard with a green "CHAIN INTACT" banner.

**Or with Docker (one command):**
```bash
docker compose up
```

### Demo flow (3 minutes)

1. **Seed events** — click "Seed 10 demo events", watch the ledger populate live via SSE
2. **Verify** — click "Run verify()" → green "✓ All records authentic and unaltered"
3. **Tamper** — enter seq 7, click "Tamper entry" → banner flips RED instantly, shows exact broken record
4. **Impersonation** — click "Attempt impersonation" → rejected at ingest, key enrolled to one agent cannot sign as another
5. **Selective disclosure** — click any entry → proof modal shows single-entry authenticity without revealing others
6. **Bitcoin anchor** — point at the confirmed anchor; once a block confirms the record is irreversible

### Example agents (run in a second terminal alongside the dashboard)

```bash
# File-writing agent — create/edit/delete files, all recorded
python3 examples/file_agent.py

# Agent tries to cover its tracks — files deleted, ledger entries remain
python3 examples/file_agent.py --cover-tracks

# AI chat agent (offline by default, no API key needed)
python3 examples/llm_agent.py

# AI chat agent with real Claude responses
python3 examples/llm_agent.py --live --chat   # needs ANTHROPIC_API_KEY

# DDIL resilience demo — kill the recorder mid-run, watch buffer drain on restart
python3 examples/ddil_demo.py

# Multi-agent simulation (4 agents, ROE decisions, nav plans, threat classifications)
python3 examples/demo_agent.py
```

### CLI verification (no UI needed)

```bash
# Check chain integrity
curl -s localhost:8000/verify | jq .ok

# Tamper an entry then re-verify
curl -s -XPOST localhost:8000/tamper \
  -d '{"seq":7,"field":"payload","new_value":"X"}' \
  -H 'Content-Type: application/json'
curl -s localhost:8000/verify | jq '{ok, broken_at, reason}'

# Show impersonation rejection
curl -s -XPOST localhost:8000/demo/impersonate | jq '{rejected, reason}'
```

## Dependency management

Dependencies are managed with **uv** for reproducible developer builds.

### Developer workflow

```bash
# Install uv (once)
brew install uv   # macOS
# or: curl -LsSf https://astral.sh/uv/install.sh | sh

# Install all deps (uses uv.lock for exact pins)
uv sync

# Run tests
uv run pytest

# Run the app
DEMO_MODE=true MOCK_ANCHOR=true uv run uvicorn src.api:app --reload
```

### Updating dependencies

```bash
# After editing pyproject.toml, regenerate the lock file and frozen exports
uv lock
uv export --frozen --no-dev --no-emit-project -o requirements.txt
uv export --frozen --group dev --no-emit-project -o requirements-dev.txt
```

The frozen `requirements.txt` (with SHA-256 hashes) is what the Dockerfile uses — pip is kept there for accessibility. Do not edit `requirements.txt` by hand.

### Python version

Pinned to `3.11.15` via `.python-version`. uv respects this automatically.

## Running tests

```bash
uv run pytest          # all 187 tests
uv run pytest -q       # quiet output
uv run pytest tests/test_api.py   # single module
```

## Environment variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `DEMO_MODE` | `false` | Enables seed/tamper/impersonate endpoints |
| `MOCK_ANCHOR` | `false` | Local Bitcoin simulation (no network required) |
| `MOCK_CONFIRM_DELAY` | `60` | Seconds until mock anchor confirms |
| `DB_PATH` | `ledger.db` | SQLite file path |
| `STAMP_INTERVAL` | `30` | Seconds between Bitcoin anchor attempts |
| `UPGRADE_INTERVAL` | `30` | Seconds between confirmation checks |
| `STRICT_SIGNING` | `false` | Reject unsigned events |
| `REQUIRE_PROVISIONED_KEYS` | `false` | Only accept authority-issued keys |
| `API_TOKEN` | unset | Bearer/X-API-Key for mutating endpoints |
