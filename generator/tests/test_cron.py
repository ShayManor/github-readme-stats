import os, tempfile, pytest
from unittest.mock import patch
from src import db as dbmod
from src import cron as cronmod


@pytest.fixture
def tmp_dbs(monkeypatch):
    with tempfile.TemporaryDirectory() as d:
        monkeypatch.setattr(dbmod, "SETTINGS_DB_PATH", os.path.join(d, "s.db"))
        monkeypatch.setattr(dbmod, "WIDGETS_DB_PATH", os.path.join(d, "w.db"))
        dbmod.init_dbs()
        yield


def test_tick_enqueues_build_when_hash_changed(tmp_dbs):
    dbmod.enroll("alice", {"theme": "dark"})
    dbmod.set_last_fetcher_hash("alice", "old")
    with dbmod._settings_conn() as c:
        c.execute("DELETE FROM jobs")
        c.commit()
    with patch("src.cron.fetcher_client.get_data",
               return_value={"data": {}, "payload_hash": "new"}):
        stats = cronmod.tick()
    assert stats["enqueued"] == 1


def test_tick_skips_when_hash_unchanged(tmp_dbs):
    dbmod.enroll("alice", {"theme": "dark"})
    dbmod.set_last_fetcher_hash("alice", "same")
    with dbmod._settings_conn() as c:
        c.execute("DELETE FROM jobs")
        c.commit()
    with patch("src.cron.fetcher_client.get_data",
               return_value={"data": {}, "payload_hash": "same"}):
        stats = cronmod.tick()
    assert stats["enqueued"] == 0


def test_cron_tick_prunes_old_analytics(tmp_path, monkeypatch):
    import os, time
    from src import db as dbmod, analytics, cron

    monkeypatch.setattr(dbmod, "SETTINGS_DB_PATH", os.path.join(tmp_path, "s.db"))
    monkeypatch.setattr(dbmod, "WIDGETS_DB_PATH", os.path.join(tmp_path, "w.db"))
    monkeypatch.setattr(dbmod, "ANALYTICS_DB_PATH", os.path.join(tmp_path, "a.db"))
    dbmod.init_dbs()
    analytics.ingest_batch([
        {"ts": int(time.time()) - 30 * 86400, "service": "edge", "kind": "request",
         "username": "u", "endpoint": "/<u>", "widget": "composite",
         "status": 200, "latency_ms": 1, "cache_hit": 1},
    ])
    # tick() iterates enrolled users but there are none, so it returns
    # immediately — we only care that the prune call ran.
    cron.tick()
    with dbmod.analytics_conn() as c:
        n = c.execute("SELECT COUNT(*) AS n FROM events").fetchone()["n"]
    assert n == 0
