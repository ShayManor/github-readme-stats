"""Edge service — cache-first SVG proxy in front of the generator."""
import logging
import requests
from flask import Flask, Response, jsonify
from flask_compress import Compress

from . import cache as cache_mod, config

app = Flask(__name__)
Compress(app)
cache_ext = cache_mod.build_cache(app)
log = logging.getLogger("edge")


def _cache_key(path: str) -> str:
    return f"edge:{path}"


def _fetch_origin(path: str) -> requests.Response:
    url = f"{config.GENERATOR_URL}/api/{path}"
    return requests.get(url, timeout=config.UPSTREAM_TIMEOUT)


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
    return _serve(username, path=username)


@app.route("/<username>/<widget>.svg", methods=["GET"])
def serve_widget(username: str, widget: str):
    return _serve(f"{username}/{widget}", path=f"{username}/{widget}.svg")


def _serve(key_suffix: str, path: str) -> Response:
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
        r = _fetch_origin(path)
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
