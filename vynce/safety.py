import frappe
from frappe import _


@frappe.whitelist()
def block_user(blocked_user: str) -> dict:
	"""Create VY Block. Auto-unmatch if matched. Clear discovery caches."""
	user = frappe.session.user
	if user == "Guest":
		frappe.throw("Not logged in", frappe.AuthenticationError)

	if blocked_user == user:
		frappe.throw("You cannot block yourself.")

	if not frappe.db.exists("User", blocked_user):
		frappe.throw("User not found.")

	if frappe.db.exists("VY Block", {"blocked_by": user, "blocked_user": blocked_user}):
		return {"ok": True, "message": "Already blocked"}

	block = frappe.get_doc({
		"doctype": "VY Block",
		"blocked_by": user,
		"blocked_user": blocked_user,
		"created_at": frappe.utils.now(),
	})
	block.insert(ignore_permissions=True)

	# Deactivate any active match between the two users
	for match in frappe.get_all(
		"VY Match",
		filters={
			"user_1": ["in", [user, blocked_user]],
			"user_2": ["in", [user, blocked_user]],
			"is_active": 1,
		},
		pluck="name",
	):
		frappe.db.set_value("VY Match", match, "is_active", 0)

	# Clear discovery cache for both users
	frappe.cache.delete_value(f"discover_feed:{user}")
	frappe.cache.delete_value(f"discover_feed:{blocked_user}")

	frappe.db.commit()
	return {"ok": True}


@frappe.whitelist()
def unblock_user(blocked_user: str) -> dict:
	"""Delete VY Block record. Clear discovery cache."""
	user = frappe.session.user
	if user == "Guest":
		frappe.throw("Not logged in", frappe.AuthenticationError)

	blocks = frappe.get_all("VY Block", filters={
		"blocked_by": user,
		"blocked_user": blocked_user,
	}, pluck="name")

	if not blocks:
		frappe.throw("Block record not found.")

	for block_name in blocks:
		frappe.delete_doc("VY Block", block_name, ignore_permissions=True)

	# Clear discovery cache for current user
	frappe.cache.delete_value(f"discover_feed:{user}")

	frappe.db.commit()
	return {"ok": True}


@frappe.whitelist()
def report_user(reported_user: str, reason: str, details: str = "") -> dict:
	"""Create VY Report with status Pending."""
	user = frappe.session.user
	if user == "Guest":
		frappe.throw("Not logged in", frappe.AuthenticationError)

	if reported_user == user:
		frappe.throw("You cannot report yourself.")

	if not frappe.db.exists("User", reported_user):
		frappe.throw("User not found.")

	doc = frappe.get_doc({
		"doctype": "VY Report",
		"reported_by": user,
		"reported_user": reported_user,
		"reason": reason,
		"details": details,
		"status": "Pending",
		"created_at": frappe.utils.now(),
	})
	doc.insert(ignore_permissions=True)
	frappe.db.commit()

	return {"ok": True, "name": doc.name}


@frappe.whitelist()
def request_verification() -> dict:
	"""Accept photo upload, create VY Verification Request with status Pending."""
	user = frappe.session.user
	if user == "Guest":
		frappe.throw("Not logged in", frappe.AuthenticationError)

	if "file" not in frappe.request.files:
		frappe.throw("No file uploaded.")

	from frappe.handler import upload_file

	filedoc = upload_file()
	file_url = filedoc.get("file_url", "")

	if not file_url:
		frappe.throw("Upload failed.")

	doc = frappe.get_doc({
		"doctype": "VY Verification Request",
		"user": user,
		"photo": file_url,
		"status": "Pending",
		"created_at": frappe.utils.now(),
	})
	doc.insert(ignore_permissions=True)
	frappe.db.commit()

	return {"ok": True, "name": doc.name}


@frappe.whitelist()
def get_blocked_users() -> list:
	"""Return list of blocked users with profile details."""
	user = frappe.session.user
	if user == "Guest":
		frappe.throw("Not logged in", frappe.AuthenticationError)

	blocked = frappe.get_all(
		"VY Block",
		filters={"blocked_by": user},
		fields=["blocked_user", "reason", "created_at"],
		order_by="creation desc",
	)

	if not blocked:
		return []

	result = []
	for b in blocked:
		if not frappe.db.exists("VY User Profile", {"user": b.blocked_user}):
			continue

		profile = frappe.db.get_value(
			"VY User Profile",
			{"user": b.blocked_user},
			["name", "display_name", "bio", "birth_date"],
			as_dict=True,
		)

		if not profile:
			continue

		photo = (
			frappe.db.get_value(
				"VY Profile Photo",
				{"parent": profile.name, "is_primary": 1},
				"image",
			)
			or ""
		)

		result.append({
			"user": b.blocked_user,
			"display_name": profile.display_name,
			"bio": profile.bio or "",
			"reason": b.reason or "",
			"primary_photo": photo,
			"blocked_at": str(b.created_at or ""),
		})

	return result


def is_blocked(user1: str, user2: str) -> bool:
	"""Check if either user has blocked the other. Returns True/False."""
	if not user1 or not user2:
		return False
	return frappe.db.exists("VY Block", {
		"blocked_by": ["in", [user1, user2]],
		"blocked_user": ["in", [user1, user2]],
	})
