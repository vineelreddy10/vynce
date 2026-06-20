# Copyright (c) 2026, vineel and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class VYEvent(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		category: DF.Link | None
		cover_image: DF.AttachImage | None
		created_by: DF.Link | None
		description: DF.Text | None
		end_time: DF.Datetime
		group: DF.Link | None
		is_active: DF.Check
		location: DF.Data | None
		location_lat: DF.Float
		location_lng: DF.Float
		max_attendees: DF.Int
		start_time: DF.Datetime
		title: DF.Data
	# end: auto-generated types

	_DOCTYPE_NAME = "VY Event"
