import { AGENTS } from '../scenario'

// The four AI agents. `states[source_id]` = { status, firing } as the scripted
// engagement drives them.
export default function AgentPanel({ states }) {
  return (
    <div className="agents">
      {Object.entries(AGENTS).map(([id, meta]) => {
        const s = states[id] || {}
        return (
          <div
            key={id}
            className={`agent ${s.firing ? 'firing' : ''}`}
            style={{ '--accent': meta.accent }}
          >
            <div className="a-name">{meta.label}</div>
            <div className={`a-status ${s.status ? '' : 'idle'}`}>
              {s.status || 'standby'}
            </div>
          </div>
        )
      })}
    </div>
  )
}
