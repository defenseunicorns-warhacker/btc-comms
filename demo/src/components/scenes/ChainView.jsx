import { AGENTS } from '../../scenario'
import { humanize, fp } from '../../humanize'

// Presentational hash-chain (records #5–9 with prev_hash connectors).
// Renders intact when brokenAt == null, and the break cascade when it's set.
// blockRefs (optional) is a ref whose .current is a { seq: el } registry the
// caller uses to drive GSAP on individual blocks.
export default function ChainView({ entries, brokenAt, blockRefs }) {
  const window5to9 = entries
    .filter((e) => e.seq >= 5 && e.seq <= 9)
    .sort((a, b) => a.seq - b.seq)

  const chain = window5to9.length === 0
    ? entries.filter((e) => e.seq > 0).slice(-5).sort((a, b) => a.seq - b.seq)
    : window5to9

  if (chain.length === 0) {
    return <div className="s3-empty">Run the engagement first (Scene 1) to populate the chain.</div>
  }

  return (
    <div className="s3-chain">
      {chain.map((e, i) => {
        const isTampered = brokenAt != null && e.seq === brokenAt
        const isBroken = brokenAt != null && e.seq > brokenAt
        const agent = AGENTS[e.source_id]
        const prevEntry = i > 0 ? chain[i - 1] : null

        return (
          <div key={e.seq}>
            {prevEntry && (
              <div className="s3-connector">
                <div className={`s3-line${isBroken || isTampered ? ' broken-link' : ''}`} />
                <span className={`s3-prev${isBroken || isTampered ? ' broken' : ''}`}>
                  {isBroken || isTampered
                    ? '✕ prev_hash mismatch'
                    : `prev: ${e.prev_hash ? e.prev_hash.slice(0, 12) : '…'}…`}
                </span>
              </div>
            )}
            <div
              ref={blockRefs ? (el) => (blockRefs.current[e.seq] = el) : undefined}
              className={`s3-block${isTampered ? ' tampered' : isBroken ? ' broken' : ''}`}
            >
              <div className="s3-block-top">
                <span className="s3-seq">#{e.seq}</span>
                <span className="s3-agent" style={{ color: agent?.accent }}>
                  {agent?.label || e.source_id}
                </span>
                {isTampered && <span className="s3-badge-tampered">ALTERED</span>}
                {isBroken && <span className="s3-badge-broken">INVALIDATED</span>}
              </div>
              <div className="s3-desc">{humanize(e)}</div>
              <div className={`s3-fp${isTampered || isBroken ? ' broken' : ''}`}>
                {fp(e.entry_hash)}
              </div>
              {isTampered && (
                <div className="s3-flag">⚠ Payload rewritten — fingerprint no longer matches</div>
              )}
              {isBroken && (
                <div className="s3-flag">✕ prev_hash points to a fingerprint that no longer exists</div>
              )}
            </div>
          </div>
        )
      })}
    </div>
  )
}
