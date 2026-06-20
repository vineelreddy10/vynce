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
    """Get Matrix homeserver status and stats using C2S API."""
    if not _is_ready():
        return SYNAPSE_NOT_READY

    try:
        client = _get_client()
        if not client:
            return SYNAPSE_NOT_READY

        versions = client.get_versions()

        return {
            "status": "Running",
            "version": versions.get("versions", ["unknown"])[0],
            "server_name": "vynce.app",
        }
    except Exception as e:
        return {"status": "Error", "error": str(e)}


# ─── User Management ───


@frappe.whitelist(allow_guest=True)
def create_test_user():
    """Create a test Matrix user via shared secret registration."""
    import string
    import secrets
    from .management import create_user as mgmt_create_user

    username = "testuser_" + "".join(secrets.choice(string.ascii_lowercase) for _ in range(6))
    password = "test123"

    try:
        result = mgmt_create_user(username, password, displayname=f"Test User {username}")
        return {
            "username": username,
            "user_id": result["user_id"],
            "password": password,
            "access_token": result.get("access_token", ""),
        }
    except Exception as e:
        frappe.throw(f"Failed to create user: {e}")


# ─── Room Management ───


@frappe.whitelist(allow_guest=True)
def create_test_room(name: str = "Test Room"):
    """Create a test room with two users via shared secret registration."""
    import string
    import secrets
    from .management import create_user as mgmt_create_user

    try:
        client = _get_client()
        if not client:
            frappe.throw("Synapse not ready")

        users = []
        for i in range(2):
            uname = "testroom_" + "".join(secrets.choice(string.ascii_lowercase) for _ in range(4))
            result = mgmt_create_user(uname, "test123", displayname=f"Room User {i}")
            users.append({"username": uname, "user_id": result["user_id"], "token": result.get("access_token", "")})

        # Create room with user 1 as creator, inviting user 2
        room = client.create_room(
            name=name,
            creator=users[0]["user_id"],
            invite=[users[1]["user_id"]],
            is_direct=False,
        )
        room_id = room.get("room_id", "")

        # Send welcome message
        if users[0]["token"] and room_id:
            client.send_message(room_id, users[0]["token"], {
                "msgtype": "m.text",
                "body": f"Welcome to {name}! 👋",
            })

        return {
            "room_id": room_id,
            "name": name,
            "users": [u["username"] for u in users],
        }
    except Exception as e:
        frappe.throw(f"Failed to create room: {e}")


@frappe.whitelist(allow_guest=True)
def list_rooms():
    """List joined Matrix rooms via C2S sync."""
    if not _is_ready():
        return []

    try:
        client = _get_client()
        if not client:
            return []

        sync = client._c2s_request("GET", "/_matrix/client/v3/sync", token=client.access_token)
        joins = sync.get("rooms", {}).get("join", {})
        result = []
        for room_id, room_data in joins.items():
            timeline = room_data.get("timeline", {}).get("events", [])
            last_event = timeline[-1] if timeline else {}
            result.append({
                "room_id": room_id,
                "name": room_id,
                "member_count": 0,
                "state": "joined",
                "last_message": last_event.get("content", {}).get("body", ""),
            })
        return result
    except Exception:
        return []


@frappe.whitelist(allow_guest=True)
def get_room_detail(room_id: str):
    """Get room details: members, recent messages via C2S messages API."""
    if not _is_ready():
        return {}

    try:
        client = _get_client()
        if not client:
            frappe.throw("Synapse not ready")

        # Use C2S messages endpoint
        msgs = client._c2s_request(
            "GET",
            f"/_matrix/client/v3/rooms/{room_id}/messages?dir=b&limit=50",
            token=client.access_token,
        )
        chunk = msgs.get("chunk", [])

        # Use C2S joined_members endpoint
        members = client._c2s_request(
            "GET",
            f"/_matrix/client/v3/rooms/{room_id}/joined_members",
            token=client.access_token,
        )
        member_ids = list(members.get("joined", {}).keys())

        return {
            "room_id": room_id,
            "members": member_ids,
            "events": [
                {
                    "event_id": m.get("event_id", ""),
                    "sender": m.get("sender", ""),
                    "type": m.get("type", ""),
                    "content": m.get("content", {}),
                    "origin_server_ts": m.get("origin_server_ts", 0),
                }
                for m in chunk
            ],
        }
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
