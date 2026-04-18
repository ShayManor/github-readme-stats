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


def test_process_one_stores_widget_data_without_rendering_svg(tmp_dbs):
    """Phase 1 worker only hydrates widget_data; SVGs are rendered by the
    /generate endpoint."""
    dbmod.enroll("alice", {"theme": "dark", "enabled": ["grade"]})
    fake_payload = {"user": {"login": "alice"}, "repos": [], "events": [],
                    "commits": [], "total_commits": 0, "recent_commits": 0,
                    "total_prs": 0, "collaborators_data": [], "avatar_b64": ""}
    fake_data = {"grade": {"grade": "A", "score": 80, "stats": {}, "tags": [], "breakdown": {}}}
    with patch("src.worker.fetcher_client.get_data",
               return_value={"data": fake_payload, "payload_hash": "h1"}), \
         patch("src.worker._compute_widget_data", return_value=fake_data):
        worker.process_one()
    # Widget data is stored for the client-side preview.
    row = dbmod.get_current_widget_data("alice")
    assert row is not None and row["data"] == fake_data
    # SVGs are NOT rendered yet — /generate hasn't been called.
    assert dbmod.get_current_widget("alice", "composite") is None


def test_render_widgets_now_produces_svg(tmp_dbs):
    """Phase 2: /generate endpoint path renders composite SVG on demand."""
    dbmod.enroll("alice", {"theme": "dark", "enabled": ["grade"]})
    fake_payload = {"user": {"login": "alice"}, "repos": [], "events": [],
                    "commits": [], "total_commits": 0, "recent_commits": 0,
                    "total_prs": 0, "collaborators_data": [], "avatar_b64": ""}
    with patch("src.worker.fetcher_client.get_data",
               return_value={"data": fake_payload, "payload_hash": "h1"}), \
         patch("src.worker._render_widgets",
               return_value={"composite": "<svg>c</svg>", "grade": "<svg>g</svg>"}):
        widgets = worker.render_widgets_now("alice")
    assert widgets["composite"] == "<svg>c</svg>"
    assert dbmod.get_current_widget("alice", "composite") == "<svg>c</svg>"


def test_not_found_payload_marks_not_found_in_data(tmp_dbs):
    """Worker records a not_found sentinel in widget_data; SVG placeholder
    is rendered at request time by /api/<u>, not by the worker."""
    dbmod.enroll("ghost", {"theme": "dark"})
    with patch("src.worker.fetcher_client.get_data",
               return_value={"data": {"error": "not_found"}, "payload_hash": "x"}):
        worker.process_one()
    assert dbmod.get_current_widget_hash("ghost") == "not_found"
    row = dbmod.get_current_widget_data("ghost")
    assert row is not None and row["data"] == {"not_found": True}


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
