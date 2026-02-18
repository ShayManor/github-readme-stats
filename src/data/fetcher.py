"""GitHub data fetching functions."""

import requests
import base64
from typing import Optional, Protocol

from ..config import (
    COLLABORATOR_MIN_COMMITS,
    COLLABORATOR_MAX_REPO_SIZE,
    COLLABORATOR_TOP_REPOS,
    COMMIT_MAX_REPOS,
    COMMIT_PER_REPO,
    API_TIMEOUT,
)


class GitHubDataSource(Protocol):
    """Protocol for GitHub data sources - allows swapping implementations."""

    def fetch_user_data(self, username: str) -> dict:
        """Fetch user profile data."""
        ...

    def fetch_repos(self, username: str) -> list:
        """Fetch user repositories."""
        ...

    def fetch_events(self, username: str) -> list:
        """Fetch user events."""
        ...

    def fetch_commits(self, username: str, repos: list) -> list:
        """Fetch commits from repositories."""
        ...

    def fetch_repo_contributors(self, repo_name: str, min_commits: int) -> list:
        """Fetch contributors for a specific repository."""
        ...

    def fetch_avatar(self, avatar_url: str) -> str:
        """Fetch and encode avatar as base64."""
        ...


class DirectAPISource:
    """Direct GitHub API implementation - for immediate requests."""

    def __init__(self, token: Optional[str] = None):
        self.token = token
        self.headers = {"Accept": "application/vnd.github.v3+json"}
        if token:
            self.headers["Authorization"] = f"token {token}"
        self.base = "https://api.github.com"

    def fetch_user_data(self, username: str) -> dict:
        """Fetch user profile data."""
        return requests.get(
            f"{self.base}/users/{username}",
            headers=self.headers
        ).json()

    def fetch_repos(self, username: str) -> list:
        """Fetch user repositories (owned + contributed to)."""
        # Fetch owned repos
        owned = requests.get(
            f"{self.base}/users/{username}/repos",
            headers=self.headers,
            params={"per_page": 100, "sort": "pushed", "type": "owner"},
        ).json()

        # Fetch all repos (includes collabs, orgs)
        all_repos = requests.get(
            f"{self.base}/users/{username}/repos",
            headers=self.headers,
            params={"per_page": 100, "sort": "pushed", "type": "all"},
        ).json()

        # Combine and deduplicate
        repos = owned if isinstance(owned, list) else []
        all_repos = all_repos if isinstance(all_repos, list) else []

        seen = {r["id"] for r in repos}
        for repo in all_repos:
            if repo["id"] not in seen:
                repos.append(repo)
                seen.add(repo["id"])

        return repos

    def fetch_events(self, username: str) -> list:
        """Fetch user events."""
        resp = requests.get(
            f"{self.base}/users/{username}/events",
            headers=self.headers,
            params={"per_page": 100},
        ).json()
        return resp if isinstance(resp, list) else []

    def fetch_commits(self, username: str, repos: list, max_repos: int = COMMIT_MAX_REPOS) -> list:
        """
        Fetch recent commits directly from user's repositories.

        Args:
            username: GitHub username
            repos: List of repository dicts
            max_repos: Maximum number of repos to fetch from

        Returns:
            List of commits with repo context
        """
        all_commits = []
        sorted_repos = sorted(
            repos, key=lambda r: r.get("pushed_at", ""), reverse=True
        )[:max_repos]

        for repo in sorted_repos:
            repo_name = repo.get("full_name")
            if not repo_name:
                continue

            try:
                commits_resp = requests.get(
                    f"{self.base}/repos/{repo_name}/commits",
                    headers=self.headers,
                    params={"author": username, "per_page": COMMIT_PER_REPO},
                    timeout=API_TIMEOUT
                )

                if commits_resp.ok:
                    commits = commits_resp.json()
                    for commit in commits:
                        commit["_repo_name"] = repo_name
                        commit["_repo_language"] = repo.get("language")
                    all_commits.extend(commits)
            except Exception as e:
                print(f"Warning: Failed to fetch commits from {repo_name}: {e}")
                continue

        return all_commits

    def fetch_repo_contributors(self, repo_name: str, min_commits: int = 1) -> list:
        """
        Fetch contributors for a specific repository.

        Args:
            repo_name: Full repository name (owner/repo)
            min_commits: Minimum commits to include contributor

        Returns:
            List of contributor dicts with login, contributions, avatar_url
        """
        try:
            resp = requests.get(
                f"{self.base}/repos/{repo_name}/contributors",
                headers=self.headers,
                params={"per_page": 100},
                timeout=API_TIMEOUT
            )

            if resp.ok:
                contributors = resp.json()
                # Filter by minimum commits
                return [
                    c for c in contributors
                    if c.get("contributions", 0) >= min_commits
                ]
        except Exception as e:
            print(f"Warning: Failed to fetch contributors from {repo_name}: {e}")

        return []

    def fetch_avatar(self, avatar_url: str) -> str:
        """Fetch and encode avatar as base64."""
        try:
            resp = requests.get(avatar_url + "&s=64", timeout=API_TIMEOUT)
            if resp.ok:
                return base64.b64encode(resp.content).decode("ascii")
        except Exception:
            pass
        return ""


# TODO: Future implementation for queue-based batching
# class QueuedAPISource:
#     """Queue-based GitHub API implementation - for batched processing."""
#     def __init__(self, queue_client, cache_client):
#         self.queue = queue_client
#         self.cache = cache_client
#
#     def fetch_user_data(self, username: str) -> dict:
#         # Check cache first, enqueue if miss
#         ...


def fetch_github_data(
    username: str,
    token: Optional[str] = None,
    data_source: Optional[GitHubDataSource] = None
) -> dict:
    """
    Fetches all relevant GitHub data for a user.

    Args:
        username: GitHub username
        token: Optional GitHub API token
        data_source: Optional data source implementation (defaults to DirectAPISource)

    Returns:
        Dict with user, repos, events, commits, collaborators_data, and avatar_b64
    """
    # Use provided data source or default to direct API
    source = data_source or DirectAPISource(token)

    # Fetch all data through the data source abstraction
    user = source.fetch_user_data(username)
    repos = source.fetch_repos(username)
    events = source.fetch_events(username)
    commits = source.fetch_commits(username, repos)

    # Fetch collaborators from repos where user has commits
    collaborators_data = _fetch_collaborators_data(
        username, commits, source
    )

    # Fetch avatar
    avatar_b64 = ""
    if user.get("avatar_url"):
        avatar_b64 = source.fetch_avatar(user["avatar_url"])

    return {
        "user": user,
        "repos": repos,
        "events": events,
        "commits": commits,
        "collaborators_data": collaborators_data,
        "avatar_b64": avatar_b64,
    }


def _fetch_collaborators_data(
    username: str,
    commits: list,
    source: GitHubDataSource,
) -> dict:
    """
    Fetch collaborator data from repos where user has committed.

    Uses config.COLLABORATOR_MIN_COMMITS threshold (default: 10) to filter
    out casual contributors and focus on meaningful collaborations.

    Args:
        username: The user's GitHub username
        commits: User's commits with repo context
        source: Data source to fetch from

    Returns:
        Dict mapping repo names to their contributors
    """
    # Find repos where user has commits
    user_repos = {}
    for commit in commits:
        repo_name = commit.get("_repo_name")
        if repo_name:
            user_repos[repo_name] = user_repos.get(repo_name, 0) + 1

    # Fetch contributors from user's top repos
    collaborators_by_repo = {}
    sorted_repos = sorted(user_repos.items(), key=lambda x: -x[1])[:COLLABORATOR_TOP_REPOS]

    for repo_name, user_commit_count in sorted_repos:
        # Fetch contributors with at least COLLABORATOR_MIN_COMMITS
        contributors = source.fetch_repo_contributors(repo_name, COLLABORATOR_MIN_COMMITS)

        # Filter out the user themselves
        contributors = [
            c for c in contributors
            if c.get("login", "").lower() != username.lower()
        ]

        # Skip repos with too many contributors (huge OSS projects)
        if len(contributors) < COLLABORATOR_MAX_REPO_SIZE:
            collaborators_by_repo[repo_name] = contributors

    return collaborators_by_repo
