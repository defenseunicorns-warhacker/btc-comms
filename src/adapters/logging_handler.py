"""
LedgerLogHandler — drop-in Python logging.Handler.

Adds immutable accountability to ANY existing Python application that uses
the standard library logging module. Two lines of integration:

    import logging
    from adapters import LedgerLogHandler                        # line 1
    logging.getLogger().addHandler(LedgerLogHandler("my-svc"))  # line 2

After that, every log record at WARNING or above is automatically shipped
to the ledger asynchronously. The application's existing behavior is
unchanged — this handler is additive.

Full config example (works with dictConfig / fileConfig too):
    handlers:
      ledger:
        class: adapters.logging_handler.LedgerLogHandler
        source_id: threat-classifier
        base_url: http://localhost:8000
        level: WARNING
"""

import logging
import traceback

from .client import LedgerClient


class LedgerLogHandler(logging.Handler):
    """
    Forwards log records to the accountability ledger as structured events.
    Non-blocking — uses LedgerClient's async queue so the handler never
    slows down the calling application.
    """

    def __init__(self, source_id: str = "python-app",
                 base_url: str = "http://localhost:8000",
                 level: int = logging.WARNING):
        super().__init__(level)
        self._client = LedgerClient(base_url=base_url, source_id=source_id, async_mode=True)

    def emit(self, record: logging.LogRecord) -> None:
        payload = {
            "event_type": "log_record",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "funcName": record.funcName,
            "lineno": record.lineno,
        }
        if record.exc_info:
            payload["exception"] = traceback.format_exception(*record.exc_info)

        # Fire-and-forget — never raises, never blocks the caller
        try:
            self._client.emit("log_record", payload)
        except Exception:
            self.handleError(record)

    def close(self):
        self._client.close()
        super().close()
