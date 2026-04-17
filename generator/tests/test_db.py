import os
import tempfile
import pytest
from src import db as dbmod


@pytest.fixture
def tmp_dbs(monkeypatch):
    with tempfile.TemporaryDirectory() as d:
        monkeypatch.setattr(dbmod, "SETTINGS_DB_PATH", os.path.join(d, "s.db"))
        monkeypatch.setattr(dbmod, "WIDGETS_DB_PATH", os.path.join(d, "w.db"))
        dbmod.init_dbs()
        yield d


def test_settings_hash_is_deterministic():
    h1 = dbmod.settings_hash({"theme": "dark", "widgets": ["a", "b"]})
    h2 = dbmod.settings_hash({"widgets": ["a", "b"], "theme": "dark"})
    assert h1 == h2


def test_enroll_and_get_settings(tmp_dbs):
    defaults = {"theme": "dark", "widgets": ["grade"]}
    job_id = dbmod.enroll("alice", defaults)
    assert job_id > 0
    s = dbmod.get_settings("alice")
    assert s["settings"] == defaults
    assert s["manual_refresh_used"] == 0


def test_enrollments_daily_counter(tmp_dbs):
    dbmod.enroll("alice", {"theme": "dark"})
    dbmod.enroll("bob", {"theme": "dark"})
    assert dbmod.enrollments_today() == 2


def test_update_settings_changes_hash(tmp_dbs):
    dbmod.enroll("alice", {"theme": "dark"})
    h_before = dbmod.get_settings("alice")["settings_hash"]
    dbmod.update_settings("alice", {"theme": "light"})
    h_after = dbmod.get_settings("alice")["settings_hash"]
    assert h_before != h_after


def test_claim_job_marks_running(tmp_dbs):
    job_id = dbmod.enroll("alice", {"theme": "dark"})
    job = dbmod.claim_next_job()
    assert job["id"] == job_id
    assert job["status"] == "running"
    assert dbmod.claim_next_job() is None  # already running


def test_complete_job(tmp_dbs):
    jid = dbmod.enroll("alice", {"theme": "dark"})
    dbmod.claim_next_job()
    dbmod.complete_job(jid)
    with dbmod._settings_conn() as c:
        status = c.execute("SELECT status FROM jobs WHERE id=?", (jid,)).fetchone()[0]
    assert status == "done"


def test_widgets_put_and_get(tmp_dbs):
    dbmod.put_widgets("alice", "hash1", {"composite": "<svg/>", "grade": "<svg/>"})
    row = dbmod.get_current_widget("alice", "composite")
    assert row == "<svg/>"


def test_current_widget_flips_atomically(tmp_dbs):
    dbmod.put_widgets("alice", "hash1", {"composite": "<svg>v1</svg>"})
    dbmod.put_widgets("alice", "hash2", {"composite": "<svg>v2</svg>"})
    assert dbmod.get_current_widget("alice", "composite") == "<svg>v2</svg>"


def test_lru_trim_keeps_n_newest(tmp_dbs):
    for i in range(12):
        dbmod.put_widgets("alice", f"hash{i}", {"composite": f"<svg>{i}</svg>"})
    dbmod.lru_trim("alice", keep=10)
    with dbmod._widgets_conn() as c:
        n = c.execute("SELECT COUNT(DISTINCT settings_hash) FROM widgets WHERE username='alice'").fetchone()[0]
    assert n == 10


def test_reclaim_stuck_running_jobs(tmp_dbs):
    jid = dbmod.enroll("alice", {"theme": "dark"})
    dbmod.claim_next_job()
    # Backdate updated_at to simulate dead worker
    with dbmod._settings_conn() as c:
        c.execute("UPDATE jobs SET updated_at='2020-01-01T00:00:00Z' WHERE id=?", (jid,))
        c.commit()
    dbmod.reclaim_stuck_jobs(older_than_minutes=10)
    job = dbmod.claim_next_job()
    assert job["id"] == jid
