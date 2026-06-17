import { useState, useCallback, useMemo } from 'react'
import { useStable } from './useStable'
import { api } from './api'
import { SCRIPT, DAMNING_SEQ, FORGED_PAYLOAD } from './scenario'
import MonitoringView from './components/MonitoringView'
import InvestigationView from './components/InvestigationView'
import AlarmBanner from './components/AlarmBanner'
import DemoControls from './components/DemoControls'
import ProofModal from './components/ProofModal'

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

export default function App() {
  const { entries, anchors, verify, connected, confirmedThrough } = useStable()

  const [view, setView] = useState('monitor')         // 'monitor' | 'investigate'
  const [selectedSeq, setSelectedSeq] = useState(null)
  const [proof, setProof] = useState(null)
  const [brokenAt, setBrokenAt] = useState(null)       // local, for instant break
  const [acknowledged, setAcknowledged] = useState(false)
  const [agentStates, setAgentStates] = useState({})
  const [busy, setBusy] = useState(false)
  const [lastAction, setLastAction] = useState(null)
  const [toasts, setToasts] = useState([])

  // verify() is the source of truth, so a mid-demo reload still shows the break.
  const effectiveBrokenAt = brokenAt ?? (verify && !verify.ok ? verify.broken_at : null)
  const breached = effectiveBrokenAt != null

  const toast = useCallback((kind, tt, tb) => {
    const id = Math.random()
    setToasts((t) => [...t, { id, kind, tt, tb }])
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 7000)
  }, [])

  // ── Simulation handlers (the only things that touch the recorder) ──────────
  async function fireEvent(ev) {
    setAgentStates((s) => ({ ...s, [ev.agent]: { status: ev.status, firing: true } }))
    await api.appendEvent(ev.agent, ev.payload).catch(() => {})
    await sleep(140)
    setAgentStates((s) => ({ ...s, [ev.agent]: { status: ev.status, firing: false } }))
    await sleep(300)
  }

  async function waitForCheckpoint(minSeq) {
    await api.anchorNow().catch(() => {})
    for (let i = 0; i < 10; i++) {
      await sleep(2000)
      await api.upgradeAnchors().catch(() => {})
      const fresh = await api.anchors().catch(() => [])
      if (fresh.some((a) => a.status === 'confirmed' && a.head_seq >= minSeq)) return true
    }
    return false
  }

  async function runEngagement() {
    setBusy(true); setLastAction('Recording counter-UAS engagement…')
    try {
      // Records #1–6: the lead-up, before the autonomous engagement decision.
      for (const ev of SCRIPT.filter((e) => e.seq <= 6)) await fireEvent(ev)
      // Lock a Bitcoin checkpoint here — this is the clean, externally-proven
      // ground truth a tamper at #7 cannot reach back and rewrite.
      setLastAction('Checkpoint: anchoring records #0–6 into Bitcoin…')
      await waitForCheckpoint(6)
      setLastAction('Checkpoint #6 locked in Bitcoin. Continuing engagement…')
      // Records #7–9: the autonomous engagement and aftermath.
      for (const ev of SCRIPT.filter((e) => e.seq >= 7)) await fireEvent(ev)
      await api.verify().catch(() => {})
      setLastAction('9 decisions recorded — signed, chained, checkpoint #6 in Bitcoin.')
    } finally { setBusy(false) }
  }

  async function injectTamper() {
    setBusy(true); setLastAction('Adversary rewriting record #7…')
    try {
      setBrokenAt(DAMNING_SEQ)
      setAcknowledged(false)
      await api.tamper(DAMNING_SEQ, FORGED_PAYLOAD).catch(() => {})
      await sleep(450)
      await api.verify().catch(() => {})   // detection fires from the fresh result
      setLastAction('Record #7 altered — watch the monitor.')
    } finally { setBusy(false) }
  }

  // The last confirmed Bitcoin anchor BEFORE the break — the clean checkpoint
  // verify() can't surface itself (it halts at broken_at), so we read it from
  // the anchors the attacker couldn't reach back and invalidate.
  const checkpoint = useMemo(() => {
    const clean = anchors.filter(
      (a) => a.status === 'confirmed' &&
        (effectiveBrokenAt == null || a.head_seq < effectiveBrokenAt))
    if (!clean.length) return null
    return clean.reduce((best, a) => (a.head_seq > best.head_seq ? a : best))
  }, [anchors, effectiveBrokenAt])

  // Operator's recovery action: don't fix the chain in place — seal it as
  // evidence and re-baseline a fresh chain from the last clean Bitcoin checkpoint.
  async function rebaselineRecord() {
    if (!checkpoint) return
    setBusy(true); setLastAction('Sealing compromised chain · re-baselining from checkpoint…')
    try {
      await api.rebaseline({
        broken_at: effectiveBrokenAt,
        reason: verify?.reason,
        checkpoint_seq: checkpoint.head_seq,
        checkpoint_hash: checkpoint.head_hash,
        block_height: checkpoint.block_height ?? null,
      }).catch(() => {})
      await sleep(300)
      await api.verify().catch(() => {})
      setBrokenAt(null); setAcknowledged(true); setAgentStates({})
      setView('monitor')
      const blk = checkpoint.block_height
      setLastAction(`Re-baselined from checkpoint #${checkpoint.head_seq}${blk ? ` · Bitcoin block ${blk.toLocaleString()}` : ''}.`)
      toast('good', '✓ Re-baselined from clean checkpoint',
        `Compromised chain sealed as evidence. New chain continues from record #${checkpoint.head_seq}${blk ? `, anchored in Bitcoin block ${blk.toLocaleString()}` : ''} — a state the attacker could not rewrite.`)
    } finally { setBusy(false) }
  }

  async function reset() {
    setBusy(true)
    try {
      await api.reset().catch(() => {})
      setBrokenAt(null); setAcknowledged(false); setSelectedSeq(null)
      setProof(null); setAgentStates({}); setLastAction('Ledger reset to genesis.')
    } finally { setBusy(false) }
  }

  async function tryImpersonate() {
    const r = await api.impersonate().catch(() => null)
    if (!r) { toast('blocked', '⚠ Unavailable', 'Impersonation endpoint needs DEMO_MODE.'); return }
    if (r.rejected) {
      toast('blocked', '✕ Forged signature rejected',
        `${r.reason} Attribution is cryptographic — not a label an attacker can type.`)
      setLastAction('Signature forgery rejected at ingest.')
    } else {
      toast('blocked', '⚠ Unexpected', r.reason || 'not blocked')
    }
  }

  const openProof = useCallback(async (seq) => {
    const r = await api.proof(seq).catch(() => null)
    if (r) setProof(r)
  }, [])

  const investigate = useCallback((seq) => {
    setSelectedSeq(seq); setView('investigate'); setAcknowledged(true)
  }, [])

  const brokenEntry = useMemo(
    () => entries.find((e) => e.seq === effectiveBrokenAt) || null,
    [entries, effectiveBrokenAt])

  return (
    <div className="app">
      <div className="topbar">
        <div className="brand">STABLE<span className="sub">accountability for autonomous systems</span></div>
        <div className="tabs">
          <button className={`tab ${view === 'monitor' ? 'on' : ''}`} onClick={() => setView('monitor')}>
            <span className="tab-dot live" /> Live Monitoring
          </button>
          <button className={`tab ${view === 'investigate' ? 'on' : ''}`} onClick={() => setView('investigate')}>
            ⚖ Investigation
          </button>
        </div>
        <div className="spacer" />
        <span className="chip"><span className={`dot ${connected ? 'live' : 'off'}`} /> {connected ? 'recorder live' : 'reconnecting…'}</span>
      </div>

      {breached && !acknowledged && (
        <AlarmBanner
          brokenAt={effectiveBrokenAt}
          entry={brokenEntry}
          reason={verify?.reason}
          checkpoint={checkpoint}
          onInvestigate={() => investigate(effectiveBrokenAt)}
          onDismiss={() => setAcknowledged(true)}
        />
      )}

      <div className="view">
        {view === 'monitor' ? (
          <MonitoringView
            entries={entries} anchors={anchors} verify={verify}
            agentStates={agentStates} brokenAt={effectiveBrokenAt}
            confirmedThrough={confirmedThrough} onSelect={openProof}
            busy={busy} checkpoint={checkpoint} reason={verify?.reason}
            onRebaseline={rebaselineRecord}
            onInvestigate={() => investigate(effectiveBrokenAt)}
          />
        ) : (
          <InvestigationView
            entries={entries} verify={verify} anchors={anchors}
            brokenAt={effectiveBrokenAt} confirmedThrough={confirmedThrough}
            selectedSeq={selectedSeq} onSelectSeq={setSelectedSeq}
            onVerify={() => api.verify().catch(() => {})} onProof={openProof}
          />
        )}
      </div>

      <DemoControls
        busy={busy} hasRun={entries.length > 1} breached={breached}
        lastAction={lastAction}
        onRun={runEngagement} onTamper={injectTamper}
        onImpersonate={tryImpersonate} onReset={reset}
      />

      <ProofModal result={proof} onClose={() => setProof(null)} />

      <div className="toasts">
        {toasts.map((t) => (
          <div key={t.id} className={`toast ${t.kind}`}>
            <div className="tt">{t.tt}</div>
            <div className="tb">{t.tb}</div>
          </div>
        ))}
      </div>
    </div>
  )
}
