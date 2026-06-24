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
              │  (Docker) │                 ┌──────▼──────┐
              └───────────┘                 │   Redis     │
                                            │  (Frappe)   │
                                            └─────────────┘
```

**Two parallel channels:**
- `matrix-js-sdk` → `/_matrix/*` → **Synapse** — messages, sync, E2EE, federation
- **Frappe API** → `/api/*` → **Frappe** — profiles, matching, discovery, app features
- **Frappe Socket.io** — typing indicators, read receipts, presence, notifications

**Deployment model:**
- **Synapse** — runs as a bare Python process, managed by `docker/synapse/*.sh` scripts
- **PostgreSQL** — runs in Docker (`postgres:16-alpine`), managed by Docker
- **Frappe + Socket.io + Redis** — managed by bench as before

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
| `vynce/matrix/install.py` | Setup instructions (no longer manages Synapse via pip) |
| `docker/synapse/setup.sh` | One-time setup: start PostgreSQL, configure Synapse, create admin user |
| `docker/synapse/start.sh` | Start Synapse + PostgreSQL |
| `docker/synapse/stop.sh` | Stop Synapse process |
| `docker/synapse/status.sh` | Check Synapse + PostgreSQL health |
| `sites/{site}/synapse/` | Synapse config, media, logs |

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

**Via Docker script:**
```bash
./docker/synapse/status.sh
```

### Starting

```bash
# First time setup (creates PostgreSQL container, generates config, starts everything)
./docker/synapse/setup.sh

# After first time (start Synapse + PostgreSQL)
./docker/synapse/start.sh
```

### Stopping

```bash
./docker/synapse/stop.sh
```

PostgreSQL stays running. To stop it:
```bash
docker stop synapse-db
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

Returns `room_id`, `users`, and `tokens` — the frontend uses the first token for C2S API calls.

### Listing Rooms with a Token

```bash
curl "http://127.0.0.1:8002/api/method/vynce.matrix.frappe_api.list_rooms_for_token?token=<access_token>"
```

### Getting Room Detail with a Token

```bash
curl "http://127.0.0.1:8002/api/method/vynce.matrix.frappe_api.get_room_detail?room_id=<room_id>&token=<access_token>"
```

### Getting the Admin Token

```bash
cat sites/test.localhost/synapse/admin_credentials.json
```

### Storing the Admin Token in Frappe

```bash
bench --site test.localhost console
>>> frappe.db.set_single_value("Matrix Settings", "admin_access_token", "<token>")
>>> frappe.db.set_single_value("Matrix Settings", "homeserver_status", "Running")
>>> frappe.db.commit()
```

## Troubleshooting

### "500 Internal Server Error" on Admin API

**Symptom:** `/_synapse/admin/v2/users` and `/_synapse/admin/v1/rooms` return 500.

**Cause on SQLite:** Synapse 1.155.0 has a SQLite compatibility bug (`IndexError: index out of range`).

**Fix:** Use PostgreSQL (current setup). All Admin APIs work correctly with PostgreSQL.
The Frappe API layer (`frappe_api.py`) uses shared secret registration (not Admin API)
for user creation, and C2S endpoints for rooms/messages — these work regardless of
the database backend.

### "Failed to get room detail" / Messages not loading

**Cause:** The token passed to `get_room_detail` doesn't belong to a member of that room.

**Fix:** The frontend should pass a test user's token (returned from `create_test_room`).
If using the admin token, the admin user must be a member of the room first.

### Synapse won't start

Check the log:
```bash
tail -50 sites/test.localhost/synapse/homeserver.log
```

Common issues:
- **Port 8008 in use** — `lsof -ti:8008 | xargs kill`
- **Invalid config** — run `python -m synapse.app.homeserver --config-path ...` to see errors
- **Old PID file** — `rm sites/test.localhost/synapse/homeserver.pid`
- **PostgreSQL not running** — `docker ps | grep synapse-db`

### PostgreSQL issues

```bash
# Check if PostgreSQL container is running
docker ps | grep synapse-db

# Check PostgreSQL logs
docker logs synapse-db

# Restart PostgreSQL
docker restart synapse-db

# If locale is wrong, recreate the container
docker rm -f synapse-db
docker volume rm synapse-pgdata
./docker/synapse/setup.sh
```

### "Registration has been disabled"

This is expected — C2S registration is disabled. All users are created via:
- Shared secret registration (`POST /_synapse/admin/v1/register`)
- Admin API (`POST /_synapse/admin/v2/users/{userId}`)

## Upgrade Synapse

```bash
cd /home/vineel/dev/galaxy
env/bin/pip install --upgrade matrix-synapse
```

## Database

Synapse uses **PostgreSQL** running in Docker (`postgres:16-alpine`).
The database is named `synapse`, owned by user `synapse`, exposed on `127.0.0.1:5432`.

Data persists in the `synapse-pgdata` Docker volume:
```bash
docker volume inspect synapse-pgdata
```

To reset the database (loses all users, rooms, messages):
```bash
./docker/synapse/setup.sh  # rebuilds from scratch
```

## Frontend: Chat Hook (`useChat`)

**Location**: `vynce-mobile/src/hooks/useChat.ts`

### Architecture

```
useChat(user)
  │
  ├── Init effect [user, mountKey]                         ← boots Matrix clients per room
  │     ├─ getMatrixCredentials() → {baseUrl, token, user}
  │     ├─ getMatchRooms()        → [{room_id, ...}]
  │     └─ createClient() + startClient({initialSyncLimit: 20})
  │
  ├── Timeline effect (stable, never re-registers)         ← listens for live messages
  │     └─ MatrixClient "Room.timeline" → m.room.message
  │          ├─ seenMessagesRef (in-memory set, 500 cap)   ← app-level dedup
  │          └─ setRooms (functional update)
  │               ├─ event_id exact match → skip
  │               └─ sender + body match → replace existing (local→server upgrade)
  │
  └── Returns: { rooms, activeRoom, sendMessage, sendTyping, ... }
```

### Duplicate Message Prevention

Matrix SDK fires **two** `Room.timeline` events when sending a message:
1. **Local echo** — event_id starts with `~` (pending)
2. **Server confirmation** — event_id starts with `$` (different ID)

The chat hook prevents duplicates at 3 levels:

| Level | Mechanism | Catches |
|-------|-----------|---------|
| **App-level** | `seenMessagesRef` — Set of `sender\|body\|eventId` with 500 cap | Same event arriving twice in the same JS session |
| **event_id match** | `r.messages.some(m → m.event_id === eventId)` | Redundant same-ID events |
| **sender+body match + local-echo guard** | `findIndex(m → m.body === body && m.sender === sender && m.event_id.startsWith("~"))` then **replace** | Local echo `~id` replaced by server `$id` |

The `startsWith("~")` guard is critical — without it, sending the same text twice (e.g., "hi" then "hi" again) would silently replace the old message instead of appending a new one.

### Stable Listener Registration

The timeline listener attached to each `MatrixClient` is registered **once per room** (tracked via `timelineRegisteredRef`). Not re-registered on every rooms state change — preventing:
- Lost events between cleanup and re-registration
- Multiple parallel listeners accumulating per room
- Infinite loops (register → timeline fires → setRooms → re-run effect → register again)

### Send Flow

```
sendMessage(roomId, text)
  └── client.sendTextMessage(roomId, text)
        └── SDK fires Room.timeline (local echo)
        └── SDK fires Room.timeline (server echo) → replaces local entry
```
