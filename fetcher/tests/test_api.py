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
