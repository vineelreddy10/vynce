# Deployment Configuration Notes

This file documents every deployment-specific configuration needed when deploying
the vynce stack (Frappe + vynce-mobile SPA + Synapse Matrix + Garage S3) on a new VPS.

## Environment Variables Required in compose.yaml

### Backend Service
```yaml
backend:
  environment:
    DB_HOST: mariadb
    DB_PORT: "3306"
    REDIS_CACHE: redis-cache:6379
    REDIS_QUEUE: redis-queue:6379
    SYNAPSE_HOST: synapse              # REQUIRED: Matrix API host (not 127.0.0.1)
    MATRIX_SERVER_NAME: vynce.asakta.cloud  # REQUIRED: Matrix server name (not vynce.app)
  volumes:
    - sites:/home/frappe/frappe-bench/sites
    - assets-data:/home/frappe/frappe-bench/assets
    - synapse-data:/home/frappe/frappe-bench/sites/{SITE_NAME}/synapse:ro  # REQUIRED: Matrix config access
```

### Frontend Service
```yaml
frontend:
  volumes:
    - sites:/home/frappe/frappe-bench/sites
    - assets-data:/home/frappe/frappe-bench/assets
```

## Volume Mounts

| Volume | Mount Path | Purpose |
|--------|-----------|---------|
| `sites` | `/home/frappe/frappe-bench/sites` | Frappe site data |
| `assets-data` | `/home/frappe/frappe-bench/assets` | Shared assets (prevents CSS hash mismatch) |
| `synapse-data` | `/home/frappe/frappe-bench/sites/{SITE_NAME}/synapse:ro` | Synapse config for Matrix user creation |
| `synapse-pg-data` | (synapse) | Synapse PostgreSQL data |
| `synapse-data` | (synapse) | Synapse config + media |
| `traefik-cert-data` | (traefik) | Let's Encrypt SSL certs |

## Known Gotchas (Fixed in Code)

### 1. `get_admin_token()` uses `get_decrypted_password` 
**File**: `vynce/matrix/synapse_client.py`
**Issue**: `frappe.db.get_single_value()` returns ENCRYPTED password for Password fields.
**Fix**: Always use `frappe.utils.password.get_decrypted_password()` for Password fields.
**Commit**: `3f35cfb`

### 2. Matrix user creation uses Admin API, not shared-secret
**File**: `vynce/api.py`
**Issue**: `vynce.matrix.management.create_user()` uses `_admin_register()` which computes HMAC-SHA1
with the shared secret. The HMAC format changes between Synapse versions.
**Fix**: Use `SynapseClient.create_user()` (Admin API `PUT /_synapse/admin/v2/users/{userId}`) instead.
**Commit**: (latest fix)

### 3. `SERVER_NAME` must be configurable
**Files**: `vynce/matrix/synapse_config.py`, `vynce/chat.py`
**Issue**: Hardcoded `"vynce.app"` in multiple places.
**Fix**: Made configurable via `MATRIX_SERVER_NAME` env var (default: `vynce.asakta.cloud`).
**Commits**: `6697016`, `b152e16`

### 4. `SYNAPSE_HOST` env var
**File**: `vynce/matrix/synapse_client.py`
**Issue**: Defaults to `127.0.0.1` when not set.
**Fix**: Must be set to `synapse` (Docker service name) in compose.yaml.
**Commit**: (deployment config)

### 5. CSS asset hash mismatch
**Root Cause**: `sites/assets` is a symlink to per-container filesystem.
Both backend and frontend containers need to access the same asset files.
**Fix**: Mount `assets-data` volume at `/home/frappe/frappe-bench/assets` in both containers.
Also added `bench build` to Dockerfile.
**Commit**: `fa1fe77`

### 6. SPA API URL broken in production
**File**: vynce-mobile (built separately on VPS)
**Issue**: SPA was built with `VITE_API_URL` unset, falling back to `http://127.0.0.1:8002`.
**Fix**: Rebuild with `VITE_API_URL=""` (relative URL through nginx proxy).
**Action**: `cd /srv/vynce/vynce-mobile && VITE_API_URL="" npm run build`

## Matrix Admin Token Setup

After fresh deployment, set the Synapse admin token in Matrix Settings:

```bash
# 1. Create a Synapse admin user
docker exec synapse register_new_matrix_user \
  -c /data/homeserver.yaml \
  -u synapse_admin \
  -p <strong-password> \
  --admin \
  http://localhost:8008

# 2. Login to get access token
curl -X POST "https://vynceapp.asakta.cloud/_matrix/client/v3/login" \
  -H "Content-Type: application/json" \
  -d '{"type":"m.login.password","user":"synapse_admin","password":"<strong-password>"}'

# 3. Set token via Frappe API
curl -X PUT "https://vynce.asakta.cloud/api/resource/Matrix%20Settings/Matrix%20Settings" \
  -H "Authorization: Bearer <frappe-admin-cookie>" \
  -H "Content-Type: application/json" \
  -d '{"admin_access_token":"<matrix-access-token>","server_name":"vynce.asakta.cloud"}'
```

## Post-Deployment Migration

After deploying code fixes, run this to provision Matrix accounts for existing users:

```python
# bench --site <site> execute path/to/provision_matrix.py
from vynce.matrix.synapse_client import SynapseClient
import frappe

client = SynapseClient()
profiles = frappe.db.get_all("VY User Profile", 
  filters={"matrix_user_id": ["is", "not set"]}, 
  fields=["name", "user"])

for p in profiles:
    user = frappe.get_doc("User", p.user)
    username = p.user.split("@")[0]
    try:
        result = client.create_user(username=username, password="<generated-pwd>", displayname=user.full_name)
        user_id = result.get("name", f"@{username}:vynce.asakta.cloud")
        frappe.db.set_value("VY User Profile", p.name, "matrix_user_id", user_id)
        frappe.logger().info(f"Provisioned Matrix account for {p.user}: {user_id}")
    except Exception as e:
        frappe.logger().error(f"Failed to provision Matrix account for {p.user}: {e}")
```

## Verifying the Deployment

```bash
# All 3 domains
curl -sI https://vynce.asakta.cloud      # → 200
curl -sI https://vynceapp.asakta.cloud    # → 200
curl -sI https://vynce-garage.asakta.cloud # → 200

# API
curl -s https://vynce.asakta.cloud/api/method/login -X POST \
  -H "Content-Type: application/json" \
  -d '{"usr":"Administrator","pwd":"admin"}'  # → Logged In

# Matrix
curl -s https://vynce.asakta.cloud/_synapse/admin/v1/server_version  # → v1.155.0

# CSS (no MIME type errors)
curl -sI https://vynce.asakta.cloud/assets/frappe/dist/css/website.bundle.*.css  # → text/css
```
