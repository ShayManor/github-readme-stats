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


@responses.activate
def test_commit_count_raises_on_graphql_rate_limit():
    # GraphQL reports a rate limit as HTTP 200 with an `errors` array — the
    # exact shape a valid response uses. It must NOT be swallowed into a 0
    # that would overwrite the last good count in fetcher.db.
    responses.add(
        responses.POST, "https://api.github.com/graphql",
        json={"data": {"user": None},
              "errors": [{"type": "RATE_LIMITED", "message": "API rate limit exceeded"}]},
        status=200,
    )
    src = github.DirectAPISource(token="t")
    with pytest.raises(github.GitHubTransientError):
        src.fetch_commit_count("alice", [])


@responses.activate
def test_commit_count_raises_on_rest_rate_limit():
    # A 403 with the remaining budget at 0 is a rate limit, not a real answer.
    responses.add(
        responses.POST, "https://api.github.com/graphql",
        json={"message": "rate limited"}, status=403,
        headers={"X-RateLimit-Remaining": "0"},
    )
    src = github.DirectAPISource(token="t")
    with pytest.raises(github.GitHubTransientError):
        src.fetch_commit_count("alice", [])


@responses.activate
def test_commit_count_zero_on_not_found_is_not_transient():
    # A genuinely unknown user (NOT_FOUND, no rate-limit error) is a real,
    # persistable "no data" answer — return 0, don't raise.
    responses.add(
        responses.POST, "https://api.github.com/graphql",
        json={"data": {"user": None}}, status=200,
    )
    src = github.DirectAPISource(token="t")
    assert src.fetch_commit_count("ghost", []) == 0
