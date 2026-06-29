from frappe.model.document import Document

class VYEvent(Document):
	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		category: DF.Link | None
		cover_image: DF.AttachImage | None
		cover_video: DF.Data | None
		created_by: DF.Link | None
		description: DF.TextEditor | None
		end_time: DF.Datetime
		event_type: DF.Literal | None
		group: DF.Link | None
		is_active: DF.Check
		is_featured: DF.Check
		is_free: DF.Check
		is_multi_day: DF.Check
		is_recurring: DF.Check
		location: DF.Data | None
		location_lat: DF.Float
		location_lng: DF.Float
		max_attendees: DF.Int
		price: DF.Currency
		start_time: DF.Datetime
		subtitle: DF.Data | None
		tags: DF.SmallText | None
		timezone: DF.Literal | None
		venue_type: DF.Literal | None
		venue_details: DF.SmallText | None
		online_url: DF.Data | None
		visibility: DF.Literal | None
		registration_deadline: DF.Datetime | None
		waitlist_enabled: DF.Check
		cancellation_policy: DF.SmallText | None
		refund_policy: DF.SmallText | None
		age_restriction: DF.Int
		family_friendly: DF.Check
		pet_friendly: DF.Check
		accessibility_info: DF.SmallText | None
		contact_email: DF.Data | None
		promotional_video: DF.Data | None
		featured_until: DF.Datetime | None
		recurrence_pattern: DF.Literal | None
		title: DF.Data

	_DOCTYPE_NAME = "VY Event"
