# Copyright (c) 2026, vineel and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class VYUserMedia(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		file: DF.Attach | None
		is_primary: DF.Check
		media_type: DF.Literal["Image", "Video"]
		order: DF.Int
		parent_doctype: DF.Data | None
		parent_name: DF.Data | None
		uploaded_at: DF.Datetime | None
		user: DF.Link
	# end: auto-generated types

	_DOCTYPE_NAME = "VY User Media"
