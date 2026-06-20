import frappe
from frappe import _


@frappe.whitelist(allow_guest=True)
def sync_user_profile(doc: dict | None = None, method: str | None = None):
    """Sync Frappe User changes to VY User Profile."""
    if not doc:
        return

    user = doc if isinstance(doc, str) else doc.get("name")
    if not user:
        return

    # Auto-create VY User Profile if missing
    if not frappe.db.exists("VY User Profile", {"user": user}):
        profile = frappe.get_doc({
            "doctype": "VY User Profile",
            "user": user,
            "display_name": doc.get("full_name") if isinstance(doc, dict) else user,
            "is_active": 1,
        })
        profile.insert(ignore_permissions=True)
        frappe.db.commit()


def get_permission_query_conditions(user: str | None = None) -> str:
    """Filter VY User Profile list: users see own, others only if not blocked."""
    if not user:
        user = frappe.session.user

    if user == "Administrator":
        return ""

    return f"""(`tabVY User Profile`.`user` = {frappe.db.escape(user)}
        OR `tabVY User Profile`.`is_active` = 1)"""


def has_permission(doc, ptype: str, user: str | None = None) -> bool:
    """Check permission on individual VY User Profile."""
    if not user:
        user = frappe.session.user

    if user == "Administrator":
        return True

    # User can always read/write their own profile
    if doc.user == user:
        return True

    # Others can only read active profiles
    if ptype == "read" and doc.is_active:
        return True

    return False
