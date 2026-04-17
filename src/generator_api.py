"""Flask API for the generator service.

Reads previously-fetched data from the shared SQLite database and renders
SVG widgets. Never calls the fetcher — if the requested user is missing or
has incomplete data, it falls back to the __dummy__ user seeded in the DB.

    python -m src.generator_api        # serves on :5002

Endpoints:
    GET  /health
    POST /generate   {username, theme?, widgets?, widget_order?,
                      custom_tags?, hidden_languages?, format?}
                     -> SVG string (format=svg, default) or
                        JSON {widgets: {...}, composite, used_dummy}
"""

import os
from flask import Flask, jsonify, request, Response

from .db import init_db, get_user, DUMMY_USERNAME, REQUIRED_FIELDS
from .data.processor import generate_widgets_from_github
from .models import AchievementData
from .widgets import compose_widget, render_achievements_widget
from .config import ENABLED_WIDGETS, WIDGET_ORDER


app = Flask(__name__)


def _load_with_fallback(username: str) -> tuple[dict, bool]:
    """Return (github_data, used_dummy).

    If the row is missing or is missing any REQUIRED_FIELDS, swap in the dummy
    payload wholesale (no partial merging).
    """
    data = get_user(username)
    if data is None or any(f not in data for f in REQUIRED_FIELDS):
        dummy = get_user(DUMMY_USERNAME)
        if dummy is None:
            raise RuntimeError("dummy user missing from database; run init_db")
        return dummy, True
    return data, False


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "service": "generator"})


@app.route("/generate", methods=["POST"])
def generate():
    body = request.get_json(silent=True) or {}
    username = body.get("username")
    if not username:
        return jsonify({"error": "username is required"}), 400

    theme = body.get("theme", "dark")
    enabled = body.get("widgets") or ENABLED_WIDGETS
    widget_order = body.get("widget_order") or WIDGET_ORDER
    custom_tags = body.get("custom_tags")
    hidden_languages = body.get("hidden_languages")
    achievements_raw = body.get("achievements") or []
    widget_settings = body.get("widget_settings") or {}
    fmt = body.get("format", "svg")

    github_data, used_dummy = _load_with_fallback(username)

    widgets = generate_widgets_from_github(
        github_data,
        theme=theme,
        custom_tags=custom_tags,
        hidden_languages=hidden_languages,
        enabled=enabled,
        widget_settings=widget_settings,
    )

    # Render achievements if provided and enabled
    if "achievements" in enabled and achievements_raw:
        achs = [
            AchievementData(
                title=a.get("title", ""),
                subtitle=a.get("subtitle", ""),
                event_date=a.get("event_date", ""),
                icon=a.get("icon", "trophy"),
            )
            for a in achievements_raw
            if a.get("title")
        ]
        if achs:
            widgets["achievements"] = render_achievements_widget(achs, theme, settings=widget_settings.get("achievements"))

    ordered = [w for w in widget_order if w in enabled and w in widgets and widgets[w]]
    display_name = username if not used_dummy else username
    composite = compose_widget(
        widgets=widgets,
        enabled=ordered,
        theme_name=theme,
        username=display_name,
        avatar_b64=github_data.get("avatar_b64", ""),
    )

    if fmt == "json":
        return jsonify({
            "username": username,
            "used_dummy": used_dummy,
            "widgets": widgets,
            "composite": composite,
        })

    headers = {"X-Used-Dummy": "1" if used_dummy else "0"}
    return Response(composite, mimetype="image/svg+xml", headers=headers)


def main():
    init_db()
    port = int(os.environ.get("GENERATOR_PORT", "5002"))
    app.run(host="0.0.0.0", port=port, debug=False)


if __name__ == "__main__":
    main()
