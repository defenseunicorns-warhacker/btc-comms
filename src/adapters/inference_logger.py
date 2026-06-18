"""
InferenceLogger — record AI inference inputs and outputs to the accountability ledger.

Enables *deterministic inference verification*: an investigator can re-run the
same model on the recorded inputs and verify the output matches. Combined with
model_anchor (which proves which weights were deployed) and TEE attestation
(which proves which binary ran), this builds the proof-of-processing chain
without requiring zero-knowledge proofs of the full computation.

Usage:
    from adapters.inference_logger import InferenceLogger

    logger = InferenceLogger(
        client=client,
        model_id="llama-3-70b",
        model_version="v1.2.3",
        hash_inputs=True,   # True for classified inputs — logs SHA-256, not raw
    )

    # Decorator form:
    @logger.log
    def classify_threat(sensor_data):
        return model.run(sensor_data)

    # Direct form (when you control the call site):
    result = model.generate(prompt)
    logger.record(inputs={"prompt": prompt}, output=result, latency_ms=38.2)

Every record includes:
  _schema         — "inference_record_v1"
  model_id        — which model
  model_version   — which weights/release
  inference_seq   — per-session call counter
  input_hash / inputs  — SHA-256 of inputs (hash_inputs=True) or raw inputs
  output / output_hash — result or its hash
  latency_ms      — wall-clock time
  status          — "ok" | "error"
"""

import functools
import hashlib
import json
import time
from typing import Any, Optional


class InferenceLogger:
    """
    Records AI inference invocations to the accountability ledger.

    hash_inputs=True (default): records SHA-256(inputs) rather than raw inputs.
      Use this for classified sensor data or prompts — the hash is enough for
      a re-execution verification check without exposing sensitive content.

    hash_outputs=False (default): records the raw output. Set True to hash it too.
    """

    def __init__(
        self,
        client,
        model_id: str,
        model_version: str = "unknown",
        hash_inputs: bool = True,
        hash_outputs: bool = False,
    ):
        self.client = client
        self.model_id = model_id
        self.model_version = model_version
        self.hash_inputs = hash_inputs
        self.hash_outputs = hash_outputs
        self._seq = 0

    # ------------------------------------------------------------------
    # Direct call
    # ------------------------------------------------------------------

    def record(
        self,
        inputs: Any = None,
        output: Any = None,
        latency_ms: Optional[float] = None,
        metadata: Optional[dict] = None,
    ) -> dict:
        """
        Record one inference directly. Returns the payload dict that was emitted.

        inputs  — the model inputs (raw value or dict).
        output  — the model output.
        latency_ms — wall-clock duration if known.
        metadata   — arbitrary extra fields (e.g. {"roe_seq": 42, "sensor_id": "FLIR-7"}).
        """
        self._seq += 1
        payload: dict = {
            "_schema": "inference_record_v1",
            "model_id": self.model_id,
            "model_version": self.model_version,
            "inference_seq": self._seq,
        }

        if inputs is not None:
            if self.hash_inputs:
                payload["input_hash"] = _hash_value(inputs)
            else:
                payload["inputs"] = _safe_serialize(inputs)

        if output is not None:
            if self.hash_outputs:
                payload["output_hash"] = _hash_value(output)
            else:
                payload["output"] = _safe_serialize(output)

        if latency_ms is not None:
            payload["latency_ms"] = round(latency_ms, 1)

        if metadata:
            payload["metadata"] = metadata

        self.client.emit("inference_record", payload)
        return payload

    # ------------------------------------------------------------------
    # Decorator
    # ------------------------------------------------------------------

    def log(self, fn=None, *, include_inputs: Optional[bool] = None,
            include_output: Optional[bool] = None):
        """
        Decorator. Wrap a function so every call is automatically logged.

        @logger.log
        def classify(sensor_data): ...

        Per-call overrides (must use parens when passing kwargs):
        @logger.log(include_inputs=False)
        def sensitive_fn(classified_data): ...
        """
        if fn is not None:
            # Called as @logger.log (no parentheses)
            return self._wrap(fn)
        # Called as @logger.log(...) — return a decorator
        def decorator(f):
            return self._wrap(f, include_inputs=include_inputs, include_output=include_output)
        return decorator

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _wrap(self, fn, include_inputs=None, include_output=None):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            start = time.monotonic()
            try:
                result = fn(*args, **kwargs)
                latency = round((time.monotonic() - start) * 1000, 1)
                self._seq += 1
                payload: dict = {
                    "_schema": "inference_record_v1",
                    "model_id": self.model_id,
                    "model_version": self.model_version,
                    "function": fn.__qualname__,
                    "inference_seq": self._seq,
                    "status": "ok",
                    "latency_ms": latency,
                }

                if include_inputs is not False:
                    inputs = {"args": list(args), "kwargs": kwargs}
                    if self.hash_inputs:
                        payload["input_hash"] = _hash_value(inputs)
                    else:
                        payload["inputs"] = _safe_serialize(inputs)

                if include_output is not False:
                    if self.hash_outputs:
                        payload["output_hash"] = _hash_value(result)
                    else:
                        payload["output"] = _safe_serialize(result)

                self.client.emit("inference_record", payload)
                return result

            except Exception as exc:
                latency = round((time.monotonic() - start) * 1000, 1)
                self._seq += 1
                self.client.emit("inference_record", {
                    "_schema": "inference_record_v1",
                    "model_id": self.model_id,
                    "model_version": self.model_version,
                    "function": fn.__qualname__,
                    "inference_seq": self._seq,
                    "status": "error",
                    "latency_ms": latency,
                    "exception_type": type(exc).__name__,
                    "exception_msg": str(exc),
                })
                raise

        return wrapper


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _hash_value(value: Any) -> str:
    """Stable SHA-256 fingerprint of any JSON-serializable value."""
    serialized = json.dumps(value, sort_keys=True, default=str).encode()
    return "sha256:" + hashlib.sha256(serialized).hexdigest()


def _safe_serialize(value: Any, max_str: int = 500) -> Any:
    """Return a JSON-safe, truncated representation of value."""
    if isinstance(value, (bool, int, float, type(None))):
        return value
    if isinstance(value, str):
        return value[:max_str] + ("…" if len(value) > max_str else "")
    if isinstance(value, (list, tuple)):
        return [_safe_serialize(x) for x in value[:20]]
    if isinstance(value, dict):
        return {str(k): _safe_serialize(v) for k, v in list(value.items())[:20]}
    rep = repr(value)
    return rep[:max_str] + ("…" if len(rep) > max_str else "")
