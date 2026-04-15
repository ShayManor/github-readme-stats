"""Flask API for the fetcher service.

Pulls data from the GitHub API and writes it to the shared SQLite database.
Does not render anything. Runs independently from the generator.

    python -m src.fetcher_api          # serves on :5001

Endpoints:
    GET  /health
    POST /fetch            {username, token?}   -> fetches + upserts
    GET  /users            -> list stored usernames
    GET  /users/<username> -> full stored payload
"""

import os
from flask import Flask, jsonify, request

from .data.fetcher import fetch_github_data
from .db import init_db, upsert_user, get_user, list_users, DUMMY_USERNAME


app = Flask(__name__)


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "service": "fetcher"})


@app.route("/fetch", methods=["POST"])
def fetch():
    body = request.get_json(silent=True) or {}
    username = body.get("username")
    if not username:
        return jsonify({"error": "username is required"}), 400
    if username == DUMMY_USERNAME:
        return jsonify({"error": "cannot overwrite dummy user"}), 400

    token = body.get("token") or os.environ.get("GITHUB_PAT")

    try:
        data = fetch_github_data(username, token)
    except Exception as e:
        return jsonify({"error": f"fetch failed: {e}"}), 502

    if not data.get("user") or data["user"].get("message") == "Not Found":
        return jsonify({"error": f"github user '{username}' not found"}), 404

    upsert_user(username, data)
    return jsonify({
        "username": username,
        "stored": True,
        "total_commits": data.get("total_commits", 0),
        "repos": len(data.get("repos", [])),
    })


@app.route("/users", methods=["GET"])
def users_list():
    return jsonify(list_users())


@app.route("/users/<username>", methods=["GET"])
def users_get(username: str):
    data = get_user(username)
    if data is None:
        return jsonify({"error": "not found"}), 404
    return jsonify(data)


def main():
    init_db()
    port = int(os.environ.get("FETCHER_PORT", "5001"))
    app.run(host="0.0.0.0", port=port, debug=False)


if __name__ == "__main__":
    main()
