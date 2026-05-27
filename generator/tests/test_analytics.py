import os, tempfile, time
import pytest
from src import db as dbmod
from src import analytics as a


@pytest.fixture
def fresh(monkeypatch):
    with tempfile.TemporaryDirectory() as d:
        monkeypatch.setattr(dbmod, "SETTINGS_DB_PATH", os.path.join(d, "s.db"))
        monkeypatch.setattr(dbmod, "WIDGETS_DB_PATH", os.path.join(d, "w.db"))
        monkeypatch.setattr(dbmod, "ANALYTICS_DB_PATH", os.path.join(d, "a.db"))
        dbmod.init_dbs()
        a._reset_for_tests()
        yield


def test_ingest_batch_writes_rows(fresh):
    n = a.ingest_batch([
        {"ts": 1000, "service": "edge", "kind": "request",
         "username": "alice", "endpoint": "/<u>", "widget": "composite",
         "status": 200, "latency_ms": 12, "cache_hit": 1},
        {"ts": 1001, "service": "edge", "kind": "request",
         "username": "bob", "endpoint": "/<u>", "widget": "composite",
         "status": 200, "latency_ms": 8, "cache_hit": 0},
    ])
    assert n == 2
    with dbmod.analytics_conn() as c:
        rows = c.execute("SELECT username, latency_ms FROM events ORDER BY ts").fetchall()
    assert [(r["username"], r["latency_ms"]) for r in rows] == [("alice", 12), ("bob", 8)]


def test_ingest_drops_bad_rows(fresh):
    n = a.ingest_batch([
        {"ts": 1, "service": "edge", "kind": "request", "latency_ms": 1},
        {"missing": "everything"},
        {"ts": 2, "service": "edge", "kind": "request", "latency_ms": "not-int"},
    ])
    assert n == 1


def test_record_render_flushes_to_db(fresh, monkeypatch):
    monkeypatch.setattr(a, "_FLUSH_SECONDS", 0.05)
    a.start_flush_thread()
    a.record_render("alice", "composite", 142)
    deadline = time.time() + 3
    row = None
    while time.time() < deadline:
        with dbmod.analytics_conn() as c:
            row = c.execute("SELECT * FROM events WHERE kind='render'").fetchone()
        if row:
            break
        time.sleep(0.05)
    assert row is not None
    assert row["username"] == "alice"
    assert row["widget"] == "composite"
    assert row["latency_ms"] == 142


def test_summary_aggregates_last_7d(fresh):
    now = int(time.time())
    rows = [
        {"ts": now - 60, "service": "edge", "kind": "request",
         "username": "alice", "endpoint": "/<u>", "widget": "composite",
         "status": 200, "latency_ms": 10, "cache_hit": 1},
        {"ts": now - 120, "service": "edge", "kind": "request",
         "username": "bob", "endpoint": "/<u>", "widget": "composite",
         "status": 200, "latency_ms": 50, "cache_hit": 0},
        {"ts": now - 10 * 86400, "service": "edge", "kind": "request",
         "username": "old", "endpoint": "/<u>", "widget": "composite",
         "status": 200, "latency_ms": 999, "cache_hit": 0},
        {"ts": now - 30, "service": "generator", "kind": "render",
         "username": "alice", "widget": "composite", "latency_ms": 200},
    ]
    a.ingest_batch(rows)
    s = a.query_summary()
    assert s["requests_7d"] == 2  # 'old' falls outside the 7d window
    assert s["active_users_7d"] == 2  # alice (edge+render dedup) + bob
    assert s["renders_7d"] == 1
    assert s["avg_render_ms"] == 200
    assert s["p50_ms"] in (10, 50)
    assert s["p95_ms"] == 50
    assert len(s["daily_requests"]) == 7


def test_query_users_returns_per_user_rows(fresh):
    now = int(time.time())
    a.ingest_batch([
        {"ts": now - 60, "service": "edge", "kind": "request",
         "username": "alice", "endpoint": "/<u>", "widget": "composite",
         "status": 200, "latency_ms": 10, "cache_hit": 1},
        {"ts": now - 30, "service": "edge", "kind": "request",
         "username": "alice", "endpoint": "/<u>/grade.svg", "widget": "grade",
         "status": 200, "latency_ms": 20, "cache_hit": 1},
        {"ts": now - 10, "service": "edge", "kind": "request",
         "username": "alice", "endpoint": "/<u>", "widget": "composite",
         "status": 200, "latency_ms": 30, "cache_hit": 1},
    ])
    users = a.query_users()
    assert len(users) == 1
    u = users[0]
    assert u["username"] == "alice"
    assert u["requests_7d"] == 3
    assert u["top_endpoint"] == "/<u>"
    assert u["avg_latency_ms"] == 20


def test_query_latency_returns_percentiles(fresh):
    now = int(time.time())
    a.ingest_batch([
        {"ts": now - 1, "service": "edge", "kind": "request",
         "username": "u", "endpoint": "/<u>", "widget": "composite",
         "status": 200, "latency_ms": v, "cache_hit": 1}
        for v in range(1, 101)
    ])
    rows = a.query_latency()
    by_ep = {r["endpoint"]: r for r in rows}
    assert by_ep["/<u>"]["count"] == 100
    assert by_ep["/<u>"]["p50"] == 50
    assert by_ep["/<u>"]["p95"] == 95
    assert by_ep["/<u>"]["p99"] == 99


def test_query_growth_buckets_by_day_and_week(fresh):
    now = int(time.time())
    a.ingest_batch([
        # Today: alice (2 requests), bob (1 request), carol (render only)
        {"ts": now - 60, "service": "edge", "kind": "request",
         "username": "alice", "endpoint": "/<u>", "widget": "composite",
         "status": 200, "latency_ms": 10, "cache_hit": 1},
        {"ts": now - 120, "service": "edge", "kind": "request",
         "username": "alice", "endpoint": "/<u>", "widget": "composite",
         "status": 200, "latency_ms": 10, "cache_hit": 1},
        {"ts": now - 180, "service": "edge", "kind": "request",
         "username": "bob", "endpoint": "/<u>", "widget": "composite",
         "status": 200, "latency_ms": 10, "cache_hit": 1},
        {"ts": now - 240, "service": "generator", "kind": "render",
         "username": "carol", "widget": "composite", "latency_ms": 100},
        # 10 days ago: dave (1 request) — outside the 30d window's start
        # would still land in the daily bucket if within range
        {"ts": now - 10 * 86400, "service": "edge", "kind": "request",
         "username": "dave", "endpoint": "/<u>", "widget": "composite",
         "status": 200, "latency_ms": 10, "cache_hit": 1},
    ])
    g = a.query_growth(daily_n=30, weekly_n=12)
    assert len(g["daily"]) == 30
    assert len(g["weekly"]) == 12
    # Today = last entry. Requests count only kind='request', users include
    # render-only callers — matching active_users_7d's definition.
    today = g["daily"][-1]
    assert today["requests"] == 3
    assert today["users"] == 3  # alice, bob, carol
    # 10-day-ago bucket has dave's single request
    ten_days_ago = g["daily"][-11]
    assert ten_days_ago["requests"] == 1
    assert ten_days_ago["users"] == 1
    # Current week (last weekly entry) includes today's traffic
    assert g["weekly"][-1]["requests"] >= 3
    assert g["weekly"][-1]["users"] >= 3


def test_growth_numbers_survive_event_prune(fresh):
    """The whole point of daily_stats: per-day counts must persist even
    after their underlying events get pruned past the retention window."""
    now = int(time.time())
    twenty_days_ago = now - 20 * 86400
    a.ingest_batch([
        {"ts": twenty_days_ago, "service": "edge", "kind": "request",
         "username": "alice", "endpoint": "/<u>", "widget": "composite",
         "status": 200, "latency_ms": 10, "cache_hit": 1},
        {"ts": twenty_days_ago + 60, "service": "edge", "kind": "request",
         "username": "bob", "endpoint": "/<u>", "widget": "composite",
         "status": 200, "latency_ms": 10, "cache_hit": 1},
        {"ts": twenty_days_ago + 120, "service": "edge", "kind": "request",
         "username": "alice", "endpoint": "/<u>", "widget": "composite",
         "status": 200, "latency_ms": 10, "cache_hit": 1},
    ])
    a.rollup_daily_stats()
    pruned = a.prune_old(retention_days=14)
    assert pruned == 3  # all three events were older than 14 days

    g = a.query_growth(daily_n=30, weekly_n=12)
    target_day = time.strftime("%Y-%m-%d", time.gmtime(twenty_days_ago))
    bucket = next(d for d in g["daily"] if d["day"] == target_day)
    assert bucket["requests"] == 3
    assert bucket["users"] == 2  # alice (deduped) + bob


def test_weekly_uniques_dedupe_across_days(fresh):
    """A user active on multiple days within the same ISO week counts
    once for that week — set union, not sum-of-daily-uniques."""
    now = int(time.time())
    # Pin to a known weekday so all three timestamps land in the same ISO week.
    # Monday-ish: subtract `weekday` days from now to land near Mon, then offset.
    monday = now - time.gmtime(now).tm_wday * 86400 + 12 * 3600  # noon UTC Monday
    a.ingest_batch([
        {"ts": monday, "service": "edge", "kind": "request",
         "username": "alice", "endpoint": "/<u>", "widget": "composite",
         "status": 200, "latency_ms": 10, "cache_hit": 1},
        {"ts": monday + 86400, "service": "edge", "kind": "request",
         "username": "alice", "endpoint": "/<u>", "widget": "composite",
         "status": 200, "latency_ms": 10, "cache_hit": 1},
        {"ts": monday + 2 * 86400, "service": "edge", "kind": "request",
         "username": "bob", "endpoint": "/<u>", "widget": "composite",
         "status": 200, "latency_ms": 10, "cache_hit": 1},
    ])
    g = a.query_growth(daily_n=30, weekly_n=12)
    target_week = time.strftime("%G-W%V", time.gmtime(monday))
    week_row = next(w for w in g["weekly"] if w["week"] == target_week)
    assert week_row["requests"] == 3
    assert week_row["users"] == 2  # alice (Mon+Tue) deduped + bob (Wed)


def test_query_health(fresh):
    now = int(time.time())
    a.ingest_batch([
        {"ts": now - 1, "service": "edge", "kind": "request",
         "username": "u", "endpoint": "/<u>", "widget": "composite",
         "status": 200, "latency_ms": 1, "cache_hit": 1},
        {"ts": now - 2, "service": "edge", "kind": "request",
         "username": "u", "endpoint": "/<u>", "widget": "composite",
         "status": 200, "latency_ms": 1, "cache_hit": 0},
        {"ts": now - 3, "service": "fetcher", "kind": "fetch",
         "username": "u", "endpoint": "github/users/<u>",
         "status": 500, "latency_ms": 100},
        {"ts": now - 4, "service": "fetcher", "kind": "fetch",
         "username": "u", "endpoint": "github/users/<u>",
         "status": 200, "latency_ms": 100},
    ])
    h = a.query_health()
    assert abs(h["edge_cache_hit_rate"] - 0.5) < 1e-6
    assert abs(h["fetcher_error_rate"] - 0.5) < 1e-6
    assert h["events_dropped_24h"] == 0


def test_prune_drops_old_events(fresh):
    now = int(time.time())
    a.ingest_batch([
        {"ts": now - 20 * 86400, "service": "edge", "kind": "request",
         "username": "u", "endpoint": "/<u>", "widget": "composite",
         "status": 200, "latency_ms": 1, "cache_hit": 1},
        {"ts": now, "service": "edge", "kind": "request",
         "username": "u", "endpoint": "/<u>", "widget": "composite",
         "status": 200, "latency_ms": 1, "cache_hit": 1},
    ])
    deleted = a.prune_old(retention_days=14)
    assert deleted == 1
    with dbmod.analytics_conn() as c:
        n = c.execute("SELECT COUNT(*) AS n FROM events").fetchone()["n"]
    assert n == 1


def test_queue_drops_when_full_and_counts(fresh, monkeypatch):
    monkeypatch.setattr(a, "_QUEUE_MAX", 3)
    a._reset_for_tests()
    for i in range(10):
        a.record_render("u", "composite", i)
    assert a._events_dropped == 7


def test_query_users_includes_render_only_users(fresh):
    """Render-only users (worker fired but no edge traffic yet) must still
    appear in the table — without this, `active_users_7d` says N while the
    table looks empty, which reads as a bug."""
    now = int(time.time())
    a.ingest_batch([
        {"ts": now - 60, "service": "generator", "kind": "render",
         "username": "alice", "widget": "composite", "latency_ms": 200},
    ])
    users = a.query_users()
    assert len(users) == 1
    u = users[0]
    assert u["username"] == "alice"
    assert u["requests_7d"] == 0      # no request events yet
    assert u["last_seen"] == now - 60
    assert u["avg_latency_ms"] == 0   # latency only averages request events
