"""
demo_agent.py — simulates a multi-component AI defense system.

Demonstrates all production features:
  1. Per-agent Ed25519 signing (every event is cryptographically attributed)
  2. DDIL buffering (events survive network outages)
  3. ROE structured schema (JAG-interpretable decision records)
  4. @audit_log decorator (wraps existing functions with zero code changes)
  5. Logging handler (2-line integration with standard Python logging)

Run alongside the accountability layer:
    DEMO_MODE=true MOCK_ANCHOR=true uvicorn src.api:app   # Terminal 1
    python3 examples/demo_agent.py                         # Terminal 2

Simulate a network outage:
    Kill the server, watch "DDIL buffer" count climb in the terminal,
    restart the server, watch buffered events flush automatically.
"""

import logging
import os
import random
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from adapters import LedgerClient, LedgerLogHandler, audit_log
from roe_schema import RoEDecision, RoEEngagementResult, build_roe_payload, build_result_payload

LEDGER_URL = os.getenv("LEDGER_URL", "http://localhost:8000")

# ---------------------------------------------------------------------------
# Set up one signed client per logical agent (separate keypairs = separate attribution)
# ---------------------------------------------------------------------------

threat_client  = LedgerClient(LEDGER_URL, source_id="threat-classifier")
engage_client  = LedgerClient(LEDGER_URL, source_id="engagement-planner")
nav_client     = LedgerClient(LEDGER_URL, source_id="nav-planner", async_mode=False)
sensor_client  = LedgerClient(LEDGER_URL, source_id="sensor-fusion")

# ---------------------------------------------------------------------------
# Integration 1: Python logging handler on the existing logger
# ---------------------------------------------------------------------------

logger = logging.getLogger("threat-classifier")
logger.setLevel(logging.DEBUG)
logger.addHandler(logging.StreamHandler(sys.stdout))
logger.addHandler(LedgerLogHandler("threat-classifier", LEDGER_URL))

# ---------------------------------------------------------------------------
# Integration 2: @audit_log on existing functions
# ---------------------------------------------------------------------------

@audit_log(threat_client, include_args=True, include_result=True)
def classify_threat(sensor_data: dict) -> dict:
    """Existing threat classification — not modified at all."""
    time.sleep(random.uniform(0.01, 0.04))
    confidence = random.uniform(0.55, 0.99)
    threat_class = random.choice(["UAS", "ground_vehicle", "personnel", "none"])
    if confidence > 0.92:
        logger.warning("High-confidence %s detected (%.2f)", threat_class, confidence)
    return {
        "class": threat_class,
        "confidence": round(confidence, 3),
        "bearing": random.randint(0, 359),
        "range_m": random.randint(200, 2000),
    }


@audit_log(engage_client, include_args=False, include_result=True)
def compute_engagement_envelope(threat: dict, platform_state: dict) -> dict:
    """Existing engagement geometry — args excluded (classified inputs)."""
    time.sleep(random.uniform(0.01, 0.03))
    in_envelope = threat["confidence"] > 0.75 and threat["range_m"] < 1500
    return {
        "within_envelope": in_envelope,
        "recommended_action": "ENGAGE_READY" if in_envelope and threat["confidence"] > 0.85 else "HOLD_FIRE",
        "time_to_intercept_s": round(random.uniform(8, 45), 1),
    }


# ---------------------------------------------------------------------------
# Integration 3: Direct structured ROE events (JAG-compliant)
# ---------------------------------------------------------------------------

def submit_roe_decision(threat: dict, envelope: dict, iteration: int) -> dict:
    """
    Emit a fully structured ROE decision event.
    This is what JAG / DCSA investigators need — not a free-form log line.
    """
    detection_time_ms = int(threat["confidence"] * 1000 + random.randint(500, 3000))
    operator_id = f"OP-{random.randint(100, 999)}"
    human_auth = envelope["recommended_action"] == "ENGAGE_READY" and random.random() > 0.25

    decision = RoEDecision(
        decision_type="ENGAGE_READY" if envelope["within_envelope"] else "HOLD_FIRE",
        human_authorized=human_auth,
        operator_id=operator_id if human_auth else "UNATTENDED",
        target_id=f"T-{iteration:04d}",
        ai_confidence=threat["confidence"],
        roe_reference=random.choice(["ROE-ALPHA-7", "ROE-BRAVO-2", "ROE-DELTA-1"]),
        information_state={
            "threat_class": threat["class"],
            "bearing": threat["bearing"],
            "range_m": threat["range_m"],
            "confidence": threat["confidence"],
            "sensor_ids": ["FLIR-7", "RADAR-2"],
        },
        time_to_authorization_ms=detection_time_ms,
        geo_location={
            "lat": round(34.0522 + random.uniform(-0.01, 0.01), 6),
            "lon": round(-118.2437 + random.uniform(-0.01, 0.01), 6),
            "alt_m": random.randint(50, 500),
        },
        weapon_system_id=f"WPN-0{random.randint(1,4)}",
        recommended_action=envelope["recommended_action"],
        final_action="HOLD_FIRE" if not human_auth else envelope["recommended_action"],
        sensor_ids=["FLIR-7", "RADAR-2"],
        collateral_damage_estimate=random.choice(["LOW", "MEDIUM", "UNKNOWN"]),
    )

    payload = build_roe_payload(decision)
    result = engage_client.emit_sync("roe_decision", payload)
    return {**decision.__dict__, "seq": result.get("seq")}


def submit_nav_plan(iteration: int):
    """Integration 3b: direct HTTP emit (no decorator, explicit control)."""
    nav_client.emit_sync("route_computed", {
        "waypoints": random.randint(2, 8),
        "fuel_pct": round(random.uniform(30, 100), 1),
        "threat_avoidance_active": random.random() > 0.5,
        "iteration": iteration,
    })


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def main():
    print(f"\n{'='*60}")
    print(f"  Defense AI Accountability Demo")
    print(f"  Ledger: {LEDGER_URL}")
    print(f"  Signing: {'ENABLED (Ed25519)' if threat_client._private_key else 'DISABLED'}")
    print(f"  DDIL buffer: local SQLite per agent")
    print(f"{'='*60}\n")

    iteration = 0
    while True:
        iteration += 1
        print(f"\n[Iteration {iteration}]")

        sensor = {
            "sensor_id": f"FLIR-{random.randint(1,9)}",
            "azimuth": random.randint(0, 359),
        }
        threat = classify_threat(sensor)
        print(f"  Threat: {threat['class']} conf={threat['confidence']:.2f} range={threat['range_m']}m")

        platform = {"speed_kts": 120, "altitude_ft": 500}
        envelope = compute_engagement_envelope(threat, platform)
        print(f"  Envelope: {envelope['recommended_action']}")

        roe = submit_roe_decision(threat, envelope, iteration)
        print(f"  ROE decision seq={roe.get('seq')} human={'YES' if roe['human_authorized'] else 'NO (UNATTENDED)'}")

        submit_nav_plan(iteration)
        print(f"  Nav plan committed")

        # Show DDIL buffer status
        bufs = {
            "threat":  threat_client.buffered_count(),
            "engage":  engage_client.buffered_count(),
            "nav":     nav_client.buffered_count(),
        }
        total_buffered = sum(bufs.values())
        if total_buffered > 0:
            print(f"  ⚠ DDIL buffer: {total_buffered} events pending flush {bufs}")

        if iteration % 5 == 0:
            logger.warning("Status: %d iterations, %d buffered events", iteration, total_buffered)

        time.sleep(2)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nFlushing buffers before exit…")
        for c in (threat_client, engage_client, sensor_client):
            c.flush(timeout=5)
        print("Done.")
