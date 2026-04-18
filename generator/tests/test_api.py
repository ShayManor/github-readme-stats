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


# ---- GET /api/<username>/data: precomputed widget data for client-side rendering ----
# Pure DB lookup — fetcher is never touched on the hot path.


def test_data_endpoint_unknown_user_enrolls_and_returns_building(client):
    r = client.get("/api/alice/data")
    assert r.status_code == 202
    assert r.get_json() == {"status": "building"}
    assert dbmod.get_settings("alice") is not None  # auto-enrolled


def test_data_endpoint_enrolled_but_unbuilt_returns_building(client):
    dbmod.enroll("alice", {"theme": "dark"})
    r = client.get("/api/alice/data")
    assert r.status_code == 202
    assert r.get_json() == {"status": "building"}


def test_data_endpoint_returns_ready_after_build(client):
    dbmod.enroll("alice", {"theme": "dark"})
    sample = {"grade": {"grade": "A", "score": 80, "stats": {}, "tags": [], "breakdown": {}}}
    dbmod.put_widget_data("alice", "h1", sample)
    with dbmod._widgets_conn() as c:
        c.execute(
            """INSERT INTO current_widget(username, settings_hash, updated_at)
               VALUES ('alice', 'h1', '2026-04-18T00:00:00Z')
               ON CONFLICT(username) DO UPDATE SET settings_hash=excluded.settings_hash""")
        c.commit()
    r = client.get("/api/alice/data")
    assert r.status_code == 200
    body = r.get_json()
    assert body["status"] == "ready"
    assert body["data"] == sample


def test_data_endpoint_returns_not_found_for_unknown_github_user(client):
    dbmod.enroll("ghost", {"theme": "dark"})
    dbmod.put_widget_data("ghost", "not_found", {"not_found": True})
    with dbmod._widgets_conn() as c:
        c.execute(
            """INSERT INTO current_widget(username, settings_hash, updated_at)
               VALUES ('ghost', 'not_found', '2026-04-18T00:00:00Z')
               ON CONFLICT(username) DO UPDATE SET settings_hash=excluded.settings_hash""")
        c.commit()
    r = client.get("/api/ghost/data")
    assert r.status_code == 404
    assert r.get_json()["status"] == "not_found"


def test_data_endpoint_rate_limited_before_enroll(client, monkeypatch):
    monkeypatch.setattr(apimod.config, "ENROLLMENT_DAILY_CAP", 0)
    r = client.get("/api/newbie/data")
    assert r.status_code == 429
    assert r.get_json()["status"] == "rate_limited"
