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
