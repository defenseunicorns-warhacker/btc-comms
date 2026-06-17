import { useState } from 'react'

// The only place that injects activity into the recorder. Visually fenced off
// as a "simulation console" so the audience never mistakes it for part of the
// real STABLE product — these are the levers a presenter pulls to stage events.
export default function DemoControls({
  busy, hasRun, breached, lastAction,
  onRun, onTamper, onImpersonate, onReset,
}) {
  const [open, setOpen] = useState(true)

  return (
    <div className={`demo-dock ${open ? 'open' : 'closed'}`}>
      <button className="dock-toggle" onClick={() => setOpen((o) => !o)}>
        <span className="dock-badge">⚙ SIMULATION CONSOLE</span>
        <span className="dock-caret">{open ? '▾' : '▴'}</span>
      </button>

      {open && (
        <div className="dock-body">
          <div className="dock-group">
            <div className="dock-label">Operate</div>
            <button className="btn btn-primary sm" disabled={busy || hasRun} onClick={onRun}>
              ▶ Run counter-UAS engagement
            </button>
          </div>

          <div className="dock-group">
            <div className="dock-label">Adversary</div>
            <button className="btn btn-danger sm" disabled={busy || !hasRun || breached} onClick={onTamper}>
              ✎ Rewrite record #7
            </button>
            <button className="btn btn-ghost sm" disabled={busy} onClick={onImpersonate}>
              🎭 Forge an agent signature
            </button>
          </div>

          <div className="dock-group">
            <div className="dock-label">Stage</div>
            <button className="btn btn-ghost sm" disabled={busy} onClick={onReset}>↻ Reset ledger</button>
          </div>

          {lastAction && (
            <div className="dock-status">{busy ? '⋯' : '›'} {lastAction}</div>
          )}
        </div>
      )}
    </div>
  )
}
