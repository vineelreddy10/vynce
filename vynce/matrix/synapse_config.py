"""Generate Synapse homeserver.yaml configuration and signing keys."""

import os
import secrets
import string
import subprocess
import tempfile
import frappe


SYNAPSE_PORT = 8008
SERVER_NAME = os.environ.get("MATRIX_SERVER_NAME", "vynce.asakta.cloud")


def generate_secret(length=64):
    """Generate a random secret string."""
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def get_synapse_dir():
    """Return the absolute path to the Synapse config directory for the current site."""
    site = frappe.local.site
    return os.path.abspath(os.path.join(frappe.get_site_path(), "synapse"))


def generate_config() -> dict:
    """Generate a complete Synapse homeserver.yaml config dict.
    
    Returns the config dict. Also writes homeserver.yaml and signing key.
    """
    synapse_dir = get_synapse_dir()
    os.makedirs(synapse_dir, exist_ok=True)

    registration_shared_secret = generate_secret()
    macaroon_secret_key = generate_secret()
    form_secret = generate_secret()

    config = {
        "server_name": SERVER_NAME,
        "pid_file": os.path.join(synapse_dir, "homeserver.pid"),
        "listeners": [
            {
                "port": SYNAPSE_PORT,
                "bind_addresses": ["127.0.0.1"],
                "type": "http",
                "tls": False,
                "x_forwarded": True,
                "resources": [
                    {"names": ["client", "federation"], "compress": True}
                ],
            }
        ],
        "database": _get_database_config(),
        "log_config": os.path.join(synapse_dir, "log.config"),
        "media_store_path": os.path.join(synapse_dir, "media_store"),
        "uploads_path": os.path.join(synapse_dir, "uploads"),
        "registration_shared_secret": registration_shared_secret,
        "macaroon_secret_key": macaroon_secret_key,
        "form_secret": form_secret,
        "signing_key_path": os.path.join(synapse_dir, "signing.key"),
        "suppress_key_server_warning": True,
        "trusted_key_servers": [
            {"server_name": "matrix.org"}
        ],
        "enable_registration": False,
        "enable_registration_captcha": False,
        "allow_guest_access": False,
        "allow_public_rooms_without_auth": False,
        "allow_public_rooms_over_federation": True,
        "federation_domain_whitelist": None,
        "rc_registration": {"per_second": 0.01, "burst_count": 5},
        "rc_login": {
            "address": {"per_second": 0.1, "burst_count": 10},
            "account": {"per_second": 0.1, "burst_count": 10},
            "failed_attempts": {"per_second": 0.05, "burst_count": 10},
        },
        "event_cache_size": "100K",
        "expire_caches": True,
        "cache_entry_ttl": "30m",
        "max_upload_size": "50M",
        "url_preview_enabled": False,
        "admin_contact": "vineel@asakta.com",
        "report_stats": False,
        "enable_metrics": False,
    }

    return config


def _get_database_config() -> dict:
    """Detect PostgreSQL availability, fall back to SQLite."""
    synapse_dir = get_synapse_dir()
    try:
        import psycopg2

        # Check if we can connect to a local PostgreSQL
        conn = psycopg2.connect(
            host="localhost",
            port=5432,
            user="synapse",
            password="synapse",
            dbname="synapse_vynce",
            connect_timeout=2,
        )
        conn.close()
        frappe.logger().info("Synapse: using PostgreSQL database")
        return {
            "name": "psycopg2",
            "args": {
                "user": "synapse",
                "password": "synapse",
                "database": "synapse_vynce",
                "host": "localhost",
                "port": 5432,
                "cp_min": 5,
                "cp_max": 10,
            },
        }
    except Exception:
        frappe.logger().info("Synapse: PostgreSQL unavailable, using SQLite")
        synapse_dir = get_synapse_dir()
        return {
            "name": "sqlite3",
            "args": {"database": os.path.join(synapse_dir, "homeserver.db")},
        }


def generate_signing_key(path: str) -> str:
    """Generate a Synapse signing key file.
    
    Format: ed25519 <key_id> <base64_key>
    """
    if os.path.exists(path):
        return path

    from unpaddedbase64 import encode_base64
    from nacl.signing import SigningKey

    key = SigningKey.generate()
    key_id = "a_" + "".join(secrets.choice(string.digits) for _ in range(4))
    key_b64 = encode_base64(key.encode())

    content = f"ed25519 {key_id} {key_b64}\n"
    with open(path, "w") as f:
        f.write(content)
    os.chmod(path, 0o600)

    return path


def write_log_config(path: str):
    """Write a minimal Synapse log config that logs to console + file."""
    if os.path.exists(path):
        return

    log_file = os.path.join(os.path.dirname(path), "homeserver.log")
    content = f"""
version: 1
formatters:
  precise:
    format: '%(asctime)s - %(name)s - %(lineno)d - %(levelname)s - %(request)s - %(message)s'
handlers:
  console:
    class: logging.StreamHandler
    formatter: precise
  file:
    class: logging.handlers.RotatingFileHandler
    formatter: precise
    filename: {log_file}
    maxBytes: 10485760
    backupCount: 10
loggers:
  synapse:
    level: INFO
  synapse.storage.SQL:
    level: WARN
root:
  level: INFO
  handlers: [console, file]
"""
    with open(path, "w") as f:
        f.write(content)


def write_homeserver_yaml(config: dict, path: str):
    """Write config dict to homeserver.yaml."""
    import yaml

    with open(path, "w") as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)
    os.chmod(path, 0o600)


def write_synapse_env(config: dict):
    """Write environment variables for the Synapse process."""
    synapse_dir = get_synapse_dir()
    env_path = os.path.join(synapse_dir, "synapse.env")
    with open(env_path, "w") as f:
        f.write(f"SYNAPSE_CONFIG_PATH={os.path.join(synapse_dir, 'homeserver.yaml')}\n")
        f.write(f"SYNAPSE_PORT={SYNAPSE_PORT}\n")
        f.write(f"REGISTRATION_SHARED_SECRET={config['registration_shared_secret']}\n")


def setup_synapse_config():
    """Full config setup — called from after_install.
    
    Returns the path to homeserver.yaml.
    """
    config = generate_config()
    synapse_dir = get_synapse_dir()

    yaml_path = os.path.join(synapse_dir, "homeserver.yaml")
    write_homeserver_yaml(config, yaml_path)
    generate_signing_key(config["signing_key_path"])
    write_log_config(config["log_config"])
    write_synapse_env(config)

    frappe.logger().info(f"Synapse config written to {yaml_path}")
    return yaml_path
