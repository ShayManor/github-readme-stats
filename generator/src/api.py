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
from functools import wraps
from threading import Thread
from flask import Flask, jsonify, request, Response, send_from_directory

from . import config, db, fetcher_client, placeholder

log = logging.getLogger("generator.api")


def _kickoff_prefetch(username: str):
    """Run one prefetch cycle in a background thread. Starts the fetcher
    immediately on enrollment / settings-change so the raw GitHub payload
    is hot by the time the user clicks Generate."""
    log.info("prefetch kickoff started for %s", username)
    try:
        from . import worker
        worker.process_one()
        log.info("prefetch kickoff finished for %s", username)
    except Exception:
        log.exception("prefetch kickoff failed for %s", username)


def _kickoff_prefetch_async(username: str):
    Thread(target=_kickoff_prefetch, args=(username,), daemon=True).start()

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
    if path:
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
def get_widget(username: str):
    return _serve(username, widget_name="composite")


@app.route("/api/<username>/<widget>.svg", methods=["GET"])
def get_widget_named(username: str, widget: str):
    return _serve(username, widget_name=widget)


@app.route("/api/<username>/data", methods=["GET"])
def get_user_data(username: str):
    """Precomputed widget data for client-side SVG rendering.

    Pure DB lookup — never touches the fetcher or runs compute on the hot
    path. On miss: auto-enroll (queues an async build) and return
    `{status: "building"}` with HTTP 202 so the client can show demo data
    and poll until ready.
    """
    settings_row = db.get_settings(username)
    if settings_row is None:
        if db.enrollments_today() >= config.ENROLLMENT_DAILY_CAP:
            return jsonify({"status": "rate_limited"}), 429
        defaults = {
            "theme": "dark",
            "enabled": config.ENABLED_WIDGETS,
            "widget_order": config.WIDGET_ORDER,
        }
        db.enroll(username, defaults)
        _kickoff_prefetch_async(username)
        return jsonify({"status": "building"}), 202

    db.touch_last_requested(username)

    row = db.get_current_widget_data(username)
    if row is None:
        return jsonify({"status": "building"}), 202

    # Worker writes settings_hash="not_found" + data={"not_found": True}
    # when GitHub returns 404 for this username.
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
    theme = settings_row["settings"].get("theme", "dark")

    if current_hash == "not_found":
        svg = db.get_current_widget(username, widget_name) or placeholder.render("not_found", username, theme=theme)
        return Response(svg, mimetype="image/svg+xml",
                        headers={"X-Widget-Status": "not_found", "Cache-Control": "no-store"})

    svg = db.get_current_widget(username, widget_name)
    if svg is None:
        return _placeholder_response("building", username, theme=theme)

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
    _kickoff_prefetch_async(username)
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
    current = db.get_settings(username)
    if current is None:
        return jsonify({"error": "not_enrolled"}), 404
    body = request.get_json(silent=True) or {}
    merged = {**current["settings"], **body}
    job_id = db.update_settings(username, merged)
    _kickoff_prefetch_async(username)
    return jsonify({"updated": True, "job_id": job_id})


@app.route("/api/<username>/generate", methods=["POST"])
def generate(username: str):
    """Render the composite SVG from the cached fetcher payload + current
    settings, persist it to widgets.db, and return status. Called by the
    Generate button; safe to call repeatedly (each call re-renders with
    the latest settings)."""
    from . import worker
    if db.get_settings(username) is None:
        return jsonify({"error": "not_enrolled"}), 404
    try:
        widgets = worker.render_widgets_now(username)
    except LookupError:
        return jsonify({"error": "not_enrolled"}), 404
    except Exception as e:
        log.exception("generate failed for %s", username)
        return jsonify({"error": f"render_failed: {e}"}), 502
    current_hash = db.get_current_widget_hash(username)
    if current_hash == "not_found":
        return jsonify({"status": "not_found"}), 404
    return jsonify({
        "status": "ready",
        "composite_url": f"/api/{username}",
        "widgets": list(widgets.keys()),
    })


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
    _kickoff_prefetch_async(username)
    return jsonify({"refreshed": True, "job_id": job_id})


def main():
    db.init_dbs()
    app.run(host="0.0.0.0", port=config.PORT)


if __name__ == "__main__":
    main()
