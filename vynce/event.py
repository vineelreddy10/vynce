import frappe
from frappe import _


@frappe.whitelist()
def list_events(category: str | None = None, page: int = 1, page_size: int = 20) -> dict:
	user = frappe.session.user
	if user == "Guest":
		frappe.throw(_("Not logged in"), frappe.AuthenticationError)

	page = int(page)
	page_size = int(page_size)

	filters = {
		"end_time": [">", frappe.utils.now()],
		"is_active": 1,
	}
	if category:
		filters["category"] = category

	events = frappe.get_all(
		"VY Event",
		filters=filters,
		fields=[
			"name", "title", "description", "cover_image",
			"category", "location", "start_time", "end_time",
			"max_attendees", "created_by",
		],
		order_by="start_time asc",
		limit_start=(page - 1) * page_size,
		limit_page_length=page_size,
	)

	for event in events:
		event["going_count"] = frappe.db.count("VY Event Attendee", {
			"event": event.name,
			"status": "Going",
		})
		event["my_rsvp"] = frappe.db.get_value(
			"VY Event Attendee",
			{"event": event.name, "user": user},
			"status",
		)

	total = frappe.db.count("VY Event", filters=filters)

	return {
		"events": events,
		"total": total,
		"page": page,
		"page_size": page_size,
	}


@frappe.whitelist()
def get_event_details(event_name: str) -> dict:
	user = frappe.session.user
	if user == "Guest":
		frappe.throw(_("Not logged in"), frappe.AuthenticationError)

	event = frappe.get_doc("VY Event", event_name)
	if not event:
		frappe.throw(_("Event not found"), frappe.DoesNotExistError)

	if not event.is_active:
		frappe.throw(_("Event not found"), frappe.DoesNotExistError)

	attendees = frappe.db.sql("""
		SELECT
			a.name, a.user, a.status, a.created_at,
			p.display_name, p.profile_photo
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

	return {
		"event": event.as_dict(),
		"attendees": attendees,
		"my_rsvp": my_rsvp,
		"going_count": going_count,
		"interested_count": interested_count,
	}


@frappe.whitelist()
def rsvp(event_name: str, status: str) -> dict:
	user = frappe.session.user
	if user == "Guest":
		frappe.throw(_("Not logged in"), frappe.AuthenticationError)

	valid_statuses = {"Going", "Interested", "Not Going"}
	if status not in valid_statuses:
		frappe.throw(_("Invalid RSVP status. Must be one of: {0}").format(", ".join(sorted(valid_statuses))))

	event = frappe.get_doc("VY Event", event_name)
	if not event or not event.is_active:
		frappe.throw(_("Event not found"), frappe.DoesNotExistError)

	if status == "Going" and event.max_attendees:
		current_going = frappe.db.count("VY Event Attendee", {
			"event": event_name,
			"status": "Going",
		})
		if current_going >= event.max_attendees:
			frappe.throw(_("This event is full. Maximum {0} attendees reached.").format(event.max_attendees))

	existing = frappe.db.get_value(
		"VY Event Attendee",
		{"event": event_name, "user": user},
		"name",
	)

	if existing:
		doc = frappe.get_doc("VY Event Attendee", existing)
		doc.status = status
		doc.save(ignore_permissions=True)
	else:
		doc = frappe.get_doc({
			"doctype": "VY Event Attendee",
			"event": event_name,
			"user": user,
			"status": status,
			"created_at": frappe.utils.now(),
		})
		doc.insert(ignore_permissions=True)

	frappe.db.commit()

	going_count = frappe.db.count("VY Event Attendee", {
		"event": event_name,
		"status": "Going",
	})
	interested_count = frappe.db.count("VY Event Attendee", {
		"event": event_name,
		"status": "Interested",
	})

	return {
		"status": status,
		"going_count": going_count,
		"interested_count": interested_count,
	}
