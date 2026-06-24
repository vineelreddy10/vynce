"""Standalone ASGI Socket.io server for Vynce real-time events.

Runs on port 3001 (configurable via VYNCE_SIO_PORT env var).
Authentication via Frappe session cookie (stored in Redis).
Redis pub/sub bridge receives events from Frappe backend.

Usage:
    python -m vynce.socketio
    # or
    uvicorn vynce.socketio:app --host 0.0.0.0 --port 3001
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import threading
from pathlib import Path
from urllib.parse import unquote

import redis.asyncio as aioredis
import socketio

# ── Configuration ────────────────────────────────────────────────────

SIO_PORT = int(os.environ.get("VYNCE_SIO_PORT", "3001"))

SITES_DIR = os.environ.get(
	"FRAPPE_SITES_DIR",
	str(Path.home() / "dev" / "galaxy" / "sites"),
)
COMMON_CONFIG_PATH = os.path.join(SITES_DIR, "common_site_config.json")
REDIS_CHANNEL = "vynce:sio"


def _get_redis_url() -> str:
	"""Read Redis URL from Frappe common_site_config.json or fall back to env."""
	try:
		with open(COMMON_CONFIG_PATH) as f:
			config = json.load(f)
		return (
			config.get("redis_cache")
			or config.get("redis_socketio")
			or "redis://127.0.0.1:13002"
		)
	except Exception:
		return os.environ.get("REDIS_URL", "redis://127.0.0.1:13002")


REDIS_URL = _get_redis_url()

# ── Socket.io Server ─────────────────────────────────────────────────

sio = socketio.AsyncServer(
	cors_allowed_origins="*",
	async_mode="asgi",
)
app = socketio.ASGIApp(sio)

# ── Session Validation ───────────────────────────────────────────────

COOKIE_SID_RE = re.compile(r"(?:^|;\s*)sid=([^;]+)", re.IGNORECASE)


def _parse_sid(cookie_header: str) -> str | None:
	"""Extract Frappe *sid* from the ``Cookie`` header."""
	m = COOKIE_SID_RE.search(cookie_header)
	if m:
		raw = m.group(1).strip()
		# Handle URL-encoded sids (rare but possible)
		if "%" in raw:
			return unquote(raw)
		return raw
	return None


async def _validate_session(sid_token: str) -> str | None:
	"""Look up Frappe session in Redis and return the user email.

	Frappe stores sessions as hash ``session:{sid}`` with fields
	``user``, ``session_id``, etc.
	Returns ``None`` when the session is missing, expired, or belongs to
	``Guest``.
	"""
	if not sid_token:
		return None
	try:
		r = aioredis.from_url(REDIS_URL, socket_connect_timeout=3)
		session_data = await r.hgetall(f"session:{sid_token}")
		await r.aclose()
		if session_data:
			user = session_data.get(b"user", b"").decode()
			if user and user != "Guest":
				return user
	except Exception:
		pass
	return None


# ── Redis Pub/Sub Listener ───────────────────────────────────────────


async def _redis_listener():
	"""Subscribe to the ``vynce:sio`` Redis channel and forward events.

	Runs in a daemon thread's event loop.  Reconnects automatically on
	connection errors.
	"""
	while True:
		try:
			r = aioredis.from_url(REDIS_URL, socket_connect_timeout=5)
			pubsub = r.pubsub()
			await pubsub.subscribe(REDIS_CHANNEL)

			async for message in pubsub.listen():
				if message["type"] != "message":
					continue
				try:
					payload = json.loads(message["data"])
				except (json.JSONDecodeError, TypeError):
					continue

				event = payload.get("event")
				data = payload.get("data", {})
				if not event:
					continue

				# Route to a specific user (most common case)
				user = payload.get("user")
				if user:
					await sio.emit(event, data, room=f"user:{user}")

				# Route to a named room (e.g. ``room:<room_id>``)
				room = payload.get("room")
				if room:
					await sio.emit(event, data, room=room)

		except asyncio.CancelledError:
			break
		except Exception as exc:
			print(f"[socketio] Redis listener error: {exc}")
			await asyncio.sleep(5)


def _start_redis_listener():
	"""Run the Redis listener in a daemon background thread."""
	loop = asyncio.new_event_loop()
	asyncio.set_event_loop(loop)
	try:
		loop.run_until_complete(_redis_listener())
	except Exception:
		pass


# Start the listener immediately on import so it works with both
# ``python -m vynce.socketio`` and ``uvicorn vynce.socketio:app``.
_listener_thread = threading.Thread(target=_start_redis_listener, daemon=True)
_listener_thread.start()

# ── Socket.io Event Handlers ─────────────────────────────────────────


@sio.event
async def connect(sid, environ, auth):
	"""Authenticate and join the user to ``user:<email>``.

	Authentication is attempted in this order:

	1. ``auth`` dict from the Socket.io handshake (sent by
	   ``socket.io-client`` with ``auth: { user: … }``).
	2. Frappe ``sid`` cookie in the HTTP request headers.
	"""
	user: str | None = None

	# 1. Auth dict from handshake
	if auth and isinstance(auth, dict):
		user = auth.get("user") or None

	# 2. Cookie fallback
	if not user:
		cookie = environ.get("HTTP_COOKIE", "")
		sid_token = _parse_sid(cookie)
		if sid_token:
			user = await _validate_session(sid_token)

	if not user:
		raise socketio.exceptions.ConnectionRefusedError("unauthorized")

	await sio.save_session(sid, {"user": user})
	await sio.enter_room(sid, f"user:{user}")
	print(f"[socketio] {user} connected (sid={sid})")


@sio.event
async def disconnect(sid):
	"""Cleanup is handled by session expiry; just log."""
	try:
		session = await sio.get_session(sid)
		if session:
			print(f"[socketio] {session['user']} disconnected (sid={sid})")
	except Exception:
		pass


@sio.event
async def typing(sid, data):
	"""Broadcast typing indicator to room members (excluding sender).

	Expected *data* shape: ``{ "room_id": str, "is_typing": bool }``
	"""
	session = await sio.get_session(sid)
	user = session["user"]
	room_id = data.get("room_id")
	is_typing = data.get("is_typing", False)

	if not room_id:
		return

	await sio.emit(
		"typing",
		{
			"user": user,
			"room_id": room_id,
			"is_typing": is_typing,
		},
		room=f"room:{room_id}",
		skip_sid=sid,
	)


@sio.event
async def join_room(sid, room_id):
	"""Join a named Socket.io room (e.g. ``room:<match_room_id>``)."""
	if not room_id:
		return
	await sio.enter_room(sid, f"room:{room_id}")
	print(f"[socketio] {sid} joined room:{room_id}")


# ── Entry Point ──────────────────────────────────────────────────────


def main():
	"""Run the server via ``python -m vynce.socketio``."""
	import uvicorn

	print(f"[socketio] starting on 0.0.0.0:{SIO_PORT} (Redis: {REDIS_URL})")
	uvicorn.run(
		"vynce.socketio:app",
		host="0.0.0.0",
		port=SIO_PORT,
		reload=False,
		log_level="info",
	)


if __name__ == "__main__":
	main()
