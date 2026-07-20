import pytest
import responses
from src import api as apimod


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(apimod.config, "GENERATOR_URL", "http://gen:5002")
    apimod.cache_ext.clear()
    apimod.app.config["TESTING"] = True
    with apimod.app.test_client() as c:
        yield c


@responses.activate
def test_miss_then_hit_serves_from_cache(client):
    responses.add(responses.GET, "http://gen:5002/api/alice",
                  body=b"<svg>ready</svg>", status=200,
                  headers={"X-Widget-Status": "ready", "Content-Type": "image/svg+xml"})
    r1 = client.get("/alice")
    assert r1.status_code == 200
    assert r1.data == b"<svg>ready</svg>"
    responses.reset()
    r2 = client.get("/alice")
    assert r2.status_code == 200
    assert r2.data == b"<svg>ready</svg>"


@responses.activate
def test_placeholder_not_cached(client):
    responses.add(responses.GET, "http://gen:5002/api/alice",
                  body=b"<svg>building</svg>", status=200,
                  headers={"X-Widget-Status": "building", "Content-Type": "image/svg+xml"})
    r1 = client.get("/alice")
    assert r1.status_code == 200
    r2 = client.get("/alice")
    assert len(responses.calls) == 2


@responses.activate
def test_origin_error_returns_503(client):
    responses.add(responses.GET, "http://gen:5002/api/alice", status=500)
    r = client.get("/alice")
    assert r.status_code == 503


@responses.activate
def test_trailing_slash_tolerated(client):
    """A hand-copied `/alice/` must resolve like `/alice`, not 404."""
    responses.add(responses.GET, "http://gen:5002/api/alice",
                  body=b"<svg>ready</svg>", status=200,
                  headers={"X-Widget-Status": "ready", "Content-Type": "image/svg+xml"})
    r = client.get("/alice/")
    assert r.status_code == 200
    assert r.data == b"<svg>ready</svg>"


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
