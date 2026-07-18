import os
import tempfile
import pytest
from unittest.mock import patch
from src import db as dbmod
from src import cron as cronmod
from src import github as ghmod


@pytest.fixture
def tmp_db(monkeypatch):
    with tempfile.TemporaryDirectory() as d:
        monkeypatch.setattr(dbmod, "DB_PATH", os.path.join(d, "t.db"))
        dbmod.init_db()
        yield


def test_refresh_tick_calls_github_for_due_users(tmp_db):
    dbmod.upsert_user("alice", {"user": {"login": "alice"}})
    # Backdate
    with dbmod._connect() as c:
        c.execute("UPDATE users SET fetched_at='2020-01-01T00:00:00Z', last_requested_at=? WHERE username='alice'",
                  (dbmod._now(),))
    with patch("src.cron.github.fetch_github_data", return_value={"user": {"login": "alice", "updated": True}}) as gh:
        stats = cronmod.tick(hours=24, active_within_days=7, gc_days=7)
    assert gh.called
    assert stats["refreshed"] == 1


def test_refresh_rate_limit_keeps_last_good_and_counts_metric(tmp_db):
    # A rate-limited refresh must NOT overwrite the cached row, and must be
    # counted as rate_limited so the monitoring stack can see it.
    dbmod.upsert_user("alice", {"user": {"login": "alice"}, "total_commits": 1841})
    with dbmod._connect() as c:
        c.execute("UPDATE users SET fetched_at='2020-01-01T00:00:00Z', last_requested_at=? WHERE username='alice'",
                  (dbmod._now(),))
    with patch("src.cron.github.fetch_github_data",
               side_effect=ghmod.GitHubTransientError("rate limited")):
        stats = cronmod.tick(hours=24, active_within_days=7, gc_days=7)
    assert stats["failed"] == 1 and stats["refreshed"] == 0
    # Last-good data retained.
    assert dbmod.get_user("alice")["data"]["total_commits"] == 1841
    assert dbmod.read_fetch_metrics()["rate_limited"] == 1


def test_tick_runs_gc_for_abandoned_trial_users(tmp_db):
    dbmod.upsert_user("ghost", {"user": {"login": "ghost"}})
    with dbmod._connect() as c:
        c.execute("UPDATE users SET last_requested_at='2020-01-01T00:00:00Z' WHERE username='ghost'")
    stats = cronmod.tick(hours=24, active_within_days=7, gc_days=7)
    assert stats["gc_removed"] == 1
    assert dbmod.get_user("ghost") is None
