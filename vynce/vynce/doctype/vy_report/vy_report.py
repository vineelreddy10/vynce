# Copyright (c) 2026, vineel and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class VYReport(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		created_at: DF.Datetime | None
		details: DF.Text | None
		reason: DF.Literal["Spam", "Harassment", "Fake Profile", "Inappropriate", "Other"]
		reported_by: DF.Link
		reported_user: DF.Link
		resolved_by: DF.Link | None
		status: DF.Literal["Pending", "Reviewed", "Resolved"]
	# end: auto-generated types

	_DOCTYPE_NAME = "VY Report"
