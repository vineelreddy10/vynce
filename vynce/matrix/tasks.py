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

        if healthy:
            frappe.db.set_value("Matrix Settings", "Matrix Settings", {
                "homeserver_status": "Running",
                "last_heartbeat": frappe.utils.now(),
            })
        else:
            frappe.db.set_value("Matrix Settings", "Matrix Settings", {
                "homeserver_status": "Error",
                "last_heartbeat": frappe.utils.now(),
            })
    except Exception as e:
        frappe.logger().error(f"Synapse heartbeat error: {e}")


def synapse_healthcheck():
    """Dedicated health check task for Synapse."""
    heartbeat()
