import os
import uuid
import random
import string
import json
from datetime import datetime, timezone

# These are set by the middleware at startup so the Matrix homeserver
# can find its database without Frappe's site initialization.
_default_site_dir = None
_bench_sites_path = None


def generate_id(prefix="", length=16):
    """Generate a Matrix-style ID: $random:localhost or !random:localhost"""
    rand = "".join(random.choices(string.ascii_lowercase + string.digits, k=length))
    return f"{prefix}{rand}:localhost"


def generate_event_id():
    return generate_id("$", length=48)


def generate_room_id():
    return generate_id("!", length=18)


def generate_user_id(username):
    return f"@{username}:localhost"


def generate_token():
    return str(uuid.uuid4()).replace("-", "")


def utcnow():
    return int(datetime.now(timezone.utc).timestamp() * 1000)


def get_matrix_db_path(site_path=None):
    """Returns the path to the Matrix SQLite database."""
    if site_path:
        return os.path.join(site_path, "matrix_homeserver.db")

    # First try using the global defaults set by the middleware
    if _default_site_dir and _bench_sites_path:
        return os.path.join(_bench_sites_path, _default_site_dir, "matrix_homeserver.db")

    # Fall back to Frappe's site path (only available after Frappe init)
    try:
        import frappe
        site_path = frappe.get_site_path()
        return os.path.join(site_path, "matrix_homeserver.db")
    except Exception:
        # Last resort: try to find the site directory
        bench_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        sites_path = os.path.join(bench_path, "sites")
        if os.path.exists(sites_path):
            for item in sorted(os.listdir(sites_path)):
                item_path = os.path.join(sites_path, item)
                if os.path.isdir(item_path) and not item.startswith(".") and item not in ("assets", "languages"):
                    return os.path.join(item_path, "matrix_homeserver.db")
        return os.path.join(os.path.expanduser("~"), ".vynce", "matrix_homeserver.db")


def get_schema_sql():
    """Returns the SQL to create all Matrix tables."""
    return """
    CREATE TABLE IF NOT EXISTS users (
        user_id TEXT PRIMARY KEY,
        password_hash TEXT NOT NULL,
        display_name TEXT DEFAULT '',
        avatar_url TEXT DEFAULT '',
        created_ts INTEGER NOT NULL
    );

    CREATE TABLE IF NOT EXISTS access_tokens (
        token TEXT PRIMARY KEY,
        user_id TEXT NOT NULL REFERENCES users(user_id),
        device_id TEXT DEFAULT '',
        created_ts INTEGER NOT NULL
    );

    CREATE INDEX IF NOT EXISTS idx_tokens_user ON access_tokens(user_id);

    CREATE TABLE IF NOT EXISTS rooms (
        room_id TEXT PRIMARY KEY,
        creator TEXT NOT NULL,
        name TEXT DEFAULT '',
        topic TEXT DEFAULT '',
        version INTEGER DEFAULT 1,
        created_ts INTEGER NOT NULL
    );

    CREATE TABLE IF NOT EXISTS room_members (
        room_id TEXT NOT NULL REFERENCES rooms(room_id),
        user_id TEXT NOT NULL REFERENCES users(user_id),
        membership TEXT NOT NULL DEFAULT 'join',
        event_id TEXT,
        PRIMARY KEY (room_id, user_id)
    );

    CREATE INDEX IF NOT EXISTS idx_members_user ON room_members(user_id);

    CREATE TABLE IF NOT EXISTS events (
        event_id TEXT PRIMARY KEY,
        room_id TEXT NOT NULL REFERENCES rooms(room_id),
        sender TEXT NOT NULL,
        type TEXT NOT NULL,
        state_key TEXT,
        content_json TEXT NOT NULL,
        origin_server_ts INTEGER NOT NULL,
        stream_ordering INTEGER NOT NULL
    );

    CREATE INDEX IF NOT EXISTS idx_events_room_ts ON events(room_id, stream_ordering);
    CREATE INDEX IF NOT EXISTS idx_events_stream ON events(stream_ordering);

    CREATE TABLE IF NOT EXISTS stream_positions (
        key TEXT PRIMARY KEY,
        value INTEGER NOT NULL
    );

    INSERT OR IGNORE INTO stream_positions (key, value) VALUES ('next_stream_id', 1);
    """
