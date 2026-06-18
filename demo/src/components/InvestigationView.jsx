import { useMemo, useState } from 'react'
import { AGENTS, INCIDENT } from '../scenario'
import { humanize, eventKind, shortTime, fp } from '../humanize'

// JAG forensic view: an investigator locates the disputed record, confirms the
// whole chain is intact, then generates a selective-disclosure proof that holds
// up on its own — without declassifying the surrounding operational record.
const STATUS_LABEL = { tampered: 'ALTERED', invalidated: 'INVALIDATED', authentic: 'AUTHENTIC', unknown: 'UNVERIFIED' }

export default function InvestigationView({
  entries, verify, anchors, brokenAt, confirmedThrough,
  selectedSeq, onSelectSeq, onVerify, onProof,
}) {
  const [agentFilter, setAgentFilter] = useState('all')
  const [q, setQ] = useState('')

  const recStatus = (seq) => {
    if (brokenAt == null) return verify?.ok ? 'authentic' : 'unknown'
    if (seq === brokenAt) return 'tampered'
    if (seq > brokenAt) return 'invalidated'
    return 'authentic'
  }

  const rows = useMemo(() => {
    const term = q.trim().toLowerCase()
    return [...entries]
      .filter((e) => e.seq !== 0)
      .sort((a, b) => b.seq - a.seq)
      .filter((e) => agentFilter === 'all' || e.source_id === agentFilter)
      .filter((e) => {
        if (!term) return true
        const hay = `#${e.seq} ${AGENTS[e.source_id]?.label || e.source_id} ${eventKind(e)} ${humanize(e)}`.toLowerCase()
        return hay.includes(term)
      })
  }, [entries, agentFilter, q])

  const selected = entries.find((e) => e.seq === selectedSeq) || null
  const confirmedAnchor = anchors.find((a) => a.status === 'confirmed')

  return (
    <div className="investigate">
      <div className="case-strip">{INCIDENT.classification}</div>
      <div className="case-header">
        <div>
          <div className="case-op">{INCIDENT.operation}</div>
          <div className="case-ref">Incident {INCIDENT.ref} · shoot-down review</div>
        </div>
        <div className="case-meta">
          {confirmedAnchor
            ? <>Ledger anchored to Bitcoin through record #{confirmedAnchor.head_seq}
                {confirmedAnchor.block_height ? ` · block ${confirmedAnchor.block_height.toLocaleString()}` : ''}</>
            : 'Ledger not yet anchored'}
        </div>
      </div>

      <div className="invest-body">
        {/* ── Event log: find the disputed record ── */}
        <div className="log-panel">
          <div className="log-filters">
            <select value={agentFilter} onChange={(e) => setAgentFilter(e.target.value)}>
              <option value="all">All agents</option>
              {Object.entries(AGENTS).map(([id, m]) => <option key={id} value={id}>{m.label}</option>)}
            </select>
            <input
              type="text" placeholder="Search the record…"
              value={q} onChange={(e) => setQ(e.target.value)}
            />
          </div>

          <div className="log-list">
            {rows.length === 0 && <div className="log-empty">No records. Stage the engagement from the simulation console.</div>}
            {rows.map((e) => {
              const st = recStatus(e.seq)
              const agent = AGENTS[e.source_id]
              return (
                <button
                  key={e.seq}
                  className={`log-row ${selectedSeq === e.seq ? 'sel' : ''} st-${st}`}
                  onClick={() => onSelectSeq(e.seq)}
                  style={agent ? { '--src-accent': agent.accent } : undefined}
                >
                  <span className="lr-seq">#{e.seq}</span>
                  <span className="lr-time">{shortTime(e.timestamp)}</span>
                  <span className="lr-agent">{agent?.label || e.source_id}</span>
                  <span className="lr-kind">{eventKind(e)}</span>
                  <span className={`lr-badge st-${st}`}>{STATUS_LABEL[st]}</span>
                </button>
              )
            })}
          </div>
        </div>

        {/* ── Detail + audit actions: prove it ── */}
        <div className="detail-panel">
          {!selected ? (
            <div className="detail-empty">
              <div className="de-icon">⚖</div>
              Select a record to examine its contents, cryptographic lineage, and proof.
            </div>
          ) : (
            <RecordDetail
              entry={selected}
              status={recStatus(selected.seq)}
              verify={verify}
              brokenAt={brokenAt}
              onVerify={onVerify}
              onProof={() => onProof(selected.seq)}
            />
          )}
        </div>
      </div>
    </div>
  )
}

function RecordDetail({ entry, status, verify, brokenAt, onVerify, onProof }) {
  const agent = AGENTS[entry.source_id]
  const p = entry.payload && typeof entry.payload === 'object' ? entry.payload : {}
  const isROE = p.type === 'roe_decision'
  const noHuman = isROE && p.human_authorized === false

  return (
    <div className="detail">
      <div className="detail-head">
        <div>
          <span className="dh-seq">RECORD #{entry.seq}</span>
          <span className="dh-agent" style={agent ? { color: agent.accent } : undefined}>
            {agent?.label || entry.source_id}
          </span>
        </div>
        <span className={`rec-badge st-${status}`}>{STATUS_LABEL[status]}</span>
      </div>
      <div className="detail-time">Recorded {shortTime(entry.timestamp)} UTC</div>

      {noHuman && (
        <div className="callout warn">
          ⚠ Autonomous engagement — <strong>no human authorization</strong> recorded for this decision.
        </div>
      )}
      {status === 'tampered' && (
        <div className="callout bad">
          ✕ This record's content no longer matches its stored fingerprint — it was altered after the fact.
        </div>
      )}
      {status === 'invalidated' && (
        <div className="callout bad">
          ✕ A record earlier in the chain (#{brokenAt}) was altered, so this record's lineage can no longer be trusted.
        </div>
      )}

      <div className="detail-section">Decision content</div>
      <div className="payload-grid">
        {Object.entries(p).map(([k, v]) => (
          <div className="pg-row" key={k}>
            <span className="pg-k">{k}</span>
            <span className={`pg-v ${k === 'human_authorized' ? (v ? 'good' : 'bad') : ''}`}>
              {String(v)}
            </span>
          </div>
        ))}
      </div>

      <div className="detail-section">Cryptographic lineage</div>
      <div className="kv"><span className="k">Entry fingerprint</span><span className="v">{fp(entry.entry_hash)}</span></div>
      <div className="kv"><span className="k">Chained from</span><span className="v">{fp(entry.prev_hash)}</span></div>
      <div className="kv"><span className="k">Payload hash</span><span className="v">{fp(entry.payload_hash)}</span></div>
      <div className="kv"><span className="k">Signature</span><span className="v">{entry.signature ? 'present · Ed25519' : 'unsigned (demo)'}</span></div>

      <div className="detail-section">Audit actions</div>
      <div className="audit-actions">
        <button className="btn btn-primary sm" onClick={onVerify}>Verify full chain integrity</button>
        <button className="btn btn-light sm" onClick={onProof}>Generate court-admissible proof</button>
      </div>

      {verify && (
        <div className={`audit-result ${verify.ok ? 'ok' : 'bad'}`}>
          {verify.ok
            ? <>✓ Chain intact — all {verify.verified_entries} records authentic{verify.externally_anchored_through != null ? `, anchored in Bitcoin through #${verify.externally_anchored_through}` : ''}.</>
            : <>✕ verify() identifies record #{verify.broken_at} as the first altered entry — {verify.reason || 'integrity check failed'}.</>}
        </div>
      )}
    </div>
  )
}
