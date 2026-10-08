"""
Structured JSON logging for production (Feature 11).

Each log line becomes a single JSON object: searchable, filterable, alertable
in any log platform (Datadog, Loki, CloudWatch, Splunk). Framework equivalent:
structlog.processors.JSONRenderer / python-json-logger.
"""
import json
import logging
import sys
from datetime import datetime, timezone


class JSONFormatter(logging.Formatter):
    """Formats log records as single-line JSON objects."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict = {
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        # Extras injected via LogRecord by middleware / endpoint handlers.
        for key in ("request_id", "path", "method", "duration_ms", "status_code", "tenant_id"):
            if hasattr(record, key):
                payload[key] = getattr(record, key)

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, default=str)


def setup_logging(level: str = "INFO") -> None:
    """Configure the root logger to emit JSON lines to stdout. Call once at startup."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter())
    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    root.handlers = [handler]
