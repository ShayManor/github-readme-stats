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
import logging
import os
import time
from collections import defaultdict, deque
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from functools import wraps
from threading import BoundedSemaphore, Lock
from flask import Flask, jsonify, request, Response, send_from_directory

from . import auth, config, db, fetcher_client, placeholder
from .themes import THEMES
from .utils import is_valid_username, settings_size_ok
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


# ---- Per-IP rate limiter -----------------------------------------------------
# In-process sliding-window limiter. Good enough for v1; behind a reverse proxy
# we read X-Forwarded-For (trusting only the last hop set by the proxy). For a
# multi-node deploy, swap this for a Redis-backed limiter.

_RATE_LIMITS = {
    # (endpoint_key): (max_hits, window_seconds). Defaults set in config.py
    # lean toward the mini PC — tighten further via env without redeploying.
    "mutate": (config.RATE_LIMIT_MUTATE_MAX, config.RATE_LIMIT_MUTATE_WINDOW),
    "enroll": (config.RATE_LIMIT_ENROLL_MAX, config.RATE_LIMIT_ENROLL_WINDOW),
    "read":   (config.RATE_LIMIT_READ_MAX,   config.RATE_LIMIT_READ_WINDOW),
}
_rate_lock = Lock()
_rate_hits: dict[tuple[str, str], deque] = defaultdict(deque)


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


def rate_limited(bucket: str):
    def deco(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if not _rate_limit(bucket):
                return jsonify({"error": "rate_limited"}), 429
            return fn(*args, **kwargs)
        return wrapper
    return deco


def _extract_bearer() -> str:
    """Read the caller-presented edit token. Accepts either
    `Authorization: Bearer <t>` or `X-Edit-Token: <t>`."""
    hdr = request.headers.get("Authorization", "")
    if hdr.startswith("Bearer "):
        return hdr[len("Bearer "):].strip()
    return request.headers.get("X-Edit-Token", "").strip()


def require_edit_token(fn):
    """Enforce per-user bearer token on mutating endpoints.

    The token is issued once at enrollment (see db.enroll) and hashed at rest.
    Without it, anyone could overwrite any registrant's settings — these
    endpoints used to live behind a no-op decorator."""
    @wraps(fn)
    def wrapper(username: str, *args, **kwargs):
        if not is_valid_username(username):
            return jsonify({"error": "invalid_username"}), 400
        presented = _extract_bearer()
        if not presented or not db.verify_edit_token(username, presented):
            return jsonify({"error": "unauthorized"}), 401
        return fn(username, *args, **kwargs)
    return wrapper


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

_ALLOWED_WIDGETS = {"grade", "impact", "collaborators", "focus", "languages", "achievements"}
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
            elif kind == "color":
                # Deep color validation happens in the widget renderer
                # (safe_color). Here we only reject obviously wrong types
                # and length-bomb strings.
                if isinstance(val, str) and len(val) <= 32:
                    clean[key] = val
        if clean:
            out[widget] = clean
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


def require_auth(fn):
    """Deprecated passthrough retained for back-compat. New code should use
    require_edit_token above, which actually authenticates."""
    return fn


@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def spa(path: str):
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


@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "service": "generator"})


@app.route("/api/<username>", methods=["GET"])
@rate_limited("read")
def get_widget(username: str):
    if not is_valid_username(username):
        return jsonify({"error": "invalid_username"}), 400
    return _serve(username, widget_name="composite")


@app.route("/api/<username>/<widget>.svg", methods=["GET"])
@rate_limited("read")
def get_widget_named(username: str, widget: str):
    if not is_valid_username(username):
        return jsonify({"error": "invalid_username"}), 400
    if widget not in _ALLOWED_WIDGETS and widget != "composite":
        return jsonify({"error": "unknown_widget"}), 400
    return _serve(username, widget_name=widget)


@app.route("/api/<username>/data", methods=["GET"])
@rate_limited("read")
def get_user_data(username: str):
    """Precomputed widget data for client-side SVG rendering.

    Pure DB lookup — never touches the fetcher or runs compute on the hot
    path. On miss: auto-enroll (queues an async build) and return
    `{status: "building"}` with HTTP 202 so the client can show demo data
    and poll until ready.
    """
    if not is_valid_username(username):
        return jsonify({"error": "invalid_username"}), 400
    settings_row = db.get_settings(username)
    if settings_row is None:
        if not _rate_limit("enroll"):
            return jsonify({"status": "rate_limited"}), 429
        if db.enrollments_today() >= config.ENROLLMENT_DAILY_CAP:
            return jsonify({"status": "rate_limited"}), 429
        # Queue-depth backpressure: if the worker is already behind, stop
        # accepting new enrollments until it catches up. Prevents a burst
        # of auto-enrolls from filling the jobs table faster than a mini
        # PC can drain it.
        if db.pending_job_count() >= config.PENDING_JOB_QUEUE_CAP:
            return jsonify({"status": "rate_limited"}), 429
        defaults = {
            "theme": "dark",
            "enabled": config.ENABLED_WIDGETS,
            "widget_order": config.WIDGET_ORDER,
        }
        result = db.enroll(username, defaults)
        _kickoff_prefetch_async(username)
        # Token is surfaced on this auto-enroll path so the browser UI can
        # edit the freshly-created profile without a separate claim step.
        resp = {"status": "building"}
        if result.get("edit_token"):
            resp["edit_token"] = result["edit_token"]
        return jsonify(resp), 202

    db.touch_last_requested(username)

    row = db.get_current_widget_data(username)
    if row is None:
        return jsonify({"status": "building"}), 202

    if row["settings_hash"] == "not_found":
        return jsonify({"status": "not_found"}), 404

    return jsonify({"status": "ready", "data": row["data"]})


def _serve(username: str, widget_name: str) -> Response:
    """Serves a cached SVG for README embeds.

    SVGs are only produced by POST /api/<u>/generate. Before that the
    endpoint returns a "building" placeholder; enrollment is frontend-
    driven (via /api/<u>/data or /api/enroll) so this path never auto-
    enrolls on its own.
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


@app.route("/api/enroll", methods=["POST"])
@rate_limited("enroll")
def enroll_endpoint():
    body = request.get_json(silent=True) or {}
    username = body.get("username")
    if not is_valid_username(username):
        return jsonify({"error": "invalid_username"}), 400
    if db.get_settings(username) is not None:
        return jsonify({"error": "already_enrolled"}), 409
    if db.enrollments_today() >= config.ENROLLMENT_DAILY_CAP:
        return jsonify({"error": "rate_limited"}), 429
    if db.pending_job_count() >= config.PENDING_JOB_QUEUE_CAP:
        return jsonify({"error": "rate_limited"}), 429
    defaults = {"theme": "dark", "enabled": config.ENABLED_WIDGETS, "widget_order": config.WIDGET_ORDER}
    result = db.enroll(username, defaults)
    _kickoff_prefetch_async(username)
    body = {"enrolled": True, "job_id": result["job_id"]}
    if result.get("edit_token"):
        body["edit_token"] = result["edit_token"]
    return jsonify(body)


@app.route("/api/<username>/settings", methods=["GET"])
@rate_limited("read")
@require_edit_token
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
@require_edit_token
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
def generate(username: str):
    """Render the composite SVG from the cached fetcher payload + current
    settings, persist it to widgets.db, and return status. Called by the
    Generate button; safe to call repeatedly (each call re-renders with
    the latest settings). Unauth'd — anyone can trigger a render of a
    previously-enrolled user's public widget.

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
@require_edit_token
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


@app.errorhandler(413)
def _too_large(_e):
    return jsonify({"error": "payload_too_large"}), 413


def main():
    db.init_dbs()
    app.run(host="0.0.0.0", port=config.PORT)


if __name__ == "__main__":
    main()
