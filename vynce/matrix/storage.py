import sqlite3
import os
import json
import threading
from .utils import get_matrix_db_path, get_schema_sql

_local = threading.local()


def get_connection():
    """Get thread-local SQLite connection."""
    db_path = get_matrix_db_path()
    if not hasattr(_local, "conn") or _local.conn is None:
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        _local.conn = sqlite3.connect(db_path)
        _local.conn.row_factory = sqlite3.Row
        _local.conn.execute("PRAGMA journal_mode=WAL")
        _local.conn.execute("PRAGMA foreign_keys=ON")
    return _local.conn


def init_db():
    """Create tables if they don't exist."""
    conn = get_connection()
    conn.executescript(get_schema_sql())
    conn.commit()


# ─── User Operations ───

def create_user(user_id, password_hash):
    conn = get_connection()
    conn.execute(
        "INSERT OR IGNORE INTO users (user_id, password_hash, created_ts) VALUES (?, ?, ?)",
        (user_id, password_hash, __import__("time").time() * 1000),
    )
    conn.commit()
    return conn.total_changes > 0


def get_user(user_id):
    conn = get_connection()
    row = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
    if row:
        return dict(row)


def user_exists(user_id):
    conn = get_connection()
    return conn.execute("SELECT 1 FROM users WHERE user_id = ?", (user_id,)).fetchone() is not None


# ─── Token Operations ───

def create_token(token, user_id, device_id=""):
    conn = get_connection()
    conn.execute(
        "INSERT OR IGNORE INTO access_tokens (token, user_id, device_id, created_ts) VALUES (?, ?, ?, ?)",
        (token, user_id, device_id, __import__("time").time() * 1000),
    )
    conn.commit()


def get_token_owner(token):
    conn = get_connection()
    row = conn.execute("SELECT user_id FROM access_tokens WHERE token = ?", (token,)).fetchone()
    return row["user_id"] if row else None


# ─── Room Operations ───

def create_room(room_id, creator, name="", topic=""):
    conn = get_connection()
    ts = __import__("time").time() * 1000
    conn.execute(
        "INSERT INTO rooms (room_id, creator, name, topic, created_ts) VALUES (?, ?, ?, ?, ?)",
        (room_id, creator, name, topic, ts),
    )
    conn.commit()


def get_room(room_id):
    conn = get_connection()
    row = conn.execute("SELECT * FROM rooms WHERE room_id = ?", (room_id,)).fetchone()
    return dict(row) if row else None


def get_user_rooms(user_id):
    conn = get_connection()
    rows = conn.execute(
        "SELECT r.* FROM rooms r JOIN room_members m ON r.room_id = m.room_id WHERE m.user_id = ? AND m.membership = 'join'",
        (user_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def add_member(room_id, user_id, membership="join", event_id=None):
    conn = get_connection()
    conn.execute(
        "INSERT OR REPLACE INTO room_members (room_id, user_id, membership, event_id) VALUES (?, ?, ?, ?)",
        (room_id, user_id, membership, event_id),
    )
    conn.commit()


def is_member(room_id, user_id):
    conn = get_connection()
    row = conn.execute(
        "SELECT 1 FROM room_members WHERE room_id = ? AND user_id = ? AND membership = 'join'",
        (room_id, user_id),
    ).fetchone()
    return row is not None


def get_room_members(room_id):
    conn = get_connection()
    rows = conn.execute(
        "SELECT user_id FROM room_members WHERE room_id = ? AND membership = 'join'",
        (room_id,),
    ).fetchall()
    return [r["user_id"] for r in rows]


# ─── Event Operations ───

def get_next_stream_id():
    conn = get_connection()
    cur = conn.execute("UPDATE stream_positions SET value = value + 1 WHERE key = 'next_stream_id' RETURNING value")
    row = cur.fetchone()
    conn.commit()
    return row["value"] if row else None


def get_latest_stream_position():
    conn = get_connection()
    row = conn.execute("SELECT value FROM stream_positions WHERE key = 'next_stream_id'").fetchone()
    return (row["value"] or 1) - 1 if row else 0


def insert_event(event_id, room_id, sender, event_type, content, state_key=None):
    stream_id = get_next_stream_id()
    if stream_id is None:
        raise RuntimeError("Failed to get stream ID")
    ts = __import__("time").time() * 1000
    conn = get_connection()
    conn.execute(
        "INSERT INTO events (event_id, room_id, sender, type, state_key, content_json, origin_server_ts, stream_ordering) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (event_id, room_id, sender, event_type, state_key, json.dumps(content), ts, stream_id),
    )
    conn.commit()
    return event_id, stream_id


def get_events_since(room_id, from_stream, limit=50):
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM events WHERE room_id = ? AND stream_ordering > ? ORDER BY stream_ordering ASC LIMIT ?",
        (room_id, from_stream, limit),
    ).fetchall()
    return [dict(r) for r in rows]


def get_room_events(room_id, from_token=None, to_token=None, limit=50, direction="b"):
    conn = get_connection()
    if direction == "b":
        if from_token:
            rows = conn.execute(
                "SELECT * FROM events WHERE room_id = ? AND stream_ordering < ? ORDER BY stream_ordering DESC LIMIT ?",
                (room_id, int(from_token), limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM events WHERE room_id = ? ORDER BY stream_ordering DESC LIMIT ?",
                (room_id, limit),
            ).fetchall()
    else:
        if from_token:
            rows = conn.execute(
                "SELECT * FROM events WHERE room_id = ? AND stream_ordering > ? ORDER BY stream_ordering ASC LIMIT ?",
                (room_id, int(from_token), limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM events WHERE room_id = ? ORDER BY stream_ordering ASC LIMIT ?",
                (room_id, limit),
            ).fetchall()
    return [dict(r) for r in rows]
