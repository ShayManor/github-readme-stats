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
def test_full_flow_data_then_generate_then_serve(env):
    """End-to-end of the new two-phase pipeline:
      1. /data enrolls + kicks off prefetch (worker populates widget_data)
      2. /generate renders SVG from the cached payload + settings
      3. /api/<u> serves the stored SVG to README consumers
    """
    responses.add(
        responses.GET, "http://fetcher-mock/data/alice",
        json={"data": {"user": {"login": "alice"}, "repos": [], "events": [],
                        "commits": [], "total_commits": 0, "recent_commits": 0,
                        "total_prs": 0, "collaborators_data": [], "avatar_b64": ""},
              "payload_hash": "h1"}, status=200,
    )
    client = apimod.app.test_client()

    # Phase 1: prefetch via /data (enrolls + kicks off background thread).
    r_data = client.get("/api/alice/data")
    assert r_data.status_code == 202

    # Drain any residual job synchronously in case the kickoff thread lost
    # the race (and to make the assertion deterministic).
    for _ in range(5):
        if not worker.process_one():
            break

    # Widget data should now be available for client-side preview.
    deadline = time.time() + 2.0
    while time.time() < deadline:
        r = client.get("/api/alice/data")
        if r.status_code == 200 and r.get_json().get("status") == "ready":
            break
        time.sleep(0.05)
    assert r.status_code == 200 and r.get_json()["status"] == "ready"

    # Phase 2: Generate button → render SVG.
    r_gen = client.post("/api/alice/generate")
    assert r_gen.status_code == 200
    assert r_gen.get_json()["status"] == "ready"

    # Phase 3: SVG is served from DB.
    r_svg = client.get("/api/alice")
    assert r_svg.headers["X-Widget-Status"] == "ready"
    assert r_svg.data.startswith(b"<svg") or r_svg.data.startswith(b"<?xml")
