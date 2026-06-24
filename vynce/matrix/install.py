"""Synapse setup script reference.

Synapse now runs as a process connected to a Docker PostgreSQL container.
The Frappe-managed pip installation approach was replaced because:
  1. Synapse on SQLite has Admin API bugs (IndexError on user/room listing)
  2. Docker PostgreSQL provides proper isolation and locale configuration
  3. The same Python env caused dependency conflicts with Frappe

To set up Synapse from scratch:
  ./docker/synapse/setup.sh

To start Synapse:
  ./docker/synapse/start.sh

To stop:
  ./docker/synapse/stop.sh

To check status:
  ./docker/synapse/status.sh

For Frappe integration, the `synapse_client.py`, `frappe_api.py`, and
`management.py` modules work identically regardless of how Synapse is
deployed — they connect via HTTP to http://127.0.0.1:8008.
"""


def _ensure_synapse_installed():
    """Check if matrix-synapse is installed, install if not."""
    try:
        import synapse  # noqa: F401
        frappe.logger().info("Synapse already installed")
    except ImportError:
        frappe.logger().info("Installing matrix-synapse...")
        bench_python = sys.executable
        result = subprocess.run(
            [bench_python, "-m", "pip", "install", "matrix-synapse"],
            capture_output=True, text=True, timeout=300,
        )
        if result.returncode != 0:
            frappe.throw(
                f"Failed to install matrix-synapse:\n{result.stderr}"
            )
        frappe.logger().info("matrix-synapse installed successfully")


def _ensure_matrix_settings_doctype():
    """Create the Matrix Settings single doctype record if it doesn't exist."""
    if not frappe.db.exists("Matrix Settings", "Matrix Settings"):
        settings = frappe.get_doc({
            "doctype": "Matrix Settings",
            "homeserver_status": "Starting",
            "server_name": SERVER_NAME,
            "port": SYNAPSE_PORT,
        })
        settings.insert(ignore_permissions=True)
        frappe.db.commit()


def _start_synapse(yaml_path: str) -> int:
    """Start the Synapse process. Returns PID."""
    synapse_dir = get_synapse_dir()
    pid_file = os.path.join(synapse_dir, "homeserver.pid")
    log_file = os.path.join(synapse_dir, "homeserver.log")

    # Check if already running
    if os.path.exists(pid_file):
        try:
            with open(pid_file) as f:
                old_pid = int(f.read().strip())
            os.kill(old_pid, 0)  # Check if process exists
            frappe.logger().info(f"Synapse already running (PID {old_pid})")
            return old_pid
        except (ProcessLookupError, ValueError, OSError):
            frappe.logger().info("Stale PID file found, starting fresh")

    bench_python = sys.executable
    module = "synapse.app.homeserver"
    proc = subprocess.Popen(
        [bench_python, "-m", module, "--config-path", yaml_path],
        stdout=open(log_file, "a"),
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )

    # Wait for startup
    import time
    for i in range(30):
        time.sleep(1)
        if _is_synapse_ready():
            frappe.logger().info(f"Synapse started (PID {proc.pid})")
            return proc.pid
        # Check if process died
        if proc.poll() is not None:
            frappe.throw(
                f"Synapse process died during startup. Check logs: {log_file}"
            )

    frappe.throw(f"Synapse failed to start within 30s. Check logs: {log_file}")


def _is_synapse_ready() -> bool:
    """Check if Synapse's C2S API is responding."""
    try:
        import requests
        resp = requests.get(
            f"{get_server_url()}/_matrix/client/versions",
            timeout=2,
        )
        return resp.status_code == 200
    except Exception:
        return False


def _create_admin_user():
    """Create the admin user using Synapse shared secret registration.
    
    Uses the registration_shared_secret from homeserver.yaml to create
    an admin user via POST /_synapse/admin/v1/register.
    """
    import hashlib
    import hmac
    import yaml
    import requests as http_requests

    admin_username = "synapse_admin"
    admin_password = generate_secret(32)

    try:
        yaml_path = os.path.join(get_synapse_dir(), "homeserver.yaml")
        with open(yaml_path) as f:
            cfg = yaml.safe_load(f)
        shared_secret = cfg.get("registration_shared_secret", "")
        if not shared_secret:
            raise ValueError("registration_shared_secret not found in config")

        # Step 1: Get nonce
        url = f"{get_server_url()}/_synapse/admin/v1/register"
        r = http_requests.get(url)
        nonce = r.json().get("nonce", "")
        if not nonce:
            raise ValueError("Failed to get registration nonce")

        # Step 2: Compute HMAC (SHA1, not SHA256!)
        mac = hmac.new(key=shared_secret.encode(), digestmod=hashlib.sha1)
        mac.update(nonce.encode())
        mac.update(b"\x00")
        mac.update(admin_username.encode())
        mac.update(b"\x00")
        mac.update(admin_password.encode())
        mac.update(b"\x00")
        mac.update(b"admin")

        # Step 3: Register admin user
        r = http_requests.post(url, json={
            "nonce": nonce,
            "username": admin_username,
            "password": admin_password,
            "admin": True,
            "mac": mac.hexdigest(),
        })

        if r.status_code >= 400:
            raise ValueError(f"Registration failed: {r.text}")

        resp = r.json()
        admin_token = resp.get("access_token", "")
        user_id = resp.get("user_id", f"@{admin_username}:{SERVER_NAME}")

        # Store admin token in Matrix Settings
        try:
            if frappe.db.exists("Matrix Settings", "Matrix Settings"):
                frappe.db.set_value("Matrix Settings", "Matrix Settings",
                    "admin_access_token", admin_token)
                frappe.db.commit()
        except Exception:
            pass

        frappe.logger().info(f"Synapse admin user created: {user_id}")

        # Store credentials in a file for CLI use
        env_path = os.path.join(get_synapse_dir(), "synapse.env")
        with open(env_path, "a") as f:
            f.write(f"\nSYNAPSE_ADMIN_TOKEN={admin_token}\n")
            f.write(f"SYNAPSE_ADMIN_USER={admin_username}\n")
            f.write(f"SYNAPSE_ADMIN_PASSWORD={admin_password}\n")

    except Exception as e:
        frappe.logger().warning(f"Admin user creation failed (may retry): {e}")


def _update_matrix_settings(pid: int):
    """Update Matrix Settings doctype with current status."""
    settings = frappe.get_doc("Matrix Settings", "Matrix Settings")
    settings.homeserver_status = "Running"
    settings.server_name = SERVER_NAME
    settings.port = SYNAPSE_PORT
    settings.db_path = os.path.join(get_synapse_dir(), "homeserver.db")
    settings.save(ignore_permissions=True)
    frappe.db.commit()


def _ensure_procfile_entry(yaml_path: str):
    """Add Synapse to the bench Procfile if not already present."""
    bench_dir = frappe.utils.get_bench_dir()
    procfile_path = os.path.join(bench_dir, "Procfile")

    entry = f"synapse: python -m synapse.app.homeserver --config-path {yaml_path}"

    if os.path.exists(procfile_path):
        with open(procfile_path) as f:
            content = f.read()
        if "synapse:" in content:
            frappe.logger().info("Synapse Procfile entry already exists")
            return

    with open(procfile_path, "a") as f:
        f.write(f"\n\n{entry}\n")

    frappe.logger().info(f"Added Synapse to Procfile: {procfile_path}")


# ─── Lifecycle Management ───


def stop_synapse():
    """Stop the Synapse process."""
    synapse_dir = get_synapse_dir()
    pid_file = os.path.join(synapse_dir, "homeserver.pid")

    if not os.path.exists(pid_file):
        frappe.logger().info("No Synapse PID file found")
        return

    with open(pid_file) as f:
        try:
            pid = int(f.read().strip())
            os.kill(pid, signal.SIGTERM)
            frappe.logger().info(f"Synapse stopped (PID {pid})")
            os.remove(pid_file)
        except (ProcessLookupError, ValueError, OSError) as e:
            frappe.logger().warning(f"Could not stop Synapse: {e}")
            os.remove(pid_file)


def restart_synapse():
    """Restart the Synapse process."""
    stop_synapse()
    yaml_path = os.path.join(get_synapse_dir(), "homeserver.yaml")
    if os.path.exists(yaml_path):
        _start_synapse(yaml_path)


def health_check() -> dict:
    """Check if Synapse is running and responding."""
    try:
        client = SynapseClient()
        versions = client.get_versions()
        return {
            "status": "Running",
            "versions": versions.get("versions", []),
            "url": get_server_url(),
        }
    except Exception as e:
        return {"status": "Error", "error": str(e)}
