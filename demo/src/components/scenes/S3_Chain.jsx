import { useRef } from 'react'
import gsap from 'gsap'
import ChainView from './ChainView'

// Scene 3 — the chain, intact. Demonstrates how each fingerprint is baked into
// the next block. No tampering here; that's the finale (Scene 6).
export default function S3_Chain({ entries }) {
  const containerRef = useRef(null)

  function traceLinks() {
    if (!containerRef.current) return
    const lines = containerRef.current.querySelectorAll('.s3-line')
    const prevs = containerRef.current.querySelectorAll('.s3-prev')
    gsap.killTweensOf([...lines, ...prevs])
    gsap.fromTo(lines,
      { backgroundColor: '#1e2633' },
      { backgroundColor: '#3b82f6', duration: 0.3, stagger: 0.18, yoyo: true, repeat: 1, ease: 'power2.inOut' })
    gsap.fromTo(prevs,
      { color: '#4a5568' },
      { color: '#3b82f6', duration: 0.3, stagger: 0.18, yoyo: true, repeat: 1, ease: 'power2.inOut',
        onComplete: () => gsap.set([...lines, ...prevs], { clearProps: 'all' }) })
  }

  const hasChain = entries.filter((e) => e.seq > 0).length > 0

  return (
    <div>
      <div ref={containerRef}>
        <ChainView entries={entries} brokenAt={null} />
      </div>
      {hasChain && (
        <div className="s3-actions">
          <button className="btn-primary cta" onClick={traceLinks}>
            ▸ Trace the hash links
          </button>
          <p className="s3-note">
            Each block stores the previous block's fingerprint. Re-compute any block and the
            next one's link no longer matches.
          </p>
        </div>
      )}
    </div>
  )
}
