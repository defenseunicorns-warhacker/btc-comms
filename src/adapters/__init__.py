# Pluggable adapters — wire any existing app into the accountability layer.
#
# Pick the integration that matches your stack:
#
#   LedgerClient        — direct HTTP client, works from any language/service
#   LedgerLogHandler    — drop-in Python logging.Handler (2-line integration)
#   audit_log           — @audit_log decorator for individual functions
#   OTLPSpanReceiver    — OpenTelemetry span receiver (see adapters/otlp.py)

from .client import LedgerClient
from .logging_handler import LedgerLogHandler
from .audit_decorator import audit_log
