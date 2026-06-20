# Copyright (c) 2026, vineel and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class VYUserProfile(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF
		from vynce.vynce.doctype.vy_profile_photo.vy_profile_photo import VYProfilePhoto
		from vynce.vynce.doctype.vy_prompt_answer.vy_prompt_answer import VYPromptAnswer

		age_max: DF.Int
		age_min: DF.Int
		bio: DF.Text | None
		birth_date: DF.Date | None
		device_tokens: DF.JSON | None
		display_name: DF.Data | None
		gender: DF.Literal["M", "F", "NB", "PNS"]
		gender_preference: DF.Literal["M", "F", "NB", "All"]
		is_active: DF.Check
		is_verified: DF.Check
		last_active: DF.Datetime | None
		location_lat: DF.Float
		location_lng: DF.Float
		matrix_user_id: DF.Data | None
		max_distance_km: DF.Int
		photos: DF.Table[VYProfilePhoto]
		profile_strength: DF.Percent
		prompts: DF.Table[VYPromptAnswer]
		user: DF.Link
	# end: auto-generated types

	_DOCTYPE_NAME = "VY User Profile"
