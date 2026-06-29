import frappe
from frappe import _
from datetime import datetime


@frappe.whitelist()
def list_events(
	category: str | None = None,
	search: str = "",
	venue_type: str | None = None,
	date_from: str | None = None,
	date_to: str | None = None,
	is_free: int | None = None,
	page: int = 1,
	page_size: int = 20,
	sort_by: str = "start_time",
	sort_order: str = "asc",
) -> dict:
	user = frappe.session.user
	if user == "Guest":
		frappe.throw(_("Not logged in"), frappe.AuthenticationError)

	page = int(page)
	page_size = int(page_size)

	filters: dict = {"is_active": 1}
	or_filters: list | None = None

	if category:
		filters["category"] = category
	if venue_type:
		filters["venue_type"] = venue_type
	if is_free:
		filters["is_free"] = 1
	if date_from:
		filters["start_time"] = [">=", date_from]
	if date_to:
		filters.setdefault("start_time", [])
		if isinstance(filters["start_time"], list):
			filters["start_time"].append(["<=", date_to])

	if search and search.strip():
		q = f"%{search.strip()}%"
		or_filters = [
			["title", "like", q],
			["subtitle", "like", q],
			["description", "like", q],
			["location", "like", q],
			["tags", "like", q],
		]

	valid_sort = {
		"start_time": "start_time",
		"created": "creation",
		"title": "title",
		"popular": "member_count",
	}
	db_sort = valid_sort.get(sort_by, "start_time")
	order = f"{db_sort} {'asc' if sort_order == 'asc' else 'desc'}"

	events = frappe.get_all(
		"VY Event",
		filters=filters,
		or_filters=or_filters,
		fields=[
			"name", "title", "subtitle", "description", "cover_image",
			"category", "location", "venue_type", "start_time", "end_time",
			"max_attendees", "is_free", "price", "is_featured", "visibility",
			"created_by", "timezone", "family_friendly", "pet_friendly",
		],
		order_by=order,
		limit_start=(page - 1) * page_size,
		limit_page_length=page_size,
	)

	for event in events:
		event["going_count"] = frappe.db.count("VY Event Attendee", {
			"event": event.name,
			"status": "Going",
		})
		event["interested_count"] = frappe.db.count("VY Event Attendee", {
			"event": event.name,
			"status": "Interested",
		})
		event["my_rsvp"] = frappe.db.get_value(
			"VY Event Attendee",
			{"event": event.name, "user": user},
			"status",
		)
		event["is_bookmarked"] = frappe.db.exists(
			"VY Event Bookmark",
			{"event": event.name, "user": user},
		)
		event["avg_rating"] = _get_avg_rating(event.name)

	total = frappe.db.count("VY Event", filters=filters)

	return {
		"events": events,
		"total": total,
		"page": page,
		"page_size": page_size,
		"has_next": (page * page_size) < total,
	}


@frappe.whitelist()
def get_event_details(event_name: str) -> dict:
	user = frappe.session.user
	if user == "Guest":
		frappe.throw(_("Not logged in"), frappe.AuthenticationError)

	event = frappe.get_doc("VY Event", event_name)
	if not event or not event.is_active:
		frappe.throw(_("Event not found"), frappe.DoesNotExistError)

	attendees = frappe.db.sql("""
		SELECT
			a.name, a.user, a.status, a.created_at,
			p.display_name,
			(SELECT ph.image FROM `tabVY Profile Photo` ph
				WHERE ph.parent = p.name AND ph.parentfield = 'photos'
				ORDER BY ph.is_primary DESC, ph.order ASC, ph.creation ASC LIMIT 1
			) as profile_photo
		FROM `tabVY Event Attendee` a
		LEFT JOIN `tabVY User Profile` p ON p.user = a.user
		WHERE a.event = %s
		ORDER BY a.creation ASC
	""", event_name, as_dict=True)

	my_rsvp = frappe.db.get_value(
		"VY Event Attendee",
		{"event": event_name, "user": user},
		"status",
	)

	going_count = sum(1 for a in attendees if a.status == "Going")
	interested_count = sum(1 for a in attendees if a.status == "Interested")
	is_bookmarked = frappe.db.exists(
		"VY Event Bookmark",
		{"event": event_name, "user": user},
	)

	# Organizer info
	organizer = None
	if event.created_by:
		org_profile = frappe.db.sql("""
			SELECT
				p.display_name,
				(SELECT ph.image FROM `tabVY Profile Photo` ph
					WHERE ph.parent = p.name AND ph.parentfield = 'photos'
					ORDER BY ph.is_primary DESC, ph.order ASC, ph.creation ASC LIMIT 1
				) as profile_photo
			FROM `tabVY User Profile` p
			WHERE p.user = %s
		""", event.created_by, as_dict=True)
		if org_profile:
			organizer = {
				"user": event.created_by,
				"display_name": org_profile[0].display_name,
				"profile_photo": org_profile[0].profile_photo,
			}

	# Gallery
	gallery = []
	if event.get("gallery"):
		for item in event.gallery:
			gallery.append({
				"image": item.image,
				"caption": item.caption,
			})

	# Reviews summary
	avg_rating = _get_avg_rating(event_name)
	review_count = frappe.db.count("VY Event Review", {"event": event_name})

	return {
		"event": event.as_dict(),
		"attendees": attendees,
		"my_rsvp": my_rsvp,
		"going_count": going_count,
		"interested_count": interested_count,
		"is_bookmarked": bool(is_bookmarked),
		"organizer": organizer,
		"gallery": gallery,
		"avg_rating": avg_rating,
		"review_count": review_count,
	}


# ─── RSVP ───

@frappe.whitelist()
def rsvp(event_name: str, status: str) -> dict:
	user = frappe.session.user
	if user == "Guest":
		frappe.throw(_("Not logged in"), frappe.AuthenticationError)

	valid_statuses = {"Going", "Interested", "Not Going"}
	if status not in valid_statuses:
		frappe.throw(_("Invalid RSVP status"))

	if not frappe.db.exists("VY Event", event_name):
		frappe.throw(_("Event not found"), frappe.DoesNotExistError)

	existing = frappe.db.get_value(
		"VY Event Attendee",
		{"event": event_name, "user": user},
		"name",
	)

	if existing:
		if status == "Not Going":
			frappe.delete_doc("VY Event Attendee", existing, ignore_permissions=True)
		else:
			frappe.db.set_value("VY Event Attendee", existing, "status", status)
	else:
		if status != "Not Going":
			attendee = frappe.get_doc({
				"doctype": "VY Event Attendee",
				"event": event_name,
				"user": user,
				"status": status,
				"created_at": frappe.utils.now(),
			})
			attendee.insert(ignore_permissions=True)

	frappe.db.commit()

	going_count = frappe.db.count("VY Event Attendee", {
		"event": event_name, "status": "Going",
	})

	return {
		"ok": True,
		"status": status,
		"attending_count": going_count,
	}


# ─── Create / Update / Delete ───

@frappe.whitelist()
def create_event(
	title: str,
	subtitle: str = "",
	description: str = "",
	category: str = "",
	venue_type: str = "Physical",
	location: str = "",
	location_lat: float | None = None,
	location_lng: float | None = None,
	venue_details: str = "",
	online_url: str = "",
	start_time: str | None = None,
	end_time: str | None = None,
	timezone: str = "UTC",
	max_attendees: int = 0,
	is_free: int = 1,
	price: float = 0,
	registration_deadline: str | None = None,
	visibility: str = "Public",
	tags: str = "",
	age_restriction: int = 0,
	family_friendly: int = 0,
	pet_friendly: int = 0,
	accessibility_info: str = "",
	contact_email: str = "",
	cancellation_policy: str = "",
	refund_policy: str = "",
) -> dict:
	user = frappe.session.user
	if user == "Guest":
		frappe.throw(_("Not logged in"), frappe.AuthenticationError)

	if not title or not title.strip():
		frappe.throw(_("Event title is required"))

	if not start_time:
		frappe.throw(_("Start time is required"))

	event = frappe.get_doc({
		"doctype": "VY Event",
		"title": title.strip(),
		"subtitle": subtitle.strip() if subtitle else "",
		"description": description,
		"category": category,
		"venue_type": venue_type,
		"location": location.strip() if location else "",
		"location_lat": location_lat,
		"location_lng": location_lng,
		"venue_details": venue_details,
		"online_url": online_url,
		"start_time": start_time,
		"end_time": end_time,
		"timezone": timezone,
		"max_attendees": int(max_attendees),
		"is_free": int(is_free),
		"price": float(price) if not is_free else 0,
		"registration_deadline": registration_deadline,
		"visibility": visibility,
		"tags": tags,
		"age_restriction": int(age_restriction),
		"family_friendly": int(family_friendly),
		"pet_friendly": int(pet_friendly),
		"accessibility_info": accessibility_info,
		"contact_email": contact_email,
		"cancellation_policy": cancellation_policy,
		"refund_policy": refund_policy,
		"created_by": user,
		"is_active": 1,
	})
	event.insert(ignore_permissions=True)

	# Creator is automatically Going
	attendee = frappe.get_doc({
		"doctype": "VY Event Attendee",
		"event": event.name,
		"user": user,
		"status": "Going",
		"created_at": frappe.utils.now(),
	})
	attendee.insert(ignore_permissions=True)
	frappe.db.commit()

	return {
		"message": "Event created successfully",
		"name": event.name,
	}


@frappe.whitelist()
def update_event(event_name: str, **kwargs) -> dict:
	user = frappe.session.user
	if user == "Guest":
		frappe.throw(_("Not logged in"), frappe.AuthenticationError)

	if not frappe.db.exists("VY Event", event_name):
		frappe.throw(_("Event not found"), frappe.DoesNotExistError)

	event = frappe.get_doc("VY Event", event_name)
	if event.created_by != user:
		frappe.throw(_("Only the event creator can update this event"))

	allowed_fields = {
		"title", "subtitle", "description", "category", "venue_type",
		"location", "location_lat", "location_lng", "venue_details",
		"online_url", "start_time", "end_time", "timezone",
		"max_attendees", "is_free", "price", "registration_deadline",
		"visibility", "tags", "age_restriction", "family_friendly",
		"pet_friendly", "accessibility_info", "contact_email",
		"cancellation_policy", "refund_policy", "cover_image",
	}

	for key, value in kwargs.items():
		if key in allowed_fields:
			setattr(event, key, value)

	event.save(ignore_permissions=True)
	frappe.db.commit()

	return {"message": "Event updated successfully", "name": event.name}


@frappe.whitelist()
def delete_event(event_name: str) -> dict:
	user = frappe.session.user
	if user == "Guest":
		frappe.throw(_("Not logged in"), frappe.AuthenticationError)

	event = frappe.get_doc("VY Event", event_name)
	if not event:
		frappe.throw(_("Event not found"), frappe.DoesNotExistError)

	if event.created_by != user:
		frappe.throw(_("Only the event creator can delete this event"))

	event.is_active = 0
	event.save(ignore_permissions=True)
	frappe.db.commit()

	return {"message": "Event cancelled"}


# ─── Bookmark ───

@frappe.whitelist()
def bookmark_event(event_name: str) -> dict:
	user = frappe.session.user
	if user == "Guest":
		frappe.throw(_("Not logged in"), frappe.AuthenticationError)

	if not frappe.db.exists("VY Event", event_name):
		frappe.throw(_("Event not found"), frappe.DoesNotExistError)

	if frappe.db.exists("VY Event Bookmark", {"event": event_name, "user": user}):
		return {"bookmarked": True}

	bookmark = frappe.get_doc({
		"doctype": "VY Event Bookmark",
		"event": event_name,
		"user": user,
		"created_at": frappe.utils.now(),
	})
	bookmark.insert(ignore_permissions=True)
	frappe.db.commit()

	return {"bookmarked": True}


@frappe.whitelist()
def unbookmark_event(event_name: str) -> dict:
	user = frappe.session.user
	if user == "Guest":
		frappe.throw(_("Not logged in"), frappe.AuthenticationError)

	name = frappe.db.get_value(
		"VY Event Bookmark",
		{"event": event_name, "user": user},
		"name",
	)
	if name:
		frappe.delete_doc("VY Event Bookmark", name, ignore_permissions=True)
		frappe.db.commit()

	return {"bookmarked": False}


@frappe.whitelist()
def list_bookmarked_events(page: int = 1, page_size: int = 20) -> dict:
	user = frappe.session.user
	if user == "Guest":
		frappe.throw(_("Not logged in"), frappe.AuthenticationError)

	page = int(page)
	page_size = int(page_size)

	bookmarks = frappe.get_all(
		"VY Event Bookmark",
		filters={"user": user},
		fields=["event", "created_at"],
		order_by="creation desc",
		limit_start=(page - 1) * page_size,
		limit_page_length=page_size,
	)

	event_names = [b.event for b in bookmarks]
	events = []
	if event_names:
		event_data = frappe.get_all(
			"VY Event",
			filters={"name": ["in", event_names], "is_active": 1},
			fields=[
				"name", "title", "subtitle", "cover_image", "category",
				"location", "start_time", "end_time", "venue_type", "is_free",
			],
		)
		event_map = {e.name: e for e in event_data}
		for b in bookmarks:
			if b.event in event_map:
				events.append(event_map[b.event])

	return {"events": events}


# ─── Reviews ───

@frappe.whitelist()
def review_event(event_name: str, rating: int, review: str = "") -> dict:
	user = frappe.session.user
	if user == "Guest":
		frappe.throw(_("Not logged in"), frappe.AuthenticationError)

	if not 1 <= rating <= 5:
		frappe.throw(_("Rating must be between 1 and 5"))

	if not frappe.db.exists("VY Event", event_name):
		frappe.throw(_("Event not found"), frappe.DoesNotExistError)

	existing = frappe.db.get_value(
		"VY Event Review",
		{"event": event_name, "user": user},
		"name",
	)

	if existing:
		frappe.db.set_value("VY Event Review", existing, {
			"rating": rating,
			"review": review,
		})
	else:
		doc = frappe.get_doc({
			"doctype": "VY Event Review",
			"event": event_name,
			"user": user,
			"rating": rating,
			"review": review,
			"created_at": frappe.utils.now(),
		})
		doc.insert(ignore_permissions=True)

	frappe.db.commit()
	return {"ok": True}


@frappe.whitelist()
def list_reviews(event_name: str, page: int = 1, page_size: int = 20) -> dict:
	user = frappe.session.user
	if user == "Guest":
		frappe.throw(_("Not logged in"), frappe.AuthenticationError)

	page = int(page)
	page_size = int(page_size)

	reviews = frappe.db.sql("""
		SELECT
			r.name, r.user, r.rating, r.review, r.created_at,
			p.display_name,
			(SELECT ph.image FROM `tabVY Profile Photo` ph
				WHERE ph.parent = p.name AND ph.parentfield = 'photos'
				ORDER BY ph.is_primary DESC, ph.order ASC, ph.creation ASC LIMIT 1
			) as profile_photo
		FROM `tabVY Event Review` r
		LEFT JOIN `tabVY User Profile` p ON p.user = r.user
		WHERE r.event = %s
		ORDER BY r.creation DESC
		LIMIT %s OFFSET %s
	""", (event_name, page_size, (page - 1) * page_size), as_dict=True)

	total = frappe.db.count("VY Event Review", {"event": event_name})
	avg_rating = _get_avg_rating(event_name)

	return {
		"reviews": reviews,
		"total": total,
		"avg_rating": avg_rating,
		"page": page,
		"page_size": page_size,
	}


# ─── Comments ───

@frappe.whitelist()
def comment_on_event(event_name: str, content: str, parent_comment: str | None = None) -> dict:
	user = frappe.session.user
	if user == "Guest":
		frappe.throw(_("Not logged in"), frappe.AuthenticationError)

	if not content or not content.strip():
		frappe.throw(_("Comment cannot be empty"))

	if not frappe.db.exists("VY Event", event_name):
		frappe.throw(_("Event not found"), frappe.DoesNotExistError)

	doc = frappe.get_doc({
		"doctype": "VY Event Comment",
		"event": event_name,
		"user": user,
		"content": content.strip(),
		"parent_comment": parent_comment,
		"created_at": frappe.utils.now(),
	})
	doc.insert(ignore_permissions=True)
	frappe.db.commit()

	return {"ok": True, "comment_id": doc.name}


@frappe.whitelist()
def list_comments(event_name: str, page: int = 1, page_size: int = 50) -> dict:
	user = frappe.session.user
	if user == "Guest":
		frappe.throw(_("Not logged in"), frappe.AuthenticationError)

	page = int(page)
	page_size = int(page_size)

	comments = frappe.db.sql("""
		SELECT
			c.name, c.user, c.content, c.parent_comment, c.created_at,
			p.display_name,
			(SELECT ph.image FROM `tabVY Profile Photo` ph
				WHERE ph.parent = p.name AND ph.parentfield = 'photos'
				ORDER BY ph.is_primary DESC, ph.order ASC, ph.creation ASC LIMIT 1
			) as profile_photo
		FROM `tabVY Event Comment` c
		LEFT JOIN `tabVY User Profile` p ON p.user = c.user
		WHERE c.event = %s AND c.parent_comment IS NULL
		ORDER BY c.creation DESC
		LIMIT %s OFFSET %s
	""", (event_name, page_size, (page - 1) * page_size), as_dict=True)

	# Get replies for each comment
	comment_ids = [c.name for c in comments]
	if comment_ids:
		replies = frappe.db.sql("""
			SELECT
				c.name, c.user, c.content, c.parent_comment, c.created_at,
				p.display_name,
				(SELECT ph.image FROM `tabVY Profile Photo` ph
					WHERE ph.parent = p.name AND ph.parentfield = 'photos'
					ORDER BY ph.is_primary DESC, ph.order ASC, ph.creation ASC LIMIT 1
				) as profile_photo
			FROM `tabVY Event Comment` c
			LEFT JOIN `tabVY User Profile` p ON p.user = c.user
			WHERE c.parent_comment IN %s
			ORDER BY c.creation ASC
		""", [tuple(comment_ids)], as_dict=True)

		reply_map: dict[str, list] = {}
		for r in replies:
			reply_map.setdefault(r.parent_comment, []).append(r)

		for c in comments:
			c["replies"] = reply_map.get(c.name, [])

	total = frappe.db.count("VY Event Comment", {"event": event_name, "parent_comment": None})

	return {"comments": comments, "total": total}


# ─── Image Upload ───

@frappe.whitelist()
def upload_event_image():
	user = frappe.session.user
	if user == "Guest":
		frappe.throw(_("Not logged in"), frappe.AuthenticationError)

	file = frappe.request.files.get("file")
	if not file:
		frappe.throw(_("No file provided"))

	from frappe.handler import upload_file
	filedoc = upload_file()

	file_doc = frappe.get_doc("File", filedoc.get("name"))
	if file_doc:
		file_doc.is_private = 0
		file_doc.save(ignore_permissions=True)

	file_url = filedoc.get("file_url", "")
	if not file_url:
		frappe.throw(_("Upload failed"))

	return {"file_url": file_url}


# ─── Discovery Feed ───

@frappe.whitelist()
def get_discovery_feed(page: int = 1, page_size: int = 20) -> dict:
	user = frappe.session.user
	if user == "Guest":
		frappe.throw(_("Not logged in"), frappe.AuthenticationError)

	page = int(page)
	page_size = int(page_size)

	now = frappe.utils.now()

	# Trending: most attendees (going count)
	trending = frappe.db.sql("""
		SELECT e.name, e.title, e.subtitle, e.cover_image, e.category,
			   e.location, e.start_time, e.venue_type, e.is_free, e.price,
			   COUNT(a.name) as attendee_count
		FROM `tabVY Event` e
		LEFT JOIN `tabVY Event Attendee` a ON a.event = e.name AND a.status = 'Going'
		WHERE e.is_active = 1 AND e.start_time > %s
		GROUP BY e.name
		ORDER BY attendee_count DESC
		LIMIT %s
	""", (now, page_size), as_dict=True)

	# Upcoming: soonest first
	upcoming = frappe.get_all(
		"VY Event",
		filters={"is_active": 1, "start_time": [">", now]},
		fields=["name", "title", "subtitle", "cover_image", "category",
				"location", "start_time", "venue_type", "is_free", "price"],
		order_by="start_time asc",
		limit=page_size,
	)

	# Recommended: same category as user's interests
	profile = frappe.get_doc("VY User Profile", {"user": user})
	import json
	interests = json.loads(profile.get("saved_interests") or "[]")
	recommended = []
	if interests:
		recommended = frappe.get_all(
			"VY Event",
			filters={
				"is_active": 1,
				"start_time": [">", now],
				"category": ["in", interests],
			},
			fields=["name", "title", "subtitle", "cover_image", "category",
					"location", "start_time", "venue_type", "is_free", "price"],
			order_by="start_time asc",
			limit=page_size,
		)

	# Friends attending
	friends_attending = []
	following = frappe.get_all("VY Like", filters={"from_user": user}, pluck="to_user")
	if following:
		attending_events = frappe.db.sql("""
			SELECT DISTINCT e.name, e.title, e.subtitle, e.cover_image, e.category,
				   e.location, e.start_time, e.venue_type, e.is_free, e.price
			FROM `tabVY Event` e
			JOIN `tabVY Event Attendee` a ON a.event = e.name
			WHERE e.is_active = 1 AND e.start_time > %s
			  AND a.user IN %s AND a.status = 'Going'
			ORDER BY e.start_time ASC
			LIMIT %s
		""", (now, tuple(following), page_size), as_dict=True)
		friends_attending = attending_events

	return {
		"trending": trending,
		"upcoming": upcoming,
		"recommended": recommended,
		"friends_attending": friends_attending,
	}


# ─── Calendar ───

@frappe.whitelist()
def get_calendar_events(year: int, month: int) -> list:
	user = frappe.session.user
	if user == "Guest":
		frappe.throw(_("Not logged in"), frappe.AuthenticationError)

	start_date = f"{year}-{month:02d}-01"
	if month == 12:
		end_date = f"{year + 1}-01-01"
	else:
		end_date = f"{year}-{month + 1:02d}-01"

	# Events user is attending
	my_events = frappe.db.sql("""
		SELECT e.name, e.title, e.start_time, e.end_time, e.location,
			   e.venue_type, e.cover_image
		FROM `tabVY Event` e
		JOIN `tabVY Event Attendee` a ON a.event = e.name
		WHERE a.user = %s AND a.status = 'Going'
		  AND e.start_time >= %s AND e.start_time < %s
		  AND e.is_active = 1
		ORDER BY e.start_time ASC
	""", (user, start_date, end_date), as_dict=True)

	# Public events in this period
	public_events = frappe.get_all(
		"VY Event",
		filters={
			"is_active": 1,
			"visibility": "Public",
			"start_time": [">=", start_date],
			"end_time": ["<", end_date],
		},
		fields=["name", "title", "start_time", "end_time", "location", "venue_type", "cover_image"],
		order_by="start_time asc",
	)

	seen = {e.name for e in my_events}
	for e in public_events:
		if e.name not in seen:
			my_events.append(e)

	return my_events


# ─── Helpers ───

def _get_avg_rating(event_name: str) -> float:
	result = frappe.db.sql("""
		SELECT COALESCE(AVG(rating), 0) as avg_rating
		FROM `tabVY Event Review`
		WHERE event = %s
	""", event_name, as_dict=True)
	return float(result[0]["avg_rating"]) if result else 0.0
