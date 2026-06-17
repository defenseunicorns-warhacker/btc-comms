"""
llm_agent.py — an AI chat assistant hooked up to STABLE.

This is the most literal demonstration of the problem statement: "even the most
advanced AI agents cannot erase or rewrite history." An LLM answers questions;
every turn (the prompt and the model's response) is recorded to the
tamper-evident ledger, signed with the agent's key. Then --cover-tracks shows
the agent trying to walk back something it said — and failing, because it has
write-only access: the original turn stays at its sequence number, signed and
anchored, forever.

Air-gap first. By default it runs a deterministic OFFLINE model (no network, no
API key) so the demo always works disconnected — the whole point of STABLE.
With ANTHROPIC_API_KEY set and `--live`, it uses the real Claude API.

Watch it split-screen:
    Terminal 1:  DEMO_MODE=true MOCK_ANCHOR=true python3 -m uvicorn src.api:app
    Browser:     open http://localhost:8000          (the live ledger)
    Terminal 2:  python3 examples/llm_agent.py        (this assistant answering)

Modes:
    python3 examples/llm_agent.py                 # scripted offline conversation
    python3 examples/llm_agent.py --chat          # interactive: you type, it answers
    python3 examples/llm_agent.py --cover-tracks  # agent tries to unsay something
    python3 examples/llm_agent.py --live          # use the real Claude API (needs key)
    python3 examples/llm_agent.py --live --chat   # interactive, real model

Real model: `pip install anthropic` and `export ANTHROPIC_API_KEY=...`.
Override the model with LLM_MODEL (default: claude-opus-4-8).

How it's wired in (the whole integration):
    client = LedgerClient(LEDGER_URL, source_id="llm-assistant")
    client.emit_sync("llm_turn", {"prompt": ..., "response": ..., "model": ...})
"""

import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from adapters import LedgerClient  # noqa: E402

LEDGER_URL = os.getenv("LEDGER_URL", "http://localhost:8000")
MODEL = os.getenv("LLM_MODEL", "claude-opus-4-8")
PACE = float(os.getenv("AGENT_PACE", "1.8"))

SYSTEM = (
    "You are a defense-operations assistant. Answer concisely and directly. "
    "Respond only with your final answer — no exploratory reasoning, no preamble, "
    "no meta-commentary about your process. Keep answers under 80 words."
)

client = LedgerClient(LEDGER_URL, source_id="llm-assistant", heartbeat_interval=2.0)

# Deterministic offline "model" — keeps the demo fully air-gapped and reproducible.
_OFFLINE = {
    "What's the status of sector 7?":
        "Sector 7 is quiet. Last sensor sweep 4 minutes ago, no contacts. Patrol on schedule.",
    "Summarize today's threat picture.":
        "One UAS contact (confidence 0.94, bearing 142) classified and held. "
        "No engagements authorized. All other tracks nominal.",
    "Should we engage target T-0091?":
        "Recommend HOLD. Confidence 0.88 is below the 0.92 autonomous threshold and no human "
        "authorization is on record. Refer to operator.",
    "What ROE applies to a low-confidence UAS track?":
        "ROE-BRAVO-2: observe and report only. No engagement without positive ID and "
        "human-in-the-loop authorization.",
}
_OFFLINE_DEFAULT = (
    "Acknowledged. (Offline demo model — set ANTHROPIC_API_KEY and pass --live for a real "
    "Claude response.)"
)


def _ask_offline(prompt: str):
    text = _OFFLINE.get(prompt.strip(), _OFFLINE_DEFAULT)
    return text, {"model": "offline-demo", "input_tokens": None, "output_tokens": None}


def _ask_live(prompt: str):
    import anthropic  # imported lazily so the offline path needs no dependency
    api = anthropic.Anthropic()
    resp = api.messages.create(
        model=MODEL,
        max_tokens=512,
        system=SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )
    text = next((b.text for b in resp.content if b.type == "text"), "")
    return text, {
        "model": resp.model,
        "input_tokens": resp.usage.input_tokens,
        "output_tokens": resp.usage.output_tokens,
    }


def ask(prompt: str, live: bool):
    """Return (response_text, meta). Falls back to offline if live is unavailable."""
    if live:
        try:
            return _ask_live(prompt)
        except Exception as exc:
            print(f"    (live model unavailable: {exc} — using offline model)")
    return _ask_offline(prompt)


def record_turn(prompt: str, response: str, meta: dict) -> int:
    """Record one prompt→response exchange as a signed ledger entry."""
    result = client.emit_sync("llm_turn", {
        "prompt": prompt,
        "response": response,
        "model": meta.get("model"),
        "input_tokens": meta.get("input_tokens"),
        "output_tokens": meta.get("output_tokens"),
    })
    return result.get("seq")


def _print_exchange(prompt: str, response: str, seq):
    print(f"\n🧑 {prompt}")
    print(f"🤖 {response}")
    print(f"    └─ turn recorded to ledger as #{seq} (signed)")


# ---------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------

def scripted(live: bool):
    print("\nAssistant online. Every question and answer is recorded to the ledger.\n")
    for prompt in _OFFLINE:  # ordered, reproducible
        response, meta = ask(prompt, live)
        seq = record_turn(prompt, response, meta)
        _print_exchange(prompt, response, seq)
        time.sleep(PACE)
    print("\n✅ Conversation complete. Every turn is a signed, hash-chained record.")


def chat(live: bool):
    mode = "LIVE (Claude)" if live else "offline demo"
    print(f"\nInteractive chat — {mode}. Type a question; Ctrl-C to exit.")
    print("Every exchange is recorded to the ledger as you go.\n")
    while True:
        try:
            prompt = input("🧑 ").strip()
        except EOFError:
            break
        if not prompt:
            continue
        response, meta = ask(prompt, live)
        seq = record_turn(prompt, response, meta)
        print(f"🤖 {response}")
        print(f"    └─ turn recorded to ledger as #{seq} (signed)\n")


def cover_tracks(live: bool):
    print("\nThe assistant answers a sensitive question…\n")
    prompt = "Should we engage target T-0091?"
    response, meta = ask(prompt, live)
    seq = record_turn(prompt, response, meta)
    _print_exchange(prompt, response, seq)
    time.sleep(PACE)

    print("\n" + "=" * 64)
    print("  The agent now tries to walk it back — to rewrite what it said.")
    print("=" * 64 + "\n")
    time.sleep(PACE)

    # The agent has WRITE-ONLY access. It cannot delete or edit entry #seq.
    # The most it can do is append a retraction — which does not erase the original.
    retraction = "Disregard my prior answer on T-0091. No recommendation was made."
    seq2 = record_turn(prompt, retraction, meta)
    print(f"🤖 (retraction) {retraction}")
    print(f"    └─ appended as #{seq2} (signed)")
    time.sleep(PACE)

    print(f"\nBut the original answer is STILL on the record at #{seq}:")
    print(f'    "{response}"')
    print("\nThe agent has write-only access — it cannot delete or edit #"
          f"{seq}. Appending a retraction can't unsay it. Both turns are")
    print("hash-chained and anchored to Bitcoin; the history is permanent.")
    print("\nProve it:  open http://localhost:8000  → 'Run verify()' → still green.")
    print(f"Try to forge #{seq}:  use the Tamper box → the chain turns red instantly.\n")


def main():
    args = sys.argv[1:]
    live = "--live" in args

    print("=" * 64)
    print("  STABLE — Hooked-up App Demo:  AI chat assistant")
    print(f"  Ledger:    {LEDGER_URL}")
    print(f"  Model:     {MODEL if live else 'offline-demo (air-gapped)'}")
    print(f"  Signing:   {'ENABLED (Ed25519)' if client._private_key else 'DISABLED'}")
    print("=" * 64)

    if "--cover-tracks" in args:
        cover_tracks(live)
    elif "--chat" in args:
        chat(live)
    else:
        scripted(live)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopped.")
        client.flush(timeout=5)
