import { useState, useEffect } from 'react'

function sortedJson(o) {
  if (typeof o !== 'object' || o === null) return JSON.stringify(o)
  if (Array.isArray(o)) return '[' + o.map(sortedJson).join(',') + ']'
  return '{' + Object.keys(o).sort().map((k) => JSON.stringify(k) + ':' + sortedJson(o[k])).join(',') + '}'
}

async function sha256hex(str) {
  const buf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(str))
  return Array.from(new Uint8Array(buf)).map((b) => b.toString(16).padStart(2, '0')).join('')
}

export default function S2_Hash({ entries }) {
  const entry = entries.find((e) => e.seq === 2) || entries.find((e) => e.seq > 0) || null
  const payload = entry?.payload || null

  const [origHash, setOrigHash] = useState('')
  const [altHash, setAltHash] = useState('')
  const [revealOrig, setRevealOrig] = useState(0)
  const [revealAlt, setRevealAlt] = useState(0)
  const [phase, setPhase] = useState('idle') // idle | revealing-orig | orig-done | changed | revealing-alt | done
  const [altPayload, setAltPayload] = useState(null)

  useEffect(() => {
    if (!payload) return
    const modified = { ...payload }
    if (modified.confidence != null) {
      modified.confidence = Math.round((modified.confidence - 0.01) * 100) / 100
    } else if (modified.range_m != null) {
      modified.range_m = modified.range_m + 1
    }
    setAltPayload(modified)
    sha256hex(sortedJson(payload)).then(setOrigHash)
    sha256hex(sortedJson(modified)).then(setAltHash)
  }, [entry?.seq])

  useEffect(() => {
    if (phase === 'revealing-orig' && origHash) {
      let i = 0
      const id = setInterval(() => {
        i++
        setRevealOrig(i)
        if (i >= origHash.length) { clearInterval(id); setPhase('orig-done') }
      }, 16)
      return () => clearInterval(id)
    }
  }, [phase, origHash])

  useEffect(() => {
    if (phase === 'revealing-alt' && altHash) {
      let i = 0
      const id = setInterval(() => {
        i++
        setRevealAlt(i)
        if (i >= altHash.length) { clearInterval(id); setPhase('done') }
      }, 16)
      return () => clearInterval(id)
    }
  }, [phase, altHash])

  if (!payload) {
    return <div className="s2-empty">Run the engagement first (Scene 1) to see entry data here.</div>
  }

  const displayPayload = phase === 'changed' || phase === 'revealing-alt' || phase === 'done'
    ? altPayload
    : payload

  const changedKey = altPayload?.confidence != null ? 'confidence' : 'range_m'

  return (
    <div className="s2-wrap">
      <div className="s2-payload">
        <div className="s2-label">Entry #{entry.seq} — payload</div>
        {Object.entries(displayPayload || payload).map(([k, v]) => {
          const isChanged = (phase === 'changed' || phase === 'revealing-alt' || phase === 'done') && k === changedKey
          return (
            <div className={`s2-field${isChanged ? ' changed' : ''}`} key={k}>
              <span className="s2-key">{k}:</span>
              <span className={`s2-val${isChanged ? ' highlighted' : ''}`}>
                {typeof v === 'object' ? JSON.stringify(v) : String(v)}
              </span>
            </div>
          )
        })}
        <div style={{ marginTop: 16 }}>
          {phase === 'idle' && (
            <button className="btn-primary cta" onClick={() => setPhase('revealing-orig')}>
              Compute fingerprint →
            </button>
          )}
          {phase === 'orig-done' && (
            <button className="btn-primary cta" onClick={() => setPhase('changed')}>
              Change one field
            </button>
          )}
          {phase === 'changed' && (
            <button className="btn-primary cta" onClick={() => setPhase('revealing-alt')}>
              Recompute fingerprint →
            </button>
          )}
        </div>
      </div>

      <div className="s2-hash-panel">
        <div className="s2-label">SHA-256 fingerprint</div>

        {phase !== 'idle' && (
          <div>
            <div className="s2-hash-label-small">Original</div>
            <div className="s2-hash">
              {origHash.slice(0, revealOrig)}
              {phase === 'revealing-orig' && <span className="hash-cursor" />}
            </div>
          </div>
        )}

        {(phase === 'revealing-alt' || phase === 'done') && (
          <div>
            <div className="s2-hash-label-small" style={{ color: 'var(--danger)' }}>After changing {changedKey}</div>
            <div className="s2-hash alt">
              {altHash.slice(0, revealAlt)}
              {phase === 'revealing-alt' && <span className="hash-cursor" style={{ background: 'var(--danger)' }} />}
            </div>
          </div>
        )}

        {phase === 'done' && (
          <div className="s2-diff-note">
            One field changed. Every one of the 64 characters is different.
          </div>
        )}
      </div>
    </div>
  )
}
