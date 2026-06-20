"""Synapse + PostgreSQL status checks.

Provides a unified status endpoint that checks:
1. Is the Synapse process running?
2. Is Synapse responding to C2S API calls?
3. Is PostgreSQL available (if configured)?
4. Last heartbeat timestamp
"""

import os
import frappe
from .synapse_config import get_synapse_dir, SYNAPSE_PORT, SERVER_NAME
from .synapse_client import SynapseClient


def get_status() -> dict:
    """Comprehensive status check: Synapse process, C2S API, PostgreSQL."""
    result = {
        "synapse": {"process": False, "api": False, "version": "", "port": SYNAPSE_PORT},
        "postgresql": {"available": False, "connected": False},
        "server_name": SERVER_NAME,
        "last_heartbeat": None,
    }

    # Check process
    pid_file = os.path.join(get_synapse_dir(), "homeserver.pid")
    result["synapse"]["process"] = _check_pid(pid_file)

    # Check API
    try:
        client = SynapseClient()
        versions = client.get_versions()
        result["synapse"]["api"] = True
        result["synapse"]["version"] = versions.get("versions", ["unknown"])[0]
    except Exception:
        pass

    # Check PostgreSQL
    result["postgresql"] = _check_postgresql()

    # Read heartbeat from Matrix Settings
    try:
        ts = frappe.db.get_single_value("Matrix Settings", "last_heartbeat")
        if ts:
            result["last_heartbeat"] = str(ts)
    except Exception:
        pass

    return result


def _check_pid(pid_file: str) -> bool:
    """Check if a process is running from its PID file."""
    if not os.path.exists(pid_file):
        return False
    try:
        with open(pid_file) as f:
            pid = int(f.read().strip())
        os.kill(pid, 0)
        return True
    except (OSError, ValueError):
        return False


def _check_postgresql() -> dict:
    """Check if PostgreSQL is available and can connect."""
    result = {"available": False, "connected": False}
    try:
        # Check if homeserver.yaml uses PostgreSQL
        import yaml
        yaml_path = os.path.join(get_synapse_dir(), "homeserver.yaml")
        if not os.path.exists(yaml_path):
            return result
        with open(yaml_path) as f:
            cfg = yaml.safe_load(f)
        db_config = cfg.get("database", {})
        if db_config.get("name") != "psycopg2":
            return result

        result["available"] = True
        try:
            import psycopg2
            conn = psycopg2.connect(
                host=db_config.get("args", {}).get("host", "localhost"),
                port=db_config.get("args", {}).get("port", 5432),
                user=db_config.get("args", {}).get("user", "synapse"),
                password=db_config.get("args", {}).get("password", ""),
                dbname=db_config.get("args", {}).get("database", "synapse_vynce"),
                connect_timeout=2,
            )
            conn.close()
            result["connected"] = True
        except Exception:
            pass
    except Exception:
        pass
    return result


@frappe.whitelist(allow_guest=True)
def full_status():
    """Frappe API endpoint: returns full Synapse + PostgreSQL status."""
    return get_status()
