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
