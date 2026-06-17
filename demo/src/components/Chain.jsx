import { forwardRef, useImperativeHandle, useRef } from 'react'
import gsap from 'gsap'
import { AGENTS, DAMNING_SEQ } from '../scenario'
import { humanize, fp } from '../humanize'

// The vertical hash chain — the centerpiece. Each block links to the one above
// via a glowing spine. When a record is tampered, the spine shatters red from
// that point down, making "break one, break all after it" visible.
const Chain = forwardRef(function Chain(
  { entries, brokenAt, confirmedThrough, onSelect }, ref) {

  const blocks = useRef({})   // seq -> block element
  const links = useRef({})    // seq -> link wrapper element

  useImperativeHandle(ref, () => ({
    // Play the shatter sequence anchored at `seq`. React sets the persistent
    // broken styling; GSAP adds the propagating flourish on top.
    playTamper(seq) {
      const block = blocks.current[seq]
      if (block) {
        const desc = block.querySelector('.desc')
        gsap.timeline()
          .to(block, { x: -7, duration: 0.05, repeat: 7, yoyo: true })
          .to(desc, { opacity: 0, duration: 0.13 }, 0)
          .to(desc, { opacity: 1, duration: 0.18 }, 0.18)
      }
      // Propagate the break downward through every later record.
      const downstream = entries
        .filter((e) => e.seq >= seq)
        .map((e) => links.current[e.seq])
        .filter(Boolean)
      const nodes = downstream.map((l) => l.querySelector('.node'))
      gsap.fromTo(nodes,
        { scale: 1 },
        { scale: 1.55, duration: 0.16, stagger: 0.06, yoyo: true, repeat: 1,
          ease: 'power2.out', delay: 0.15 })
    },
  }), [entries])

  if (entries.length <= 1) {
    const g = entries[0]
    const rebased = g && g.payload && typeof g.payload === 'object' && g.payload.rebaselined
    return (
      <div className="chain-wrap">
        {rebased ? (
          <div className="rebaseline-card">
            <div className="rb-badge">↻ Chain re-baselined</div>
            <p>
              Fresh chain continuing from clean checkpoint #{g.payload.recovered_from_checkpoint_seq}
              {g.payload.bitcoin_block_height ? <> · Bitcoin block {g.payload.bitcoin_block_height.toLocaleString()}</> : null}.
            </p>
            <p className="rb-sub">
              The compromised chain (broke at #{g.payload.prior_chain_break?.broken_at} — {g.payload.prior_chain_break?.reason}) is sealed as evidence. New decisions chain and anchor forward from here.
            </p>
          </div>
        ) : (
          <div className="chain-empty">
            The record is empty.<br />Start the engagement to watch it fill.
          </div>
        )}
      </div>
    )
  }

  const ordered = [...entries].sort((a, b) => b.seq - a.seq) // newest on top

  return (
    <div className="chain-wrap">
      <div className="chain">
        {ordered.map((e) => {
          const broken = brokenAt != null && e.seq >= brokenAt
          const isTampered = brokenAt != null && e.seq === brokenAt
          const isGenesis = e.seq === 0
          const isDamning = e.seq === DAMNING_SEQ
          const agent = AGENTS[e.source_id]
          // Keep the anchor mark on records locked in BEFORE the tamper — it
          // shows the true history was in Bitcoin before the forgery.
          const anchored = confirmedThrough >= e.seq && (brokenAt == null || e.seq < brokenAt)

          const cls = [
            'link',
            broken ? 'broken-spine' : '',
          ].join(' ')

          const blockCls = [
            'block', 'block-anim',
            isGenesis ? 'genesis' : '',
            isDamning && brokenAt == null ? 'damning' : '',
            isTampered ? 'tampered' : (broken ? 'downstream' : ''),
          ].join(' ')

          return (
            <div className={cls} key={e.seq} ref={(el) => (links.current[e.seq] = el)}>
              <span className="node" />
              <div
                className={blockCls}
                ref={(el) => (blocks.current[e.seq] = el)}
                onClick={() => !isGenesis && onSelect?.(e.seq)}
                style={agent ? { '--src-accent': agent.accent } : undefined}
              >
                <div className="block-top">
                  <span className="seq">#{e.seq}</span>
                  <span className="src">{isGenesis ? 'system' : (agent?.label || e.source_id)}</span>
                  {anchored && <span className="anchored">⚓ in Bitcoin</span>}
                </div>
                <div className="desc">{humanize(e)}</div>
                {isTampered && (
                  <span className="flag warn">⚠ content no longer matches its fingerprint</span>
                )}
                {!isGenesis && !broken && <div className="fingerprint">{fp(e.entry_hash)}</div>}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
})

export default Chain
