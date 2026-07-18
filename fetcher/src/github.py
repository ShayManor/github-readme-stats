"""GitHub data fetching functions."""

import re
import requests
import base64
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional, Protocol

from . import config


# GitHub's own username rules: alphanumerics and hyphens, 1–39 chars, no
# leading/trailing hyphen, no double-hyphens. The fetcher hard-refuses
# anything else before it reaches URL construction or GraphQL interpolation —
# the generator validates too, but this is the last line of defense before
# we talk to GitHub on a caller's behalf.
_USERNAME_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9]|-(?=[A-Za-z0-9])){0,38}$")

# Repo full names: owner/repo. Owner matches the username rule; repo allows the
# same chars plus dot and underscore (matches GitHub's repo-name regex).
_REPO_FULL_NAME_RE = re.compile(
    r"^[A-Za-z0-9](?:[A-Za-z0-9]|-(?=[A-Za-z0-9])){0,38}"
    r"/[A-Za-z0-9_.-]{1,100}$"
)


def _assert_username(name: str) -> str:
    if not isinstance(name, str) or not _USERNAME_RE.match(name):
        raise ValueError(f"invalid github username: {name!r}")
    return name


def _assert_repo_full_name(name: str) -> str:
    if not isinstance(name, str) or not _REPO_FULL_NAME_RE.match(name):
        raise ValueError(f"invalid github repo name: {name!r}")
    return name


class GitHubTransientError(Exception):
    """A GitHub call failed transiently (rate limit, 5xx, or a network error)
    rather than returning real data.

    This MUST NOT be swallowed into a zero/empty count. A contribution count
    computed from a rate-limited response is 0, and persisting that 0 silently
    overwrites the last good value in fetcher.db — which is exactly how a
    traffic spike turns into permanently-wrong "0 commits" cards until the
    next successful fetch. Propagate it instead so the caller aborts the fetch
    and keeps the previously-cached record."""


def _raise_if_transient(resp) -> None:
    """Raise GitHubTransientError if `resp` looks like a rate limit or server
    error. A genuine NOT_FOUND (unknown user) is left alone — that is a real,
    persistable "this user has no data" answer, not a transient failure."""
    if resp.status_code in (429, 500, 502, 503, 504):
        raise GitHubTransientError(f"HTTP {resp.status_code}")
    # Primary/secondary REST rate limits come back as 403 with the remaining
    # budget at 0 (or a "secondary rate limit" message).
    if resp.status_code == 403 and resp.headers.get("X-RateLimit-Remaining") == "0":
        raise GitHubTransientError("REST rate limit exhausted")
    # GraphQL reports rate limits as HTTP 200 with an `errors` array — the same
    # 200 that a valid response uses — so the body has to be inspected.
    try:
        body = resp.json()
    except ValueError:
        return
    for err in (body.get("errors") or []):
        if err.get("type") in ("RATE_LIMITED", "SERVICE_UNAVAILABLE"):
            raise GitHubTransientError(err.get("message") or err.get("type"))


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

    def fetch_user_commit_repos(self, username: str, since_date: str) -> list:
        """Fetch repos the user has committed to, with per-repo user commit counts."""
        ...

    def fetch_avatar(self, avatar_url: str) -> str:
        """Fetch and encode avatar as base64."""
        ...

    def fetch_repo_languages(self, full_name: str) -> dict:
        """Return {language: bytes} for a single repo, or {} on failure."""
        ...


class DirectAPISource:
    """Direct GitHub API implementation - for immediate requests."""

    def __init__(self, token: Optional[str] = None):
        self.token = token
        self.headers = {"Accept": "application/vnd.github.v3+json"}
        if token:
            self.headers["Authorization"] = f"token {token}"
        self.base = "https://api.github.com"

    def _graphql(self, query: str, variables: Optional[dict] = None) -> Optional[dict]:
        """
        Execute a GraphQL query against the GitHub API.

        Returns the `data` block of the response, or None on any failure.
        GraphQL requires a Bearer token, not `token ...`.
        """
        headers = {**self.headers, "Content-Type": "application/json"}
        auth = headers.get("Authorization", "")
        if auth.startswith("token "):
            headers["Authorization"] = auth.replace("token ", "Bearer ", 1)

        payload = {"query": query}
        if variables is not None:
            payload["variables"] = variables

        try:
            resp = requests.post(
                "https://api.github.com/graphql",
                json=payload,
                headers=headers,
                timeout=config.API_TIMEOUT,
            )
        except Exception as e:
            print(f"  GraphQL request failed: {e}")
            return None

        if not resp.ok:
            print(f"  GraphQL HTTP {resp.status_code}: {resp.text[:200]}")
            return None

        body = resp.json()
        if "errors" in body:
            print(f"  GraphQL errors: {body['errors']}")
            return None
        return body.get("data")

    def fetch_user_data(self, username: str) -> dict:
        """Fetch user profile data."""
        _assert_username(username)
        return requests.get(
            f"{self.base}/users/{username}",
            headers=self.headers,
            timeout=config.API_TIMEOUT,
        ).json()

    def fetch_repos(self, username: str) -> list:
        """Fetch user repositories (owned + contributed to)."""
        _assert_username(username)

        def _get(repo_type: str):
            return requests.get(
                f"{self.base}/users/{username}/repos",
                headers=self.headers,
                params={"per_page": 100, "sort": "pushed", "type": repo_type},
                timeout=config.API_TIMEOUT,
            ).json()

        # The two REST calls are independent — fire them in parallel so the
        # second isn't waiting on the first to come back.
        with ThreadPoolExecutor(max_workers=2, thread_name_prefix="fetch-repos") as pool:
            fut_owned = pool.submit(_get, "owner")
            fut_all = pool.submit(_get, "all")
            owned = fut_owned.result()
            all_repos = fut_all.result()

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
        _assert_username(username)
        resp = requests.get(
            f"{self.base}/users/{username}/events",
            headers=self.headers,
            params={"per_page": 100},
            timeout=config.API_TIMEOUT,
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
            _assert_username(username)
            # Get the last year of contribution data
            now = datetime.now()
            one_year_ago = now.replace(year=now.year - 1)
            from_date = one_year_ago.strftime("%Y-%m-%dT%H:%M:%SZ")
            to_date = now.strftime("%Y-%m-%dT%H:%M:%SZ")

            # Parameterize username + date range — interpolating username into
            # the query lets a malicious name break out of the string literal
            # and smuggle additional GraphQL fields. GitHub's PAT scopes bound
            # the damage, but the injection is still worth shutting down.
            query = """
            query($login: String!, $from: DateTime!, $to: DateTime!) {
              user(login: $login) {
                contributionsCollection(from: $from, to: $to) {
                  contributionCalendar {
                    weeks {
                      contributionDays {
                        date
                        contributionCount
                      }
                    }
                  }
                }
              }
            }
            """

            headers = {
                **self.headers,
                'Content-Type': 'application/json'
            }
            # GraphQL uses Bearer token
            if 'Authorization' in headers and headers['Authorization'].startswith('token '):
                headers['Authorization'] = headers['Authorization'].replace('token ', 'Bearer ')

            resp = requests.post(
                'https://api.github.com/graphql',
                json={
                    'query': query,
                    'variables': {'login': username, 'from': from_date, 'to': to_date},
                },
                headers=headers,
                timeout=config.API_TIMEOUT
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
        except GitHubTransientError:
            # Rate limit / 5xx: abort the fetch so the caller keeps the last
            # good count instead of persisting a spurious 0.
            raise
        except requests.RequestException as e:
            # A network-level failure is transient too.
            raise GitHubTransientError(str(e))
        except Exception as e:
            print(f"  Error fetching contribution count: {e}")
            return 0

    def _fetch_commit_count_graphql_alltime(self, username: str) -> int:
        """Fetch all-time contribution count using GraphQL."""
        from datetime import datetime

        _assert_username(username)
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
            timeout=config.API_TIMEOUT
        )

        _raise_if_transient(resp)
        if not resp.ok or 'data' not in resp.json():
            print(f"  GraphQL error: {resp.status_code}")
            return 0

        data = resp.json()
        if not data.get('data', {}).get('user'):
            return 0

        created_at = data['data']['user']['createdAt']
        created_year = int(created_at[:4])
        current_year = datetime.now().year

        # Fetch year by year, in parallel. Sequentially this was 1 request
        # per year of account age (~7-10 calls for typical accounts), each
        # ~1s — easily a 10s wall-clock contributor on its own.
        print(f"  Fetching contributions from {created_year} to {current_year}...")
        year_query = """
        query($login: String!, $from: DateTime!, $to: DateTime!) {
          user(login: $login) {
            contributionsCollection(from: $from, to: $to) {
              contributionCalendar { totalContributions }
            }
          }
        }
        """

        def _fetch_year(year: int) -> tuple[int, int]:
            year_resp = requests.post(
                'https://api.github.com/graphql',
                json={
                    'query': year_query,
                    'variables': {
                        'login': username,
                        'from': f"{year}-01-01T00:00:00Z",
                        'to': f"{year}-12-31T23:59:59Z",
                    },
                },
                headers=headers,
                timeout=config.API_TIMEOUT,
            )
            _raise_if_transient(year_resp)
            if not year_resp.ok:
                print(f"    {year}: HTTP {year_resp.status_code}")
                return year, 0
            year_data = year_resp.json()
            if 'data' in year_data and year_data['data'].get('user'):
                n = year_data['data']['user']['contributionsCollection']['contributionCalendar']['totalContributions']
                return year, n
            print(f"    {year}: Error - {year_data}")
            return year, 0

        years = list(range(created_year, current_year + 1))
        total_contributions = 0
        with ThreadPoolExecutor(max_workers=min(10, len(years) or 1)) as pool:
            for year, n in sorted(pool.map(_fetch_year, years)):
                total_contributions += n
                print(f"    {year}: {n:,} contributions")

        print(f"  GraphQL API found {total_contributions:,} contributions (all-time)")
        return total_contributions

    def _fetch_commit_count_graphql_range(self, username: str, since_date: str) -> int:
        """Fetch contribution count for a specific date range using GraphQL."""
        from datetime import datetime

        _assert_username(username)
        # Convert since_date to proper format
        from_date = f"{since_date}T00:00:00Z"
        to_date = datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")

        query = """
        query($login: String!, $from: DateTime!, $to: DateTime!) {
          user(login: $login) {
            contributionsCollection(from: $from, to: $to) {
              contributionCalendar { totalContributions }
            }
          }
        }
        """

        headers = {
            **self.headers,
            'Content-Type': 'application/json'
        }
        # GraphQL uses Bearer token
        if 'Authorization' in headers and headers['Authorization'].startswith('token '):
            headers['Authorization'] = headers['Authorization'].replace('token ', 'Bearer ')

        resp = requests.post(
            'https://api.github.com/graphql',
            json={
                'query': query,
                'variables': {'login': username, 'from': from_date, 'to': to_date},
            },
            headers=headers,
            timeout=config.API_TIMEOUT,
        )

        _raise_if_transient(resp)
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
                timeout=config.API_TIMEOUT
            )

            _raise_if_transient(resp)
            if resp.ok:
                data = resp.json()
                return data.get("total_count", 0)
        except GitHubTransientError:
            raise
        except requests.RequestException as e:
            raise GitHubTransientError(str(e))
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
                timeout=config.API_TIMEOUT
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

    def fetch_user_commit_repos(self, username: str, since_date: str) -> list:
        """
        Fetch all repos the user has committed to in the given window, with the
        user's own commit count per repo — via one GraphQL call.

        Args:
            username: GitHub username
            since_date: ISO date (YYYY-MM-DD) — start of lookback window

        Returns:
            List of dicts: [{full_name, is_fork, is_owner, user_commits, url}, ...]
        """
        from datetime import datetime

        from_ts = f"{since_date}T00:00:00Z"
        to_ts = datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")

        query = """
        query($username: String!, $from: DateTime!, $to: DateTime!) {
          user(login: $username) {
            contributionsCollection(from: $from, to: $to) {
              commitContributionsByRepository(maxRepositories: 100) {
                contributions { totalCount }
                repository {
                  nameWithOwner
                  isFork
                  url
                  owner { login }
                }
              }
            }
          }
        }
        """

        data = self._graphql(
            query,
            variables={"username": username, "from": from_ts, "to": to_ts},
        )
        if not data or not data.get("user"):
            return []

        out = []
        contrib_repos = (
            data["user"]["contributionsCollection"]["commitContributionsByRepository"]
        )
        for entry in contrib_repos:
            repo = entry.get("repository") or {}
            full_name = repo.get("nameWithOwner")
            if not full_name:
                continue
            out.append({
                "full_name": full_name,
                "is_fork": bool(repo.get("isFork")),
                "is_owner": (repo.get("owner") or {}).get("login", "").lower() == username.lower(),
                "user_commits": entry.get("contributions", {}).get("totalCount", 0),
                "url": repo.get("url", ""),
            })

        print(f"  GraphQL found {len(out)} repos user committed to (since {since_date})")
        return out

    def fetch_avatar(self, avatar_url: str) -> str:
        """Fetch and encode avatar as base64."""
        try:
            resp = requests.get(avatar_url + "&s=64", timeout=config.API_TIMEOUT)
            if resp.ok:
                return base64.b64encode(resp.content).decode("ascii")
        except Exception:
            pass
        return ""

    def fetch_repo_languages(self, full_name: str) -> dict:
        """Return {language: bytes} for a repo. REST returns exactly this
        shape — total is summed client-side."""
        try:
            resp = requests.get(
                f"{self.base}/repos/{full_name}/languages",
                headers=self.headers,
                timeout=config.API_TIMEOUT,
            )
            if resp.ok:
                data = resp.json()
                return data if isinstance(data, dict) else {}
        except Exception:
            pass
        return {}


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

    six_months_ago = (datetime.now() - timedelta(days=180)).strftime("%Y-%m-%d")

    # Stage 1: every fetch with no dependencies on another fetch's result
    # runs in parallel. Previously these 8 calls ran one at a time, so the
    # whole pipeline was wait-time × 8. Each is I/O-bound (a single HTTPS
    # request to GitHub or a small GraphQL query), so threading is the
    # right primitive. _fetch_collaborators_data internally calls
    # fetch_user_commit_repos and ignores the `repos` arg, so it has no
    # ordering dependency on fetch_repos — start them together.
    with ThreadPoolExecutor(max_workers=10, thread_name_prefix="fetch-stage1") as pool:
        fut_user = pool.submit(source.fetch_user_data, username)
        fut_repos = pool.submit(source.fetch_repos, username)
        fut_events = pool.submit(source.fetch_events, username)
        fut_commits = pool.submit(source.fetch_commits, username)
        fut_total = pool.submit(source.fetch_commit_count, username, [])
        fut_recent = pool.submit(source.fetch_commit_count, username, [], six_months_ago)
        fut_prs = pool.submit(source.fetch_pr_count, username)
        fut_collab = pool.submit(_fetch_collaborators_data, username, [], source)

        user = fut_user.result()
        repos = fut_repos.result()
        events = fut_events.result()
        commits = fut_commits.result()
        total_commits = fut_total.result()
        recent_commits = fut_recent.result()
        total_prs = fut_prs.result()
        collaborators_data = fut_collab.result()

    # Stage 2: avatar needs user.avatar_url, languages need the repos list.
    # Both run in parallel against each other.
    avatar_b64 = ""
    avatar_url = user.get("avatar_url") if isinstance(user, dict) else None
    with ThreadPoolExecutor(max_workers=2, thread_name_prefix="fetch-stage2") as pool:
        fut_lang = pool.submit(_enrich_repo_languages, repos, source)
        fut_avatar = pool.submit(source.fetch_avatar, avatar_url) if avatar_url else None
        fut_lang.result()
        if fut_avatar is not None:
            avatar_b64 = fut_avatar.result()

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


def _enrich_repo_languages(repos: list, source: GitHubDataSource) -> None:
    """Mutates `repos` in-place, attaching `language_bytes: {lang: bytes}` to
    each repo. Uses a small thread pool — one REST call per repo is cheap
    individually, but sequentially N repos would block the fetch noticeably."""
    if not repos:
        return
    names = [(i, r["full_name"]) for i, r in enumerate(repos) if r.get("full_name")]
    print(f"  Fetching language byte breakdown for {len(names)} repos...")
    with ThreadPoolExecutor(max_workers=10) as pool:
        futures = {pool.submit(source.fetch_repo_languages, fn): i for i, fn in names}
        for fut in as_completed(futures):
            i = futures[fut]
            try:
                repos[i]["language_bytes"] = fut.result() or {}
            except Exception:
                repos[i]["language_bytes"] = {}


def _fetch_collaborators_data(
    username: str,
    repos: list,
    source: GitHubDataSource,
) -> list:
    """
    Find meaningful collaborators using a user-weighted scoring model.

    Pipeline:
      1. GraphQL: fetch repos the user has committed to in the last year, with
         the user's own commit count in each.
      2. Filter out forks unless the user has meaningful commits in them, and
         drop repos with too few user commits overall.
      3. For each surviving repo, REST-fetch contributors.
      4. Score each contributor as min(user_commits, their_commits) — you can't
         collaborate more than the smaller side contributed.
      5. Apply owner boost, then rank by (raw_score * shared_repos).
      6. Drop collaborators below the multi-repo / deep-collab floors.

    Returns:
        List of scored collaborators, sorted by final_score desc:
        [{"login", "avatar_url", "raw_score", "shared_repos", "final_score", "repos"}, ...]
    """
    from datetime import datetime, timedelta

    # Bots and automated accounts that show up as "contributors" but aren't collaborators.
    BOT_LOGINS = {
        "claude", "claude-code", "dependabot", "dependabot-preview",
        "github-actions", "renovate", "renovate-bot", "imgbot",
        "greenkeeper", "snyk-bot", "codecov",
    }

    def _is_bot(login: str) -> bool:
        low = login.lower()
        return low in BOT_LOGINS or low.endswith("[bot]") or low.endswith("-bot")

    since = (datetime.now() - timedelta(days=config.COLLABORATOR_LOOKBACK_DAYS)).strftime("%Y-%m-%d")
    commit_repos = source.fetch_user_commit_repos(username, since)
    if not commit_repos:
        return []

    # Step 2: filter by meaningful user activity
    qualifying = []
    for r in commit_repos:
        user_commits = r.get("user_commits", 0)
        if user_commits < config.MEANINGFUL_MIN_COMMITS:
            continue
        if r.get("is_fork") and user_commits < config.FORK_MIN_COMMITS:
            continue
        qualifying.append(r)

    # Rank user's repos by their own commit count, scan top N
    qualifying.sort(key=lambda r: -r.get("user_commits", 0))
    qualifying = qualifying[:config.COLLABORATOR_TOP_REPOS]
    print(f"  Scoring collaborators across {len(qualifying)} qualifying repos")

    # Step 3: fetch contributors for all qualifying repos in parallel.
    # The per-repo REST call is ~300-500ms; sequentially this dominated the
    # whole fetch (30 repos × ~0.5s ≈ 15s). Fan out with the same pool size
    # used for languages — GitHub's secondary rate limit tolerates this fine.
    contributors_by_repo: dict[str, list] = {}
    with ThreadPoolExecutor(max_workers=10) as pool:
        futures = {
            pool.submit(source.fetch_repo_contributors, r["full_name"], 1): r["full_name"]
            for r in qualifying
        }
        for fut in as_completed(futures):
            full_name = futures[fut]
            try:
                contributors_by_repo[full_name] = fut.result() or []
            except Exception as e:
                print(f"    failed to fetch contributors for {full_name}: {e}")
                contributors_by_repo[full_name] = []

    # Step 4: score sequentially (cheap, in-memory) preserving the original
    # `qualifying` order so deterministic-output tests still pass.
    collab_stats: dict = {}
    for r in qualifying:
        full_name = r["full_name"]
        user_commits = r["user_commits"]
        boost = config.OWNER_BOOST if r["is_owner"] else 1.0

        contributors = contributors_by_repo.get(full_name, [])
        # Drop huge OSS projects
        if len(contributors) >= config.COLLABORATOR_MAX_REPO_SIZE:
            print(f"    skipping {full_name}: too many contributors ({len(contributors)})")
            continue

        # A "tight" repo: one the user owns with few contributors — hackathon
        # and side-project partners qualify from a single such repo.
        is_tight_owned = r["is_owner"] and len(contributors) <= config.SMALL_OWNED_REPO_SIZE

        for c in contributors:
            login = c.get("login", "")
            if not login or login.lower() == username.lower() or _is_bot(login):
                continue
            their_commits = c.get("contributions", 0)
            # Scoring:
            # - Tight owned repo: their investment IS the collaboration signal
            #   (partner poured commits into *your* project). Use their_commits.
            # - Otherwise: min() prevents a prolific stranger in a large repo
            #   from dominating based on work you weren't part of.
            if is_tight_owned:
                contribution = their_commits * boost
            else:
                contribution = min(user_commits, their_commits) * boost

            stat = collab_stats.setdefault(login, {
                "login": login,
                "avatar_url": c.get("avatar_url", ""),
                "raw_score": 0.0,
                "repos": [],
                "tight_owned_partner": False,
            })
            stat["raw_score"] += contribution
            stat["repos"].append(full_name)
            if is_tight_owned:
                stat["tight_owned_partner"] = True
            if not stat["avatar_url"]:
                stat["avatar_url"] = c.get("avatar_url", "")

    # Step 5: composite score rewards multi-repo presence
    scored = []
    for stat in collab_stats.values():
        shared = len(stat["repos"])
        stat["shared_repos"] = shared
        stat["final_score"] = stat["raw_score"] * shared
        scored.append(stat)

    # Step 6: qualification floor — either multi-repo, deep single-repo,
    # or a partner in a tight user-owned project (hackathon/side-project).
    filtered = [
        s for s in scored
        if s["shared_repos"] >= config.MIN_SHARED_REPOS
        or s["raw_score"] >= config.DEEP_COLLAB_THRESHOLD
        or s["tight_owned_partner"]
    ]

    filtered.sort(key=lambda s: -s["final_score"])

    print(f"  Found {len(filtered)} collaborators after filtering ({len(scored)} before)")
    for s in filtered[:6]:
        print(f"    {s['login']}: final={s['final_score']:.0f} raw={s['raw_score']:.0f} repos={s['shared_repos']}")

    return filtered
