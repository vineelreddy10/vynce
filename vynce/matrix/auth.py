import hashlib
import secrets
from . import storage as store
from .utils import generate_token


def hash_password(password: str) -> str:
    """Hash a password using SHA-256 with a random salt (simpler than bcrypt for POC)."""
    salt = secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 260000)
    return f"{salt}:{h.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        salt, h = stored_hash.split(":", 1)
        expected = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 260000).hex()
        return h == expected
    except (ValueError, AttributeError):
        return False


def register(user_id: str, password: str) -> dict:
    """Register a new Matrix user. Returns user info."""
    if store.user_exists(user_id):
        return {"errcode": "M_USER_IN_USE", "error": "User already exists"}

    pw_hash = hash_password(password)
    store.create_user(user_id, pw_hash)

    # Auto-create access token
    token = generate_token()
    store.create_token(token, user_id)

    return {
        "user_id": user_id,
        "access_token": token,
        "device_id": "POC",
    }


def login(identifier: str, password: str) -> dict:
    """Login and return access token."""
    user_id = identifier if identifier.startswith("@") else f"@{identifier}:localhost"
    user = store.get_user(user_id)
    if not user or not verify_password(password, user["password_hash"]):
        return {"errcode": "M_FORBIDDEN", "error": "Invalid username or password"}

    token = generate_token()
    store.create_token(token, user_id)

    return {
        "user_id": user_id,
        "access_token": token,
        "device_id": "POC",
        "well_known": {
            "m.homeserver": {"base_url": ""},
            "m.identity_server": {"base_url": ""},
        },
    }


def validate_token(token: str) -> str | None:
    """Returns user_id if token is valid, None otherwise."""
    return store.get_token_owner(token)
