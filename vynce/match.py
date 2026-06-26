import frappe, json
from datetime import date
from .utils import calculate_age


def check_and_create_match(from_user: str, to_user: str):
	"""Check if to_user already liked from_user. If so, create a match."""
	if not frappe.db.exists("VY Like", {
		"from_user": to_user,
		"to_user": from_user,
		"like_type": ["in", ["Like", "Super Like"]],
	}):
		return  # No reciprocal like yet

	if frappe.db.exists("VY Match", {
		"user_1": ["in", [from_user, to_user]],
		"user_2": ["in", [from_user, to_user]],
		"is_active": 1,
	}):
		return  # Already matched

	# Create match (ensure consistent ordering)
	user_1, user_2 = sorted([from_user, to_user])
	match = frappe.get_doc({
		"doctype": "VY Match",
		"user_1": user_1,
		"user_2": user_2,
		"matched_at": frappe.utils.now(),
		"is_active": 1,
	})
	match.insert(ignore_permissions=True)
	frappe.db.commit()

	# Create Matrix room for the matched pair
	create_matrix_room_for_match(match.name)

	# Notify both users
	from .notification import send_notification
	for u, other in [(from_user, to_user), (to_user, from_user)]:
		other_profile = frappe.db.get_value("VY User Profile", {"user": other}, "display_name")
		send_notification(
			user=u,
			ntype="Match",
			title="It's a Match! 💫",
			body=f"You matched with {other_profile or other}",
			data={"match_id": match.name, "user": other},
		)

	# Emit real-time event to both users
	from .socketio_bridge import publish_sio_event
	for u in (from_user, to_user):
		publish_sio_event("new_match", {
			"match_id": match.name,
			"other_user": to_user if u == from_user else from_user,
		}, user=u)

	frappe.db.commit()
	return match.name


def create_matrix_room_for_match(match_name: str):
	"""Create a Matrix room for a matched pair using Synapse C2S API.

	Uses the C2S createRoom endpoint (via a user's access token) instead of
	the Admin API, since some Synapse versions don't support
	POST /_synapse/admin/v1/rooms.
	"""
	match = frappe.get_doc("VY Match", match_name)
	u1 = frappe.get_doc("VY User Profile", {"user": match.user_1})
	u2 = frappe.get_doc("VY User Profile", {"user": match.user_2})

	if not u1.matrix_user_id or not u2.matrix_user_id:
		frappe.logger().warning(
			f"Cannot create Matrix room for {match_name}: "
			f"missing matrix_user_id for user_1={bool(u1.matrix_user_id)} user_2={bool(u2.matrix_user_id)}"
		)
		return

	try:
		from vynce.matrix.synapse_client import SynapseClient
		client = SynapseClient()

		# Get an access token for user_1 to create the room via C2S API
		creator_token = client.get_login_token(u1.matrix_user_id)
		if not creator_token:
			frappe.logger().error(f"Cannot get login token for {u1.matrix_user_id}")
			return

		# Create room via C2S createRoom endpoint (user_1 creates, invites user_2)
		room = client._c2s_request(
			"POST",
			"/_matrix/client/v3/createRoom",
			{
				"name": f"{u1.display_name} & {u2.display_name}",
				"preset": "trusted_private_chat",
				"is_direct": True,
				"invite": [u2.matrix_user_id],
			},
			token=creator_token,
		)

		room_id = room.get("room_id", "")
		if not room_id:
			frappe.logger().error(f"Synapse createRoom returned no room_id for match {match_name}")
			return

		# Auto-join user_2 to the room
		try:
			user2_token = client.get_login_token(u2.matrix_user_id)
			if user2_token:
				client._c2s_request(
					"POST",
					f"/_matrix/client/v3/rooms/{room_id}/join",
					{},
					token=user2_token,
				)
		except Exception as e:
			frappe.logger().warning(f"Failed to auto-join {u2.matrix_user_id} to {room_id}: {e}")

		match.db_set("matrix_room_id", room_id, update_modified=False)
		frappe.db.commit()

	except Exception as e:
		frappe.logger().error(f"Failed to create Matrix room for match {match_name}: {e}")


@frappe.whitelist()
def get_matches():
	"""Return all active matches for current user with profile details."""
	user = frappe.session.user
	if user == "Guest":
		frappe.throw("Not logged in", frappe.AuthenticationError)

	matches = frappe.get_all(
		"VY Match",
		filters={
			"is_active": 1,
		},
		or_filters=[
			{"user_1": user},
			{"user_2": user},
		],
		fields=["name", "user_1", "user_2", "matched_at", "matrix_room_id"],
		order_by="matched_at desc",
	)

	result = []
	for m in matches:
		other_user = m.user_2 if m.user_1 == user else m.user_1
		other_profile = frappe.get_doc("VY User Profile", {"user": other_user})

		photo_row = frappe.db.get_value(
			"VY Profile Photo",
			{"parent": other_profile.name, "is_primary": 1},
			["name", "image"],
			as_dict=True,
		)
		photo = photo_row.image if photo_row else ""

		interests = json.loads(other_profile.get("saved_interests") or "[]")
		age = calculate_age(other_profile.birth_date) if other_profile.birth_date else None

		result.append({
			"match_id": m.name,
			"matched_at": str(m.matched_at or ""),
			"matrix_room_id": m.matrix_room_id or "",
			"user": {
				"name": other_profile.name,
				"user": other_user,
				"display_name": other_profile.display_name,
				"age": age,
				"bio": other_profile.bio or "",
				"primary_photo": photo or "",
				"interests": interests[:3],
				"location_name": other_profile.location_name or "",
				"last_active": str(other_profile.last_active or ""),
			},
		})

	return result


@frappe.whitelist()
def unmatch(match_name: str):
	"""Unmatch: set is_active = 0."""
	user = frappe.session.user
	if user == "Guest":
		frappe.throw("Not logged in", frappe.AuthenticationError)

	if not frappe.db.exists("VY Match", match_name):
		frappe.throw("Match not found")

	match = frappe.get_doc("VY Match", match_name)
	if user not in (match.user_1, match.user_2):
		frappe.throw("Not your match to unmatch")

	match.is_active = 0
	match.save(ignore_permissions=True)
	frappe.db.commit()

	# Delete reciprocal VY Like records so both users can see each
	# other in their discover feeds again. Without this, the stale
	# Like records permanently exclude the other person from discover.
	for u1, u2 in [(match.user_1, match.user_2), (match.user_2, match.user_1)]:
		frappe.db.delete("VY Like", {"from_user": u1, "to_user": u2})

	# Invalidate discover cache for both users
	for u in (match.user_1, match.user_2):
		frappe.cache.delete_value(f"discover_feed:{u}")

	return {"ok": True}


@frappe.whitelist()
def get_new_matches_count():
	"""Return count of matches since user's last check (simple version)."""
	user = frappe.session.user
	if user == "Guest":
		return {"count": 0}

	count = frappe.db.count("VY Match", {
		"is_active": 1,
		"matched_at": [">", frappe.utils.add_days(frappe.utils.now(), -7)],
	})
	return {"count": count}


@frappe.whitelist()
def get_matches_with_rooms():
	"""Return matches that have Matrix rooms, for the chat page."""
	user = frappe.session.user
	if user == "Guest":
		frappe.throw("Not logged in", frappe.AuthenticationError)

	matches = frappe.get_all(
		"VY Match",
		filters={"is_active": 1, "matrix_room_id": ["!=", ""]},
		or_filters=[{"user_1": user}, {"user_2": user}],
		fields=["name", "user_1", "user_2", "matched_at", "matrix_room_id"],
		order_by="matched_at desc",
	)

	result = []
	for m in matches:
		other_user = m.user_2 if m.user_1 == user else m.user_1
		other_profile = frappe.get_doc("VY User Profile", {"user": other_user})
		photo_row = frappe.db.get_value(
			"VY Profile Photo",
			{"parent": other_profile.name, "is_primary": 1},
			["name", "image"],
			as_dict=True,
		)
		age = calculate_age(other_profile.birth_date) if other_profile.birth_date else None
		result.append({
			"match_id": m.name,
			"room_id": m.matrix_room_id,
			"matched_at": str(m.matched_at or ""),
			"other_user": {
				"user": other_user,
				"matrix_user_id": other_profile.matrix_user_id or "",
				"display_name": other_profile.display_name,
				"primary_photo": photo_row.image if photo_row else "",
				"age": age,
				"last_active": str(other_profile.last_active or ""),
			},
		})

	return result
