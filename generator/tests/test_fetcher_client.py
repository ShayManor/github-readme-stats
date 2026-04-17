import responses
import pytest
from src import fetcher_client as fc


@pytest.fixture(autouse=True)
def cfg(monkeypatch):
    monkeypatch.setattr(fc.config, "FETCHER_URL", "http://fetcher:5001")
    monkeypatch.setattr(fc.config, "FETCHER_INTERNAL_TOKEN", "secret")


@responses.activate
def test_get_data_returns_payload_and_hash():
    responses.add(
        responses.GET, "http://fetcher:5001/data/alice",
        json={"data": {"user": {"login": "alice"}}, "payload_hash": "abc"},
        status=200,
    )
    result = fc.get_data("alice")
    assert result["payload_hash"] == "abc"
    assert result["data"]["user"]["login"] == "alice"


@responses.activate
def test_get_data_sends_auth_header():
    responses.add(responses.GET, "http://fetcher:5001/data/alice",
                  json={"data": {}, "payload_hash": "h"}, status=200)
    fc.get_data("alice")
    assert responses.calls[0].request.headers["X-Internal-Token"] == "secret"


@responses.activate
def test_force_fetch():
    responses.add(responses.POST, "http://fetcher:5001/fetch",
                  json={"stored": True, "payload_hash": "new", "changed": True}, status=200)
    r = fc.force_fetch("alice")
    assert r["changed"] is True
