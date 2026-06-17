# STABLE — interactive demo

An interactive, two-role demo of STABLE for a technical audience that doesn't
know blockchain. It drives the **real** recorder — nothing is faked; `verify()`,
the proofs, and the Bitcoin anchor all run against the live cryptographic engine.

The app is built around two real-world roles, switchable from the top bar:

### ● Live Monitoring (the SOC operator)
The autonomous system is running. Every agent decision streams into an
append-only, hash-chained, **signed** ledger. One big readout shows **INTEGRITY
VERIFIED**. The moment any record is altered, it flips to **BREACH DETECTED**, an
alarm drops in, and the chain visibly shatters from the altered record down —
because tampering can never be silent: changing one record breaks every hash
after it.

The breach then shows a **recovery runbook** that maps 1:1 to `verify()`'s
output — and reflects how STABLE actually recovers (it's tamper-*evident*, it
does not heal itself):

1. **What broke** — `verify()` halts at `broken_at` and names the attack class
   (`payload altered`, `chain link broken`, `bitcoin proof invalid`, …).
2. **What still holds** — records up to the last clean **Bitcoin checkpoint** are
   external ground truth the attacker can't rewrite; post-break records that are
   still validly **signed** stay individually attributable (you lose ordering
   proof, not authenticity proof).
3. **Recover forward** — you don't fix the chain in place. **Re-baseline**: seal
   the compromised chain as forensic evidence and start a fresh chain whose
   genesis embeds the last clean checkpoint. New activity chains and anchors
   forward from a state that was proven before the tamper.

### ⚖ Investigation (the JAG legal officer)
A shoot-down is under review. The investigator filters the operational log to
find the disputed record (#7 — an autonomous engagement with **no human in the
loop**), runs **Verify full chain integrity** to confirm nothing was altered, and
generates a **court-admissible selective-disclosure proof** for that single
record — without declassifying any of the surrounding operational history.

The alarm's **Investigate →** button hands off directly from the SOC view to the
investigation, pre-focused on the broken record.

## The simulation console

The dashed panel in the bottom-right is the **only** thing that injects activity
into the recorder — it's fenced off so the audience never mistakes it for the
real product. From it you stage:

- **Run counter-UAS engagement** — posts the 9-event scenario (each signed and chained)
- **Rewrite record #7** — the adversary's tamper; fires the live breach detection
- **Forge an agent signature** — rejected at ingest (attribution is cryptographic)
- **Reset ledger** — wipe back to genesis to re-run

## Run it

**1. Start the recorder** (from the repo root) in demo mode with a clean DB and
short anchor intervals so it confirms on stage:

```bash
rm -f demo.db demo.db-wal demo.db-shm
DEMO_MODE=true MOCK_ANCHOR=true \
  MOCK_CONFIRM_DELAY=4 STAMP_INTERVAL=30 UPGRADE_INTERVAL=6 \
  DB_PATH=demo.db python3 -m uvicorn src.api:app --port 8001
```

`STAMP_INTERVAL=30` keeps the background stamper out of the way — the demo takes
an **explicit Bitcoin checkpoint after record #6** (mid-engagement), so records
#7–9 stay deliberately un-anchored. That makes the recovery story honest: #0–6
are externally proven, #7 onward is the in-question zone.

**2. Start the demo** (from `demo/`):

```bash
npm install        # first time only
npm run dev        # opens http://localhost:5173
```

The Vite dev server proxies all `/events`, `/stream`, `/verify`, … calls to the
recorder on `:8001` (override with `STABLE_URL`).

## Suggested demo flow

1. **Monitoring** — *"Run counter-UAS engagement"*. Agents fire and the ledger
   fills, all green: INTEGRITY VERIFIED. Mid-way it locks a Bitcoin checkpoint at
   record #6.
2. *"Rewrite record #7"*. The alarm fires instantly, the chain shatters, and the
   **recovery runbook** appears. Tampering is impossible to hide.
3. Click **Investigate →**. You're now the JAG officer: filter to record #7,
   **Verify full chain integrity** (`verify()` names #7), then **Generate
   court-admissible proof** — prove the record against its Bitcoin block without
   revealing any other record.
4. Back in **Monitoring**, **Re-baseline from checkpoint #6**. The compromised
   chain is sealed as evidence; a fresh, trusted chain starts from the last clean
   checkpoint. The operator can run a new engagement on it immediately.
5. **Reset ledger** to run the whole thing again.

## Build for air-gapped serving

```bash
npm run build      # → demo/dist (plain static assets)
```

The `dist/` bundle can be served by any static host or wired into the recorder
itself — no Node runtime required at the edge.

## Structure

```
src/
  scenario.js      the 9-event counter-UAS scenario + incident framing
  useStable.js     SSE subscription → live ledger / anchor / verify state
  api.js           thin client over the recorder
  humanize.js      raw payloads → plain-English log lines
  App.jsx          shell: role tabs, alarm, simulation console, shared state
  components/
    MonitoringView.jsx    SOC dashboard — integrity readout + live chain
    InvestigationView.jsx JAG forensic audit — filter, inspect, prove
    AlarmBanner.jsx       breach alert with hand-off to Investigation
    DemoControls.jsx      the fenced-off simulation console
    Chain.jsx             the vertical hash chain; GSAP shatter on tamper
    AgentPanel.jsx        the four AI agents
    AnchorBar.jsx         the Bitcoin anchor (pulses to "irreversible")
    ProofModal.jsx        selective-disclosure proof for one record
    VerifyBanner.jsx      (legacy) green/red chain status
```
