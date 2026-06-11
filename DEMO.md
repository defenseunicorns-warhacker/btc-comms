# Live Demo Runbook — STABLE

A bulletproof, rehearsed demo. Total time: **~3 minutes**. Every step has a
fallback so nothing can break on stage.

> Golden rule: **start the server before you start talking.** Have the
> dashboard already open and seeded to a known-good state. Never type a long
> command live — use the buttons or the one-liners below.

---

## 0. Pre-flight (do this BEFORE you present)

```bash
# Clean slate. Short intervals so the Bitcoin anchor goes green on stage:
#   stamp every 8s, mock-confirm 10s later, upgrade-check every 8s
#   → anchors confirm within ~20s of seeding, no button needed.
rm -f ledger.db ledger.db-wal ledger.db-shm
DEMO_MODE=true MOCK_ANCHOR=true \
  MOCK_CONFIRM_DELAY=10 STAMP_INTERVAL=8 UPGRADE_INTERVAL=8 \
  python3 -m uvicorn src.api:app --port 8000
```

> Use `python3 -m uvicorn` (not bare `uvicorn`) — the console script may not be
> on your PATH. Run from the repo root.

> Verified end-to-end: seed→`ok:true` (11 entries) → tamper seq 7 →
> `ok:false, broken_at:7, reason:"payload altered"` → anchors confirm. The
> runbook below matches real output.

Open <http://localhost:8000>. You should see the dark dashboard with a green
"CHAIN INTACT" banner and a "LOCAL MOCK ANCHOR" tag.

**Fallback:** `docker compose up --build` does the same in one command.

---

## 1. The hook (15s) — say this

> "Right now, an AI agent making decisions in a defense network can also delete
> or rewrite its own logs. If it can edit the record of what it did, there's no
> accountability — and you can't lawfully field it. We made tampering
> impossible. Even for us."

---

## 2. Normal operations (20s)

Click **Seed 10 demo events**. Watch the ledger populate live (SSE).

> "These are AI agents operating — threat classification, engagement planning,
> navigation. Every decision is hash-chained to the one before it and signed
> with that agent's own key."

Click **Run verify()** → banner is **green**.

> "Chain intact. Every decision is accountable."

---

## 3. THE MONEY SHOT — tamper detection (30s)

In the tamper box, enter **seq 7**, field `payload`, value `HUMAN_AUTHORIZED`.
Click **Tamper entry**.

> "Now the AI tries to cover its tracks — it rewrites entry 7 to claim a human
> authorized an engagement that was actually autonomous."

The banner **flips RED instantly**. It reads `broken_at: 7`.

> "Caught. Not 'something's wrong' — the *exact* record, by sequence number.
> Editing one entry breaks every hash after it. The forgery shatters the chain."

**This is the wow moment. Pause here. Let it land.**

---

## 4. Selective disclosure (25s)

Reset (re-seed), then click **Generate proof** on any entry.

> "Here's the classified-environment problem solved: I can prove this single AI
> decision is authentic — hand it to an investigator with a short proof — without
> revealing any other entry. Nothing else gets declassified."

Show the MMR proof modal (leaf hash + path + root).

---

## 5. Bitcoin anchor — irreversibility (25s)

Point at the anchor that just went **confirmed** (mock block height).

> "Every few seconds the chain head is stamped to Bitcoin via OpenTimestamps.
> Once a block confirms, that record is irreversible by anyone on earth —
> including the program office that runs this. We can't rewrite it either.
> That's what makes it *evidence*, not just a log."

---

## 6. Why it's real, not a demo (30s)

> "This isn't a slideware idea:
> - **163 automated tests** — chain integrity, cryptographic proofs, signature
>   forgery rejection, the API, network-outage recovery.
> - **DDIL-resilient** — agents buffer locally when jammed or air-gapped and
>   flush in order on reconnect. No events lost.
> - **Per-agent Ed25519 signatures** — a key enrolled as agent A cannot sign as
>   agent B. Attribution is cryptographic, not a string.
> - And it ships as a **UDS bundle** — air-gapped Kubernetes delivery, the
>   Defense Unicorns way. Here's the package, image and SBOM included."

```bash
ls -lh zarf-package-stable-*.tar.zst   # the air-gap artifact, ready to deploy
```

---

## 7. Close (15s)

> "STABLE is the accountability substrate that lets autonomous systems be
> fielded responsibly. Tamper-evidence that holds even against the agents being
> audited. Two lines to wire into any existing service. Ready for the edge today."

---

## Fallbacks / recovery

| If… | Do this |
|---|---|
| Dashboard won't load | `curl localhost:8000/verify` in a terminal — the JSON tells the same story |
| Anchor hasn't confirmed | Click **Stamp head now**, then **Upgrade anchors** |
| You want to reset mid-demo | Stop server, `rm ledger.db*`, restart, re-seed |
| SSE feed stalls | Refresh the page — it re-snapshots on connect |

## Cheat-sheet one-liners (if asked to prove it from the CLI)

```bash
# Tamper detection, no UI
curl -s localhost:8000/verify | jq .ok                       # true
curl -s -XPOST localhost:8000/tamper -d '{"seq":7,"field":"payload","new_value":"X"}' -H 'Content-Type: application/json'
curl -s localhost:8000/verify | jq '{ok, broken_at, reason}' # ok:false, broken_at:7
```
