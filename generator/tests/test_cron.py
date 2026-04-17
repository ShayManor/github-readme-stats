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
