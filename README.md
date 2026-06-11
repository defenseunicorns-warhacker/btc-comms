# STABLE — An Immutable Accountability Layer for AI

**CODENAME: STABLE** — *Signed, Tamper-evident, Anchored Blockchain Ledger of Events.*

> An accountability layer for AI agents in defense networks — tamper-evidence
> that holds **even against the agent being audited**.

---

## The problem

AI agents are starting to make autonomous decisions in defense networks. The
hardest barrier to fielding them isn't capability — it's **accountability**.

The same agents that generate the records are also gaining the ability to
**modify or delete** those records. If an AI can rewrite the log of what it did,
then after an engagement no commander, JAG officer, or oversight body can answer
the question that always comes:

> *"What did the system know, what did it recommend, who authorized it — and can
> you prove the record wasn't changed afterward?"*

Traditional logs and databases are fundamentally mutable. Deploy autonomy on top
of them and you have no guaranteed way to prove what the system actually did.

## What STABLE does

STABLE makes the record **impossible to alter undetectably — even by the AI that
created it, even by the people who run the system.**

Every event an agent emits is:

- **Chained** to the one before it, so changing any past record breaks
  everything after it,
- **Signed** with that agent's own key, so no one can forge who did what, and
- **Anchored to the Bitcoin blockchain**, so the record's existence is locked
  into infrastructure no one can rewrite.

Altering, deleting, or backdating any record is **immediately detectable** — and,
once anchored, **provably impossible to deny**.

## The guarantee, stated honestly

- **Local tamper-evidence is real-time.** The instant an entry is recorded, any
  later edit to any prior entry is detectable. No network needed.
- **External proof is near-real-time.** Every few seconds the record's
  fingerprint is stamped to Bitcoin; once a block confirms (~10 min), that proof
  is verifiable and irreversible by anyone on earth.

> "Continuous tamper-evidence in real time. Externally verifiable, irreversible
> proof up to the most recent confirmed anchor."

It is tamper-**evident**, attributable, and non-repudiable — not tamper-*proof*.
It proves a record existed and hasn't changed; it does not claim the record was
*true* when written. That honesty is the point: garbage in is now *permanently
recorded* garbage, which is exactly what an investigation needs.

---

## See it work in 60 seconds

```bash
pip install -r requirements.txt

# Local demo — mock Bitcoin confirmation, no network required.
DEMO_MODE=true MOCK_ANCHOR=true python3 -m uvicorn src.api:app

open http://localhost:8000
```

On the dashboard:

1. Click **Seed 10 demo events** — realistic AI-agent decisions fill the ledger,
   each in plain English with a green **✓ signed** badge.
2. Click **Run verify()** — the banner goes green: *all records authentic and
   unaltered.*
3. Type a number and click **Tamper entry** — the banner flips **red instantly**
   and names the exact record that was altered. *That's the whole idea.*
4. Click any entry to prove it's authentic — without revealing any other record.

No Bitcoin or cryptography knowledge required to see it working. To watch a real
app get anchored live, run an example agent in a second terminal:

```bash
python3 examples/file_agent.py    # a file-writing agent; or llm_agent.py / ddil_demo.py
```

---

## Documentation

| Doc | What's in it |
|---|---|
| [docs/PITCH.md](docs/PITCH.md) | The pitch, scoring-criteria mapping, **mission impact** (DoDD 3000.09 / Responsible AI), and the "AI that tried to cover its tracks" scenario |
| [docs/DEMO.md](docs/DEMO.md) | The rehearsed live-demo runbook + the runnable example apps |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | How it works — data model, hash chain, Merkle Mountain Range, Bitcoin anchor, signing, DDIL, the API, configuration, trust model |
| [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) | Run locally / Docker / air-gapped Kubernetes (UDS / Zarf), tests, hardening |
| [docs/UDS_CAPABILITY.md](docs/UDS_CAPABILITY.md) | STABLE as a **shared cluster capability** any UDS app opts into — deploy one recorder, every AI app gets a tamper-evident record in two lines |

---

## Why it matters

This is the missing accountability substrate that lets autonomous systems be
fielded *responsibly*. It maps directly to **DoD Directive 3000.09** (appropriate
human judgment over force, traceability) and the **DoD Responsible AI**
principles (Traceable, Governable) — and it ships to the air-gapped edge as a
**UDS bundle**, the Defense Unicorns way. The full mission case is in
[docs/PITCH.md](docs/PITCH.md).

Wires into any service in two lines; runs jammed, disconnected, or air-gapped;
costs nothing recurring (OpenTimestamps mainnet is public and free).
