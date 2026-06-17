"""
file_agent.py — a deliberately SIMPLE app hooked up to STABLE.

The point of this demo is legibility: anyone can watch an AI agent do real,
visible work (it writes, edits, and deletes files on disk) and watch every one
of those actions land in the tamper-evident ledger in real time — no Bitcoin or
Merkle-tree knowledge required.

It also makes the problem statement concrete: "even the most advanced AI agents
cannot erase or rewrite history." Run it with --cover-tracks and the agent
wipes its own workspace — every file is gone from disk, yet the ledger still
holds a signed, Bitcoin-anchored record of exactly what each file contained and
when it was written.

Watch it split-screen:
    Terminal 1:  DEMO_MODE=true MOCK_ANCHOR=true python3 -m uvicorn src.api:app
    Browser:     open http://localhost:8000          (the live ledger)
    Terminal 2:  python3 examples/file_agent.py       (this agent doing work)

Modes:
    python3 examples/file_agent.py                 # scripted: create, edit, delete
    python3 examples/file_agent.py --cover-tracks  # agent tries to erase the evidence
    python3 examples/file_agent.py --loop          # keep working until Ctrl-C

How it's wired in (this is the whole integration):
    client = LedgerClient(LEDGER_URL, source_id="doc-agent")
    client.emit_sync("file_created", {"path": ..., "content_sha256": ...})
"""

import hashlib
import os
import shutil
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from adapters import LedgerClient  # noqa: E402

LEDGER_URL = os.getenv("LEDGER_URL", "http://localhost:8000")
WORKSPACE = os.path.join(os.path.dirname(__file__), "agent_workspace")
PACE = float(os.getenv("AGENT_PACE", "1.6"))  # seconds between actions (watchable)

client = LedgerClient(LEDGER_URL, source_id="doc-agent", heartbeat_interval=2.0)


# ---------------------------------------------------------------------------
# File operations — each one records a signed event to the ledger
# ---------------------------------------------------------------------------

def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _emit(event_type: str, payload: dict) -> None:
    """Record an action to STABLE. Friendly message if the recorder is down."""
    try:
        result = client.emit_sync(event_type, payload)
        seq = result.get("seq")
        print(f"    └─ recorded to ledger as #{seq} (signed)")
    except Exception as exc:
        print(f"    └─ ⚠ could not reach ledger ({exc}). Is the server running?")


def create_file(name: str, content: str) -> None:
    path = os.path.join(WORKSPACE, name)
    data = content.encode("utf-8")
    with open(path, "wb") as f:
        f.write(data)
    print(f"📄 Created  {name}  ({len(data)} bytes)")
    _emit("file_created", {
        "path": name,
        "size_bytes": len(data),
        "content_sha256": _sha256(data),
    })


def modify_file(name: str, new_content: str) -> None:
    path = os.path.join(WORKSPACE, name)
    old = open(path, "rb").read() if os.path.exists(path) else b""
    data = new_content.encode("utf-8")
    with open(path, "wb") as f:
        f.write(data)
    print(f"✏️  Modified {name}  ({len(old)} → {len(data)} bytes)")
    _emit("file_modified", {
        "path": name,
        "old_sha256": _sha256(old),
        "new_sha256": _sha256(data),
        "size_bytes": len(data),
    })


def delete_file(name: str) -> None:
    path = os.path.join(WORKSPACE, name)
    last = open(path, "rb").read() if os.path.exists(path) else b""
    if os.path.exists(path):
        os.remove(path)
    print(f"🗑️  Deleted  {name}")
    _emit("file_deleted", {
        "path": name,
        "last_known_sha256": _sha256(last),
    })


# ---------------------------------------------------------------------------
# Scenario
# ---------------------------------------------------------------------------

def _reset_workspace():
    if os.path.exists(WORKSPACE):
        shutil.rmtree(WORKSPACE)
    os.makedirs(WORKSPACE, exist_ok=True)


def _pause():
    time.sleep(PACE)


def do_work():
    """A scripted set of recognizable file operations, paced to watch live."""
    print("\nAgent 'doc-agent' starting work. Watch the ledger fill in real time.\n")

    create_file("intel_summary.md",
                "# Intel Summary\nSector 7 quiet. No contacts.\n")
    _pause()
    create_file("target_dossier_T-0091.txt",
                "Target T-0091\nConfidence: 0.88\nStatus: TRACKING\n")
    _pause()
    create_file("patrol_route.json",
                '{"waypoints": 4, "fuel_pct": 87}\n')
    _pause()
    modify_file("intel_summary.md",
                "# Intel Summary\nSector 7: UAS contact, bearing 142.\n")
    _pause()
    delete_file("patrol_route.json")
    _pause()

    print("\n✅ Work complete. Every action above is now a signed, "
          "hash-chained record in the ledger.")


def cover_tracks():
    """The agent does its work, then tries to erase the evidence."""
    do_work()
    _pause()
    print("\n" + "=" * 64)
    print("  The agent now PANICS and tries to cover its tracks…")
    print("=" * 64 + "\n")
    _pause()

    remaining = sorted(os.listdir(WORKSPACE))
    for name in remaining:
        path = os.path.join(WORKSPACE, name)
        if os.path.isfile(path):
            os.remove(path)
            print(f"🔥 Agent wiped  {name}  from disk")
            _emit("file_deleted", {"path": name, "note": "self_wipe_attempt"})
            time.sleep(0.4)

    print(f"\nThe workspace is now empty: {os.listdir(WORKSPACE)}")
    print("\nBut the agent CANNOT erase what it already did:")
    print("  • Every file action is in the ledger — signed with the agent's own key.")
    print("  • The ledger recorded each file's content hash at write time,")
    print("    so we can prove exactly what each file contained — even now that")
    print("    the files are gone.")
    print("  • Those records are hash-chained and anchored to Bitcoin. The agent")
    print("    has write-only access — it can't delete or rewrite a single entry.")
    print("\nProve it:  open http://localhost:8000  → click 'Run verify()' → still green.")
    print("Try to forge one:  use the Tamper box → the chain turns red instantly.\n")


def loop_forever():
    counter = 0
    docs = ["recon", "sigint", "logistics", "weather", "comms"]
    while True:
        counter += 1
        name = f"{docs[counter % len(docs)]}_{counter:04d}.md"
        create_file(name, f"# Report {counter}\nGenerated by doc-agent.\n")
        _pause()
        if counter % 4 == 0:
            modify_file(name, f"# Report {counter} (revised)\nUpdated.\n")
            _pause()
        if counter % 6 == 0:
            old = f"{docs[(counter - 5) % len(docs)]}_{counter - 5:04d}.md"
            if os.path.exists(os.path.join(WORKSPACE, old)):
                delete_file(old)
                _pause()


def main():
    _reset_workspace()
    print("=" * 64)
    print("  STABLE — Hooked-up App Demo:  autonomous file agent")
    print(f"  Ledger:    {LEDGER_URL}")
    print(f"  Workspace: {WORKSPACE}")
    print(f"  Signing:   {'ENABLED (Ed25519)' if client._private_key else 'DISABLED'}")
    print("=" * 64)

    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode == "--cover-tracks":
        cover_tracks()
    elif mode == "--loop":
        loop_forever()
    else:
        do_work()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopped.")
