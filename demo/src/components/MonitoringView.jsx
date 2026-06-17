import { useEffect, useRef } from 'react'
import gsap from 'gsap'
import Chain from './Chain'
import AgentPanel from './AgentPanel'
import AnchorBar from './AnchorBar'
import { AGENTS } from '../scenario'
import { humanize } from '../humanize'

// Live SOC view: agents operating, the decision ledger filling in real time,
// and one big integrity readout that flips to BREACH the instant verify() fails.
function deriveStates(entries) {
  const out = {}
  for (const e of entries) {
    if (e.seq === 0 || !AGENTS[e.source_id]) continue
    out[e.source_id] = { status: humanize(e), firing: false }
  }
  return out
}

export default function MonitoringView({
  entries, anchors, verify, agentStates, brokenAt, confirmedThrough, onSelect,
  busy, checkpoint, reason, onRebaseline, onInvestigate,
}) {
  const chainRef = useRef(null)
  const hero = useRef(null)
  const prevBroken = useRef(null)

  const liveStates = { ...deriveStates(entries), ...agentStates }

  useEffect(() => {
    if (brokenAt != null && prevBroken.current == null) {
      chainRef.current?.playTamper(brokenAt)
      if (hero.current) {
        gsap.fromTo(hero.current, { x: -7 },
          { x: 0, duration: 0.06, repeat: 9, yoyo: true, ease: 'none' })
      }
    }
    prevBroken.current = brokenAt
  }, [brokenAt])

  const breached = brokenAt != null
  const ok = verify?.ok && !breached
  const state = breached ? 'breach' : ok ? 'ok' : 'idle'

  // Post-break records that still carry a valid signature stay attributable —
  // you lose ordering/continuity proof, not authenticity proof.
  const signedAfter = entries.filter((e) => breached && e.seq > brokenAt && e.signature)

  return (
    <div className="monitor">
      <div ref={hero} className={`integrity-hero ${state}`}>
        <div className="ih-icon">{breached ? '⚠' : ok ? '✓' : '○'}</div>
        <div className="ih-text">
          <div className="ih-title">
            {breached ? 'INTEGRITY BREACH DETECTED'
              : ok ? 'INTEGRITY VERIFIED'
              : 'AWAITING ACTIVITY'}
          </div>
          <div className="ih-sub">
            {breached
              ? `Tampering at record #${brokenAt} — ${reason || verify?.reason || 'chain broken downstream'}`
              : ok
                ? `All ${verify?.verified_entries ?? entries.length} records authentic · continuously re-verified`
                : 'No autonomous decisions recorded yet'}
          </div>
        </div>
        <div className="ih-live">
          <span className={`dot ${breached ? 'off' : 'live'}`} />
          {breached ? 'alarm' : 'monitoring'}
        </div>
      </div>

      {breached && (
        <div className="recovery">
          <div className="rec-step">
            <span className="rec-n">1</span>
            <div><strong>What broke.</strong> verify() halts at record #{brokenAt} — “{reason || verify?.reason}”. It will not vouch for anything from #{brokenAt} on.</div>
          </div>
          <div className="rec-step">
            <span className="rec-n">2</span>
            <div>
              <strong>What still holds.</strong>{' '}
              {checkpoint
                ? <>Records #0–{checkpoint.head_seq} are anchored in Bitcoin{checkpoint.block_height ? ` (block ${checkpoint.block_height.toLocaleString()})` : ''} — ground truth the attacker can’t rewrite.</>
                : <>No Bitcoin checkpoint precedes the break.</>}
              {signedAfter.length > 0 && <> Records {signedAfter.map((e) => `#${e.seq}`).join(', ')} are still signed → individually attributable; only their ordering is in question.</>}
            </div>
          </div>
          <div className="rec-step">
            <span className="rec-n">3</span>
            <div className="rec-action">
              <div><strong>Recover forward.</strong> Seal the compromised chain as evidence and re-baseline a fresh chain from the last clean checkpoint.</div>
              <div className="rec-btns">
                <button className="btn btn-ghost sm" onClick={onInvestigate}>Investigate →</button>
                <button className="btn btn-light sm" disabled={busy || !checkpoint}
                  onClick={onRebaseline}>
                  ↻ Re-baseline from checkpoint{checkpoint ? ` #${checkpoint.head_seq}` : ''}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      <div className="monitor-body">
        <aside className="monitor-side">
          <div className="side-label">AI agents · counter-UAS</div>
          <AgentPanel states={liveStates} />
          <div className="side-label">Bitcoin anchor</div>
          <AnchorBar anchors={anchors} />
        </aside>

        <section className="monitor-stream">
          <div className="stream-head">
            Live decision ledger
            {breached && <span className="stream-alarm">● BREACH</span>}
          </div>
          <Chain
            ref={chainRef}
            entries={entries}
            brokenAt={brokenAt}
            confirmedThrough={confirmedThrough}
            onSelect={onSelect}
          />
        </section>
      </div>
    </div>
  )
}
