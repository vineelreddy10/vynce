import frappe


@frappe.whitelist(allow_guest=True)
def ping():
	return {"status": "ok"}


@frappe.whitelist(allow_guest=True)
def get_csrf_token():
	return frappe.sessions.get_csrf_token()


@frappe.whitelist(allow_guest=True)
def get_session_user():
	user = frappe.session.user
	if user == "Guest":
		return {"user": None}
	return {"user": user}
