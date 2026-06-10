# WarHacker Hackathon Problem 30
## Problem: Implement Real-Time Blockchain Anchoring for AI Agent Auditability, Ensure Immutable Accountability in Autonomous Defense Networks

### Tags

USN, Unicorn, High Priority, team: full, all-the-uds

### Description

Maintaining Accountability in AI-Enabled Defense Networks As AI agents are increasingly 
integrated into defense networks to automate decision-making, data processing, and 
operational workflows, the importance of accountability and auditability is rapidly 
escalating. Commanders and system owners must retain the ability to reconstruct events, 
verify actions, and attribute outcomes—especially as AI begins to operate with greater 
autonomy and speed. However, this requirement is colliding with a growing risk: the same 
AI agents that generate and interact with system records are also gaining the capability 
to access, modify, or delete those records, either unintentionally or through compromise. 
This creates a critical vulnerability. If AI systems can alter or erase the very logs and 
data used to audit their behavior, then trust in the system collapses. Traditional logging 
and database controls—no matter how well designed—remain fundamentally mutable, and 
therefore susceptible to tampering by sufficiently capable adversaries or misaligned AI 
agents. In effect, we risk deploying highly autonomous systems without a guaranteed way to 
prove what they actually did. To mitigate this, we must anchor critical records to immutable, 
externally verifiable infrastructure that AI agents cannot retroactively alter. While 
existing approaches—such as hashing files and anchoring those hashes to blockchains via 
timestamping—provide integrity for discrete data artifacts (e.g., PDFs, reports), they are 
insufficient for dynamic, continuously evolving systems. What is needed is a “rolling 
timestamp” capability: a mechanism that continuously commits system state, logs, or event 
streams to an immutable ledger in near real time, creating an auditable chain of evidence 
that cannot be modified after the fact. Accordingly, we are seeking ways to implement 
continuous or near-real-time data anchoring onto major proof-of-work blockchains, such as 
Bitcoin, to ensure data integrity, provenance, and non-repudiation at scale. The objective 
is to create a system where even the most advanced AI agents—regardless of capability—cannot 
erase or rewrite history, thereby preserving accountability and trust in AI-enabled defense 
operations.

### My Solution

A continuous, hash-chained ledger of system and AI-agent events whose head hash is periodically 
anchored to the Bitcoin blockchain via OpenTimestamps. Because each entry commits to the 
previous one and the chain head is committed to an external proof-of-work ledger, any attempt 
to alter, delete, or backdate a record is detectable locally in real time and externally 
provable up to the last confirmed anchor. Events enter through a pluggable adapter into 
a recorder that runs in a separate trust domain from the systems it audits, making the 
resulting audit trail tamper-evident, attributable, and non-repudiable.

## Plan: Immutable Accountability Layer for Autonomous Systems

A hackathon build spec for a "rolling timestamp" accountability layer: an append-only,
hash-chained event ledger whose head is continuously anchored to Bitcoin, so that no
system — including a compromised AI agent — can rewrite, delete, or backdate the history
of what it did. The guarantee is tamper-evident, attributable, and non-repudiable.

---

### How to use this file

This file is the prompt. Open the project in VSCode, point Claude at this file, and say
something like: "Read plan.md and build the spine described under 'Build sequence', one
phase at a time. Stop after each phase so I can run it."

Expectations for the agent:
- Build in the phase order below. Do not start a later phase until the earlier one runs.
- After each phase, give me a runnable command and a one-line "how to see it work".
- Write small, readable code with tests for the hashing and `verify()` logic specifically.
- Ask before adding heavy dependencies. Prefer the recommended stack unless I say otherwise.
- Keep everything container-friendly (a single `Dockerfile`) so it can later be packaged
  as a UDS/Zarf bundle. Do not build the bundle yet — that is a stretch goal.

---

### What we are building (the spine)

Three pieces, in dependency order:

1. An append-only, hash-chained event ledger. Each entry commits to the previous one, so
   the head hash is a commitment to all of history. This gives continuous, internal
   tamper-evidence with no blockchain involved.
2. A `verify()` routine that walks the chain and reports the exact point of any tampering.
3. An anchoring loop that periodically commits the current head hash to Bitcoin via
   OpenTimestamps, turning "internally detectable" into "externally provable".

The winning demo is: edit one byte of an old entry, run verify, and watch it fail — first
against the local chain, then against the confirmed Bitcoin proof.

---

### Real-time characteristics (read this before scoping)

This system is *near*-real-time, and it is important to describe it accurately. There are
two layered guarantees with different latencies:

- Tamper-evidence (local hash chain): effectively real-time. The moment an entry is
  appended, any later edit to a prior entry is detectable. Latency is the ingest path only.
- External immutability (Bitcoin anchor): near-real-time, bounded by two windows.
  - The anchoring interval (you control this — e.g. every 5–30 seconds the head is stamped).
  - Bitcoin confirmation latency (~10 minutes for the first block, ~1 hour for strong
    confirmation). Until a block confirms, recent entries are tamper-*evident* but not yet
    externally *proven*.

State the claim precisely: "Continuous tamper-evidence in real time; externally verifiable,
irreversible proof up to the most recent confirmed anchor." Do not claim instant Bitcoin
finality — it does not exist, and judges will know.

Operational consequence for the demo: stamp a record early (first hour) so a confirmed
proof exists by presentation time. See "Definition of done".

---

### Core data model — ledger entry schema

Every event becomes one immutable entry. Fields:

```
LedgerEntry
  seq            integer    monotonic, starts at 0 (genesis), no gaps
  timestamp      string     RFC3339 UTC, set by the RECORDER (not the source) at append time
  source_id      string     identity of the emitting system/agent (attribution)
  payload        object     the event content (JSON); store opaque if classified
  payload_hash   string     SHA-256 hex of the canonicalized payload
  prev_hash      string     entry_hash of entry (seq-1); genesis uses 64 zeros
  entry_hash     string     SHA-256 hex over the canonical record (the chain link)
```

Genesis entry: `seq=0`, `prev_hash = "0"*64`, `payload = {"type":"genesis"}`.

Anchor record (one per stamp):

```
Anchor
  head_seq       integer    seq of the entry whose hash was stamped
  head_hash      string     entry_hash at head_seq (what we committed)
  ots_proof      bytes      OpenTimestamps proof (.ots), upgraded over time
  created_at     string     RFC3339 UTC
  status         enum       pending | confirmed
  block_height   integer?   set once confirmed on Bitcoin
  block_time     string?    set once confirmed
```

---

### Hashing and canonicalization rules

These are the gotchas that silently break verification. Specify them once and reuse:

- Hash function: SHA-256, output as lowercase hex.
- Canonicalization: serialize objects as canonical JSON — keys sorted, no insignificant
  whitespace, UTF-8 — before hashing. Both `payload_hash` and `entry_hash` use this.
- `payload_hash = sha256(canonical_json(payload))`
- `entry_hash   = sha256(canonical_json({seq, timestamp, source_id, payload_hash, prev_hash}))`
  Hash the structured object, never a naive string concatenation (concatenation without
  length-prefixing or structure is ambiguous and attackable).
- The recorder, not the source, assigns `seq`, `timestamp`, `prev_hash`, and computes hashes.
  The source only supplies `payload` and `source_id`. This keeps the chain in a trust
  domain the source cannot manipulate.

---

### verify() — behavior and pseudocode

`verify()` answers two questions: is the chain internally intact, and how far is it
externally proven on Bitcoin? It must pinpoint the first broken entry.

```
function verify(ledger, anchors):
    # 1. Structural + chain integrity (real-time guarantee)
    expected_prev = "0"*64
    last_seq = -1
    for entry in ledger ordered by seq ascending:
        if entry.seq != last_seq + 1:
            return BROKEN(at=entry.seq, reason="sequence gap or reorder — possible deletion")
        if sha256(canonical_json(entry.payload)) != entry.payload_hash:
            return BROKEN(at=entry.seq, reason="payload altered")
        recomputed = sha256(canonical_json({
            seq: entry.seq, timestamp: entry.timestamp, source_id: entry.source_id,
            payload_hash: entry.payload_hash, prev_hash: entry.prev_hash }))
        if recomputed != entry.entry_hash:
            return BROKEN(at=entry.seq, reason="entry hash mismatch")
        if entry.prev_hash != expected_prev:
            return BROKEN(at=entry.seq, reason="chain link broken")
        expected_prev = entry.entry_hash
        last_seq = entry.seq

    # 2. External anchoring (immutability proven to an outside party)
    anchored_through = none
    for anchor in anchors ordered by head_seq ascending:
        if ledger[anchor.head_seq].entry_hash != anchor.head_hash:
            return BROKEN(at=anchor.head_seq, reason="anchored head does not match ledger")
        if ots_verify(anchor.ots_proof, anchor.head_hash) == valid:
            anchored_through = anchor.head_seq      # commits to everything <= this seq
        else if anchor.status == confirmed:
            return BROKEN(at=anchor.head_seq, reason="bitcoin proof invalid")
        # else: still pending confirmation — not an error

    return OK(verified_entries = last_seq + 1,
              externally_anchored_through = anchored_through)
```

Because each entry commits to the previous, anchoring a single head hash transitively
proves every entry at or below that seq. A full Merkle tree is a stretch goal, not needed
for the MVP.

---

### API surface

Keep it minimal. HTTP/JSON is fine.

```
POST /events           append an event   body: {source_id, payload}   -> {seq, entry_hash}
GET  /verify           run full verification                          -> verify() result
GET  /entries          list entries (for the dashboard)               -> [LedgerEntry...]
GET  /anchors          list anchors with status                       -> [Anchor...]
POST /tamper           DEMO ONLY: mutate one entry in place           -> {ok}
```

`/tamper` must be gated behind an explicit `--demo` flag or env var and clearly labeled
in code as a deliberate integrity-breaking endpoint for the live demonstration only.

---

### Architecture / components

- Ingest handler: validates input, lets the recorder assign seq/timestamp/hashes, appends.
- Store: append-only. SQLite or a JSONL file for the MVP. The process holds append rights;
  conceptually the source has write-only access and no modify/delete path.
- Anchoring loop: background task; every N seconds takes the current head and stamps it via
  OpenTimestamps; persists the proof; periodically upgrades pending proofs to confirmed.
- Verifier: the `verify()` routine above, exposed via API and a CLI command.
- Dashboard: live event stream, per-anchor status (pending/confirmed), a prominent tamper
  button, and a verification panel that flips green→red and names the broken seq.

---

### Recommended stack

Fast path: Python 3.11+, FastAPI, SQLite (stdlib `sqlite3`), the `opentimestamps-client`
library, a single-file static dashboard (plain HTML/JS or a small React page). One
`Dockerfile`. This is the quickest to a working demo and has a clean OTS client.

Alternative: Go, if the team is strong there and wants closer alignment with the UDS
ecosystem. Same architecture; shell out to the `ots` CLI for stamping.

Language is a speed decision, not an architecture decision — the deployable artifact is a
container either way.

---

### Suggested project structure

```
.
├── plan.md
├── Dockerfile
├── README.md
├── src/
│   ├── ledger.py        # entry schema, hashing, append, store
│   ├── verify.py        # verify() — keep pure and unit-tested
│   ├── anchor.py        # OpenTimestamps stamping + upgrade loop
│   ├── api.py           # HTTP endpoints
│   └── demo.py          # /tamper and seed data, demo-flag gated
├── web/
│   └── index.html       # dashboard
└── tests/
    └── test_verify.py   # tamper cases MUST be covered
```

---

### Build sequence (do in this order)

Phase 1 — Ledger + verify (the spine, no blockchain yet)
- [ ] Implement the entry schema, canonical hashing, genesis, and append.
- [ ] Implement `verify()` with the exact broken-entry reasons above.
- [ ] Unit tests: clean chain passes; altered payload, altered hash, broken link, and
      a deleted entry (sequence gap) each fail at the right seq.
- [ ] Manual check: append a few events, tamper one, see verify pinpoint it.

Phase 2 — Anchoring (external proof)
- [ ] Stamp the current head via OpenTimestamps every N seconds; persist the proof.
- [ ] Extend `verify()` to check anchored heads and report `externally_anchored_through`.
- [ ] Add proof "upgrade" so pending anchors become confirmed once Bitcoin mines them.

Phase 3 — Dashboard + tamper button (the demo surface)
- [ ] Live entry stream and anchor status (pending/confirmed).
- [ ] Tamper button (demo-gated) and a verification panel that flips green→red and names
      the broken seq and the mismatch against the anchored record.

---

### Definition of done (the demo)

The MVP is complete when, on stage:
1. Events are streaming into the ledger and the dashboard shows them live.
2. At least one anchor shows "confirmed" against Bitcoin (stamp it in hour one so it has
   time to confirm — this is the single biggest scheduling risk).
3. Pressing tamper on an old entry flips verification to red and points at the exact entry.
4. Verification fails not just locally but against the confirmed Bitcoin proof.

Cache anything verification needs locally (e.g. the relevant Bitcoin block header) so the
climactic check does not depend on venue wifi.

---

### Stretch goals (only after Definition of done)

- Minimal UDS/Zarf bundle manifest packaging the container (highest-leverage credibility
  item for a DoD audience; demonstrates "deploys to air-gap").
- OpenTelemetry (OTLP) ingest path to back the "universal adapter, any system" story.
- Air-gap simulation: cut the network, show local tamper-evidence still works, reconnect
  and watch buffered anchors flush to Bitcoin.
- Per-entry signing with a key (note TPM/enclave as the production upgrade) for attribution.
- Merkle inclusion proofs for selective disclosure (prove one event without revealing its
  neighbors) — relevant for classified contexts.

---

### Threat model guardrails (keep the build honest)

- The system proves a record existed at time T and has not changed since. It does not prove
  the record was true when written. Frame it as tamper-evident, attributable, and
  non-repudiable — never tamper-proof.
- The recorder must live in a different trust domain than the source it audits. The source
  gets append/write only; no modify or delete path.
- Capture as close to the source as possible to shrink the window before an event is hashed.
- Monotonic seq numbers make deletion detectable (a gap is evidence). Keep them strict.
