# Vynce Production Deployment Guide

> Version 1.0 | 2026-06-30 | Target: VPS with Docker Compose

---

## Architecture

```
Internet → Traefik :443 (Let's Encrypt SSL)
├── vynce.asakta.cloud     → Frappe Desk + Synapse Matrix (_matrix/*, _synapse/*)
├── vynceapp.asakta.cloud   → React SPA (vynce-mobile)
└── vynce-garage.asakta.cloud → Garage Web UI

All services on vynce-network Docker network:
├── mariadb:10.6     ─── Frappe DB
├── redis-cache:7    ─── Frappe cache
├── redis-queue:7    ─── Frappe queue
├── synapse-db (PG16)── Synapse DB
├── synapse:latest    ─── Matrix homeserver (port 8008)
├── configurator      ─── One-time Frappe setup
├── backend           ─── Frappe gunicorn (:8000)
├── frontend          ─── Frappe nginx (:8080)
├── websocket         ─── Socket.io (:9000)
├── queue-short/long  ─── Background workers
├── scheduler         ─── Scheduled tasks
├── vynce-mobile      ─── nginx:alpine serving SPA
└── traefik:v3.6      ─── Reverse proxy
```

---

## Prerequisites

- VPS: 2+ CPU, 4+ GB RAM, 40+ GB disk
- Docker 25+, Docker Compose v2
- 3 DNS A records pointing to VPS IP
- Git access to `vineelreddy10/vynce` and `vineelreddy10/vynce-mobile`
- GitHub Secrets: `GITLAB_PAT` (vynce repo), `VPS_SSH_KEY` (vynce-mobile repo)

---

## Step-by-Step Deployment

### 1. DNS Records

| Name | Type | Value |
|------|------|-------|
| vynce.asakta.cloud | A | VPS_IP |
| vynceapp.asakta.cloud | A | VPS_IP |
| vynce-garage.asakta.cloud | A | VPS_IP |

### 2. VPS Setup

```bash
ssh root@VPS_IP
mkdir -p /srv/vynce/vynce-mobile
docker network create vynce-network
```

### 3. Environment — .env

Create `/srv/vynce/.env`:
```env
DB_PASSWORD=<strong-mariadb-password>
LETSENCRYPT_EMAIL=<your-email>
SYNAPSE_DB_PASSWORD=<strong-synapse-pg-password>
CUSTOM_IMAGE=ghcr.io/vineelreddy10/vynce-bench
CUSTOM_TAG=latest
```

### 4. Docker Compose

Create `/srv/vynce/compose.yaml`. **Critical env vars for backend:**

```yaml
backend:
  environment:
    DB_HOST: mariadb
    DB_PORT: "3306"
    REDIS_CACHE: redis-cache:6379
    REDIS_QUEUE: redis-queue:6379
    # ⚠️ CRITICAL: These MUST be set or Matrix will break!
    SYNAPSE_HOST: synapse              # default is 127.0.0.1
    MATRIX_SERVER_NAME: vynce.asakta.cloud  # default is vynce.app
    MATRIX_SERVER_URL: https://vynce.asakta.cloud  # default is http://127.0.0.1:8008
  volumes:
    - sites:/home/frappe/frappe-bench/sites
    - assets-data:/home/frappe/frappe-bench/assets  # ⚠️ CRITICAL for CSS
    - synapse-data:/home/frappe/frappe-bench/sites/vynce.asakta.cloud/synapse:ro  # ⚠️ Matrix config

frontend:
  volumes:
    - sites:/home/frappe/frappe-bench/sites
    - assets-data:/home/frappe/frappe-bench/assets  # ⚠️ Shared with backend
```

**⛔ IF YOU FORGET THESE →** Matrix user creation fails, messages work only via notifications, login breaks, CSS returns 404.

### 5. Start Services

```bash
cd /srv/vynce
docker compose pull
docker compose up -d
# Wait 2 minutes
```

### 6. MariaDB Permissions

```bash
docker exec vynce-mariadb-1 mysql -u root -p${DB_PASSWORD} -e "
  CREATE USER IF NOT EXISTS 'vynce'@'%' IDENTIFIED BY '${DB_PASSWORD}';
  GRANT ALL PRIVILEGES ON *.* TO 'vynce'@'%' WITH GRANT OPTION;
  FLUSH PRIVILEGES;
"
```

### 7. Create Frappe Site

```bash
# Write common_site_config.json
cat > /tmp/common_site_config.json << EOF
{
  "db_host": "mariadb",
  "db_port": 3306,
  "db_name": "vynce",
  "db_password": "${DB_PASSWORD}",
  "redis_cache": "redis://redis-cache:6379",
  "redis_queue": "redis://redis-queue:6379",
  "redis_socketio": "redis://redis-queue:6379",
  "socketio_port": 9000,
  "mariadb_root_password": "${DB_PASSWORD}"
}
EOF
docker cp /tmp/common_site_config.json vynce-backend-1:/home/frappe/frappe-bench/sites/

# Create site
docker exec -e DB_PASSWORD=${DB_PASSWORD} vynce-backend-1 \
  bench new-site vynce.asakta.cloud \
  --install-app vynce \
  --install-app dfp_external_storage \
  --admin-password <admin-password>

# Build assets
docker exec vynce-backend-1 bench build
```

### 8. Build & Deploy SPA

```bash
cd /srv/vynce/vynce-mobile
git clone https://github.com/vineelreddy10/vynce-mobile.git .
npm install
VITE_API_URL="" npm run build    # ⚠️ MUST set VITE_API_URL="" !
docker compose up -d vynce-mobile
```

**⛔ IF `VITE_API_URL=""` IS NOT SET →** SPA login silently fails because API calls go to `http://127.0.0.1:8002`

### 9. Configure Synapse

```bash
# Generate config
docker compose run --rm synapse generate

# Create admin user
docker exec vynce-synapse-1 register_new_matrix_user \
  -c /data/homeserver.yaml \
  -u synapse_admin \
  -p <strong-password> \
  --admin \
  http://localhost:8008
```

### 10. Set Matrix Admin Token

```bash
TOKEN=$(curl -sk -X POST "https://vynce.asakta.cloud/_matrix/client/v3/login" \
  -H "Content-Type: application/json" \
  -d '{"type":"m.login.password","user":"synapse_admin","password":"<password>"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin).get('access_token',''))")

# Login to Frappe and update Matrix Settings doctype
curl -sk -X PUT "https://vynce.asakta.cloud/api/resource/Matrix%20Settings/Matrix%20Settings" \
  -H "Content-Type: application/json" \
  -d "{\"server_name\":\"vynce.asakta.cloud\",\"port\":8008,\"homeserver_status\":\"Running\",\"admin_access_token\":\"$TOKEN\"}"
```

### 11. Configure DFP External Storage

```bash
# Create S3 bucket in Garage (if not exists)
# Then create DFP record in Frappe:
# POST /api/resource/DFP%20External%20Storage
# {
#   "title": "Garage S3 Pre-Prod",
#   "type": "S3 Compatible",
#   "access_key": "<garage-key>",
#   "secret_key": "<garage-secret>",
#   "region": "garage",
#   "bucket_name": "vynce-files",
#   "endpoint": "garage:3900",
#   "secure": 0,
#   "enabled": 1,
#   "folders": [{"folder": "Home"}]
# }
```

**⛔ IF FOLDERS IS EMPTY →** Files aren't routed to S3, they stay on local disk.

### 12. Setup CI/CD Secrets

**vynce repo** (Settings → Secrets → Actions):
| Secret | Purpose |
|--------|---------|
| `GITLAB_PAT` | Clone dfp_external_storage from gitlab.asakta.com |

**vynce-mobile repo** (Settings → Secrets → Actions):
| Secret | Purpose |
|--------|---------|
| `VPS_SSH_KEY` | SSH private key for rsync deploy to VPS |

Generate deploy key:
```bash
ssh-keygen -t ed25519 -f vps_deploy_key -N ""
# Add public key to VPS: ssh-copy-id -i vps_deploy_key.pub root@VPS_IP
# Add private key as GitHub secret "VPS_SSH_KEY"
```

---

## Post-Deployment Verification

```bash
# All 3 domains
curl -sI https://vynce.asakta.cloud      # → 200
curl -sI https://vynceapp.asakta.cloud    # → 200
curl -sI https://vynce-garage.asakta.cloud # → 200

# API
curl -sk -X POST "https://vynce.asakta.cloud/api/method/login" \
  -H "Content-Type: application/json" \
  -d '{"usr":"Administrator","pwd":"<admin-pwd>"}'  # → "Logged In"

# CSS (no MIME type errors)
curl -sI https://vynce.asakta.cloud/assets/frappe/dist/css/website.bundle.*.css  # → text/css

# Synapse
curl -s https://vynce.asakta.cloud/_synapse/admin/v1/server_version  # → {"server_version":"1.155.0"}

# Registration
curl -sk -X POST "https://vynce.asakta.cloud/api/method/vynce.api.register" \
  -H "Content-Type: application/json" \
  -d '{"email":"test@test.local","password":"StrongPass1!","display_name":"Test","birth_date":"1995-06-15","gender":"Male"}'  # → {"status":"ok"}

# Matrix account creation (check Synapse for @test:vynce.asakta.cloud user)
```

**Run E2E tests:**
```bash
pip install playwright && python3 -m playwright install chromium
VYNCE_QA_BASE_URL=https://vynceapp.asakta.cloud \
VYNCE_QA_API_URL=https://vynce.asakta.cloud \
  python3 tests/e2e_deployment_test.py
# Should pass 14/14
```

---

## CI/CD Pipelines

### vynce (backend)
- **Trigger**: Push to `main` touching `vynce/**`, `Dockerfile`, `pyproject.toml`, or CI workflow
- **Action**: Build Docker image → Push to `ghcr.io/vineelreddy10/vynce-bench:latest`
- **⚠️ Has retry for Docker Hub rate limits**
- **⚠️ `bench build` runs post-deploy, not during Docker build**

### vynce-mobile (SPA)
- **Trigger**: Push to `main` touching `src/**`, `package.json`, `vite.config.ts`, or deploy workflow
- **Action**: `npm ci` → `VITE_API_URL="" npm run build` → rsync `dist/` to VPS
- **⚠️ Requires `VPS_SSH_KEY` GitHub secret**

---

## Volume Configuration (Critical!)

| Volume | Mounted To | Why |
|--------|-----------|-----|
| `assets-data` | **backend** + **frontend** at `/home/frappe/frappe-bench/assets` | Prevents CSS hash mismatch between containers |
| `synapse-data` | **backend** at `/sites/{SITE}/synapse:ro` | Backend needs `homeserver.yaml` for shared secret |
| `sites` | **backend** + **frontend** at `/home/frappe/frappe-bench/sites` | Frappe site data |

**Why `assets-data` is critical:** Frappe uses `sites/assets → /home/frappe/frappe-bench/assets` symlink. This symlink target is INSIDE the image (per-container). Without a shared volume, `bench build` in backend creates hashes that frontend doesn't have → CSS 404s.

---

## Troubleshooting — Quick Reference

| Symptom | Root Cause | Fix |
|---------|-----------|-----|
| "Connection refused" to `127.0.0.1:8008` | `SYNAPSE_HOST` not set | Add `SYNAPSE_HOST=synapse` to compose.yaml |
| Matrix user IDs as `@user:vynce.app` | `MATRIX_SERVER_NAME` not set | Add `MATRIX_SERVER_NAME=vynce.asakta.cloud` |
| SPA returns `matrix_server_url: http://127.0.0.1:8008` | `MATRIX_SERVER_URL` not set | Add `MATRIX_SERVER_URL=https://vynce.asakta.cloud` |
| CSS 404 - `website.bundle.ABC.css` not found | `assets-data` volume not shared | Mount in both backend + frontend |
| `save_interests not whitelisted` | Old code in Docker image | Rebuild image from latest commit |
| Messages go via `notification`, not `matrix` | `get_login_token()` treated as dict | Fixed in chat.py (commit `4d8a659`) |
| "Set up job" failure in CI | Docker Hub rate limits | CI has retry logic; wait and retry |
| Files not going to S3 | DFP folders empty | Add `{"folder": "Home"}` to DFP record |
| Admin API returns 500 / "IndexError" | `get_admin_token()` returns encrypted password | Fixed in `synapse_client.py` (commit `3f35cfb`) |
| Photos not showing on SPA | DFP bypass for `image_url` path | Use multipart upload instead of JSON `image_url` |
| SPA login never works | `VITE_API_URL` not set during build | Rebuild with `VITE_API_URL=""` |
| Garage Web UI shows no buckets | Wrong env vars | Use `API_BASE_URL` + `S3_ENDPOINT_URL`, mount config |
| MariaDB "Access denied" after restart | User IP changed | Grant `vynce@%` (wildcard host) |
| Bench console hangs | `run-patch` treats file as module | Use `bench --site site console < file.py` |
| Login page returns 500 | MariaDB user permissions | Check `common_site_config.json` has `db_password` |

---

## Application Code Bugs Fixed

These are already committed and won't re-occur, but document for awareness:

| Bug | File | Commit | What |
|-----|------|--------|------|
| Admin token encrypted | `synapse_client.py:26` | `3f35cfb` | `get_single_value` → `get_decrypted_password` |
| HMAC admin flag wrong | `management.py:62` | `0578359` | `"admin"` → `"true"` |
| Server name hardcoded `vynce.app` | `synapse_config.py:12` | `6697016` | Now reads `MATRIX_SERVER_NAME` env var |
| `chat.py` hardcoded `vynce.app` | `chat.py:82` | `b152e16` | Now uses `SERVER_NAME` from config |
| Registration uses broken HMAC | `api.py:110` | `f630e45` | Now uses `SynapseClient.create_user()` (Admin API) |
| `send_message` treats token as dict | `chat.py:24` | `4d8a659` | `token_resp.get("access_token")` → `access_token` directly |
| `upload_photo` no JSON fallback | `profile.py` | `73f9f96` | Added `image_url` support |

---

## Health Check Commands

```bash
# All services running
docker compose ps  # all should be "Up" or "healthy"

# Frappe site exists
docker exec vynce-backend-1 bench --site vynce.asakta.cloud list-apps

# Synapse healthy
curl -s https://vynce.asakta.cloud/_synapse/admin/v1/server_version

# Matrix users created (registration working)
TOKEN=$(docker exec vynce-backend-1 bench --site vynce.asakta.cloud execute "frappe.utils.password.get_decrypted_password" --kwargs '{"doctype":"Matrix Settings","name":"Matrix Settings","fieldname":"admin_access_token"}' 2>/dev/null | tail -1)
curl -s https://vynce.asakta.cloud/_synapse/admin/v2/users?limit=10 -H "Authorization: Bearer $TOKEN"

# DFP storage working
curl -s https://vynce.asakta.cloud/api/resource/DFP%20External%20Storage?limit=1  # should show record with enabled=1, folders not empty

# Logs
docker compose logs --tail 50 backend | grep -i error
docker compose logs --tail 50 synapse | grep -i error
```
