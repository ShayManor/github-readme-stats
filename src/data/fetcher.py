"""GitHub data fetching functions."""

import requests
import base64
from typing import Optional


def fetch_github_data(username: str, token: Optional[str] = None) -> dict:
    """
    Fetches all relevant GitHub data for a user.
    Returns a dict with user profile, repos, events, and avatar.
    """
    headers = {"Accept": "application/vnd.github.v3+json"}
    if token:
        headers["Authorization"] = f"token {token}"

    base = "https://api.github.com"

    # User profile
    user = requests.get(f"{base}/users/{username}", headers=headers).json()

    # Repos (up to 100)
    repos = requests.get(
        f"{base}/users/{username}/repos",
        headers=headers,
        params={"per_page": 100, "sort": "pushed", "type": "owner"},
    ).json()

    # Events (recent activity)
    events = requests.get(
        f"{base}/users/{username}/events",
        headers=headers,
        params={"per_page": 100},
    ).json()

    # Avatar as base64
    avatar_b64 = ""
    if user.get("avatar_url"):
        try:
            resp = requests.get(user["avatar_url"] + "&s=64", timeout=5)
            if resp.ok:
                avatar_b64 = base64.b64encode(resp.content).decode("ascii")
        except Exception:
            pass

    return {
        "user": user,
        "repos": repos if isinstance(repos, list) else [],
        "events": events if isinstance(events, list) else [],
        "avatar_b64": avatar_b64,
    }
