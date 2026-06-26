import frappe
from frappe import _
from datetime import datetime


@frappe.whitelist()
def list_groups(category: str | None = None, search: str = "", page: int = 1, page_size: int = 20) -> dict:
	"""List groups, optionally filtered by category or search query. Sorted by member_count desc."""
	user = frappe.session.user
	if user == "Guest":
		frappe.throw("Not logged in", frappe.AuthenticationError)

	page = int(page)
	page_size = int(page_size)

	filters = {"is_active": 1}
	or_filters = None

	if category:
		filters["category"] = category

	if search and search.strip():
		q = f"%{search.strip()}%"
		or_filters = [
			["title", "like", q],
			["description", "like", q],
			["location", "like", q],
		]

	groups = frappe.get_all(
		"VY Group",
		filters=filters,
		or_filters=or_filters,
		fields=["name as group_name", "title", "description", "cover_image", "category", "location", "privacy", "member_count", "creation"],
		order_by="member_count desc",
		start=(page - 1) * page_size,
		limit=page_size,
	)

	# Enrich with membership info for current user
	group_names = [g.group_name for g in groups]
	memberships = frappe.get_all(
		"VY Group Member",
		filters={"group": ["in", group_names], "user": user},
		fields=["group", "role", "join_request_status"],
	)
	member_map = {m.group: m for m in memberships}

	for g in groups:
		m = member_map.get(g.group_name)
		g["is_member"] = bool(m and m.join_request_status == "Approved")
		g["is_admin"] = bool(m and m.role == "Admin")
		g["join_request_status"] = m.join_request_status if m else None

	if or_filters:
		# frappe.db.count doesn't support or_filters in this version
		total_count = len(frappe.get_all("VY Group", filters=filters, or_filters=or_filters, pluck="name"))
	else:
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
	"""Get group with member list, privacy, join_request_status for current user."""
	user = frappe.session.user
	if user == "Guest":
		frappe.throw("Not logged in", frappe.AuthenticationError)

	if not frappe.db.exists("VY Group", group_name):
		frappe.throw(_("Group not found"), frappe.DoesNotExistError)

	doc = frappe.get_doc("VY Group", group_name)

	members = frappe.get_all(
		"VY Group Member",
		filters={"group": group_name, "join_request_status": "Approved"},
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

	# Check current user membership
	membership = frappe.db.get_value(
		"VY Group Member",
		{"group": group_name, "user": user},
		["role", "join_request_status"],
		as_dict=True,
	)

	# Pending join request count (for admins)
	pending_requests_count = 0
	if membership and membership.role == "Admin":
		pending_requests_count = frappe.db.count(
			"VY Group Member",
			{"group": group_name, "join_request_status": "Pending"},
		)

	return {
		"group_name": doc.name,
		"title": doc.title,
		"description": doc.description,
		"cover_image": doc.cover_image,
		"category": doc.category,
		"location": doc.location,
		"privacy": doc.privacy,
		"rules": doc.rules,
		"member_count": len(members),
		"members": member_details,
		"is_member": bool(membership and membership.join_request_status == "Approved"),
		"is_admin": bool(membership and membership.role == "Admin"),
		"join_request_status": membership.join_request_status if membership else None,
		"pending_requests_count": pending_requests_count,
	}


@frappe.whitelist()
def upload_cover_image():
	"""Accept multipart file upload and return public URL for use as group cover."""
	user = frappe.session.user
	if user == "Guest":
		frappe.throw("Not logged in", frappe.AuthenticationError)

	file = frappe.request.files.get("file")
	if not file:
		frappe.throw("No file provided")

	from frappe.handler import upload_file
	filedoc = upload_file()

	file_doc = frappe.get_doc("File", filedoc.get("name"))
	if file_doc:
		file_doc.is_private = 0
		file_doc.save(ignore_permissions=True)

	file_url = filedoc.get("file_url", "")
	if not file_url:
		frappe.throw("Upload failed")

	return {"file_url": file_url}


@frappe.whitelist()
def create_group(title: str, description: str = "", category: str = "", location: str = "", privacy: str = "Public", cover_image: str = "", rules: str = "") -> dict:
	"""Create a new group. Creator becomes Admin."""
	user = frappe.session.user
	if user == "Guest":
		frappe.throw("Not logged in", frappe.AuthenticationError)

	if not title or not title.strip():
		frappe.throw(_("Group title is required"))

	group = frappe.get_doc({
		"doctype": "VY Group",
		"title": title.strip(),
		"description": description.strip() if description else "",
		"category": category,
		"location": location.strip() if location else "",
		"privacy": privacy,
		"cover_image": cover_image,
		"rules": rules.strip() if rules else "",
		"created_by": user,
		"is_active": 1,
		"member_count": 1,
	})
	group.insert(ignore_permissions=True)

	# Add creator as Admin member
	member = frappe.get_doc({
		"doctype": "VY Group Member",
		"group": group.name,
		"user": user,
		"role": "Admin",
		"join_request_status": "Approved",
		"joined_at": frappe.utils.now(),
	})
	member.insert(ignore_permissions=True)
	frappe.db.commit()

	return {
		"message": "Group created successfully",
		"group_name": group.name,
	}


@frappe.whitelist()
def join_group(group_name: str) -> dict:
	"""Join a public group, or create a join request for a private group."""
	user = frappe.session.user
	if user == "Guest":
		frappe.throw("Not logged in", frappe.AuthenticationError)

	if not frappe.db.exists("VY Group", group_name):
		frappe.throw(_("Group not found"), frappe.DoesNotExistError)

	existing = frappe.db.get_value(
		"VY Group Member",
		{"group": group_name, "user": user},
		["name", "join_request_status"],
		as_dict=True,
	)
	if existing:
		if existing.join_request_status == "Approved":
			return {"message": "Already a member", "status": "already_member"}
		elif existing.join_request_status == "Pending":
			return {"message": "Join request already pending", "status": "pending"}
		elif existing.join_request_status == "Rejected":
			# Allow re-requesting
			frappe.db.set_value("VY Group Member", existing.name, "join_request_status", "Pending")
			frappe.db.commit()
			return {"message": "Join request re-sent", "status": "pending"}

	group_privacy = frappe.db.get_value("VY Group", group_name, "privacy")
	is_private = group_privacy == "Private"

	status = "Pending" if is_private else "Approved"

	member = frappe.get_doc({
		"doctype": "VY Group Member",
		"group": group_name,
		"user": user,
		"role": "Member",
		"join_request_status": status,
		"joined_at": frappe.utils.now() if not is_private else None,
	})
	member.insert(ignore_permissions=True)

	if not is_private:
		frappe.db.set_value("VY Group", group_name, "member_count", frappe.db.count(
			"VY Group Member", {"group": group_name, "join_request_status": "Approved"}
		))

	frappe.db.commit()

	if is_private:
		return {"message": "Join request sent to group admin", "status": "pending", "group": group_name}
	else:
		return {"message": "Joined group successfully", "status": "approved", "group": group_name}


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
		"VY Group Member", {"group": group_name, "join_request_status": "Approved"}
	))
	frappe.db.commit()

	return {"message": "Left group successfully", "group": group_name}


@frappe.whitelist()
def get_join_requests(group_name: str) -> dict:
	"""Get pending join requests for a group (admin only)."""
	user = frappe.session.user
	if user == "Guest":
		frappe.throw("Not logged in", frappe.AuthenticationError)

	if not frappe.db.exists("VY Group", group_name):
		frappe.throw(_("Group not found"), frappe.DoesNotExistError)

	is_admin = frappe.db.exists(
		"VY Group Member",
		{"group": group_name, "user": user, "role": "Admin"},
	)
	if not is_admin:
		frappe.throw(_("Only group admins can view join requests"), frappe.PermissionError)

	requests = frappe.get_all(
		"VY Group Member",
		filters={"group": group_name, "join_request_status": "Pending"},
		fields=["name", "user", "creation"],
		order_by="creation asc",
	)

	request_details = []
	for r in requests:
		prof_name = frappe.db.get_value("VY User Profile", {"user": r.user})
		display_name = frappe.db.get_value("VY User Profile", prof_name, "display_name") if prof_name else None
		bio = frappe.db.get_value("VY User Profile", prof_name, "bio") if prof_name else None
		photo = None
		if prof_name:
			photo = frappe.db.get_value(
				"VY Profile Photo",
				{"parent": prof_name, "is_primary": 1},
				"image",
			)
		request_details.append({
			"name": r.name,
			"user": r.user,
			"display_name": display_name or r.user,
			"profile_image": photo,
			"bio": bio,
			"requested_at": r.creation,
		})

	return {"requests": request_details, "count": len(request_details)}


@frappe.whitelist()
def approve_join_request(request_name: str) -> dict:
	"""Approve a pending join request."""
	user = frappe.session.user
	if user == "Guest":
		frappe.throw("Not logged in", frappe.AuthenticationError)

	request_doc = frappe.get_doc("VY Group Member", request_name)
	group_name = request_doc.group

	is_admin = frappe.db.exists(
		"VY Group Member",
		{"group": group_name, "user": user, "role": "Admin"},
	)
	if not is_admin:
		frappe.throw(_("Only group admins can approve requests"), frappe.PermissionError)

	if request_doc.join_request_status != "Pending":
		frappe.throw(_("Request is not pending"))

	request_doc.join_request_status = "Approved"
	request_doc.joined_at = frappe.utils.now()
	request_doc.save(ignore_permissions=True)

	frappe.db.set_value("VY Group", group_name, "member_count", frappe.db.count(
		"VY Group Member", {"group": group_name, "join_request_status": "Approved"}
	))
	frappe.db.commit()

	return {"message": "Join request approved", "group": group_name, "user": request_doc.user}


@frappe.whitelist()
def reject_join_request(request_name: str) -> dict:
	"""Reject a pending join request."""
	user = frappe.session.user
	if user == "Guest":
		frappe.throw("Not logged in", frappe.AuthenticationError)

	request_doc = frappe.get_doc("VY Group Member", request_name)
	group_name = request_doc.group

	is_admin = frappe.db.exists(
		"VY Group Member",
		{"group": group_name, "user": user, "role": "Admin"},
	)
	if not is_admin:
		frappe.throw(_("Only group admins can reject requests"), frappe.PermissionError)

	if request_doc.join_request_status != "Pending":
		frappe.throw(_("Request is not pending"))

	request_doc.join_request_status = "Rejected"
	request_doc.save(ignore_permissions=True)
	frappe.db.commit()

	return {"message": "Join request rejected", "group": group_name, "user": request_doc.user}


@frappe.whitelist()
def remove_member(group_name: str, target_user: str) -> dict:
	"""Remove a member from the group (admin only). Cannot remove the creator/admin unless there's another admin."""
	user = frappe.session.user
	if user == "Guest":
		frappe.throw("Not logged in", frappe.AuthenticationError)

	if not frappe.db.exists("VY Group", group_name):
		frappe.throw(_("Group not found"), frappe.DoesNotExistError)

	is_admin = frappe.db.exists(
		"VY Group Member",
		{"group": group_name, "user": user, "role": "Admin"},
	)
	if not is_admin:
		frappe.throw(_("Only group admins can remove members"), frappe.PermissionError)

	membership = frappe.db.get_value(
		"VY Group Member",
		{"group": group_name, "user": target_user, "join_request_status": "Approved"},
		["name", "role"],
		as_dict=True,
	)
	if not membership:
		return {"message": "User is not a member", "ok": False}

	if membership.role == "Admin" and target_user != user:
		# Check if there are other admins
		admin_count = frappe.db.count(
			"VY Group Member",
			{"group": group_name, "role": "Admin", "join_request_status": "Approved"},
		)
		if admin_count <= 1:
			frappe.throw(_("Cannot remove the only admin. Transfer admin first."))

	frappe.delete_doc("VY Group Member", membership.name, ignore_permissions=True)

	frappe.db.set_value("VY Group", group_name, "member_count", frappe.db.count(
		"VY Group Member", {"group": group_name, "join_request_status": "Approved"}
	))
	frappe.db.commit()

	return {"message": "Member removed", "ok": True}


@frappe.whitelist()
def transfer_admin(group_name: str, target_user: str) -> dict:
	"""Transfer admin role to another member. Current admin becomes Member."""
	user = frappe.session.user
	if user == "Guest":
		frappe.throw("Not logged in", frappe.AuthenticationError)

	if not frappe.db.exists("VY Group", group_name):
		frappe.throw(_("Group not found"), frappe.DoesNotExistError)

	is_admin = frappe.db.exists(
		"VY Group Member",
		{"group": group_name, "user": user, "role": "Admin"},
	)
	if not is_admin:
		frappe.throw(_("Only group admins can transfer admin"), frappe.PermissionError)

	target_membership = frappe.db.get_value(
		"VY Group Member",
		{"group": group_name, "user": target_user, "join_request_status": "Approved"},
		["name", "role"],
		as_dict=True,
	)
	if not target_membership:
		frappe.throw(_("Target user is not an active member"))

	# Demote current admin
	current_membership = frappe.db.get_value(
		"VY Group Member",
		{"group": group_name, "user": user, "join_request_status": "Approved"},
		"name",
	)
	frappe.db.set_value("VY Group Member", current_membership, "role", "Member")
	# Promote target
	frappe.db.set_value("VY Group Member", target_membership.name, "role", "Admin")
	frappe.db.commit()

	return {"message": "Admin transferred successfully", "ok": True}


@frappe.whitelist()
def create_post(group_name: str, content: str = "", media: str = "", media_type: str = "") -> dict:
	"""Create a post in a group. User must be an approved member."""
	user = frappe.session.user
	if user == "Guest":
		frappe.throw("Not logged in", frappe.AuthenticationError)

	if not frappe.db.exists("VY Group", group_name):
		frappe.throw(_("Group not found"), frappe.DoesNotExistError)

	is_approved = frappe.db.exists(
		"VY Group Member",
		{"group": group_name, "user": user, "join_request_status": "Approved"},
	)
	if not is_approved:
		frappe.throw(_("Only group members can create posts"), frappe.PermissionError)

	if not content and not media:
		frappe.throw(_("Post must have content or media"))

	post = frappe.get_doc({
		"doctype": "VY Group Post",
		"group": group_name,
		"user": user,
		"content": content.strip() if content else "",
		"media": media,
		"media_type": media_type if media_type else "",
		"created_at": frappe.utils.now(),
	})
	post.insert(ignore_permissions=True)
	frappe.db.commit()

	return {"message": "Post created", "post_name": post.name}


@frappe.whitelist()
def get_group_posts(group_name: str, page: int = 1, page_size: int = 20) -> dict:
	"""Get posts for a group."""
	user = frappe.session.user
	if user == "Guest":
		frappe.throw("Not logged in", frappe.AuthenticationError)

	if not frappe.db.exists("VY Group", group_name):
		frappe.throw(_("Group not found"), frappe.DoesNotExistError)

	page = int(page)
	page_size = int(page_size)

	posts = frappe.get_all(
		"VY Group Post",
		filters={"group": group_name},
		fields=["name", "user", "content", "media", "media_type", "created_at"],
		order_by="created_at desc",
		start=(page - 1) * page_size,
		limit=page_size,
	)

	# Enrich with user profile info
	post_details = []
	for p in posts:
		prof_name = frappe.db.get_value("VY User Profile", {"user": p.user})
		display_name = frappe.db.get_value("VY User Profile", prof_name, "display_name") if prof_name else None
		photo = None
		if prof_name:
			photo = frappe.db.get_value(
				"VY Profile Photo",
				{"parent": prof_name, "is_primary": 1},
				"image",
			)
		post_details.append({
			"name": p.name,
			"user": p.user,
			"display_name": display_name or p.user,
			"user_photo": photo,
			"content": p.content,
			"media": p.media,
			"media_type": p.media_type,
			"created_at": p.created_at,
		})

	total_count = frappe.db.count("VY Group Post", filters={"group": group_name})

	return {
		"posts": post_details,
		"total": total_count,
		"page": page,
		"page_size": page_size,
		"total_pages": max(1, (total_count + page_size - 1) // page_size),
	}


@frappe.whitelist()
def send_match_request(group_name: str, target_user: str) -> dict:
	"""Send a match request to another group member. Creates a VY Like record."""
	user = frappe.session.user
	if user == "Guest":
		frappe.throw("Not logged in", frappe.AuthenticationError)

	if target_user == user:
		frappe.throw(_("Cannot send match request to yourself"))

	if not frappe.db.exists("VY Group", group_name):
		frappe.throw(_("Group not found"), frappe.DoesNotExistError)

	# Both must be approved members
	for u in [user, target_user]:
		if not frappe.db.exists(
			"VY Group Member",
			{"group": group_name, "user": u, "join_request_status": "Approved"},
		):
			frappe.throw(_("Both users must be group members"))

	# Check if already liked
	if frappe.db.exists("VY Like", {"user": user, "liked_user": target_user}):
		return {"message": "Match request already sent", "status": "already_sent"}

	# Create a like record (which powers the match system)
	like = frappe.get_doc({
		"doctype": "VY Like",
		"user": user,
		"liked_user": target_user,
		"source": "Group",
		"source_name": group_name,
	})
	like.insert(ignore_permissions=True)

	# Check if reciprocal like exists -> create match
	reciprocal = frappe.db.exists(
		"VY Like",
		{"user": target_user, "liked_user": user},
	)
	if reciprocal:
		frappe.get_doc({
			"doctype": "VY Match",
			"user_a": user,
			"user_b": target_user,
			"matched_at": frappe.utils.now(),
			"is_active": 1,
		}).insert(ignore_permissions=True)

	frappe.db.commit()

	return {"message": "Match request sent", "status": "matched" if reciprocal else "pending"}
