"""Flask app for the generator service.

Serves:
  /               -> React SPA (static/index.html)
  /assets/<p>     -> SPA bundles
  /api/*          -> JSON/SVG API

Two-phase pipeline:
  * Enrollment / settings change enqueues a prefetch job and kicks it off
    in a background thread so the fetcher starts pulling GitHub data the
    instant the user submits a username. The thread only hydrates
    widget_data for the client-side Workshop preview — it does not render
    SVGs.
  * POST /api/<u>/generate synchronously renders and persists the composite
    SVG. This is what the user's "Generate" button calls.
"""
import hmac
import logging
import os
import time
from collections import defaultdict, deque
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from functools import wraps
from threading import BoundedSemaphore, Lock
from flask import Flask, jsonify, request, Response, send_from_directory, session

from . import analytics, auth, config, db, fetcher_client, placeholder, processor
from .themes import THEMES
from .utils import is_valid_username, settings_size_ok
from .widgets import render_grade_widget
import json as _json

log = logging.getLogger("generator.api")


# Bounded pool for prefetch kickoffs. The old code spawned an unbounded
# Thread() per request, so a burst of PATCH /settings would fork hundreds
# of threads each doing a GitHub fetch + SVG compute — easily enough to
# swamp a mini PC. The pool's workqueue absorbs spikes; excess kickoffs
# wait rather than executing in parallel.
_PREFETCH_POOL = ThreadPoolExecutor(
    max_workers=max(1, config.PREFETCH_MAX_WORKERS),
    thread_name_prefix="prefetch",
)

# Global cap on concurrent SVG renders. A render is the single most
# expensive user-facing operation; capping it makes the worst-case CPU
# load predictable regardless of how many callers pile on.
_GENERATE_SEMAPHORE = BoundedSemaphore(max(1, config.GENERATE_CONCURRENCY))


def _kickoff_prefetch(username: str):
    """Run one prefetch cycle in the bounded pool. Starts the fetcher
    soon after enrollment / settings-change so the raw GitHub payload
    is hot by the time the user clicks Generate, but never runs more
    than PREFETCH_MAX_WORKERS at once."""
    log.info("prefetch kickoff started for %s", username)
    try:
        from . import worker
        worker.process_one()
        log.info("prefetch kickoff finished for %s", username)
    except Exception:
        log.exception("prefetch kickoff failed for %s", username)


def _kickoff_prefetch_async(username: str):
    try:
        _PREFETCH_POOL.submit(_kickoff_prefetch, username)
    except RuntimeError:
        # Pool was shut down (process exiting). Dropping the kickoff is
        # safe: the cron loop will pick the job up on its next tick.
        log.warning("prefetch pool shut down; skipping kickoff for %s", username)


def _request_fetch_async(username: str) -> None:
    """Ask the fetcher to start a background GitHub fetch for `username`.

    Returns as soon as the fetcher acks (HTTP 202). The fetcher will POST
    back to /internal/data-ready when the data lands in fetcher.db, which
    is what enqueues the build job. Failures here are logged and dropped:
    the generator's cron loop will see the user on its next tick and try
    again, so a transient network blip can't permanently strand a signup.
    """
    try:
        fetcher_client.start_fetch_async(username)
    except Exception:
        log.warning("fetch-async kickoff failed for %s", username, exc_info=True)


# ---- Per-IP rate limiter -----------------------------------------------------
# In-process sliding-window limiter. Good enough for v1; behind a reverse proxy
# we read X-Forwarded-For (trusting only the last hop set by the proxy). For a
# multi-node deploy, swap this for a Redis-backed limiter.

_RATE_LIMITS = {
    # (endpoint_key): (max_hits, window_seconds). Defaults set in config.py
    # lean toward the mini PC — tighten further via env without redeploying.
    "mutate": (config.RATE_LIMIT_MUTATE_MAX, config.RATE_LIMIT_MUTATE_WINDOW),
    "read":   (config.RATE_LIMIT_READ_MAX,   config.RATE_LIMIT_READ_WINDOW),
}
_rate_lock = Lock()
_rate_hits: dict[tuple[str, str], deque] = defaultdict(deque)
_rate_hits_per_login: dict[tuple[str, str], deque] = defaultdict(deque)


def _client_ip() -> str:
    fwd = request.headers.get("X-Forwarded-For", "")
    if fwd:
        # Last value is the closest trusted proxy's client.
        return fwd.split(",")[-1].strip()
    return request.remote_addr or "unknown"


def _rate_limit(bucket: str) -> bool:
    """Return True if the request is allowed; False if it should be rejected."""
    limit, window = _RATE_LIMITS[bucket]
    ip = _client_ip()
    now = time.time()
    key = (bucket, ip)
    with _rate_lock:
        q = _rate_hits[key]
        cutoff = now - window
        while q and q[0] < cutoff:
            q.popleft()
        if len(q) >= limit:
            return False
        q.append(now)
    return True


def _rate_limit_per_login(bucket: str, login: str) -> bool:
    """Per-login rate limit layered on top of per-IP limit.

    Returns True if allowed; False if the login has exceeded the limit.
    If no login (unauthenticated), returns True (per-IP already covers it).
    """
    if not login:
        return True  # per-IP already covers the unauth path
    if bucket == "mutate":
        limit, window = config.RATE_LIMIT_MUTATE_PER_LOGIN_MAX, config.RATE_LIMIT_MUTATE_PER_LOGIN_WINDOW
    else:
        return True
    now = time.time()
    cutoff = now - window
    key = (bucket, login)
    with _rate_lock:
        q = _rate_hits_per_login[key]
        while q and q[0] < cutoff:
            q.popleft()
        if len(q) >= limit:
            return False
        q.append(now)
    return True


def rate_limited(bucket: str):
    def deco(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if not _rate_limit(bucket):
                return jsonify({"error": "rate_limited"}), 429
            if not _rate_limit_per_login(bucket, auth.current_login() or ""):
                return jsonify({"error": "rate_limited"}), 429
            return fn(*args, **kwargs)
        return wrapper
    return deco


def track_request(widget):
    """Record one analytics 'request' event per call. `widget` may be a
    literal string or a callable taking the route kwargs.

    The endpoint template comes from Flask's matched url_rule; the
    username is the route arg or `?username=` query param. Stack ABOVE
    @rate_limited so 429s are counted too — rate-limit hits are signal.
    """
    def deco(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            t0 = time.monotonic()
            resp = fn(*args, **kwargs)
            try:
                uname = kwargs.get("username") or request.args.get("username") or ""
                uname = uname.lower() if isinstance(uname, str) and uname else None
                if isinstance(resp, tuple):
                    status_code = resp[1] if len(resp) > 1 else 200
                else:
                    status_code = getattr(resp, "status_code", 200)
                rule = request.url_rule.rule if request.url_rule else ""
                endpoint = rule.replace("<username>", "<u>")
                w = widget(kwargs) if callable(widget) else widget
                analytics.record_request(
                    endpoint=endpoint, username=uname, widget=w,
                    status=int(status_code),
                    latency_ms=int((time.monotonic() - t0) * 1000),
                )
            except Exception:
                log.exception("analytics record_request failed")
            return resp
        return wrapper
    return deco




_STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")

app = Flask(__name__, static_folder=None)

if config.SECRET_KEY:
    app.secret_key = config.SECRET_KEY
else:
    # In tests and local dev we allow a weak default; production must set the env.
    app.secret_key = "dev-insecure-secret-do-not-use-in-prod"

app.config.update(
    SESSION_COOKIE_NAME="gh_session",
    SESSION_COOKIE_SECURE=config.SESSION_COOKIE_SECURE,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    PERMANENT_SESSION_LIFETIME=timedelta(days=30),
)

auth.init_oauth(app)

# Reject oversized bodies before they reach the DB. 128 KB is generous for our
# settings shape and still caps the memory footprint of a flood of PATCHes.
app.config["MAX_CONTENT_LENGTH"] = 128 * 1024


# ---- Settings shape validator -----------------------------------------------
# Settings flow from the public PATCH endpoint into SQLite and then into widget
# renderers. Unvalidated input means an attacker can DoS the render pipeline by
# storing an object that makes `int(settings["widget_settings"]["collaborators"]
# ["max_count"])` raise, or by ballooning the DB with unbounded fields.
# We normalize to an explicit allow-list of fields and coerce/trim types.

_ALLOWED_WIDGETS = {"name", "grade", "impact", "streaks", "collaborators", "focus", "languages", "achievements"}
_ALLOWED_ICONS = {"trophy", "medal", "star", "hackathon"}
_MAX_ACHIEVEMENTS = 10
_TITLE_MAX = 80
_SUBTITLE_MAX = 160
_EVENT_DATE_MAX = 32
_MAX_CUSTOM_TAGS = 10
_MAX_HIDDEN_LANGS = 40
_TAG_MAX = 40
_LANG_MAX = 40


def _clip_str(v, max_len: int) -> str:
    if v is None:
        return ""
    s = v if isinstance(v, str) else str(v)
    return s[:max_len]


def _coerce_achievement(a) -> dict | None:
    if not isinstance(a, dict):
        return None
    title = _clip_str(a.get("title"), _TITLE_MAX).strip()
    if not title:
        return None
    icon = a.get("icon") or "trophy"
    if not isinstance(icon, str) or icon not in _ALLOWED_ICONS:
        icon = "trophy"
    return {
        "title": title,
        "subtitle": _clip_str(a.get("subtitle"), _SUBTITLE_MAX),
        "event_date": _clip_str(a.get("event_date"), _EVENT_DATE_MAX),
        "icon": icon,
    }


def _coerce_str_list(v, max_items: int, max_item_len: int) -> list[str]:
    if not isinstance(v, list):
        return []
    out = []
    for x in v[:max_items]:
        if isinstance(x, str) and x:
            out.append(x[:max_item_len])
    return out


def _coerce_widget_settings(v) -> dict:
    """Whitelist per-widget settings down to the shape each renderer expects.
    Anything else is silently dropped — callers cannot smuggle arbitrary keys
    into the SVG renderers this way."""
    if not isinstance(v, dict):
        return {}
    out: dict[str, dict] = {}
    allowed = {
        "grade": {"max_tags": "int"},
        "impact": {"line_color": "color"},
        "streaks": {"color": "color"},
        "collaborators": {"max_count": "int", "bar_color": "color"},
        "focus": {"max_categories": "int"},
        "languages": {"max_languages": "int"},
        "achievements": {"max_items": "int"},
    }
    for widget, schema in allowed.items():
        raw = v.get(widget)
        if not isinstance(raw, dict):
            continue
        clean = {}
        for key, kind in schema.items():
            if key not in raw:
                continue
            val = raw[key]
            if kind == "int":
                try:
                    clean[key] = int(val)
                except (TypeError, ValueError):
                    continue
            elif kind == "bool":
                clean[key] = bool(val)
            elif kind == "color":
                # Deep color validation happens in the widget renderer
                # (safe_color). Here we only reject obviously wrong types
                # and length-bomb strings.
                if isinstance(val, str) and len(val) <= 32:
                    clean[key] = val
        if clean:
            out[widget] = clean
    return out


def sanitize_settings_query(args) -> dict:
    """Parse settings overrides from URL query params for the public
    `GET /api/<u>` endpoint. This is the unauthenticated edit path — the
    caller doesn't need to own the widget, they just craft a URL whose
    query string encodes their chosen settings.

    Accepted params (all optional, case-sensitive):

        theme=<name>                   - one of THEMES keys
        widgets=<csv>                  - enabled widget ids
        order=<csv>                    - widget render order
        hide=<csv>                     - languages to exclude
        tags=<csv>                     - extra custom tags
        <widget>.<key>=<value>         - per-widget settings (e.g. grade.max_tags=6,
                                         impact.line_color=%23a78bfa)
        ach=<url-safe-base64-json>     - list of {title, subtitle, event_date, icon}

    Unknown keys and malformed values are silently dropped; the same
    allow-listing rules as `sanitize_settings` apply. The result is a
    partial settings dict that can be merged onto the user's stored
    settings without any further validation.
    """
    out: dict = {}
    if args is None:
        return out

    theme = args.get("theme")
    if isinstance(theme, str) and theme in THEMES:
        out["theme"] = theme

    def _csv(key: str) -> list[str]:
        v = args.get(key) or ""
        return [s for s in (p.strip() for p in v.split(",")) if s]

    if "widgets" in args:
        out["enabled"] = [w for w in _csv("widgets") if w in _ALLOWED_WIDGETS][:20]
    if "order" in args:
        out["widget_order"] = [w for w in _csv("order") if w in _ALLOWED_WIDGETS][:20]
    if "hide" in args:
        out["hidden_languages"] = [s[:_LANG_MAX] for s in _csv("hide")[:_MAX_HIDDEN_LANGS]]
    if "tags" in args:
        out["custom_tags"] = [s[:_TAG_MAX] for s in _csv("tags")[:_MAX_CUSTOM_TAGS]]

    # Per-widget settings via dot-notation keys. Collect first, then hand off
    # to _coerce_widget_settings so type rules stay in exactly one place.
    ws_raw: dict[str, dict] = {}
    for key in args.keys():
        if "." not in key:
            continue
        widget, sub = key.split(".", 1)
        if widget not in _ALLOWED_WIDGETS:
            continue
        ws_raw.setdefault(widget, {})[sub] = args.get(key)
    if ws_raw:
        ws = _coerce_widget_settings(ws_raw)
        if ws:
            out["widget_settings"] = ws

    # Achievements as url-safe base64(json). Compact enough for reasonable
    # counts; longer embeds can still fall back to the authenticated path.
    ach_raw = args.get("ach")
    if isinstance(ach_raw, str) and ach_raw:
        try:
            import base64
            padded = ach_raw + "=" * (-len(ach_raw) % 4)
            decoded = base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8")
            parsed = _json.loads(decoded)
        except Exception:
            parsed = None
        if isinstance(parsed, list):
            cleaned = []
            for a in parsed[:_MAX_ACHIEVEMENTS]:
                ca = _coerce_achievement(a)
                if ca:
                    cleaned.append(ca)
            out["achievements"] = cleaned

    return out


def sanitize_settings(body: dict) -> dict:
    """Project an untrusted JSON object down to the fields we accept.

    This is the ONLY place that decides what the settings schema is. Anything
    not listed here is dropped. Widget renderers can assume the shape holds."""
    if not isinstance(body, dict):
        return {}
    out: dict = {}

    theme = body.get("theme")
    if isinstance(theme, str) and theme in THEMES:
        out["theme"] = theme

    if "enabled" in body:
        out["enabled"] = [w for w in _coerce_str_list(body["enabled"], 20, 32)
                         if w in _ALLOWED_WIDGETS]
    if "widget_order" in body:
        out["widget_order"] = [w for w in _coerce_str_list(body["widget_order"], 20, 32)
                              if w in _ALLOWED_WIDGETS]

    if "custom_tags" in body:
        out["custom_tags"] = _coerce_str_list(body["custom_tags"], _MAX_CUSTOM_TAGS, _TAG_MAX)
    if "hidden_languages" in body:
        out["hidden_languages"] = _coerce_str_list(
            body["hidden_languages"], _MAX_HIDDEN_LANGS, _LANG_MAX
        )

    if "widget_settings" in body:
        ws = _coerce_widget_settings(body["widget_settings"])
        if ws:
            out["widget_settings"] = ws

    if "achievements" in body:
        raw = body["achievements"] if isinstance(body["achievements"], list) else []
        cleaned = []
        for a in raw[:_MAX_ACHIEVEMENTS]:
            ca = _coerce_achievement(a)
            if ca:
                cleaned.append(ca)
        out["achievements"] = cleaned

    return out


@app.route("/dev")
@auth.require_basic_auth
def dev_index():
    """Gate the dashboard page itself so the browser pops the native
    Basic-Auth prompt before any HTML loads. Without this, the SPA bundle
    serves unauthenticated and the dashboard shell renders before the XHR
    401 lands — defeating the auth wall."""
    index = os.path.join(_STATIC_DIR, "index.html")
    if os.path.isfile(index):
        return send_from_directory(_STATIC_DIR, "index.html")
    return jsonify({"error": "frontend not built"}), 503


@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def spa(path: str):
    # Drop-in shortcut: `/?username=X` (or `/api/?username=X`) force-renders
    # just the developer profile (grade) widget for that user and returns the
    # SVG directly. No SPA, no composite — the single widget that README
    # embeds care about. `/api/<u>` and friends keep working below.
    if path in ("", "api", "api/") and request.args.get("username"):
        t0 = time.monotonic()
        u = request.args.get("username", "")
        resp = _serve_profile_widget(u)
        try:
            status_code = resp[1] if isinstance(resp, tuple) else getattr(resp, "status_code", 200)
            analytics.record_request(
                endpoint="/?username=<u>",
                username=(u or "").lower() if isinstance(u, str) else None,
                widget="grade", status=int(status_code),
                latency_ms=int((time.monotonic() - t0) * 1000),
            )
        except Exception:
            log.exception("analytics record_request failed")
        return resp
    if path.startswith("api/"):
        return jsonify({"error": "not found"}), 404
    if path:
        # send_from_directory enforces that `path` cannot escape _STATIC_DIR.
        try:
            return send_from_directory(_STATIC_DIR, path)
        except Exception:
            pass
    index = os.path.join(_STATIC_DIR, "index.html")
    if os.path.isfile(index):
        return send_from_directory(_STATIC_DIR, "index.html")
    return jsonify({"error": "frontend not built"}), 503


@app.route("/api/auth/me", methods=["GET"])
def auth_me():
    login = auth.current_login()
    if login is None:
        return jsonify({"login": None})
    return jsonify({
        "login": login,
        "avatar_url": session.get("gh_avatar_url"),
    })


@app.route("/api/auth/logout", methods=["POST"])
@auth.require_same_origin
def auth_logout():
    session.clear()
    return ("", 204)


@app.route("/api/auth/github/login", methods=["GET"])
def auth_github_login():
    import secrets as _secrets
    nxt = request.args.get("next", "/")
    # Only accept local relative paths to prevent open-redirect.
    # Reject protocol-relative ("//evil") and backslash ("/\evil") forms,
    # which browsers resolve against the current scheme.
    if (not isinstance(nxt, str)
            or not nxt.startswith("/")
            or nxt.startswith(("//", "/\\"))):
        nxt = "/"
    state = _secrets.token_urlsafe(32)
    session["oauth_state"] = state
    session["oauth_next"] = nxt
    redirect_uri = config.GITHUB_OAUTH_REDIRECT_URI or _derived_redirect_uri()
    return auth.github_client().authorize_redirect(redirect_uri, state=state)


def _derived_redirect_uri() -> str:
    # Works behind cloudflared: the X-Forwarded-Proto/Host headers are set.
    proto = request.headers.get("X-Forwarded-Proto") or request.scheme
    host = request.headers.get("X-Forwarded-Host") or request.host
    return f"{proto}://{host}/api/auth/github/callback"


def _gh_api_get(token: str, path: str) -> dict:
    """Thin wrapper over requests.get so tests can monkeypatch one function."""
    import requests
    r = requests.get(
        f"https://api.github.com/{path.lstrip('/')}",
        headers={"Authorization": f"Bearer {token}",
                 "Accept": "application/vnd.github+json"},
        timeout=config.API_TIMEOUT,
    )
    if r.status_code >= 400:
        raise RuntimeError(f"github {path} {r.status_code}")
    return r.json()


@app.route("/api/auth/github/callback", methods=["GET"])
def auth_github_callback():
    from flask import redirect
    state = request.args.get("state", "")
    expected = session.pop("oauth_state", None)
    nxt = session.pop("oauth_next", "/") or "/"
    if not expected or state != expected:
        return jsonify({"error": "bad_state"}), 400
    try:
        token_resp = auth.github_client().authorize_access_token()
    except Exception:
        log.exception("token exchange failed")
        return redirect("/?auth_error=exchange")
    access_token = token_resp.get("access_token") if token_resp else None
    if not access_token:
        return redirect("/?auth_error=exchange")
    try:
        user = _gh_api_get(access_token, "user")
    except Exception:
        log.exception("github /user failed")
        return redirect("/?auth_error=profile")

    login_raw = user.get("login")
    gh_id = user.get("id")
    avatar_url = user.get("avatar_url") or ""
    if not isinstance(login_raw, str) or not is_valid_username(login_raw) or not isinstance(gh_id, int):
        return redirect("/?auth_error=profile")

    login = login_raw.lower()
    session.permanent = True
    session["gh_login"] = login
    session["gh_id"] = gh_id
    session["gh_avatar_url"] = avatar_url

    # Implicit enrollment. Three converging paths kick off the build, all
    # idempotent — the goal is that no single failure (fetcher unreachable,
    # worker process not running, callback mis-delivered) can strand the
    # signup waiting on cron's 15-min tick.
    #   1) db.enroll() enqueues a 'build' job. Worker container or the
    #      in-process kickoff pool will pop it; if the fetcher has no
    #      data yet, /data auto-fetches synchronously (fast now that the
    #      pipeline is parallelized end-to-end).
    #   2) _request_fetch_async asks the fetcher to start a background
    #      fetch immediately. When it finishes, it calls back to
    #      /internal/data-ready, which is a no-op if a pending build for
    #      this user already exists — it just shortens latency in the
    #      common case.
    #   3) _kickoff_prefetch_async runs process_one() in this process's
    #      thread pool. This is the safety net for deployments that don't
    #      run a separate worker process (gunicorn-only setups).
    defaults = {
        "theme": "dark",
        "enabled": config.ENABLED_WIDGETS,
        "widget_order": config.WIDGET_ORDER,
    }
    db.enroll(login, defaults, github_id=gh_id, github_avatar_url=avatar_url)
    _request_fetch_async(login)
    _kickoff_prefetch_async(login)

    return redirect(nxt)


@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "service": "generator"})


@app.route("/internal/data-ready", methods=["POST"])
def internal_data_ready():
    """Called by the fetcher when a /fetch-async background job finishes.

    Token-protected by the same shared secret used for generator -> fetcher
    calls. The body is `{username, payload_hash, ok}`. If the user is
    enrolled, enqueue a build job; the worker picks it up on its next 0.5s
    tick and the fetcher's data is already cached, so the build runs in
    seconds. If the user is not enrolled here we silently ignore — the
    fetcher might have been kicked off by some other path (cron, manual
    refresh) and we don't want to leak a job for a stranger.
    """
    token = request.headers.get("X-Internal-Token", "")
    if not config.FETCHER_INTERNAL_TOKEN or not hmac.compare_digest(
        token, config.FETCHER_INTERNAL_TOKEN
    ):
        return jsonify({"error": "unauthorized"}), 401
    body = request.get_json(silent=True) or {}
    username = body.get("username")
    if not isinstance(username, str) or not is_valid_username(username):
        return jsonify({"error": "invalid_username"}), 400
    username = username.lower()
    if db.get_settings(username) is None:
        return jsonify({"ignored": True, "reason": "not_enrolled"}), 200
    if not body.get("ok", True):
        # The fetch failed (network / GitHub 5xx). No point queueing a
        # build that would just fail too. The cron loop will retry the
        # fetch on its next tick.
        return jsonify({"ignored": True, "reason": "fetch_failed"}), 200
    # Idempotent: the OAuth callback already enqueues a build directly so
    # the worker can make progress even if this callback never arrives.
    # If a build is already pending/running, don't queue a second one.
    if db.has_open_build(username):
        return jsonify({"ignored": True, "reason": "already_queued"}), 200
    job_id = db.enqueue_build(username)
    log.info("enqueued build %d for %s after fetch completion", job_id, username)
    return jsonify({"queued": True, "job_id": job_id}), 200


@app.route("/internal/analytics/events", methods=["POST"])
def internal_analytics_events():
    token = request.headers.get("X-Internal-Token", "")
    if not config.FETCHER_INTERNAL_TOKEN or not hmac.compare_digest(
        token, config.FETCHER_INTERNAL_TOKEN
    ):
        return jsonify({"error": "unauthorized"}), 401
    body = request.get_json(silent=True) or {}
    events = body.get("events", [])
    if not isinstance(events, list):
        return jsonify({"error": "bad_request"}), 400
    n = analytics.ingest_batch(events)
    return jsonify({"ingested": n})


@app.route("/api/<username>", methods=["GET"])
@track_request("composite")
@rate_limited("read")
def get_widget(username: str):
    if not is_valid_username(username):
        return jsonify({"error": "invalid_username"}), 400
    return _serve(username, widget_name="composite")


@app.route("/api/<username>/<widget>.svg", methods=["GET"])
@track_request(lambda kw: kw.get("widget"))
@rate_limited("read")
def get_widget_named(username: str, widget: str):
    if not is_valid_username(username):
        return jsonify({"error": "invalid_username"}), 400
    if widget not in _ALLOWED_WIDGETS and widget != "composite":
        return jsonify({"error": "unknown_widget"}), 400
    return _serve(username, widget_name=widget)


@app.route("/api/top-langs", methods=["GET"])
@track_request("languages")
@rate_limited("read")
def compat_top_langs():
    """Compatibility shim for upstream anuraghazra/github-readme-stats URLs.

    People copy `/api/top-langs?username=X&...` straight out of READMEs
    that target the upstream Vercel-hosted service and just swap in
    gh-stats.com. Without this route the request would fall through to
    /api/<u> with username='top-langs', which is meaningless here.

    Routing precedence: Flask matches the literal '/api/top-langs' before
    the '/api/<username>' rule, so this can't shadow real users.

    Upstream-only query params (layout, title_color, text_color,
    bg_color, hide_border, langs_count, hide, etc.) are deliberately
    ignored — themeing in this fork is per-user, configured in the
    workshop, not per-URL. The intent is that the embedded image
    *renders something coherent* instead of 'user not found'.
    """
    username = request.args.get("username", "")
    if not isinstance(username, str) or not is_valid_username(username):
        return jsonify({"error": "invalid_username"}), 400
    username = username.lower()
    # Same auto-enroll path as GET /api/<u>/data so a first-time visitor
    # doesn't sit on a placeholder forever. Daily cap is the abuse
    # backstop; without it a botnet hitting random ?username= values
    # could exhaust the GitHub PAT budget.
    if db.get_settings(username) is None:
        if db.enrollments_today() >= config.ENROLLMENT_DAILY_CAP:
            return _placeholder_response("rate_limited", username)
        defaults = {
            "theme": "dark",
            "enabled": config.ENABLED_WIDGETS,
            "widget_order": config.WIDGET_ORDER,
        }
        db.enroll(username, defaults)
        _request_fetch_async(username)
        _kickoff_prefetch_async(username)
    return _serve(username, widget_name="languages")


@app.route("/api/<username>/data", methods=["GET"])
@track_request("data")
@rate_limited("read")
def get_user_data(username: str):
    """Precomputed widget data for client-side SVG rendering.

    Auto-enrolls visitors for users that haven't signed in themselves yet
    (subject to ENROLLMENT_DAILY_CAP, same as the /?username=X shortcut).
    Without this, typing someone else's username into the workshop's
    search bar produced 'not_enrolled' forever — the user only got
    enrolled if they personally went through OAuth, which makes the
    public-preview UX dead-on-arrival.
    """
    if not is_valid_username(username):
        return jsonify({"error": "invalid_username"}), 400
    username = username.lower()
    settings_row = db.get_settings(username)
    if settings_row is None:
        # Daily cap is the abuse backstop: a botnet typing random names
        # can't burn through the GitHub PAT budget past this number.
        if db.enrollments_today() >= config.ENROLLMENT_DAILY_CAP:
            return jsonify({"status": "rate_limited"}), 429
        defaults = {
            "theme": "dark",
            "enabled": config.ENABLED_WIDGETS,
            "widget_order": config.WIDGET_ORDER,
        }
        # Same triple-converging kickoff as the OAuth callback: enqueue
        # the build directly + ask the fetcher to start in the background
        # + run process_one in the API's thread pool. Robust to any one
        # of the three paths failing.
        db.enroll(username, defaults)
        _request_fetch_async(username)
        _kickoff_prefetch_async(username)
        return jsonify({"status": "building"}), 202

    db.touch_last_requested(username)

    row = db.get_current_widget_data(username)
    if row is None:
        return jsonify({"status": "building"}), 202

    if row["settings_hash"] == "not_found":
        return jsonify({"status": "not_found"}), 404

    return jsonify({"status": "ready", "data": row["data"]})


def _serve(username: str, widget_name: str) -> Response:
    """Serves a cached SVG for README embeds.

    Two code paths:
      * No query overrides: return the pre-rendered composite stored in
        widgets.db (cheap, cacheable).
      * Query overrides present: render on-demand with the override dict
        merged onto the owner's stored settings. Nothing is persisted; the
        owner's widget is unaffected. This is how unauthenticated users
        "edit" a widget — they just craft a URL.
    """
    settings_row = db.get_settings(username)
    if settings_row is None:
        return _placeholder_response("building", username)

    db.touch_last_requested(username)
    current_hash = db.get_current_widget_hash(username)
    raw_theme = settings_row["settings"].get("theme", "dark")
    theme = raw_theme if isinstance(raw_theme, str) and raw_theme in THEMES else "dark"

    headers_common = {
        "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; img-src data:",
        "X-Content-Type-Options": "nosniff",
    }

    # Ad-hoc render path. Only triggers for the composite — named widgets
    # keep serving the cached per-widget SVG, which is what edge fetches.
    overrides = sanitize_settings_query(request.args) if widget_name == "composite" else {}
    if overrides and current_hash != "not_found":
        # Honor the possibly-overridden theme for error placeholders.
        override_theme = overrides.get("theme") if isinstance(overrides.get("theme"), str) else None
        effective_theme = override_theme or theme
        acquired = _GENERATE_SEMAPHORE.acquire(timeout=config.GENERATE_SEMAPHORE_WAIT_S)
        if not acquired:
            resp = jsonify({"error": "busy"})
            resp.status_code = 503
            resp.headers["Retry-After"] = "5"
            return resp
        try:
            from . import worker
            svg = worker.render_composite_adhoc(username, overrides)
        except Exception:
            log.exception("adhoc render failed for %s", username)
            svg = None
        finally:
            _GENERATE_SEMAPHORE.release()
        if svg is None:
            return _placeholder_response("building", username, theme=effective_theme)
        # Query-string renders are deterministic from (user, query) but
        # depend on fetcher data that does rotate. Use a short shared cache
        # window so bursty viewers of the same embed don't all hit compute.
        headers = {"X-Widget-Status": "ready",
                   "Cache-Control": "public, max-age=300",
                   **headers_common}
        return Response(svg, mimetype="image/svg+xml", headers=headers)

    if current_hash == "not_found":
        svg = db.get_current_widget(username, widget_name) or placeholder.render("not_found", username, theme=theme)
        headers = {"X-Widget-Status": "not_found", "Cache-Control": "no-store", **headers_common}
        return Response(svg, mimetype="image/svg+xml", headers=headers)

    svg = db.get_current_widget(username, widget_name)
    if svg is None:
        return _placeholder_response("building", username, theme=theme)

    headers = {"X-Widget-Status": "ready",
               "Cache-Control": "public, max-age=3600",
               **headers_common}
    return Response(svg, mimetype="image/svg+xml", headers=headers)


def _placeholder_response(variant: str, username: str, theme: str = "dark") -> Response:
    svg = placeholder.render(variant, username, theme=theme)
    return Response(svg, mimetype="image/svg+xml",
                    headers={"X-Widget-Status": variant, "Cache-Control": "no-store",
                             "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; img-src data:",
                             "X-Content-Type-Options": "nosniff"})


def _serve_profile_widget(username: str) -> Response:
    """Force-generate and return the developer profile (grade) widget SVG.

    Powers the `/?username=X` and `/api/?username=X` shortcuts. Unlike the
    cached `/api/<u>` composite path, this one will auto-enroll a new user
    (subject to the daily cap) so a first-time visitor who pastes a
    username in the URL gets a usable SVG back on the first request.
    Only the grade widget is rendered; no composite, no other widgets.
    """
    if not is_valid_username(username):
        return jsonify({"error": "invalid_username"}), 400
    username = username.lower()
    if not _rate_limit("read"):
        return jsonify({"error": "rate_limited"}), 429

    settings_row = db.get_settings(username)
    if settings_row is None:
        if db.enrollments_today() >= config.ENROLLMENT_DAILY_CAP:
            return _placeholder_response("rate_limited", username)
        defaults = {
            "theme": "dark",
            "enabled": config.ENABLED_WIDGETS,
            "widget_order": config.WIDGET_ORDER,
        }
        db.enroll(username, defaults)
        settings_row = db.get_settings(username)
        if settings_row is None:
            return _placeholder_response("building", username)

    theme_raw = settings_row["settings"].get("theme", "dark")
    theme = theme_raw if isinstance(theme_raw, str) and theme_raw in THEMES else "dark"

    acquired = _GENERATE_SEMAPHORE.acquire(timeout=config.GENERATE_SEMAPHORE_WAIT_S)
    if not acquired:
        resp = jsonify({"error": "busy"})
        resp.status_code = 503
        resp.headers["Retry-After"] = "5"
        return resp
    try:
        result = fetcher_client.get_data(username)
        payload = result.get("data") or {}
        if payload.get("error") == "not_found":
            return _placeholder_response("not_found", username, theme=theme)
        t0 = time.monotonic()
        grade = processor.compute_grade(
            payload,
            custom_tags=settings_row["settings"].get("custom_tags"),
        )
        ws = (settings_row["settings"].get("widget_settings") or {}).get("grade")
        svg = render_grade_widget(grade, theme, settings=ws)
        analytics.record_render(username, "grade",
                                int((time.monotonic() - t0) * 1000))
    except Exception:
        log.exception("profile widget render failed for %s", username)
        return _placeholder_response("building", username, theme=theme)
    finally:
        _GENERATE_SEMAPHORE.release()

    db.touch_last_requested(username)
    return Response(
        svg,
        mimetype="image/svg+xml",
        headers={
            "X-Widget-Status": "ready",
            "Cache-Control": "public, max-age=300",
            "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; img-src data:",
            "X-Content-Type-Options": "nosniff",
        },
    )


@app.route("/api/<username>/settings", methods=["GET"])
@rate_limited("read")
def get_settings(username: str):
    s = db.get_settings(username)
    if s is None:
        return jsonify({"error": "not_enrolled"}), 404
    # Strip internal-only fields before returning.
    return jsonify({
        "settings": s["settings"],
        "settings_hash": s["settings_hash"],
        "manual_refresh_used": s["manual_refresh_used"],
        "enrolled_at": s["enrolled_at"],
    })


@app.route("/api/<username>/settings", methods=["PATCH"])
@rate_limited("mutate")
@auth.require_same_origin
@auth.require_github_owner
def patch_settings(username: str):
    current = db.get_settings(username)
    if current is None:
        return jsonify({"error": "not_enrolled"}), 404
    body = request.get_json(silent=True) or {}
    clean = sanitize_settings(body)
    merged = {**current["settings"], **clean}
    # Defense in depth: reject after-the-fact if the merged blob is pathological.
    if not settings_size_ok(_json.dumps(merged)):
        return jsonify({"error": "settings_too_large"}), 413
    job_id = db.update_settings(username, merged)
    _kickoff_prefetch_async(username)
    return jsonify({"updated": True, "job_id": job_id})


@app.route("/api/<username>/generate", methods=["POST"])
@rate_limited("mutate")
@auth.require_same_origin
@auth.require_github_owner
def generate(username: str):
    """Render the composite SVG from the cached fetcher payload + current
    settings, persist it to widgets.db, and return status. Called by the
    Generate button; safe to call repeatedly (each call re-renders with
    the latest settings). Requires OAuth session with matching login.

    Capacity:
      * Per-IP rate limit (mutate bucket) caps how fast any one caller can
        trigger renders.
      * Global semaphore caps how many renders run in parallel across all
        callers — the mini PC backstop. Callers that can't acquire the
        slot within GENERATE_SEMAPHORE_WAIT_S get 503 + Retry-After so the
        frontend can back off cleanly.
    """
    from . import worker
    if not is_valid_username(username):
        return jsonify({"error": "invalid_username"}), 400
    if db.get_settings(username) is None:
        return jsonify({"error": "not_enrolled"}), 404

    acquired = _GENERATE_SEMAPHORE.acquire(timeout=config.GENERATE_SEMAPHORE_WAIT_S)
    if not acquired:
        resp = jsonify({"error": "busy"})
        resp.status_code = 503
        resp.headers["Retry-After"] = "5"
        return resp
    try:
        widgets = worker.render_widgets_now(username)
    except LookupError:
        return jsonify({"error": "not_enrolled"}), 404
    except Exception:
        log.exception("generate failed for %s", username)
        return jsonify({"error": "render_failed"}), 502
    finally:
        _GENERATE_SEMAPHORE.release()

    current_hash = db.get_current_widget_hash(username)
    if current_hash == "not_found":
        return jsonify({"status": "not_found"}), 404
    return jsonify({
        "status": "ready",
        "composite_url": f"/api/{username}",
        "widgets": list(widgets.keys()),
    })


@app.route("/api/<username>/refresh", methods=["POST"])
@rate_limited("mutate")
@auth.require_same_origin
@auth.require_github_owner
def refresh(username: str):
    s = db.get_settings(username)
    if s is None:
        return jsonify({"error": "not_enrolled"}), 404
    if not db.mark_manual_refresh(username):
        return jsonify({"error": "already_used"}), 409
    try:
        fetcher_client.force_fetch(username)
    except Exception:
        log.exception("refresh fetcher call failed for %s", username)
        return jsonify({"error": "fetch_failed"}), 502
    job_id = db.enqueue_build(username)
    _kickoff_prefetch_async(username)
    return jsonify({"refreshed": True, "job_id": job_id})


@app.route("/api/dev/summary", methods=["GET"])
@auth.require_basic_auth
def dev_summary():
    return jsonify(analytics.query_summary())


@app.route("/api/dev/users", methods=["GET"])
@auth.require_basic_auth
def dev_users():
    q = request.args.get("q", "")
    sort = request.args.get("sort", "requests")
    return jsonify(analytics.query_users(q=q, sort=sort))


@app.route("/api/dev/latency", methods=["GET"])
@auth.require_basic_auth
def dev_latency():
    return jsonify(analytics.query_latency())


@app.route("/api/dev/health", methods=["GET"])
@auth.require_basic_auth
def dev_health():
    return jsonify(analytics.query_health())


@app.errorhandler(413)
def _too_large(_e):
    return jsonify({"error": "payload_too_large"}), 413


def _invalidate_widgets_on_new_build() -> None:
    """On boot, if BUILD_VERSION differs from the last stamp, queue a
    rebuild for every enrolled user so widgets re-render against the new
    code. Races safely with the worker/cron containers: the first caller
    to flip the meta row enqueues; the rest observe a no-op.
    """
    if not config.BUILD_VERSION:
        return
    try:
        if db.claim_build_version(config.BUILD_VERSION):
            n = db.enqueue_build_all()
            log.info("build %s: queued %d rebuild(s)", config.BUILD_VERSION, n)
    except Exception:
        # Never let a failed invalidation prevent the API from booting —
        # the next boot (or a manual refresh) will pick up the change.
        log.exception("build-version invalidation failed")


def main():
    db.init_dbs()
    _invalidate_widgets_on_new_build()
    analytics.start_flush_thread()
    app.run(host="0.0.0.0", port=config.PORT)


def _boot_analytics_for_gunicorn():
    """Gunicorn imports the module without calling main(); fire the daemon
    flush thread here so render timings actually get flushed in production.
    Idempotent — start_flush_thread checks for a running thread."""
    try:
        analytics.start_flush_thread()
    except Exception:
        log.exception("analytics boot failed")

_boot_analytics_for_gunicorn()

if __name__ == "__main__":
    main()
