"""
ddil_demo.py — show DDIL resilience: an agent that survives a network outage.

DDIL = Denied, Degraded, Intermittent, or Limited connectivity — the contested
edge. This agent emits one signed event per second using the buffered (async)
client. When the recorder is unreachable, events queue in a local SQLite buffer
and the agent keeps working; when connectivity returns, the buffer flushes in
order and nothing is lost. The agent also heartbeats its buffer depth, so the
dashboard's "Agents" strip shows this agent flip to ⚠ buffering and back to live.

Demo flow (watch the dashboard's Agents strip):
    Terminal 1:  DEMO_MODE=true MOCK_ANCHOR=true python3 -m uvicorn src.api:app
    Browser:     open http://localhost:8000
    Terminal 2:  python3 examples/ddil_demo.py

    Now KILL Terminal 1 (Ctrl-C). The recorder — and the dashboard — go down.
    Watch Terminal 2: the local buffer count climbs every second. No events lost.

    RESTART Terminal 1. Refresh the dashboard. The Agents strip shows
    'edge-sensor ⚠ N buffered', then it drains to '✓ live' and the buffered
    events stream into the ledger in order.

Run `verify()` afterward → still green. The outage left no gap.
"""

import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from adapters import LedgerClient  # noqa: E402

LEDGER_URL = os.getenv("LEDGER_URL", "http://localhost:8000")

# async_mode=True → emit() buffers locally on failure; heartbeat reports depth.
client = LedgerClient(LEDGER_URL, source_id="edge-sensor",
                      async_mode=True, heartbeat_interval=2.0)


def main():
    print("=" * 64)
    print("  STABLE — DDIL Resilience Demo:  edge-sensor")
    print(f"  Ledger:    {LEDGER_URL}")
    print(f"  Signing:   {'ENABLED (Ed25519)' if client._private_key else 'DISABLED'}")
    print("=" * 64)
    print("\nEmitting one event/sec. Kill the recorder and watch the buffer climb;")
    print("restart it and watch the buffer drain. No events are lost.\n")

    i = 0
    while True:
        i += 1
        client.emit("sensor_ping", {
            "sensor_id": "FLIR-7",
            "azimuth": (i * 37) % 360,
            "reading": i,
        })
        # Give the background drain a moment to deliver before judging the link,
        # so a healthy recorder reads as "delivered" and only a real outage buffers.
        for _ in range(6):
            if client.buffered_count() == 0:
                break
            time.sleep(0.1)
        buffered = client.buffered_count()
        if buffered > 0:
            print(f"  [{i:>4}]  ⚠ recorder unreachable — {buffered} events buffered locally (DDIL)")
        else:
            print(f"  [{i:>4}]  ✓ delivered (buffer empty)")
        time.sleep(0.6)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nFlushing buffer before exit…")
        client.flush(timeout=5)
        print("Done.")
