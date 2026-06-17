import { fp } from '../humanize'

// Selective-disclosure proof for a single record: prove ONE entry is authentic
// (or catch that it was tampered) without revealing any other record.
export default function ProofModal({ result, onClose }) {
  if (!result) return null
  const { entry, proof, anchor, valid, payload_hash_ok, root_matches_anchor } = result
  const steps = proof?.path?.length ?? 0

  return (
    <div className="overlay" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal">
        <button className="close" onClick={onClose}>✕</button>
        <h3>◈ Proof for record #{entry.seq}</h3>

        <div className={`verdict ${valid ? 'ok' : 'bad'}`}>
          {valid ? '✓ AUTHENTIC' : '✕ TAMPERED'}
          <p>
            {valid
              ? `This single record is provably authentic. An investigator can verify it from just the entry, a ${steps}-step proof, and the Bitcoin-anchored fingerprint — without seeing any other record.`
              : payload_hash_ok === false
                ? 'The content no longer matches the fingerprint stored for this record. Every record built on top of it is now invalid too.'
                : 'This record does not match the authenticated history.'}
          </p>
        </div>

        <div className="kv"><span className="k">Source</span><span className="v">{entry.source_id}</span></div>
        <div className="kv"><span className="k">Fingerprint</span><span className="v">{fp(entry.entry_hash)}</span></div>
        <div className="kv"><span className="k">Proof path</span><span className="v">{steps} hash steps</span></div>
        {anchor && (
          <div className="kv">
            <span className="k">Bitcoin anchor</span>
            <span className="v">
              {anchor.status}{root_matches_anchor === true ? ' · root ✓'
                : root_matches_anchor === false ? ' · root ✕' : ''}
            </span>
          </div>
        )}
        <p style={{ color: 'var(--muted)', fontSize: 12, marginTop: 14 }}>
          Selective disclosure: a verifier needs only this entry + the proof path +
          the anchored fingerprint. Nothing else is declassified.
        </p>
      </div>
    </div>
  )
}
