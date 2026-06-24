"""Seed the Vynce test site with realistic users and data for manual QA.

Run with:
    bench --site test.localhost execute vynce.vynce.manual_qa_seed.run_seed
"""
from __future__ import annotations

import json
import sys
import frappe
from datetime import date, datetime, timedelta

from vynce.utils import GENDER_MAP, calculate_age

TEST_EMAILS = [
    "alex@vynce.app",
    "blake@vynce.app",
    "casey@vynce.app",
    "dana@vynce.app",
]

COMMON_PASSWORD = "TestPass123!"

USERS = {
    "alex@vynce.app": {
        "first_name": "Alex",
        "gender": "Male",
        "birth_date": date(1998, 5, 12),
        "bio": "Coffee lover, hiking enthusiast, and amateur photographer.",
        "interests": ["Hiking", "Photography", "Coffee", "Travel", "Movies", "Music"],
        "prompts": [
            ("A perfect day looks like", "Hiking to a viewpoint with great coffee afterwards."),
            ("My favorite travel story", "Got lost in Tokyo and found the best ramen shop."),
            ("Two truths and a lie", "I speak 3 languages, I’ve climbed a volcano, I hate pizza."),
        ],
        "lat": 40.7128,
        "lng": -74.0060,
        "location_name": "New York, NY",
    },
    "blake@vynce.app": {
        "first_name": "Blake",
        "gender": "Female",
        "birth_date": date(1999, 8, 22),
        "bio": "Yoga instructor who loves live music and trying new restaurants.",
        "interests": ["Yoga", "Food", "Music", "Travel", "Reading", "Dancing"],
        "prompts": [
            ("My happy place", "A sunny rooftop with good friends and mocktails."),
            ("Best concert I’ve been to", "An intimate acoustic set under the stars."),
            ("I’m looking for", "Someone kind, curious, and up for adventures."),
        ],
        "lat": 40.7200,
        "lng": -73.9950,
        "location_name": "New York, NY",
    },
    "casey@vynce.app": {
        "first_name": "Casey",
        "gender": "Non-Binary",
        "birth_date": date(1997, 3, 3),
        "bio": "Digital artist and gamer. Always sketching something new.",
        "interests": ["Art", "Gaming", "Anime", "Music", "Technology"],
        "prompts": [
            ("Current obsession", "A cozy indie game with a beautiful soundtrack."),
            ("My creative process", "Late nights, lo-fi beats, and lots of tea."),
        ],
        "lat": 40.7300,
        "lng": -73.9850,
        "location_name": "Brooklyn, NY",
    },
    "dana@vynce.app": {
        "first_name": "Dana",
        "gender": "Female",
        "birth_date": date(2000, 11, 30),
        "bio": "Bookworm and cafe hopper. Let’s swap recommendations.",
        "interests": ["Reading", "Coffee", "Writing", "Music", "Travel"],
        "prompts": [
            ("Currently reading", "A mystery novel set in a small coastal town."),
            ("Ideal first date", "A quiet bookstore followed by coffee."),
        ],
        "lat": 40.7400,
        "lng": -73.9750,
        "location_name": "Manhattan, NY",
    },
}


def _ensure_role():
    if not frappe.db.exists("Role", "VY User"):
        role = frappe.get_doc({"doctype": "Role", "role_name": "VY User", "desk_access": 0})
        role.insert(ignore_permissions=True)
        frappe.db.commit()


def _delete_previous_test_data():
    emails = [e.replace("'", "''") for e in TEST_EMAILS]
    quoted = ", ".join(f"'{e}'" for e in emails)

    # Table-specific deletions with correct column names
    deletions = [
        ("tabVY Event Attendee", f"`user` IN ({quoted})"),
        ("tabVY Event", f"`created_by` IN ({quoted}) OR `user` IN ({quoted})"),
        ("tabVY Group Member", f"`user` IN ({quoted})"),
        ("tabVY Group", f"`created_by` IN ({quoted})"),
        ("tabVY Notification", f"`user` IN ({quoted})"),
        ("tabVY Block", f"`blocked_by` IN ({quoted}) OR `blocked_user` IN ({quoted})"),
        ("tabVY Match", f"`user_1` IN ({quoted}) OR `user_2` IN ({quoted})"),
        ("tabVY Like", f"`from_user` IN ({quoted}) OR `to_user` IN ({quoted})"),
        ("tabVY User Profile", f"`user` IN ({quoted})"),
    ]
    for table, where in deletions:
        try:
            frappe.db.sql(f"DELETE FROM `{table}` WHERE {where}")
        except Exception as e:
            pass

    for email in emails:
        try:
            frappe.db.sql(f"DELETE FROM `tabUser` WHERE `name` = '{email}'")
        except Exception:
            pass

    frappe.db.commit()

    # Clear cached discover feeds for test users
    for email in emails:
        frappe.cache.delete_value(f"discover_feed:{email}")


def _compute_strength(profile) -> int:
    score = 0.0
    photo_count = len(profile.get("photos", []))
    score += min(photo_count / 3, 1.0) * 25
    interests = json.loads(profile.get("saved_interests") or "[]")
    score += min(len(interests) / 5, 1.0) * 20
    answered = sum(1 for p in profile.get("prompts", []) if p.answer and p.answer.strip())
    score += min(answered / 3, 1.0) * 20
    if profile.bio and profile.bio.strip():
        score += 15
    if profile.max_distance_km or profile.age_min or profile.gender_preference != "All":
        score += 10
    if profile.location_lat and profile.location_lng:
        score += 10
    score += 10
    return min(round(score), 100)


def _create_matrix_user(username: str, display_name: str):
    from vynce.matrix.management import create_user as create_matrix_user
    return create_matrix_user(
        username=username.split("@")[0],
        password=COMMON_PASSWORD,
        displayname=display_name,
        admin=False,
    )


def _add_profile_photo(profile, index: int):
    # Use a stable placeholder avatar so the frontend has an image URL
    url = f"https://i.pravatar.cc/300?u={profile.user}"
    photo = profile.append("photos", {
        "image": url,
        "order": index + 1,
        "is_primary": 1 if index == 0 else 0,
    })
    return photo


def _seed_users():
    profiles = {}
    for email, data in USERS.items():
        user_doc = frappe.get_doc({
            "doctype": "User",
            "email": email,
            "first_name": data["first_name"],
            "send_welcome_email": 0,
            "new_password": COMMON_PASSWORD,
            "roles": [{"role": "VY User"}],
        })
        user_doc.insert(ignore_permissions=True, ignore_links=True)

        # The hook may have created a basic profile; fetch or create
        if frappe.db.exists("VY User Profile", {"user": email}):
            profile = frappe.get_doc("VY User Profile", {"user": email})
        else:
            profile = frappe.get_doc({
                "doctype": "VY User Profile",
                "user": email,
                "is_active": 1,
            })
            profile.insert(ignore_permissions=True, ignore_links=True)

        gender_code = GENDER_MAP[data["gender"]]
        profile.display_name = data["first_name"]
        profile.birth_date = data["birth_date"]
        profile.gender = gender_code
        profile.bio = data["bio"]
        profile.location_lat = data["lat"]
        profile.location_lng = data["lng"]
        profile.location_name = data["location_name"]
        profile.max_distance_km = 50
        profile.age_min = 18
        profile.age_max = 45
        profile.gender_preference = "All"
        profile.saved_interests = json.dumps(data["interests"])

        # Add prompts
        profile.set("prompts", [])
        for prompt, answer in data["prompts"]:
            profile.append("prompts", {"prompt": prompt, "answer": answer})

        # Add photos (2 per profile => ~16% each, still enough with bio/location/preferences)
        profile.set("photos", [])
        for i in range(2):
            _add_profile_photo(profile, i)

        profile.profile_strength = _compute_strength(profile)
        profile.save(ignore_permissions=True)

        # Create Matrix user for chat
        try:
            matrix_result = _create_matrix_user(email, data["first_name"])
            profile.db_set("matrix_user_id", matrix_result["user_id"], update_modified=False)
        except Exception as e:
            frappe.logger().warning(f"Matrix user creation failed for {email}: {e}")

        profiles[email] = profile
        frappe.db.commit()

    return profiles


def _seed_likes_and_matches():
    alex = "alex@vynce.app"
    blake = "blake@vynce.app"
    casey = "casey@vynce.app"

    # Alex likes Blake
    like1 = frappe.get_doc({
        "doctype": "VY Like",
        "from_user": alex,
        "to_user": blake,
        "like_type": "Like",
    })
    like1.insert(ignore_permissions=True)
    frappe.db.commit()

    # Casey likes Alex (notification test)
    like2 = frappe.get_doc({
        "doctype": "VY Like",
        "from_user": casey,
        "to_user": alex,
        "like_type": "Like",
    })
    like2.insert(ignore_permissions=True)
    frappe.db.commit()

    # Blake likes Alex -> match
    like3 = frappe.get_doc({
        "doctype": "VY Like",
        "from_user": blake,
        "to_user": alex,
        "like_type": "Like",
    })
    like3.insert(ignore_permissions=True)
    frappe.db.commit()

    # Create notifications for these seed likes (since they bypassed the API)
    from vynce.notification import send_notification

    alex_profile = frappe.db.get_value("VY User Profile", {"user": alex}, "display_name")
    blake_profile = frappe.db.get_value("VY User Profile", {"user": blake}, "display_name")
    casey_profile = frappe.db.get_value("VY User Profile", {"user": casey}, "display_name")

    # Casey liked Alex -> notify Alex
    send_notification(alex, "Like", "New Like!", f"{casey_profile} liked your profile.", {"from_user": casey, "like_type": "Like"})
    # Alex liked Blake -> notify Blake
    send_notification(blake, "Like", "New Like!", f"{alex_profile} liked your profile.", {"from_user": alex, "like_type": "Like"})

    from vynce.match import check_and_create_match
    match_id = check_and_create_match(alex, blake)

    # Send notification for group creation to Blake
    send_notification(blake, "Event", "Group Invitation", f"You've been added to Weekend Hikers NYC.", {"group": "Weekend Hikers NYC"})


def _seed_group_and_event():
    alex = "alex@vynce.app"
    blake = "blake@vynce.app"

    group = frappe.get_doc({
        "doctype": "VY Group",
        "title": "Weekend Hikers NYC",
        "description": "A casual group for weekend hikes around NYC.",
        "category": "Travel",
        "location": "Central Park, NYC",
        "cover_image": "https://images.unsplash.com/photo-1551632811-561732d1e306?w=800",
        "member_count": 2,
        "is_active": 1,
        "created_by": alex,
    })
    group.insert(ignore_permissions=True)

    for user, role in [(alex, "Admin"), (blake, "Member")]:
        member = frappe.get_doc({
            "doctype": "VY Group Member",
            "group": group.name,
            "user": user,
            "role": role,
            "joined_at": frappe.utils.now(),
        })
        member.insert(ignore_permissions=True)

    start = datetime.now() + timedelta(days=2)
    end = start + timedelta(hours=3)
    event = frappe.get_doc({
        "doctype": "VY Event",
        "title": "Sunset Hike & Picnic",
        "description": "Join us for a scenic sunset hike followed by a picnic.",
        "location": "Prospect Park, Brooklyn",
        "start_time": start,
        "end_time": end,
        "category": "Travel",
        "cover_image": "https://images.unsplash.com/photo-1501555088652-021faa106b9b?w=800",
        "max_attendees": 20,
        "created_by": alex,
        "group": group.name,
        "is_active": 1,
    })
    event.insert(ignore_permissions=True)

    attendee = frappe.get_doc({
        "doctype": "VY Event Attendee",
        "event": event.name,
        "user": blake,
        "status": "Going",
    })
    attendee.insert(ignore_permissions=True)

    frappe.db.commit()


def _seed_safety():
    alex = "alex@vynce.app"
    dana = "dana@vynce.app"
    block = frappe.get_doc({
        "doctype": "VY Block",
        "blocked_by": alex,
        "blocked_user": dana,
        "reason": "Other",
    })
    block.insert(ignore_permissions=True)
    frappe.db.commit()


def run_seed():
    frappe.init(site="test.localhost", sites_path="/home/vineel/dev/galaxy/sites")
    frappe.connect()
    frappe.set_user("Administrator")

    _ensure_role()
    _delete_previous_test_data()
    profiles = _seed_users()
    _seed_likes_and_matches()
    _seed_group_and_event()
    _seed_safety()

    print("Seed complete. Users:")
    for email in TEST_EMAILS:
        p = profiles.get(email)
        if p:
            print(f"  {email} -> {p.name} (strength={p.profile_strength}, matrix={p.matrix_user_id or 'N/A'})")

    frappe.db.commit()


if __name__ == "__main__":
    run_seed()
