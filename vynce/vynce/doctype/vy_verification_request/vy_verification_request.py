# Copyright (c) 2026, vineel and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class VYVerificationRequest(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		created_at: DF.Datetime | None
		photo: DF.AttachImage | None
		reviewed_by: DF.Link | None
		status: DF.Literal["Pending", "Approved", "Rejected"]
		user: DF.Link
	# end: auto-generated types

	_DOCTYPE_NAME = "VY Verification Request"
