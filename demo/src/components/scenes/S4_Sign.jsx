import { AGENTS, DAMNING_SEQ } from '../../scenario'
import { humanize, fp } from '../../humanize'

export default function S4_Sign({ entries, busy, forgeResult, onForge }) {
  const entry = entries.find((e) => e.seq === DAMNING_SEQ) || entries.find((e) => e.seq > 0 && e.signature)
  const agent = entry ? AGENTS[entry.source_id] : null

  if (!entry) {
    return <div className="s4-empty">Run the engagement first (Scene 1) to see signed entries here.</div>
  }

  return (
    <div className="s4-wrap">
      <div>
        <div className="s2-label">Entry #{entry.seq}</div>
        <div className="s4-entry">
          <div className="s4-entry-top">
            <span className="s3-seq">#{entry.seq}</span>
            <span className="s3-agent" style={{ color: agent?.accent }}>
              {agent?.label || entry.source_id}
            </span>
          </div>
          <div className="s4-entry-desc">{humanize(entry)}</div>
          {entry.entry_hash && (
            <div className="s4-entry-fp">{fp(entry.entry_hash)}</div>
          )}
        </div>

        <div style={{ marginTop: 24 }}>
          <p className="s4-caption">
            The {agent?.label || entry.source_id} signed this record with its private key.
            The signature binds the agent's identity to the exact payload — you cannot change who said what.
          </p>
        </div>

        <div className="s4-forge">
          {!forgeResult && !busy && (
            <>
              <button className="btn-danger cta" onClick={onForge}>
                🔓 Try to post a forged entry (impersonate another agent)
              </button>
              <p className="s4-forge-sub">
                Sends a real request to the recorder, signed with the wrong agent's key.
              </p>
            </>
          )}

          {busy && !forgeResult && (
            <div className="forge-log">
              <div className="forge-req">→ POST /demo/impersonate</div>
              <div className="forge-pending">submitting forged signature to the recorder…</div>
            </div>
          )}

          {forgeResult && forgeResult.rejected && (
            <>
              <div className="forge-log">
                <div className="forge-req">→ POST /demo/impersonate</div>
                <div className="forge-req">&nbsp;&nbsp;{forgeResult.attacker} signs a record claiming to be {forgeResult.victim}</div>
                <div className="forge-res">← REJECTED by recorder · signature invalid</div>
              </div>
              <div className="s4-rejection">
                <div className="s4-rejection-title">✕ Forged attribution rejected</div>
                {forgeResult.reason} The recorder ran the same Ed25519 check it runs on every ingest —
                the attacker's key isn't enrolled to the victim's identity, so the signature fails.
                Attribution is cryptographic, not a label you can overwrite.
              </div>
            </>
          )}

          {forgeResult && !forgeResult.rejected && (
            <div className="s4-rejection">
              <div className="s4-rejection-title">⚠ Forge attempt blocked</div>
              The endpoint requires DEMO_MODE and a valid enrolled keypair. Forgery is not possible.
            </div>
          )}
        </div>
      </div>

      <div>
        <div className="s2-label">Cryptographic lineage</div>
        <div className="s4-crypto">
          <div className="s4-crypto-row">
            <span className="s4-crypto-label">Source</span>
            <span className="s4-crypto-val">{entry.source_id}</span>
          </div>
          {entry.key_id && (
            <div className="s4-crypto-row">
              <span className="s4-crypto-label">Key ID</span>
              <span className="s4-crypto-val">{entry.key_id}</span>
            </div>
          )}
          <div className="s4-crypto-row">
            <span className="s4-crypto-label">Entry hash</span>
            <span className="s4-crypto-val">{entry.entry_hash || '—'}</span>
          </div>
          <div className="s4-crypto-row">
            <span className="s4-crypto-label">Prev hash</span>
            <span className="s4-crypto-val">{entry.prev_hash || '—'}</span>
          </div>
          <div className="s4-crypto-row">
            <span className="s4-crypto-label">Signature (Ed25519)</span>
            <span className="s4-crypto-val">
              {entry.signature
                ? entry.signature.slice(0, 48) + '…'
                : <span style={{ color: 'var(--muted)', fontFamily: 'var(--sans)' }}>unsigned</span>}
            </span>
          </div>
        </div>
      </div>
    </div>
  )
}
