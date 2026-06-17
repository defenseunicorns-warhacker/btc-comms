// Turn a raw ledger payload into one plain-English line a non-engineer reads.
const pct = (x) => (x == null ? '?' : Math.round(x * 100) + '%')

export function humanize(entry) {
  if (entry.seq === 0) {
    const p = entry.payload
    if (p && typeof p === 'object' && p.rebaselined) {
      return `Re-baselined chain — continues from checkpoint #${p.recovered_from_checkpoint_seq}` +
        (p.bitcoin_block_height ? ` (Bitcoin block ${p.bitcoin_block_height.toLocaleString()})` : '') +
        '; prior chain sealed as evidence'
    }
    return 'Genesis — start of the record'
  }
  const p = entry.payload
  if (typeof p !== 'object' || p === null) return String(p).slice(0, 80)
  const t = p.type || p.event_type || p.event || p.action
  switch (t) {
    case 'sensor_ping':
      return `Sensor ${p.sensor_id ?? ''} — azimuth ${p.azimuth ?? '?'}°, range ${p.range_m ?? '?'} m`
    case 'threat_detected':
      return `Threat: ${p.class ?? '?'} at ${p.bearing ?? '?'}° — ${pct(p.confidence)} confidence`
    case 'route_computed':
      return `Route computed — ${p.waypoints ?? '?'} waypoints, fuel ${Math.round(p.fuel_pct ?? 0)}%`
    case 'roe_decision':
      return `Engagement: ${p.final_action ?? '?'} — ` +
        (p.human_authorized
          ? `human authorized (${p.operator_id ?? '?'})`
          : 'NO human in the loop')
    case 'TAMPERED':
      return '⚠ Forged content — injected by adversary'
    default:
      return t ? String(t) : JSON.stringify(p).slice(0, 80)
  }
}

// Short visual fingerprint instead of full hex.
export function fp(hash) {
  if (!hash) return ''
  return hash.slice(0, 8) + '…' + hash.slice(-6)
}

// A short type label for log rows / filters.
export function eventKind(entry) {
  if (entry.seq === 0) return 'Genesis'
  const p = entry.payload
  const t = (typeof p === 'object' && p) ? (p.type || p.event_type || p.event || p.action) : null
  switch (t) {
    case 'sensor_ping':     return 'Sensor ping'
    case 'threat_detected': return 'Threat detection'
    case 'route_computed':  return 'Route plan'
    case 'roe_decision':    return 'ROE / engagement'
    case 'TAMPERED':        return 'Tampered'
    default:                return t || 'Event'
  }
}

// HH:MM:SS from an ISO timestamp.
export function shortTime(ts) {
  if (!ts) return '—'
  const m = /T(\d{2}:\d{2}:\d{2})/.exec(ts)
  return m ? m[1] : String(ts).slice(0, 19)
}
