"""Unit tests for auth helpers (no network)."""
import pytest
from flask import Flask, jsonify

from src import auth, config


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setattr(config, "ALLOWED_ORIGINS", ("https://gh-stats.com",))
    app = Flask(__name__)
    app.secret_key = "test-secret"

    @app.route("/protected/<username>", methods=["POST"])
    @auth.require_same_origin
    @auth.require_github_owner
    def protected(username):
        return jsonify({"ok": True, "you": auth.current_login()})

    return app


def _good_hdrs():
    return {"Origin": "https://gh-stats.com"}


def test_current_login_none_by_default(app):
    with app.test_request_context("/"):
        assert auth.current_login() is None


def test_require_github_owner_401_without_session(app):
    with app.test_client() as c:
        r = c.post("/protected/alice", headers=_good_hdrs())
    assert r.status_code == 401
    assert r.get_json()["error"] == "login_required"


def test_require_github_owner_403_on_mismatch(app):
    with app.test_client() as c:
        with c.session_transaction() as s:
            s["gh_login"] = "bob"
        r = c.post("/protected/alice", headers=_good_hdrs())
    assert r.status_code == 403


def test_require_github_owner_passes_with_matching_login(app):
    with app.test_client() as c:
        with c.session_transaction() as s:
            s["gh_login"] = "Alice"  # stored mixed-case on purpose
        r = c.post("/protected/alice", headers=_good_hdrs())
    assert r.status_code == 200
    assert r.get_json()["you"] == "alice"


def test_require_same_origin_rejects_bad_origin(app):
    with app.test_client() as c:
        with c.session_transaction() as s:
            s["gh_login"] = "alice"
        r = c.post("/protected/alice", headers={"Origin": "https://evil.example"})
    assert r.status_code == 403


def test_require_same_origin_rejects_missing_origin(app):
    with app.test_client() as c:
        with c.session_transaction() as s:
            s["gh_login"] = "alice"
        r = c.post("/protected/alice")
    assert r.status_code == 403


from src import api as api_module


@pytest.fixture
def api_client(monkeypatch, tmp_path):
    # Point DBs at tmp + configure origins.
    from src import db as dbmod, config as cfg
    monkeypatch.setattr(cfg, "SETTINGS_DB_PATH", str(tmp_path / "s.db"))
    monkeypatch.setattr(cfg, "WIDGETS_DB_PATH", str(tmp_path / "w.db"))
    monkeypatch.setattr(dbmod, "SETTINGS_DB_PATH", str(tmp_path / "s.db"))
    monkeypatch.setattr(dbmod, "WIDGETS_DB_PATH", str(tmp_path / "w.db"))
    dbmod.init_dbs()
    monkeypatch.setattr(cfg, "ALLOWED_ORIGINS", ("https://gh-stats.com",))
    api_module.app.config["TESTING"] = True
    api_module.app.config["SESSION_COOKIE_SECURE"] = False
    return api_module.app.test_client()


def test_me_unauthed_returns_null(api_client):
    r = api_client.get("/api/auth/me")
    assert r.status_code == 200
    assert r.get_json() == {"login": None}


def test_me_authed_returns_login(api_client):
    with api_client.session_transaction() as s:
        s["gh_login"] = "alice"
        s["gh_avatar_url"] = "https://x/a.png"
    r = api_client.get("/api/auth/me")
    assert r.status_code == 200
    j = r.get_json()
    assert j["login"] == "alice"
    assert j["avatar_url"] == "https://x/a.png"


def test_logout_clears_session(api_client):
    with api_client.session_transaction() as s:
        s["gh_login"] = "alice"
    r = api_client.post("/api/auth/logout", headers={"Origin": "https://gh-stats.com"})
    assert r.status_code == 204
    r = api_client.get("/api/auth/me")
    assert r.get_json()["login"] is None


def test_logout_rejects_bad_origin(api_client):
    with api_client.session_transaction() as s:
        s["gh_login"] = "alice"
    r = api_client.post("/api/auth/logout", headers={"Origin": "https://evil.example"})
    assert r.status_code == 403


def test_login_stashes_state_and_redirects(api_client):
    """Don't depend on authlib's exact redirect URL — just confirm the route
    stashes a random state, records the next path, and returns a 3xx."""
    r = api_client.get("/api/auth/github/login?next=/workshop")
    assert r.status_code in (302, 303)
    with api_client.session_transaction() as s:
        assert s.get("oauth_state")
        assert s.get("oauth_next") == "/workshop"


def test_login_rejects_external_next(api_client):
    r = api_client.get("/api/auth/github/login?next=https://evil.example/foo")
    assert r.status_code in (302, 303)
    with api_client.session_transaction() as s:
        assert s.get("oauth_next") == "/"
