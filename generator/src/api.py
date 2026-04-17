"""Flask app for the generator service.

Serves:
  /               -> React SPA (static/index.html)
  /assets/<p>     -> SPA bundles
  /api/*          -> JSON/SVG API
"""
import os
from functools import wraps
from flask import Flask, jsonify, request, Response, send_from_directory

from . import config, db, fetcher_client, placeholder

_STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")

app = Flask(__name__, static_folder=None)


def require_auth(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        return fn(*args, **kwargs)
    return wrapper


@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def spa(path: str):
    if path.startswith("api/"):
        return jsonify({"error": "not found"}), 404
    full = os.path.join(_STATIC_DIR, path) if path else os.path.join(_STATIC_DIR, "index.html")
    if path and os.path.isfile(full):
        return send_from_directory(_STATIC_DIR, path)
    index = os.path.join(_STATIC_DIR, "index.html")
    if os.path.isfile(index):
        return send_from_directory(_STATIC_DIR, "index.html")
    return jsonify({"error": "frontend not built"}), 503


@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "service": "generator"})


@app.route("/api/<username>", methods=["GET"])
def get_widget(username: str):
    return _serve(username, widget_name="composite")


@app.route("/api/<username>/<widget>.svg", methods=["GET"])
def get_widget_named(username: str, widget: str):
    return _serve(username, widget_name=widget)


def _serve(username: str, widget_name: str) -> Response:
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
        return _placeholder_response("building", username)

    db.touch_last_requested(username)
    svg = db.get_current_widget(username, widget_name)
    if svg is None:
        return _placeholder_response("building", username, theme=settings_row["settings"].get("theme", "dark"))

    if settings_row.get("settings_hash") == "not_found":
        return Response(svg, mimetype="image/svg+xml",
                        headers={"X-Widget-Status": "not_found", "Cache-Control": "no-store"})

    return Response(svg, mimetype="image/svg+xml",
                    headers={"X-Widget-Status": "ready",
                             "Cache-Control": "public, max-age=3600"})


def _placeholder_response(variant: str, username: str, theme: str = "dark") -> Response:
    svg = placeholder.render(variant, username, theme=theme)
    return Response(svg, mimetype="image/svg+xml",
                    headers={"X-Widget-Status": variant, "Cache-Control": "no-store"})


@app.route("/api/enroll", methods=["POST"])
def enroll_endpoint():
    body = request.get_json(silent=True) or {}
    username = body.get("username")
    if not username:
        return jsonify({"error": "username required"}), 400
    if db.get_settings(username) is not None:
        return jsonify({"error": "already_enrolled"}), 409
    if db.enrollments_today() >= config.ENROLLMENT_DAILY_CAP:
        return jsonify({"error": "rate_limited"}), 429
    defaults = {"theme": "dark", "enabled": config.ENABLED_WIDGETS, "widget_order": config.WIDGET_ORDER}
    job_id = db.enroll(username, defaults)
    return jsonify({"enrolled": True, "job_id": job_id})


@app.route("/api/<username>/settings", methods=["GET"])
@require_auth
def get_settings(username: str):
    s = db.get_settings(username)
    if s is None:
        return jsonify({"error": "not_enrolled"}), 404
    return jsonify(s)


@app.route("/api/<username>/settings", methods=["PATCH"])
@require_auth
def patch_settings(username: str):
    if db.get_settings(username) is None:
        return jsonify({"error": "not_enrolled"}), 404
    body = request.get_json(silent=True) or {}
    merged = {**db.get_settings(username)["settings"], **body}
    job_id = db.update_settings(username, merged)
    return jsonify({"updated": True, "job_id": job_id})


@app.route("/api/<username>/refresh", methods=["POST"])
@require_auth
def refresh(username: str):
    s = db.get_settings(username)
    if s is None:
        return jsonify({"error": "not_enrolled"}), 404
    if not db.mark_manual_refresh(username):
        return jsonify({"error": "already_used"}), 409
    try:
        fetcher_client.force_fetch(username)
    except Exception as e:
        return jsonify({"error": f"fetch failed: {e}"}), 502
    job_id = db.enqueue_build(username)
    return jsonify({"refreshed": True, "job_id": job_id})


def main():
    db.init_dbs()
    app.run(host="0.0.0.0", port=config.PORT)


if __name__ == "__main__":
    main()
