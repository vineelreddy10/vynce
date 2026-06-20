# Copyright (c) 2026, vineel and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class VYBlock(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		blocked_by: DF.Link
		blocked_user: DF.Link
		created_at: DF.Datetime | None
		reason: DF.Literal["Spam", "Harassment", "Inappropriate", "Other"]
	# end: auto-generated types

	_DOCTYPE_NAME = "VY Block"
