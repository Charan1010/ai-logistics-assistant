"""
In-memory metrics store for the Feature 11 observability layer.

Thread-safe via threading.Lock — handles the read-modify-write pattern
that would otherwise race under the GIL. Swap for prometheus-client or
OpenTelemetry SDK in production.
"""
import threading
from typing import Any, Optional

_lock = threading.Lock()

_metrics: dict[str, Any] = {
    "total_requests":   0,
    "total_errors":     0,
    "total_latency_ms": 0.0,
    "eval_last_run":    None,
}


def record_request(duration_ms: float, had_error: bool = False) -> None:
    """Increment request counter and accumulate latency. Called by TimingMiddleware."""
    with _lock:
        _metrics["total_requests"]   += 1
        _metrics["total_latency_ms"] += duration_ms
        if had_error:
            _metrics["total_errors"] += 1


def set_eval_result(report: dict) -> None:
    """Store the most recent eval report so GET /api/eval/last can retrieve it."""
    with _lock:
        _metrics["eval_last_run"] = report


def get_last_eval() -> Optional[dict]:
    with _lock:
        return _metrics["eval_last_run"]


def get_metrics() -> dict:
    """Snapshot with derived avg_latency_ms and error_rate computed on read."""
    with _lock:
        total = _metrics["total_requests"]
        avg_ms = (_metrics["total_latency_ms"] / total) if total > 0 else 0.0
        error_rate = (_metrics["total_errors"] / total) if total > 0 else 0.0
        eval_last = _metrics["eval_last_run"]

    return {
        "total_requests": total,
        "total_errors": _metrics["total_errors"],
        "avg_latency_ms": round(avg_ms, 2),
        "error_rate": round(error_rate, 4),
        "last_eval_pass_rate": (eval_last or {}).get("pass_rate") if eval_last else None,
    }


def reset_for_tests() -> None:
    """Reset all counters. Only for test setup/teardown."""
    with _lock:
        _metrics["total_requests"] = 0
        _metrics["total_errors"] = 0
        _metrics["total_latency_ms"] = 0.0
        _metrics["eval_last_run"] = None
