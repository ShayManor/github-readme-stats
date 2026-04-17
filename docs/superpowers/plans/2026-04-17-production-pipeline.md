# Production Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Commit approval:** Global user rule forbids `git commit` / `git push` without explicit approval. The commit step in each task must ask the user for approval before running. Do not amend prior commits; always create new ones. Never `git push` unless the user explicitly asks.

**Goal:** Split the existing monolithic widget-generator repo into three independent Python services (`fetcher`, `generator`, `edge`) plus a React/Vite frontend folded into `generator/frontend`, each with its own Dockerfile, tests, and README. End state: a public `GET /<username>` on the edge returns a precomputed SVG (or a clean placeholder) for any GitHub user, with a background pipeline that enrolls, fetches, builds, and refreshes.

**Architecture:** Three Flask services communicating over HTTP. Fetcher owns the GitHub PAT and `fetcher.db`. Generator owns settings + widgets DBs, runs a build worker + cron, and serves both the React SPA (at `/`) and JSON/SVG APIs (at `/api/*`). Edge is a thin Flask-Caching / Flask-Compress proxy that serves widget SVGs cache-first with the generator as origin. Redis is designed for but not deployed — `cache.py` is a no-op wrapper in v1.

**Tech Stack:** Python 3.11, Flask, SQLite (WAL mode), Flask-Caching (SimpleCache in v1), Flask-Compress, `requests`, `pytest`, `responses` (HTTP mocking), React + Vite + TypeScript (existing), Docker (multi-stage for generator).

**Spec:** `docs/superpowers/specs/2026-04-17-production-pipeline-design.md`

---

## Phases

- **Phase 0** — Scaffolding + removal of retired code
- **Phase 1** — Fetcher service (full)
- **Phase 2** — Generator: DB, cache wrapper, placeholder, processor, fetcher client
- **Phase 3** — Generator: API, worker, cron, integration test
- **Phase 4** — Edge service
- **Phase 5** — Frontend migration into generator + multi-stage Dockerfile
- **Phase 6** — Top-level README, CLAUDE.md update, final gitignore

---

## Phase 0 — Scaffolding

### Task 0.1: Create service folders and .gitignore

**Files:**
- Create: `fetcher/`, `fetcher/src/`, `fetcher/tests/`, `fetcher/data/`
- Create: `generator/`, `generator/src/`, `generator/tests/`, `generator/tests/integration/`, `generator/data/`
- Create: `edge/`, `edge/src/`, `edge/tests/`
- Modify: `.gitignore`

- [ ] **Step 1: Create directories**

```bash
mkdir -p fetcher/src fetcher/tests fetcher/data
mkdir -p generator/src generator/tests/integration generator/data
mkdir -p edge/src edge/tests
touch fetcher/src/__init__.py fetcher/tests/__init__.py
touch generator/src/__init__.py generator/tests/__init__.py generator/tests/integration/__init__.py
touch edge/src/__init__.py edge/tests/__init__.py
touch fetcher/data/.gitkeep generator/data/.gitkeep
```

- [ ] **Step 2: Update `.gitignore`**

Append to `.gitignore`:

```
# Per-service SQLite databases (runtime data)
fetcher/data/*.db
fetcher/data/*.db-wal
fetcher/data/*.db-shm
generator/data/*.db
generator/data/*.db-wal
generator/data/*.db-shm

# Built frontend bundle
generator/src/static/
generator/frontend/dist/
generator/frontend/node_modules/

# Python build artifacts
**/__pycache__/
**/*.pyc
.pytest_cache/

# Widget build artifacts at repo root (retired)
/widget_*.svg
/data/ghstats.db
```

- [ ] **Step 3: Commit (ask user for approval first)**

```bash
git add .gitignore fetcher/ generator/ edge/
git commit -m "chore(scaffold): create fetcher/generator/edge service folders"
```

---

### Task 0.2: Remove retired top-level code and artifacts

**Files to delete:**
- `run.py`
- `src/generate.py`, `src/fetcher_api.py`, `src/generator_api.py`
- `src/data/ARCHITECTURE.md`
- `widget_*.svg` at repo root
- `data/ghstats.db`
- `REPORT.md`, `CHANGELOG.md` (stale)
- `src/README.md`

Do NOT delete yet: `src/config.py`, `src/widgets/`, `src/themes/`, `src/models/`, `src/utils/`, `src/data/fetcher.py`, `src/data/processor.py`, `src/db/`. These move in later phases via `git mv`.

- [ ] **Step 1: Stage removals**

```bash
git rm run.py src/generate.py src/fetcher_api.py src/generator_api.py
git rm src/data/ARCHITECTURE.md src/README.md
git rm REPORT.md CHANGELOG.md
git rm widget_achievements.svg widget_collaborators.svg widget_focus.svg widget_grade.svg widget_impact.svg widget_languages.svg widget_shaymanor.svg
git rm data/ghstats.db
```

- [ ] **Step 2: Verify no remaining imports of deleted modules**

Run: `grep -rn "from src.generate\|from src.fetcher_api\|from src.generator_api\|import run" src/ 2>/dev/null || echo "clean"`
Expected: `clean`

- [ ] **Step 3: Commit (ask user for approval first)**

```bash
git commit -m "chore(cleanup): remove retired entry points and build artifacts"
```

---

## Phase 1 — Fetcher Service

### Task 1.1: Fetcher scaffolding (requirements, config, pytest, Dockerfile)

**Files:**
- Create: `fetcher/requirements.txt`
- Create: `fetcher/pytest.ini`
- Create: `fetcher/src/config.py`
- Create: `fetcher/Dockerfile`

- [ ] **Step 1: `fetcher/requirements.txt`**

```
flask==3.0.3
requests==2.32.3
pytest==8.3.3
responses==0.25.3
gunicorn==23.0.0
```

- [ ] **Step 2: `fetcher/pytest.ini`**

```ini
[pytest]
testpaths = tests
python_files = test_*.py
pythonpath = .
addopts = -ra --strict-markers
```

- [ ] **Step 3: `fetcher/src/config.py`**

```python
"""Fetcher service configuration, overridable via env vars."""
import os

PORT = int(os.getenv("FETCHER_PORT", "5001"))
DB_PATH = os.getenv("FETCHER_DB_PATH", "./data/fetcher.db")
GITHUB_PAT = os.getenv("GITHUB_PAT", "")
INTERNAL_TOKEN = os.getenv("FETCHER_INTERNAL_TOKEN", "")
REFRESH_INTERVAL_HOURS = int(os.getenv("FETCHER_REFRESH_INTERVAL_HOURS", "24"))
TRIAL_GC_DAYS = int(os.getenv("FETCHER_TRIAL_GC_DAYS", "7"))
API_TIMEOUT = int(os.getenv("API_TIMEOUT", "15"))
```

- [ ] **Step 4: `fetcher/Dockerfile`**

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY src ./src
RUN mkdir -p /app/data

EXPOSE 5001
ENV FETCHER_DB_PATH=/app/data/fetcher.db

# Default is the API. Override CMD for cron: ["python", "-m", "src.cron"]
CMD ["gunicorn", "-b", "0.0.0.0:5001", "-w", "2", "src.api:app"]
```

- [ ] **Step 5: Commit**

```bash
git add fetcher/requirements.txt fetcher/pytest.ini fetcher/src/config.py fetcher/Dockerfile
git commit -m "feat(fetcher): scaffold config, requirements, pytest, Dockerfile"
```

---

### Task 1.2: Fetcher `db.py` — schema, WAL, CRUD, payload hashing

**Files:**
- Create: `fetcher/src/db.py`
- Create: `fetcher/tests/test_db.py`

- [ ] **Step 1: Write the failing tests `fetcher/tests/test_db.py`**

```python
import os
import tempfile
import pytest
from src import db as dbmod


@pytest.fixture
def tmp_db(monkeypatch):
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "t.db")
        monkeypatch.setattr(dbmod, "DB_PATH", path)
        dbmod.init_db()
        yield path


def test_init_creates_schema_with_wal(tmp_db):
    with dbmod._connect() as c:
        mode = c.execute("PRAGMA journal_mode").fetchone()[0]
        assert mode.lower() == "wal"
        cols = [r[1] for r in c.execute("PRAGMA table_info(users)").fetchall()]
        assert set(cols) == {"username", "data_json", "payload_hash",
                             "fetched_at", "last_requested_at"}


def test_upsert_and_get_round_trip(tmp_db):
    dbmod.upsert_user("alice", {"user": {"login": "alice"}, "repos": []})
    row = dbmod.get_user("alice")
    assert row["data"]["user"]["login"] == "alice"
    assert row["payload_hash"]
    assert row["fetched_at"]


def test_payload_hash_is_deterministic_and_changes_on_diff():
    h1 = dbmod.payload_hash({"a": 1, "b": 2})
    h2 = dbmod.payload_hash({"b": 2, "a": 1})
    h3 = dbmod.payload_hash({"a": 1, "b": 3})
    assert h1 == h2
    assert h1 != h3


def test_get_updates_last_requested_at(tmp_db):
    dbmod.upsert_user("alice", {"user": {"login": "alice"}})
    first = dbmod.get_user("alice")["last_requested_at"]
    import time; time.sleep(1.1)
    second = dbmod.get_user("alice")["last_requested_at"]
    assert second > first


def test_delete_stale_removes_old_rows(tmp_db):
    dbmod.upsert_user("ghost", {"user": {"login": "ghost"}})
    # Manually backdate last_requested_at
    with dbmod._connect() as c:
        c.execute("UPDATE users SET last_requested_at='2020-01-01T00:00:00Z' WHERE username='ghost'")
    removed = dbmod.delete_stale(days=7)
    assert removed == 1
    assert dbmod.get_user("ghost") is None


def test_users_due_for_refresh(tmp_db):
    dbmod.upsert_user("alice", {"user": {"login": "alice"}})
    # Backdate fetched_at so alice is due
    with dbmod._connect() as c:
        c.execute("UPDATE users SET fetched_at='2020-01-01T00:00:00Z' WHERE username='alice'")
    due = dbmod.users_due_for_refresh(hours=24, active_within_days=7)
    assert "alice" in due
```

- [ ] **Step 2: Run tests — expect failures**

Run: `cd fetcher && pytest tests/test_db.py -v`
Expected: `ModuleNotFoundError` or similar (db module not yet complete).

- [ ] **Step 3: Implement `fetcher/src/db.py`**

```python
"""SQLite repository for the fetcher service.

Single table: users (raw GitHub payloads keyed by username).
Uses WAL mode so concurrent readers don't block the writer.
"""
import hashlib
import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Optional

from . import config

DB_PATH = config.DB_PATH

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS users (
    username          TEXT PRIMARY KEY,
    data_json         TEXT NOT NULL,
    payload_hash      TEXT NOT NULL,
    fetched_at        TEXT NOT NULL,
    last_requested_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_users_fetched_at ON users(fetched_at);
CREATE INDEX IF NOT EXISTS idx_users_last_requested_at ON users(last_requested_at);
"""


def _now() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


@contextmanager
def _connect():
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")
    try:
        yield conn
    finally:
        conn.close()


def init_db() -> None:
    with _connect() as c:
        c.executescript(SCHEMA_SQL)
        c.commit()


def payload_hash(data: dict) -> str:
    canonical = json.dumps(data, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def upsert_user(username: str, data: dict) -> str:
    h = payload_hash(data)
    now = _now()
    with _connect() as c:
        c.execute(
            """INSERT INTO users(username, data_json, payload_hash, fetched_at, last_requested_at)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(username) DO UPDATE SET
                   data_json = excluded.data_json,
                   payload_hash = excluded.payload_hash,
                   fetched_at = excluded.fetched_at""",
            (username, json.dumps(data), h, now, now),
        )
        c.commit()
    return h


def get_user(username: str) -> Optional[dict]:
    """Returns {data, payload_hash, fetched_at, last_requested_at} or None. Updates last_requested_at."""
    now = _now()
    with _connect() as c:
        row = c.execute(
            "SELECT data_json, payload_hash, fetched_at, last_requested_at FROM users WHERE username=?",
            (username,),
        ).fetchone()
        if row is None:
            return None
        c.execute("UPDATE users SET last_requested_at=? WHERE username=?", (now, username))
        c.commit()
    return {
        "data": json.loads(row["data_json"]),
        "payload_hash": row["payload_hash"],
        "fetched_at": row["fetched_at"],
        "last_requested_at": now,
    }


def delete_stale(days: int) -> int:
    cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat(timespec="seconds") + "Z"
    with _connect() as c:
        cur = c.execute("DELETE FROM users WHERE last_requested_at < ?", (cutoff,))
        c.commit()
        return cur.rowcount


def users_due_for_refresh(hours: int, active_within_days: int) -> list[str]:
    """Return usernames with fetched_at older than `hours` and last_requested_at within `active_within_days`."""
    stale_before = (datetime.utcnow() - timedelta(hours=hours)).isoformat(timespec="seconds") + "Z"
    active_after = (datetime.utcnow() - timedelta(days=active_within_days)).isoformat(timespec="seconds") + "Z"
    with _connect() as c:
        rows = c.execute(
            "SELECT username FROM users WHERE fetched_at < ? AND last_requested_at > ?",
            (stale_before, active_after),
        ).fetchall()
    return [r["username"] for r in rows]


def list_usernames() -> list[str]:
    with _connect() as c:
        return [r["username"] for r in c.execute("SELECT username FROM users ORDER BY username").fetchall()]
```

- [ ] **Step 4: Run tests — expect pass**

Run: `cd fetcher && pytest tests/test_db.py -v`
Expected: all 6 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add fetcher/src/db.py fetcher/tests/test_db.py
git commit -m "feat(fetcher): add SQLite db module with WAL, payload hashing, GC"
```

---

### Task 1.3: Fetcher `github.py` — move from `src/data/fetcher.py`

**Files:**
- Move: `src/data/fetcher.py` → `fetcher/src/github.py`
- Create: `fetcher/tests/test_github.py`

- [ ] **Step 1: Move file**

```bash
git mv src/data/fetcher.py fetcher/src/github.py
```

- [ ] **Step 2: Adjust imports inside `fetcher/src/github.py`**

Inside that file, change `from src.config import ...` to `from . import config` and update all config references to `config.NAME`. Remove any `src.models` or other generator-only imports if present (the fetcher only needs to produce raw JSON — no typed models).

- [ ] **Step 3: Write smoke tests `fetcher/tests/test_github.py`**

```python
import responses
import pytest
from src import github


@responses.activate
def test_fetch_user_data_returns_user_payload():
    responses.add(
        responses.POST, "https://api.github.com/graphql",
        json={"data": {"user": {"contributionsCollection": {"contributionCalendar": {"weeks": []}}}}},
        status=200,
    )
    responses.add(
        responses.GET, "https://api.github.com/users/alice",
        json={"login": "alice", "public_repos": 3, "followers": 5, "avatar_url": "https://avatars.example/1"},
        status=200,
    )
    responses.add(
        responses.GET, "https://api.github.com/users/alice/repos",
        json=[], status=200,
    )
    responses.add(
        responses.GET, "https://api.github.com/users/alice/events",
        json=[], status=200,
    )
    data = github.fetch_github_data("alice", token="t")
    assert data["user"]["login"] == "alice"
    assert "repos" in data
    assert "events" in data


@responses.activate
def test_fetch_handles_404():
    responses.add(
        responses.GET, "https://api.github.com/users/nope",
        json={"message": "Not Found"}, status=404,
    )
    responses.add(
        responses.POST, "https://api.github.com/graphql",
        json={"data": {"user": None}}, status=200,
    )
    responses.add(
        responses.GET, "https://api.github.com/users/nope/repos",
        json={"message": "Not Found"}, status=404,
    )
    responses.add(
        responses.GET, "https://api.github.com/users/nope/events",
        json={"message": "Not Found"}, status=404,
    )
    data = github.fetch_github_data("nope", token="t")
    # The existing fetcher returns whatever GitHub gave it; we just assert it doesn't crash
    # and the caller can detect not_found via data["user"].get("message")
    assert data["user"].get("message") == "Not Found" or data["user"] is None
```

- [ ] **Step 4: Run tests**

Run: `cd fetcher && pytest tests/test_github.py -v`
Expected: both PASS. If the second fails because the existing code expects a specific shape, adjust the test to match the actual return shape (read `fetcher/src/github.py` to see what it returns on 404).

- [ ] **Step 5: Commit**

```bash
git add fetcher/src/github.py fetcher/tests/test_github.py
git commit -m "feat(fetcher): move GitHub client into fetcher service"
```

---

### Task 1.4: Fetcher `api.py` — Flask routes + shared-secret auth

**Files:**
- Create: `fetcher/src/api.py`
- Create: `fetcher/tests/test_api.py`

- [ ] **Step 1: Write failing tests `fetcher/tests/test_api.py`**

```python
import os
import tempfile
import pytest
import responses as resp_lib
from src import db as dbmod
from src import api as apimod


@pytest.fixture
def client(monkeypatch):
    with tempfile.TemporaryDirectory() as d:
        monkeypatch.setattr(dbmod, "DB_PATH", os.path.join(d, "t.db"))
        monkeypatch.setattr(apimod.config, "INTERNAL_TOKEN", "secret")
        monkeypatch.setattr(apimod.config, "GITHUB_PAT", "ghp_test")
        dbmod.init_db()
        app = apimod.app
        app.config["TESTING"] = True
        with app.test_client() as c:
            yield c


def test_health_no_auth_required(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.get_json()["service"] == "fetcher"


def test_endpoints_require_internal_token(client):
    r = client.get("/data/alice")
    assert r.status_code == 401


@resp_lib.activate
def test_data_auto_fetches_on_miss(client, monkeypatch):
    resp_lib.add(resp_lib.POST, "https://api.github.com/graphql",
                 json={"data": {"user": {"contributionsCollection": {"contributionCalendar": {"weeks": []}}}}}, status=200)
    resp_lib.add(resp_lib.GET, "https://api.github.com/users/alice",
                 json={"login": "alice", "public_repos": 1, "followers": 0, "avatar_url": "https://avatars.example/a"}, status=200)
    resp_lib.add(resp_lib.GET, "https://api.github.com/users/alice/repos", json=[], status=200)
    resp_lib.add(resp_lib.GET, "https://api.github.com/users/alice/events", json=[], status=200)

    r = client.get("/data/alice", headers={"X-Internal-Token": "secret"})
    assert r.status_code == 200
    body = r.get_json()
    assert body["payload_hash"]
    assert body["data"]["user"]["login"] == "alice"


def test_force_fetch_requires_auth(client):
    r = client.post("/fetch", json={"username": "alice"})
    assert r.status_code == 401
```

- [ ] **Step 2: Run — expect fail**

Run: `cd fetcher && pytest tests/test_api.py -v`
Expected: import error (no api module yet).

- [ ] **Step 3: Implement `fetcher/src/api.py`**

```python
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
```

- [ ] **Step 4: Run tests — expect pass**

Run: `cd fetcher && pytest tests/test_api.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add fetcher/src/api.py fetcher/tests/test_api.py
git commit -m "feat(fetcher): add Flask API with auth, auto-fetch, avatar"
```

---

### Task 1.5: Fetcher `cron.py` — scheduled refresh + GC

**Files:**
- Create: `fetcher/src/cron.py`
- Create: `fetcher/tests/test_cron.py`

- [ ] **Step 1: Write failing tests**

```python
import os
import tempfile
import pytest
from unittest.mock import patch
from src import db as dbmod
from src import cron as cronmod


@pytest.fixture
def tmp_db(monkeypatch):
    with tempfile.TemporaryDirectory() as d:
        monkeypatch.setattr(dbmod, "DB_PATH", os.path.join(d, "t.db"))
        dbmod.init_db()
        yield


def test_refresh_tick_calls_github_for_due_users(tmp_db):
    dbmod.upsert_user("alice", {"user": {"login": "alice"}})
    # Backdate
    with dbmod._connect() as c:
        c.execute("UPDATE users SET fetched_at='2020-01-01T00:00:00Z', last_requested_at=? WHERE username='alice'",
                  (dbmod._now(),))
    with patch("src.cron.github.fetch_github_data", return_value={"user": {"login": "alice", "updated": True}}) as gh:
        stats = cronmod.tick(hours=24, active_within_days=7, gc_days=7)
    assert gh.called
    assert stats["refreshed"] == 1


def test_tick_runs_gc_for_abandoned_trial_users(tmp_db):
    dbmod.upsert_user("ghost", {"user": {"login": "ghost"}})
    with dbmod._connect() as c:
        c.execute("UPDATE users SET last_requested_at='2020-01-01T00:00:00Z' WHERE username='ghost'")
    stats = cronmod.tick(hours=24, active_within_days=7, gc_days=7)
    assert stats["gc_removed"] == 1
    assert dbmod.get_user("ghost") is None
```

- [ ] **Step 2: Run — expect fail**

Run: `cd fetcher && pytest tests/test_cron.py -v`
Expected: fail.

- [ ] **Step 3: Implement `fetcher/src/cron.py`**

```python
"""Scheduled refresh + GC loop. Run as its own container (CMD override)."""
import logging
import time

from . import config, db, github

log = logging.getLogger("fetcher.cron")


def tick(hours: int, active_within_days: int, gc_days: int) -> dict:
    """Refresh due users, then GC abandoned ones. Returns counts."""
    refreshed = 0
    failed = 0
    due = db.users_due_for_refresh(hours=hours, active_within_days=active_within_days)
    for username in due:
        try:
            data = github.fetch_github_data(username, token=config.GITHUB_PAT)
            user = data.get("user")
            if user is None or (isinstance(user, dict) and user.get("message") == "Not Found"):
                data = {"error": "not_found"}
            db.upsert_user(username, data)
            refreshed += 1
        except Exception as e:
            log.warning("refresh failed for %s: %s", username, e)
            failed += 1
    gc_removed = db.delete_stale(days=gc_days)
    return {"refreshed": refreshed, "failed": failed, "gc_removed": gc_removed}


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    db.init_db()
    interval = 3600  # 1h between ticks
    while True:
        try:
            stats = tick(
                hours=config.REFRESH_INTERVAL_HOURS,
                active_within_days=config.TRIAL_GC_DAYS,
                gc_days=config.TRIAL_GC_DAYS,
            )
            log.info("tick complete: %s", stats)
        except Exception:
            log.exception("tick failed")
        time.sleep(interval)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests — expect pass**

Run: `cd fetcher && pytest tests/test_cron.py -v`
Expected: PASS.

- [ ] **Step 5: Write `fetcher/README.md`**

```markdown
# Fetcher Service

Owns every GitHub API interaction. Holds the PAT. Exposes cached payloads
over an internal-only HTTP API protected by a shared secret.

## Run locally

    cd fetcher
    pip install -r requirements.txt
    FETCHER_INTERNAL_TOKEN=dev GITHUB_PAT=ghp_xxx python -m src.api

Cron (separate process):

    FETCHER_INTERNAL_TOKEN=dev GITHUB_PAT=ghp_xxx python -m src.cron

## Test

    cd fetcher && pytest

## Docker

    docker build -t ghstats-fetcher .
    docker run -e GITHUB_PAT=ghp_xxx -e FETCHER_INTERNAL_TOKEN=dev -p 5001:5001 -v $(pwd)/data:/app/data ghstats-fetcher
    # cron: override CMD to ["python","-m","src.cron"]

## Endpoints

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | /health | none | health check |
| GET | /data/<u> | X-Internal-Token | return stored payload; auto-fetches on miss |
| POST | /fetch | X-Internal-Token | force re-fetch (body: {username}) |
| GET | /avatar/<u> | X-Internal-Token | proxied avatar bytes |

## Env

See `src/config.py`.
```

- [ ] **Step 6: Commit**

```bash
git add fetcher/src/cron.py fetcher/tests/test_cron.py fetcher/README.md
git commit -m "feat(fetcher): add cron refresh + GC and service README"
```

---

## Phase 2 — Generator: DB, Cache, Placeholder, Processor, Fetcher client

### Task 2.1: Generator scaffolding + move widgets/themes/models/utils/processor

**Files:**
- Create: `generator/requirements.txt`, `generator/pytest.ini`
- Move: `src/widgets/` → `generator/src/widgets/`
- Move: `src/themes/` → `generator/src/themes/`
- Move: `src/models/` → `generator/src/models/`
- Move: `src/utils/` → `generator/src/utils/`
- Move: `src/data/processor.py` → `generator/src/processor.py`
- Move: `src/config.py` → `generator/src/config.py` (merge with new env vars)

- [ ] **Step 1: `generator/requirements.txt`**

```
flask==3.0.3
flask-caching==2.3.0
flask-compress==1.15
requests==2.32.3
pytest==8.3.3
responses==0.25.3
gunicorn==23.0.0
```

- [ ] **Step 2: `generator/pytest.ini`**

```ini
[pytest]
testpaths = tests
python_files = test_*.py
pythonpath = .
addopts = -ra --strict-markers
```

- [ ] **Step 3: Move existing modules**

```bash
git mv src/widgets generator/src/widgets
git mv src/themes generator/src/themes
git mv src/models generator/src/models
git mv src/utils generator/src/utils
git mv src/data/processor.py generator/src/processor.py
git mv src/config.py generator/src/config.py
```

- [ ] **Step 4: Adjust imports in moved files**

In every moved `.py` file under `generator/src/`, replace:

- `from src.config` → `from .. import config` (if in subpackage) or `from . import config` (if at top level)
- `from src.widgets` → `from .widgets` (in top-level modules) or `from ..widgets` (in subpackages)
- `from src.themes`, `from src.models`, `from src.utils` similarly
- `from src.data.processor` → `from . import processor`

Run a sweep:

```bash
grep -rn "from src\." generator/src/ && echo "FIX THESE" || echo "clean"
```

Fix each reported line until the grep prints `clean`.

- [ ] **Step 5: Extend `generator/src/config.py` with new env vars**

Append to existing config.py:

```python
# --- Service-specific additions (v2 of config) ---

PORT = int(os.getenv("GENERATOR_PORT", "5002"))
SETTINGS_DB_PATH = os.getenv("GENERATOR_SETTINGS_DB_PATH", "./data/settings.db")
WIDGETS_DB_PATH = os.getenv("GENERATOR_WIDGETS_DB_PATH", "./data/widgets.db")
FETCHER_URL = os.getenv("FETCHER_URL", "http://localhost:5001")
FETCHER_INTERNAL_TOKEN = os.getenv("FETCHER_INTERNAL_TOKEN", "")
REDIS_URL = os.getenv("REDIS_URL", "")
ENROLLMENT_DAILY_CAP = int(os.getenv("ENROLLMENT_DAILY_CAP", "50"))
WIDGET_LRU_PER_USER = int(os.getenv("WIDGET_LRU_PER_USER", "10"))
POLL_INTERVAL_MINUTES = int(os.getenv("GENERATOR_POLL_INTERVAL_MINUTES", "15"))
```

- [ ] **Step 6: Delete now-empty `src/` tree**

```bash
# After moves above, src/data/__init__.py and src/__init__.py still exist.
# Remove the retired db module and empty src/
git rm -r src/db src/data src/__init__.py
rmdir src 2>/dev/null || true
```

- [ ] **Step 7: Smoke-check generator-side imports load**

```bash
cd generator && python -c "from src import processor, widgets, themes, models, utils, config; print('ok')"
```

Expected: `ok`. If not, fix the failing import and repeat.

- [ ] **Step 8: Commit**

```bash
git add generator/requirements.txt generator/pytest.ini generator/src/ -A
git add -u src/ 2>/dev/null || true
git commit -m "feat(generator): scaffold + move widgets/themes/models/utils/processor/config"
```

---

### Task 2.2: Generator `db.py` — settings + widgets + jobs + enrollments

**Files:**
- Create: `generator/src/db.py`
- Create: `generator/tests/test_db.py`

- [ ] **Step 1: Write failing tests `generator/tests/test_db.py`**

```python
import os
import tempfile
import pytest
from src import db as dbmod


@pytest.fixture
def tmp_dbs(monkeypatch):
    with tempfile.TemporaryDirectory() as d:
        monkeypatch.setattr(dbmod, "SETTINGS_DB_PATH", os.path.join(d, "s.db"))
        monkeypatch.setattr(dbmod, "WIDGETS_DB_PATH", os.path.join(d, "w.db"))
        dbmod.init_dbs()
        yield d


def test_settings_hash_is_deterministic():
    h1 = dbmod.settings_hash({"theme": "dark", "widgets": ["a", "b"]})
    h2 = dbmod.settings_hash({"widgets": ["a", "b"], "theme": "dark"})
    assert h1 == h2


def test_enroll_and_get_settings(tmp_dbs):
    defaults = {"theme": "dark", "widgets": ["grade"]}
    job_id = dbmod.enroll("alice", defaults)
    assert job_id > 0
    s = dbmod.get_settings("alice")
    assert s["settings"] == defaults
    assert s["manual_refresh_used"] == 0


def test_enrollments_daily_counter(tmp_dbs):
    dbmod.enroll("alice", {"theme": "dark"})
    dbmod.enroll("bob", {"theme": "dark"})
    assert dbmod.enrollments_today() == 2


def test_update_settings_changes_hash(tmp_dbs):
    dbmod.enroll("alice", {"theme": "dark"})
    h_before = dbmod.get_settings("alice")["settings_hash"]
    dbmod.update_settings("alice", {"theme": "light"})
    h_after = dbmod.get_settings("alice")["settings_hash"]
    assert h_before != h_after


def test_claim_job_marks_running(tmp_dbs):
    job_id = dbmod.enroll("alice", {"theme": "dark"})
    job = dbmod.claim_next_job()
    assert job["id"] == job_id
    assert job["status"] == "running"
    assert dbmod.claim_next_job() is None  # already running


def test_complete_job(tmp_dbs):
    jid = dbmod.enroll("alice", {"theme": "dark"})
    dbmod.claim_next_job()
    dbmod.complete_job(jid)
    with dbmod._settings_conn() as c:
        status = c.execute("SELECT status FROM jobs WHERE id=?", (jid,)).fetchone()[0]
    assert status == "done"


def test_widgets_put_and_get(tmp_dbs):
    dbmod.put_widgets("alice", "hash1", {"composite": "<svg/>", "grade": "<svg/>"})
    row = dbmod.get_current_widget("alice", "composite")
    assert row == "<svg/>"


def test_current_widget_flips_atomically(tmp_dbs):
    dbmod.put_widgets("alice", "hash1", {"composite": "<svg>v1</svg>"})
    dbmod.put_widgets("alice", "hash2", {"composite": "<svg>v2</svg>"})
    assert dbmod.get_current_widget("alice", "composite") == "<svg>v2</svg>"


def test_lru_trim_keeps_n_newest(tmp_dbs):
    for i in range(12):
        dbmod.put_widgets("alice", f"hash{i}", {"composite": f"<svg>{i}</svg>"})
    dbmod.lru_trim("alice", keep=10)
    with dbmod._widgets_conn() as c:
        n = c.execute("SELECT COUNT(DISTINCT settings_hash) FROM widgets WHERE username='alice'").fetchone()[0]
    assert n == 10


def test_reclaim_stuck_running_jobs(tmp_dbs):
    jid = dbmod.enroll("alice", {"theme": "dark"})
    dbmod.claim_next_job()
    # Backdate updated_at to simulate dead worker
    with dbmod._settings_conn() as c:
        c.execute("UPDATE jobs SET updated_at='2020-01-01T00:00:00Z' WHERE id=?", (jid,))
        c.commit()
    dbmod.reclaim_stuck_jobs(older_than_minutes=10)
    job = dbmod.claim_next_job()
    assert job["id"] == jid
```

- [ ] **Step 2: Run — expect fail**

- [ ] **Step 3: Implement `generator/src/db.py`**

```python
"""Generator's two SQLite DBs: settings.db (settings + jobs + enrollments) and widgets.db (svg cache).

All access goes through this module so a future Postgres swap is local to here.
Both DBs are opened with WAL mode.
"""
import hashlib
import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Optional

from . import config

SETTINGS_DB_PATH = config.SETTINGS_DB_PATH
WIDGETS_DB_PATH = config.WIDGETS_DB_PATH

_SETTINGS_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    username                  TEXT PRIMARY KEY,
    settings_json             TEXT NOT NULL,
    settings_hash             TEXT NOT NULL,
    enrolled_at               TEXT NOT NULL,
    last_fetcher_payload_hash TEXT,
    manual_refresh_used       INTEGER DEFAULT 0,
    last_requested_at         TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS enrollments_daily (
    day   TEXT PRIMARY KEY,
    count INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS jobs (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    kind       TEXT NOT NULL,
    username   TEXT NOT NULL,
    status     TEXT NOT NULL,
    attempts   INTEGER DEFAULT 0,
    last_error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_jobs_pending ON jobs(status, created_at);
"""

_WIDGETS_SCHEMA = """
CREATE TABLE IF NOT EXISTS widgets (
    username      TEXT NOT NULL,
    settings_hash TEXT NOT NULL,
    widget_name   TEXT NOT NULL,
    svg           TEXT NOT NULL,
    built_at      TEXT NOT NULL,
    PRIMARY KEY (username, settings_hash, widget_name)
);
CREATE TABLE IF NOT EXISTS current_widget (
    username      TEXT PRIMARY KEY,
    settings_hash TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_widgets_username ON widgets(username);
"""


def _now() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


def _today() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d")


def _open(path: str) -> sqlite3.Connection:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


@contextmanager
def _settings_conn():
    conn = _open(SETTINGS_DB_PATH)
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def _widgets_conn():
    conn = _open(WIDGETS_DB_PATH)
    try:
        yield conn
    finally:
        conn.close()


def init_dbs() -> None:
    with _settings_conn() as c:
        c.executescript(_SETTINGS_SCHEMA)
        c.commit()
    with _widgets_conn() as c:
        c.executescript(_WIDGETS_SCHEMA)
        c.commit()


def settings_hash(settings: dict) -> str:
    canonical = json.dumps(settings, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# ---- settings / enrollment ----

def enroll(username: str, defaults: dict) -> int:
    """Insert a settings row + increment daily counter + enqueue build. Returns job_id."""
    sh = settings_hash(defaults)
    now = _now()
    with _settings_conn() as c:
        c.execute(
            """INSERT INTO users(username, settings_json, settings_hash, enrolled_at, last_requested_at)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(username) DO NOTHING""",
            (username, json.dumps(defaults), sh, now, now),
        )
        c.execute(
            """INSERT INTO enrollments_daily(day, count) VALUES (?, 1)
               ON CONFLICT(day) DO UPDATE SET count = count + 1""",
            (_today(),),
        )
        cur = c.execute(
            """INSERT INTO jobs(kind, username, status, created_at, updated_at)
               VALUES ('build', ?, 'pending', ?, ?)""",
            (username, now, now),
        )
        c.commit()
        return cur.lastrowid


def enrollments_today() -> int:
    with _settings_conn() as c:
        row = c.execute("SELECT count FROM enrollments_daily WHERE day=?", (_today(),)).fetchone()
        return row["count"] if row else 0


def get_settings(username: str) -> Optional[dict]:
    with _settings_conn() as c:
        row = c.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
    if row is None:
        return None
    return {
        "settings": json.loads(row["settings_json"]),
        "settings_hash": row["settings_hash"],
        "manual_refresh_used": row["manual_refresh_used"],
        "last_fetcher_payload_hash": row["last_fetcher_payload_hash"],
        "enrolled_at": row["enrolled_at"],
    }


def update_settings(username: str, new_settings: dict) -> int:
    """Updates settings + enqueues rebuild. Returns job_id."""
    sh = settings_hash(new_settings)
    now = _now()
    with _settings_conn() as c:
        c.execute(
            "UPDATE users SET settings_json=?, settings_hash=? WHERE username=?",
            (json.dumps(new_settings), sh, username),
        )
        cur = c.execute(
            """INSERT INTO jobs(kind, username, status, created_at, updated_at)
               VALUES ('build', ?, 'pending', ?, ?)""",
            (username, now, now),
        )
        c.commit()
        return cur.lastrowid


def mark_manual_refresh(username: str) -> bool:
    """Sets manual_refresh_used=1 only if it was 0. Returns True if successfully flipped."""
    with _settings_conn() as c:
        cur = c.execute(
            "UPDATE users SET manual_refresh_used=1 WHERE username=? AND manual_refresh_used=0",
            (username,),
        )
        c.commit()
        return cur.rowcount == 1


def touch_last_requested(username: str) -> None:
    with _settings_conn() as c:
        c.execute("UPDATE users SET last_requested_at=? WHERE username=?", (_now(), username))
        c.commit()


def list_enrolled() -> list[str]:
    with _settings_conn() as c:
        return [r["username"] for r in c.execute("SELECT username FROM users").fetchall()]


def set_last_fetcher_hash(username: str, h: str) -> None:
    with _settings_conn() as c:
        c.execute("UPDATE users SET last_fetcher_payload_hash=? WHERE username=?", (h, username))
        c.commit()


# ---- jobs ----

def enqueue_build(username: str) -> int:
    now = _now()
    with _settings_conn() as c:
        cur = c.execute(
            """INSERT INTO jobs(kind, username, status, created_at, updated_at)
               VALUES ('build', ?, 'pending', ?, ?)""",
            (username, now, now),
        )
        c.commit()
        return cur.lastrowid


def claim_next_job() -> Optional[dict]:
    now = _now()
    with _settings_conn() as c:
        row = c.execute(
            "SELECT * FROM jobs WHERE status='pending' ORDER BY created_at LIMIT 1"
        ).fetchone()
        if row is None:
            return None
        c.execute("UPDATE jobs SET status='running', updated_at=?, attempts=attempts+1 WHERE id=?",
                  (now, row["id"]))
        c.commit()
        return {"id": row["id"], "username": row["username"], "kind": row["kind"], "status": "running"}


def complete_job(job_id: int) -> None:
    with _settings_conn() as c:
        c.execute("UPDATE jobs SET status='done', updated_at=? WHERE id=?", (_now(), job_id))
        c.commit()


def fail_job(job_id: int, err: str, retry: bool) -> None:
    status = "pending" if retry else "failed"
    with _settings_conn() as c:
        c.execute("UPDATE jobs SET status=?, last_error=?, updated_at=? WHERE id=?",
                  (status, err, _now(), job_id))
        c.commit()


def reclaim_stuck_jobs(older_than_minutes: int) -> int:
    cutoff = (datetime.utcnow() - timedelta(minutes=older_than_minutes)).isoformat(timespec="seconds") + "Z"
    with _settings_conn() as c:
        cur = c.execute(
            "UPDATE jobs SET status='pending', updated_at=? WHERE status='running' AND updated_at < ?",
            (_now(), cutoff),
        )
        c.commit()
        return cur.rowcount


# ---- widgets ----

def put_widgets(username: str, hash_: str, widgets: dict[str, str]) -> None:
    """Insert widget rows for this (user, hash) and flip current_widget to point at it."""
    now = _now()
    with _widgets_conn() as c:
        for name, svg in widgets.items():
            c.execute(
                """INSERT INTO widgets(username, settings_hash, widget_name, svg, built_at)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(username, settings_hash, widget_name) DO UPDATE SET
                       svg = excluded.svg, built_at = excluded.built_at""",
                (username, hash_, name, svg, now),
            )
        c.execute(
            """INSERT INTO current_widget(username, settings_hash, updated_at)
               VALUES (?, ?, ?)
               ON CONFLICT(username) DO UPDATE SET settings_hash=excluded.settings_hash, updated_at=excluded.updated_at""",
            (username, hash_, now),
        )
        c.commit()


def get_current_widget(username: str, widget_name: str) -> Optional[str]:
    with _widgets_conn() as c:
        row = c.execute(
            """SELECT w.svg FROM widgets w
               JOIN current_widget cw ON cw.username=w.username AND cw.settings_hash=w.settings_hash
               WHERE w.username=? AND w.widget_name=?""",
            (username, widget_name),
        ).fetchone()
    return row["svg"] if row else None


def lru_trim(username: str, keep: int) -> int:
    """Keep only the N newest settings_hashes per user; delete older rows."""
    with _widgets_conn() as c:
        hashes = [r["settings_hash"] for r in c.execute(
            """SELECT settings_hash, MAX(built_at) AS latest FROM widgets
               WHERE username=? GROUP BY settings_hash ORDER BY latest DESC""",
            (username,),
        ).fetchall()]
        to_delete = hashes[keep:]
        if not to_delete:
            return 0
        placeholders = ",".join("?" * len(to_delete))
        cur = c.execute(
            f"DELETE FROM widgets WHERE username=? AND settings_hash IN ({placeholders})",
            (username, *to_delete),
        )
        c.commit()
        return cur.rowcount
```

- [ ] **Step 4: Run tests — expect pass**

Run: `cd generator && pytest tests/test_db.py -v`
Expected: all 10 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add generator/src/db.py generator/tests/test_db.py
git commit -m "feat(generator): add settings+widgets db with jobs, enrollment, LRU"
```

---

### Task 2.3: Generator `cache.py` — no-op wrapper (Redis later)

**Files:**
- Create: `generator/src/cache.py`
- Create: `generator/tests/test_cache.py`

- [ ] **Step 1: Tests**

```python
from src import cache


def test_noop_when_redis_url_empty(monkeypatch):
    monkeypatch.setattr(cache.config, "REDIS_URL", "")
    c = cache.Cache()
    assert c.get("k") is None
    c.set("k", "v", 60)
    c.delete("k")
    assert c.get("k") is None  # still None because no-op


def test_enabled_flag_reflects_config(monkeypatch):
    monkeypatch.setattr(cache.config, "REDIS_URL", "")
    assert cache.Cache().enabled is False
```

- [ ] **Step 2: Implement `generator/src/cache.py`**

```python
"""Tiny cache wrapper. v1 = no-op (REDIS_URL empty). v2 = real Redis."""
from typing import Optional

from . import config


class Cache:
    def __init__(self):
        self.enabled = bool(config.REDIS_URL)
        self._client = None
        if self.enabled:
            import redis  # local import so v1 doesn't require redis in runtime path
            self._client = redis.from_url(config.REDIS_URL, decode_responses=True)

    def get(self, key: str) -> Optional[str]:
        if not self.enabled:
            return None
        try:
            return self._client.get(key)
        except Exception:
            return None

    def set(self, key: str, value: str, ttl_seconds: int) -> None:
        if not self.enabled:
            return
        try:
            self._client.setex(key, ttl_seconds, value)
        except Exception:
            pass

    def delete(self, *keys: str) -> None:
        if not self.enabled or not keys:
            return
        try:
            self._client.delete(*keys)
        except Exception:
            pass
```

- [ ] **Step 3: Run tests — pass.** Commit:

```bash
git add generator/src/cache.py generator/tests/test_cache.py
git commit -m "feat(generator): add no-op cache wrapper (enables Redis later via env)"
```

---

### Task 2.4: Generator `placeholder.py` — three SVG variants

**Files:**
- Create: `generator/src/placeholder.py`
- Create: `generator/tests/test_placeholder.py`

- [ ] **Step 1: Write failing tests**

```python
from src import placeholder


def test_building_contains_username_and_svg_tag():
    svg = placeholder.render("building", "alice", theme="dark")
    assert svg.startswith("<svg") and "</svg>" in svg
    assert "alice" in svg
    assert "Building" in svg or "building" in svg.lower()


def test_rate_limited_variant():
    svg = placeholder.render("rate_limited", "alice", theme="dark")
    assert "tomorrow" in svg.lower() or "try again" in svg.lower()


def test_not_found_variant():
    svg = placeholder.render("not_found", "ghost", theme="dark")
    assert "ghost" in svg
    assert "doesn't exist" in svg or "not found" in svg.lower()


def test_unknown_variant_raises():
    import pytest
    with pytest.raises(ValueError):
        placeholder.render("bogus", "alice", theme="dark")
```

- [ ] **Step 2: Implement `generator/src/placeholder.py`**

```python
"""Placeholder SVG renderer — three variants for unknown / rate-limited / not-found users.

Uses the same card wrapper + theme system as real widgets so they look consistent.
"""
from .themes.themes import get_theme
from .utils.svg_helpers import card_wrapper

_MESSAGES = {
    "building":      ("Building @{u}'s widget…", "This usually takes under a minute."),
    "rate_limited":  ("Too many new users today",  "Try again tomorrow."),
    "not_found":     ("GitHub user @{u} doesn't exist", "Check the spelling of the username."),
}


def render(variant: str, username: str, theme: str = "dark") -> str:
    if variant not in _MESSAGES:
        raise ValueError(f"unknown placeholder variant: {variant}")
    title_tpl, subtitle = _MESSAGES[variant]
    title = title_tpl.format(u=username)
    palette = get_theme(theme)

    body = f"""
  <text x="24" y="56" font-family="-apple-system,Segoe UI,sans-serif" font-size="18"
        font-weight="600" fill="{palette.title_color}">{_esc(title)}</text>
  <text x="24" y="82" font-family="-apple-system,Segoe UI,sans-serif" font-size="13"
        fill="{palette.text_color}">{_esc(subtitle)}</text>
"""
    return card_wrapper(body=body, width=400, height=120, theme_name=theme)


def _esc(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;")
             .replace(">", "&gt;").replace('"', "&quot;"))
```

Note: if `themes.get_theme` or `card_wrapper` have different signatures in the moved code, adjust accordingly — read `generator/src/themes/themes.py` and `generator/src/utils/svg_helpers.py` first and match the actual API.

- [ ] **Step 3: Run tests — pass.** Commit:

```bash
git add generator/src/placeholder.py generator/tests/test_placeholder.py
git commit -m "feat(generator): add three placeholder SVG variants"
```

---

### Task 2.5: Generator `fetcher_client.py` — HTTP client to fetcher service

**Files:**
- Create: `generator/src/fetcher_client.py`
- Create: `generator/tests/test_fetcher_client.py`

Rationale: the spec says "fetcher HTTP client inline" — but both `api.py` and `worker.py` need it, and worker should not import Flask. Keeping it as its own 40-line module is the cleanest resolution; it's not a new service, just a DRY helper.

- [ ] **Step 1: Tests**

```python
import responses
import pytest
from src import fetcher_client as fc


@pytest.fixture(autouse=True)
def cfg(monkeypatch):
    monkeypatch.setattr(fc.config, "FETCHER_URL", "http://fetcher:5001")
    monkeypatch.setattr(fc.config, "FETCHER_INTERNAL_TOKEN", "secret")


@responses.activate
def test_get_data_returns_payload_and_hash():
    responses.add(
        responses.GET, "http://fetcher:5001/data/alice",
        json={"data": {"user": {"login": "alice"}}, "payload_hash": "abc"},
        status=200,
    )
    result = fc.get_data("alice")
    assert result["payload_hash"] == "abc"
    assert result["data"]["user"]["login"] == "alice"


@responses.activate
def test_get_data_sends_auth_header():
    responses.add(responses.GET, "http://fetcher:5001/data/alice",
                  json={"data": {}, "payload_hash": "h"}, status=200)
    fc.get_data("alice")
    assert responses.calls[0].request.headers["X-Internal-Token"] == "secret"


@responses.activate
def test_force_fetch():
    responses.add(responses.POST, "http://fetcher:5001/fetch",
                  json={"stored": True, "payload_hash": "new", "changed": True}, status=200)
    r = fc.force_fetch("alice")
    assert r["changed"] is True
```

- [ ] **Step 2: Implement `generator/src/fetcher_client.py`**

```python
"""HTTP client to the fetcher service. Used by api.py, worker.py, cron.py."""
import requests

from . import config


def _headers() -> dict:
    return {"X-Internal-Token": config.FETCHER_INTERNAL_TOKEN}


def get_data(username: str) -> dict:
    r = requests.get(f"{config.FETCHER_URL}/data/{username}", headers=_headers(), timeout=30)
    r.raise_for_status()
    return r.json()


def force_fetch(username: str) -> dict:
    r = requests.post(f"{config.FETCHER_URL}/fetch", headers=_headers(),
                      json={"username": username}, timeout=30)
    r.raise_for_status()
    return r.json()
```

- [ ] **Step 3: Run — pass. Commit:**

```bash
git add generator/src/fetcher_client.py generator/tests/test_fetcher_client.py
git commit -m "feat(generator): add typed HTTP client to the fetcher service"
```

---

## Phase 3 — Generator API, Worker, Cron, Integration

### Task 3.1: Generator `worker.py` — build worker loop

**Files:**
- Create: `generator/src/worker.py`
- Create: `generator/tests/test_worker.py`

- [ ] **Step 1: Tests**

```python
import os, tempfile, pytest
from unittest.mock import patch, MagicMock
from src import db as dbmod
from src import worker


@pytest.fixture
def tmp_dbs(monkeypatch):
    with tempfile.TemporaryDirectory() as d:
        monkeypatch.setattr(dbmod, "SETTINGS_DB_PATH", os.path.join(d, "s.db"))
        monkeypatch.setattr(dbmod, "WIDGETS_DB_PATH", os.path.join(d, "w.db"))
        dbmod.init_dbs()
        yield d


def test_process_one_renders_and_stores_widgets(tmp_dbs):
    dbmod.enroll("alice", {"theme": "dark", "enabled": ["grade"]})
    fake_payload = {"user": {"login": "alice"}, "repos": [], "events": [],
                    "commits": [], "total_commits": 0, "recent_commits": [],
                    "total_prs": 0, "collaborators_data": [], "avatar_b64": ""}
    with patch("src.worker.fetcher_client.get_data",
               return_value={"data": fake_payload, "payload_hash": "h1"}), \
         patch("src.worker._render_widgets",
               return_value={"composite": "<svg>c</svg>", "grade": "<svg>g</svg>"}):
        worker.process_one()
    svg = dbmod.get_current_widget("alice", "composite")
    assert svg == "<svg>c</svg>"


def test_not_found_payload_renders_not_found_placeholder(tmp_dbs):
    dbmod.enroll("ghost", {"theme": "dark"})
    with patch("src.worker.fetcher_client.get_data",
               return_value={"data": {"error": "not_found"}, "payload_hash": "x"}):
        worker.process_one()
    svg = dbmod.get_current_widget("ghost", "composite")
    assert svg and "ghost" in svg


def test_worker_retries_on_fetcher_failure(tmp_dbs):
    dbmod.enroll("alice", {"theme": "dark"})
    with patch("src.worker.fetcher_client.get_data", side_effect=RuntimeError("boom")):
        worker.process_one()
    # Job should have been re-queued with an incremented attempt count
    with dbmod._settings_conn() as c:
        row = c.execute("SELECT status, attempts, last_error FROM jobs WHERE username='alice'").fetchone()
    assert row["status"] == "pending"
    assert row["attempts"] == 1
    assert "boom" in row["last_error"]


def test_worker_marks_failed_after_max_attempts(tmp_dbs):
    dbmod.enroll("alice", {"theme": "dark"})
    with patch("src.worker.fetcher_client.get_data", side_effect=RuntimeError("boom")):
        for _ in range(4):
            worker.process_one()
    with dbmod._settings_conn() as c:
        row = c.execute("SELECT status, attempts FROM jobs WHERE username='alice'").fetchone()
    assert row["status"] == "failed"
    assert row["attempts"] >= 3
```

- [ ] **Step 2: Implement `generator/src/worker.py`**

```python
"""Build worker. Pulls pending jobs and renders widgets.

Run as its own container: CMD python -m src.worker
"""
import logging
import time
from typing import Optional

from . import cache, config, db, fetcher_client, placeholder, processor
from .widgets import compose_widget

log = logging.getLogger("generator.worker")
MAX_ATTEMPTS = 3


def _render_widgets(username: str, payload: dict, settings: dict) -> dict[str, str]:
    """Wrap the existing processor pipeline."""
    enabled = settings.get("enabled") or config.ENABLED_WIDGETS
    order = settings.get("widget_order") or config.WIDGET_ORDER
    theme = settings.get("theme", "dark")
    widgets = processor.generate_widgets_from_github(
        payload,
        theme=theme,
        custom_tags=settings.get("custom_tags"),
        hidden_languages=settings.get("hidden_languages"),
        enabled=enabled,
        widget_settings=settings.get("widget_settings") or {},
    )
    ordered = [w for w in order if w in enabled and w in widgets and widgets[w]]
    composite = compose_widget(
        widgets=widgets, enabled=ordered, theme_name=theme,
        username=username, avatar_b64=payload.get("avatar_b64", ""),
    )
    out = {name: svg for name, svg in widgets.items() if svg}
    out["composite"] = composite
    return out


def process_one() -> bool:
    """Process one pending job. Returns True if a job was handled."""
    job = db.claim_next_job()
    if job is None:
        return False
    username = job["username"]
    try:
        result = fetcher_client.get_data(username)
        payload = result.get("data") or {}
        if payload.get("error") == "not_found":
            svg = placeholder.render("not_found", username, theme="dark")
            db.put_widgets(username, "not_found", {"composite": svg})
            db.complete_job(job["id"])
            log.info("not_found marker persisted for %s", username)
            return True

        settings_row = db.get_settings(username)
        if settings_row is None:
            db.fail_job(job["id"], "settings missing", retry=False)
            return True

        widgets = _render_widgets(username, payload, settings_row["settings"])
        db.put_widgets(username, settings_row["settings_hash"], widgets)
        db.set_last_fetcher_hash(username, result.get("payload_hash", ""))
        db.lru_trim(username, config.WIDGET_LRU_PER_USER)
        c = cache.Cache()
        c.delete(f"widget:composite:{username}", *[f"widget:{n}:{username}" for n in widgets])
        db.complete_job(job["id"])
        log.info("built widgets for %s", username)
        return True
    except Exception as e:
        retry = job.get("attempts", 0) < MAX_ATTEMPTS
        db.fail_job(job["id"], str(e)[:500], retry=retry)
        log.warning("build failed for %s (retry=%s): %s", username, retry, e)
        return True


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    db.init_dbs()
    while True:
        db.reclaim_stuck_jobs(older_than_minutes=10)
        if not process_one():
            time.sleep(0.5)


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Run tests — pass. Commit:**

```bash
git add generator/src/worker.py generator/tests/test_worker.py
git commit -m "feat(generator): add build worker with retries and placeholder fallback"
```

---

### Task 3.2: Generator `api.py` — Flask routes + SPA static + auth stub

**Files:**
- Create: `generator/src/api.py`
- Create: `generator/tests/test_api.py`

- [ ] **Step 1: Tests**

```python
import os, tempfile, pytest
from unittest.mock import patch
from src import db as dbmod
from src import api as apimod


@pytest.fixture
def client(monkeypatch):
    with tempfile.TemporaryDirectory() as d:
        monkeypatch.setattr(dbmod, "SETTINGS_DB_PATH", os.path.join(d, "s.db"))
        monkeypatch.setattr(dbmod, "WIDGETS_DB_PATH", os.path.join(d, "w.db"))
        dbmod.init_dbs()
        app = apimod.app
        app.config["TESTING"] = True
        with app.test_client() as c:
            yield c


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.get_json()["service"] == "generator"


def test_get_unknown_user_auto_enrolls_and_returns_placeholder(client):
    r = client.get("/api/alice")
    assert r.status_code == 200
    assert r.headers["X-Widget-Status"] == "building"
    assert "Building" in r.data.decode()
    assert dbmod.get_settings("alice") is not None


def test_rate_limit_returns_rate_limited_placeholder(client, monkeypatch):
    monkeypatch.setattr(apimod.config, "ENROLLMENT_DAILY_CAP", 1)
    client.get("/api/alice")  # uses the one slot
    r = client.get("/api/bob")
    assert r.headers["X-Widget-Status"] == "rate_limited"


def test_enrolled_user_with_built_widget_returns_ready(client):
    dbmod.enroll("alice", {"theme": "dark"})
    dbmod.put_widgets("alice", "h1", {"composite": "<svg>ready</svg>"})
    # Force settings_hash to match
    with dbmod._settings_conn() as c:
        c.execute("UPDATE users SET settings_hash='h1' WHERE username='alice'")
        c.commit()
    r = client.get("/api/alice")
    assert r.status_code == 200
    assert r.headers["X-Widget-Status"] == "ready"
    assert b"ready" in r.data


def test_settings_patch_enqueues_rebuild(client):
    dbmod.enroll("alice", {"theme": "dark"})
    r = client.patch("/api/alice/settings", json={"theme": "light"})
    assert r.status_code == 200
    assert dbmod.get_settings("alice")["settings"]["theme"] == "light"


def test_refresh_is_one_shot(client):
    dbmod.enroll("alice", {"theme": "dark"})
    with patch("src.api.fetcher_client.force_fetch", return_value={"changed": True, "payload_hash": "x", "stored": True}):
        r1 = client.post("/api/alice/refresh")
        assert r1.status_code == 200
        r2 = client.post("/api/alice/refresh")
        assert r2.status_code == 409


def test_not_found_status_header(client):
    dbmod.enroll("ghost", {"theme": "dark"})
    dbmod.put_widgets("ghost", "not_found", {"composite": "<svg>404</svg>"})
    with dbmod._settings_conn() as c:
        c.execute("UPDATE users SET settings_hash='not_found' WHERE username='ghost'")
        c.commit()
    r = client.get("/api/ghost")
    assert r.headers["X-Widget-Status"] == "not_found"
```

- [ ] **Step 2: Implement `generator/src/api.py`**

```python
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


# ---- auth stub (v1: no-op; swap to real OAuth later) ----

def require_auth(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        # v1: honor system — no check. Future: verify Authorization header.
        return fn(*args, **kwargs)
    return wrapper


# ---- SPA ----

@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def spa(path: str):
    # Reserve /api/* for API; everything else serves the SPA.
    if path.startswith("api/"):
        return jsonify({"error": "not found"}), 404
    full = os.path.join(_STATIC_DIR, path) if path else os.path.join(_STATIC_DIR, "index.html")
    if path and os.path.isfile(full):
        return send_from_directory(_STATIC_DIR, path)
    index = os.path.join(_STATIC_DIR, "index.html")
    if os.path.isfile(index):
        return send_from_directory(_STATIC_DIR, "index.html")
    return jsonify({"error": "frontend not built"}), 503


# ---- API ----

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

    # Unknown user -> try to enroll
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

    # Detect "not_found" widget stashed by the worker
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
```

- [ ] **Step 3: Run tests — pass. Commit:**

```bash
git add generator/src/api.py generator/tests/test_api.py
git commit -m "feat(generator): add Flask API with SPA static, auth stub, rate limit"
```

---

### Task 3.3: Generator `cron.py` — poll fetcher, enqueue rebuilds

**Files:**
- Create: `generator/src/cron.py`
- Create: `generator/tests/test_cron.py`

- [ ] **Step 1: Tests**

```python
import os, tempfile, pytest
from unittest.mock import patch
from src import db as dbmod
from src import cron as cronmod


@pytest.fixture
def tmp_dbs(monkeypatch):
    with tempfile.TemporaryDirectory() as d:
        monkeypatch.setattr(dbmod, "SETTINGS_DB_PATH", os.path.join(d, "s.db"))
        monkeypatch.setattr(dbmod, "WIDGETS_DB_PATH", os.path.join(d, "w.db"))
        dbmod.init_dbs()
        yield


def test_tick_enqueues_build_when_hash_changed(tmp_dbs):
    dbmod.enroll("alice", {"theme": "dark"})
    dbmod.set_last_fetcher_hash("alice", "old")
    # Clear initial enroll job
    with dbmod._settings_conn() as c:
        c.execute("DELETE FROM jobs")
        c.commit()
    with patch("src.cron.fetcher_client.get_data",
               return_value={"data": {}, "payload_hash": "new"}):
        stats = cronmod.tick()
    assert stats["enqueued"] == 1


def test_tick_skips_when_hash_unchanged(tmp_dbs):
    dbmod.enroll("alice", {"theme": "dark"})
    dbmod.set_last_fetcher_hash("alice", "same")
    with dbmod._settings_conn() as c:
        c.execute("DELETE FROM jobs")
        c.commit()
    with patch("src.cron.fetcher_client.get_data",
               return_value={"data": {}, "payload_hash": "same"}):
        stats = cronmod.tick()
    assert stats["enqueued"] == 0
```

- [ ] **Step 2: Implement `generator/src/cron.py`**

```python
"""Generator cron: poll fetcher for payload-hash changes, enqueue rebuilds.

Run as its own container: CMD python -m src.cron
"""
import logging
import time

from . import config, db, fetcher_client

log = logging.getLogger("generator.cron")


def tick() -> dict:
    enqueued = 0
    failed = 0
    for username in db.list_enrolled():
        try:
            info = db.get_settings(username)
            current = info.get("last_fetcher_payload_hash")
            r = fetcher_client.get_data(username)
            latest = r.get("payload_hash")
            if latest and latest != current:
                db.enqueue_build(username)
                db.set_last_fetcher_hash(username, latest)
                enqueued += 1
        except Exception as e:
            log.warning("poll failed for %s: %s", username, e)
            failed += 1
    return {"enqueued": enqueued, "failed": failed}


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    db.init_dbs()
    interval_s = config.POLL_INTERVAL_MINUTES * 60
    while True:
        try:
            log.info("tick: %s", tick())
        except Exception:
            log.exception("tick failed")
        time.sleep(interval_s)


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Run tests — pass. Commit:**

```bash
git add generator/src/cron.py generator/tests/test_cron.py
git commit -m "feat(generator): add poll cron that enqueues on payload-hash change"
```

---

### Task 3.4: Integration test + generator README

**Files:**
- Create: `generator/tests/integration/test_end_to_end.py`
- Create: `generator/README.md`

- [ ] **Step 1: Integration test**

```python
"""End-to-end: api + worker in-process + mocked fetcher HTTP."""
import os, tempfile, threading, time
import pytest
import responses
from unittest.mock import patch
from src import api as apimod, db as dbmod, worker


@pytest.fixture
def env(monkeypatch):
    with tempfile.TemporaryDirectory() as d:
        monkeypatch.setattr(dbmod, "SETTINGS_DB_PATH", os.path.join(d, "s.db"))
        monkeypatch.setattr(dbmod, "WIDGETS_DB_PATH", os.path.join(d, "w.db"))
        monkeypatch.setattr(apimod.config, "FETCHER_URL", "http://fetcher-mock")
        monkeypatch.setattr(apimod.config, "FETCHER_INTERNAL_TOKEN", "t")
        dbmod.init_dbs()
        yield


@responses.activate
def test_first_request_builds_then_serves_ready(env):
    responses.add(
        responses.GET, "http://fetcher-mock/data/alice",
        json={"data": {"user": {"login": "alice"}, "repos": [], "events": [],
                        "commits": [], "total_commits": 0, "recent_commits": [],
                        "total_prs": 0, "collaborators_data": [], "avatar_b64": ""},
              "payload_hash": "h1"}, status=200,
    )
    client = apimod.app.test_client()

    r1 = client.get("/api/alice")
    assert r1.headers["X-Widget-Status"] == "building"

    # Drain any pending jobs
    for _ in range(5):
        if not worker.process_one():
            break

    r2 = client.get("/api/alice")
    assert r2.headers["X-Widget-Status"] == "ready"
    assert r2.data.startswith(b"<svg") or r2.data.startswith(b"<?xml")
```

- [ ] **Step 2: Run integration test**

Run: `cd generator && pytest tests/integration -v`
Expected: PASS.

- [ ] **Step 3: Write `generator/README.md`**

```markdown
# Generator Service

Serves precomputed SVGs to the public internet. Holds user settings and
the widgets cache. Runs a build worker + cron in the background. Also
serves the React SPA (frontend sources live under `frontend/`).

## Run locally (3 processes)

    cd generator
    pip install -r requirements.txt

    # API
    FETCHER_URL=http://localhost:5001 FETCHER_INTERNAL_TOKEN=dev python -m src.api
    # Build worker
    FETCHER_URL=http://localhost:5001 FETCHER_INTERNAL_TOKEN=dev python -m src.worker
    # Poll cron
    FETCHER_URL=http://localhost:5001 FETCHER_INTERNAL_TOKEN=dev python -m src.cron

## Frontend (dev)

    cd generator/frontend && npm install && npm run dev
    # Vite dev server proxies /api to the Flask app.

## Test

    cd generator && pytest

## Docker

Multi-stage (builds the frontend with node, serves everything from Python):

    docker build -t ghstats-generator .
    docker run --rm -e FETCHER_URL=http://fetcher:5001 -e FETCHER_INTERNAL_TOKEN=dev \
               -p 5002:5002 -v $(pwd)/data:/app/data ghstats-generator
    # Worker: override CMD to ["python","-m","src.worker"]
    # Cron:   override CMD to ["python","-m","src.cron"]

## Endpoints

All API endpoints are under `/api/`. The root and `/assets/*` serve the SPA.

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | /api/health | none | health |
| GET | /api/<u> | none | composite SVG; auto-enrolls unknown users |
| GET | /api/<u>/<w>.svg | none | individual widget SVG |
| POST | /api/enroll | none | explicit enroll (body: {username}) |
| GET | /api/<u>/settings | stub | current settings |
| PATCH | /api/<u>/settings | stub | update settings (enqueues rebuild) |
| POST | /api/<u>/refresh | stub | one-shot re-fetch + rebuild |

Responses carry `X-Widget-Status: ready | building | rate_limited | not_found`.

## Env

See `src/config.py`.
```

- [ ] **Step 4: Commit**

```bash
git add generator/tests/integration/test_end_to_end.py generator/README.md
git commit -m "test(generator): add end-to-end integration test + README"
```

---

## Phase 4 — Edge Service

### Task 4.1: Edge scaffolding + requirements + Dockerfile

**Files:**
- Create: `edge/requirements.txt`, `edge/pytest.ini`, `edge/Dockerfile`
- Create: `edge/src/config.py`

- [ ] **Step 1: `edge/requirements.txt`**

```
flask==3.0.3
flask-caching==2.3.0
flask-compress==1.15
requests==2.32.3
pytest==8.3.3
responses==0.25.3
gunicorn==23.0.0
```

- [ ] **Step 2: `edge/pytest.ini`**

```ini
[pytest]
testpaths = tests
python_files = test_*.py
pythonpath = .
addopts = -ra --strict-markers
```

- [ ] **Step 3: `edge/src/config.py`**

```python
import os

PORT = int(os.getenv("EDGE_PORT", "5003"))
GENERATOR_URL = os.getenv("GENERATOR_URL", "http://localhost:5002")
CACHE_TYPE = os.getenv("CACHE_TYPE", "SimpleCache")
CACHE_REDIS_URL = os.getenv("CACHE_REDIS_URL", "")
CACHE_DEFAULT_TIMEOUT = int(os.getenv("CACHE_DEFAULT_TIMEOUT", "86400"))
CACHE_THRESHOLD = int(os.getenv("CACHE_THRESHOLD", "10000"))
UPSTREAM_TIMEOUT = int(os.getenv("EDGE_UPSTREAM_TIMEOUT", "10"))
```

- [ ] **Step 4: `edge/Dockerfile`**

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY src ./src

EXPOSE 5003
CMD ["gunicorn", "-b", "0.0.0.0:5003", "-w", "2", "src.api:app"]
```

- [ ] **Step 5: Commit**

```bash
git add edge/requirements.txt edge/pytest.ini edge/src/config.py edge/Dockerfile
git commit -m "feat(edge): scaffold config, requirements, Dockerfile"
```

---

### Task 4.2: Edge `cache.py` + `api.py` with Flask-Caching and Flask-Compress

**Files:**
- Create: `edge/src/cache.py`
- Create: `edge/src/api.py`
- Create: `edge/tests/test_api.py`

- [ ] **Step 1: Tests `edge/tests/test_api.py`**

```python
import pytest
import responses
from src import api as apimod


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(apimod.config, "GENERATOR_URL", "http://gen:5002")
    # Reset cache between tests
    apimod.cache_ext.clear()
    apimod.app.config["TESTING"] = True
    with apimod.app.test_client() as c:
        yield c


@responses.activate
def test_miss_then_hit_serves_from_cache(client):
    responses.add(responses.GET, "http://gen:5002/api/alice",
                  body=b"<svg>ready</svg>", status=200,
                  headers={"X-Widget-Status": "ready", "Content-Type": "image/svg+xml"})
    r1 = client.get("/alice")
    assert r1.status_code == 200
    assert r1.data == b"<svg>ready</svg>"
    # second call should not hit origin
    responses.reset()
    r2 = client.get("/alice")
    assert r2.status_code == 200
    assert r2.data == b"<svg>ready</svg>"


@responses.activate
def test_placeholder_not_cached(client):
    responses.add(responses.GET, "http://gen:5002/api/alice",
                  body=b"<svg>building</svg>", status=200,
                  headers={"X-Widget-Status": "building", "Content-Type": "image/svg+xml"})
    r1 = client.get("/alice")
    assert r1.status_code == 200
    # Origin MUST be called again on the second request because building wasn't cached
    r2 = client.get("/alice")
    assert len(responses.calls) == 2


@responses.activate
def test_origin_error_returns_503(client):
    responses.add(responses.GET, "http://gen:5002/api/alice", status=500)
    r = client.get("/alice")
    assert r.status_code == 503


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
```

- [ ] **Step 2: `edge/src/cache.py`**

```python
"""Flask-Caching config. v1 = SimpleCache (in-process). Swap to RedisCache via env."""
from flask_caching import Cache
from . import config


def build_cache(app) -> Cache:
    cfg = {
        "CACHE_TYPE": config.CACHE_TYPE,
        "CACHE_DEFAULT_TIMEOUT": config.CACHE_DEFAULT_TIMEOUT,
        "CACHE_THRESHOLD": config.CACHE_THRESHOLD,
    }
    if config.CACHE_TYPE == "RedisCache" and config.CACHE_REDIS_URL:
        cfg["CACHE_REDIS_URL"] = config.CACHE_REDIS_URL
    c = Cache(config=cfg)
    c.init_app(app)
    return c
```

- [ ] **Step 3: `edge/src/api.py`**

```python
"""Edge service — cache-first SVG proxy in front of the generator."""
import logging
import requests
from flask import Flask, Response, jsonify, request
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
```

- [ ] **Step 4: Run tests — pass**

Run: `cd edge && pytest -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add edge/src/cache.py edge/src/api.py edge/tests/test_api.py
git commit -m "feat(edge): add cache-first SVG proxy with Flask-Caching + Flask-Compress"
```

---

### Task 4.3: Edge README

**Files:**
- Create: `edge/README.md`

- [ ] **Step 1: Write**

```markdown
# Edge Service

Cache-first SVG proxy in front of the generator. Deploy many instances
around the world. No DB of its own; optional Redis for shared cache.

## Run locally

    cd edge
    pip install -r requirements.txt
    GENERATOR_URL=http://localhost:5002 python -m src.api

## Test

    cd edge && pytest

## Docker

    docker build -t ghstats-edge .
    docker run --rm -e GENERATOR_URL=http://host.docker.internal:5002 -p 5003:5003 ghstats-edge

## Endpoints

| Method | Path | Description |
|---|---|---|
| GET | /health | cache type + upstream reachability |
| GET | /<u> | composite SVG (cached on X-Widget-Status: ready) |
| GET | /<u>/<w>.svg | individual widget SVG |

## Env

- `GENERATOR_URL` — origin (required)
- `CACHE_TYPE` — `SimpleCache` (default) or `RedisCache`
- `CACHE_REDIS_URL` — if using RedisCache
- `CACHE_DEFAULT_TIMEOUT` — seconds, default 86400
- `CACHE_THRESHOLD` — max entries (SimpleCache only), default 10000
```

- [ ] **Step 2: Commit**

```bash
git add edge/README.md
git commit -m "docs(edge): add README"
```

---

## Phase 5 — Frontend Migration

### Task 5.1: Move frontend into generator + rename API paths

**Files:**
- Move: `frontend/*` → `generator/frontend/*`
- Modify: any React sources that call the API — change hardcoded paths to `/api/*`

- [ ] **Step 1: Move**

```bash
git mv frontend generator/frontend
```

- [ ] **Step 2: Update React API calls**

```bash
grep -rn "'/enroll\|'/users\|'/settings\|'/generate\|'/health\|'/refresh" generator/frontend/src || echo "clean"
```

Open each result and prepend `/api` to the path. Do the same for any `fetch('http://localhost:5002/...')` — replace with a `VITE_GENERATOR_URL` env var + `/api/<path>`.

- [ ] **Step 3: Add `generator/frontend/.env.example`**

```
VITE_GENERATOR_URL=http://localhost:5002
VITE_EDGE_URL=http://localhost:5003
```

- [ ] **Step 4: Update `vite.config.ts` dev proxy**

In `generator/frontend/vite.config.ts`, add a dev proxy so `/api/*` during `npm run dev` hits the local Flask:

```typescript
// Inside defineConfig({ server: { ... } })
server: {
  proxy: {
    '/api': 'http://localhost:5002',
  },
},
```

- [ ] **Step 5: Verify frontend builds**

```bash
cd generator/frontend && npm install && npm run build
ls -la dist/
```

Expected: `dist/index.html` and `dist/assets/` present.

- [ ] **Step 6: Commit**

```bash
git add generator/frontend/ -A
git commit -m "feat(generator): move frontend into generator + namespace API calls under /api/"
```

---

### Task 5.2: Multi-stage Dockerfile for generator

**Files:**
- Create: `generator/Dockerfile`

- [ ] **Step 1: Write**

```dockerfile
# --- stage 1: build the React SPA ---
FROM node:20-alpine AS frontend-build
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
# VITE_* env vars can be injected at build time via --build-arg
ARG VITE_GENERATOR_URL=""
ARG VITE_EDGE_URL=""
ENV VITE_GENERATOR_URL=$VITE_GENERATOR_URL
ENV VITE_EDGE_URL=$VITE_EDGE_URL
RUN npm run build

# --- stage 2: python runtime ---
FROM python:3.11-slim AS runtime
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY src ./src
RUN mkdir -p /app/src/static /app/data
COPY --from=frontend-build /app/frontend/dist/ /app/src/static/

EXPOSE 5002
ENV GENERATOR_SETTINGS_DB_PATH=/app/data/settings.db
ENV GENERATOR_WIDGETS_DB_PATH=/app/data/widgets.db

# Default is the API. Worker/cron containers override CMD.
CMD ["gunicorn", "-b", "0.0.0.0:5002", "-w", "2", "src.api:app"]
```

- [ ] **Step 2: Verify build succeeds**

```bash
cd generator && docker build -t ghstats-generator-test .
```

Expected: image builds successfully. If frontend build fails because of missing env vars, set them via `--build-arg`.

- [ ] **Step 3: Commit**

```bash
git add generator/Dockerfile
git commit -m "feat(generator): add multi-stage Dockerfile (node build -> python runtime)"
```

---

### Task 5.3: `generator/frontend/README.md`

**Files:**
- Create or overwrite: `generator/frontend/README.md`

- [ ] **Step 1: Write**

```markdown
# Frontend (Vite + React)

Part of the generator service. Sources live here; the production build
is served as static files by the generator's Flask app (at `/`) and
produced by the generator's Dockerfile.

## Dev

    npm install
    VITE_GENERATOR_URL=http://localhost:5002 VITE_EDGE_URL=http://localhost:5003 npm run dev

Vite proxies `/api/*` to the Flask app at :5002.

## Build

    npm run build
    # produces dist/ which is copied into generator/src/static/ by the Docker build
```

- [ ] **Step 2: Commit**

```bash
git add generator/frontend/README.md
git commit -m "docs(frontend): update README for new location + API contract"
```

---

## Phase 6 — Polish

### Task 6.1: Top-level README + CLAUDE.md update

**Files:**
- Modify: `README.md`
- Modify: `CLAUDE.md`

- [ ] **Step 1: Replace `README.md` contents**

```markdown
# github-readme-stats

A monorepo of three independent Python services plus a React frontend,
each self-contained. See each service's README for details.

## Services

| Folder | Port | Responsibility |
|---|---|---|
| [`fetcher/`](./fetcher/README.md) | 5001 | Owns GitHub PAT + `fetcher.db`; cron-refreshes data |
| [`generator/`](./generator/README.md) | 5002 | Settings + widgets DBs, build worker, serves React SPA + `/api/*` |
| [`edge/`](./edge/README.md) | 5003 | Cache-first SVG proxy; deploy globally |

## Design Docs

- Spec: [`docs/superpowers/specs/2026-04-17-production-pipeline-design.md`](docs/superpowers/specs/2026-04-17-production-pipeline-design.md)
- Plan: [`docs/superpowers/plans/2026-04-17-production-pipeline.md`](docs/superpowers/plans/2026-04-17-production-pipeline.md)

## Quick start (local dev, no Docker)

    # 1) fetcher
    (cd fetcher && pip install -r requirements.txt &&
     FETCHER_INTERNAL_TOKEN=dev GITHUB_PAT=<your-pat> python -m src.api) &

    # 2) generator API, worker, cron (three processes)
    cd generator && pip install -r requirements.txt
    FETCHER_URL=http://localhost:5001 FETCHER_INTERNAL_TOKEN=dev python -m src.api &
    FETCHER_URL=http://localhost:5001 FETCHER_INTERNAL_TOKEN=dev python -m src.worker &
    FETCHER_URL=http://localhost:5001 FETCHER_INTERNAL_TOKEN=dev python -m src.cron &

    # 3) edge
    (cd ../edge && pip install -r requirements.txt &&
     GENERATOR_URL=http://localhost:5002 python -m src.api) &

    # 4) frontend (dev server)
    cd ../generator/frontend && npm install && npm run dev

Test everything:

    (cd fetcher && pytest) && (cd generator && pytest) && (cd edge && pytest)
```

- [ ] **Step 2: Update `CLAUDE.md`**

Replace its Commands + Architecture sections with a brief pointer to the new layout and per-service READMEs. Leave configuration + conventions sections intact but update paths (e.g., `src/config.py` → `generator/src/config.py`).

- [ ] **Step 3: Commit**

```bash
git add README.md CLAUDE.md
git commit -m "docs: top-level README + CLAUDE.md reflect three-service layout"
```

---

### Task 6.2: Remove stale top-level artifacts + final verification

**Files:**
- Delete: `CONFIGURATION.md`, `TAG_CUSTOMIZATION.md` (if kept, move their content into `generator/README.md`; if not needed, drop)
- Verify: every service's tests pass end-to-end

- [ ] **Step 1: Decide stale-docs disposition**

Inspect `CONFIGURATION.md` and `TAG_CUSTOMIZATION.md`. Either:
- Move their useful sections into `generator/README.md` under an "Advanced config" heading, OR
- `git rm` them if their content is covered in the service READMEs.

- [ ] **Step 2: Full test sweep**

```bash
(cd fetcher && pytest -q) && (cd generator && pytest -q) && (cd edge && pytest -q)
```

Expected: all green. If anything fails, fix before committing.

- [ ] **Step 3: Docker build sweep**

```bash
docker build ./fetcher -t ghstats-fetcher-test
docker build ./generator -t ghstats-generator-test
docker build ./edge -t ghstats-edge-test
```

All three must succeed independently (no shared build context).

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "chore: final cleanup — remove stale docs, verify three-service build"
```

---

## Completion Criteria

- [ ] All three services build independently via `docker build ./<service>`.
- [ ] All three services pass their own `pytest`.
- [ ] `GET http://<edge>/<username>` returns a placeholder on unknown user; a real SVG after the build worker runs.
- [ ] `PATCH /api/<u>/settings` on the generator enqueues a rebuild and the edge serves updated SVG after cache expiry (or via future Redis invalidation).
- [ ] `POST /api/<u>/refresh` works once, returns 409 the second time.
- [ ] Retired files (`run.py`, old `src/*_api.py`, root `widget_*.svg`, `data/ghstats.db`, `REPORT.md`, `CHANGELOG.md`) are gone from the working tree.
- [ ] Frontend builds and is served by the generator container at `/`.
- [ ] `REDIS_URL` unset → every `cache.Cache()` call is a no-op; setting it later enables real caching with no code changes.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-04-17-production-pipeline.md`. Two execution options:

**1. Subagent-Driven (recommended)** — dispatch a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** — execute tasks in this session using `executing-plans`, batch execution with checkpoints.

Which approach?
