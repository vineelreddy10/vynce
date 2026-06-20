"""Frappe Socket.io integration for Matrix real-time events.

Uses Frappe's built-in Socket.io server (managed by bench) to emit
ephemeral events: typing indicators, read receipts, presence updates.
"""

import frappe
from .synapse_client import SynapseClient


def _get_room_members(room_id: str) -> list[str]:
    """Get the list of Matrix user IDs in a room."""
    try:
        client = SynapseClient()
        members = client._c2s_request(
            "GET",
            f"/_matrix/client/v3/rooms/{room_id}/joined_members",
            token=client.access_token,
        )
        return list(members.get("joined", {}).keys())
    except Exception:
        return []


def _map_matrix_user_to_frappe(matrix_user_id: str) -> str | None:
    """Map a Matrix user ID (@user:vynce.app) to a Frappe user email.

    Matrix user IDs are @{username}:vynce.app.
    The Frappe user may have email = {username}@example.com or the same username.
    This mapping is stored on VY User Profile.matrix_user_id.
    """
    try:
        profiles = frappe.get_all(
            "VY User Profile",
            filters={"matrix_user_id": matrix_user_id},
            fields=["user"],
            limit=1,
        )
        if profiles:
            return profiles[0]["user"]
    except Exception:
        pass
    return None


# ─── Typing Indicators ───


@frappe.whitelist()
def send_typing(room_id: str, typing: bool = True):
    """Broadcast typing indicator to all room members except sender.
    
    Called by frontend via frappe.call() when user starts/stops typing.
    """
    user = frappe.session.user
    members = _get_room_members(room_id)

    for matrix_user_id in members:
        frappe_user = _map_matrix_user_to_frappe(matrix_user_id)
        if frappe_user and frappe_user != user:
            frappe.publish_realtime(
                "vynce:typing",
                {"room_id": room_id, "user_id": user, "matrix_user_id": matrix_user_id, "typing": bool(typing)},
                user=frappe_user,
            )


# ─── Read Receipts ───


@frappe.whitelist()
def send_read_receipt(room_id: str, event_id: str):
    """Broadcast read receipt to all room members except sender."""
    user = frappe.session.user
    members = _get_room_members(room_id)

    for matrix_user_id in members:
        frappe_user = _map_matrix_user_to_frappe(matrix_user_id)
        if frappe_user and frappe_user != user:
            frappe.publish_realtime(
                "vynce:read_receipt",
                {"room_id": room_id, "user_id": user, "matrix_user_id": matrix_user_id, "event_id": event_id},
                user=frappe_user,
            )


# ─── Presence ───


@frappe.whitelist()
def update_presence(presence: str = "online"):
    """Update user presence and broadcast to connections.
    
    Stores last_active timestamp and broadcasts to all users who
    have this user in their connections.
    """
    user = frappe.session.user
    try:
        profile = frappe.get_doc("VY User Profile", {"user": user})
        profile.db_set("last_active", frappe.utils.now(), update_modified=False)
    except Exception:
        pass

    frappe.publish_realtime(
        "vynce:presence",
        {"user_id": user, "presence": presence, "last_active": frappe.utils.now()},
    )


# ─── Match Notifications ───


def notify_new_match(user_id: str, match_id: str, room_id: str, matched_user: str):
    """Emit a new match notification to a user.
    
    Called from match.py when a mutual like is detected.
    """
    frappe.publish_realtime(
        "vynce:new_match",
        {
            "match_id": match_id,
            "room_id": room_id,
            "matched_user": matched_user,
        },
        user=user_id,
    )
