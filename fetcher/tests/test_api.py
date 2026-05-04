import os
import tempfile
import pytest
import responses as resp_lib
from src import db as dbmod
from src import api as apimod


@pytest.fixture
def client(monkeypatch):
    with tempfile.TemporaryDirectory() as d:
        monkeypatch.setattr(dbmod, "DB_PATH", os.path.join(d, "t.db"))
        monkeypatch.setattr(apimod.config, "INTERNAL_TOKEN", "secret")
        monkeypatch.setattr(apimod.config, "GITHUB_PAT", "ghp_test")
        dbmod.init_db()
        app = apimod.app
        app.config["TESTING"] = True
        with app.test_client() as c:
            yield c


def test_health_no_auth_required(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.get_json()["service"] == "fetcher"


def test_endpoints_require_internal_token(client):
    r = client.get("/data/alice")
    assert r.status_code == 401


@resp_lib.activate
def test_data_auto_fetches_on_miss(client, monkeypatch):
    # fetch_commits: contributionCalendar/weeks
    resp_lib.add(resp_lib.POST, "https://api.github.com/graphql",
                 json={"data": {"user": {"contributionsCollection": {"contributionCalendar": {"weeks": []}}}}}, status=200)
    # fetch_commit_count (alltime) — first call: get createdAt
    resp_lib.add(resp_lib.POST, "https://api.github.com/graphql",
                 json={"data": {"user": {"createdAt": "2020-01-01T00:00:00Z"}}}, status=200)
    # fetch_commit_count (alltime) — per-year contribution totals (2020–2026, 7 years)
    for _ in range(7):
        resp_lib.add(resp_lib.POST, "https://api.github.com/graphql",
                     json={"data": {"user": {"contributionsCollection": {"contributionCalendar": {"totalContributions": 10}}}}},
                     status=200)
    # fetch_commit_count (recent, last 6 months)
    resp_lib.add(resp_lib.POST, "https://api.github.com/graphql",
                 json={"data": {"user": {"contributionsCollection": {"contributionCalendar": {"totalContributions": 5}}}}},
                 status=200)
    # fetch_user_commit_repos (for collaborators)
    resp_lib.add(resp_lib.POST, "https://api.github.com/graphql",
                 json={"data": {"user": {"contributionsCollection": {"commitContributionsByRepository": []}}}},
                 status=200)
    # PR count search
    resp_lib.add(resp_lib.GET, "https://api.github.com/search/issues",
                 json={"total_count": 0, "items": []}, status=200)
    resp_lib.add(resp_lib.GET, "https://api.github.com/users/alice",
                 json={"login": "alice", "public_repos": 1, "followers": 0, "avatar_url": "https://avatars.example/a"}, status=200)
    # fetch_repos: two calls (owner + all)
    resp_lib.add(resp_lib.GET, "https://api.github.com/users/alice/repos", json=[], status=200)
    resp_lib.add(resp_lib.GET, "https://api.github.com/users/alice/repos", json=[], status=200)
    resp_lib.add(resp_lib.GET, "https://api.github.com/users/alice/events", json=[], status=200)

    r = client.get("/data/alice", headers={"X-Internal-Token": "secret"})
    assert r.status_code == 200
    body = r.get_json()
    assert body["payload_hash"]
    assert body["data"]["user"]["login"] == "alice"


def test_force_fetch_requires_auth(client):
    r = client.post("/fetch", json={"username": "alice"})
    assert r.status_code == 401


def test_fetch_async_requires_auth(client):
    r = client.post("/fetch-async", json={"username": "alice"})
    assert r.status_code == 401


def test_fetch_async_rejects_invalid_username(client):
    r = client.post("/fetch-async", headers={"X-Internal-Token": "secret"},
                    json={"username": "../etc/passwd"})
    assert r.status_code == 400


def test_fetch_async_runs_in_background_and_calls_back(client, monkeypatch):
    """The async path must (a) return 202 immediately without waiting for
    GitHub, and (b) POST back to the generator's /internal/data-ready when
    the background fetch completes. Without (a) we'd be back to the old
    synchronous-blocking design that timed out the worker; without (b)
    nothing would ever enqueue the build job."""
    import threading
    from src import api as apimod

    fetch_done = threading.Event()
    callback_calls: list = []

    def fake_fetch(username, token=None):
        # Block briefly so the test can prove /fetch-async returned before
        # this finished.
        fetch_done.wait(timeout=2)
        return {"user": {"login": username, "avatar_url": "x"}, "repos": []}

    def fake_post(url, headers=None, json=None, timeout=None):
        callback_calls.append({"url": url, "json": json, "headers": headers})
        class _R: status_code = 200
        return _R()

    monkeypatch.setattr(apimod.github, "fetch_github_data", fake_fetch)
    monkeypatch.setattr(apimod.requests, "post", fake_post)
    monkeypatch.setattr(apimod.config, "GENERATOR_URL", "http://gen:5002")

    r = client.post("/fetch-async", headers={"X-Internal-Token": "secret"},
                    json={"username": "alice"})
    assert r.status_code == 202
    assert r.get_json()["queued"] is True

    # Let the background fetch finish; wait for the callback.
    fetch_done.set()
    for _ in range(50):
        if callback_calls:
            break
        threading.Event().wait(0.05)

    assert len(callback_calls) == 1
    cb = callback_calls[0]
    assert cb["url"] == "http://gen:5002/internal/data-ready"
    assert cb["json"]["username"] == "alice"
    assert cb["json"]["ok"] is True
    assert cb["json"]["payload_hash"]


def test_fetch_async_dedupes_inflight(client, monkeypatch):
    """A second /fetch-async call for the same user while the first is
    still in flight must not start a second GitHub fetch."""
    import threading
    from src import api as apimod

    started = threading.Event()
    release = threading.Event()
    fetch_calls = {"n": 0}

    def fake_fetch(username, token=None):
        fetch_calls["n"] += 1
        started.set()
        release.wait(timeout=2)
        return {"user": {"login": username, "avatar_url": "x"}, "repos": []}

    monkeypatch.setattr(apimod.github, "fetch_github_data", fake_fetch)
    monkeypatch.setattr(apimod.requests, "post", lambda *a, **kw: type("R", (), {"status_code": 200})())
    monkeypatch.setattr(apimod.config, "GENERATOR_URL", "")

    r1 = client.post("/fetch-async", headers={"X-Internal-Token": "secret"},
                     json={"username": "alice"})
    assert r1.status_code == 202
    assert started.wait(timeout=2)

    r2 = client.post("/fetch-async", headers={"X-Internal-Token": "secret"},
                     json={"username": "alice"})
    assert r2.status_code == 202
    assert r2.get_json().get("already_inflight") is True

    release.set()
    # Drain
    for _ in range(50):
        if fetch_calls["n"] >= 1 and "alice" not in apimod._INFLIGHT:
            break
        threading.Event().wait(0.05)
    assert fetch_calls["n"] == 1
