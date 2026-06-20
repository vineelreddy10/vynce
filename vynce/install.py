import frappe


def after_install():
    """Run after app installation. Seeds interests and more."""
    seed_interests()


def seed_interests():
    """Create default interest records."""
    interests = [
        ("Adventure Travel", "Travel"),
        ("Photography", "Arts"),
        ("Cooking", "Food"),
        ("Yoga & Meditation", "Wellness"),
        ("Live Music", "Music"),
        ("Reading", "Books"),
        ("Running", "Fitness"),
        ("Hiking", "Fitness"),
        ("Dancing", "Fitness"),
        ("Painting", "Arts"),
        ("Volunteering", "Lifestyle"),
        ("Board Games", "Lifestyle"),
        ("Movie Nights", "Lifestyle"),
        ("Wine Tasting", "Food"),
        ("Surfing", "Fitness"),
        ("Rock Climbing", "Fitness"),
        ("Stand-up Comedy", "Arts"),
        ("Karaoke", "Music"),
        ("Baking", "Food"),
        ("Camping", "Travel"),
        ("Tech & Startups", "Tech"),
        ("Gaming", "Tech"),
        ("Fashion", "Lifestyle"),
        ("Gardening", "Lifestyle"),
        ("Pets & Animals", "Lifestyle"),
        ("Language Learning", "Books"),
        ("Cycling", "Fitness"),
        ("Skiing", "Fitness"),
        ("Pottery", "Arts"),
        ("Sailing", "Travel"),
    ]

    for title, category in interests:
        if not frappe.db.exists("VY Interest", title):
            doc = frappe.get_doc({
                "doctype": "VY Interest",
                "title": title,
                "category": category,
            })
            doc.insert(ignore_permissions=True)

    frappe.db.commit()
    print(f"Seeded {len(interests)} interests")
