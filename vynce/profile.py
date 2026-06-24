import frappe, json, math
from frappe import _
from typing import Any

@frappe.whitelist(allow_guest=True)
def sync_user_profile(doc: Any = None, method: str | None = None):
    """Sync Frappe User changes to VY User Profile."""
    if not doc:
        return
    user = doc if isinstance(doc, str) else doc.get("name")
    if not user:
        return
    if not frappe.db.exists("VY User Profile", {"user": user}):
        profile = frappe.get_doc({
            "doctype": "VY User Profile",
            "user": user,
            "display_name": doc.get("full_name") if isinstance(doc, dict) else user,
            "is_active": 1,
        })
        profile.insert(ignore_permissions=True)
        frappe.db.commit()


# ── GET ─────────────────────────────────────────────


@frappe.whitelist()
def get_my_profile():
    """Return current user's VY User Profile."""
    user = frappe.session.user
    if user == "Guest":
        frappe.throw("Not logged in", frappe.AuthenticationError)
    if not frappe.db.exists("VY User Profile", {"user": user}):
        return {}
    profile = frappe.get_doc("VY User Profile", {"user": user})
    _recalc_strength(profile)
    return _serialize_profile(profile)


def _recalc_strength(profile):
    """Compute and persist profile_strength on the profile doc."""
    strength = _compute_strength(profile)
    if strength != profile.profile_strength:
        profile.db_set("profile_strength", strength, update_modified=False)
    return strength


def _serialize_profile(profile):
    """Convert VY User Profile doc to a clean dict for the API."""
    return {
        "name": profile.name,
        "user": profile.user,
        "display_name": profile.display_name,
        "birth_date": str(profile.birth_date or ""),
        "gender": profile.gender,
        "gender_preference": profile.gender_preference,
        "bio": profile.bio or "",
        "location_lat": profile.location_lat,
        "location_lng": profile.location_lng,
        "max_distance_km": profile.max_distance_km,
        "age_min": profile.age_min,
        "age_max": profile.age_max,
        "is_active": profile.is_active,
        "profile_strength": profile.profile_strength,
        "photos": [{"name": p.name, "image": p.image, "order": p.order, "is_primary": p.is_primary}
                    for p in profile.get("photos", [])],
        "prompts": [{"name": p.name, "prompt": p.prompt, "answer": p.answer}
                     for p in profile.get("prompts", [])],
        "interests": json.loads(profile.get("saved_interests") or "[]"),
    }


# ── UPDATE ──────────────────────────────────────────


@frappe.whitelist()
def update_profile(**kwargs):
    """Update profile fields. Accepts any valid field name as kwarg."""
    user = frappe.session.user
    if user == "Guest":
        frappe.throw("Not logged in", frappe.AuthenticationError)
    if not frappe.db.exists("VY User Profile", {"user": user}):
        frappe.throw("Profile not found")

    profile = frappe.get_doc("VY User Profile", {"user": user})
    allowed = {"display_name", "bio", "location_lat", "location_lng", "location_name",
               "max_distance_km", "age_min", "age_max", "gender_preference", "gender"}
    for key, val in kwargs.items():
        if key in allowed and val is not None:
            profile.set(key, val)
    profile.save(ignore_permissions=True)
    frappe.db.commit()
    _recalc_strength(profile)
    return _serialize_profile(profile)


# ── PHOTOS ──────────────────────────────────────────


@frappe.whitelist()
def upload_photo():
    """Accept multipart file upload and attach to profile."""
    user = frappe.session.user
    if user == "Guest":
        frappe.throw("Not logged in", frappe.AuthenticationError)
    if not frappe.db.exists("VY User Profile", {"user": user}):
        frappe.throw("Profile not found")

    file = frappe.request.files.get("file")
    if not file:
        frappe.throw("No file provided")

    profile = frappe.get_doc("VY User Profile", {"user": user})
    existing = len(profile.get("photos", []))
    if existing >= 6:
        frappe.throw("Maximum 6 photos allowed")

    # Save file via Frappe's upload handler
    from frappe.handler import upload_file
    filedoc = upload_file()

    # Make profile photos publicly accessible (not private)
    file_doc = frappe.get_doc("File", filedoc.get("name"))
    if file_doc:
        file_doc.is_private = 0
        file_doc.save(ignore_permissions=True)
    file_url = filedoc.get("file_url", "")

    if not file_url:
        frappe.throw("Upload failed")

    photo = profile.append("photos", {
        "image": file_url,
        "order": existing + 1,
        "is_primary": 1 if existing == 0 else 0,
    })
    profile.save(ignore_permissions=True)
    frappe.db.commit()
    _recalc_strength(profile)

    return {"name": photo.name, "image": file_url, "order": photo.order, "is_primary": photo.is_primary}


@frappe.whitelist()
def delete_photo(photo_name: str):
    """Delete a photo from the profile."""
    user = frappe.session.user
    if not frappe.db.exists("VY Profile Photo", photo_name):
        return {"ok": False}
    frappe.delete_doc("VY Profile Photo", photo_name, ignore_permissions=True)
    frappe.db.commit()
    profile = frappe.get_doc("VY User Profile", {"user": frappe.session.user})
    _recalc_strength(profile)
    return {"ok": True}


@frappe.whitelist()
def set_primary_photo(photo_name: str):
    """Mark a photo as primary."""
    user = frappe.session.user
    if user == "Guest":
        frappe.throw("Not logged in")
    if not frappe.db.exists("VY Profile Photo", photo_name):
        frappe.throw("Photo not found")

    profile = frappe.get_doc("VY User Profile", {"user": user})
    for p in profile.get("photos", []):
        p.is_primary = 1 if p.name == photo_name else 0
    profile.save(ignore_permissions=True)
    frappe.db.commit()
    return {"ok": True}


@frappe.whitelist()
def reorder_photos(ordered_names: list):
    """Reorder photos. ordered_names is a list of photo names in new order."""
    user = frappe.session.user
    if user == "Guest":
        frappe.throw("Not logged in")
    profile = frappe.get_doc("VY User Profile", {"user": user})
    name_order = {n: i + 1 for i, n in enumerate(ordered_names)}
    for p in profile.get("photos", []):
        if p.name in name_order:
            p.order = name_order[p.name]
    profile.save(ignore_permissions=True)
    frappe.db.commit()
    return {"ok": True}


# ── INTERESTS ───────────────────────────────────────


@frappe.whitelist()
def save_interests(interest_names: list):
    """Save a list of interest titles to the profile."""
    user = frappe.session.user
    if user == "Guest":
        frappe.throw("Not logged in")
    if not frappe.db.exists("VY User Profile", {"user": user}):
        frappe.throw("Profile not found")

    profile = frappe.get_doc("VY User Profile", {"user": user})
    profile.set("saved_interests", json.dumps(interest_names))
    profile.save(ignore_permissions=True)
    frappe.db.commit()
    _recalc_strength(profile)
    return {"ok": True, "interests": interest_names}


# ── PROMPTS ─────────────────────────────────────────


@frappe.whitelist()
def save_prompts(prompts: list):
    """Save prompt answers. prompts = [{prompt, answer}, ...]"""
    user = frappe.session.user
    if user == "Guest":
        frappe.throw("Not logged in")
    if not frappe.db.exists("VY User Profile", {"user": user}):
        frappe.throw("Profile not found")

    profile = frappe.get_doc("VY User Profile", {"user": user})
    profile.set("prompts", [])
    for p in prompts:
        if p.get("answer", "").strip():
            profile.append("prompts", {"prompt": p["prompt"], "answer": p["answer"]})
    profile.save(ignore_permissions=True)
    frappe.db.commit()
    _recalc_strength(profile)
    return {"ok": True, "count": len(profile.get("prompts", []))}


# ── PREFERENCES ─────────────────────────────────────


@frappe.whitelist()
def save_preferences(data: str):
    """Save discovery preferences. data is a JSON string."""
    import json
    vals = json.loads(data) if isinstance(data, str) else data
    user = frappe.session.user
    if user == "Guest":
        frappe.throw("Not logged in")
    if not frappe.db.exists("VY User Profile", {"user": user}):
        frappe.throw("Profile not found")

    profile = frappe.get_doc("VY User Profile", {"user": user})
    for key in ("max_distance_km", "age_min", "age_max", "gender_preference"):
        if key in vals:
            profile.set(key, vals[key])
    profile.save(ignore_permissions=True)
    frappe.db.commit()
    _recalc_strength(profile)
    return {"ok": True}


# ── PROFILE STRENGTH ────────────────────────────────


@frappe.whitelist()
def calculate_profile_strength():
    """Calculate and return profile_strength percentage."""
    user = frappe.session.user
    if user == "Guest" or not frappe.db.exists("VY User Profile", {"user": user}):
        return {"profile_strength": 0}

    profile = frappe.get_doc("VY User Profile", {"user": user})
    strength = _compute_strength(profile)
    if strength != profile.profile_strength:
        profile.db_set("profile_strength", strength, update_modified=False)
    return {"profile_strength": strength}


def _compute_strength(profile):
    """Compute profile strength based on completed fields."""
    score = 0.0
    # Photos: 25% for 3+, prorated below
    photo_count = len(profile.get("photos", []))
    score += min(photo_count / 3, 1.0) * 25
    # Interests: 20% for 5+
    interests = json.loads(profile.get("saved_interests") or "[]")
    score += min(len(interests) / 5, 1.0) * 20
    # Prompts: 20% for 3 answered
    answered = sum(1 for p in profile.get("prompts", []) if p.answer and p.answer.strip())
    score += min(answered / 3, 1.0) * 20
    # Bio: 15%
    if profile.bio and profile.bio.strip():
        score += 15
    # Preferences: 10% (has any set)
    if profile.max_distance_km or profile.age_min or profile.gender_preference != "All":
        score += 10
    # Location: 10%
    if profile.location_lat and profile.location_lng:
        score += 10
    # Base: 10% (registered)
    score += 10
    return min(round(score), 100)


# ── LIST ALL INTERESTS ──────────────────────────────


@frappe.whitelist(allow_guest=True)
def get_interests():
    """Return all VY Interest titles grouped by category."""
    interests = frappe.get_all("VY Interest", fields=["title", "category"], order_by="category asc")
    grouped = {}
    for i in interests:
        grouped.setdefault(i.category, []).append(i.title)
    return {"interests": interests, "grouped": grouped}


# ── PERMISSIONS ─────────────────────────────────────


def get_permission_query_conditions(user: str | None = None) -> str:
    if not user:
        user = frappe.session.user
    if user == "Administrator":
        return ""
    return f"""(`tabVY User Profile`.`user` = {frappe.db.escape(user)}
        OR `tabVY User Profile`.`is_active` = 1)"""


def has_permission(doc, ptype: str, user: str | None = None) -> bool:
    if not user:
        user = frappe.session.user
    if user == "Administrator":
        return True
    if doc.user == user:
        return True
    if ptype == "read" and doc.is_active:
        return True
    return False


@frappe.whitelist(allow_guest=True)
def get_photo(photo_name: str):
    """Public endpoint to serve profile photos without cookie auth."""
    if not frappe.db.exists("VY Profile Photo", photo_name):
        frappe.throw("Photo not found", frappe.PageDoesNotExistError)

    image = frappe.db.get_value("VY Profile Photo", photo_name, "image")
    if not image:
        frappe.throw("Photo not found", frappe.PageDoesNotExistError)

    # Strip leading / and route through Frappe's file handler
    file_path = image.lstrip("/")
    # Build full URL to the file
    site_url = frappe.utils.get_url()
    return {"url": f"{site_url}/{file_path}", "path": file_path}

