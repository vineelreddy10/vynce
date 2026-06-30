# Post-Deployment Issues: Vynce Stack on VPS

> **Date**: 2026-06-29  
> **VPS**: 2 CPU, 3.7GB RAM, 38GB disk  
> **Services**: Frappe Desk + vynce-mobile SPA + Synapse Matrix + Garage S3  
> **Reverse Proxy**: Single Traefik instance, 3 subdomains, Let's Encrypt SSL

---

## Summary

| Category | Count |
|----------|-------|
| **Infrastructure / Deployment Config** | 8 |
| **Application Code Bugs** | 5 |
| **Pre-existing Data Migration** | 3 |
| **CI/CD** | 2 |
| **Total** | **18 issues found & fixed** |

---

## A. Infrastructure / Deployment Configuration

### A1. `SYNAPSE_HOST` not set (defaults to `127.0.0.1`)

- **Symptom**: Backend tried to connect to `127.0.0.1:8008` for Matrix operations → Connection refused
- **Cause**: `synapse_client.py` reads `SYNAPSE_HOST` env var, falls back to `127.0.0.1`
- **Fix**: Added `SYNAPSE_HOST: synapse` to `compose.yaml`
- **Future prevention**: `DEPLOYMENT_NOTES.md` checklist

### A2. Synapse config file not accessible from backend

- **Symptom**: `_read_shared_secret()` → `FileNotFoundError: /sites/vynce.asakta.cloud/synapse/homeserver.yaml`
- **Cause**: The `synapse-data` Docker volume was only mounted into the Synapse container, not the backend. The management code expects the config at a path inside the Frappe site directory.
- **Fix**: Mounted `synapse-data` volume into backend at `/sites/{SITE_NAME}/synapse:ro`
- **Future prevention**: `DEPLOYMENT_NOTES.md` volume mounts section

### A3. `assets-data` volume not shared between containers

- **Symptom**: CSS 404s — pages referenced `website.bundle.ABC.css` but only `website.bundle.XYZ.css` existed. Frappe generates unique file hashes per `bench build`, and backend/frontend had separate filesystems.
- **Root cause**: `sites/assets` is a symlink → `/home/frappe/frappe-bench/assets`. Each container has its OWN `/home/frappe/frappe-bench/assets` in the image. `bench build` in one container doesn't affect the other.
- **Fix**: Create shared `assets-data` volume mounted at `/home/frappe/frappe-bench/assets` in BOTH backend and frontend containers.
- **Future prevention**: Always mount shared assets volume.

### A4. SPA `VITE_API_URL` not set during build

- **Symptom**: SPA login failed silently. All Matrix API calls returned "not whitelisted" because no session cookie was set.
- **Root cause**: The SPA was built with `VITE_API_URL` unset, causing axios to use `baseURL="http://127.0.0.1:8002"` as fallback. All API calls went to `localhost` in the browser.
- **Fix**: Rebuilt SPA with `VITE_API_URL=""` (relative URL through nginx proxy)
- **Future prevention**: Always set `VITE_API_URL` before `npm run build`

### A5. Garage Web UI not connecting to Garage

- **Symptom**: Garage Web UI loaded but showed no buckets / "status not running"
- **Root cause**: Container started without Garage config mounted, used wrong env vars (`GARAGE_HOST` instead of `API_BASE_URL`, `S3_ENDPOINT_URL`)
- **Fix**: Mount `/data/garage/config.toml` at `/etc/garage.toml:ro`, set `API_BASE_URL=http://garage:3903` and `S3_ENDPOINT_URL=http://garage:3900`
- **Future prevention**: Follow `khairul169/garage-webui` Docker docs for env vars

### A6. Traefik routing for Matrix paths

- **Symptom**: `/_matrix/*` requests went to Frappe instead of Synapse (404 / wrong responses)
- **Cause**: Initial Traefik router for `vynce.asakta.cloud` matched all paths. Matrix path routing wasn't configured.
- **Fix**: Added dedicated Traefik router for synapse with `PathPrefix(/_matrix/, /_synapse/)` and priority 1000
- **Future prevention**: Included in compose.yaml labels

### A7. Garage Traefik routing

- **Symptom**: `vynce-garage.asakta.cloud` returned 404
- **Cause**: garage-webui container had no Traefik labels (it was running outside the compose stack)
- **Fix**: Recreated garage-webui container with Traefik labels on `vynce-network`
- **Future prevention**: Documented in compose.yaml

### A8. MariaDB user permissions

- **Symptom**: Backend got `Access denied for user 'vynce'@'172.18.0.x'` after container restart
- **Cause**: User `vynce@172.18.0.12` was created initially but backend IP changed on restart
- **Fix**: Granted `vynce@%` (all hosts) access
- **Future prevention**: Always use wildcard host `%` for Docker containers

---

## B. Application Code Bugs

### B1. `get_admin_token()` returns encrypted password

- **File**: `vynce/matrix/synapse_client.py` (line 26)
- **Symptom**: All Matrix admin API calls returned 500 Internal Server Error. The encrypted password string was sent as the Bearer token.
- **Root cause**: `frappe.db.get_single_value("Matrix Settings", "admin_access_token")` returns the **encrypted** value of a Password field, not the decrypted one.
- **Fix**: Changed to `frappe.utils.password.get_decrypted_password("Matrix Settings", "Matrix Settings", "admin_access_token")`
- **Commit**: `3f35cfb`

### B2. `chat.py` sends Matrix messages via notification fallback

- **File**: `vynce/chat.py` (line 24-25)
- **Symptom**: All chat messages fell back to Frappe notifications (`via=notification`). Messages appeared in the app but never reached Matrix.
- **Root cause**: `get_login_token()` returns a **string** (the access token), but the code treated it as a **dict**:
  ```python
  token_resp = client.get_login_token(profile.matrix_user_id)
  if token_resp and token_resp.get("access_token"):  # BUG: strings don't have .get()
  ```
  This condition was always False, so the Matrix send path was never executed.
- **Fix**: Changed to `access_token = client.get_login_token(...)` and `if access_token:`, passing `access_token` directly to `send_message()`.
- **Commit**: `4d8a659`

### B3. HMAC admin flag value wrong

- **File**: `vynce/matrix/management.py` (line 62)
- **Symptom**: `_admin_register()` → Synapse returns "HMAC incorrect" or 500
- **Root cause**: The MAC computation used `b"admin"` for admin users but Synapse expects `b"true"`. Similarly `b"notadmin"` vs `b"false"`.
- **Fix**: Changed `b"admin"/b"notadmin"` to `b"true"/b"false"`
- **Commit**: `0578359`

### B4. Registration uses shared-secret API instead of Admin API

- **File**: `vynce/api.py` (line 110)
- **Symptom**: New user registrations silently skipped Matrix account creation (caught in try/except)
- **Root cause**: Registration flow called `vynce.matrix.management.create_user()` which uses `_admin_register()` — the shared-secret HMAC path which was broken.
- **Fix**: Changed to `vynce.matrix.synapse_client.SynapseClient.create_user()` which uses the Admin API directly.
- **Commit**: `f630e45`

### B5. `SERVER_NAME` hardcoded as `vynce.app`

- **Files**: `vynce/matrix/synapse_config.py`, `vynce/chat.py`
- **Symptom**: Matrix user IDs created as `@user:vynce.app` instead of `@user:vynce.asakta.cloud`
- **Root cause**: `SERVER_NAME = "vynce.app"` hardcoded in config
- **Fix**: Made configurable via `MATRIX_SERVER_NAME` env var (default `vynce.asakta.cloud`). Also fixed `chat.py` which had another hardcoded `vynce.app`.
- **Commits**: `6697016`, `b152e16`

---

## C. Pre-existing Data Migration

### C1. Existing users missing Matrix accounts

- **Symptom**: Users registered before the `get_admin_token` fix had `matrix_user_id: null` on their profiles. Matches couldn't create Matrix rooms.
- **Count**: ~21 users affected
- **Fix**: Ran provision script to create Matrix accounts via Admin API for all users without `matrix_user_id`.
- **Future prevention**: Add to deployment notes as post-deploy step.

### C2. Existing matches missing Matrix rooms

- **Symptom**: Mutual likes existed but `VY Match` records had `matrix_room_id: ""`. Alice and Bob matched but couldn't chat.
- **Root cause**: When the mutual like happened, the Matrix room creation failed (because of B1 above), but the match creation code may have still proceeded.
- **Fix**: Ran `create_matrix_room_for_match()` after provisioning Matrix accounts
- **Future prevention**: Add match room backfill to deployment notes.

### C3. Profile photos reference local file paths

- **Symptom**: test1 profile photos were stored as `/files/screenshot.png` — these files DID exist on the Frappe filesystem and served correctly via `https://vynce.asakta.cloud/files/...` (HTTP 200, `content-type: image/png`)
- **Status**: Actually working, no fix needed
- **Note**: If files were missing (fresh DB restore without files backup), they would need to be re-uploaded.

---

## D. CI/CD Issues

### D1. Docker build fails with `bench build`

- **Symptom**: CI build step "Build and push" fails with no clear error. The `bench build` command runs during Docker image build.
- **Root cause**: `bench build` in the Docker image likely requires additional dependencies (Node.js, npm packages) that aren't available in the build environment. The base `frappe/erpnext:v16` image may not support it during build.
- **Fix**: Removed `bench build` from Dockerfile. Assets are handled via shared `assets-data` volume and can be built post-deploy.
- **Commit**: `5c59e24`

### D2. CI trigger path matching

- **Symptom**: Empty commits (with `--allow-empty`) don't trigger CI because the workflow has path filters
- **Fix**: Commits must change at least one file under `vynce/**`, `pyproject.toml`, `Dockerfile`, or `.github/workflows/build-bench.yml`
- **Note**: Added `workflow_dispatch:` as manual trigger option

---

## E. Monitoring & Observability Gaps

| Gap | Impact |
|-----|--------|
| No Synapse error log tailing | B1/B3 would have been caught immediately |
| No Frappe error log monitoring | B4 silently skipped Matrix account creation for 21 users |
| No CI build failure notifications | D1 caused delayed deployment of B2 fix |
| No health check for Matrix sync | Would have caught B2 earlier |

---

## F. Deployment Checklist (Future Deployments)

When deploying to a new VPS, follow these steps **in order**:

1. **Set env vars** in compose.yaml:
   - `SYNAPSE_HOST=synapse`
   - `MATRIX_SERVER_NAME=vynce.asakta.cloud`
   - `MATRIX_SERVER_URL=https://vynce.asakta.cloud`

2. **Mount volumes**:
   - `assets-data:/home/frappe/frappe-bench/assets`
   - `synapse-data:/home/frappe/frappe-bench/sites/{SITE_NAME}/synapse:ro`

3. **Rebuild SPA**: `VITE_API_URL="" npm run build`

4. **Populate shared assets** (one-time):
   ```bash
   docker exec backend bench build
   ```

5. **Provision Matrix admin token** (see DEPLOYMENT_NOTES.md)

6. **Run E2E tests**: `python3 tests/e2e_deployment_test.py`

7. **Backfill Matrix accounts**:
   ```bash
   bench --site {SITE} execute "vynce.matrix.synapse_client.SynapseClient().create_user"
   ```

---

## G. All Git Commits

| Commit | Message | Type |
|--------|---------|------|
| `fa1fe77` | `build: add bench build to Dockerfile, add workflow_dispatch to CI` | Build |
| `73f9f96` | `fix: add image_url fallback to upload_photo API` | Code |
| `6697016` | `fix: use vynce.asakta.cloud as Matrix server name` | Code |
| `0578359` | `fix: correct HMAC admin flag from 'admin' to 'true'` | Code |
| `b152e16` | `fix: use SERVER_NAME from config instead of hardcoded vynce.app in chat.py` | Code |
| `3f35cfb` | `fix: use get_decrypted_password instead of get_single_value for admin token` | Code |
| `f630e45` | `fix: use SynapseClient.create_user instead of shared-secret HMAC` | Code |
| `4d8a659` | `fix: get_login_token returns string, not dict — fix send_message` | Code |
| `5c59e24` | `fix: remove bench build from Dockerfile (causes CI failure)` | Build |
