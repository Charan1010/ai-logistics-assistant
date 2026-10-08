"""
Production middleware for Feature 11.

RequestIDMiddleware — assigns a UUID to every request, echoes it as X-Request-ID.
                      Framework equivalent: OpenTelemetry trace context.

TimingMiddleware    — records wall-clock latency + 5xx error rate for every /api/*
                      call to app/metrics.py. Framework equivalent: Prometheus
                      request_duration_seconds histogram middleware.

Order in main.py matters: RequestIDMiddleware must be added LAST so it executes
FIRST (Starlette adds middleware in LIFO order).
"""
import logging
import time
import uuid
from contextvars import ContextVar

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app import metrics

logger = logging.getLogger(__name__)

_request_id_var: ContextVar[str] = ContextVar("request_id", default="")


def get_request_id() -> str:
    """Return the X-Request-ID for the currently executing request."""
    return _request_id_var.get()


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Attach a unique ID to every request; honour inbound X-Request-ID if present."""

    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        _request_id_var.set(request_id)
        request.state.request_id = request_id
        response: Response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


class TimingMiddleware(BaseHTTPMiddleware):
    """Measure wall-clock latency for /api/* and record to metrics + JSON log."""

    async def dispatch(self, request: Request, call_next):
        if not request.url.path.startswith("/api/"):
            return await call_next(request)

        start = time.perf_counter()
        had_error = False
        status_code = 500
        try:
            response: Response = await call_next(request)
            status_code = response.status_code
            had_error = status_code >= 500
            return response
        except Exception:
            had_error = True
            raise
        finally:
            duration_ms = (time.perf_counter() - start) * 1000.0
            metrics.record_request(duration_ms, had_error=had_error)
            logger.info(
                "request handled",
                extra={
                    "request_id": _request_id_var.get(),
                    "path": request.url.path,
                    "method": request.method,
                    "duration_ms": round(duration_ms, 2),
                    "status_code": status_code,
                },
            )
