"""SQLite repository: the only communication channel between fetcher and generator.

Stores each user's fetched GitHub payload as a JSON blob in a single table.
The generator reads from here; the fetcher writes to here. Neither imports the
other.
"""

import json
import os
import sqlite3
from datetime import datetime
from typing import Optional

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DB_PATH = os.environ.get(
    "GHSTATS_DB_PATH",
    os.path.join(_PROJECT_ROOT, "data", "ghstats.db"),
)

DUMMY_USERNAME = "__dummy__"

# Fields the generator considers load-bearing. If any is missing from a row,
# the generator treats the row as unusable and falls back to the dummy user.
REQUIRED_FIELDS = (
    "user",
    "repos",
    "events",
    "commits",
    "total_commits",
    "recent_commits",
    "total_prs",
    "collaborators_data",
    "avatar_b64",
)

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS users (
    username   TEXT PRIMARY KEY,
    data_json  TEXT NOT NULL,
    is_dummy   INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL
);
"""


def _connect() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Create the schema and seed the dummy user if missing."""
    with _connect() as conn:
        conn.executescript(SCHEMA_SQL)
        conn.commit()
        seed_dummy_user(conn=conn)


def upsert_user(username: str, data: dict, conn: Optional[sqlite3.Connection] = None) -> None:
    payload = json.dumps(data)
    now = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    sql = """
        INSERT INTO users (username, data_json, is_dummy, updated_at)
        VALUES (?, ?, 0, ?)
        ON CONFLICT(username) DO UPDATE SET
            data_json = excluded.data_json,
            is_dummy = 0,
            updated_at = excluded.updated_at
    """
    if conn is None:
        with _connect() as c:
            c.execute(sql, (username, payload, now))
            c.commit()
    else:
        conn.execute(sql, (username, payload, now))
        conn.commit()


def get_user(username: str) -> Optional[dict]:
    """Return the stored GitHub-data dict for a user, or None if not present."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT data_json FROM users WHERE username = ?",
            (username,),
        ).fetchone()
    if row is None:
        return None
    return json.loads(row["data_json"])


def delete_user(username: str) -> bool:
    if username == DUMMY_USERNAME:
        return False
    with _connect() as conn:
        cur = conn.execute("DELETE FROM users WHERE username = ?", (username,))
        conn.commit()
        return cur.rowcount > 0


def list_users() -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT username, is_dummy, updated_at FROM users ORDER BY username"
        ).fetchall()
    return [dict(r) for r in rows]


def seed_dummy_user(conn: Optional[sqlite3.Connection] = None) -> None:
    """Insert (or replace) the __dummy__ row using an explicit hand-written payload.

    This is the fallback the generator uses whenever a requested user is missing
    or has incomplete data. Kept deliberately plausible so every widget has
    something to render.
    """
    from .dummy_seed import DUMMY_PAYLOAD

    payload = json.dumps(DUMMY_PAYLOAD)
    now = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    sql = """
        INSERT INTO users (username, data_json, is_dummy, updated_at)
        VALUES (?, ?, 1, ?)
        ON CONFLICT(username) DO UPDATE SET
            data_json = excluded.data_json,
            is_dummy = 1,
            updated_at = excluded.updated_at
    """
    if conn is None:
        with _connect() as c:
            c.execute(sql, (DUMMY_USERNAME, payload, now))
            c.commit()
    else:
        conn.execute(sql, (DUMMY_USERNAME, payload, now))
        conn.commit()
