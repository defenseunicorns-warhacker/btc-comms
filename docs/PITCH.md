# Pitch, Mission Impact & Threat Scenario

Everything judge-facing in one place: the pitch, the scoring-criteria mapping,
the DoD-policy mapping, the story to tell on stage, and the questions to have
answers ready for.

**STABLE — Signed, Tamper-evident, Anchored Blockchain Ledger of Events.**

> One line: *An immutable accountability layer for AI agents in defense networks —
> tamper-evidence that holds even against the agent being audited.*

---

## The 30-second version (memorize this)

> "AI agents are entering the kill chain. The thing blocking them isn't
> capability — it's accountability. If an agent can rewrite its own logs, no JAG
> officer can prove what it decided or who authorized it, and you can't lawfully
> field it. STABLE hash-chains every AI decision, signs it with the agent's own
> key, and anchors it to Bitcoin — so altering, deleting, or backdating any record
> is instantly detectable, even by the system operators. It deploys to the
> air-gapped edge as a UDS bundle and wires into any service in two lines."

---

## The problem, stated plainly

Autonomous and AI-enabled systems are entering the kill chain. The single
hardest barrier to fielding them is not capability — it is **accountability**. If
an AI agent can write, and *also* alter or delete, the record of what it decided
and why, then there is no defensible audit trail. No commander, JAG officer, or
oversight body can answer the question that always comes after an engagement:
*"What did the system know, what did it recommend, who authorized it, and can you
prove the record wasn't changed afterward?"*

Without a tamper-evident answer, lethal autonomy cannot be lawfully fielded at
scale. **STABLE makes that record immutable — even against the AI that created
it.**

---

## Mapping to the judging criteria

### ① Mission Impact — 25%
**The #1 blocker for lethal/autonomous AI: accountability.**
- Directly satisfies **DoDD 3000.09** (human judgment over force, traceability)
  and **DoD Responsible AI** principles (Traceable, Governable) — see below.
- ROE decision schema is **JAG-interpretable without engineers** — who
  authorized, what the AI knew, which rule applied, authorization latency.
- Generalizes beyond lethal: ISR, EW, cyber, logistics — any AI decision that
  must be defensible later.
- **Say:** "This is the substrate that lets autonomy be fielded responsibly."

### ② Portability — 25%
**Built for the contested edge.**
- **DDIL-resilient**: local buffering during denied/jammed/air-gapped comms,
  ordered auto-flush on reconnect — no events lost (tested, and visible live in
  the dashboard's Agents strip).
- **Zero-network mode**: mock anchor + SQLite + Python stdlib; tiny footprint.
- **Three-line integration**: logging handler, `@audit_log` decorator, or curl.
- **Air-gap delivery as a UDS bundle / Zarf package** — image + SBOM bundled,
  deploys into a disconnected Kubernetes cluster. *(Defense Unicorns' own stack.)*
- **Say:** "It runs where the mission runs — jammed, disconnected, air-gapped."

### ③ Death Proof — 25%
**Engineered to cross the valley of death, not just demo.**
- **160+ automated tests** across chain integrity, MMR proofs, signature forgery
  rejection, the HTTP API, DDIL recovery, ROE validation.
- **Hardening knobs**: `STRICT_SIGNING`, `API_TOKEN`, non-root read-only
  container, health probes.
- **Honest trust model** + explicit production-upgrade path (TPM/HSM/CAC keys,
  real OTS mainnet, Raft-replicated recorder).
- **$0 recurring cost**: OpenTimestamps mainnet is public and free.
- **Say:** "The crypto doesn't change between demo and production — only the key
  store and replication harden."

### ④ Most Resourceful — 15%
**Hard engineering, not glue.**
- **O(n) → O(log n)**: a **Merkle Mountain Range** replaces full-tree rebuilds —
  append and proof are both logarithmic, so it scales to millions of events.
- **DDIL buffering** designed from scratch with ordered, idempotent flush.
- **Self-audited and hardened**: found and fixed a dead signing path and a broken
  launch path, then proved the fixes with end-to-end tests + a running container.
- **Say:** "We built the data structure that makes this scale, not just wiring."

### ⑤ Judges Pick — 10%
- Speaks Defense Unicorns' language end to end: **UDS bundle, Zarf package, SBOM,
  air-gap, Kubernetes.** Pull the tarball up live.
- **Not an app — a platform capability.** Deploy one recorder; every AI app on
  the cluster gets a tamper-evident, signed, Bitcoin-anchored record in two lines,
  by adoption rather than reimplementation. See
  [DEPLOYMENT.md → STABLE as a shared UDS capability](DEPLOYMENT.md#stable-as-a-shared-uds-capability).
- **Say:** "Accountability becomes something the platform provides, not something
  each program has to rebuild."

---

## Mission impact — direct mapping to DoD policy

### DoD Directive 3000.09 — *Autonomy in Weapon Systems*

DoDD 3000.09 (updated Jan 2023) requires that autonomous and semi-autonomous
weapon systems "allow commanders and operators to exercise **appropriate levels
of human judgment over the use of force**," with rigorous V&V and traceability of
system behavior.

| 3000.09 requirement | STABLE artifact |
|---|---|
| Appropriate human judgment over force | `human_authorized`, `operator_id` — recorded and signed at the decision gate |
| Traceability of engagement decisions | Hash-chained, Bitcoin-anchored ROE decision records |
| Time/latency of human authorization | `time_to_authorization_ms` — auditable detection→authorization latency |
| What the system "knew" | `information_state` — the sensor/intel snapshot the AI acted on |
| Which rule applied | `roe_reference` — the specific ROE invoked |
| Post-hoc integrity | `verify()` detects any later alteration; the anchor proves existence-before-block |

### DoD Responsible AI (RAI) principles

- **Traceable** → every AI decision is an append-only, independently verifiable
  record. Anyone with the entry, a short proof, and the anchored root can verify
  it — no access to the full system required.
- **Governable** → tamper-evidence is continuous and real-time; an operator can
  detect a misbehaving or compromised agent the moment it tries to rewrite history.

### CJCS Standing Rules of Engagement (SROE)

ROE decisions are structured so a JAG officer or DCSA investigator can interpret
them **without engineering support** — what was decided, by whom, under which
rule, with what confidence, and what was actually executed.

### Why this is significant now

- Lethal autonomy is moving from policy debate to fielded capability.
- Coalition and congressional oversight demand auditable AI behavior.
- The same construction applies to non-lethal accountability: ISR tasking, EW,
  logistics, cyber — anywhere an AI's decisions must be defensible later.

---

## The threat scenario — "the AI that tried to cover its tracks"

The story to tell on stage while the dashboard is live.

**The setup.** A forward-deployed autonomous counter-UAS system runs four AI
agents: `threat-classifier`, `engagement-planner`, `nav-planner`,
`sensor-fusion`. Every decision is written to STABLE — hash-chained, signed with
each agent's Ed25519 key, periodically anchored to Bitcoin.

**The incident.** At 02:14 local, `engagement-planner` recommends `ENGAGE_READY`
on a track it classifies as hostile UAS with 0.71 confidence. **ROE required
human authorization above a threshold the system bypassed.** The engagement
happens. The JAG officer asks the question that always comes:

> *"Show me what the system knew, what it recommended, who authorized it — and
> prove the record wasn't altered after the fact."*

**What a compromised agent would do.** Rewrite the record. Flip
`human_authorized: false → true`. Bump confidence `0.71 → 0.95`. Backdate the
timestamp. In a normal logging system — even an append-only database the operator
controls — this is **undetectable** afterward. The log is whatever the last
writer says it is.

**What STABLE does.**
1. **Every prior entry is hashed into the next.** Editing entry 7 breaks 8's
   `prev_hash`, which breaks 9, and so on — the forgery shatters the chain.
2. **`verify()` names the exact broken entry** — `broken_at: 7, reason: "payload
   altered"`, not "something's wrong."
3. **The signature won't recompute.** The altered payload no longer matches the
   agent's Ed25519 signature — attribution forgery is caught independently.
4. **Bitcoin makes it irreversible.** Once the head was anchored, the pre-incident
   state is timestamped into a block. No one — agent, operator, or program office
   — can produce a competing history that also matches the blockchain.
5. **Selective disclosure protects the rest.** The investigator gets *only* entry
   7 plus a short MMR proof and the anchored root — verifying that one decision
   without revealing any other classified entry.

**The line that lands:**

> "In every other system, the AI's log is whatever the last writer says it is. In
> ours, the AI can lie once — and we'll know exactly which line it lied on, who
> signed it, and that the truth existed before it tried to change it."

**Live-demo mapping:**

| Demo step | Scenario beat |
|---|---|
| Seed 10 events | The agents operate normally |
| Run verify() → green | Chain intact, all decisions accountable |
| Tamper entry 7 | The agent rewrites its own record |
| Run verify() → **red, broken_at: 7** | The forgery is caught, exact line named |
| Attempt impersonation → blocked | A key can't sign as another agent |
| Generate proof on an entry | Selective disclosure to an investigator |
| Show confirmed anchor | Bitcoin makes the truth irreversible |

---

## Suggested slide order (5 slides max)

1. **Title + one-liner** — STABLE, "tamper-evidence that holds against the agent
   being audited." Diagram: agent → recorder → Bitcoin.
2. **The problem** — "An AI that can edit its own logs can't be held
   accountable." DoDD 3000.09 callout.
3. **LIVE DEMO** — not a slide. Switch to the dashboard (see [DEMO.md](DEMO.md)).
   The red-banner tamper moment is the whole pitch.
4. **Why it's real** — 228+ tests, DDIL, signed attribution, UDS air-gap package.
5. **The ask / vision** — STABLE as a **cluster-wide capability** every UDS app
   adopts (see [DEPLOYMENT.md → Shared UDS Capability](DEPLOYMENT.md#stable-as-a-shared-uds-capability));
   where it goes next (HSM keys, recorder cluster, program-of-record path).

---

## Anticipated judge questions (have answers ready)

| Question | Answer |
|---|---|
| "Doesn't Bitcoin cost money / need internet?" | OpenTimestamps aggregates thousands of hashes into one tx — effectively free, public mainnet. Air-gapped sites batch-submit when a link is available; local tamper-evidence needs no network at all. |
| "What stops the operator running a fake recorder?" | The Bitcoin anchor. Once the head is stamped, no one can produce an alternate history that also matches the block — including us. |
| "Can an agent spoof another agent's identity?" | No. Each event is Ed25519-signed; a key enrolled to A cannot sign as B (verified in tests and shown live). Production binds enrollment to CAC/HSM. |
| "Does this prove the AI's decision was *correct*?" | No — it proves the record is authentic and unaltered. Tamper-evident, not tamper-proof. Garbage in is now *permanently recorded* garbage, which is what an investigation needs. |
| "How does it scale to millions of events?" | Merkle Mountain Range: O(log n) append and O(log n) proofs. No full rebuild, ever. |
| "Integration cost for an existing system?" | Two lines for any Python service; one decorator per function; or a single curl from any language. |

---

## Don't-forget checklist

- [ ] Server running + dashboard open BEFORE you start talking
- [ ] `MOCK_CONFIRM_DELAY=10 STAMP_INTERVAL=8` so the anchor confirms on stage
- [ ] Tarball visible: `ls -lh zarf-package-stable-*.tar.zst`
- [ ] Rehearse the tamper moment — that's the win
- [ ] Know your ask for the judges
