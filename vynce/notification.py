import frappe, json
from frappe import _


@frappe.whitelist()
def get_notifications(page: int = 1, page_size: int = 50) -> list:
	"""Return current user's notifications sorted by created_at desc, unread first."""
	user = frappe.session.user
	if user == "Guest":
		frappe.throw("Not logged in", frappe.AuthenticationError)

	notifications = frappe.get_all(
		"VY Notification",
		filters={"user": user},
		fields=["name", "type", "title", "body", "data", "is_read", "created_at"],
		order_by="is_read asc, created_at desc",
	)

	start = (page - 1) * page_size
	end = start + page_size
	return notifications[start:end]


@frappe.whitelist()
def mark_read(notification_id: str) -> dict:
	"""Mark a single notification as read."""
	user = frappe.session.user
	if user == "Guest":
		frappe.throw("Not logged in", frappe.AuthenticationError)

	if not frappe.db.exists("VY Notification", notification_id):
		frappe.throw("Notification not found")

	notif = frappe.get_doc("VY Notification", notification_id)
	if notif.user != user:
		frappe.throw("Not your notification")

	notif.is_read = 1
	notif.save(ignore_permissions=True)
	frappe.db.commit()

	return {"ok": True}


@frappe.whitelist()
def mark_all_read() -> dict:
	"""Mark all current user's notifications as read."""
	user = frappe.session.user
	if user == "Guest":
		frappe.throw("Not logged in", frappe.AuthenticationError)

	frappe.db.sql("""
		UPDATE `tabVY Notification`
		SET is_read = 1
		WHERE user = %s AND is_read = 0
	""", user)
	frappe.db.commit()

	return {"ok": True}


def send_notification(user: str, ntype: str, title: str, body: str, data: dict | None = None):
	"""Create a VY Notification doc for the given user.

	Args:
	    user: The recipient Frappe user ID.
	    ntype: Notification type (Like, Match, Message, Event, System).
	    title: Notification title.
	    body: Notification body text.
	    data: Optional JSON-serializable dict (e.g. {"match_id": "..."}).
	"""
	notif = frappe.get_doc({
		"doctype": "VY Notification",
		"user": user,
		"type": ntype,
		"title": title,
		"body": body,
		"data": json.dumps(data) if data else None,
		"created_at": frappe.utils.now(),
	})
	notif.insert(ignore_permissions=True)

	# Emit real-time notification event
	try:
		from .socketio_bridge import publish_sio_event
		publish_sio_event("notification", {
			"id": notif.name,
			"type": ntype,
			"title": title,
			"body": body,
			"data": data,
			"created_at": str(notif.created_at or frappe.utils.now()),
		}, user=user)
	except Exception:
		pass

	return notif


@frappe.whitelist()
def register_device_token(token: str, platform: str) -> dict:
	"""Register FCM/APNs device token for push notifications (stub)."""
	user = frappe.session.user
	if user == "Guest":
		frappe.throw("Not logged in", frappe.AuthenticationError)

	profile = frappe.get_doc("VY User Profile", {"user": user})
	if not profile:
		frappe.throw("User profile not found")

	tokens = json.loads(profile.get("device_tokens") or "{}")
	tokens[platform] = token
	profile.db_set("device_tokens", json.dumps(tokens))

	return {"ok": True}
