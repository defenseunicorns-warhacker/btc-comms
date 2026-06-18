import { useEffect, useRef, useState, useCallback } from 'react'

// Subscribes to the recorder's SSE stream and exposes live ledger state:
//   entries  — full chain, oldest-first (index 0 = genesis)
//   anchors  — Bitcoin anchors with pending/confirmed status
//   verify   — latest verify() result ({ ok, broken_at, reason, ... })
//   connected — SSE link status
export function useStable() {
  const [entries, setEntries] = useState([])
  const [anchors, setAnchors] = useState([])
  const [verify, setVerify] = useState(null)
  const [connected, setConnected] = useState(false)
  const esRef = useRef(null)

  const connect = useCallback(() => {
    if (esRef.current) esRef.current.close()
    const es = new EventSource('/stream')
    esRef.current = es

    es.onopen = () => setConnected(true)
    es.onerror = () => {
      setConnected(false)
      es.close()
      esRef.current = null
      setTimeout(connect, 2500)
    }

    es.addEventListener('snapshot', (e) => {
      const d = JSON.parse(e.data)
      setEntries(d.entries || [])
      setAnchors(d.anchors || [])
      // Populate the banner on first connect (and on reconnect) so it never
      // sticks on "awaiting". /verify also re-broadcasts to all subscribers.
      fetch('/verify').then((r) => r.json()).then(setVerify).catch(() => {})
    })
    es.addEventListener('entry', (e) => {
      const entry = JSON.parse(e.data)
      setEntries((prev) =>
        prev.some((x) => x.seq === entry.seq) ? prev : [...prev, entry])
    })
    es.addEventListener('anchor', (e) => {
      const a = JSON.parse(e.data)
      setAnchors((prev) => {
        const i = prev.findIndex((x) => x.id === a.id)
        if (i < 0) return [...prev, a]
        const next = [...prev]
        next[i] = a
        return next
      })
    })
    es.addEventListener('tamper', (e) => {
      // The recorder mutated an entry in place; pull the fresh row so the UI
      // shows the forged content.
      const { seq } = JSON.parse(e.data)
      fetch(`/entries?limit=1000`).then((r) => r.json()).then((all) => {
        const fresh = all.find((x) => x.seq === seq)
        if (fresh) setEntries((prev) => prev.map((x) => (x.seq === seq ? fresh : x)))
      }).catch(() => {})
    })
    es.addEventListener('verify', (e) => setVerify(JSON.parse(e.data)))
    es.addEventListener('reset', () => {
      setAnchors([])
      setVerify(null)
      fetch('/entries?limit=1000').then((r) => r.json())
        .then((all) => setEntries(all))
        .catch(() => setEntries([]))
    })
  }, [])

  useEffect(() => {
    connect()
    return () => { if (esRef.current) esRef.current.close() }
  }, [connect])

  // Latest confirmed anchor's covered seq, for the "anchored through" marker.
  const confirmedThrough = anchors.reduce(
    (m, a) => (a.status === 'confirmed' ? Math.max(m, a.head_seq) : m), -1)

  return { entries, anchors, verify, connected, confirmedThrough, setVerify }
}
