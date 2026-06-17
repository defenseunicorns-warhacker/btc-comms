// The scripted counter-UAS engagement from docs/PITCH.md.
//
// We POST these to the REAL recorder in order, so genesis is seq 0 and these
// become seq 1..9. The damning record — an autonomous ENGAGE with no human in
// the loop — is deliberately placed at SEQ 7 to match the pitch narrative
// ("broken_at: 7"). Nothing here is faked: verify() runs against the live
// cryptographic engine.

export const AGENTS = {
  'sensor-fusion':      { label: 'Sensor Fusion',      accent: 'var(--c-sensor)' },
  'threat-classifier':  { label: 'Threat Classifier',  accent: 'var(--c-threat)' },
  'nav-planner':        { label: 'Nav Planner',        accent: 'var(--c-nav)' },
  'engagement-planner': { label: 'Engagement Planner', accent: 'var(--c-engage)' },
}

// seq is the sequence number each event WILL receive (genesis is 0).
export const SCRIPT = [
  { seq: 1, agent: 'sensor-fusion', payload: {
      type: 'sensor_ping', sensor_id: 'FLIR-7', azimuth: 142, range_m: 1420 },
    status: 'Contact — FLIR-7, az 142°' },

  { seq: 2, agent: 'threat-classifier', payload: {
      type: 'threat_detected', class: 'UAS', confidence: 0.71, bearing: 142,
      range_m: 1420, sensor_ids: ['FLIR-7', 'RADAR-2'] },
    status: 'UAS — 71% confidence' },

  { seq: 3, agent: 'nav-planner', payload: {
      type: 'route_computed', waypoints: 4, fuel_pct: 88,
      threat_avoidance_active: true },
    status: 'Intercept route · 4 waypoints' },

  { seq: 4, agent: 'sensor-fusion', payload: {
      type: 'sensor_ping', sensor_id: 'FLIR-7', azimuth: 139, range_m: 980 },
    status: 'Track closing — 980 m' },

  { seq: 5, agent: 'threat-classifier', payload: {
      type: 'threat_detected', class: 'UAS', confidence: 0.69, bearing: 139,
      range_m: 980, sensor_ids: ['FLIR-7'] },
    status: 'UAS persists — 69% confidence' },

  { seq: 6, agent: 'nav-planner', payload: {
      type: 'route_computed', waypoints: 2, fuel_pct: 84,
      threat_avoidance_active: false },
    status: 'Closing route · 2 waypoints' },

  // ── THE DAMNING RECORD (seq 7) ────────────────────────────────────────────
  // ROE required human authorization above a confidence/CDE threshold the
  // system bypassed. This decision was made with NO human in the loop.
  { seq: 7, agent: 'engagement-planner', damning: true, payload: {
      type: 'roe_decision',
      decision_type: 'ENGAGE_READY',
      final_action: 'ENGAGE_READY',
      human_authorized: false,
      operator_id: null,
      target_id: 'T-0007',
      ai_confidence: 0.71,
      roe_reference: 'ROE-ALPHA-7',
      within_envelope: true,
      collateral_damage_estimate: 'LOW',
      time_to_authorization_ms: 0 },
    status: 'ENGAGE_READY — UNATTENDED' },

  { seq: 8, agent: 'sensor-fusion', payload: {
      type: 'sensor_ping', sensor_id: 'FLIR-7', azimuth: 137, range_m: 410 },
    status: 'Post-engagement — 410 m' },

  { seq: 9, agent: 'nav-planner', payload: {
      type: 'route_computed', waypoints: 5, fuel_pct: 79,
      threat_avoidance_active: false },
    status: 'Return-to-base route' },
]

export const DAMNING_SEQ = 7

// What a compromised agent rewrites the record to: flip the autonomous engage
// into a "human-authorized" one and bump the confidence to look defensible.
export const FORGED_PAYLOAD = {
  type: 'roe_decision',
  decision_type: 'ENGAGE_READY',
  final_action: 'ENGAGE_READY',
  human_authorized: true,
  operator_id: 'OP-414',
  target_id: 'T-0007',
  ai_confidence: 0.95,
  roe_reference: 'ROE-ALPHA-7',
  within_envelope: true,
  collateral_damage_estimate: 'LOW',
  time_to_authorization_ms: 1840,
}

// Scenario framing for the investigation view.
export const INCIDENT = {
  operation: 'Counter-UAS · OP IRON DOME',
  ref: 'INC-2026-0617-A',
  classification: 'UNCLASSIFIED // DEMO',
}
