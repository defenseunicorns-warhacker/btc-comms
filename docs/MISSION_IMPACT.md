# Mission Impact — Why an Immutable AI Accountability Layer Matters

## The problem, stated plainly

Autonomous and AI-enabled systems are entering the kill chain. The single
hardest barrier to fielding them is not capability — it is **accountability**.
If an AI agent can write, and *also* alter or delete, the record of what it
decided and why, then there is no defensible audit trail. No commander, JAG
officer, or oversight body can answer the question that always comes after an
engagement: *"What did the system know, what did it recommend, who authorized
it, and can you prove the record wasn't changed afterward?"*

Without a tamper-evident answer, lethal autonomy cannot be lawfully fielded at
scale. **STABLE makes that record immutable** — even against the AI that
created it.

## Direct mapping to DoD policy

### DoD Directive 3000.09 — *Autonomy in Weapon Systems*

DoDD 3000.09 (updated Jan 2023) requires that autonomous and semi-autonomous
weapon systems "allow commanders and operators to exercise **appropriate levels
of human judgment over the use of force**." It further requires rigorous V&V,
realistic testing, and traceability of system behavior.

| 3000.09 requirement | STABLE artifact |
|---|---|
| Appropriate human judgment over force | `human_authorized`, `operator_id` fields, recorded and signed at the decision gate |
| Traceability of engagement decisions | Hash-chained, Bitcoin-anchored ROE decision records |
| Time/latency of human authorization | `time_to_authorization_ms` — auditable detection→authorization latency |
| What the system "knew" | `information_state` — the sensor/intel snapshot the AI acted on |
| Which rule applied | `roe_reference` — the specific ROE invoked |
| Post-hoc integrity | `verify()` detects any later alteration; anchor proves existence-before-block |

### DoD Responsible AI (RAI) Principles

The DoD's five AI ethical principles include **Traceable** ("relevant
personnel possess an appropriate understanding of … the development processes
and operational methods … including transparent and auditable methodologies,
data sources, and design procedure and documentation") and **Governable**.

- **Traceable** → every AI decision is an append-only, independently verifiable
  record. Anyone with the entry, a short proof, and the anchored root can verify
  it — no access to the full system required.
- **Governable** → tamper-evidence is continuous and real-time; an operator can
  detect a misbehaving or compromised agent the moment it tries to rewrite
  history.

### CJCS Standing Rules of Engagement (SROE)

ROE decisions are structured (`roe_schema.py`) so a JAG officer or DCSA
investigator can interpret them **without engineering support** — what was
decided, by whom, under which rule, with what confidence, and what was actually
executed.

## The scenario that makes it concrete

See [THREAT_SCENARIO.md](THREAT_SCENARIO.md): an AI agent conducts an
engagement outside its authorization, then attempts to rewrite its own log to
hide it. STABLE detects the alteration and names the exact tampered record —
the accountability the mission requires.

## Why this is significant now

- Lethal autonomy is moving from policy debate to fielded capability.
- Coalition and congressional oversight demand auditable AI behavior.
- The same construction applies to non-lethal accountability: ISR tasking,
  EW, logistics, cyber — anywhere an AI's decisions must be defensible later.

STABLE is the missing accountability substrate that lets these systems be
fielded *responsibly* — tamper-evidence that holds even against the agents
being audited.
