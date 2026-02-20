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

    def fetch_commits(self, username: str, repos: list = None) -> list:
        """Fetch daily commit data from contribution calendar."""
        ...

    def fetch_commit_count(self, username: str, repos: list, since_date: str = None) -> int:
        """Fetch total commit count by aggregating from repos."""
        ...

    def fetch_pr_count(self, username: str) -> int:
        """Fetch total PR count using search API."""
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

    def fetch_commits(self, username: str, repos: list = None) -> list:
        """
        Fetch daily commit data using GitHub's GraphQL contributionsCollection.

        Uses the contribution calendar to get accurate daily commit counts
        matching what GitHub shows on the user's profile page.

        Args:
            username: GitHub username
            repos: Not used, kept for interface compatibility

        Returns:
            List of daily commit data: [{"date": "YYYY-MM-DD", "count": N}, ...]
        """
        from datetime import datetime

        try:
            # Get the last year of contribution data
            now = datetime.now()
            one_year_ago = now.replace(year=now.year - 1)
            from_date = one_year_ago.strftime("%Y-%m-%dT%H:%M:%SZ")
            to_date = now.strftime("%Y-%m-%dT%H:%M:%SZ")

            query = f'''
            query {{
              user(login: "{username}") {{
                contributionsCollection(from: "{from_date}", to: "{to_date}") {{
                  contributionCalendar {{
                    weeks {{
                      contributionDays {{
                        date
                        contributionCount
                      }}
                    }}
                  }}
                }}
              }}
            }}
            '''

            headers = {
                **self.headers,
                'Content-Type': 'application/json'
            }
            # GraphQL uses Bearer token
            if 'Authorization' in headers and headers['Authorization'].startswith('token '):
                headers['Authorization'] = headers['Authorization'].replace('token ', 'Bearer ')

            resp = requests.post(
                'https://api.github.com/graphql',
                json={'query': query},
                headers=headers,
                timeout=API_TIMEOUT
            )

            if not resp.ok:
                print(f"  GraphQL error fetching commits: {resp.status_code}")
                return []

            data = resp.json()
            if 'data' not in data or not data['data'].get('user'):
                print("  No user data in GraphQL response")
                return []

            # Extract daily commit data
            daily_commits = []
            weeks = data['data']['user']['contributionsCollection']['contributionCalendar']['weeks']

            for week in weeks:
                for day in week['contributionDays']:
                    if day['contributionCount'] > 0:  # Only include days with commits
                        daily_commits.append({
                            'date': day['date'],
                            'count': day['contributionCount']
                        })

            print(f"  GraphQL API found {len(daily_commits)} days with commits")
            return daily_commits

        except Exception as e:
            print(f"  Error fetching daily commits via GraphQL: {e}")
            return []

    def fetch_commit_count(self, username: str, repos: list, since_date: str = None) -> int:
        """
        Fetch total contribution count using GitHub GraphQL API.

        Uses the contributionsCollection to get accurate contribution counts (commits, PRs,
        issues, reviews) matching what GitHub shows on user profiles and what streak-stats displays.
        Fetches year-by-year to get all-time total.

        Args:
            username: GitHub username
            repos: List of repository dicts (unused, kept for interface compatibility)
            since_date: ISO date string (YYYY-MM-DD) to filter contributions after this date

        Returns:
            Total number of contributions (commits + PRs + issues + reviews)
        """
        from datetime import datetime

        try:
            # If since_date is provided, use specific date range
            if since_date:
                return self._fetch_commit_count_graphql_range(username, since_date)
            else:
                return self._fetch_commit_count_graphql_alltime(username)
        except Exception as e:
            print(f"  Error fetching contribution count: {e}")
            return 0

    def _fetch_commit_count_graphql_alltime(self, username: str) -> int:
        """Fetch all-time contribution count using GraphQL."""
        from datetime import datetime

        # First, get account creation date
        query = '''
        query($username: String!) {
          user(login: $username) {
            createdAt
          }
        }
        '''

        headers = {
            **self.headers,
            'Content-Type': 'application/json'
        }
        # GraphQL uses Bearer token instead of 'token'
        if 'Authorization' in headers and headers['Authorization'].startswith('token '):
            headers['Authorization'] = headers['Authorization'].replace('token ', 'Bearer ')

        resp = requests.post(
            'https://api.github.com/graphql',
            json={'query': query, 'variables': {'username': username}},
            headers=headers,
            timeout=API_TIMEOUT
        )

        if not resp.ok or 'data' not in resp.json():
            print(f"  GraphQL error: {resp.status_code}")
            return 0

        data = resp.json()
        if not data.get('data', {}).get('user'):
            return 0

        created_at = data['data']['user']['createdAt']
        created_year = int(created_at[:4])
        current_year = datetime.now().year

        # Fetch year by year
        total_contributions = 0
        print(f"  Fetching contributions from {created_year} to {current_year}...")
        for year in range(created_year, current_year + 1):
            year_query = f'''
            query {{
              user(login: "{username}") {{
                contributionsCollection(from: "{year}-01-01T00:00:00Z", to: "{year}-12-31T23:59:59Z") {{
                  contributionCalendar {{
                    totalContributions
                  }}
                }}
              }}
            }}
            '''

            year_resp = requests.post(
                'https://api.github.com/graphql',
                json={'query': year_query},
                headers=headers,
                timeout=API_TIMEOUT
            )

            if year_resp.ok:
                year_data = year_resp.json()
                if 'data' in year_data and year_data['data'].get('user'):
                    year_contributions = year_data['data']['user']['contributionsCollection']['contributionCalendar']['totalContributions']
                    total_contributions += year_contributions
                    print(f"    {year}: {year_contributions:,} contributions")
                else:
                    print(f"    {year}: Error - {year_data}")
            else:
                print(f"    {year}: HTTP {year_resp.status_code}")

        print(f"  GraphQL API found {total_contributions:,} contributions (all-time)")
        return total_contributions

    def _fetch_commit_count_graphql_range(self, username: str, since_date: str) -> int:
        """Fetch contribution count for a specific date range using GraphQL."""
        from datetime import datetime

        # Convert since_date to proper format
        from_date = f"{since_date}T00:00:00Z"
        to_date = datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")

        query = f'''
        query {{
          user(login: "{username}") {{
            contributionsCollection(from: "{from_date}", to: "{to_date}") {{
              contributionCalendar {{
                totalContributions
              }}
            }}
          }}
        }}
        '''

        headers = {
            **self.headers,
            'Content-Type': 'application/json'
        }
        # GraphQL uses Bearer token
        if 'Authorization' in headers and headers['Authorization'].startswith('token '):
            headers['Authorization'] = headers['Authorization'].replace('token ', 'Bearer ')

        resp = requests.post(
            'https://api.github.com/graphql',
            json={'query': query},
            headers=headers,
            timeout=API_TIMEOUT
        )

        if resp.ok:
            data = resp.json()
            if 'data' in data and data['data'].get('user'):
                total = data['data']['user']['contributionsCollection']['contributionCalendar']['totalContributions']
                print(f"  GraphQL API found {total:,} contributions (since {since_date})")
                return total

        print(f"  GraphQL error: {resp.status_code if resp else 'unknown'}")
        return 0

    def fetch_pr_count(self, username: str) -> int:
        """
        Fetch total PR count using GitHub search API.

        Args:
            username: GitHub username

        Returns:
            Total number of PRs authored by user
        """
        try:
            query = f"is:pr author:{username}"

            resp = requests.get(
                f"{self.base}/search/issues",
                headers=self.headers,
                params={"q": query, "per_page": 1},
                timeout=API_TIMEOUT
            )

            if resp.ok:
                data = resp.json()
                return data.get("total_count", 0)
        except Exception as e:
            print(f"Warning: Failed to fetch PR count via search API: {e}")

        return 0

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
        Dict with user, repos, events, commits, commit counts, collaborators_data, and avatar_b64
    """
    from datetime import datetime, timedelta

    # Use provided data source or default to direct API
    source = data_source or DirectAPISource(token)

    # Fetch all data through the data source abstraction
    user = source.fetch_user_data(username)
    repos = source.fetch_repos(username)
    events = source.fetch_events(username)
    commits = source.fetch_commits(username)

    # Fetch contribution counts (commits + PRs + issues + reviews)
    print("  Fetching all-time contribution count...")
    total_commits = source.fetch_commit_count(username, repos)

    # Recent contributions (last 6 months)
    six_months_ago = (datetime.now() - timedelta(days=180)).strftime("%Y-%m-%d")
    print("  Fetching recent contribution count (last 6 months)...")
    recent_commits = source.fetch_commit_count(username, repos, since_date=six_months_ago)

    # Fetch PR count
    print("  Fetching PR count...")
    total_prs = source.fetch_pr_count(username)

    # Fetch collaborators from user's active repos
    collaborators_data = _fetch_collaborators_data(
        username, repos, source
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
        "total_commits": total_commits,
        "recent_commits": recent_commits,
        "total_prs": total_prs,
        "collaborators_data": collaborators_data,
        "avatar_b64": avatar_b64,
    }


def _fetch_collaborators_data(
    username: str,
    repos: list,
    source: GitHubDataSource,
) -> dict:
    """
    Fetch collaborator data from user's most active repositories.

    Uses config.COLLABORATOR_MIN_COMMITS threshold (default: 5) to filter
    out casual contributors and focus on meaningful collaborations.

    Args:
        username: The user's GitHub username
        repos: List of user's repositories
        source: Data source to fetch from

    Returns:
        Dict mapping repo names to their contributors
    """
    # Use the user's most recently pushed repos
    sorted_repos = sorted(
        repos,
        key=lambda r: r.get("pushed_at", ""),
        reverse=True
    )[:COLLABORATOR_TOP_REPOS]

    collaborators_by_repo = {}

    for repo in sorted_repos:
        repo_name = repo.get("full_name")
        if not repo_name:
            continue

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
