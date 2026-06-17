# Work Statement Conformance

How STABLE answers the AI-accountability work statement — requirement by
requirement, each mapped to the mechanism that satisfies it and the code that
implements it. For the engineering reference see
[ARCHITECTURE.md](ARCHITECTURE.md); for the mission framing see
[PITCH.md](PITCH.md).

---

## The problem, in the work statement's own terms

> As AI agents are integrated into defense networks, commanders and system
> owners must retain the ability to **reconstruct events, verify actions, and
> attribute outcomes**. But the same agents that generate records are gaining the
> ability to **access, modify, or delete** them — unintentionally or through
> compromise. Traditional logging and database controls remain **fundamentally
> mutable**. Hashing discrete files and timestamping them to a blockchain works
> for static artifacts (PDFs, reports) but is **insufficient for dynamic,
> continuously evolving systems**. What is needed is a **"rolling timestamp"** —
> continuous, near-real-time anchoring of logs and event streams onto a major
> proof-of-work blockchain (Bitcoin) for **integrity, provenance, and
> non-repudiation at scale** — so that **even the most advanced AI agents cannot
> erase or rewrite history.**

## The answer, in one paragraph

STABLE is that rolling-timestamp system. Every event an agent emits is appended
to a hash-chained, append-only ledger in a **trust domain the agent cannot
write to except by appending** — the agent has no modify or delete path. Each
entry is **Ed25519-signed** by the agent (provenance, non-repudiation), **chained**
to its predecessor (any retroactive edit is detectable instantly, offline), and
**continuously anchored to Bitcoin** via OpenTimestamps on a rolling interval
(externally verifiable, irreversible). A **Merkle Mountain Range** makes append
and proof both `O(log n)`, so this holds at the scale of millions of events. The
result is exactly the work statement's bar: an auditable chain of evidence that
cannot be modified after the fact.

---

## Requirement-by-requirement mapping

| # | Work-statement requirement | STABLE mechanism | Evidence |
|---|---|---|---|
| 1 | **Reconstruct events / attribute outcomes** | Append-only ledger; every event is one immutable entry carrying `source_id`, recorder-assigned `seq` + `timestamp`, and the full payload. ROE schema makes engagement decisions JAG-interpretable. | [ledger.py:116](../src/ledger.py#L116) · [roe_schema.py](../src/roe_schema.py) |
| 2 | **Agents must not be able to modify or delete their own records** | Agents have a **write-only (append-only) interface**: the only entry-facing endpoint is `POST /events`. There is no `PUT`/`PATCH`/`DELETE` on entries, and the `append()` code path issues only `INSERT`. | [api.py:205](../src/api.py#L205) · [ledger.py:116-146](../src/ledger.py#L116-L146) |
| 3 | **Records live in a trust domain the agent doesn't control** | The recorder — not the caller — assigns `seq`, `timestamp`, `prev_hash` and computes every hash. The source supplies only `source_id` + `payload`. | [ledger.py:127-143](../src/ledger.py#L127-L143) |
| 4 | **Traditional logs are "fundamentally mutable" → make alteration detectable** | Hash chain: each entry's hash commits to the previous entry's hash. Change one byte and every later hash breaks; delete an entry and a `seq` gap appears. `verify()` pinpoints the *first* broken entry and why. | [ledger.py:34-42](../src/ledger.py#L34-L42) · [verify.py:76-124](../src/verify.py#L76-L124) |
| 5 | **Anchor to immutable, externally verifiable infrastructure agents can't alter** | The chain/MMR head is stamped to the **Bitcoin** blockchain via OpenTimestamps. Once a block confirms, the proof is verifiable by anyone and rewritable by no one — including the operators. | [anchor.py](../src/anchor.py) |
| 6 | **Discrete-artifact timestamping is insufficient for evolving systems** | STABLE does not timestamp one file. It maintains a continuously-growing **Merkle Mountain Range** over the entire event stream and stamps its evolving root — the data structure *is* the stream. | [mmr.py](../src/mmr.py) · [ledger.py:142](../src/ledger.py#L142) |
| 7 | **"Rolling timestamp" — continuous, near-real-time anchoring** | A background `AnchorLoop` stamps the current head every `STAMP_INTERVAL` seconds and runs a separate loop that upgrades pending proofs to confirmed as Bitcoin mines them. | [anchor.py:189-205](../src/anchor.py#L189-L205) |
| 8 | **Provenance & non-repudiation** | Per-agent Ed25519 signatures. The signed message binds `source_id`, and the key registry binds each `key_id` to exactly one `source_id` — so a key enrolled to agent A **cannot** sign as agent B. `verify()` re-checks every signature. | [signing.py:104-144](../src/signing.py#L104-L144) · [verify.py:132-147](../src/verify.py#L132-L147) |
| 9 | **At scale** | MMR: `O(log n)` append and `O(log n)` inclusion proofs — no full-tree rebuild per anchor. Enables **selective disclosure** (prove one entry without revealing the rest). | [mmr.py](../src/mmr.py) · [api.py:270](../src/api.py#L270) |
| 10 | **Even advanced agents cannot erase or rewrite history** | The combination: write-only separation (can't delete) + hash chain (can't edit undetectably, offline, in real time) + Bitcoin anchor (can't rewrite the past at all) + signing (can't forge attribution). | all of the above |

---

## The two points the work statement leans on hardest

### "Rolling timestamp," not discrete-artifact timestamping

The work statement explicitly calls out that hashing a PDF and timestamping it
is **insufficient for dynamic systems**. STABLE's design is the direct answer:

- The unit of anchoring is not a file — it is the **root of a Merkle Mountain
  Range built incrementally over the live event stream**
  ([ledger.py:142](../src/ledger.py#L142)).
- That root is re-stamped on a rolling cadence by a background loop
  ([anchor.py:189-205](../src/anchor.py#L189-L205)), so the "timestamp" tracks the
  system as it evolves rather than freezing one artifact.
- Each stamp commits to **everything at or below that head** — one Bitcoin
  anchor covers the entire history up to that moment, not a single document.

This is the "continuously commits system state, logs, or event streams to an
immutable ledger in near real time" capability, verbatim.

### "At scale" is an engineering claim, and it's load-bearing

Anchoring a growing stream naively means rebuilding a Merkle tree on every
stamp — `O(n)` per anchor, `O(n²)` over the run. STABLE uses a Merkle Mountain
Range instead: append is `O(log n)` and inclusion proofs are `O(log n)`
([mmr.py](../src/mmr.py)). That is what lets it hold at "millions of events"
without the anchor cadence degrading. Selective disclosure falls out of the same
structure: an investigator can verify one AI decision against the Bitcoin-anchored
root without being handed any other (possibly classified) entry
([api.py:270](../src/api.py#L270)).

---

## Stated honestly: what "cannot rewrite history" does and doesn't mean

The work statement sets the bar at "even the most advanced AI agents — regardless
of capability." STABLE meets that bar **for the agent being audited**, and it is
precise about the boundary rather than overclaiming:

- **It is tamper-*evident*, attributable, and non-repudiable — not
  tamper-*proof*.** It proves a record *existed at time T and has not changed
  since*; it does **not** prove the record was *true* when written. "Garbage in"
  becomes *permanently recorded* garbage — which is exactly what an investigation
  needs ([ARCHITECTURE.md](ARCHITECTURE.md#trust-model-read-this-first)).
- **Two latencies, both stated plainly.** Local hash-chain tamper-evidence is
  **real-time and needs no network**. External Bitcoin proof is **near-real-time**
  — irreversible only up to the most recently *confirmed* anchor (~10 min for a
  first block). The README and ARCHITECTURE deliberately avoid claiming instant
  Bitcoin finality.
- **Key *enrollment* is the trust anchor — and the recorder now enforces it.** A
  signature only proves "the key registered to this `source_id` signed this," so
  enrollment must be controlled. By default the demo lets keys self-enroll (TOFU)
  so it runs in one command. Set **`REQUIRE_PROVISIONED_KEYS=true`** and the
  recorder honors *only* keys issued by the provisioning authority — a self-enrolled
  key is rejected at ingest even if its signature is mathematically valid. Set
  **`ALLOW_AUTO_ENROLL=false`** and new identities cannot self-enroll at all; keys
  are issued out-of-band via `provision_keypair()` / `register_public_key()` (the
  CAC/PIV / HSM path — the private key can stay in the token). The
  signing/verification math is unchanged; only key issuance hardens
  ([signing.py](../src/signing.py) · [api.py:70](../src/api.py#L70), enforced at
  [api.py:209-226](../src/api.py#L209-L226), tested in
  [test_signing.py](../tests/test_signing.py) and
  [test_api_features.py](../tests/test_api_features.py)).
- **The model assumes the recorder is a separate trust domain from the agent.**
  "The agent can't rewrite history" holds because the agent cannot reach the
  recorder's process, its database, or its keys — only the append API. Co-locating
  the recorder inside the agent's own trust boundary would void the guarantee;
  this is a deployment requirement, not a cryptographic weakness. The production
  path replaces the single SQLite process with a replicated/clustered recorder and
  swaps file keys for TPM/HSM/CAC ([ARCHITECTURE.md](ARCHITECTURE.md#production-upgrade-path)).
- **The `/tamper`, `/seed`, and `/demo/impersonate` endpoints are demo-only** and
  gated behind `DEMO_MODE`; they must be off in production. They exist to *show*
  the tamper-evidence working, not as a real mutation path
  ([api.py:448](../src/api.py#L448)).

This honesty is the point. The work statement's real requirement is a record an
agent cannot **erase or rewrite undetectably** — and that is precisely what
STABLE delivers and proves.

---

## Conformance summary

| Work-statement objective | Status | Where |
|---|---|---|
| Reconstruct / verify / attribute agent actions | ✅ Met | append-only signed ledger + `verify()` |
| Agents cannot modify or delete their records | ✅ Met | write-only API, recorder-controlled trust domain |
| Immutable, externally verifiable anchor (Bitcoin PoW) | ✅ Met | OpenTimestamps rolling anchor |
| Rolling / continuous near-real-time anchoring | ✅ Met | `AnchorLoop` stamp + upgrade loops |
| Integrity, provenance, non-repudiation | ✅ Met | hash chain + Ed25519 identity binding |
| At scale (millions of events) | ✅ Met | Merkle Mountain Range, `O(log n)` |
| Cannot erase or rewrite history undetectably | ✅ Met | chain (real-time) + Bitcoin (irreversible past) |
| Reject self-enrolled (TOFU) keys, honor only authority-issued ones | ✅ Met when configured | `REQUIRE_PROVISIONED_KEYS=true` (+ optional `ALLOW_AUTO_ENROLL=false`) — enforced at ingest, tested |
| Recorder must not share a trust domain with the audited agent | ⚠️ Deployment requirement | run the recorder as a separate process/host with a write-protected registry (production path documented) |
