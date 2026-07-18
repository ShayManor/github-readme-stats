import os
import tempfile
import pytest
from src import db as dbmod


@pytest.fixture
def tmp_db(monkeypatch):
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "t.db")
        monkeypatch.setattr(dbmod, "DB_PATH", path)
        dbmod.init_db()
        yield path


def test_init_creates_schema_with_wal(tmp_db):
    with dbmod._connect() as c:
        mode = c.execute("PRAGMA journal_mode").fetchone()[0]
        assert mode.lower() == "wal"
        cols = [r[1] for r in c.execute("PRAGMA table_info(users)").fetchall()]
        assert set(cols) == {"username", "data_json", "payload_hash",
                             "fetched_at", "last_requested_at"}


def test_upsert_and_get_round_trip(tmp_db):
    dbmod.upsert_user("alice", {"user": {"login": "alice"}, "repos": []})
    row = dbmod.get_user("alice")
    assert row["data"]["user"]["login"] == "alice"
    assert row["payload_hash"]
    assert row["fetched_at"]


def test_fetch_metrics_round_trip(tmp_db):
    # Zero-filled for every known outcome before anything is recorded.
    assert dbmod.read_fetch_metrics() == {o: 0 for o in dbmod.FETCH_OUTCOMES}
    dbmod.bump_fetch_metric("ok")
    dbmod.bump_fetch_metric("ok")
    dbmod.bump_fetch_metric("rate_limited")
    counts = dbmod.read_fetch_metrics()
    assert counts["ok"] == 2
    assert counts["rate_limited"] == 1
    assert counts["not_found"] == 0


def test_fetch_metric_unknown_outcome_buckets_to_error(tmp_db):
    dbmod.bump_fetch_metric("bogus")
    assert dbmod.read_fetch_metrics()["error"] == 1


def test_payload_hash_is_deterministic_and_changes_on_diff():
    h1 = dbmod.payload_hash({"a": 1, "b": 2})
    h2 = dbmod.payload_hash({"b": 2, "a": 1})
    h3 = dbmod.payload_hash({"a": 1, "b": 3})
    assert h1 == h2
    assert h1 != h3


def test_get_updates_last_requested_at(tmp_db):
    dbmod.upsert_user("alice", {"user": {"login": "alice"}})
    first = dbmod.get_user("alice")["last_requested_at"]
    import time; time.sleep(1.1)
    second = dbmod.get_user("alice")["last_requested_at"]
    assert second > first


def test_delete_stale_removes_old_rows(tmp_db):
    dbmod.upsert_user("ghost", {"user": {"login": "ghost"}})
    # Manually backdate last_requested_at
    with dbmod._connect() as c:
        c.execute("UPDATE users SET last_requested_at='2020-01-01T00:00:00Z' WHERE username='ghost'")
    removed = dbmod.delete_stale(days=7)
    assert removed == 1
    assert dbmod.get_user("ghost") is None


def test_users_due_for_refresh(tmp_db):
    dbmod.upsert_user("alice", {"user": {"login": "alice"}})
    # Backdate fetched_at so alice is due
    with dbmod._connect() as c:
        c.execute("UPDATE users SET fetched_at='2020-01-01T00:00:00Z' WHERE username='alice'")
    due = dbmod.users_due_for_refresh(hours=24, active_within_days=7)
    assert "alice" in due
