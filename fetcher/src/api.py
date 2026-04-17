"""Flask app for the fetcher service. All endpoints require X-Internal-Token."""
import hmac
import requests
from flask import Flask, jsonify, request, Response
from functools import wraps

from . import config, db, github

app = Flask(__name__)


def require_internal_token(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        token = request.headers.get("X-Internal-Token", "")
        if not config.INTERNAL_TOKEN or not hmac.compare_digest(token, config.INTERNAL_TOKEN):
            return jsonify({"error": "unauthorized"}), 401
        return fn(*args, **kwargs)
    return wrapper


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "service": "fetcher", "users": len(db.list_usernames())})


@app.route("/data/<username>", methods=["GET"])
@require_internal_token
def get_data(username: str):
    row = db.get_user(username)
    if row is None:
        # Auto-fetch path
        data = github.fetch_github_data(username, token=config.GITHUB_PAT)
        if _is_github_not_found(data):
            data = {"error": "not_found"}
        h = db.upsert_user(username, data)
        return jsonify({"data": data, "payload_hash": h, "fetched": True})
    return jsonify({
        "data": row["data"],
        "payload_hash": row["payload_hash"],
        "fetched_at": row["fetched_at"],
        "fetched": False,
    })


@app.route("/fetch", methods=["POST"])
@require_internal_token
def force_fetch():
    body = request.get_json(silent=True) or {}
    username = body.get("username")
    if not username:
        return jsonify({"error": "username required"}), 400
    try:
        data = github.fetch_github_data(username, token=config.GITHUB_PAT)
    except Exception as e:
        return jsonify({"error": f"fetch failed: {e}"}), 502
    if _is_github_not_found(data):
        data = {"error": "not_found"}
    old = db.get_user(username)
    old_hash = old["payload_hash"] if old else None
    new_hash = db.upsert_user(username, data)
    return jsonify({"stored": True, "payload_hash": new_hash, "changed": old_hash != new_hash})


@app.route("/avatar/<username>", methods=["GET"])
@require_internal_token
def avatar(username: str):
    r = requests.get(f"https://github.com/{username}.png", timeout=config.API_TIMEOUT, allow_redirects=True)
    if r.status_code != 200:
        return jsonify({"error": "avatar unavailable"}), 404
    return Response(r.content, mimetype=r.headers.get("Content-Type", "image/png"))


def _is_github_not_found(data: dict) -> bool:
    user = data.get("user")
    if user is None:
        return True
    if isinstance(user, dict) and user.get("message") == "Not Found":
        return True
    return False


def main():
    db.init_db()
    app.run(host="0.0.0.0", port=config.PORT)


if __name__ == "__main__":
    main()
