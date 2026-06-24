"""HTTP client for Synapse Admin API and C2S API.

Used by the Frappe API layer to manage users, rooms, and messages
on the Synapse homeserver.
"""

import os
from typing import Any
import requests
import frappe
from .synapse_config import SERVER_NAME, get_synapse_dir


class SynapseError(Exception):
    """Raised when Synapse API returns an error."""

    def __init__(self, status: int, body: Any):
        self.status = status
        self.body = body
        super().__init__(f"[{status}] {body}")


def get_admin_token() -> str | None:
    """Read admin access token from Matrix Settings doctype or env."""
    try:
        return frappe.db.get_single_value("Matrix Settings", "admin_access_token")
    except Exception:
        return os.environ.get("SYNAPSE_ADMIN_TOKEN")


def get_server_url() -> str:
    """Return the base URL of the local Synapse instance.
    
    Uses SYNAPSE_HOST env var in Docker deployments, falls back to 127.0.0.1.
    """
    from .synapse_config import SYNAPSE_PORT

    host = os.environ.get("SYNAPSE_HOST", "127.0.0.1")
    return f"http://{host}:{SYNAPSE_PORT}"


class SynapseClient:
    """HTTP client for Synapse Admin & C2S APIs."""

    def __init__(self, base_url: str | None = None, access_token: str | None = None):
        self.base_url = (base_url or get_server_url()).rstrip("/")
        self.access_token = access_token or get_admin_token()

    # ─── Admin API helpers ───

    def _admin_request(self, method: str, path: str, json_body: dict | None = None):
        """Make an authenticated request to Synapse Admin API."""
        headers = {"Authorization": f"Bearer {self.access_token}"}
        url = self.base_url + path
        resp = requests.request(method, url, headers=headers, json=json_body, timeout=10)
        if resp.status_code >= 400:
            raise SynapseError(resp.status_code, resp.text)
        return resp.json()

    def _c2s_request(self, method: str, path: str, json_body: dict | None = None, token: str | None = None):
        """Make a request to the Synapse C2S (Client-Server) API."""
        headers = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        url = self.base_url + path
        resp = requests.request(method, url, headers=headers, json=json_body, timeout=10)
        if resp.status_code >= 400:
            raise SynapseError(resp.status_code, resp.text)
        return resp.json()

    # ─── Health / Status ───

    def health_check(self) -> bool:
        """Check if Synapse is alive by hitting its versions endpoint."""
        try:
            self._c2s_request("GET", "/_matrix/client/versions")
            return True
        except Exception:
            return False

    def get_versions(self) -> dict:
        """GET /_matrix/client/versions"""
        return self._c2s_request("GET", "/_matrix/client/versions")

    # ─── User Management (Admin API) ───

    def create_user(self, username: str, password: str, displayname: str | None = None) -> dict:
        """Create or update a user via Synapse Admin API.
        
        POST /_synapse/admin/v2/users/{userId}
        """
        user_id = f"@{username}:{SERVER_NAME}"
        body: dict = {"password": password}
        if displayname:
            body["displayname"] = displayname
        return self._admin_request("PUT", f"/_synapse/admin/v2/users/{user_id}", body)

    def get_user(self, user_id: str) -> dict:
        """GET /_synapse/admin/v1/users/{userId}"""
        return self._admin_request("GET", f"/_synapse/admin/v1/users/{user_id}")

    def deactivate_user(self, user_id: str) -> dict:
        """POST /_synapse/admin/v1/deactivate/{userId}"""
        return self._admin_request("POST", f"/_synapse/admin/v1/deactivate/{user_id}")

    def get_users(self, from_idx: int = 0, limit: int = 50) -> dict:
        """GET /_synapse/admin/v2/users"""
        return self._admin_request("GET", f"/_synapse/admin/v2/users?from={from_idx}&limit={limit}")

    def get_login_token(self, user_id: str) -> str:
        """Get a login token for a user.
        
        POST /_synapse/admin/v1/users/{userId}/login
        Returns the access_token that the client can use directly.
        """
        resp = self._admin_request("POST", f"/_synapse/admin/v1/users/{user_id}/login")
        return resp.get("access_token", "")

    # ─── Room Management (Admin API) ───

    def create_room(self, name: str, topic: str = "", creator: str | None = None,
                    invite: list[str] | None = None, is_direct: bool = False) -> dict:
        """Create a room via Synapse Admin API.
        
        POST /_synapse/admin/v1/rooms
        Returns the room creation response with room_id.
        """
        body: dict = {
            "name": name,
            "topic": topic,
            "is_direct": is_direct,
            "preset": "trusted_private_chat" if is_direct else "private_chat",
        }
        if creator:
            body["creator"] = creator
        if invite:
            body["invite"] = invite
        return self._admin_request("POST", "/_synapse/admin/v1/rooms", body)

    def get_room(self, room_id: str) -> dict:
        """GET /_synapse/admin/v1/rooms/{roomId}"""
        return self._admin_request("GET", f"/_synapse/admin/v1/rooms/{room_id}")

    def get_rooms(self, from_idx: int = 0, limit: int = 50) -> dict:
        """GET /_synapse/admin/v1/rooms"""
        return self._admin_request("GET", f"/_synapse/admin/v1/rooms?from={from_idx}&limit={limit}")

    def get_room_messages(self, room_id: str, limit: int = 50) -> dict:
        """GET /_synapse/admin/v1/rooms/{roomId}/messages"""
        return self._admin_request("GET", f"/_synapse/admin/v1/rooms/{room_id}/messages?limit={limit}")

    def get_room_members(self, room_id: str) -> dict:
        """GET /_synapse/admin/v1/rooms/{roomId}/members"""
        return self._admin_request("GET", f"/_synapse/admin/v1/rooms/{room_id}/members")

    def delete_room(self, room_id: str) -> dict:
        """DELETE /_synapse/admin/v1/rooms/{roomId}"""
        return self._admin_request("DELETE", f"/_synapse/admin/v1/rooms/{room_id}")

    # ─── C2S API (for direct client operations) ───

    def login(self, username: str, password: str) -> dict:
        """POST /_matrix/client/v3/login"""
        body = {
            "type": "m.login.password",
            "identifier": {"type": "m.id.user", "user": username},
            "password": password,
        }
        return self._c2s_request("POST", "/_matrix/client/v3/login", body)

    def register(self, username: str, password: str) -> dict:
        """POST /_matrix/client/v3/register
        
        Note: Uses shared_secret registration. Requires registration_shared_secret
        to be set in homeserver.yaml. This is for testing only — use Admin API
        create_user for production.
        """
        # We set ?kind=user for full account
        body = {
            "username": username,
            "password": password,
            "auth": {"type": "m.login.dummy"},
        }
        return self._c2s_request("POST", "/_matrix/client/v3/register?kind=user", body)

    def send_message(self, room_id: str, access_token: str, content: dict) -> dict:
        """PUT /_matrix/client/v3/rooms/{roomId}/send/m.room.message/{txnId}
        
        Sends a message to a room using a user's access_token.
        """
        import time
        import uuid

        txn_id = str(int(time.time() * 1000)) + uuid.uuid4().hex[:6]
        path = f"/_matrix/client/v3/rooms/{room_id}/send/m.room.message/{txn_id}"
        return self._c2s_request("PUT", path, content, token=access_token)

    def sync(self, access_token: str, since: str | None = None) -> dict:
        """GET /_matrix/client/v3/sync"""
        path = "/_matrix/client/v3/sync"
        if since:
            path += f"?since={since}"
        return self._c2s_request("GET", path, token=access_token)


def get_client() -> SynapseClient:
    """Convenience — get a SynapseClient with default credentials."""
    return SynapseClient()
