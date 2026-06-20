import frappe
import os
from .storage import init_db
from .utils import get_matrix_db_path


def after_install():
    """Called after the app is installed. Creates the Matrix homeserver SQLite DB."""
    db_path = get_matrix_db_path()
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    init_db()
    frappe.logger().info(f"Matrix homeserver database created at {db_path}")

    # Create Matrix Settings doctype record if it doesn't exist
    if not frappe.db.exists("Matrix Settings", "Matrix Settings"):
        settings = frappe.get_doc({
            "doctype": "Matrix Settings",
            "homeserver_status": "Running",
            "db_path": db_path,
        })
        settings.insert(ignore_permissions=True)
        frappe.db.commit()
