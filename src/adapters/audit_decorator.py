"""
@audit_log — wrap any function so every call is recorded in the ledger.

Usage:

    from adapters import audit_log

    client = LedgerClient("http://localhost:8000", source_id="nav-planner")

    @audit_log(client)
    def compute_route(origin, destination, threat_level):
        ...
        return {"waypoints": [...], "eta_min": 42}

Every call records: function name, arguments, return value summary, and
duration. Exceptions are recorded with the traceback before re-raising.
The caller's code is completely unchanged beyond the decorator.

For methods on a class:
    class ThreatClassifier:
        @audit_log(client, include_args=True)
        def classify(self, sensor_data):
            ...
"""

import functools
import time
import traceback
from typing import Any, Callable, Optional


def audit_log(client, include_args: bool = True, include_result: bool = True,
              event_type: Optional[str] = None):
    """
    Decorator factory. Wraps a function so every call is shipped to the ledger.

    client        — LedgerClient instance
    include_args  — record positional/keyword arguments (set False for classified inputs)
    include_result — record the return value summary (set False for classified outputs)
    event_type    — override the event type name (defaults to the function name)
    """
    def decorator(fn: Callable) -> Callable:
        name = event_type or fn.__qualname__

        @functools.wraps(fn)
        def wrapper(*args, **kwargs) -> Any:
            start = time.monotonic()
            payload: dict = {"function": name, "status": "called"}

            if include_args:
                # Skip 'self'/'cls' for methods
                positional = list(args[1:]) if (args and hasattr(args[0], fn.__name__)) else list(args)
                payload["args"] = [_safe_repr(a) for a in positional]
                payload["kwargs"] = {k: _safe_repr(v) for k, v in kwargs.items()}

            try:
                result = fn(*args, **kwargs)
                elapsed_ms = round((time.monotonic() - start) * 1000, 1)
                payload["status"] = "ok"
                payload["duration_ms"] = elapsed_ms
                if include_result and result is not None:
                    payload["result_summary"] = _safe_repr(result)
                client.emit(name, payload)
                return result
            except Exception as exc:
                elapsed_ms = round((time.monotonic() - start) * 1000, 1)
                payload["status"] = "error"
                payload["duration_ms"] = elapsed_ms
                payload["exception_type"] = type(exc).__name__
                payload["exception_msg"] = str(exc)
                payload["traceback"] = traceback.format_exc()
                client.emit(name, payload)
                raise

        return wrapper
    return decorator


def _safe_repr(obj: Any, max_len: int = 200) -> Any:
    """Return a JSON-safe, truncated representation of obj."""
    if isinstance(obj, (bool, int, float, type(None))):
        return obj
    if isinstance(obj, str):
        return obj[:max_len] + ("…" if len(obj) > max_len else "")
    if isinstance(obj, (list, tuple)):
        return [_safe_repr(x) for x in obj[:10]]
    if isinstance(obj, dict):
        return {str(k): _safe_repr(v) for k, v in list(obj.items())[:10]}
    rep = repr(obj)
    return rep[:max_len] + ("…" if len(rep) > max_len else "")
