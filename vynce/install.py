import frappe


def after_install():
    """Run after app installation. Sets up Synapse and seeds interests."""
    try:
        from vynce.matrix.install import after_install as setup_matrix
        setup_matrix()
    except Exception as e:
        frappe.logger().error(f"Matrix setup failed (non-fatal): {e}")

    seed_interests()
    seed_events()
    seed_groups()


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


def seed_events():
    """Create sample events for demo."""
    now = frappe.utils.now_datetime()

    events = [
        {
            "title": "Sunset Yoga at Marina Beach",
            "description": "Unwind with a relaxing sunset yoga session on the marina. All levels welcome. Bring your own mat and water bottle. We'll end with a guided meditation as the sun sets over the water.",
            "location": "Marina Beach Boardwalk",
            "category": "Yoga & Meditation",
            "start_time": frappe.utils.add_to_date(now, days=3, hours=17),
            "end_time": frappe.utils.add_to_date(now, days=3, hours=19),
            "max_attendees": 30,
        },
        {
            "title": "Wine & Paint Night",
            "description": "Sip wine while creating your own masterpiece! Professional artist will guide you step-by-step. No experience needed. All materials included. Perfect for a fun night out.",
            "location": "The Artisan Loft, Downtown",
            "category": "Wine Tasting",
            "start_time": frappe.utils.add_to_date(now, days=5, hours=19),
            "end_time": frappe.utils.add_to_date(now, days=5, hours=22),
            "max_attendees": 25,
        },
        {
            "title": "Weekend Hiking Adventure",
            "description": "Explore the scenic Ridgeback Trail. Moderate difficulty, about 8 km round trip. We'll stop at the summit for a picnic lunch. Good hiking shoes recommended.",
            "location": "Ridgeback Trailhead, Pine Hills",
            "category": "Hiking",
            "start_time": frappe.utils.add_to_date(now, days=7, hours=8),
            "end_time": frappe.utils.add_to_date(now, days=7, hours=14),
            "max_attendees": 20,
        },
        {
            "title": "Board Game Café Meetup",
            "description": "Join us for an afternoon of board games, coffee, and conversation. We have a huge library of games from Catan to Codenames. Bring your friends or come solo — we'll set up a game for you!",
            "location": "The Dice Cup Café",
            "category": "Board Games",
            "start_time": frappe.utils.add_to_date(now, days=10, hours=14),
            "end_time": frappe.utils.add_to_date(now, days=10, hours=18),
            "max_attendees": 40,
        },
        {
            "title": "Live Jazz Evening",
            "description": "An intimate evening of live jazz featuring the Blue Note Quartet. Enjoy craft cocktails and small plates in a cozy speakeasy atmosphere. Limited seating for an exclusive experience.",
            "location": "The Velvet Lounge",
            "category": "Live Music",
            "start_time": frappe.utils.add_to_date(now, days=14, hours=20),
            "end_time": frappe.utils.add_to_date(now, days=14, hours=23),
            "max_attendees": 50,
        },
        {
            "title": "Photography Walk: Old Town",
            "description": "Capture the charm of Old Town's historic architecture and hidden alleyways. Suitable for all skill levels. Bring any camera or phone. We'll share tips on composition and lighting along the way.",
            "location": "Meet at Old Town Square Fountain",
            "category": "Photography",
            "start_time": frappe.utils.add_to_date(now, days=17, hours=9),
            "end_time": frappe.utils.add_to_date(now, days=17, hours=12),
            "max_attendees": 15,
        },
        {
            "title": "Cooking Class: Italian Classics",
            "description": "Learn to make fresh pasta from scratch, classic marinara, and tiramisu. Hands-on class led by Chef Marco. Enjoy your creations with a glass of wine at the end. All ingredients provided.",
            "location": "La Cucina Cooking School",
            "category": "Cooking",
            "start_time": frappe.utils.add_to_date(now, days=21, hours=18),
            "end_time": frappe.utils.add_to_date(now, days=21, hours=21),
            "max_attendees": 16,
        },
        {
            "title": "Tech & Startups Networking Mixer",
            "description": "Connect with founders, developers, and investors over drinks and appetizers. Lightning talks from three local startup founders. Great for anyone in tech or looking to break in.",
            "location": "Innovation Hub, 4th Floor",
            "category": "Tech & Startups",
            "start_time": frappe.utils.add_to_date(now, days=28, hours=18),
            "end_time": frappe.utils.add_to_date(now, days=28, hours=21),
            "max_attendees": 100,
        },
    ]

    for ev in events:
        title = ev["title"]
        if not frappe.db.exists("VY Event", {"title": title}):
            doc = frappe.get_doc({
                "doctype": "VY Event",
                **ev,
                "created_by": "Administrator",
                "is_active": 1,
            })
            doc.insert(ignore_permissions=True)

    frappe.db.commit()
    print(f"Seeded {len(events)} events")


def seed_groups():
    """Create sample groups for discovery."""
    groups = [
        ("Weekend Hikers", "Explore scenic trails every Saturday morning. All fitness levels welcome!", "Hiking", "San Francisco, CA", 47),
        ("Photography Walks", "Monthly photowalks around the city. Bring your camera or phone!", "Photography", "Austin, TX", 31),
        ("Board Game Nights", "Weekly board game meetups at local cafes. From Catan to Codenames.", "Board Games", "New York, NY", 28),
        ("Book Lovers Club", "Read and discuss a new book every two weeks. Fiction and non-fiction.", "Reading", "Chicago, IL", 24),
        ("Running Crew", "Daily morning runs along the waterfront. All paces welcome.", "Running", "Seattle, WA", 52),
        ("Baking Enthusiasts", "Share recipes, tips, and taste-test each other's creations.", "Baking", "Portland, OR", 18),
        ("Rock Climbing Buddies", "Indoor bouldering and top-rope sessions for all skill levels.", "Rock Climbing", "Denver, CO", 35),
        ("Yoga in the Park", "Outdoor yoga every Sunday morning. Bring your own mat.", "Yoga & Meditation", "Los Angeles, CA", 41),
        ("Foodies Unite", "Try new restaurants, host potlucks, and share cooking adventures.", "Cooking", "Miami, FL", 38),
        ("Tech Talk", "Casual meetups about startups, coding, and the latest in tech.", "Tech & Startups", "San Francisco, CA", 56),
    ]

    created = 0
    for title, description, interest, location, member_count in groups:
        if not frappe.db.exists("VY Group", {"title": title}):
            doc = frappe.get_doc({
                "doctype": "VY Group",
                "title": title,
                "description": description,
                "category": interest,
                "location": location,
                "member_count": member_count,
                "is_active": 1,
            })
            doc.insert(ignore_permissions=True)
            created += 1

    frappe.db.commit()
    print(f"Seeded {created} groups")
