import os
import tempfile
import pytest
import responses
from src import analytics as a
from src import config as cfg
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


def test_record_fetch():
    a._reset_for_tests()
    a.record_fetch("alice", 200, 312)
    assert len(a._QUEUE) == 1
    e = a._QUEUE[0]
    assert e["service"] == "fetcher"
    assert e["kind"] == "fetch"
    assert e["status"] == 200
    assert e["latency_ms"] == 312
    assert e["endpoint"] == "github/users/<u>"


@responses.activate
def test_flush_posts(monkeypatch):
    monkeypatch.setattr(cfg, "GENERATOR_URL", "http://gen:5002")
    monkeypatch.setattr(cfg, "INTERNAL_TOKEN", "secret")
    a._reset_for_tests()
    responses.add(responses.POST, "http://gen:5002/internal/analytics/events",
                  json={"ingested": 1}, status=200)
    a.record_fetch("alice", 200, 100)
    a.flush_now()
    assert len(responses.calls) == 1


def test_force_fetch_records_event(monkeypatch, client):
    a._reset_for_tests()
    monkeypatch.setattr("src.api.github.fetch_github_data",
                        lambda u, token: {"user": {"login": u}})
    r = client.post("/fetch",
                    headers={"X-Internal-Token": "secret"},
                    json={"username": "alice"})
    assert r.status_code == 200
    assert any(e["kind"] == "fetch" and e["username"] == "alice"
               for e in a._QUEUE)
