# Copyright (c) 2026, vineel and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class VYInterest(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		category: DF.Literal["Lifestyle", "Food", "Arts", "Fitness", "Music", "Travel", "Books", "Wellness", "Tech", "Other"]
		title: DF.Data
	# end: auto-generated types

	_DOCTYPE_NAME = "VY Interest"
