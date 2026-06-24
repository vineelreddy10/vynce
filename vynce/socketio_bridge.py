"""Bridge between Frappe backend and the standalone Socket.io server.

Calls ``publish_sio_event()`` from Frappe handlers to emit real-time
events over Redis pub/sub.  The ``vynce.socketio`` server subscribes to
the same channel and forwards events to connected clients.
"""
from __future__ import annotations

import json

import frappe

REDIS_CHANNEL = "vynce:sio"


def publish_sio_event(
	event: str,
	data: dict,
	*,
	user: str | None = None,
	room: str | None = None,
) -> None:
	"""Publish a real-time event to the Socket.io server.

	Args:
	    event: Event name (``new_like``, ``new_match``, ``notification``, …).
	    data: JSON-serialisable payload dict.
	    user: If set, route to ``user:<email>`` room.
	    room: If set, route to the given room name.
	"""
	try:
		payload = json.dumps({
			"event": event,
			"data": data,
			"user": user,
			"room": room,
		})
		r = frappe.cache.redis_client
		if r:
			r.publish(REDIS_CHANNEL, payload)
	except Exception as exc:
		frappe.logger().error(
			"socketio_bridge: failed to publish %s: %s", event, exc
		)
