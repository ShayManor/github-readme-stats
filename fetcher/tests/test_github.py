import responses
import pytest
from src import github


@responses.activate
def test_fetch_user_data_returns_user_payload():
    # The fetcher fires the independent GitHub calls in parallel, so the
    # mock registry can't depend on FIFO ordering. Route GraphQL requests
    # by query content instead.
    import json as _json

    def _graphql_callback(request):
        q = _json.loads(request.body).get("query", "")
        if "weeks" in q:
            data = {"user": {"contributionsCollection": {"contributionCalendar": {"weeks": []}}}}
        elif "createdAt" in q:
            data = {"user": {"createdAt": "2020-01-01T00:00:00Z"}}
        elif "commitContributionsByRepository" in q:
            data = {"user": {"contributionsCollection": {"commitContributionsByRepository": []}}}
        elif "totalContributions" in q:
            data = {"user": {"contributionsCollection": {"contributionCalendar": {"totalContributions": 10}}}}
        else:
            data = {"user": None}
        return (200, {}, _json.dumps({"data": data}))

    responses.add_callback(responses.POST, "https://api.github.com/graphql",
                           callback=_graphql_callback)
    responses.add(responses.GET, "https://api.github.com/search/issues",
                  json={"total_count": 0, "items": []}, status=200)
    responses.add(
        responses.GET, "https://api.github.com/users/alice",
        json={"login": "alice", "public_repos": 3, "followers": 5,
              "avatar_url": "https://avatars.example/1"},
        status=200,
    )
    responses.add(responses.GET, "https://api.github.com/users/alice/repos", json=[], status=200)
    responses.add(responses.GET, "https://api.github.com/users/alice/repos", json=[], status=200)
    responses.add(responses.GET, "https://api.github.com/users/alice/events", json=[], status=200)
    data = github.fetch_github_data("alice", token="t")
    assert data["user"]["login"] == "alice"
    assert "repos" in data
    assert "events" in data


@responses.activate
def test_fetch_handles_404():
    responses.add(
        responses.GET, "https://api.github.com/users/nope",
        json={"message": "Not Found"}, status=404,
    )
    responses.add(
        responses.POST, "https://api.github.com/graphql",
        json={"data": {"user": None}}, status=200,
    )
    # Both fetch_repos calls (owner + all) hit the same URL — register
    # twice so the parallel firing gets a response either way round.
    responses.add(
        responses.GET, "https://api.github.com/users/nope/repos",
        json={"message": "Not Found"}, status=404,
    )
    responses.add(
        responses.GET, "https://api.github.com/users/nope/repos",
        json={"message": "Not Found"}, status=404,
    )
    responses.add(
        responses.GET, "https://api.github.com/users/nope/events",
        json={"message": "Not Found"}, status=404,
    )
    responses.add(
        responses.GET, "https://api.github.com/search/issues",
        json={"total_count": 0, "items": []}, status=200,
    )
    data = github.fetch_github_data("nope", token="t")
    assert data["user"].get("message") == "Not Found" or data["user"] is None
