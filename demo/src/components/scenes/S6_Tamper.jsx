import { useEffect, useRef } from 'react'
import gsap from 'gsap'
import ChainView from './ChainView'

// Scene 6 (finale) — the chain is already signed and anchored in Bitcoin. Now an
// adversary alters record #7. The break cascades, and the Bitcoin anchor makes
// the tamper mathematically provable.
export default function S6_Tamper({ entries, brokenAt, busy, injectTamper, anchor }) {
  const blockRefs = useRef({})
  const prevBroken = useRef(null)
  const proofRef = useRef(null)

  const window5to9 = entries.filter((e) => e.seq >= 5 && e.seq <= 9).sort((a, b) => a.seq - b.seq)
  const chain = window5to9.length === 0
    ? entries.filter((e) => e.seq > 0).slice(-5).sort((a, b) => a.seq - b.seq)
    : window5to9

  useEffect(() => {
    if (brokenAt != null && prevBroken.current == null) {
      const tamperEl = blockRefs.current[brokenAt]
      if (tamperEl) {
        gsap.timeline().to(tamperEl, { x: -6, duration: 0.05, repeat: 7, yoyo: true, ease: 'none' })
      }
      const downstream = chain
        .filter((e) => e.seq > brokenAt)
        .map((e) => blockRefs.current[e.seq])
        .filter(Boolean)
      if (downstream.length) {
        gsap.fromTo(downstream,
          { opacity: 1 },
          { opacity: 0.5, duration: 0.2, stagger: 0.12, yoyo: true, repeat: 1,
            onComplete: () => gsap.set(downstream, { opacity: 1 }) })
      }
      // Reveal the Bitcoin-proof payoff — the climax of the whole walkthrough —
      // after the cascade settles, since the broken flags grow the chain past the fold.
      setTimeout(() => {
        proofRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
      }, 900)
    }
    prevBroken.current = brokenAt
  }, [brokenAt])

  const hasChain = chain.length > 0
  const blockHeight = anchor?.block_height

  return (
    <div>
      {brokenAt == null && (
        <div className={`s6-anchored-banner${anchor ? '' : ' muted'}`}>
          {anchor
            ? `✓ This chain is anchored in Bitcoin block #${blockHeight?.toLocaleString()}. Its fingerprint is now immutable.`
            : 'Tip: anchor the chain in Scene 5 first to see the full proof.'}
        </div>
      )}

      <div style={{ marginTop: 12 }}>
        <ChainView entries={entries} brokenAt={brokenAt} blockRefs={blockRefs} />
      </div>

      {brokenAt == null && hasChain && (
        <div className="s3-actions">
          <button className="btn-danger cta" onClick={injectTamper} disabled={busy}>
            {busy ? 'Rewriting…' : 'Rewrite record #7 — flip human_authorized to true'}
          </button>
        </div>
      )}

      {brokenAt != null && (
        <>
          <div className="s3-verdict">
            verify() halts at #{brokenAt}. Every record after it is invalidated — the break is impossible to hide.
          </div>
          <div className="s6-btc-proof" ref={proofRef}>
            {blockHeight
              ? <>Bitcoin block #{blockHeight.toLocaleString()} still holds the <strong>original</strong> chain's
                fingerprint. The altered record produces a different fingerprint — the mismatch is cryptographic
                proof of tampering. No central authority is needed to detect it.</>
              : <>The altered record produces a different fingerprint than the one anchored in Bitcoin. The mismatch
                is cryptographic proof of tampering — no central authority is needed to detect it.</>}
          </div>
        </>
      )}
    </div>
  )
}
