import { useEffect, useRef } from 'react'
import gsap from 'gsap'
import { fp } from '../humanize'

// The Bitcoin anchor at the base of the chain. Pulses to "confirmed" when a
// (mock or real) block locks the chain's fingerprint in — the moment the truth
// becomes irreversible.
export default function AnchorBar({ anchors }) {
  const badge = useRef(null)
  const latest = anchors.length ? anchors[anchors.length - 1] : null
  const confirmed = anchors.find((a) => a.status === 'confirmed')
  const best = confirmed || latest
  const status = best ? best.status : 'none'

  const wasConfirmed = useRef(false)
  useEffect(() => {
    if (status === 'confirmed' && !wasConfirmed.current && badge.current) {
      wasConfirmed.current = true
      gsap.fromTo(badge.current, { scale: 0.7 },
        { scale: 1, duration: 0.6, ease: 'elastic.out(1, 0.5)' })
    }
  }, [status])

  return (
    <div className="anchor-bar">
      <div ref={badge} className={`btc-badge ${status === 'confirmed' ? 'confirmed' : ''}`}>₿</div>
      <div className="anchor-text">
        <div className="t1">Bitcoin anchor</div>
        <div className="t2">
          {best
            ? <>covers records ≤ #{best.head_seq} · <span className="mono">{fp(best.head_hash)}</span></>
            : 'no fingerprint stamped yet'}
        </div>
      </div>
      <div className={`anchor-status ${status}`}>
        {status === 'confirmed' ? '✓ irreversible'
          : status === 'pending' ? '◷ confirming…'
          : '— not anchored'}
      </div>
    </div>
  )
}
