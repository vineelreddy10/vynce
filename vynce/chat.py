"""Chat-related API endpoints: Matrix credentials, TURN credentials for WebRTC calls."""

import frappe
from .matrix.synapse_config import SYNAPSE_PORT


@frappe.whitelist()
def get_matrix_credentials():
    """Get Matrix access token for the current user.
    
    Lazily creates a Matrix account if one doesn't exist yet.
    Uses Synapse Admin API to generate a login token (no user password needed).
    Returns: { matrix_user_id, matrix_access_token, matrix_server_url }
    """
    user = frappe.session.user
    if user == "Guest":
        frappe.throw("Not logged in", frappe.AuthenticationError)

    profile = frappe.get_doc("VY User Profile", {"user": user})

    # Lazy-provision Matrix account if missing (handles users who registered before Phase 3A)
    if not profile.matrix_user_id:
        try:
            from vynce.matrix.synapse_client import SynapseClient
            import secrets
            import string

            client = SynapseClient()
            username = user.split("@")[0]
            generated_pwd = "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(16))

            result = client.create_user(
                username=username,
                password=generated_pwd,
                displayname=profile.display_name,
            )

            matrix_user_id = f"@{username}:vynce.app"
            # Verify the response contains the user
            if result.get("name"):
                profile.db_set("matrix_user_id", matrix_user_id, update_modified=False)
                frappe.db.commit()
            else:
                frappe.logger().error(f"Matrix user creation returned unexpected result: {result}")
                frappe.throw("Failed to create Matrix account")
        except Exception as e:
            frappe.logger().error(f"Failed to create Matrix account for {user}: {e}")
            # Still allow the request to proceed — frontend will handle the error gracefully
            frappe.throw(f"Failed to create Matrix account. Please contact support: {e}")

    from vynce.matrix.synapse_client import SynapseClient

    client = SynapseClient()
    try:
        token = client.get_login_token(profile.matrix_user_id)
    except Exception as e:
        frappe.throw(f"Failed to get Matrix access token: {e}")

    return {
        "matrix_user_id": profile.matrix_user_id,
        "matrix_access_token": token,
        "matrix_server_url": f"http://127.0.0.1:{SYNAPSE_PORT}",
    }


@frappe.whitelist()
def get_turn_credentials():
    """Return ephemeral TURN credentials for WebRTC calls.
    
    Uses time-limited HMAC-based credentials (TURN REST API).
    Requires coturn server to be running on the VPS.
    """
    import hmac
    import hashlib
    import base64
    import time

    secret = frappe.conf.get("turn_shared_secret", "shared-turn-secret")
    ttl = 86400  # 24 hours

    username = f"{int(time.time()) + ttl}:{frappe.session.user}"
    digest = hmac.new(
        secret.encode("utf8"),
        username.encode("utf8"),
        hashlib.sha1,
    ).digest()
    password = base64.b64encode(digest).decode("utf8")

    return {
        "uris": [
            "turn:91.107.206.65:3478?transport=udp",
            "turns:91.107.206.65:5349?transport=tcp",
        ],
        "username": username,
        "password": password,
    }


@frappe.whitelist()
def get_webrtc_config():
    """Return ICE servers (STUN + TURN) for WebRTC peer connections."""
    try:
        turn = get_turn_credentials()
        turn_servers = [
            {
                "urls": turn["uris"],
                "username": turn["username"],
                "credential": turn["password"],
            }
        ]
    except Exception:
        turn_servers = []

    return {
        "ice_servers": [
            {"urls": ["stun:stun.l.google.com:19302"]},
            {"urls": ["stun:stun1.l.google.com:19302"]},
            *turn_servers,
        ],
    }
