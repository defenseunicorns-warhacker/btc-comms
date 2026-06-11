# STABLE — Judge-Facing Pitch

**STABLE — Signed Tamper-evident Anchored Blockchain Ledger of Events**

> One line: *An immutable accountability layer for AI agents in defense networks —
> tamper-evidence that holds even against the agent being audited.*

---

## The 30-second version (memorize this)

"AI agents are entering the kill chain. The thing blocking them isn't
capability — it's accountability. If an agent can rewrite its own logs, no JAG
officer can prove what it decided or who authorized it, and you can't lawfully
field it. STABLE hash-chains every AI decision, signs it with the agent's own
key, and anchors it to Bitcoin — so altering, deleting, or backdating any record
is instantly detectable, even by the system operators. It deploys to the
air-gapped edge as a UDS bundle and wires into any service in two lines."

---

## Mapping to the judging criteria

### ① Mission Impact — 25%
**The problem is the #1 blocker for lethal/autonomous AI: accountability.**
- Directly satisfies **DoDD 3000.09** (human judgment over force, traceability)
  and **DoD Responsible AI** principles (Traceable, Governable). See
  [docs/MISSION_IMPACT.md](docs/MISSION_IMPACT.md).
- ROE decision schema is **JAG-interpretable without engineers** — who
  authorized, what the AI knew, which rule applied, authorization latency.
- Generalizes beyond lethal: ISR, EW, cyber, logistics — any AI decision that
  must be defensible later.
- **Say:** "This is the substrate that lets autonomy be fielded responsibly."

### ② Portability — 25%
**Built for the contested edge.**
- **DDIL-resilient**: local buffering during denied/jammed/air-gapped comms,
  ordered auto-flush on reconnect — no events lost (tested).
- **Zero-network mode**: mock anchor + SQLite + Python stdlib; tiny footprint
  (64Mi request).
- **Three-line integration**: logging handler, `@audit_log` decorator, or curl —
  language-agnostic.
- **Air-gap delivery as a UDS bundle / Zarf package** — image + SBOM bundled,
  deploys into a disconnected Kubernetes cluster. *(Defense Unicorns' own stack.)*
- **Say:** "It runs where the mission runs — jammed, disconnected, air-gapped."

### ③ Death Proof — 25%
**Engineered to cross the valley of death, not just demo.**
- **163 automated tests** across chain integrity, MMR proofs, signature forgery
  rejection, the HTTP API, DDIL recovery, ROE validation.
- **Hardening knobs**: `STRICT_SIGNING` (reject unsigned), `API_TOKEN` (auth on
  mutating endpoints), non-root read-only container, health probes.
- **Honest trust model** + explicit production-upgrade path (TPM/HSM/CAC keys,
  real OTS mainnet, Raft-replicated recorder).
- **$0 recurring cost**: OpenTimestamps mainnet is public and free.
- **Say:** "The crypto construction doesn't change between demo and production —
  only the key store and the replication hardens."

### ④ Most Resourceful — 15%
**Hard engineering, not glue.**
- **O(n) → O(log n)**: replaced full-tree-rebuild-per-anchor with a **Merkle
  Mountain Range** — append and proof are both logarithmic, so it scales to
  millions of events.
- **DDIL buffering** designed from scratch with ordered, idempotent flush.
- **Self-audited and hardened**: found and fixed a dead signing path and a
  broken launch path, then proved the fixes with end-to-end tests + a running
  container.
- **Say:** "We didn't just wire libraries together — we built the data structure
  that makes this scale."

### ⑤ Judges Pick — 10%
- Speaks Defense Unicorns' language end to end: **UDS bundle, Zarf package,
  SBOM, air-gap, Kubernetes.** Pull the tarball up live.

---

## Suggested slide order (5 slides max)

1. **Title + one-liner** — STABLE, "tamper-evidence that holds against the agent
   being audited." Logo/diagram of agent → recorder → Bitcoin.
2. **The problem** — "An AI that can edit its own logs can't be held
   accountable." DoDD 3000.09 callout.
3. **LIVE DEMO** — not a slide. Switch to the dashboard. (See [DEMO.md](DEMO.md).)
   The red-banner tamper moment is the whole pitch.
4. **Why it's real** — 163 tests, DDIL, signed attribution, UDS air-gap package.
5. **The ask / vision** — where this goes next (HSM keys, recorder cluster,
   program-of-record path). What you want from the judges.

---

## Anticipated judge questions (have answers ready)

| Question | Answer |
|---|---|
| "Doesn't Bitcoin cost money / need internet?" | OpenTimestamps aggregates thousands of hashes into one tx — effectively free, and it's public mainnet. Air-gapped sites batch-submit when a link is available; local tamper-evidence needs no network at all. |
| "What stops the operator from just running a fake recorder?" | The Bitcoin anchor. Once the head is stamped, no one can produce an alternate history that also matches the block — including us. |
| "Can an agent spoof another agent's identity?" | No. Each event is Ed25519-signed; a key enrolled to agent A cannot sign as B (verified in tests). Production binds enrollment to CAC/HSM. |
| "Does this prove the AI's decision was *correct*?" | No — it proves the record is authentic and unaltered. Tamper-evident, not tamper-proof. Garbage in is now *permanently recorded* garbage, which is exactly what an investigation needs. |
| "How does it scale to millions of events?" | Merkle Mountain Range: O(log n) append and O(log n) proofs. No full rebuild, ever. |
| "Integration cost for an existing system?" | Two lines for any Python service; one decorator per function; or a single curl from any language. |

---

## Don't-forget checklist

- [ ] Server running + dashboard open BEFORE you start talking
- [ ] `MOCK_CONFIRM_DELAY=15` so the anchor confirms on stage
- [ ] Tarball visible: `ls -lh zarf-package-stable-*.tar.zst`
- [ ] Rehearse the tamper moment — that's the win
- [ ] Know your ask for the judges
