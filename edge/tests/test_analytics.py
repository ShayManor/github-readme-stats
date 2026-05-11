import responses
from src import analytics as a
from src import config as cfg


def test_record_request_enqueues():
    a._reset_for_tests()
    a.record_request("/<u>", "alice", "composite", 200, 12, cache_hit=1)
    assert len(a._QUEUE) == 1
    e = a._QUEUE[0]
    assert e["service"] == "edge"
    assert e["username"] == "alice"
    assert e["latency_ms"] == 12


@responses.activate
def test_flush_posts_batch(monkeypatch):
    monkeypatch.setattr(cfg, "ANALYTICS_GENERATOR_URL", "http://gen:5002")
    monkeypatch.setattr(cfg, "ANALYTICS_INTERNAL_TOKEN", "secret")
    a._reset_for_tests()
    responses.add(responses.POST, "http://gen:5002/internal/analytics/events",
                  json={"ingested": 2}, status=200)
    a.record_request("/<u>", "alice", "composite", 200, 12, cache_hit=1)
    a.record_request("/<u>", "bob", "composite", 200, 8, cache_hit=0)
    a.flush_now()
    assert len(responses.calls) == 1
    import json
    body = json.loads(responses.calls[0].request.body)
    assert len(body["events"]) == 2


def test_instrument_wraps_serve_and_records(monkeypatch):
    monkeypatch.setattr(cfg, "ANALYTICS_INTERNAL_TOKEN", "secret")
    a._reset_for_tests()
    from src import api as apimod
    with apimod.app.test_client() as c:
        class FakeResp:
            status_code = 200
            content = b"<svg/>"
            headers = {"X-Widget-Status": "ready", "Content-Type": "image/svg+xml"}
        monkeypatch.setattr(apimod, "_fetch_origin", lambda *a, **k: FakeResp())
        apimod.cache_ext.clear()
        c.get("/alice")
    assert len(a._QUEUE) == 1
    assert a._QUEUE[0]["username"] == "alice"
    assert a._QUEUE[0]["endpoint"] == "/<u>"
