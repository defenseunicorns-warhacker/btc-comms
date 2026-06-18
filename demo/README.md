# STABLE — visual explainer

A stepped, animated explainer of how STABLE works, for a technical audience that
doesn't know blockchain. It drives the **real** recorder — nothing is faked;
hashing, signing, `verify()`, and the Bitcoin anchor all run against the live
cryptographic engine. The animation *is* the explanation.

Six scenes, advanced with **Back / Next**. Each scene has one in-scene action
button (the glowing one) that demonstrates the concept live.

1. **Every decision is recorded** — click *Record engagement* and the 9-event
   counter-UAS scenario streams into an append-only, signed, hash-chained ledger,
   one record at a time.
2. **Each entry gets a fingerprint** — compute a record's SHA-256 fingerprint,
   then change a single field and watch the fingerprint become unrecognizable.
3. **Entries chain together** — the chain, intact. *Trace the hash links* shows
   how each block stores the previous block's fingerprint, linking them in order.
4. **Every agent signs its work** — each record carries an Ed25519 signature.
   *Try to post a forged entry* sends a real impersonation request to the
   recorder and shows it **rejected** — attribution is cryptographic.
5. **Bitcoin locks the chain in time** — *Anchor to Bitcoin* publishes the chain's
   Merkle root; once confirmed in a block, the chain's state is immutable.
6. **Tampering can't hide** (finale) — now an adversary rewrites record #7. The
   chain breaks and cascades red, and because the original fingerprint is already
   in Bitcoin, the alteration is **mathematically provable** — detected instantly,
   no central authority required.

The good chain is recorded, signed, and anchored to Bitcoin (scenes 1–5, all
green) **before** anything is tampered (scene 6). Trust is established and banked
first; the break is the payoff.

## Run it

**1. Start the recorder** (from the repo root) in demo mode with a clean DB:

```bash
rm -f demo.db demo.db-wal demo.db-shm
DEMO_MODE=true MOCK_ANCHOR=true \
  MOCK_CONFIRM_DELAY=3 AUTO_STAMP=false UPGRADE_INTERVAL=6 \
  DB_PATH=demo.db python3 -m uvicorn src.api:app --port 8001
```

`AUTO_STAMP=false` doesn't start the background stamp/upgrade thread, so anchoring
happens **only** when you click *Anchor to Bitcoin* in Scene 5. This keeps the demo
deterministic — without it the loop stamps genesis at startup, leaving a stale
anchor that races the button. Manual `/anchor/now` + `/anchor/upgrade` still work.

**2. Start the demo** (from `demo/`):

```bash
npm install        # first time only
npm run dev        # opens http://localhost:5173
```

The Vite dev server proxies all `/stream`, `/verify`, `/demo/*`, … calls to the
recorder on `:8001` (override with `STABLE_URL`).

## Suggested demo flow

Just walk the six scenes in order with **Next**, performing each scene's glowing
action button as you go. Use **Reset** (top-right) to wipe back to genesis and run
it again from a clean state.

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
  App.jsx          shell: 6-scene router, progress dots, shared state
  components/
    scenes/
      S1_Stream.jsx   records stream in, auto-scrolling as the chain fills
      S2_Hash.jsx     SHA-256 fingerprint reveal + one-field mutation
      S3_Chain.jsx    the intact chain; "trace the hash links"
      S4_Sign.jsx     Ed25519 lineage + live forged-attribution rejection
      S5_Anchor.jsx   Merkle tree → Bitcoin block (pending → confirmed)
      S6_Tamper.jsx   finale: alter #7, watch it break, Bitcoin proves it
      ChainView.jsx   shared chain renderer (intact + broken) for S3 and S6
```
