# Copyright (c) 2026, vineel and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class VYNotification(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		body: DF.Text | None
		created_at: DF.Datetime | None
		data: DF.JSON | None
		is_read: DF.Check
		title: DF.Data | None
		type: DF.Literal["Like", "Match", "Message", "Event", "System"]
		user: DF.Link
	# end: auto-generated types

	_DOCTYPE_NAME = "VY Notification"
