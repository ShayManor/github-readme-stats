"""Edge service — cache-first SVG proxy in front of the generator."""
import logging
import re
import time
from collections import defaultdict, deque
from threading import Lock
import requests
from flask import Flask, Response, jsonify, request
from flask_compress import Compress

from . import cache as cache_mod, config

app = Flask(__name__)
Compress(app)
cache_ext = cache_mod.build_cache(app)
log = logging.getLogger("edge")

# GitHub usernames: 1-39 chars, alnum, single hyphens. Keep the regex in
# sync with generator/src/utils/validate.py so invalid paths get rejected
# before they waste an upstream round-trip.
_USERNAME_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9]|-(?=[A-Za-z0-9])){0,38}$")
_ALLOWED_WIDGETS = {"grade", "impact", "collaborators", "focus", "languages", "achievements", "composite"}


def _valid_username(u: str) -> bool:
    return bool(u) and bool(_USERNAME_RE.match(u))


# ---- Per-IP rate limiter ---------------------------------------------------
# The edge is the mini PC's front door. Cache hits are cheap, but a hostile
# cache-miss storm (unique usernames, unique widget names) would funnel into
# the generator's render path. Bound it here so the generator's own limiter
# isn't the only layer. Operators who run behind a CDN / nginx should prefer
# the upstream limiter and raise these env vars.
_rate_lock = Lock()
_rate_hits: dict[str, deque] = defaultdict(deque)


def _client_ip() -> str:
    fwd = request.headers.get("X-Forwarded-For", "")
    if fwd:
        return fwd.split(",")[-1].strip()
    return request.remote_addr or "unknown"


def _allow(ip: str) -> bool:
    now = time.time()
    cutoff = now - config.RATE_LIMIT_WINDOW
    with _rate_lock:
        q = _rate_hits[ip]
        while q and q[0] < cutoff:
            q.popleft()
        if len(q) >= config.RATE_LIMIT_MAX:
            return False
        q.append(now)
    return True


def _cache_key(path: str) -> str:
    return f"edge:{path}"


def _fetch_origin(path: str, client_ip: str) -> requests.Response:
    url = f"{config.GENERATOR_URL}/api/{path}"
    # Forward the caller's IP so the generator's rate limiter can
    # discriminate per user rather than treating the edge's single IP as
    # one client — otherwise the first 300 requests/min exhaust the bucket
    # for everyone behind the edge.
    headers = {"X-Forwarded-For": client_ip}
    return requests.get(url, headers=headers, timeout=config.UPSTREAM_TIMEOUT)


@app.route("/health", methods=["GET"])
def health():
    ok = True
    try:
        r = requests.get(f"{config.GENERATOR_URL}/api/health", timeout=config.UPSTREAM_TIMEOUT)
        ok = r.status_code == 200
    except Exception:
        ok = False
    return jsonify({"service": "edge", "cache_type": config.CACHE_TYPE, "upstream_ok": ok})


@app.route("/<username>", methods=["GET"])
def serve(username: str):
    if not _valid_username(username):
        return jsonify({"error": "invalid_username"}), 400
    return _serve(username, path=username)


@app.route("/<username>/<widget>.svg", methods=["GET"])
def serve_widget(username: str, widget: str):
    if not _valid_username(username):
        return jsonify({"error": "invalid_username"}), 400
    if widget not in _ALLOWED_WIDGETS:
        return jsonify({"error": "unknown_widget"}), 400
    return _serve(f"{username}/{widget}", path=f"{username}/{widget}.svg")


def _serve(key_suffix: str, path: str) -> Response:
    ip = _client_ip()
    if not _allow(ip):
        return jsonify({"error": "rate_limited"}), 429

    ck = _cache_key(key_suffix)
    cached = cache_ext.get(ck)
    if cached is not None:
        body, content_type = cached
        return Response(body, mimetype=content_type, headers={
            "X-Widget-Status": "ready",
            "X-Cache": "HIT",
            "Cache-Control": "public, max-age=3600, s-maxage=86400, stale-while-revalidate=86400",
        })

    try:
        r = _fetch_origin(path, ip)
    except Exception as e:
        log.warning("origin unreachable for %s: %s", path, e)
        return jsonify({"error": "origin unreachable"}), 503

    if r.status_code >= 500:
        return jsonify({"error": "origin error"}), 503

    status = r.headers.get("X-Widget-Status", "ready")
    content_type = r.headers.get("Content-Type", "image/svg+xml")
    if status == "ready" and r.status_code == 200:
        cache_ext.set(ck, (r.content, content_type), timeout=config.CACHE_DEFAULT_TIMEOUT)
        cc = "public, max-age=3600, s-maxage=86400, stale-while-revalidate=86400"
    else:
        cc = "no-store"

    return Response(r.content, status=r.status_code, mimetype=content_type, headers={
        "X-Widget-Status": status,
        "X-Cache": "MISS",
        "Cache-Control": cc,
    })


def main():
    app.run(host="0.0.0.0", port=config.PORT)


if __name__ == "__main__":
    main()
