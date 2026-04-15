"""Hand-written dummy user payload.

Shape matches what ``fetch_github_data`` returns, so the generator's processor
code runs unchanged against it. Used as the fallback whenever a requested user
is missing from the DB or has incomplete data.
"""

from datetime import datetime, timedelta


def _recent_iso(days_ago: int) -> str:
    return (datetime.utcnow() - timedelta(days=days_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _daily_commits() -> list[dict]:
    out = []
    for i in range(0, 180, 2):
        date = (datetime.utcnow() - timedelta(days=i)).strftime("%Y-%m-%d")
        out.append({"date": date, "count": 3 + (i % 5)})
    return out


DUMMY_PAYLOAD: dict = {
    "user": {
        "login": "octocat",
        "name": "Demo Developer",
        "followers": 120,
        "following": 40,
        "public_repos": 24,
        "avatar_url": "",
        "created_at": "2018-01-15T00:00:00Z",
    },
    "repos": [
        {
            "id": 1, "name": "stellar-api", "full_name": "octocat/stellar-api",
            "language": "Python", "stargazers_count": 310, "forks_count": 42,
            "pushed_at": _recent_iso(3), "topics": ["backend", "api", "fastapi"],
            "size": 2400,
        },
        {
            "id": 2, "name": "pixel-ui", "full_name": "octocat/pixel-ui",
            "language": "TypeScript", "stargazers_count": 180, "forks_count": 19,
            "pushed_at": _recent_iso(6), "topics": ["frontend", "react", "design-system"],
            "size": 1800,
        },
        {
            "id": 3, "name": "nimbus-infra", "full_name": "octocat/nimbus-infra",
            "language": "Go", "stargazers_count": 95, "forks_count": 12,
            "pushed_at": _recent_iso(10), "topics": ["devops", "kubernetes", "terraform"],
            "size": 1100,
        },
        {
            "id": 4, "name": "ml-playground", "full_name": "octocat/ml-playground",
            "language": "Jupyter Notebook", "stargazers_count": 64, "forks_count": 8,
            "pushed_at": _recent_iso(14), "topics": ["ml", "pytorch"],
            "size": 900,
        },
        {
            "id": 5, "name": "dotfiles", "full_name": "octocat/dotfiles",
            "language": "Shell", "stargazers_count": 22, "forks_count": 3,
            "pushed_at": _recent_iso(20), "topics": [], "size": 120,
        },
        {
            "id": 6, "name": "rustle", "full_name": "octocat/rustle",
            "language": "Rust", "stargazers_count": 48, "forks_count": 5,
            "pushed_at": _recent_iso(30), "topics": ["systems", "cli"], "size": 450,
        },
        {
            "id": 7, "name": "web-playground", "full_name": "octocat/web-playground",
            "language": "JavaScript", "stargazers_count": 30, "forks_count": 4,
            "pushed_at": _recent_iso(40), "topics": ["frontend"], "size": 380,
        },
        {
            "id": 8, "name": "notes-app", "full_name": "octocat/notes-app",
            "language": "TypeScript", "stargazers_count": 15, "forks_count": 2,
            "pushed_at": _recent_iso(55), "topics": ["frontend"], "size": 260,
        },
    ],
    "events": [
        {"type": "PushEvent", "created_at": _recent_iso(1),
         "actor": {"login": "octocat"}, "repo": {"name": "octocat/stellar-api"},
         "payload": {"commits": [{"sha": "abc"}, {"sha": "def"}]}},
        {"type": "PullRequestEvent", "created_at": _recent_iso(2),
         "actor": {"login": "octocat"}, "repo": {"name": "octocat/pixel-ui"},
         "payload": {}},
        {"type": "PushEvent", "created_at": _recent_iso(4),
         "actor": {"login": "octocat"}, "repo": {"name": "octocat/nimbus-infra"},
         "payload": {"commits": [{"sha": "ghi"}]}},
    ],
    "commits": _daily_commits(),
    "total_commits": 2450,
    "recent_commits": 680,
    "total_prs": 180,
    "collaborators_data": [
        {
            "login": "alice-dev", "avatar_url": "",
            "raw_score": 220.0, "shared_repos": 3, "final_score": 660.0,
            "repos": ["octocat/stellar-api", "octocat/pixel-ui", "octocat/nimbus-infra"],
            "tight_owned_partner": True,
        },
        {
            "login": "bob-builder", "avatar_url": "",
            "raw_score": 140.0, "shared_repos": 2, "final_score": 280.0,
            "repos": ["octocat/stellar-api", "octocat/ml-playground"],
            "tight_owned_partner": False,
        },
        {
            "login": "carol-codes", "avatar_url": "",
            "raw_score": 95.0, "shared_repos": 2, "final_score": 190.0,
            "repos": ["octocat/pixel-ui", "octocat/web-playground"],
            "tight_owned_partner": False,
        },
    ],
    "avatar_b64": "",
}
