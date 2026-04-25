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


def test_process_one_stores_widget_data_and_renders_svg(tmp_dbs):
    """The cron-driven worker must hydrate widget_data AND render SVGs so
    embedded widgets stay fresh as the fetcher rotates the payload — not
    just when the user clicks Generate."""
    dbmod.enroll("alice", {"theme": "dark", "enabled": ["grade"]})
    fake_payload = {"user": {"login": "alice"}, "repos": [], "events": [],
                    "commits": [], "total_commits": 0, "recent_commits": 0,
                    "total_prs": 0, "collaborators_data": [], "avatar_b64": ""}
    fake_data = {"grade": {"grade": "A", "score": 80, "stats": {}, "tags": [], "breakdown": {}}}
    with patch("src.worker.fetcher_client.get_data",
               return_value={"data": fake_payload, "payload_hash": "h1"}), \
         patch("src.worker._compute_widget_data", return_value=fake_data), \
         patch("src.worker._render_widgets",
               return_value={"composite": "<svg>c</svg>", "grade": "<svg>g</svg>"}):
        worker.process_one()
    row = dbmod.get_current_widget_data("alice")
    assert row is not None and row["data"] == fake_data
    assert dbmod.get_current_widget("alice", "composite") == "<svg>c</svg>"
    assert dbmod.get_current_widget("alice", "grade") == "<svg>g</svg>"


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


def test_process_one_persists_streak(tmp_dbs):
    """Phase 1 worker must compute and persist the user's streak so max survives
    future settings changes."""
    from datetime import date, timedelta

    today = date.today()
    dates = [today - timedelta(days=i) for i in range(3)]
    dbmod.enroll("alice", {"theme": "dark", "enabled": ["streaks"]})
    fake_payload = {
        "user": {"login": "alice"}, "repos": [], "events": [],
        "commits": [{"date": d.isoformat(), "count": 1} for d in dates],
        "total_commits": 3, "recent_commits": 3, "total_prs": 0,
        "collaborators_data": [], "avatar_b64": "",
    }
    with patch("src.worker.fetcher_client.get_data",
               return_value={"data": fake_payload, "payload_hash": "h1"}):
        worker.process_one()

    row = dbmod.get_user_streak("alice")
    assert row is not None
    assert row["current_streak"] == 3
    assert row["max_streak"] == 3
    assert row["last_active_date"] == today.isoformat()


def test_process_one_refreshes_streak_svg_when_payload_changes(tmp_dbs):
    """Regression: the streak SVG must reflect the latest payload after the
    cron-driven worker runs, even when settings_hash hasn't changed. The bug
    was that process_one only updated widget_data and left the SVG frozen at
    whatever the last /generate call rendered, so streak counters stayed
    stuck for days."""
    from datetime import date, timedelta

    today = date.today()
    dbmod.enroll("alice", {"theme": "dark", "enabled": ["streaks"]})

    # Day 1: 1 day of activity → streak SVG renders "1".
    payload_v1 = {
        "user": {"login": "alice"}, "repos": [], "events": [],
        "commits": [{"date": today.isoformat(), "count": 1}],
        "total_commits": 1, "recent_commits": 1, "total_prs": 0,
        "collaborators_data": [], "avatar_b64": "",
    }
    with patch("src.worker.fetcher_client.get_data",
               return_value={"data": payload_v1, "payload_hash": "h1"}):
        worker.process_one()
    svg_v1 = dbmod.get_current_widget("alice", "streaks")
    assert svg_v1 is not None and ">1<" in svg_v1

    # Day 2: 2 days of activity → enqueue a fresh job, re-run worker.
    dbmod.enqueue_build("alice")
    payload_v2 = {
        "user": {"login": "alice"}, "repos": [], "events": [],
        "commits": [{"date": (today - timedelta(days=i)).isoformat(), "count": 1}
                    for i in range(2)],
        "total_commits": 2, "recent_commits": 2, "total_prs": 0,
        "collaborators_data": [], "avatar_b64": "",
    }
    with patch("src.worker.fetcher_client.get_data",
               return_value={"data": payload_v2, "payload_hash": "h2"}):
        worker.process_one()
    svg_v2 = dbmod.get_current_widget("alice", "streaks")
    assert svg_v2 is not None
    assert ">2<" in svg_v2, "streak SVG should reflect the new 2-day streak"
    assert svg_v1 != svg_v2, "SVG must change when payload changes"


def test_process_one_merges_stored_max(tmp_dbs):
    """A stored max of 50 must survive a refresh whose window max is only 2."""
    from datetime import date, timedelta

    today = date.today()
    dbmod.enroll("alice", {"theme": "dark", "enabled": ["streaks"]})
    dbmod.put_user_streak("alice", {
        "current_streak": 0, "current_start": "",
        "last_active_date": "2023-01-15",
        "max_streak": 50,
        "max_start": "2023-01-01", "max_end": "2023-02-19",
    })

    dates = [today - timedelta(days=i) for i in range(2)]
    fake_payload = {
        "user": {"login": "alice"}, "repos": [], "events": [],
        "commits": [{"date": d.isoformat(), "count": 1} for d in dates],
        "total_commits": 2, "recent_commits": 2, "total_prs": 0,
        "collaborators_data": [], "avatar_b64": "",
    }
    with patch("src.worker.fetcher_client.get_data",
               return_value={"data": fake_payload, "payload_hash": "h1"}):
        worker.process_one()

    row = dbmod.get_user_streak("alice")
    assert row["max_streak"] == 50
    assert row["max_start"] == "2023-01-01"
    assert row["current_streak"] == 2
