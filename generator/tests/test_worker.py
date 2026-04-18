import os, tempfile, pytest
from unittest.mock import patch, MagicMock
from src import db as dbmod
from src import worker


@pytest.fixture
def tmp_dbs(monkeypatch):
    with tempfile.TemporaryDirectory() as d:
        monkeypatch.setattr(dbmod, "SETTINGS_DB_PATH", os.path.join(d, "s.db"))
        monkeypatch.setattr(dbmod, "WIDGETS_DB_PATH", os.path.join(d, "w.db"))
        dbmod.init_dbs()
        yield d


def test_process_one_renders_and_stores_widgets(tmp_dbs):
    dbmod.enroll("alice", {"theme": "dark", "enabled": ["grade"]})
    fake_payload = {"user": {"login": "alice"}, "repos": [], "events": [],
                    "commits": [], "total_commits": 0, "recent_commits": 0,
                    "total_prs": 0, "collaborators_data": [], "avatar_b64": ""}
    fake_data = {"grade": {"grade": "A", "score": 80, "stats": {}, "tags": [], "breakdown": {}}}
    with patch("src.worker.fetcher_client.get_data",
               return_value={"data": fake_payload, "payload_hash": "h1"}), \
         patch("src.worker._render_widgets",
               return_value={"composite": "<svg>c</svg>", "grade": "<svg>g</svg>"}), \
         patch("src.worker._compute_widget_data", return_value=fake_data):
        worker.process_one()
    svg = dbmod.get_current_widget("alice", "composite")
    assert svg == "<svg>c</svg>"
    # Data JSON is written alongside the SVGs so the /data endpoint is a lookup.
    row = dbmod.get_current_widget_data("alice")
    assert row is not None and row["data"] == fake_data


def test_not_found_payload_renders_not_found_placeholder(tmp_dbs):
    dbmod.enroll("ghost", {"theme": "dark"})
    with patch("src.worker.fetcher_client.get_data",
               return_value={"data": {"error": "not_found"}, "payload_hash": "x"}):
        worker.process_one()
    svg = dbmod.get_current_widget("ghost", "composite")
    assert svg and "ghost" in svg


def test_worker_retries_on_fetcher_failure(tmp_dbs):
    dbmod.enroll("alice", {"theme": "dark"})
    with patch("src.worker.fetcher_client.get_data", side_effect=RuntimeError("boom")):
        worker.process_one()
    with dbmod._settings_conn() as c:
        row = c.execute("SELECT status, attempts, last_error FROM jobs WHERE username='alice'").fetchone()
    assert row["status"] == "pending"
    assert row["attempts"] == 1
    assert "boom" in row["last_error"]


def test_worker_marks_failed_after_max_attempts(tmp_dbs):
    dbmod.enroll("alice", {"theme": "dark"})
    with patch("src.worker.fetcher_client.get_data", side_effect=RuntimeError("boom")):
        for _ in range(4):
            worker.process_one()
    with dbmod._settings_conn() as c:
        row = c.execute("SELECT status, attempts FROM jobs WHERE username='alice'").fetchone()
    assert row["status"] == "failed"
    assert row["attempts"] >= 3
