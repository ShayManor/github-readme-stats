import responses
import pytest
from src import github


@responses.activate
def test_fetch_user_data_returns_user_payload():
    # fetch_commits: contributionCalendar/weeks
    responses.add(
        responses.POST, "https://api.github.com/graphql",
        json={"data": {"user": {"contributionsCollection": {"contributionCalendar": {"weeks": []}}}}},
        status=200,
    )
    # fetch_commit_count (alltime) — first call: get createdAt
    responses.add(
        responses.POST, "https://api.github.com/graphql",
        json={"data": {"user": {"createdAt": "2020-01-01T00:00:00Z"}}},
        status=200,
    )
    # fetch_commit_count (alltime) — per-year contribution totals (2020–2026)
    for _ in range(7):
        responses.add(
            responses.POST, "https://api.github.com/graphql",
            json={"data": {"user": {"contributionsCollection": {"contributionCalendar": {"totalContributions": 10}}}}},
            status=200,
        )
    # fetch_commit_count (recent, last 6 months)
    responses.add(
        responses.POST, "https://api.github.com/graphql",
        json={"data": {"user": {"contributionsCollection": {"contributionCalendar": {"totalContributions": 5}}}}},
        status=200,
    )
    # fetch_user_commit_repos (for collaborators)
    responses.add(
        responses.POST, "https://api.github.com/graphql",
        json={"data": {"user": {"contributionsCollection": {"commitContributionsByRepository": []}}}},
        status=200,
    )
    # PR count search
    responses.add(
        responses.GET, "https://api.github.com/search/issues",
        json={"total_count": 0, "items": []},
        status=200,
    )
    responses.add(
        responses.GET, "https://api.github.com/users/alice",
        json={"login": "alice", "public_repos": 3, "followers": 5, "avatar_url": "https://avatars.example/1"},
        status=200,
    )
    # fetch_repos: two calls (owner + all)
    responses.add(
        responses.GET, "https://api.github.com/users/alice/repos",
        json=[], status=200,
    )
    responses.add(
        responses.GET, "https://api.github.com/users/alice/repos",
        json=[], status=200,
    )
    responses.add(
        responses.GET, "https://api.github.com/users/alice/events",
        json=[], status=200,
    )
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
    responses.add(
        responses.GET, "https://api.github.com/users/nope/repos",
        json={"message": "Not Found"}, status=404,
    )
    responses.add(
        responses.GET, "https://api.github.com/users/nope/events",
        json={"message": "Not Found"}, status=404,
    )
    data = github.fetch_github_data("nope", token="t")
    assert data["user"].get("message") == "Not Found" or data["user"] is None
