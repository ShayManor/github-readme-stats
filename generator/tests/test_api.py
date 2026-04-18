import os, tempfile, pytest
from unittest.mock import patch
from src import db as dbmod
from src import api as apimod


@pytest.fixture
def client(monkeypatch):
    with tempfile.TemporaryDirectory() as d:
        monkeypatch.setattr(dbmod, "SETTINGS_DB_PATH", os.path.join(d, "s.db"))
        monkeypatch.setattr(dbmod, "WIDGETS_DB_PATH", os.path.join(d, "w.db"))
        dbmod.init_dbs()
        app = apimod.app
        app.config["TESTING"] = True
        with app.test_client() as c:
            yield c


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.get_json()["service"] == "generator"


def test_get_unknown_user_auto_enrolls_and_returns_placeholder(client):
    r = client.get("/api/alice")
    assert r.status_code == 200
    assert r.headers["X-Widget-Status"] == "building"
    assert "Building" in r.data.decode()
    assert dbmod.get_settings("alice") is not None


def test_rate_limit_returns_rate_limited_placeholder(client, monkeypatch):
    monkeypatch.setattr(apimod.config, "ENROLLMENT_DAILY_CAP", 1)
    client.get("/api/alice")
    r = client.get("/api/bob")
    assert r.headers["X-Widget-Status"] == "rate_limited"


def test_enrolled_user_with_built_widget_returns_ready(client):
    dbmod.enroll("alice", {"theme": "dark"})
    dbmod.put_widgets("alice", "h1", {"composite": "<svg>ready</svg>"})
    with dbmod._settings_conn() as c:
        c.execute("UPDATE users SET settings_hash='h1' WHERE username='alice'")
        c.commit()
    r = client.get("/api/alice")
    assert r.status_code == 200
    assert r.headers["X-Widget-Status"] == "ready"
    assert b"ready" in r.data


def test_settings_patch_enqueues_rebuild(client):
    dbmod.enroll("alice", {"theme": "dark"})
    r = client.patch("/api/alice/settings", json={"theme": "light"})
    assert r.status_code == 200
    assert dbmod.get_settings("alice")["settings"]["theme"] == "light"


def test_refresh_is_one_shot(client):
    dbmod.enroll("alice", {"theme": "dark"})
    with patch("src.api.fetcher_client.force_fetch", return_value={"changed": True, "payload_hash": "x", "stored": True}):
        r1 = client.post("/api/alice/refresh")
        assert r1.status_code == 200
        r2 = client.post("/api/alice/refresh")
        assert r2.status_code == 409


def test_not_found_status_header(client):
    dbmod.enroll("ghost", {"theme": "dark"})
    dbmod.put_widgets("ghost", "not_found", {"composite": "<svg>404</svg>"})
    with dbmod._settings_conn() as c:
        c.execute("UPDATE users SET settings_hash='not_found' WHERE username='ghost'")
        c.commit()
    r = client.get("/api/ghost")
    assert r.headers["X-Widget-Status"] == "not_found"


# ---- GET /api/<username>/data: computed widget data for client-side rendering ----

_FAKE_GITHUB_DATA = {
    "user": {"login": "alice", "followers": 10},
    "repos": [{"language": "Python", "stargazers_count": 5, "forks_count": 1, "topics": []}],
    "events": [],
    "commits": [],
    "total_commits": 42,
    "total_prs": 3,
    "recent_commits": 20,
}


def test_data_endpoint_auto_enrolls_and_returns_widget_data(client, monkeypatch):
    monkeypatch.setattr(
        apimod.fetcher_client, "get_data",
        lambda u: {"data": _FAKE_GITHUB_DATA, "payload_hash": "h1", "fetched": True},
    )
    r = client.get("/api/alice/data")
    assert r.status_code == 200
    body = r.get_json()
    assert "data" in body
    for key in ("grade", "impact", "collaborators", "focus", "languages"):
        assert key in body["data"]
    assert body["data"]["grade"]["grade"]  # non-empty letter grade
    assert dbmod.get_settings("alice") is not None  # auto-enrolled


def test_data_endpoint_returns_404_for_unknown_github_user(client, monkeypatch):
    monkeypatch.setattr(
        apimod.fetcher_client, "get_data",
        lambda u: {"data": {"error": "not_found"}, "payload_hash": "nf"},
    )
    r = client.get("/api/ghost/data")
    assert r.status_code == 404
    assert r.get_json()["error"] == "not_found"


def test_data_endpoint_502_when_fetcher_fails(client, monkeypatch):
    def boom(_u):
        raise RuntimeError("connection refused")
    monkeypatch.setattr(apimod.fetcher_client, "get_data", boom)
    r = client.get("/api/alice/data")
    assert r.status_code == 502


def test_data_endpoint_rate_limited_before_enroll(client, monkeypatch):
    monkeypatch.setattr(apimod.config, "ENROLLMENT_DAILY_CAP", 0)
    r = client.get("/api/newbie/data")
    assert r.status_code == 429
    assert r.get_json()["error"] == "rate_limited"
