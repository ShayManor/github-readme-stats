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
        conn.commit()
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
