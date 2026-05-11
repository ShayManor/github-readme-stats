"""Fetcher analytics — record fetch latency + push batches to the generator.

The hot path enqueues; a daemon thread flushes batches over the internal
Docker network. On push failure we drop the batch and keep going.
"""
import logging
import threading
import time
from collections import deque
import requests

from . import config

log = logging.getLogger("fetcher.analytics")

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


def record_fetch(username: str, status: int, latency_ms: int) -> None:
    ev = {
        "ts": int(time.time()),
        "service": "fetcher",
        "kind": "fetch",
        "username": username,
        "endpoint": "github/users/<u>",
        "widget": None,
        "status": int(status),
        "latency_ms": int(latency_ms),
        "cache_hit": None,
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
    if not config.GENERATOR_URL or not config.INTERNAL_TOKEN:
        return 0
    try:
        requests.post(
            f"{config.GENERATOR_URL}/internal/analytics/events",
            headers={"X-Internal-Token": config.INTERNAL_TOKEN},
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
        t = threading.Thread(target=_flush_loop, name="fetcher-analytics-flush", daemon=True)
        t.start()
        _FLUSH_THREAD = t
