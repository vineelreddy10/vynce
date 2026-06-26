# Copyright (c) 2026, vineel and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class VYGroupPost(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		content: DF.Text | None
		created_at: DF.Datetime | None
		group: DF.Link
		media: DF.Attach | None
		media_type: DF.Literal["", "Image", "Video"] | None
		user: DF.Link
	# end: auto-generated types

	_DOCTYPE_NAME = "VY Group Post"
