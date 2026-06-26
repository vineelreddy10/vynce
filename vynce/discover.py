import frappe, json
from frappe import _
from datetime import date
from .utils import calculate_age


@frappe.whitelist()
def get_feed(page: int = 1, page_size: int = 20):
	"""Return discovery feed of profiles matching current user's preferences."""
	user = frappe.session.user
	if user == "Guest":
		frappe.throw("Not logged in", frappe.AuthenticationError)

	# Try cache (full feed cached under user key, pagination applied on retrieval)
	cache_key = f"discover_feed:{user}"
	cached = frappe.cache.get_value(cache_key)
	if cached:
		start = (page - 1) * page_size
		end = start + page_size
		return cached[start:end]

	profile = frappe.get_doc("VY User Profile", {"user": user})
	if not profile:
		return []

	profile_interests = json.loads(profile.get("saved_interests") or "[]")
	age_min = profile.age_min or 18
	age_max = profile.age_max or 99
	gender_pref = profile.gender_preference or "All"

	# Build exclusion lists
	liked_users = frappe.get_all("VY Like", filters={"from_user": user}, pluck="to_user")
	blocked_by_me = frappe.get_all("VY Block", filters={"blocked_by": user}, pluck="blocked_user")
	blocked_me = frappe.get_all("VY Block", filters={"blocked_user": user}, pluck="blocked_by")
	exclude_users = set(liked_users + blocked_by_me + blocked_me + [user])

	# Build filters
	filters = {
		"is_active": 1,
		"profile_strength": [">=", 50],
	}
	if gender_pref != "All":
		filters["gender"] = gender_pref

	# Get all eligible profiles
	table_cols = frappe.db.get_table_columns("VY User Profile")
	query_fields = [
		"name", "user", "display_name", "birth_date", "gender",
		"bio", "location_lat", "location_lng", "max_distance_km",
		"saved_interests", "profile_strength", "last_active",
	]
	if "location_name" in table_cols:
		query_fields.append("location_name")

	profiles = frappe.get_all(
		"VY User Profile",
		filters=filters,
		fields=query_fields,
		order_by="last_active desc",
	)

	# Filter, score, and serialize
	today = date.today()
	current_lat = profile.location_lat
	current_lng = profile.location_lng
	max_dist = profile.max_distance_km or 50
	result = []

	for p in profiles:
		if p.user in exclude_users:
			continue

		# Age filter
		if p.birth_date:
			age = calculate_age(p.birth_date)
			if age < age_min or age > age_max:
				continue

		# Distance filter
		distance = None
		if current_lat and current_lng and p.location_lat and p.location_lng:
			distance = _haversine(current_lat, current_lng, p.location_lat, p.location_lng)
			if distance > max_dist:
				continue
			distance = round(distance, 1)

		# Interest matching
		p_interests = json.loads(p.get("saved_interests") or "[]")
		common = [i for i in p_interests if i in profile_interests]
		common_count = len(common)

		# Get primary photo
		photo_row = frappe.db.get_value(
			"VY Profile Photo",
			{"parent": p.name, "is_primary": 1},
			["name", "image"],
			as_dict=True,
		)
		photo = photo_row.image if photo_row else ""

		result.append({
			"name": p.name,
			"user": p.user,
			"display_name": p.display_name,
			"age": calculate_age(p.birth_date) if p.birth_date else None,
			"bio": p.bio or "",
			"latitude": p.location_lat,
			"longitude": p.location_lng,
			"distance_km": distance,
			"location_name": p.get("location_name", "") or "",
			"interests": p_interests,
			"common_interests_count": common_count,
			"primary_photo": photo or "",
			"profile_strength": p.profile_strength,
		})

	# Sort: common interests desc, then last_active desc
	result.sort(key=lambda r: (-r["common_interests_count"], r.get("age") or 0))

	# Paginate
	start = (page - 1) * page_size
	end = start + page_size
	page_result = result[start:end]

	# Cache full feed for 30 min (under user key, not page-scoped)
	frappe.cache.set_value(cache_key, result, expires_in_sec=1800)

	return page_result


@frappe.whitelist()
def get_user_profile(user: str):
	"""Return full profile details for a specific user (for the profile detail page)."""
	current_user = frappe.session.user
	if current_user == "Guest":
		frappe.throw("Not logged in", frappe.AuthenticationError)

	if not frappe.db.exists("VY User Profile", {"user": user}):
		frappe.throw("User not found")

	# Get the target profile
	p = frappe.get_doc("VY User Profile", {"user": user})

	# Calculate distance from current user
	distance = None
	my_profile = frappe.get_doc("VY User Profile", {"user": current_user})
	if my_profile and my_profile.location_lat and my_profile.location_lng and p.location_lat and p.location_lng:
		distance = round(_haversine(
			my_profile.location_lat, my_profile.location_lng,
			p.location_lat, p.location_lng
		), 1)

	# Check match status
	match = frappe.db.get_value(
		"VY Match",
		{
			"user_1": ["in", [current_user, user]],
			"user_2": ["in", [current_user, user]],
			"is_active": 1,
		},
		["name", "matrix_room_id"],
		as_dict=True,
	)

	# Check like status
	liked = frappe.db.exists("VY Like", {"from_user": current_user, "to_user": user})

	# Get photos
	photos = frappe.get_all(
		"VY Profile Photo",
		filters={"parent": p.name},
		fields=["name", "image", "order", "is_primary"],
		order_by="order asc, idx asc",
	)

	# Get primary photo
	primary_photo = ""
	for ph in photos:
		if ph.is_primary:
			primary_photo = ph.image
			break
	if not primary_photo and photos:
		primary_photo = photos[0].image

	# Get interests
	interests = json.loads(p.get("saved_interests") or "[]")

	# Get prompts
	prompts_raw = p.get("prompts") or []
	prompts = []
	for pr in prompts_raw:
		prompts.append({
			"name": pr.get("name", ""),
			"prompt": pr.get("prompt", ""),
			"answer": pr.get("answer", ""),
		})

	return {
		"name": p.name,
		"user": p.user,
		"display_name": p.display_name,
		"age": calculate_age(p.birth_date) if p.birth_date else None,
		"bio": p.bio or "",
		"gender": p.gender or "",
		"latitude": p.location_lat,
		"longitude": p.location_lng,
		"distance_km": distance,
		"location_name": p.get("location_name", "") or "",
		"interests": interests,
		"common_interests_count": 0,
		"primary_photo": primary_photo,
		"photos": photos,
		"prompts": prompts,
		"profile_strength": p.profile_strength,
		"is_active": p.is_active,
		"match_status": "matched" if match else ("liked" if liked else None),
		"match_id": match.name if match else None,
		"matrix_room_id": match.matrix_room_id if match else None,
	}


@frappe.whitelist()
def like_user(to_user: str, like_type: str):
	"""Like, Super Like, or Pass a user. Triggers match check on Like/Super Like."""
	user = frappe.session.user
	if user == "Guest":
		frappe.throw("Not logged in", frappe.AuthenticationError)

	if like_type not in ("Like", "Super Like", "Pass"):
		frappe.throw("Invalid like_type. Must be Like, Super Like, or Pass.")

	if to_user == user:
		frappe.throw("You cannot like yourself.")

	if not frappe.db.exists("VY User Profile", {"user": to_user}):
		frappe.throw("Target user has no profile.")

	# Check not already liked / passed
	if frappe.db.exists("VY Like", {"from_user": user, "to_user": to_user}):
		frappe.throw("You have already interacted with this user.")

	# Check blocks
	if frappe.db.exists("VY Block", {"blocked_by": user, "blocked_user": to_user}):
		frappe.throw("Cannot interact with a blocked user.")
	if frappe.db.exists("VY Block", {"blocked_by": to_user, "blocked_user": user}):
		frappe.throw("This user has blocked you.")

	# Create VY Like
	like = frappe.get_doc({
		"doctype": "VY Like",
		"from_user": user,
		"to_user": to_user,
		"like_type": like_type,
		"created_at": frappe.utils.now(),
	})
	like.insert(ignore_permissions=True)
	frappe.db.commit()

	# Notification for likes
	from .notification import send_notification
	if like_type == "Super Like":
		send_notification(
			user=to_user,
			ntype="Like",
			title="Someone super liked you! ⭐",
			body="Someone thinks you're really special.",
			data={"from_user": user, "like_type": "Super Like"},
		)
	else:
		target_profile = frappe.get_doc("VY User Profile", {"user": user})
		display_name = target_profile.display_name or user
		send_notification(
			user=to_user,
			ntype="Like",
			title="New Like!",
			body=f"{display_name} liked your profile.",
			data={"from_user": user, "like_type": "Like"},
		)
	frappe.db.commit()

	# Emit real-time event to recipient
	if like_type in ("Like", "Super Like"):
		from .socketio_bridge import publish_sio_event
		publish_sio_event("new_like", {
			"from_user": user,
			"like_type": like_type,
		}, user=to_user)

	# Invalidate cache
	frappe.cache.delete_value(f"discover_feed:{user}")

	# Check for match synchronously (only for Like/Super Like)
	match_created = False
	new_match_id = None
	if like_type in ("Like", "Super Like"):
		from .match import check_and_create_match
		try:
			new_match_id = check_and_create_match(from_user=user, to_user=to_user)
			match_created = bool(new_match_id)
		except Exception as e:
			frappe.logger().error(f"Match check failed: {e}")

	# Return the other user's profile info for optimistic UI
	target_profile = frappe.get_doc("VY User Profile", {"user": to_user})
	photo_row = frappe.db.get_value(
		"VY Profile Photo",
		{"parent": target_profile.name, "is_primary": 1},
		["name", "image"],
		as_dict=True,
	)
	return {
		"ok": True,
		"like_type": like_type,
		"match_created": match_created,
		"match_id": new_match_id,
		"target": {
			"name": target_profile.name,
			"user": target_profile.user,
			"display_name": target_profile.display_name,
		},
	}


def _haversine(lat1, lng1, lat2, lng2):
	"""Calculate distance in km between two lat/lng points."""
	import math
	r = 6371  # Earth radius in km
	d_lat = math.radians(lat2 - lat1)
	d_lng = math.radians(lng2 - lng1)
	a = (
		math.sin(d_lat / 2) ** 2
		+ math.cos(math.radians(lat1))
		* math.cos(math.radians(lat2))
		* math.sin(d_lng / 2) ** 2
	)
	return r * 2 * math.asin(math.sqrt(a))
