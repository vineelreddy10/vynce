"""Chat-related API endpoints: Messaging, Matrix credentials, TURN credentials."""

import os

import frappe
from .matrix.synapse_config import SYNAPSE_PORT


@frappe.whitelist()
def send_message(match_id: str, message: str) -> dict:
	user = frappe.session.user
	if user == "Guest":
		frappe.throw("Not logged in", frappe.AuthenticationError)

	if not frappe.db.exists("VY Match", match_id):
		frappe.throw("Match not found")

	# Try Matrix, log as fallback
	try:
		profile = frappe.get_doc("VY User Profile", {"user": user})
		if profile.matrix_user_id:
			from vynce.matrix.synapse_client import SynapseClient
			client = SynapseClient()
			token_resp = client.get_login_token(profile.matrix_user_id)
			if token_resp and token_resp.get("access_token"):
				room_id = frappe.db.get_value("VY Match", match_id, "matrix_room_id")
				if room_id:
					client.send_message(room_id, token_resp["access_token"], {
						"msgtype": "m.text",
						"body": message,
					})
					frappe.db.commit()
					return {"ok": True, "via": "matrix"}
	except Exception as e:
		frappe.logger().info(f"Matrix send failed, logging: {e}")

	# Log message as fallback
	from vynce.notification import send_notification
	match_doc = frappe.get_doc("VY Match", match_id)
	other_user = match_doc.user_2 if match_doc.user_1 == user else match_doc.user_1
	send_notification(
		user=other_user,
		ntype="Message",
		title="New Message",
		body=message[:200],
		data={"match_id": match_id, "from": user, "text": message},
	)
	return {"ok": True, "via": "notification"}


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

    matrix_server_url = os.environ.get(
        "MATRIX_SERVER_URL",
        f"http://127.0.0.1:{SYNAPSE_PORT}"
    )

    return {
        "matrix_user_id": profile.matrix_user_id,
        "matrix_access_token": token,
        "matrix_server_url": matrix_server_url,
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
