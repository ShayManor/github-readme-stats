"""GitHub OAuth integration for the generator service.

Owns:
  - OAuth client registration (authlib)
  - `current_login()` — lowercase GitHub login from session, or None
  - `require_github_owner` — decorator: 401 if no session, 403 if mismatch
  - `require_same_origin` — decorator: 403 if Origin/Referer not in allowlist
"""
from functools import wraps
from urllib.parse import urlparse

from authlib.integrations.flask_client import OAuth
from flask import jsonify, request, session

from . import config

_oauth: OAuth | None = None


def init_oauth(app) -> OAuth:
    """Register the `github` provider. Safe to call once at app startup."""
    global _oauth
    oauth = OAuth(app)
    oauth.register(
        name="github",
        client_id=config.GITHUB_OAUTH_CLIENT_ID,
        client_secret=config.GITHUB_OAUTH_CLIENT_SECRET,
        access_token_url="https://github.com/login/oauth/access_token",
        authorize_url="https://github.com/login/oauth/authorize",
        api_base_url="https://api.github.com/",
        client_kwargs={"scope": "read:user"},
    )
    _oauth = oauth
    return oauth


def github_client():
    if _oauth is None:
        raise RuntimeError("OAuth not initialized — call init_oauth(app) first.")
    return _oauth.github


def current_login() -> str | None:
    v = session.get("gh_login")
    return v.lower() if isinstance(v, str) else None


def _origin_ok() -> bool:
    origin = request.headers.get("Origin") or request.headers.get("Referer") or ""
    if not origin:
        return False
    try:
        o = urlparse(origin)
        normalized = f"{o.scheme}://{o.netloc}"
    except Exception:
        return False
    return normalized in config.ALLOWED_ORIGINS


def require_github_owner(fn):
    """401 if no session; 403 if session login != url username (case-insensitive)."""
    @wraps(fn)
    def wrapper(username: str, *args, **kwargs):
        me = current_login()
        if me is None:
            return jsonify({"error": "login_required"}), 401
        if me != (username or "").lower():
            return jsonify({"error": "forbidden"}), 403
        return fn(username, *args, **kwargs)
    return wrapper


def require_same_origin(fn):
    """Defense in depth beyond SameSite=Lax. Rejects cross-site mutate attempts."""
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not _origin_ok():
            return jsonify({"error": "bad_origin"}), 403
        return fn(*args, **kwargs)
    return wrapper
