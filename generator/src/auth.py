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


import base64
import hmac as _hmac
from functools import wraps as _wraps
from flask import jsonify as _jsonify, request as _request

from . import config as _config


def require_basic_auth(fn):
    """HTTP Basic Auth gate for the /dev dashboard. Returns 503 if either
    credential env var is unset so a missing-secret deploy fails closed.
    Constant-time comparison on the decoded user+pass concatenation keeps
    the timing channel narrow without leaking length."""
    @_wraps(fn)
    def wrapper(*args, **kwargs):
        u = _config.DEV_DASHBOARD_USER
        p = _config.DEV_DASHBOARD_PASSWORD
        if not u or not p:
            return _jsonify({"error": "dashboard_disabled"}), 503
        hdr = _request.headers.get("Authorization", "")
        if not hdr.startswith("Basic "):
            return _unauth()
        try:
            decoded = base64.b64decode(hdr[6:].encode("ascii"), validate=True).decode("utf-8")
        except Exception:
            return _unauth()
        expected = f"{u}:{p}"
        if not _hmac.compare_digest(decoded, expected):
            return _unauth()
        return fn(*args, **kwargs)
    return wrapper


def _unauth():
    resp = _jsonify({"error": "unauthorized"})
    resp.status_code = 401
    resp.headers["WWW-Authenticate"] = 'Basic realm="dev"'
    return resp
