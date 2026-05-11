"""Edge analytics — record + flush + push to generator.

The hot path enqueues; the background thread does the network I/O. If the
generator is unreachable we drop the batch (logging a warning) and let the
queue catch the next tick.
"""
import logging
import threading
import time
from collections import deque
import requests

from . import config

log = logging.getLogger("edge.analytics")

_QUEUE: deque = deque(maxlen=config.ANALYTICS_QUEUE_MAX)
_QUEUE_LOCK = threading.Lock()
_THREAD_LOCK = threading.Lock()
_FLUSH_THREAD: threading.Thread | None = None
_events_dropped: int = 0
_drop_lock = threading.Lock()


def _reset_for_tests() -> None:
    global _events_dropped, _FLUSH_THREAD, _QUEUE
    with _QUEUE_LOCK:
        _QUEUE = deque(maxlen=config.ANALYTICS_QUEUE_MAX)
    with _drop_lock:
        _events_dropped = 0
    _FLUSH_THREAD = None


def record_request(endpoint: str, username: str | None, widget: str | None,
                   status: int, latency_ms: int, cache_hit: int | None = None) -> None:
    ev = {
        "ts": int(time.time()),
        "service": "edge",
        "kind": "request",
        "username": username,
        "endpoint": endpoint,
        "widget": widget,
        "status": int(status),
        "latency_ms": int(latency_ms),
        "cache_hit": cache_hit,
    }
    global _events_dropped
    with _QUEUE_LOCK:
        if len(_QUEUE) >= _QUEUE.maxlen:
            with _drop_lock:
                _events_dropped += 1
            return
        _QUEUE.append(ev)


def flush_now() -> int:
    with _QUEUE_LOCK:
        batch = list(_QUEUE)
        _QUEUE.clear()
    if not batch:
        return 0
    if not config.ANALYTICS_GENERATOR_URL or not config.ANALYTICS_INTERNAL_TOKEN:
        return 0
    try:
        requests.post(
            f"{config.ANALYTICS_GENERATOR_URL}/internal/analytics/events",
            headers={"X-Internal-Token": config.ANALYTICS_INTERNAL_TOKEN},
            json={"events": batch},
            timeout=2,
        )
    except Exception:
        log.warning("analytics flush failed (events lost)", exc_info=True)
        return 0
    return len(batch)


def _flush_loop():
    while True:
        time.sleep(config.ANALYTICS_FLUSH_SECONDS)
        try:
            flush_now()
        except Exception:
            log.exception("flush loop error")


def start_flush_thread():
    global _FLUSH_THREAD
    with _THREAD_LOCK:
        if _FLUSH_THREAD is not None and _FLUSH_THREAD.is_alive():
            return
        t = threading.Thread(target=_flush_loop, name="edge-analytics-flush", daemon=True)
        t.start()
        _FLUSH_THREAD = t
