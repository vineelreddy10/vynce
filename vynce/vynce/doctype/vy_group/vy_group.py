# Copyright (c) 2026, vineel and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class VYGroup(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		category: DF.Link | None
		cover_image: DF.AttachImage | None
		created_by: DF.Link | None
		description: DF.Text | None
		is_active: DF.Check
		location: DF.Data | None
		member_count: DF.Int
		title: DF.Data
	# end: auto-generated types

	_DOCTYPE_NAME = "VY Group"
