import { useEffect, useRef } from 'react'
import gsap from 'gsap'
import { AGENTS } from '../scenario'

// Fires the instant verify() flips to not-ok. In a real deployment this is the
// SOC alert / pager — a tamper can never be silent, because altering any record
// breaks every hash after it and the next verification names it.
export default function AlarmBanner({
  brokenAt, entry, reason, checkpoint, onInvestigate, onDismiss,
}) {
  const el = useRef(null)
  useEffect(() => {
    if (el.current) {
      gsap.fromTo(el.current,
        { y: -70, opacity: 0 },
        { y: 0, opacity: 1, duration: 0.45, ease: 'back.out(1.5)' })
    }
  }, [])

  const agent = entry ? (AGENTS[entry.source_id]?.label || entry.source_id) : 'unknown agent'

  return (
    <div ref={el} className="alarm">
      <div className="alarm-led" />
      <div className="alarm-main">
        <div className="alarm-title">INTEGRITY BREACH DETECTED</div>
        <div className="alarm-detail">
          Record #{brokenAt} · {agent} · {reason || 'payload altered'} — verify() will not vouch for records #{brokenAt}+.
          {checkpoint
            ? <> Clean checkpoint #{checkpoint.head_seq} is anchored in Bitcoin{checkpoint.block_height ? ` (block ${checkpoint.block_height.toLocaleString()})` : ''} — recovery available in the monitor.</>
            : <> No clean Bitcoin checkpoint precedes the break.</>}
        </div>
      </div>
      <div className="alarm-actions">
        <button className="btn btn-light sm" onClick={onInvestigate}>Investigate →</button>
        <button className="alarm-x" onClick={onDismiss} title="Acknowledge">✕</button>
      </div>
    </div>
  )
}
