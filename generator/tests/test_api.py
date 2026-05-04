import os, tempfile, pytest
from unittest.mock import patch
from src import db as dbmod
from src import api as apimod
from src import config as cfg


@pytest.fixture
def client(monkeypatch):
    # No-op the kickoff so tests don't spawn background threads that
    # would try to reach the (unmocked) fetcher and race tempdir teardown.
    monkeypatch.setattr(apimod, "_kickoff_prefetch_async", lambda *_a, **_kw: None)
    # Same reason for the new async-fetch hook used by the OAuth callback.
    monkeypatch.setattr(apimod, "_request_fetch_async", lambda *_a, **_kw: None)
    with tempfile.TemporaryDirectory() as d:
        monkeypatch.setattr(dbmod, "SETTINGS_DB_PATH", os.path.join(d, "s.db"))
        monkeypatch.setattr(dbmod, "WIDGETS_DB_PATH", os.path.join(d, "w.db"))
        dbmod.init_dbs()
        # Configure OAuth fixture with allowed origins and insecure cookies for testing.
        monkeypatch.setattr(cfg, "ALLOWED_ORIGINS", ("https://gh-stats.com",))
        app = apimod.app
        app.config["TESTING"] = True
        app.config["SESSION_COOKIE_SECURE"] = False
        with app.test_client() as c:
            yield c
    # Clear rate limit state after each test to prevent pollution.
    apimod._rate_hits.clear()
    apimod._rate_hits_per_login.clear()


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.get_json()["service"] == "generator"


def test_root_with_username_param_force_renders_grade_widget(client, monkeypatch):
    """`GET /?username=<u>` auto-enrolls and returns just the grade widget SVG,
    force-generated from fresh fetcher data. No composite, no other widgets."""
    from src.models import GradeData
    monkeypatch.setattr(
        "src.api.fetcher_client.get_data",
        lambda u: {"data": {"user": {}, "repos": [], "events": []}, "payload_hash": "h"},
    )
    monkeypatch.setattr(
        "src.api.processor.compute_grade",
        lambda *a, **kw: GradeData(grade="A", score=88.0, stats={}, tags=[]),
    )
    monkeypatch.setattr("src.api.render_grade_widget", lambda *a, **kw: "<svg id='grade'/>")
    r = client.get("/?username=alice")
    assert r.status_code == 200
    assert r.mimetype == "image/svg+xml"
    assert r.headers["X-Widget-Status"] == "ready"
    assert dbmod.get_settings("alice") is not None
    body = r.data.decode()
    assert "<svg" in body
    assert "composite" not in body


def test_api_with_username_param_also_works(client, monkeypatch):
    """Same shortcut is available at `/api/?username=<u>` so the /api prefix
    stays consistent for callers that expect it."""
    from src.models import GradeData
    monkeypatch.setattr(
        "src.api.fetcher_client.get_data",
        lambda u: {"data": {"user": {}, "repos": [], "events": []}, "payload_hash": "h"},
    )
    monkeypatch.setattr(
        "src.api.processor.compute_grade",
        lambda *a, **kw: GradeData(grade="A", score=88.0, stats={}, tags=[]),
    )
    monkeypatch.setattr("src.api.render_grade_widget", lambda *a, **kw: "<svg id='grade'/>")
    r = client.get("/api/?username=bob")
    assert r.status_code == 200
    assert r.mimetype == "image/svg+xml"
    assert r.headers["X-Widget-Status"] == "ready"


def test_root_without_username_serves_spa(client):
    """Plain `/` still returns the SPA (or the 'frontend not built' fallback
    in test, where static assets aren't bundled)."""
    r = client.get("/")
    # Either 200 (static built) or 503 (not built) — the important thing is we
    # don't accidentally route to the grade-widget handler.
    assert r.status_code in (200, 503)
    assert r.mimetype != "image/svg+xml"


def test_get_unknown_user_returns_building_placeholder_without_enrolling(client):
    """The SVG endpoint is for README embeds — enrollment is frontend-driven
    through /data or /api/enroll, so GET /api/<u> does not auto-enroll."""
    r = client.get("/api/alice")
    assert r.status_code == 200
    assert r.headers["X-Widget-Status"] == "building"
    assert "Building" in r.data.decode()
    assert dbmod.get_settings("alice") is None


def test_enrolled_but_not_generated_returns_building(client):
    """After enrollment (via /data) but before /generate is clicked the SVG
    endpoint returns a building placeholder."""
    dbmod.enroll("alice", {"theme": "dark"})
    r = client.get("/api/alice")
    assert r.headers["X-Widget-Status"] == "building"


def test_enrolled_user_with_built_widget_returns_ready(client):
    dbmod.enroll("alice", {"theme": "dark"})
    dbmod.put_widgets("alice", "h1", {"composite": "<svg>ready</svg>"})
    dbmod.point_current_widget("alice", "h1")
    r = client.get("/api/alice")
    assert r.status_code == 200
    assert r.headers["X-Widget-Status"] == "ready"
    assert b"ready" in r.data


def test_settings_patch_enqueues_rebuild(client):
    dbmod.enroll("alice", {"theme": "dark"})
    with client.session_transaction() as s:
        s["gh_login"] = "alice"
    r = client.patch(
        "/api/alice/settings",
        json={"theme": "light"},
        headers={"Origin": "https://gh-stats.com"},
    )
    assert r.status_code == 200
    assert dbmod.get_settings("alice")["settings"]["theme"] == "light"


def test_settings_patch_without_origin_is_unauthorized(client):
    dbmod.enroll("alice", {"theme": "dark"})
    with client.session_transaction() as s:
        s["gh_login"] = "alice"
    r = client.patch("/api/alice/settings", json={"theme": "light"})
    assert r.status_code == 403
    # Settings must not be mutated when the origin check fails.
    assert dbmod.get_settings("alice")["settings"]["theme"] == "dark"


def test_patch_settings_without_session_is_401(client):
    dbmod.enroll("alice", {"theme": "dark"})
    r = client.patch("/api/alice/settings", json={"theme": "light"},
                     headers={"Origin": "https://gh-stats.com"})
    assert r.status_code == 401


def test_patch_settings_wrong_login_is_403(client):
    dbmod.enroll("alice", {"theme": "dark"})
    with client.session_transaction() as s:
        s["gh_login"] = "bob"
    r = client.patch("/api/alice/settings", json={"theme": "light"},
                     headers={"Origin": "https://gh-stats.com"})
    assert r.status_code == 403


def test_patch_settings_matching_login_succeeds(client):
    dbmod.enroll("alice", {"theme": "dark"})
    with client.session_transaction() as s:
        s["gh_login"] = "alice"
    r = client.patch("/api/alice/settings", json={"theme": "light"},
                     headers={"Origin": "https://gh-stats.com"})
    assert r.status_code == 200


def test_patch_settings_bad_origin_is_403(client):
    dbmod.enroll("alice", {"theme": "dark"})
    with client.session_transaction() as s:
        s["gh_login"] = "alice"
    r = client.patch("/api/alice/settings", json={"theme": "light"},
                     headers={"Origin": "https://evil.example"})
    assert r.status_code == 403


def test_refresh_is_one_shot(client):
    dbmod.enroll("alice", {"theme": "dark"})
    with client.session_transaction() as s:
        s["gh_login"] = "alice"
    with patch("src.api.fetcher_client.force_fetch", return_value={"changed": True, "payload_hash": "x", "stored": True}):
        r1 = client.post("/api/alice/refresh", headers={"Origin": "https://gh-stats.com"})
        assert r1.status_code == 200
        r2 = client.post("/api/alice/refresh", headers={"Origin": "https://gh-stats.com"})
        assert r2.status_code == 409


def test_refresh_without_token_is_unauthorized(client):
    """Old test name; now tests without session but with proper Origin."""
    dbmod.enroll("alice", {"theme": "dark"})
    r = client.post("/api/alice/refresh", headers={"Origin": "https://gh-stats.com"})
    assert r.status_code == 401


def test_not_found_status_header(client):
    dbmod.enroll("ghost", {"theme": "dark"})
    dbmod.put_widgets("ghost", "not_found", {"composite": "<svg>404</svg>"})
    dbmod.point_current_widget("ghost", "not_found")
    r = client.get("/api/ghost")
    assert r.headers["X-Widget-Status"] == "not_found"


def test_generate_endpoint_renders_and_stores_svg(client):
    """POST /api/<u>/generate invokes the on-demand render path and caches
    the composite SVG for subsequent README embeds."""
    dbmod.enroll("alice", {"theme": "dark"})
    with client.session_transaction() as s:
        s["gh_login"] = "alice"
    with patch("src.worker.render_widgets_now",
               return_value={"composite": "<svg>r</svg>", "grade": "<svg>g</svg>"}):
        # Simulate the render path also updating current_widget so the
        # follow-up GET sees ready.
        def fake_render(username):
            dbmod.put_widgets(username, "h1", {"composite": "<svg>r</svg>"})
            dbmod.point_current_widget(username, "h1")
            return {"composite": "<svg>r</svg>"}
        with patch("src.worker.render_widgets_now", side_effect=fake_render):
            r = client.post("/api/alice/generate", headers={"Origin": "https://gh-stats.com"})
    assert r.status_code == 200
    body = r.get_json()
    assert body["status"] == "ready"
    assert body["composite_url"] == "/api/alice"
    r2 = client.get("/api/alice")
    assert r2.headers["X-Widget-Status"] == "ready"
    assert b"<svg>r</svg>" in r2.data


def test_generate_endpoint_rejects_unenrolled(client):
    """With OAuth, unenrolled means having a session but no profile."""
    with client.session_transaction() as s:
        s["gh_login"] = "bob"
    r = client.post("/api/bob/generate", headers={"Origin": "https://gh-stats.com"})
    assert r.status_code == 404


# ---- GET /api/<username>/data: precomputed widget data for client-side rendering ----
# Pure DB lookup — fetcher is never touched on the hot path.


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


def test_generate_without_session_is_401(client):
    dbmod.enroll("alice", {"theme": "dark"})
    r = client.post("/api/alice/generate", headers={"Origin": "https://gh-stats.com"})
    assert r.status_code == 401


def test_generate_wrong_login_is_403(client):
    dbmod.enroll("alice", {"theme": "dark"})
    with client.session_transaction() as s:
        s["gh_login"] = "bob"
    r = client.post("/api/alice/generate", headers={"Origin": "https://gh-stats.com"})
    assert r.status_code == 403


def test_refresh_without_session_is_401(client):
    dbmod.enroll("alice", {"theme": "dark"})
    r = client.post("/api/alice/refresh", headers={"Origin": "https://gh-stats.com"})
    assert r.status_code == 401


def test_data_unknown_user_returns_404(client):
    r = client.get("/api/testuser/data")
    assert r.status_code == 404
    # Unknown-but-not-enrolled is distinct from confirmed-not-on-GitHub so
    # the frontend can avoid a misleading "User not found" message.
    assert r.get_json()["status"] == "not_enrolled"


def test_enroll_endpoint_is_gone(client):
    r = client.post("/api/enroll", json={"username": "alice"},
                    headers={"Origin": "https://gh-stats.com"})
    assert r.status_code == 405


# ---- POST /internal/data-ready: callback from fetcher when an async fetch lands ----


def test_data_ready_requires_internal_token(client, monkeypatch):
    monkeypatch.setattr(cfg, "FETCHER_INTERNAL_TOKEN", "secret")
    r = client.post("/internal/data-ready", json={"username": "alice"})
    assert r.status_code == 401


def test_data_ready_enqueues_build_for_enrolled_user(client, monkeypatch):
    """The whole point of the async path: the build job appears in the queue
    after the fetcher has stored data, not before. Enrolling a user no
    longer adds a job, so /data-ready is the only thing that does."""
    monkeypatch.setattr(cfg, "FETCHER_INTERNAL_TOKEN", "secret")
    dbmod.enroll("alice", {"theme": "dark"}, enqueue_build=False)
    assert dbmod.pending_job_count() == 0

    r = client.post("/internal/data-ready",
                    headers={"X-Internal-Token": "secret"},
                    json={"username": "alice", "payload_hash": "h1", "ok": True})
    assert r.status_code == 200
    assert r.get_json()["queued"] is True
    assert dbmod.pending_job_count() == 1


def test_data_ready_ignores_unknown_user(client, monkeypatch):
    """If we get a callback for someone who hasn't enrolled here we must not
    create a job — the fetcher might be shared or the enrollment might
    have been deleted in between."""
    monkeypatch.setattr(cfg, "FETCHER_INTERNAL_TOKEN", "secret")
    r = client.post("/internal/data-ready",
                    headers={"X-Internal-Token": "secret"},
                    json={"username": "stranger", "payload_hash": "h1", "ok": True})
    assert r.status_code == 200
    assert r.get_json()["ignored"] is True
    assert dbmod.pending_job_count() == 0


def test_data_ready_does_not_enqueue_on_failed_fetch(client, monkeypatch):
    monkeypatch.setattr(cfg, "FETCHER_INTERNAL_TOKEN", "secret")
    dbmod.enroll("alice", {"theme": "dark"}, enqueue_build=False)
    r = client.post("/internal/data-ready",
                    headers={"X-Internal-Token": "secret"},
                    json={"username": "alice", "payload_hash": "", "ok": False})
    assert r.status_code == 200
    assert r.get_json()["ignored"] is True
    assert dbmod.pending_job_count() == 0


def test_query_override_triggers_adhoc_render_without_persisting(client):
    """GET /api/<u>?theme=... renders on-demand via worker.render_composite_adhoc
    and does not mutate the stored settings blob — this is the path visitors
    use to embed a customized widget of someone else's profile."""
    dbmod.enroll("alice", {"theme": "midnight"})
    dbmod.put_widgets("alice", "h1", {"composite": "<svg>cached</svg>"})
    dbmod.point_current_widget("alice", "h1")

    captured = {}

    def fake_adhoc(username, overrides):
        captured["username"] = username
        captured["overrides"] = overrides
        return "<svg>adhoc</svg>"

    with patch("src.worker.render_composite_adhoc", side_effect=fake_adhoc):
        r = client.get("/api/alice?theme=onyx&widgets=name,grade")

    assert r.status_code == 200
    assert r.headers["X-Widget-Status"] == "ready"
    assert r.headers["Cache-Control"] == "public, max-age=300"
    assert b"<svg>adhoc</svg>" in r.data
    assert captured["username"] == "alice"
    assert captured["overrides"]["theme"] == "onyx"
    assert captured["overrides"]["enabled"] == ["name", "grade"]
    # Stored settings must remain untouched.
    assert dbmod.get_settings("alice")["settings"]["theme"] == "midnight"


def test_query_override_without_params_uses_cached_composite(client):
    """No query params → fast path serves the pre-rendered composite from
    widgets.db. Ad-hoc render must not be invoked."""
    dbmod.enroll("alice", {"theme": "midnight"})
    dbmod.put_widgets("alice", "h1", {"composite": "<svg>cached</svg>"})
    dbmod.point_current_widget("alice", "h1")

    with patch("src.worker.render_composite_adhoc") as adhoc:
        r = client.get("/api/alice")
        assert adhoc.call_count == 0

    assert r.status_code == 200
    assert r.headers["X-Widget-Status"] == "ready"
    assert b"<svg>cached</svg>" in r.data


def test_query_override_ignores_unknown_params(client):
    """Keys not in the allow-list are dropped by sanitize_settings_query so
    bogus query strings don't trigger the expensive ad-hoc path."""
    dbmod.enroll("alice", {"theme": "midnight"})
    dbmod.put_widgets("alice", "h1", {"composite": "<svg>cached</svg>"})
    dbmod.point_current_widget("alice", "h1")

    with patch("src.worker.render_composite_adhoc") as adhoc:
        r = client.get("/api/alice?nonsense=1&t=12345")
        assert adhoc.call_count == 0

    assert b"<svg>cached</svg>" in r.data


def test_per_login_mutate_rate_limit(client, monkeypatch):
    """Per-login rate limit on mutate routes allows up to MAX requests,
    then rejects with 429."""
    monkeypatch.setattr(cfg, "RATE_LIMIT_MUTATE_PER_LOGIN_MAX", 2)
    monkeypatch.setattr(cfg, "RATE_LIMIT_MUTATE_PER_LOGIN_WINDOW", 60)
    dbmod.enroll("alice", {"theme": "dark"})
    with client.session_transaction() as s:
        s["gh_login"] = "alice"
    h = {"Origin": "https://gh-stats.com"}
    # First two requests should succeed.
    r1 = client.patch("/api/alice/settings", json={}, headers=h)
    assert r1.status_code == 200
    r2 = client.patch("/api/alice/settings", json={}, headers=h)
    assert r2.status_code == 200
    # Third request should be rate-limited.
    r3 = client.patch("/api/alice/settings", json={}, headers=h)
    assert r3.status_code == 429
