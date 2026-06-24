# Copyright (c) 2026, vineel and contributors
# See license.txt

import frappe
from frappe.tests import IntegrationTestCase

from vynce.discover import get_feed, like_user
from vynce.match import check_and_create_match
from vynce.group import list_groups, get_group_details, join_group, leave_group
from vynce.event import list_events, get_event_details, rsvp
from vynce.safety import block_user, unblock_user, report_user, get_blocked_users
from vynce.notification import get_notifications, send_notification, mark_all_read


class TestVynceFeatures(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self._cleanup_test_users()
		self.user_a = self._create_user("test_a@example.com")
		self.user_b = self._create_user("test_b@example.com")
		self._create_profile(self.user_a, "Test A", "M", "All", 37.7749, -122.4194)
		self._create_profile(self.user_b, "Test B", "F", "All", 37.7749, -122.4194)

	def _cleanup_test_users(self):
		for email in ["test_a@example.com", "test_b@example.com"]:
			if frappe.db.exists("VY User Profile", email):
				frappe.delete_doc("VY User Profile", email, force=True)
			if frappe.db.exists("User", email):
				frappe.delete_doc("User", email, force=True)
		frappe.db.commit()

	def tearDown(self):
		frappe.set_user("Administrator")
		for doctype in ["VY Group Member", "VY Group", "VY Event Attendee", "VY Event"]:
			frappe.db.delete(doctype)
		frappe.db.delete("VY Block")
		frappe.db.delete("VY Report")
		frappe.db.delete("VY Notification")
		frappe.db.delete("VY Like")
		frappe.db.delete("VY Match")
		frappe.db.delete("VY User Profile")
		for email in ["test_a@example.com", "test_b@example.com"]:
			if frappe.db.exists("User", email):
				frappe.delete_doc("User", email, force=True)
		frappe.db.commit()

	def _create_user(self, email):
		if frappe.db.exists("User", email):
			return email
		user = frappe.get_doc({
			"doctype": "User",
			"email": email,
			"first_name": email.split("@")[0],
			"enabled": 1,
		})
		user.insert(ignore_permissions=True)
		return email

	def _create_profile(self, user, display_name, gender, preference, lat, lng):
		if not frappe.db.exists("VY User Profile", user):
			return
		profile = frappe.get_doc("VY User Profile", user)
		profile.update({
			"display_name": display_name,
			"gender": gender,
			"gender_preference": preference,
			"birth_date": "1990-01-01",
			"location_lat": lat,
			"location_lng": lng,
			"is_active": 1,
		})
		profile.save(ignore_permissions=True)

	def _create_group(self, created_by):
		group = frappe.get_doc({
			"doctype": "VY Group",
			"title": "Test Group",
			"description": "A test group",
			"location": "San Francisco",
			"created_by": created_by,
			"is_active": 1,
		})
		group.insert(ignore_permissions=True)
		return group.name

	def _create_event(self, created_by, group=None):
		event = frappe.get_doc({
			"doctype": "VY Event",
			"title": "Test Event",
			"description": "A test event",
			"location": "San Francisco",
			"start_time": frappe.utils.now_datetime(),
			"end_time": frappe.utils.add_to_date(frappe.utils.now_datetime(), hours=2),
			"created_by": created_by,
			"group": group,
			"is_active": 1,
		})
		event.insert(ignore_permissions=True)
		return event.name

	def test_like_user_creates_like(self):
		frappe.set_user(self.user_a)
		like_user(self.user_b, "Like")
		self.assertTrue(frappe.db.exists("VY Like", {"from_user": self.user_a, "to_user": self.user_b}))

	def test_like_user_blocks_duplicate(self):
		frappe.set_user(self.user_a)
		like_user(self.user_b, "Like")
		with self.assertRaises(frappe.ValidationError):
			like_user(self.user_b, "Like")

	def test_mutual_like_creates_match(self):
		frappe.set_user(self.user_a)
		like_user(self.user_b, "Like")
		frappe.set_user(self.user_b)
		like_user(self.user_a, "Like")
		self.assertTrue(frappe.db.exists("VY Match", {
			"user_1": self.user_a,
			"user_2": self.user_b,
		}) or frappe.db.exists("VY Match", {
			"user_1": self.user_b,
			"user_2": self.user_a,
		}))

	def test_group_lifecycle(self):
		frappe.set_user(self.user_a)
		group_name = self._create_group(self.user_a)
		groups = list_groups()
		self.assertTrue(any(g["group_name"] == group_name for g in groups["groups"]))

		frappe.set_user(self.user_b)
		join_group(group_name)
		self.assertTrue(frappe.db.exists("VY Group Member", {"group": group_name, "user": self.user_b}))

		leave_group(group_name)
		self.assertFalse(frappe.db.exists("VY Group Member", {"group": group_name, "user": self.user_b}))

	def test_event_rsvp(self):
		frappe.set_user(self.user_a)
		group_name = self._create_group(self.user_a)
		event_name = self._create_event(self.user_a, group=group_name)
		frappe.set_user(self.user_b)
		rsvp(event_name, "Going")
		self.assertTrue(frappe.db.exists("VY Event Attendee", {"event": event_name, "user": self.user_b, "status": "Going"}))

	def test_safety_block_and_report(self):
		frappe.set_user(self.user_a)
		block_user(self.user_b)
		blocked = get_blocked_users()
		self.assertTrue(any(b.get("user") == self.user_b for b in blocked))
		report_user(self.user_b, "Harassment", "Details")
		self.assertTrue(frappe.db.exists("VY Report", {"reported_by": self.user_a, "reported_user": self.user_b}))
		unblock_user(self.user_b)
		self.assertFalse(any(b.get("user") == self.user_b for b in get_blocked_users()))

	def test_notifications(self):
		frappe.set_user(self.user_a)
		send_notification(self.user_a, "System", "Hello", "Test body")
		notifications = get_notifications()
		self.assertTrue(any(n["title"] == "Hello" for n in notifications))
		mark_all_read()
		self.assertEqual(frappe.db.count("VY Notification", {"user": self.user_a, "is_read": 0}), 0)
