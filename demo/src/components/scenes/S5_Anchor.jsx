import { useEffect, useRef } from 'react'
import gsap from 'gsap'
import { fp } from '../../humanize'

export default function S5_Anchor({ entries, anchors, busy, onAnchor }) {
  const confirmed = anchors.find((a) => a.status === 'confirmed')
  const pending = anchors.find((a) => a.status === 'pending')
  const hasAnchor = confirmed || pending

  const line1aRef = useRef(null)
  const line1bRef = useRef(null)
  const line2aRef = useRef(null)
  const line2bRef = useRef(null)
  const nodeARef = useRef(null)
  const nodeBRef = useRef(null)
  const nodeRootRef = useRef(null)
  const lineRootRef = useRef(null)
  const animated = useRef(false)

  const leaves = [1, 3, 5, 7].map((seq) => entries.find((e) => e.seq === seq)).filter(Boolean)

  useEffect(() => {
    if (hasAnchor && !animated.current) {
      animated.current = true
      const tl = gsap.timeline()
      const lines = [line1aRef.current, line1bRef.current, line2aRef.current, line2bRef.current].filter(Boolean)
      const nodes = [nodeARef.current, nodeBRef.current].filter(Boolean)
      const root = nodeRootRef.current
      const rootLine = lineRootRef.current

      lines.forEach((l) => {
        const len = l.getTotalLength?.() || 60
        gsap.set(l, { strokeDasharray: len, strokeDashoffset: len })
      })
      if (root) gsap.set(root, { opacity: 0, scale: 0.5, transformOrigin: '50% 50%' })
      if (rootLine) {
        const len = rootLine.getTotalLength?.() || 60
        gsap.set(rootLine, { strokeDasharray: len, strokeDashoffset: len })
      }
      nodes.forEach((n) => gsap.set(n, { opacity: 0 }))

      tl.to(lines, { strokeDashoffset: 0, duration: 0.5, stagger: 0.1, ease: 'power2.inOut' })
        .to(nodes, { opacity: 1, duration: 0.3, stagger: 0.1 }, '-=0.1')
        .to(rootLine, { strokeDashoffset: 0, duration: 0.4, ease: 'power2.inOut' }, '-=0.1')
        .to(root, { opacity: 1, scale: 1, duration: 0.4, ease: 'back.out(1.5)' }, '-=0.2')
    }
  }, [hasAnchor])

  return (
    <div className="s5-wrap">
      <div className="s5-leaves">
        {leaves.length > 0
          ? leaves.map((e) => (
              <div className="s5-leaf" key={e.seq}>
                <div className="s5-leaf-seq">#{e.seq}</div>
                <div>{fp(e.entry_hash)}</div>
              </div>
            ))
          : [1, 3, 5, 7].map((n) => (
              <div className="s5-leaf s5-leaf-placeholder" key={n}>
                <div className="s5-leaf-seq">#{n}</div>
                <div style={{ color: 'var(--muted)' }}>not yet recorded</div>
              </div>
            ))}
      </div>

      <svg className="s5-tree-svg" viewBox="0 0 480 180" fill="none" xmlns="http://www.w3.org/2000/svg">
        {/* Lines from leaves to intermediate nodes */}
        <line ref={line1aRef} x1="60"  y1="10" x2="140" y2="90" stroke="#3b82f6" strokeWidth="1.5" />
        <line ref={line1bRef} x1="180" y1="10" x2="140" y2="90" stroke="#3b82f6" strokeWidth="1.5" />
        <line ref={line2aRef} x1="300" y1="10" x2="340" y2="90" stroke="#3b82f6" strokeWidth="1.5" />
        <line ref={line2bRef} x1="420" y1="10" x2="340" y2="90" stroke="#3b82f6" strokeWidth="1.5" />
        {/* Intermediate nodes */}
        <circle ref={nodeARef} cx="140" cy="90" r="8" fill="#1e2633" stroke="#3b82f6" strokeWidth="1.5" />
        <circle ref={nodeBRef} cx="340" cy="90" r="8" fill="#1e2633" stroke="#3b82f6" strokeWidth="1.5" />
        {/* Lines to root */}
        <line ref={lineRootRef} x1="140" y1="98" x2="240" y2="160" stroke="#3b82f6" strokeWidth="1.5" />
        <line x1="340" y1="98" x2="240" y2="160" stroke="#3b82f6" strokeWidth="1.5" opacity={hasAnchor ? 1 : 0} />
        {/* Root node */}
        <circle ref={nodeRootRef} cx="240" cy="160" r="10" fill="#1e2633" stroke={confirmed ? '#f7931a' : '#3b82f6'} strokeWidth="2" />
        <text x="240" y="164" textAnchor="middle" fill={confirmed ? '#f7931a' : '#3b82f6'} fontSize="9" fontFamily="monospace">root</text>
      </svg>

      {confirmed && (
        <div className="s5-btc-block confirmed">
          <div className="s5-btc-icon">₿</div>
          <div className="s5-btc-height">
            Bitcoin block #{confirmed.block_height?.toLocaleString() ?? '…'}
          </div>
          <div className="s5-btc-label">Merkle root anchored — permanently recorded</div>
          {confirmed.head_hash && (
            <div className="s5-btc-hash">{fp(confirmed.head_hash)}</div>
          )}
        </div>
      )}

      {pending && !confirmed && (
        <div className="s5-btc-block pending">
          <div className="s5-btc-icon">₿</div>
          <div className="s5-btc-height">Pending confirmation…</div>
          <div className="s5-btc-label">Merkle root submitted to Bitcoin calendar</div>
        </div>
      )}

      {!hasAnchor && (
        <div>
          <p className="s5-pre-note">
            The chain's Merkle root will be published to the Bitcoin blockchain.
            Once confirmed in a block, no authority can alter these records without it being detectable.
          </p>
          <button className="btn-primary cta" onClick={onAnchor} disabled={busy || leaves.length === 0}>
            {busy ? 'Anchoring…' : '⚓ Anchor to Bitcoin'}
          </button>
        </div>
      )}

      {confirmed && (
        <p className="s5-confirmed-note">
          This chain's state is permanently recorded in Bitcoin block #{confirmed.block_height?.toLocaleString()}.
          No one can alter these records without it being detectable — no central authority required.
        </p>
      )}
    </div>
  )
}
