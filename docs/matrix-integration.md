# Matrix Integration — Architecture & Operations

## Architecture

```
                    ┌──────────────────────────────────────────┐
                    │          Matrix JS SDK (Frontend)         │
                    │  matrix-js-sdk → /_matrix/* → Synapse    │
                    │  Frappe API  → /api/* → Frappe           │
                    │  Socket.io   → /socket.io → Frappe       │
                    └────────┬──────────────┬──────────────────┘
                             │              │
              ┌──────────────┼──────────────┼───────────────┐
              │    Nginx     │              │               │
              │  /_matrix/*  │  /api/*      │  /socket.io   │
              │  → :8008     │  → :8002     │  → :9002      │
              └──────┬───────┴──────┬───────┴──────┬────────┘
                     │              │              │
              ┌──────▼────┐  ┌─────▼─────┐  ┌─────▼──────┐
              │  Synapse  │  │  Frappe   │  │  Socket.io  │
              │  :8008    │  │  :8002    │  │  Node.js    │
              │  Matrix   │  │  WSGI     │  │  (Frappe)   │
              │  C2S/E2EE │  │  API      │  │             │
              └──────┬────┘  │  Auth     │  │  Realtime   │
                     │       │  Business │  │  Events     │
              ┌──────▼────┐  └───────────┘  └──────┬──────┘
              │ PostgreSQL│                        │
              │  (or      │                 ┌──────▼──────┐
              │   SQLite) │                 │   Redis     │
              └───────────┘                 │  (Frappe)   │
                                            └─────────────┘
```

**Two parallel channels:**
- `matrix-js-sdk` → `/_matrix/*` → **Synapse** — messages, sync, E2EE, federation
- **Frappe API** → `/api/*` → **Frappe** — profiles, matching, discovery, app features
- **Frappe Socket.io** — typing indicators, read receipts, presence, notifications

## Files

| File | Purpose |
|------|---------|
| `vynce/matrix/synapse_config.py` | Generates `homeserver.yaml`, signing keys, log config |
| `vynce/matrix/synapse_client.py` | HTTP client for Synapse APIs |
| `vynce/matrix/management.py` | User creation via shared secret, admin token management |
| `vynce/matrix/status.py` | Health checks: process, API, PostgreSQL, heartbeat |
| `vynce/matrix/frappe_api.py` | Frappe whitelisted endpoints (status, users, rooms) |
| `vynce/matrix/realtime.py` | Frappe Socket.io events (typing, read receipts, presence) |
| `vynce/matrix/tasks.py` | Scheduled heartbeat task |
| `vynce/matrix/install.py` | `after_install` hook: installs/configures/starts Synapse |
| `Procfile` (bench root) | `synapse` entry for `bench start` |
| `sites/{site}/synapse/` | Synapse config, database, media, logs |

## Key Doctypes

- **Matrix Settings** (single) — admin token, status, port, heartbeat
- **Matrix Room** — room metadata (linked from VY Match)

## Operations

### Status Check

**Via Frappe API:**
```bash
curl http://127.0.0.1:8002/api/method/vynce.matrix.status.full_status
```

**Via bench console:**
```bash
bench --site test.localhost console
>>> from vynce.matrix.status import get_status
>>> get_status()
```

### Starting / Stopping

**All services via Procfile:**
```bash
cd /home/vineel/dev/galaxy
bench start               # Start everything (Frappe, Synapse, Socket.io, Redis, Workers)
bench start synapse       # Start only Synapse
```

**Manual start (if not using Procfile):**
```bash
cd /home/vineel/dev/galaxy
env/bin/python -m synapse.app.homeserver \
  --config-path sites/test.localhost/synapse/homeserver.yaml
```

**Stop:**
```bash
kill $(cat sites/test.localhost/synapse/homeserver.pid)
# or: bench start (Ctrl+C)
```

### Creating Users

**Via Frappe API (test user):**
```bash
curl http://127.0.0.1:8002/api/method/vynce.matrix.frappe_api.create_test_user
```

**Via bench console:**
```bash
bench --site test.localhost console
>>> from vynce.matrix.management import create_user
>>> create_user("alice", "mypassword")
```

### Creating a Test Room

**Via Frappe API:**
```bash
curl "http://127.0.0.1:8002/api/method/vynce.matrix.frappe_api.create_test_room?name=MyRoom"
```

### Getting the Admin Token

```bash
bench --site test.localhost console
>>> frappe.db.get_single_value("Matrix Settings", "admin_access_token")
```

### Resetting the Admin User

```bash
bench --site test.localhost console
>>> from vynce.matrix.management import get_admin_token
>>> get_admin_token()
```

## Troubleshooting

### "500 Internal Server Error" on Admin API

**Symptom:** `/_synapse/admin/v2/users` and `/_synapse/admin/v1/rooms` return 500 with SQLite.

**Cause:** Synapse 1.155.0 has a SQLite compatibility bug (`IndexError: index out of range`) on Admin API endpoints.

**Fix:** Either:
1. **Use shared secret registration** (works) — `/_synapse/admin/v1/register`
2. **Switch to PostgreSQL** — see below
3. The Frappe API layer handles this automatically — `create_test_room` and `create_test_user` now use the shared secret registration

### Enabling PostgreSQL

1. Install PostgreSQL:
   ```bash
   sudo apt install postgresql postgresql-client libpq-dev
   sudo systemctl start postgresql
   ```

2. Create database and user:
   ```bash
   sudo -u postgres psql -c "CREATE DATABASE synapse_vynce;"
   sudo -u postgres psql -c "CREATE USER synapse WITH PASSWORD 'synapse';"
   sudo -u postgres psql -c "GRANT ALL ON DATABASE synapse_vynce TO synapse;"
   ```

3. Update `homeserver.yaml`:
   ```yaml
   database:
     name: psycopg2
     args:
       user: synapse
       password: synapse
       database: synapse_vynce
       host: localhost
       port: 5432
   ```

4. Restart Synapse:
   ```bash
   kill $(cat sites/test.localhost/synapse/homeserver.pid)
   # Start again
   ```

### Synapse won't start

Check the log:
```bash
tail -50 sites/test.localhost/synapse/homeserver.log
```

Common issues:
- **Port 8008 in use** — `lsof -ti:8008 | xargs kill`
- **Invalid config** — run `python -m synapse.app.homeserver --config-path ...` to see errors
- **Old PID file** — `rm sites/test.localhost/synapse/homeserver.pid`

### "Registration has been disabled"

This is expected — C2S registration is disabled. All users are created via:
- Shared secret registration (`POST /_synapse/admin/v1/register`)
- Admin API (`POST /_synapse/admin/v2/users/{userId}`) — when PostgreSQL is available

## Upgrade Synapse

```bash
cd /home/vineel/dev/galaxy
env/bin/pip install --upgrade matrix-synapse
```

## Database

Synapse uses SQLite by default at `sites/{site}/synapse/homeserver.db`.
For production, switch to PostgreSQL as described above.

The `_get_database_config()` function in `synapse_config.py` auto-detects
PostgreSQL availability — if it can connect, it uses PostgreSQL; otherwise
it falls back to SQLite.

## After Install

When you run `bench --site test.localhost migrate` or the app's
`after_install` hook fires, the following happens:

1. `vynce.install.after_install()` runs
2. Checks if `matrix-synapse` is installed — installs via pip if not
3. Generates `sites/{site}/synapse/homeserver.yaml` with signing keys
4. Starts the Synapse process
5. Creates the `synapse_admin` user via shared secret registration
6. Adds Synapse to the bench Procfile
7. Seeds 30 interests into VY Interest doctype
