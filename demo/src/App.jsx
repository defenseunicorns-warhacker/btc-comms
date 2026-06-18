import { useState, useCallback } from 'react'
import { useStable } from './useStable'
import { api } from './api'
import { SCRIPT, DAMNING_SEQ, FORGED_PAYLOAD } from './scenario'
import S1_Stream from './components/scenes/S1_Stream'
import S2_Hash from './components/scenes/S2_Hash'
import S3_Chain from './components/scenes/S3_Chain'
import S4_Sign from './components/scenes/S4_Sign'
import S5_Anchor from './components/scenes/S5_Anchor'
import S6_Tamper from './components/scenes/S6_Tamper'

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

const SCENES = [
  {
    title: 'Every decision is recorded',
    sub: 'Each action the autonomous system takes is written to an append-only ledger — in sequence, the instant it happens.',
  },
  {
    title: 'Each entry gets a fingerprint',
    sub: 'A cryptographic hash is a fingerprint of the data. Change one character anywhere — the fingerprint is unrecognizable.',
  },
  {
    title: 'Entries chain together',
    sub: "Each entry's fingerprint is baked into the next, linking them in order. This is what makes the records tamper-evident.",
  },
  {
    title: 'Every agent signs its work',
    sub: "Each decision is signed with a private key only that agent holds. Attribution is cryptographic — not a label you can overwrite.",
  },
  {
    title: 'Bitcoin locks the chain in time',
    sub: "The chain's fingerprint is published to the Bitcoin blockchain. Once confirmed, no authority on earth can rewrite it.",
  },
  {
    title: "Tampering can't hide",
    sub: 'Now watch an adversary alter a record. Because the original chain’s fingerprint is already locked in Bitcoin, the change is mathematically provable — and instantly detected.',
  },
]

export default function App() {
  const { entries, anchors, verify, connected } = useStable()

  const [scene, setScene] = useState(0)
  const [busy, setBusy] = useState(false)
  const [brokenAt, setBrokenAt] = useState(null)
  const [forgeResult, setForgeResult] = useState(null)

  const effectiveBrokenAt = brokenAt ?? (verify && !verify.ok ? verify.broken_at : null)

  const fireEngagement = useCallback(async () => {
    if (entries.length > 1) return
    setBusy(true)
    try {
      for (const ev of SCRIPT) {
        await api.appendEvent(ev.agent, ev.payload).catch(() => {})
        await sleep(600)
      }
    } finally {
      setBusy(false)
    }
  }, [entries.length])

  const injectTamper = useCallback(async () => {
    setBusy(true)
    try {
      setBrokenAt(DAMNING_SEQ)
      await api.tamper(DAMNING_SEQ, FORGED_PAYLOAD).catch(() => {})
      await sleep(400)
      await api.verify().catch(() => {})
    } finally {
      setBusy(false)
    }
  }, [])

  const tryForge = useCallback(async () => {
    setBusy(true)
    try {
      const r = await api.impersonate().catch(() => null)
      setForgeResult(r || { error: true })
    } finally {
      setBusy(false)
    }
  }, [])

  const fireAnchor = useCallback(async () => {
    setBusy(true)
    try {
      await api.anchorNow().catch(() => {})
      for (let i = 0; i < 15; i++) {
        await sleep(2000)
        await api.upgradeAnchors().catch(() => {})
        const fresh = await api.anchors().catch(() => [])
        if (fresh.some((a) => a.status === 'confirmed')) break
      }
    } finally {
      setBusy(false)
    }
  }, [])

  const reset = useCallback(async () => {
    setBusy(true)
    try {
      await api.reset().catch(() => {})
      setBrokenAt(null)
      setForgeResult(null)
      setScene(0)
    } finally {
      setBusy(false)
    }
  }, [])

  const n = SCENES.length
  const num = String(scene + 1).padStart(2, '0')
  const total = String(n).padStart(2, '0')

  return (
    <div className="app">
      <div className="topbar">
        <div className="brand">STABLE</div>
        <div className="progress-dots">
          {SCENES.map((_, i) => (
            <div
              key={i}
              className={`pdot ${i === scene ? 'cur' : i < scene ? 'past' : ''}`}
            />
          ))}
        </div>
        <div className="topbar-right">
          <span className={`conn-dot ${connected ? 'live' : 'off'}`} />
          <button className="btn-ghost sm" onClick={reset} disabled={busy}>
            Reset
          </button>
        </div>
      </div>

      <div className="scene-header">
        <div className="scene-n">{num} / {total}</div>
        <h1 className="scene-title">{SCENES[scene].title}</h1>
        <p className="scene-sub">{SCENES[scene].sub}</p>
      </div>

      <div className="scene-body">
        {scene === 0 && (
          <S1_Stream entries={entries} busy={busy} onStart={fireEngagement} />
        )}
        {scene === 1 && (
          <S2_Hash entries={entries} />
        )}
        {scene === 2 && (
          <S3_Chain entries={entries} />
        )}
        {scene === 3 && (
          <S4_Sign
            entries={entries}
            busy={busy}
            forgeResult={forgeResult}
            onForge={tryForge}
          />
        )}
        {scene === 4 && (
          <S5_Anchor
            entries={entries}
            anchors={anchors}
            busy={busy}
            onAnchor={fireAnchor}
          />
        )}
        {scene === 5 && (
          <S6_Tamper
            entries={entries}
            brokenAt={effectiveBrokenAt}
            busy={busy}
            injectTamper={injectTamper}
            anchor={anchors.find((a) => a.status === 'confirmed')}
          />
        )}
      </div>

      <div className="scene-nav">
        <button
          className="nav-btn"
          onClick={() => setScene((s) => s - 1)}
          disabled={scene === 0 || busy}
        >
          ← Back
        </button>
        <button
          className="nav-btn primary"
          onClick={() => setScene((s) => s + 1)}
          disabled={scene === n - 1 || busy}
        >
          Next →
        </button>
      </div>
    </div>
  )
}
