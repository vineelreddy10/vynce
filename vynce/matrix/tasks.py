"""Scheduled tasks for Synapse health monitoring."""

import frappe
from .synapse_client import SynapseClient


def init():
    """Ensure Synapse is initialized. Called from various hooks."""
    pass


def heartbeat():
    """Periodic task: check Synapse health and update Matrix Settings."""
    try:
        client = SynapseClient()
        healthy = client.health_check()

        if not frappe.db.exists("Matrix Settings", "Matrix Settings"):
            return

        settings = {}

        if healthy:
            settings["homeserver_status"] = "Running"
            # Fetch room count from Synapse Admin API
            try:
                rooms = client.get_rooms(limit=0)
                settings["total_rooms"] = rooms.get("total_rooms", 0)
            except Exception:
                pass
        else:
            settings["homeserver_status"] = "Error"

        settings["last_heartbeat"] = frappe.utils.now()
        frappe.db.set_value("Matrix Settings", "Matrix Settings", settings)

    except Exception as e:
        frappe.logger().error(f"Synapse heartbeat error: {e}")


def synapse_healthcheck():
    """Dedicated health check task for Synapse."""
    heartbeat()
