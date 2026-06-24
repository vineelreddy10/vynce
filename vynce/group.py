import frappe
from frappe import _
from datetime import datetime


@frappe.whitelist()
def list_groups(category: str | None = None, page: int = 1, page_size: int = 20) -> dict:
	"""List groups, optionally filtered by category. Sorted by member_count desc."""
	user = frappe.session.user
	if user == "Guest":
		frappe.throw("Not logged in", frappe.AuthenticationError)

	page = int(page)
	page_size = int(page_size)

	filters = {"is_active": 1}
	if category:
		filters["category"] = category

	groups = frappe.get_all(
		"VY Group",
		filters=filters,
		fields=["name as group_name", "title", "description", "cover_image", "category", "location", "member_count", "creation"],
		order_by="member_count desc",
		start=(page - 1) * page_size,
		limit=page_size,
	)

	total_count = frappe.db.count("VY Group", filters=filters)

	return {
		"groups": groups,
		"total": total_count,
		"page": page,
		"page_size": page_size,
		"total_pages": max(1, (total_count + page_size - 1) // page_size),
	}


@frappe.whitelist()
def get_group_details(group_name: str) -> dict:
	"""Get group with member list and upcoming events count."""
	user = frappe.session.user
	if user == "Guest":
		frappe.throw("Not logged in", frappe.AuthenticationError)

	if not frappe.db.exists("VY Group", group_name):
		frappe.throw(_("Group not found"), frappe.DoesNotExistError)

	group = frappe.get_doc("VY Group", group_name).as_dict()
	group["group_name"] = group.name

	members = frappe.get_all(
		"VY Group Member",
		filters={"group": group_name},
		fields=["name", "user", "role", "joined_at"],
		order_by="joined_at desc",
	)

	member_details = []
	for m in members:
		prof_name = frappe.db.get_value("VY User Profile", {"user": m.user})
		display_name = frappe.db.get_value("VY User Profile", prof_name, "display_name") if prof_name else None
		photo = None
		if prof_name:
			photo = frappe.db.get_value(
				"VY Profile Photo",
				{"parent": prof_name, "is_primary": 1},
				"image",
			)
		member_details.append({
			"name": m.name,
			"user": m.user,
			"role": m.role,
			"joined_at": m.joined_at,
			"display_name": display_name or m.user,
			"profile_image": photo,
		})

	upcoming_events_count = frappe.db.count(
		"VY Event",
		filters={
			"group": group_name,
			"is_active": 1,
			"start_time": [">=", datetime.now()],
		},
	)

	is_member = frappe.db.exists(
		"VY Group Member",
		{"group": group_name, "user": user},
	)

	return {
		"group": group,
		"members": member_details,
		"member_count": len(members),
		"upcoming_events_count": upcoming_events_count,
		"is_member": bool(is_member),
	}


@frappe.whitelist()
def join_group(group_name: str) -> dict:
	"""Create VY Group Member record. Increment member_count."""
	user = frappe.session.user
	if user == "Guest":
		frappe.throw("Not logged in", frappe.AuthenticationError)

	if not frappe.db.exists("VY Group", group_name):
		frappe.throw(_("Group not found"), frappe.DoesNotExistError)

	if frappe.db.exists("VY Group Member", {"group": group_name, "user": user}):
		return {"message": "Already a member", "already_member": True}

	member = frappe.get_doc({
		"doctype": "VY Group Member",
		"group": group_name,
		"user": user,
		"role": "Member",
		"joined_at": frappe.utils.now(),
	})
	member.insert(ignore_permissions=True)

	frappe.db.set_value("VY Group", group_name, "member_count", frappe.db.count(
		"VY Group Member", {"group": group_name}
	))
	frappe.db.commit()

	return {"message": "Joined group successfully", "group": group_name}


@frappe.whitelist()
def leave_group(group_name: str) -> dict:
	"""Remove VY Group Member record. Decrement member_count."""
	user = frappe.session.user
	if user == "Guest":
		frappe.throw("Not logged in", frappe.AuthenticationError)

	if not frappe.db.exists("VY Group", group_name):
		frappe.throw(_("Group not found"), frappe.DoesNotExistError)

	membership = frappe.db.exists("VY Group Member", {"group": group_name, "user": user})
	if not membership:
		return {"message": "Not a member", "already_left": True}

	frappe.delete_doc("VY Group Member", membership, ignore_permissions=True)

	frappe.db.set_value("VY Group", group_name, "member_count", frappe.db.count(
		"VY Group Member", {"group": group_name}
	))
	frappe.db.commit()

	return {"message": "Left group successfully", "group": group_name}
