"""Analytics: bounded in-memory queue, daemon flush thread, query helpers.

Three call sites write events:
  * record_request   — generator's own HTTP path (rarely used; edge handles most)
  * record_render    — worker / on-demand /generate
  * ingest_batch     — POST /internal/analytics/events from edge & fetcher

All writes go through a shared bounded deque so the hot path never blocks on
SQLite I/O. A daemon thread flushes the queue every _FLUSH_SECONDS into
analytics.db in a single transaction.
"""
import json
import logging
import math
import threading
import time
from collections import deque
from typing import Any

from . import config, db

log = logging.getLogger("generator.analytics")

_FLUSH_SECONDS = config.ANALYTICS_FLUSH_SECONDS
_QUEUE_MAX = config.ANALYTICS_QUEUE_MAX
_RETENTION_DAYS = config.ANALYTICS_RETENTION_DAYS

_QUEUE: deque = deque(maxlen=_QUEUE_MAX)
_QUEUE_LOCK = threading.Lock()
_FLUSH_THREAD: threading.Thread | None = None
_THREAD_LOCK = threading.Lock()
_events_dropped: int = 0
_drop_lock = threading.Lock()

_ALLOWED_KINDS = {"request", "render", "fetch"}
_ALLOWED_SERVICES = {"edge", "generator", "fetcher"}


def _reset_for_tests() -> None:
    """Clear the queue + dropped counter; rebuild deque so a monkeypatched
    _QUEUE_MAX takes effect for the next test."""
    global _FLUSH_THREAD, _events_dropped, _QUEUE
    with _QUEUE_LOCK:
        _QUEUE = deque(maxlen=_QUEUE_MAX)
    with _drop_lock:
        _events_dropped = 0
    _FLUSH_THREAD = None


def _enqueue(event: dict) -> None:
    global _events_dropped
    with _QUEUE_LOCK:
        if len(_QUEUE) >= _QUEUE.maxlen:
            with _drop_lock:
                _events_dropped += 1
            return
        _QUEUE.append(event)


def record_request(endpoint: str, username: str | None, widget: str | None,
                   status: int, latency_ms: int, cache_hit: int | None = None) -> None:
    _enqueue({
        "ts": int(time.time()),
        "service": "generator",
        "kind": "request",
        "username": username,
        "endpoint": endpoint,
        "widget": widget,
        "status": int(status),
        "latency_ms": int(latency_ms),
        "cache_hit": cache_hit,
    })


def record_render(username: str, widget: str, latency_ms: int) -> None:
    _enqueue({
        "ts": int(time.time()),
        "service": "generator",
        "kind": "render",
        "username": username,
        "endpoint": None,
        "widget": widget,
        "status": None,
        "latency_ms": int(latency_ms),
        "cache_hit": None,
    })


def _coerce_int_or_none(v: Any) -> int | None:
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, int):
        return v
    return None


def _validate(ev: Any) -> dict | None:
    if not isinstance(ev, dict):
        return None
    try:
        ts = int(ev.get("ts", 0))
        if ts <= 0:
            ts = int(time.time())
        service = ev.get("service")
        kind = ev.get("kind")
        latency_ms = int(ev.get("latency_ms"))
    except (TypeError, ValueError):
        return None
    if service not in _ALLOWED_SERVICES or kind not in _ALLOWED_KINDS:
        return None
    return {
        "ts": ts,
        "service": service,
        "kind": kind,
        "username": ev.get("username") if isinstance(ev.get("username"), str) else None,
        "endpoint": ev.get("endpoint") if isinstance(ev.get("endpoint"), str) else None,
        "widget": ev.get("widget") if isinstance(ev.get("widget"), str) else None,
        "status": _coerce_int_or_none(ev.get("status")),
        "latency_ms": max(0, latency_ms),
        "cache_hit": _coerce_int_or_none(ev.get("cache_hit")),
    }


def ingest_batch(events: list) -> int:
    """Validate + persist a batch in one transaction. Returns rows inserted."""
    if not isinstance(events, list):
        return 0
    cleaned = []
    for ev in events[:500]:
        n = _validate(ev)
        if n is not None:
            cleaned.append(n)
    if not cleaned:
        return 0
    with db.analytics_conn() as c:
        c.executemany(
            """INSERT INTO events(ts, service, kind, username, endpoint, widget,
                                  status, latency_ms, cache_hit)
               VALUES (:ts, :service, :kind, :username, :endpoint, :widget,
                       :status, :latency_ms, :cache_hit)""",
            cleaned,
        )
        c.commit()
    return len(cleaned)


def _drain_queue() -> list[dict]:
    with _QUEUE_LOCK:
        out = list(_QUEUE)
        _QUEUE.clear()
    return out


def _flush_loop() -> None:
    while True:
        time.sleep(_FLUSH_SECONDS)
        try:
            batch = _drain_queue()
            if batch:
                ingest_batch(batch)
        except Exception:
            log.exception("analytics flush failed")


def start_flush_thread() -> None:
    global _FLUSH_THREAD
    with _THREAD_LOCK:
        if _FLUSH_THREAD is not None and _FLUSH_THREAD.is_alive():
            return
        t = threading.Thread(target=_flush_loop, name="analytics-flush", daemon=True)
        t.start()
        _FLUSH_THREAD = t


def _percentile(sorted_vals: list[int], pct: float) -> int:
    if not sorted_vals:
        return 0
    n = len(sorted_vals)
    k = max(0, min(n - 1, math.ceil(pct / 100.0 * n) - 1))
    return int(sorted_vals[k])


def query_summary() -> dict:
    now = int(time.time())
    week_ago = now - 7 * 86400
    with db.analytics_conn() as c:
        req_rows = c.execute(
            """SELECT username, latency_ms, ts FROM events
               WHERE kind='request' AND ts >= ?""", (week_ago,)
        ).fetchall()
        render_rows = c.execute(
            """SELECT username, latency_ms FROM events
               WHERE kind='render' AND ts >= ?""", (week_ago,)
        ).fetchall()
    requests_7d = len(req_rows)
    renders_7d = len(render_rows)
    latencies = sorted(r["latency_ms"] for r in req_rows)
    active = {r["username"] for r in req_rows if r["username"]}
    active.update(r["username"] for r in render_rows if r["username"])
    avg_render_ms = (sum(r["latency_ms"] for r in render_rows) // renders_7d) if renders_7d else 0
    by_day: dict[str, int] = {}
    for r in req_rows:
        day = time.strftime("%Y-%m-%d", time.gmtime(r["ts"]))
        by_day[day] = by_day.get(day, 0) + 1
    daily = []
    for i in range(6, -1, -1):
        day = time.strftime("%Y-%m-%d", time.gmtime(now - i * 86400))
        daily.append({"day": day, "count": by_day.get(day, 0)})
    return {
        "requests_7d": requests_7d,
        "active_users_7d": len(active),
        "p50_ms": _percentile(latencies, 50),
        "p95_ms": _percentile(latencies, 95),
        "renders_7d": renders_7d,
        "avg_render_ms": avg_render_ms,
        "daily_requests": daily,
    }


def query_users(q: str = "", sort: str = "requests", limit: int = 200) -> list[dict]:
    now = int(time.time())
    week_ago = now - 7 * 86400
    with db.analytics_conn() as c:
        c.execute("ATTACH DATABASE ? AS settings", (db.SETTINGS_DB_PATH,))
        try:
            # Count any event kind (request OR render) as activity so the
            # table matches `active_users_7d` in query_summary — without
            # this, render-only users (e.g. cron-driven worker refreshes
            # before any edge traffic) appear in the count but not the
            # table, which looks like a bug.
            rows = c.execute(
                """SELECT e.username AS username,
                          SUM(CASE WHEN e.kind='request' THEN 1 ELSE 0 END) AS requests_7d,
                          MAX(e.ts) AS last_seen,
                          COALESCE(AVG(CASE WHEN e.kind='request'
                                            THEN e.latency_ms END), 0) AS avg_latency_ms,
                          (SELECT u.github_avatar_url FROM settings.users u
                            WHERE u.username = e.username) AS github_avatar_url
                   FROM events e
                   WHERE e.kind IN ('request', 'render')
                     AND e.ts >= ? AND e.username IS NOT NULL
                   GROUP BY e.username""",
                (week_ago,),
            ).fetchall()
            top_eps_rows = c.execute(
                """SELECT username, endpoint, COUNT(*) AS n
                   FROM events
                   WHERE kind='request' AND ts >= ? AND username IS NOT NULL
                   GROUP BY username, endpoint""",
                (week_ago,),
            ).fetchall()
        finally:
            c.execute("DETACH DATABASE settings")
    top_by_user: dict[str, tuple[str, int]] = {}
    for r in top_eps_rows:
        cur = top_by_user.get(r["username"])
        if cur is None or r["n"] > cur[1]:
            top_by_user[r["username"]] = (r["endpoint"], r["n"])
    out = []
    needle = q.lower().strip()
    for r in rows:
        if needle and needle not in (r["username"] or "").lower():
            continue
        out.append({
            "username": r["username"],
            "requests_7d": r["requests_7d"],
            "last_seen": r["last_seen"],
            "avg_latency_ms": int(r["avg_latency_ms"] or 0),
            "top_endpoint": top_by_user.get(r["username"], ("", 0))[0],
            "github_avatar_url": r["github_avatar_url"],
        })
    key = {
        "requests": lambda u: -u["requests_7d"],
        "latency": lambda u: -u["avg_latency_ms"],
        "last_seen": lambda u: -(u["last_seen"] or 0),
    }.get(sort, lambda u: -u["requests_7d"])
    out.sort(key=key)
    return out[: max(1, min(int(limit), 500))]


def rollup_daily_stats() -> int:
    """Snapshot the events table into daily_stats so per-day numbers
    survive the 14d event prune.

    Aggregates every day that still has events in the events table,
    UPSERTing one row per day with (request count, JSON list of unique
    usernames). Days whose events have already been pruned are left
    untouched — their previously-written daily_stats row is preserved.

    Idempotent: re-running rebuilds the affected days from current
    events. Pairs with prune_old, which aligns its cutoff to UTC
    midnight so a day is either entirely retained or entirely pruned
    (no half-pruned days that would corrupt the snapshot on next call).

    Returns number of day rows written.
    """
    with db.analytics_conn() as c:
        rows = c.execute(
            """SELECT ts, kind, username FROM events
               WHERE kind IN ('request', 'render')"""
        ).fetchall()
    if not rows:
        return 0
    buckets: dict[str, dict] = {}
    for r in rows:
        day = time.strftime("%Y-%m-%d", time.gmtime(r["ts"]))
        b = buckets.setdefault(day, {"requests": 0, "users": set()})
        if r["kind"] == "request":
            b["requests"] += 1
        if r["username"]:
            b["users"].add(r["username"])
    now_iso = db._now()
    payload = [
        {"day": day,
         "requests": b["requests"],
         "users_json": json.dumps(sorted(b["users"]), separators=(",", ":")),
         "updated_at": now_iso}
        for day, b in buckets.items()
    ]
    with db.analytics_conn() as c:
        c.executemany(
            """INSERT INTO daily_stats(day, requests, users_json, updated_at)
               VALUES (:day, :requests, :users_json, :updated_at)
               ON CONFLICT(day) DO UPDATE SET
                   requests   = excluded.requests,
                   users_json = excluded.users_json,
                   updated_at = excluded.updated_at""",
            payload,
        )
        c.commit()
    return len(payload)


def query_growth(daily_n: int = 30, weekly_n: int = 12) -> dict:
    """Per-day and per-week unique users + request counts.

    Reads from daily_stats (the long-lived snapshot table) so historical
    numbers survive past the 14d event retention. Calls rollup_daily_stats
    first so today's partial-day numbers are fresh even between cron ticks.

    "Users" mirrors the active_users definition in query_summary — any
    kind in (request, render) counts as active. Weekly uniques are the
    set-union across the week's days (not a sum), so a user active on
    multiple days in the same week counts once.

    Returns:
        {"daily":  [{"day":  "YYYY-MM-DD", "users": int, "requests": int}, ...],  # oldest -> newest
         "weekly": [{"week": "GGGG-Www",   "users": int, "requests": int}, ...]}
    """
    rollup_daily_stats()
    now = int(time.time())
    with db.analytics_conn() as c:
        stat_rows = c.execute(
            "SELECT day, requests, users_json FROM daily_stats"
        ).fetchall()
    by_day: dict[str, dict] = {}
    for r in stat_rows:
        try:
            users = set(json.loads(r["users_json"]))
        except (ValueError, TypeError):
            users = set()
        by_day[r["day"]] = {"requests": int(r["requests"] or 0), "users": users}

    daily = []
    for i in range(daily_n - 1, -1, -1):
        d = time.strftime("%Y-%m-%d", time.gmtime(now - i * 86400))
        b = by_day.get(d)
        daily.append({
            "day": d,
            "requests": b["requests"] if b else 0,
            "users": len(b["users"]) if b else 0,
        })

    # Weekly: union across each ISO week's days. Stepping by 7 days from
    # `now` lands on a different calendar day each loop but always inside
    # the target ISO week, so %G-W%V correctly picks out one week per step.
    week_buckets: dict[str, dict] = {}
    for day, b in by_day.items():
        try:
            gm = time.strptime(day, "%Y-%m-%d")
        except ValueError:
            continue
        wk = time.strftime("%G-W%V", gm)
        wb = week_buckets.setdefault(wk, {"requests": 0, "users": set()})
        wb["requests"] += b["requests"]
        wb["users"].update(b["users"])
    weekly = []
    for i in range(weekly_n - 1, -1, -1):
        wk = time.strftime("%G-W%V", time.gmtime(now - i * 7 * 86400))
        wb = week_buckets.get(wk)
        weekly.append({
            "week": wk,
            "requests": wb["requests"] if wb else 0,
            "users": len(wb["users"]) if wb else 0,
        })
    return {"daily": daily, "weekly": weekly}


def query_latency() -> list[dict]:
    now = int(time.time())
    week_ago = now - 7 * 86400
    with db.analytics_conn() as c:
        top = c.execute(
            """SELECT endpoint, COUNT(*) AS n FROM events
               WHERE kind='request' AND ts >= ? AND endpoint IS NOT NULL
               GROUP BY endpoint ORDER BY n DESC LIMIT 12""",
            (week_ago,),
        ).fetchall()
        out = []
        for r in top:
            vals = [
                row["latency_ms"]
                for row in c.execute(
                    """SELECT latency_ms FROM events
                       WHERE kind='request' AND ts >= ? AND endpoint = ?""",
                    (week_ago, r["endpoint"]),
                ).fetchall()
            ]
            vals.sort()
            out.append({
                "endpoint": r["endpoint"],
                "count": r["n"],
                "p50": _percentile(vals, 50),
                "p95": _percentile(vals, 95),
                "p99": _percentile(vals, 99),
            })
    return out


def query_health() -> dict:
    now = int(time.time())
    week_ago = now - 7 * 86400
    with db.analytics_conn() as c:
        edge = c.execute(
            """SELECT SUM(CASE WHEN cache_hit=1 THEN 1 ELSE 0 END) AS hits,
                      COUNT(*) AS total
               FROM events WHERE service='edge' AND kind='request' AND ts >= ?""",
            (week_ago,),
        ).fetchone()
        fetcher = c.execute(
            """SELECT SUM(CASE WHEN status >= 400 THEN 1 ELSE 0 END) AS errs,
                      COUNT(*) AS total
               FROM events WHERE service='fetcher' AND kind='fetch' AND ts >= ?""",
            (week_ago,),
        ).fetchone()
        oldest = c.execute(
            "SELECT MIN(ts) AS oldest FROM events"
        ).fetchone()
    edge_total = (edge["total"] or 0)
    fetch_total = (fetcher["total"] or 0)
    return {
        "edge_cache_hit_rate": (edge["hits"] / edge_total) if edge_total else 0.0,
        "fetcher_error_rate": (fetcher["errs"] / fetch_total) if fetch_total else 0.0,
        "events_dropped_24h": _events_dropped,
        "oldest_event_ts": oldest["oldest"] if oldest and oldest["oldest"] else None,
    }


def prune_old(retention_days: int = _RETENTION_DAYS) -> int:
    # Align cutoff to UTC midnight: a day's events are either fully kept
    # or fully pruned. Without this, the rollup running after a prune
    # could observe a half-emptied day and overwrite daily_stats with
    # partial counts.
    import calendar
    target_day = time.gmtime(int(time.time()) - retention_days * 86400)
    cutoff = calendar.timegm((target_day.tm_year, target_day.tm_mon, target_day.tm_mday,
                              0, 0, 0, 0, 0, 0))
    deleted = 0
    with db.analytics_conn() as c:
        while True:
            cur = c.execute(
                "DELETE FROM events WHERE id IN ("
                "  SELECT id FROM events WHERE ts < ? LIMIT 5000)",
                (cutoff,),
            )
            c.commit()
            n = cur.rowcount or 0
            deleted += n
            if n < 5000:
                break
    return deleted
