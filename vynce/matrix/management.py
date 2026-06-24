"""Synapse management utilities — user creation, status checks, lifecycle.

Uses the shared secret registration API (which works on both SQLite and 
PostgreSQL) instead of the Admin API (which has a SQLite bug in 1.155.0).
"""

import os
import secrets
import string
import hmac
import hashlib
from typing import Any
import requests
import yaml
import frappe
from .synapse_config import get_synapse_dir, SERVER_NAME, SYNAPSE_PORT


def get_server_url() -> str:
    """Return the base URL of the local Synapse instance."""
    return f"http://127.0.0.1:{SYNAPSE_PORT}"


def _read_shared_secret() -> str:
    """Read registration_shared_secret from homeserver.yaml."""
    yaml_path = os.path.join(get_synapse_dir(), "homeserver.yaml")
    with open(yaml_path) as f:
        cfg = yaml.safe_load(f)
    return cfg.get("registration_shared_secret", "")


def _admin_register(username: str, password: str, admin: bool = False) -> dict:
    """Create a user via the shared-secret registration API.
    
    POST /_synapse/admin/v1/register
    
    This works on both SQLite and PostgreSQL (unlike the v2 Admin API
    which crashes on SQLite with IndexError).
    """
    base_url = get_server_url()
    shared_secret = _read_shared_secret()
    if not shared_secret:
        raise RuntimeError("registration_shared_secret not found in config")

    # Get nonce
    r = requests.get(f"{base_url}/_synapse/admin/v1/register", timeout=10)
    r.raise_for_status()
    nonce = r.json()["nonce"]

    # Compute HMAC-SHA1
    mac = hmac.new(key=shared_secret.encode("utf8"), digestmod=hashlib.sha1)
    mac.update(nonce.encode("utf8"))
    mac.update(b"\x00")
    mac.update(username.encode("utf8"))
    mac.update(b"\x00")
    mac.update(password.encode("utf8"))
    mac.update(b"\x00")
    mac.update(b"admin" if admin else b"notadmin")

    # Register
    resp = requests.post(f"{base_url}/_synapse/admin/v1/register", json={
        "nonce": nonce,
        "username": username,
        "password": password,
        "admin": admin,
        "mac": mac.hexdigest(),
    }, timeout=10)

    if resp.status_code == 400:
        body = resp.json()
        if body.get("errcode") == "M_USER_IN_USE":
            # User exists — login to get a token
            login_resp = requests.post(f"{base_url}/_matrix/client/v3/login", json={
                "type": "m.login.password",
                "identifier": {"type": "m.id.user", "user": username},
                "password": password,
            }, timeout=10)
            if login_resp.status_code < 400:
                return login_resp.json()
        raise RuntimeError(f"Registration failed: {body.get('error', resp.text)}")

    resp.raise_for_status()
    return resp.json()


def create_user(username: str | None = None, password: str | None = None,
                displayname: str | None = None, admin: bool = False) -> dict:
    """Create a Matrix user and return their credentials.
    
    Returns: { "user_id", "access_token", "device_id", "username", "password" }
    """
    if not username:
        username = "user_" + "".join(secrets.choice(string.ascii_lowercase) for _ in range(8))
    if not password:
        password = "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(16))

    result = _admin_register(username, password, admin=admin)
    user_id = result.get("user_id", f"@{username}:{SERVER_NAME}")

    return {
        "user_id": user_id,
        "access_token": result.get("access_token", ""),
        "device_id": result.get("device_id", ""),
        "username": username,
        "password": password,
    }


def get_cached_admin_token() -> str:
    """Get admin access token with Redis caching (1 hour TTL)."""
    try:
        token = frappe.cache.get_value("matrix_admin_token")
        if token:
            return token
    except Exception:
        pass

    token = get_admin_token()
    if token:
        try:
            frappe.cache.set_value("matrix_admin_token", token, expires_in_sec=3600)
        except Exception:
            pass
    return token


def get_admin_token() -> str:
    """Return a valid admin access token for Synapse API calls.
    Creates the admin user if it doesn't exist.
    """
    try:
        return frappe.db.get_single_value("Matrix Settings", "admin_access_token") or ""
    except Exception:
        pass

    # Try to create admin user
    admin_username = "synapse_admin"
    admin_password = "Admin123!"
    try:
        result = create_user(admin_username, admin_password, admin=True)
        token = result.get("access_token", "")
        _save_admin_token(token, admin_username, admin_password)
        return token
    except RuntimeError:
        # User might already exist — login
        try:
            r = requests.post(f"{get_server_url()}/_matrix/client/v3/login", json={
                "type": "m.login.password",
                "identifier": {"type": "m.id.user", "user": admin_username},
                "password": admin_password,
            }, timeout=10)
            if r.status_code < 400:
                token = r.json().get("access_token", "")
                _save_admin_token(token, admin_username, admin_password)
                return token
        except Exception:
            pass
    return ""


def _save_admin_token(token: str, username: str, password: str):
    """Persist admin credentials."""
    try:
        import frappe
        if frappe.db.exists("Matrix Settings", "Matrix Settings"):
            doc = frappe.get_doc("Matrix Settings", "Matrix Settings")
            doc.admin_access_token = token
            doc.save(ignore_permissions=True)
            frappe.db.commit()
    except Exception:
        pass

    # Also save to env file
    env_path = os.path.join(get_synapse_dir(), "synapse.env")
    with open(env_path, "a") as f:
        f.write(f"\nSYNAPSE_ADMIN_TOKEN={token}\n")
        f.write(f"SYNAPSE_ADMIN_USER={username}\n")
        f.write(f"SYNAPSE_ADMIN_PASSWORD={password}\n")
