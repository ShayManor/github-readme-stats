"""End-to-end: api + worker in-process + mocked fetcher HTTP."""
import os, tempfile, time
import pytest
import responses
from src import api as apimod, db as dbmod, worker


@pytest.fixture
def env(monkeypatch):
    with tempfile.TemporaryDirectory() as d:
        monkeypatch.setattr(dbmod, "SETTINGS_DB_PATH", os.path.join(d, "s.db"))
        monkeypatch.setattr(dbmod, "WIDGETS_DB_PATH", os.path.join(d, "w.db"))
        monkeypatch.setattr(apimod.config, "FETCHER_URL", "http://fetcher-mock")
        monkeypatch.setattr(apimod.config, "FETCHER_INTERNAL_TOKEN", "t")
        dbmod.init_dbs()
        yield


@responses.activate
def test_first_request_builds_then_serves_ready(env):
    responses.add(
        responses.GET, "http://fetcher-mock/data/alice",
        json={"data": {"user": {"login": "alice"}, "repos": [], "events": [],
                        "commits": [], "total_commits": 0, "recent_commits": 0,
                        "total_prs": 0, "collaborators_data": [], "avatar_b64": ""},
              "payload_hash": "h1"}, status=200,
    )
    client = apimod.app.test_client()

    r1 = client.get("/api/alice")
    assert r1.headers["X-Widget-Status"] == "building"

    # First request kicks off a background build thread; drain any residual
    # job in case of races, then poll the API for readiness.
    for _ in range(5):
        if not worker.process_one():
            break

    deadline = time.time() + 2.0
    while time.time() < deadline:
        r2 = client.get("/api/alice")
        if r2.headers["X-Widget-Status"] == "ready":
            break
        time.sleep(0.05)
    assert r2.headers["X-Widget-Status"] == "ready"
    assert r2.data.startswith(b"<svg") or r2.data.startswith(b"<?xml")
