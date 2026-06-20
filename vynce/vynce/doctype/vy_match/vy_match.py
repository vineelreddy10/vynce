# Copyright (c) 2026, vineel and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class VYMatch(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		is_active: DF.Check
		matched_at: DF.Datetime | None
		matrix_room_id: DF.Data | None
		user_1: DF.Link
		user_2: DF.Link
	# end: auto-generated types

	_DOCTYPE_NAME = "VY Match"
