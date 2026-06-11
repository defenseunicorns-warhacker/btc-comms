# Live Demo Runbook

A bulletproof, rehearsed demo plus the runnable example apps. Core runbook is
**~3 minutes**; the example apps are optional acts. Every step has a fallback so
nothing breaks on stage.

> Golden rule: **start the server before you start talking.** Have the dashboard
> open and seeded to a known-good state. Never type a long command live — use the
> buttons or the one-liners below.

---

## 0. Pre-flight (before you present)

```bash
# Clean slate. Short intervals so the Bitcoin anchor goes green on stage:
rm -f ledger.db ledger.db-wal ledger.db-shm
DEMO_MODE=true MOCK_ANCHOR=true \
  MOCK_CONFIRM_DELAY=10 STAMP_INTERVAL=8 UPGRADE_INTERVAL=8 \
  python3 -m uvicorn src.api:app --port 8001
```

> Use `python3 -m uvicorn` (not bare `uvicorn`) — the console script may not be
> on your PATH. Run from the repo root.

Open <http://localhost:8001>. You should see the dark dashboard with a green
"CHAIN INTACT" banner and a "LOCAL MOCK ANCHOR" tag.

**Fallback:** `docker compose up --build` does the same in one command.

---

## 1. The hook (15s)

> "Right now, an AI agent making decisions in a defense network can also delete
> or rewrite its own logs. If it can edit the record of what it did, there's no
> accountability — and you can't lawfully field it. We made tampering
> impossible. Even for us."

## 2. Normal operations (20s)

Click **Seed 10 demo events**. Watch the ledger populate live (SSE). Each row
shows a plain-English description and a green **✓ signed** badge.

> "These are AI agents operating — threat classification, engagement planning,
> navigation. Every decision is hash-chained to the one before it and signed with
> that agent's own key."

Click **Run verify()** → banner is **green**: *"✓ All 11 records are authentic
and unaltered."*

## 3. THE MONEY SHOT — tamper detection (30s)

In the tamper box, enter **seq 7** and click **Tamper entry**.

> "Now the AI tries to cover its tracks — it rewrites entry 7 to claim a human
> authorized an engagement that was actually autonomous."

The banner **flips RED instantly**: *"✗ Record #7 was altered — and we caught
exactly which one."*

> "Caught. Not 'something's wrong' — the *exact* record, by sequence number.
> Editing one entry breaks every hash after it. The forgery shatters the chain."

**This is the wow moment. Pause here. Let it land.**

### 3b. Bonus — you can't impersonate another agent either (15s)

Click **Attempt impersonation**. A red toast appears: *"✗ Impersonation blocked —
a key enrolled to 'nav-planner' cannot sign as 'threat-classifier'."*

> "And you can't frame another agent. A key enrolled to one agent physically
> cannot sign as another — the recorder rejects the forgery at ingest.
> Attribution is cryptographic, not a label you can type."

## 4. Selective disclosure (25s)

Reset (re-seed), then click any entry → the proof modal opens.

> "Here's the classified-environment problem solved: I can prove this single AI
> decision is authentic — hand an investigator a short proof — without revealing
> any other entry. Nothing else gets declassified."

The modal leads with **✓ AUTHENTIC** in plain English; the hash-tree math is
tucked behind "▸ Show the cryptographic proof" for anyone who wants it.

## 5. Bitcoin anchor — irreversibility (25s)

Point at the anchor that just went **confirmed**.

> "Every few seconds the chain head is stamped to Bitcoin via OpenTimestamps.
> Once a block confirms, that record is irreversible by anyone on earth —
> including the program office that runs this. That's what makes it *evidence*,
> not just a log."

## 6. Why it's real, not a demo (30s)

> "This isn't slideware:
> - **160+ automated tests** — chain integrity, cryptographic proofs, signature
>   forgery rejection, the API, network-outage recovery.
> - **DDIL-resilient** — agents buffer locally when jammed or air-gapped and
>   flush in order on reconnect. No events lost.
> - **Per-agent Ed25519 signatures** — a key enrolled as agent A cannot sign as
>   agent B.
> - And it ships as a **UDS bundle** — air-gapped Kubernetes delivery, the
>   Defense Unicorns way. Here's the package, image and SBOM included."

```bash
ls -lh zarf-package-stable-*.tar.zst
```

## 7. Close (15s)

> "STABLE is the accountability substrate that lets autonomous systems be fielded
> responsibly. Tamper-evidence that holds even against the agents being audited.
> Two lines to wire into any existing service. Ready for the edge today."

---

## Optional acts — watch real apps get anchored

The most intuitive part for a non-technical audience: a real app doing visible
work, every action landing in the ledger live. Run any of these in a second
terminal, split-screen with the dashboard.

### A — File-writing agent

```bash
python3 examples/file_agent.py                 # scripted: create, edit, delete
python3 examples/file_agent.py --cover-tracks  # agent wipes its own files
```

Rows appear as `📄 Created file …`, `✏️ Modified …`, `🗑️ Deleted …`, each signed.
In cover-tracks mode the agent wipes its entire workspace — but it has write-only
access and can't delete a single ledger record. The files are gone; the
accountability isn't.

### B — AI chat assistant (the most literal version)

```bash
python3 examples/llm_agent.py                 # offline (air-gapped) demo model
python3 examples/llm_agent.py --live --chat   # real Claude; you type the questions
python3 examples/llm_agent.py --cover-tracks  # the agent tries to unsay something
```

Each prompt→response turn appears as `🤖 AI turn …`, signed. In cover-tracks mode
the agent appends a retraction — and the original answer is *still* at its
sequence number: write-only access means it can't delete or edit what it said.

> Live mode needs `pip install anthropic` and `ANTHROPIC_API_KEY`. The default
> runs fully offline so the air-gapped demo never depends on a network.

### C — DDIL resilience: survive a network outage

The dashboard's **Agents** strip (top of the page) shows each connected agent and
its local buffer depth in real time.

```bash
python3 examples/ddil_demo.py
```

The strip shows `edge-sensor ✓ live`. Now **kill the recorder** (Ctrl-C) — the
agent's buffer count climbs every second; no events lost. **Restart it**, refresh
the dashboard: the strip shows `⚠ N buffered`, then drains to `✓ live` as the
buffered events flush *in order*. Run **verify()** → still green, no gap.

### D — Full multi-agent simulation

```bash
python3 examples/demo_agent.py
```

Four AI agents emitting signed ROE decisions, nav plans, and threat
classifications continuously — exercises every adapter and the ROE schema.

> All example agents heartbeat their buffer depth, so each appears in the Agents
> strip. Integration is two lines — see
> [ARCHITECTURE.md → Integration](ARCHITECTURE.md#integration--wiring-into-an-existing-system).

---

## Fallbacks / recovery

| If… | Do this |
|---|---|
| Dashboard won't load | `curl localhost:8000/verify` — the JSON tells the same story |
| Anchor hasn't confirmed | Click **Stamp head now**, then **Upgrade anchors** |
| You want to reset mid-demo | Stop server, `rm ledger.db*`, restart, re-seed |
| SSE feed stalls | Refresh the page — it re-snapshots on connect |

## CLI cheat-sheet (prove it from the terminal)

```bash
# Tamper detection, no UI
curl -s localhost:8000/verify | jq .ok                       # true
curl -s -XPOST localhost:8000/tamper -d '{"seq":7,"field":"payload","new_value":"X"}' -H 'Content-Type: application/json'
curl -s localhost:8000/verify | jq '{ok, broken_at, reason}' # ok:false, broken_at:7

# Impersonation rejected at ingest
curl -s -XPOST localhost:8000/demo/impersonate | jq '{rejected, reason}'
```
