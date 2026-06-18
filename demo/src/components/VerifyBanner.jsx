// Top-of-record status. Green when the chain verifies, red the instant any
// record is altered — naming the exact sequence number.
export default function VerifyBanner({ verify }) {
  if (!verify) {
    return <div className="banner wait"><span className="b-icon">○</span> Awaiting first verification…</div>
  }
  if (verify.ok) {
    return (
      <div className="banner ok">
        <span className="b-icon">✓</span>
        All {verify.verified_entries} records authentic &amp; unaltered
        {verify.externally_anchored_through != null && (
          <small>· anchored in Bitcoin through #{verify.externally_anchored_through}</small>
        )}
      </div>
    )
  }
  return (
    <div className="banner broken">
      <span className="b-icon">✕</span>
      Record #{verify.broken_at} was altered — caught exactly which one
      <small>· {verify.reason || 'integrity check failed'}</small>
    </div>
  )
}
