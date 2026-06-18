import { useEffect, useRef } from 'react'
import gsap from 'gsap'
import { AGENTS } from '../../scenario'
import { humanize, fp, shortTime, eventKind } from '../../humanize'

export default function S1_Stream({ entries, busy, onStart }) {
  const listRef = useRef(null)
  const endRef = useRef(null)
  const prevLen = useRef(0)

  const visible = entries.filter((e) => e.seq > 0)

  useEffect(() => {
    if (!listRef.current) return
    const cards = listRef.current.querySelectorAll('.entry-card')
    const newCards = Array.from(cards).slice(prevLen.current)
    if (newCards.length > 0) {
      gsap.fromTo(newCards,
        { x: 40, opacity: 0 },
        { x: 0, opacity: 1, duration: 0.35, stagger: 0.06, ease: 'power2.out' })
    }
    prevLen.current = cards.length
    // Keep the newest record (and the text under it) in view as the chain fills.
    endRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [visible.length])

  if (visible.length === 0) {
    return (
      <div className="s1-empty">
        <div className="s1-idle-ring" />
        <div className="s1-idle-text">No activity recorded yet.</div>
        <button className="btn-primary cta" onClick={onStart} disabled={busy}>
          {busy ? 'Recording…' : '▶ Record engagement'}
        </button>
      </div>
    )
  }

  return (
    <div>
      <div className="entry-list" ref={listRef}>
        {visible.map((e) => {
          const agent = AGENTS[e.source_id]
          const accent = agent?.accent || 'var(--accent)'
          return (
            <div className="entry-card" key={e.seq} style={{ '--src-accent': accent }}>
              <span className="ec-seq">#{e.seq}</span>
              <div className="ec-body">
                <div className="ec-top">
                  <span className="ec-type">{eventKind(e)}</span>
                  <span className="ec-agent">{agent?.label || e.source_id}</span>
                  <span className="ec-time">{shortTime(e.timestamp)}</span>
                </div>
                <div className="ec-desc">{humanize(e)}</div>
                {e.entry_hash && <div className="ec-hash">{fp(e.entry_hash)}</div>}
              </div>
            </div>
          )
        })}
      </div>
      {visible.length >= 9 && (
        <div className="s1-done">
          <span>✓</span>
          <span>{visible.length} decisions recorded — signed, chained, append-only.</span>
        </div>
      )}
      <div ref={endRef} />
    </div>
  )
}
