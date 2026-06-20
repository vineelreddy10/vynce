"""Frappe whitelisted API endpoints for Matrix operations.

These are called by the React frontend (vynce-mobile) for app-specific
Matrix management. The actual Matrix C2S API is handled directly by
Synapse at /_matrix/*.
"""

import frappe
from frappe import _
from .synapse_client import SynapseClient, SynapseError

SYNAPSE_NOT_READY = {"status": "Starting", "detail": "Synapse is still starting up"}


def _get_client():
    """Get a SynapseClient instance or None if not ready."""
    try:
        return SynapseClient()
    except Exception:
        return None


def _is_ready():
    """Quick check if Synapse is up."""
    try:
        import requests
        from .synapse_config import SYNAPSE_PORT
        resp = requests.get(f"http://127.0.0.1:{SYNAPSE_PORT}/_matrix/client/versions", timeout=2)
        return resp.status_code == 200
    except Exception:
        return False


# ─── Status ───


@frappe.whitelist(allow_guest=True)
def get_status():
    """Get Matrix homeserver status and stats."""
    if not _is_ready():
        return SYNAPSE_NOT_READY

    try:
        client = _get_client()
        if not client:
            return SYNAPSE_NOT_READY

        versions = client.get_versions()
        users_resp = client.get_users(limit=0)
        rooms_resp = client.get_rooms(limit=0)

        return {
            "status": "Running",
            "users": users_resp.get("total", 0),
            "rooms": rooms_resp.get("total", 0),
            "version": versions.get("versions", ["unknown"])[0],
            "server_name": "vynce.app",
        }
    except Exception as e:
        return {"status": "Error", "error": str(e)}


# ─── User Management ───


@frappe.whitelist(allow_guest=True)
def create_test_user():
    """Create a test Matrix user via Synapse Admin API."""
    import string
    import secrets

    username = "testuser_" + "".join(secrets.choice(string.ascii_lowercase) for _ in range(6))
    password = "test123"

    try:
        client = _get_client()
        if not client:
            frappe.throw("Synapse not ready")

        result = client.create_user(username, password, displayname=f"Test User {username}")
        user_id = result.get("name", f"@{username}:vynce.app")

        return {
            "username": username,
            "user_id": user_id,
            "password": password,
        }
    except SynapseError as e:
        frappe.throw(f"Synapse error: {e.body}")
    except Exception as e:
        frappe.throw(f"Failed to create user: {e}")


# ─── Room Management ───


@frappe.whitelist(allow_guest=True)
def create_test_room(name: str = "Test Room"):
    """Create a test room with two users via Synapse Admin API."""
    import string
    import secrets

    try:
        client = _get_client()
        if not client:
            frappe.throw("Synapse not ready")

        users = []
        for i in range(2):
            uname = "testroom_" + "".join(secrets.choice(string.ascii_lowercase) for _ in range(4))
            result = client.create_user(uname, "test123", displayname=f"Room User {i}")
            user_id = result.get("name", f"@{uname}:vynce.app")
            users.append({"username": uname, "user_id": user_id})

        # Create room with user 1 as creator, inviting user 2
        room = client.create_room(
            name=name,
            creator=users[0]["user_id"],
            invite=[users[1]["user_id"]],
            is_direct=False,
        )
        room_id = room.get("room_id", "")

        # Login as user 1 to send a welcome message
        login_result = client.login(users[0]["username"], "test123")
        token = login_result.get("access_token", "")

        if token:
            client.send_message(room_id, token, {
                "msgtype": "m.text",
                "body": f"Welcome to {name}! 👋",
            })

        return {
            "room_id": room_id,
            "name": name,
            "users": [u["username"] for u in users],
        }
    except SynapseError as e:
        frappe.throw(f"Synapse error: {e.body}")
    except Exception as e:
        frappe.throw(f"Failed to create room: {e}")


@frappe.whitelist(allow_guest=True)
def list_rooms():
    """List all Matrix rooms via Synapse Admin API."""
    if not _is_ready():
        return []

    try:
        client = _get_client()
        if not client:
            return []

        rooms_resp = client.get_rooms()
        rooms = rooms_resp.get("rooms", [])

        result = []
        for r in rooms:
            result.append({
                "room_id": r.get("room_id", ""),
                "name": r.get("name", ""),
                "topic": r.get("topic", ""),
                "member_count": r.get("joined_local_devices", 0),
                "state": "joined",
            })

        return result
    except Exception:
        return []


@frappe.whitelist(allow_guest=True)
def get_room_detail(room_id: str):
    """Get room details: members, recent messages via Synapse Admin API."""
    if not _is_ready():
        return {}

    try:
        client = _get_client()
        if not client:
            frappe.throw("Synapse not ready")

        room = client.get_room(room_id)
        members_resp = client.get_room_members(room_id)
        messages_resp = client.get_room_messages(room_id)

        members = members_resp.get("members", [])
        messages = messages_resp.get("messages", [])

        return {
            "room": room,
            "members": [m.get("user_id", m) for m in members],
            "events": [
                {
                    "event_id": m.get("event_id", ""),
                    "sender": m.get("sender", ""),
                    "type": m.get("type", ""),
                    "content": m.get("content", {}),
                    "origin_server_ts": m.get("origin_server_ts", 0),
                }
                for m in messages
            ],
        }
    except SynapseError as e:
        frappe.throw(f"Synapse error: {e.body}")
    except Exception as e:
        frappe.throw(f"Failed to get room detail: {e}")


# ─── Health Check ───


@frappe.whitelist(allow_guest=True)
def health_check():
    """Health check endpoint for the Frappe API layer."""
    try:
        client = _get_client()
        if not client:
            return {"synapse": False, "message": "Synapse not yet configured"}

        ok = client.health_check()
        return {
            "synapse": ok,
            "message": "Synapse is running" if ok else "Synapse is not responding",
        }
    except Exception as e:
        return {"synapse": False, "error": str(e)}
