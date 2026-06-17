# How It Works, in Plain English

No cryptography background needed. This is a guided tour of the **whole system** —
every moving part — using everyday analogies. If you only want the three things
people get stuck on first (fingerprints, leaves, and what lands on Bitcoin), read
Parts 1, 2, and 4. For the engineer's version, see [ARCHITECTURE.md](ARCHITECTURE.md).

**What this system is, in one sentence:** a way to record what AI agents do so that
**nobody — not even the AI that wrote the record, not even the people who run the
system — can secretly change or erase it afterward.**

---

### Contents

- **Part 1 — The building block:** [fingerprints](#part-1--the-building-block)
- **Part 2 — Locking the records together:** [leaves, the chain, the tree](#part-2--locking-the-records-together)
- **Part 3 — Who did it:** [signatures, keys, the write-only vault](#part-3--who-did-it-identity--trust)
- **Part 4 — The outside witness:** [stamping & Bitcoin](#part-4--the-outside-witness-bitcoin)
- **Part 5 — Using and trusting it:** [verifying, selective disclosure, scale](#part-5--using-and-trusting-it)
- **Part 6 — Built for the field:** [network outages, legal records, integration, air-gap](#part-6--built-for-the-field)
- **Part 7 — The big picture:** [end-to-end journey, the payoff, honest limits](#part-7--the-big-picture)
- **Part 8 — Reference:** [recap & glossary](#part-8--quick-reference)

---

# Part 1 — The building block

## The one idea everything rests on: a fingerprint

A **hash** is a digital fingerprint of some data.

- Feed in *anything* — a sentence, a file, an AI decision — and you get back a short
  string of letters and numbers.
- The **same input always gives the same fingerprint.**
- Change the input by even **one character**, and the fingerprint comes out
  **completely different.**
- You **cannot work backwards** from the fingerprint to the original data.

That's it. When we say "hash," picture a tamper-evident fingerprint. If two
fingerprints match, the data is identical. If they don't, *something changed.*

> **Why it matters:** if we write down an AI decision's fingerprint today, anyone can
> re-fingerprint that decision tomorrow and instantly see whether a single character
> was altered.

> **Quick myth-buster:** the real logs are **not** stored as hashes, and hashes can
> never be "un-hashed." The actual record is kept in full, in plain readable form,
> with its fingerprint stored *next to it* as a seal. The fingerprint is for
> *checking* the record, not for *storing* it.

---

# Part 2 — Locking the records together

## Each event becomes a "leaf"

Every time an AI agent does something (classifies a threat, plans a route, authorizes
an action), the system records that event and takes its fingerprint. That single
event-fingerprint is called a **leaf node** — or just a **leaf.** "Leaf" is simply
the word for the fingerprints at the very bottom, one per event.

```
   ev1        ev2        ev3        ev4       ← the actual AI events
    │          │          │          │
   f1         f2         f3         f4        ← each event's fingerprint = a "leaf"
```

Now the records get locked together **two different ways at once.** They sound
similar but do different jobs, so it's worth seeing both.

## Lock #1 — The chain (puts the events in unbreakable order)

Picture a stack of numbered pages, where **each page is sealed with a copy of the
previous page's fingerprint.** Page 7 literally contains page 6's fingerprint; page 8
contains page 7's; and so on.

```
  entry 5 ──▶ entry 6 ──▶ entry 7 ──▶ entry 8
            each arrow = "this entry carries the
            fingerprint of the one before it"
```

This does two things:

- **Editing a past entry breaks the chain.** Change entry 7 and its fingerprint
  changes — but entry 8 still carries the *old* fingerprint of 7. The mismatch is
  obvious, and every entry after it breaks too. One quiet edit shatters the whole
  tail of the chain.
- **Deleting an entry leaves a hole.** Entries are numbered in order with no gaps
  (the very first one, number 0, is called the **genesis** entry — the cornerstone).
  Remove entry 7 and the numbering jumps 6 → 8. A gap is evidence.

The best part: **this protection needs no internet.** The instant an entry is added,
any later tampering with the past is detectable right there on the device. (Bitcoin,
in Part 4, adds a second layer on top.)

## Lock #2 — The tree and its single "root"

Now imagine a **tournament bracket.** Pair up the leaves and take a fingerprint *of
each pair.* Then pair up *those* and fingerprint again. Keep going until everything
funnels up to **one fingerprint at the very top.**

```
              ROOT          ← one fingerprint that stands for ALL events
             /    \
        H(f1,f2)  H(f3,f4)  ← fingerprints of pairs
          /  \      /  \
        f1   f2   f3   f4    ← the leaves (one per event)
```

That top fingerprint is the **root.** It's a single fingerprint that represents
**every event underneath it.** Change any event at the bottom and its leaf changes,
which changes the root. So instead of protecting thousands of events individually, we
only have to protect **one number: the root.** (That one number is what we'll hand to
Bitcoin in Part 4.)

The tree also gives us a superpower we'll use later: you can prove *one* event belongs
in the record by revealing just that event and the short trail of fingerprints up its
branch — **without showing any of the other events.** (More in Part 5.)

> **Chain vs. tree, in a line:** the **chain** keeps events in tamper-proof *order* and
> works offline; the **tree** squeezes everything into *one fingerprint* that's cheap to
> witness on Bitcoin and lets you prove single events. You get both at once.

*(The real system uses an efficient version of the tree called a "Merkle Mountain
Range" so it can keep adding events without rebuilding the whole bracket each time. The
idea is identical — events at the bottom, one root at the top.)*

---

# Part 3 — Who did it (identity & trust)

A record of *what happened* isn't enough; you need *who did it,* provably. Three pieces
handle this.

## Signatures — every event is signed by the agent that created it

Each AI agent gets its own **signing key** — think of it as a unique pen that only that
agent has, plus a matching "checker" everyone else can use to recognize its
handwriting. (The technology is called Ed25519; the pen analogy is all you need.)

When an agent emits an event, it **signs** it. The signature is tied to *both* the
agent's identity *and* the exact content of the event. So:

- If anyone changes the event afterward, the signature no longer fits — forgery caught.
- The signature proves *which agent* produced it. This is called **attribution.**

**You can't sign as someone else.** Each pen is registered to one identity. If
"agent A" tries to sign a record as "agent B," the registry says *"that pen belongs to
A, not B"* and rejects it. Identity isn't just a label you type — it's cryptographically
enforced.

## Where the pens come from — enrollment

Issuing and registering a pen is called **enrollment**, and it's the one spot where
trust ultimately rests. There are two modes:

- **Demo mode (easy):** the first time an agent shows up, it grabs a pen and writes its
  own name in the registry ("trust on first use"). Frictionless for demos — but it means
  anyone could invent a brand-new identity.
- **Hardened mode (production):** pens are issued only by an **official desk** — a
  military CAC/PIV card, an enrollment authority, or a hardware security module (HSM)
  where the secret half of the pen **never leaves the device.** The recorder then
  **honors only pens issued by that desk** and rejects any self-made ones, even if the
  signature itself is mathematically valid.

You flip between them with settings (`REQUIRE_PROVISIONED_KEYS`, `ALLOW_AUTO_ENROLL`),
and the demo stays one-command by default. This is deliberately the *only* knob that
changes between demo and production — the rest of the math is identical.

## The write-only vault — agents can add, but never edit or erase

Here's the structural piece that makes the whole thing work: **the recorder is a
separate vault that the agents don't control.**

Picture a one-way mail slot into a locked vault. Agents can **drop new records in.**
They have **no way to reach back in** to change or delete anything already inside —
there is simply no "edit" or "delete" door exposed to them. And the **vault clerk (the
recorder), not the agent,** stamps each record with its order number and the time. The
agent only supplies *who it is* and *what happened.*

This is why an agent — even a compromised or misbehaving one — can't quietly rewrite its
own history: **it was never given the ability to reach the past at all.** It can only
ever append.

---

# Part 4 — The outside witness (Bitcoin)

## "Stamping" — getting the root witnessed by something nobody controls

We now have one fingerprint (the root) that stands for everything, locked in order and
signed. But a fingerprint we keep on *our own* computer isn't proof to an outsider — we
could claim anything about when it was made.

We need an **independent, trusted witness** to say: *"I saw this exact fingerprint at
this point in time, and it can never be backdated."* Handing the root to that witness is
called **stamping** (or *anchoring*).

The witness is the **Bitcoin blockchain** — the hardest-to-rewrite record humanity has
built. Rewriting Bitcoin's history would cost billions and is, for practical purposes,
impossible. Tie our fingerprint into Bitcoin, and our record's *existence at that time*
becomes just as impossible to fake. (Bitcoin is "proof-of-work," which just means it
takes enormous real-world energy to extend or change — that cost is the security.)

## The part everyone asks about: the *stamp* vs. the *hash*, and what actually lands on Bitcoin

**We do NOT put the AI's data on Bitcoin. We don't even put our root fingerprint on
Bitcoin directly.** Three separate things:

| Thing | What it is | Where it lives |
|---|---|---|
| **The data** | The actual AI events | Stays on *your* system. Never leaves. (Great for classified info.) |
| **The hash (root)** | The one fingerprint standing for all your events | Computed on your system; it's the thing you want to prove |
| **The stamp** | A small *receipt* proving your root existed before a Bitcoin block | Saved next to your records (a little `.ots` file) |

So how does the root tie to Bitcoin without being written there directly? Through a free
public service called **OpenTimestamps**, which works like a **post office that
postmarks a huge sack of mail at once:**

1. Thousands of people (including us) hand OpenTimestamps their root fingerprints in the
   same short window.
2. It **braids all of them into one combined fingerprint** (another tree, exactly like
   Part 2).
3. **Only that one combined fingerprint goes into one Bitcoin transaction** — about once
   every block (~10 minutes). One transaction covers thousands of submitters. That's why
   it's effectively free and scales.

```
  your root ───┐
  someone else ├──►  OpenTimestamps braids them all  ──►  ONE fingerprint
  thousands more┘     into a single combined fingerprint      │
                                                              ▼
                                              written into ONE Bitcoin block
                                                     (~every 10 minutes)
```

And **the stamp** (that `.ots` receipt) is the **set of directions tracing your root up
through the braid to the exact fingerprint that landed in Bitcoin.** It's not your data;
it's not even your root by itself; it's the *proof of the connection.*

> **In one sentence:** the **hash (root)** is the fingerprint of your records; the
> **stamp** is the receipt proving that fingerprint was folded into a specific Bitcoin
> block — so what reaches Bitcoin is a *combined* fingerprint your root provably feeds
> into, never your actual data.

## "Pending," then "confirmed"

Right after stamping, Bitcoin hasn't mined the block yet, so the receipt is **pending** —
"submitted, waiting." About 10 minutes later, once a block is mined, the receipt is
automatically **upgraded to confirmed** — now it points at a real, permanent block. The
system does this waiting and upgrading in the background.

*(In the local demo we simulate this round-trip so it works with no internet — a fake
"block" confirms after a few seconds. The real version uses the actual public Bitcoin
network, which is free to stamp to.)*

---

# Part 5 — Using and trusting it

## Checking everything — what "verify" does

**Verifying** is the auditor's walkthrough. With one command the system:

1. **Re-fingerprints every record** and checks it matches the stored fingerprint.
2. **Walks the chain** to confirm each entry correctly points to the one before it, with
   no missing numbers.
3. **Checks every signature** — right agent, unaltered content, properly enrolled pen.
4. **Checks the Bitcoin receipts** — how far back the record is witnessed by confirmed
   blocks.

If everything's intact, you get a green "all authentic." If anything is off, it doesn't
just say "something's wrong" — it **names the exact entry and the reason**, e.g.
*"broken at entry 7 — payload altered."* That precision is the point: you learn exactly
which record was touched.

## Proving one thing without revealing everything — selective disclosure

Remember the tree's superpower from Part 2. Suppose an investigator needs to verify a
*single* AI decision, but the other records are classified or unrelated.

You hand them **only that one event, a short trail of fingerprints up its branch, and
the Bitcoin-witnessed root.** They can confirm that exact decision is genuine and
unaltered — **without ever seeing any other record.** Like proving one page of a
notarized book is authentic by showing just that page and a short fingerprint trail,
never opening the rest of the book.

## Scale — a million events is no problem

Because everything funnels into one root, the cost of adding an event or proving one
barely grows as the pile gets huge. The clever tree structure means **doubling the number
of events adds only about one more step** — so going from a thousand to a million events is
a handful of extra steps, not a thousand times the work. (Engineers call this
"logarithmic." In practice: it stays fast whether you have a thousand events or many
millions.)

---

# Part 6 — Built for the field

## Working when the network is down — "DDIL"

Defense networks are often **DDIL: Denied, Degraded, Intermittent, or Limited** — jammed,
cut off, or air-gapped. The system is built for that.

Each agent keeps a **local notebook (buffer).** If the recorder is unreachable, the agent
**keeps working and writes events into its own notebook.** The moment the link returns,
the backlog **transmits automatically, in the original order** — nothing is lost, nothing
is reordered. Like a field radio that records into a notepad when the signal drops, then
sends the backlog the instant it reconnects. (Agents can also report how many events are
waiting, so a dashboard shows their status live.)

## Decisions a lawyer can read — the ROE record

For the highest-stakes events — engagement decisions — plain free-text isn't enough. The
system has a **standardized Rules-of-Engagement (ROE) form** a JAG officer or investigator
can read **without an engineer.** Each ROE decision record captures:

- **What** was decided (e.g. "engage-ready," "hold fire") and what the AI *recommended* vs.
  what was actually *authorized*
- **Who** authorized it — and whether a human was in the loop at all (or it ran unattended)
- **What the AI knew** at that moment (the sensor/intel snapshot)
- **Which ROE rule** applied, and the AI's **confidence**
- **How fast** — the time from first detection to authorization
- **Where**, which weapon system, and optional extras like a collateral-damage estimate or
  a JAG pre-authorization reference

There's also a **follow-up "what happened" record** that links back to the decision and
closes the loop (outcome, battle-damage assessment, whether collateral was confirmed). So
you can reconstruct not just the decision, but its consequences — all tamper-evident.

## How an existing app plugs in — three ways, all tiny

You don't rewrite your application. Pick whichever fits:

1. **Logging handler (two lines):** switch it on and your app's existing warnings/errors
   *also* flow into the vault automatically.
2. **One-line decorator:** tag a function and every call to it is recorded — inputs,
   result, how long it took, and any errors. (You can omit inputs/outputs for classified
   data.)
3. **A plain web request (curl):** any program in any language can post an event directly.

## Running disconnected — air-gap delivery

It ships as a self-contained **"care package"** (a UDS bundle / Zarf package) — the app
image plus its parts list (an SBOM, so security teams know exactly what's inside) — that
installs into a **disconnected, classified Kubernetes environment with no internet and no
app store.** It runs at the edge, on the same kind of network the mission runs on.

---

# Part 7 — The big picture

## The whole journey, end to end

Follow one event from birth to courtroom:

1. **An AI agent acts** — say, the threat-classifier flags a track.
2. **It signs the event** with its own pen (Part 3) and drops it through the one-way slot
   into the vault — or into its local notebook if the network is down (Part 6).
3. **The recorder appends it**, assigns the next number and a timestamp, takes its
   **fingerprint (leaf)**, links it to the previous entry (**the chain**), and folds it
   into **the tree** (Part 2).
4. **Every few seconds the tree's root is stamped to Bitcoin** via the post-office service;
   the receipt starts **pending** and turns **confirmed** ~10 minutes later (Part 4).
5. **Later, someone asks "prove what the system did."** You **verify** (re-fingerprint,
   check chain, check signatures, check receipts — Part 5). If anyone altered a record,
   verification names the exact entry.
6. **For a classified review,** you hand over just the one decision plus its short proof
   trail and the Bitcoin-witnessed root — **selective disclosure** (Part 5) — proving that
   decision without exposing anything else.

At no point could the AI reach back and change step 1. And once step 4 confirmed, the
record's existence-before-that-block is witnessed by all of Bitcoin.

## Why even the AI can't rewrite history

Put it together. Suppose the AI — or anyone — tries to quietly change a past record:

- Changing the event changes its **leaf**, which breaks **the chain** and changes **the
  root.**
- But the **old root is already witnessed by Bitcoin**, with a confirmed receipt.
- The altered records produce a root that **no longer matches** what Bitcoin saw, and the
  signature no longer fits.

The forgery doesn't blend in — it **fails to match the public record**, and the system
points to the exact entry that changed. The truth was witnessed *before* anyone tried to
change it, and that can't be undone.

## What it honestly does NOT do

Being straight about the limits is part of the design:

- **It's tamper-*evident*, not tamper-*proof.*** Think of a sealed glass evidence case, not
  a force field. It can't stop someone from putting a *false* statement inside — but once
  the case is sealed, you can always tell if the contents were swapped afterward. **"Garbage
  in" becomes permanently recorded garbage** — which is exactly what an investigation needs.
- **It proves a record existed and wasn't changed — not that it was *true* when written.**
  That's a different question, answered by the humans and processes around it.
- **The guarantee assumes two things about deployment:** (1) the vault runs **separately**
  from the agents it watches — letting the same AI run the vault is like letting a suspect
  run the evidence room; and (2) the pens are issued by a **real authority** (the hardened
  enrollment from Part 3), not self-issued. Get those right and the rest holds even against
  a highly capable adversary.

---

# Part 8 — Quick reference

## 30-second recap

- **Hash / fingerprint** — a unique stamp of data; changes completely if the data changes
  at all; can never be reversed.
- **Leaf** — the fingerprint of one single event.
- **Chain** — each entry carries the previous one's fingerprint, locking order; works
  offline; deletion leaves a gap.
- **Root** — one fingerprint standing for *all* events; the only thing we hand to Bitcoin.
- **Signature** — each agent signs its events with a pen only it has; proves who did it and
  that nothing changed.
- **Enrollment** — how pens are issued; the one place trust rests (self-issued in the demo,
  authority-issued in production).
- **Write-only vault** — agents can add records but never edit or delete them.
- **Stamping** — handing the root to Bitcoin (via OpenTimestamps) for a permanent timestamp.
- **The stamp** — your receipt proving your root was folded into a Bitcoin block; never your
  data.
- **Verify** — the auditor's walkthrough that re-checks everything and names any altered entry.
- **DDIL** — keeps working and buffers events when the network is down, then flushes in order.

## Mini-glossary

| Term | Plain meaning |
|---|---|
| **Hash** | A digital fingerprint of data. Same data → same fingerprint; any change → a totally different one; can't be reversed. |
| **Leaf node** | The fingerprint of one individual event. |
| **Hash chain** | Records linked so each carries the previous one's fingerprint — locks their order, detectable offline. |
| **Genesis** | The very first entry (number 0); the cornerstone the chain builds on. |
| **Merkle tree / Merkle Mountain Range** | The "tournament bracket" that combines all leaves up into one root, efficiently, even as events keep arriving. |
| **Root** | The single top fingerprint that represents every event below it. |
| **Signature (Ed25519)** | An agent's unforgeable mark on an event; ties the event to that agent's identity and exact content. |
| **Attribution** | Knowing *which* agent produced a record, provably. |
| **Enrollment / provisioning** | Issuing and registering an agent's signing key; the ultimate trust anchor. |
| **Recorder / write-only vault** | The separate service that holds the ledger; agents can append but never edit or delete. |
| **Stamping / anchoring** | Getting the root permanently timestamped by Bitcoin. |
| **OpenTimestamps** | The free public service that bundles thousands of roots and writes one combined fingerprint to Bitcoin. |
| **Stamp / `.ots` proof** | The receipt tracing your root to a specific Bitcoin block — your proof, not your data. |
| **Pending vs. confirmed** | "Submitted, waiting for Bitcoin" vs. "a Bitcoin block has permanently recorded it." |
| **Verify** | Re-checking the whole record (fingerprints, chain, signatures, receipts) and naming any altered entry. |
| **Selective disclosure** | Proving one event is genuine without revealing any of the others. |
| **DDIL** | Denied/Degraded/Intermittent/Limited comms — the system buffers locally and flushes in order. |
| **ROE record** | A standardized engagement-decision form a JAG officer can read without an engineer. |
| **Tamper-evident (vs. tamper-proof)** | You can always *detect* a change afterward — though you can't stop a lie from being written in the first place. |
| **Air-gap / UDS bundle / Zarf** | A self-contained package that installs into a disconnected, classified network. |
