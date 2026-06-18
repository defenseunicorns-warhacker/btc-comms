// Thin client over the STABLE recorder. URLs are relative so the Vite dev
// proxy (or the recorder serving the built bundle) routes them.

async function req(method, path, body) {
  const opts = { method, headers: { 'Content-Type': 'application/json' } }
  if (body) opts.body = JSON.stringify(body)
  const r = await fetch(path, opts)
  if (!r.ok) {
    const err = await r.json().catch(() => ({ detail: r.statusText }))
    throw new Error(err.detail || r.statusText)
  }
  return r.json()
}

export const api = {
  info: () => req('GET', '/info'),
  verify: () => req('GET', '/verify'),
  anchors: () => req('GET', '/anchors'),
  proof: (seq) => req('GET', `/entries/${seq}/proof`),
  // DEMO append: signed server-side with the agent's enrolled key so events are
  // attributable (the production path is each agent signing locally).
  appendEvent: (source_id, payload) => req('POST', '/demo/append', { source_id, payload }),
  anchorNow: () => req('POST', '/anchor/now'),
  upgradeAnchors: () => req('POST', '/anchor/upgrade'),
  // DEMO-only endpoints (require DEMO_MODE on the recorder):
  tamper: (seq, payload) =>
    req('POST', '/tamper', { seq, field: 'payload', new_value: JSON.stringify(payload) }),
  rebaseline: (info) => req('POST', '/demo/rebaseline', info),
  impersonate: () => req('POST', '/demo/impersonate'),
  reset: () => req('POST', '/demo/reset'),
}
