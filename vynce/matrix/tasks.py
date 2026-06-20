import frappe
from .storage import get_connection, init_db


def init():
    """Ensure Matrix DB is initialized. Called from various hooks."""
    init_db()


def heartbeat():
    """Periodic task: update Matrix Settings with stats."""
    try:
        conn = get_connection()

        user_count = conn.execute("SELECT COUNT(*) as c FROM users").fetchone()["c"]
        room_count = conn.execute("SELECT COUNT(*) as c FROM rooms").fetchone()["c"]
        event_count = conn.execute("SELECT COUNT(*) as c FROM events").fetchone()["c"]

        if frappe.db.exists("Matrix Settings", "Matrix Settings"):
            frappe.db.set_value("Matrix Settings", "Matrix Settings", {
                "total_users": user_count,
                "total_rooms": room_count,
                "total_events": event_count,
                "homeserver_status": "Running",
            })
    except Exception as e:
        frappe.logger().error(f"Matrix heartbeat error: {e}")
