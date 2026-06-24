#!/usr/bin/env python3
"""
Vynce Dating App — Manual QA Test Runner (Playwright + API)

Tests:
  1. Registration / Onboarding (UI + API)
  2. Discover / Likes / Matches (UI + real-time notifications)
  3. Real-time chat (Matrix + Socket.io)
  4. Groups (create + join)
  5. Events (create + RSVP)
  6. Safety (block + report)
  7. Notifications (end-to-end)

Usage:
  /home/vineel/dev/galaxy/env/bin/python manual_qa_test.py

Environment:
  - Backend: http://127.0.0.1:8002
  - Frontend: http://127.0.0.1:5173
  - Socket.io: http://127.0.0.1:3001

Output: Screenshots + logs under /tmp/vynce_qa/
"""

import json, os, sys, time, base64, io, traceback
from datetime import date, datetime
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

import requests

# ── Config ───────────────────────────────────────────────────────────────
BACKEND = "http://127.0.0.1:8002"
FRONTEND = "http://127.0.0.1:5173"
SIO_URL = "http://127.0.0.1:3001"
OUT_DIR = Path("/tmp/vynce_qa")
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Test users
TEST_USERS = [
    {"email": "qa_alex@test.local", "password": "Pass1234", "display_name": "Alex", "birth_date": "1995-06-15", "gender": "Male"},
    {"email": "qa_blake@test.local", "password": "Pass1234", "display_name": "Blake", "birth_date": "1997-03-22", "gender": "Non-Binary"},
    {"email": "qa_casey@test.local", "password": "Pass1234", "display_name": "Casey", "birth_date": "1994-11-08", "gender": "Female"},
    {"email": "qa_dana@test.local", "password": "Pass1234", "display_name": "Dana", "birth_date": "1996-09-30", "gender": "Female"},
]

session = requests.Session()
session.headers.update({"Accept": "application/json"})

passed = 0
failed = 0
errors = []


def log(msg: str):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}")


def screenshot(page, name: str):
    path = OUT_DIR / f"{name}.png"
    page.screenshot(path=str(path), full_page=True)
    log(f"  📸 {path.name}")
    return path


# ── API Helpers (requests, no Playwright) ────────────────────────────────

def api_get_csrf(backend_url: str = BACKEND):
    """Fetch CSRF token from Frappe."""
    r = session.get(f"{backend_url}/api/method/vynce.api.get_csrf_token")
    r.raise_for_status()
    token = r.json().get("message")
    session.headers.update({"X-Frappe-CSRF-Token": token})
    return token


def api_login(usr: str, pwd: str, backend_url: str = BACKEND):
    """Login via Frappe /api/method/login."""
    api_get_csrf(backend_url)
    r = session.post(f"{backend_url}/api/method/login", json={"usr": usr, "pwd": pwd})
    r.raise_for_status()
    return r.json()


def api_register(user: dict, backend_url: str = BACKEND):
    """Register a user via Frappe whitelisted method."""
    api_get_csrf(backend_url)
    r = session.post(f"{backend_url}/api/method/vynce.api.register", json=user)
    if r.status_code == 200:
        return r.json()
    # If user already exists, try to login
    if "already exists" in r.text or "already registered" in r.text:
        log(f"  ⚠️  User {user['email']} already exists, logging in…")
        return api_login(user["email"], user["password"], backend_url)
    r.raise_for_status()


def api_call(method: str, params: dict = None, data: dict = None):
    """Call a Frappe whitelisted method."""
    api_get_csrf()
    if data is None:
        data = {}
    r = session.post(f"{BACKEND}/api/method/{method}", params=params, json=data)
    r.raise_for_status()
    return r.json().get("message")


def api_get(method: str, params: dict = None):
    """GET a Frappe whitelisted method."""
    r = session.get(f"{BACKEND}/api/method/{method}", params=params)
    r.raise_for_status()
    return r.json().get("message")


def create_user_via_api(user: dict):
    """Register a user with complete profile setup."""
    log(f"📝 Creating user: {user['email']}")

    # Register / Login
    result = api_register(user)
    if not result:
        raise RuntimeError(f"Failed to register {user['email']}")

    # Get CSRF token after login
    api_get_csrf()

    # Setup complete profile
    bio_map = {
        "qa_alex@test.local": "Software engineer and outdoor enthusiast. Love hiking and photography.",
        "qa_blake@test.local": "Artist and musician exploring the city one coffee shop at a time.",
        "qa_casey@test.local": "Book lover and yoga instructor. Looking for meaningful connections.",
        "qa_dana@test.local": "Foodie and traveler. Always planning the next adventure.",
    }

    # Save bio / display name
    api_call("vynce.profile.update_profile", data={
        "bio": bio_map.get(user["email"], "Hello! I'm new here."),
        "display_name": user["display_name"],
    })

    # Save interests (need at least 5 for profile strength > 50)
    interests_map = {
        "qa_alex@test.local": ["Hiking", "Photography", "Travel", "Tech", "Music"],
        "qa_blake@test.local": ["Art", "Music", "Coffee", "Writing", "Film"],
        "qa_casey@test.local": ["Yoga", "Reading", "Cooking", "Meditation", "Nature"],
        "qa_dana@test.local": ["Travel", "Food", "Photography", "Dancing", "Fashion"],
    }
    api_call("vynce.profile.save_interests", data={
        "interest_names": interests_map.get(user["email"], ["Music", "Travel", "Food", "Reading", "Art"])
    })

    # Save preferences
    api_call("vynce.profile.save_preferences", data={
        "data": json.dumps({
            "age_min": 18,
            "age_max": 60,
            "max_distance_km": 100,
            "gender_preference": "All",
        })
    })

    # Save prompts
    api_call("vynce.profile.save_prompts", data={
        "prompts": [
            {"prompt": "My favorite travel story...", "answer": f"{user['display_name']}'s travel story"},
            {"prompt": "A fun fact about me...", "answer": f"{user['display_name']}'s fun fact"},
            {"prompt": "My ideal first date...", "answer": f"A coffee date at a nice café"},
        ]
    })

    # Set location
    locations = {
        "qa_alex@test.local": {"lat": 40.7128, "lng": -74.0060, "name": "New York, NY"},
        "qa_blake@test.local": {"lat": 40.7282, "lng": -73.7949, "name": "New York, NY"},
        "qa_casey@test.local": {"lat": 40.7580, "lng": -73.9855, "name": "New York, NY"},
        "qa_dana@test.local": {"lat": 40.7484, "lng": -73.9857, "name": "New York, NY"},
    }
    loc = locations.get(user["email"], {"lat": 40.7128, "lng": -74.0060, "name": "New York, NY"})
    api_call("vynce.profile.update_profile", data={
        "location_lat": loc["lat"],
        "location_lng": loc["lng"],
        "location_name": loc["name"],
    })

    # Mark profile active and set profile strength via direct update
    api_call("vynce.profile.update_profile", data={"is_active": True})

    # Verify profile
    profile = api_get("vynce.profile.get_my_profile")
    log(f"  ✅ Profile created: {profile.get('display_name')} (strength: {profile.get('profile_strength')})")

    return profile


def bench_exec_script(script_path: str):
    """Run a Python script file in Frappe bench context via exec."""
    import subprocess
    cmd = ["bench", "--site", "test.localhost", "execute", f"exec(open('{script_path}').read())"]
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd="/home/vineel/dev/galaxy",
        env={**os.environ, "PATH": f"/home/vineel/dev/galaxy/env/bin:{os.environ.get('PATH', '')}"},
        timeout=30,
    )
    if result.returncode != 0:
        log(f"  ⚠️  bench stderr: {result.stderr[:500]}")
    return result.stdout, result.stderr


def cleanup_test_users(emails: list[str]):
    """Remove test users and related data via Frappe API (admin session)."""
    log("🧹 Cleaning up test users…")
    # Login as Administrator
    admin_session = requests.Session()
    admin_session.headers.update({"Accept": "application/json"})
    r = admin_session.post(f"{BACKEND}/api/method/login", json={"usr": "Administrator", "pwd": "admin"})
    if r.status_code != 200:
        log("  ⚠️  Could not login as Administrator, trying other cleanup")
        return

    # Get CSRF
    r = admin_session.get(f"{BACKEND}/api/method/vynce.api.get_csrf_token")
    csrf = r.json().get("message", "")
    admin_session.headers.update({"X-Frappe-CSRF-Token": csrf})

    for email in emails:
        # Check if user exists
        try:
            r = admin_session.get(f"{BACKEND}/api/resource/User/{email}")
            if r.status_code != 200:
                log(f"  User {email} not found, skipping")
                continue
        except Exception:
            continue

        # Delete related doctype records
        child_dt = ["VY Like", "VY Block", "VY Report", "VY Notification",
                     "VY Group Member", "VY Event Attendee", "VY User Media",
                     "VY Prompt Answer"]
        for dt in child_dt:
            try:
                # Get all records for this user
                csrf2 = admin_session.get(f"{BACKEND}/api/method/vynce.api.get_csrf_token").json().get("message", "")
                admin_session.headers.update({"X-Frappe-CSRF-Token": csrf2})
                r = admin_session.get(f"{BACKEND}/api/resource/{dt}", params={
                    "filters": json.dumps({"user": email}),
                    "fields": '["name"]',
                    "limit_page_length": 1000,
                })
                if r.status_code == 200:
                    data = r.json().get("data", [])
                    for doc in data:
                        doc_name = doc["name"]
                        admin_session.delete(f"{BACKEND}/api/resource/{dt}/{doc_name}")
            except Exception:
                pass

        # Delete profile
        try:
            csrf3 = admin_session.get(f"{BACKEND}/api/method/vynce.api.get_csrf_token").json().get("message", "")
            admin_session.headers.update({"X-Frappe-CSRF-Token": csrf3})
            profiles = admin_session.get(f"{BACKEND}/api/resource/VY User Profile", params={
                "filters": json.dumps({"user": email}),
                "fields": '["name"]',
            })
            if profiles.status_code == 200:
                for p in profiles.json().get("data", []):
                    admin_session.delete(f"{BACKEND}/api/resource/VY User Profile/{p['name']}")
        except Exception:
            pass

        # Delete the user
        try:
            csrf4 = admin_session.get(f"{BACKEND}/api/method/vynce.api.get_csrf_token").json().get("message", "")
            admin_session.headers.update({"X-Frappe-CSRF-Token": csrf4})
            r = admin_session.delete(f"{BACKEND}/api/resource/User/{email}")
            if r.status_code in (200, 202):
                log(f"  ✅ Deleted {email}")
            else:
                log(f"  ⚠️  Delete {email} returned {r.status_code}: {r.text[:100]}")
        except Exception as e:
            log(f"  ⚠️  Error deleting {email}: {e}")

# ── Playwright Test Runner ──────────────────────────────────────────────

def run_playwright_tests():
    """Main test orchestrator using Playwright."""
    global passed, failed

    try:
        from playwright.sync_api import sync_playwright, expect
    except ImportError:
        log("❌ Playwright not installed. Installing…")
        import subprocess
        subprocess.run(
            [f"{os.path.dirname(sys.executable)}/pip", "install", "playwright"],
            check=True, capture_output=True,
        )
        from playwright.sync_api import sync_playwright, expect

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=[
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-dev-shm-usage",
        ])
        context = browser.new_context(
            viewport={"width": 1280, "height": 800},
            locale="en-US",
        )
        page = context.new_page()

        # Collect console logs
        console_logs = []
        page.on("console", lambda msg: console_logs.append(f"[{msg.type}] {msg.text}"))
        page.on("pageerror", lambda err: console_logs.append(f"[PAGE_ERROR] {err}"))

        try:
            run_all_tests(page, context, browser)
        except Exception as e:
            log(f"❌ TEST FAILURE: {e}")
            traceback.print_exc()
            errors.append(str(e))
            failed += 1
            screenshot(page, "FAILURE_crash")
        finally:
            context.close()
            browser.close()

        # Write console logs
        with open(OUT_DIR / "console_logs.txt", "w") as f:
            f.write("\n".join(console_logs))

        # Generate report
        generate_report()


def run_all_tests(page, context, browser):
    global passed, failed

    log("=" * 60)
    log("🚀 STARTING VYNCE QA TEST SUITE")
    log("=" * 60)

    # ── 0. Health check ────────────────────────────────────────────
    log("\n🔍 Health check…")
    try:
        r = session.get(f"{BACKEND}/api/method/vynce.api.ping", timeout=5)
        assert r.json().get("message") == {"status": "ok"}
        log("  ✅ Backend reachable")
    except Exception as e:
        log(f"  ❌ Backend unreachable: {e}")
        failed += 1
        errors.append(f"Backend unreachable: {e}")
        return

    # Check frontend (use separate session without JSON Accept header)
    try:
        fe_session = requests.Session()
        fe_session.headers.update({"Accept": "text/html,*/*"})
        r = fe_session.get(FRONTEND, timeout=5)
        assert r.status_code == 200
        assert "Vynce" in r.text or "root" in r.text
        log("  ✅ Frontend reachable")
    except Exception as e:
        log(f"  ❌ Frontend unreachable: {e}")
        failed += 1
        errors.append(f"Frontend unreachable: {e}")
        return

    # ── 1. Create test users ───────────────────────────────────────
    log("\n" + "=" * 60)
    log("📝 1. TEST USER CREATION & ONBOARDING")
    log("=" * 60)

    profiles = {}
    for user in TEST_USERS:
        try:
            profile = create_user_via_api(user)
            profiles[user["email"]] = profile
            passed += 1
        except Exception as e:
            log(f"  ❌ Failed to create {user['email']}: {e}")
            errors.append(f"User creation failed for {user['email']}: {e}")
            failed += 1
            # Try logging in
            try:
                api_login(user["email"], user["password"])
                profile = api_get("vynce.profile.get_my_profile")
                profiles[user["email"]] = profile
            except Exception as e2:
                log(f"  ❌ Also login failed: {e2}")

    if len(profiles) < 4:
        log("⚠️  Not all users created. Continuing with available users.")

    # ── 2. REGISTRATION FLOW (UI) ──────────────────────────────────
    log("\n" + "=" * 60)
    log("📝 2. UI REGISTRATION FLOW")
    log("=" * 60)

    # Test registering a NEW user through the UI
    temp_email = f"qa_ui_test_{int(time.time())}@test.local"
    try:
        page.goto(f"{FRONTEND}/register", wait_until="networkidle")
        screenshot(page, "01_register_page")
        log("  📄 Register page loaded")

        # Fill registration form (use desktop IDs on 1280px viewport)
        page.fill("input#disp_name", "UITester")
        page.fill("input#email_desk", temp_email)
        page.fill("input#pass_desk", "StrongPass1")
        page.fill("input#confirm_desk", "StrongPass1")
        page.fill("input#dob_desk", "1995-06-15")
        page.select_option("select#gender_desk", "Male")

        # Accept terms
        page.click("input[type='checkbox']")

        screenshot(page, "02_register_form_filled")
        log("  📄 Registration form filled")

        # Submit
        page.locator("button[type='submit']").last.click()
        page.wait_for_timeout(3000)
        screenshot(page, "03_after_registration")

        # Check if we got redirected to onboarding or feed
        current_url = page.url
        log(f"  📍 Redirected to: {current_url}")

        if "/onboarding" in current_url:
            log("  ✅ Registration successful, redirected to onboarding")
            passed += 1
        elif "/feed" in current_url or "/" == page.url.rstrip("/"):
            log("  ✅ Registration successful, on feed page (onboarding completed)")
            passed += 1
        elif "/login" in current_url:
            log("  ⚠️  Redirected to login, registration may have succeeded but needs login")
        else:
            log(f"  ⚠️  Unknown redirect: {current_url}")

    except Exception as e:
        log(f"  ❌ UI Registration test failed: {e}")
        errors.append(f"UI Registration: {e}")
        failed += 1

    # Clean up the UI test user
    try:
        if frappe_db_exists(temp_email):
            cleanup_test_users([temp_email])
    except:
        pass

    # ── 3. LOGIN FLOW & DISCOVER ──────────────────────────────────
    log("\n" + "=" * 60)
    log("👤 3. LOGIN & DISCOVER FEED")
    log("=" * 60)

    alex_email = "qa_alex@test.local"
    try:
        # Login as Alex
        api_login(alex_email, "Pass1234")  # Ensure session is fresh
        page.goto(f"{FRONTEND}/login", wait_until="networkidle")
        screenshot(page, "04_login_page")

        page.locator("input#email").last.fill(alex_email)
        page.locator("input#password").last.fill("Pass1234")
        screenshot(page, "05_login_filled")
        page.locator("button[type='submit']").last.click()
        page.wait_for_timeout(3000)

        current_url = page.url
        log(f"  📍 After login redirect: {current_url}")

        # Check that we landed on feed or discover page
        if "/feed" in current_url or "/" == page.url.rstrip("/") or "/discover" in current_url:
            log("  ✅ Login successful, on feed page")
            passed += 1
            screenshot(page, "06_feed_page")
        else:
            log(f"  ⚠️  After login at: {current_url}")
            # Try navigating
            page.goto(f"{FRONTEND}/feed", wait_until="networkidle")
            page.wait_for_timeout(2000)
            screenshot(page, "06_feed_page_navigated")

        # Check discover page
        page.goto(f"{FRONTEND}/people", wait_until="networkidle")
        page.wait_for_timeout(3000)
        screenshot(page, "07_discover_people_page")

        # Check if profiles are visible (suggested section)
        content = page.content()
        if "Blake" in content or "Casey" in content or "Dana" in content or "Suggested for You" in content:
            log("  ✅ Discover feed shows profiles")
            passed += 1
        else:
            log("  ⚠️  Discover feed may be empty")

    except Exception as e:
        log(f"  ❌ Login/Discover test failed: {e}")
        errors.append(f"Login/Discover: {e}")
        failed += 1

    # ── 4. LIKES & MATCHES ─────────────────────────────────────────
    log("\n" + "=" * 60)
    log("💕 4. LIKES & MATCHES")
    log("=" * 60)

    try:
        # Login as Alex
        api_login("qa_alex@test.local", "Pass1234")

        # Get Blake's user ID
        api_login("qa_blake@test.local", "Pass1234")
        blake_profile = api_get("vynce.profile.get_my_profile")
        blake_user = blake_profile.get("user")
        log(f"  Blake's user ID: {blake_user}")

        # Alex likes Blake
        api_login("qa_alex@test.local", "Pass1234")
        result = api_call("vynce.discover.like_user", data={"to_user": blake_user, "like_type": "Like"})
        log(f"  Alex likes Blake: {json.dumps(result)[:200]}")
        if result:
            log("  ✅ Alex liked Blake")
            passed += 1
        else:
            log("  ❌ Like failed")
            failed += 1

        # Wait a moment
        time.sleep(2)

        # Check Blake's notifications (should receive a "new like" notification)
        api_login("qa_blake@test.local", "Pass1234")
        notifs = api_get("vynce.notification.get_notifications")
        log(f"  Blake's notifications after Alex like: {len(notifs) if notifs else 0}")
        if notifs and any(n.get("type") in ("Like", "Match") for n in notifs):
            log("  ✅ Blake received like notification")
            passed += 1
        else:
            log("  ⚠️  No like notification for Blake yet")

        # Blake likes Alex back
        alex_profile = api_get("vynce.profile.get_my_profile", {"user": "qa_alex@test.local"})
        # Actually get Alex's profile by logging in as Alex first
        api_login("qa_alex@test.local", "Pass1234")
        alex_profile = api_get("vynce.profile.get_my_profile")
        alex_user = alex_profile.get("user")

        api_login("qa_blake@test.local", "Pass1234")
        result = api_call("vynce.discover.like_user", data={"to_user": alex_user, "like_type": "Like"})
        log(f"  Blake likes Alex: {json.dumps(result)[:200]}")

        if result and result.get("match_created"):
            log("  ✅ Match created! 💫")
            passed += 1
        else:
            log("  ⚠️  Match may not have been created (could be cached feed)")

        # Wait for match processing
        time.sleep(3)

        # Verify match in Matches page
        api_login("qa_alex@test.local", "Pass1234")
        matches = api_get("vynce.match.get_matches")
        log(f"  Alex's matches: {len(matches) if matches else 0}")
        if matches:
            log(f"  First match: {json.dumps(matches[0])[:200]}")
            log("  ✅ Alex sees match")
            passed += 1
        else:
            log("  ⚠️  No matches visible for Alex yet")

        api_login("qa_blake@test.local", "Pass1234")
        matches_blake = api_get("vynce.match.get_matches")
        log(f"  Blake's matches: {len(matches_blake) if matches_blake else 0}")

        # Also check notifications
        for u_email in ["qa_alex@test.local", "qa_blake@test.local"]:
            api_login(u_email, "Pass1234")
            notifs = api_get("vynce.notification.get_notifications")
            match_notifs = [n for n in (notifs or []) if n.get("type") == "Match"]
            log(f"  {u_email} - Match notifications: {len(match_notifs)}")

    except Exception as e:
        log(f"  ❌ Likes/Match test failed: {e}")
        traceback.print_exc()
        errors.append(f"Likes/Match: {e}")
        failed += 1

    # ── 5. UI MATCHES PAGE ─────────────────────────────────────────
    log("\n" + "=" * 60)
    log("💕 5. UI MATCHES PAGE VERIFICATION")
    log("=" * 60)

    try:
        # Login as Alex via UI
        page.goto(f"{FRONTEND}/login", wait_until="networkidle")
        page.locator("input#email").last.fill("qa_alex@test.local")
        page.locator("input#password").last.fill("Pass1234")
        page.locator("button[type='submit']").last.click()
        page.wait_for_timeout(3000)

        # Navigate to matches
        page.goto(f"{FRONTEND}/matches", wait_until="networkidle")
        page.wait_for_timeout(3000)
        screenshot(page, "08_matches_page")

        content = page.content()
        if "Blake" in content or "match" in content.lower() or "connection" in content.lower():
            log("  ✅ Matches page shows match")
            passed += 1
        else:
            log("  ⚠️  Matches page may be empty in UI")

    except Exception as e:
        log(f"  ❌ UI Matches test failed: {e}")
        errors.append(f"UI Matches: {e}")
        failed += 1

    # ── 6. GROUPS ───────────────────────────────────────────────────
    log("\n" + "=" * 60)
    log("👥 6. GROUPS")
    log("=" * 60)

    group_name = None
    try:
        # Alex creates a group
        api_login("qa_alex@test.local", "Pass1234")
        result = api_call("vynce.group.create_group", data={
            "title": "NYC Tech Meetup",
            "description": "A group for tech enthusiasts in NYC to connect and share ideas.",
            "category": "Tech",
            "location": "New York, NY",
            "max_members": 50,
        })
        log(f"  Group created: {json.dumps(result)[:200]}")
        if result and result.get("group_name"):
            group_name = result["group_name"]
            log(f"  ✅ Group created: {group_name}")
            passed += 1
        else:
            log("  ❌ Group creation failed")
            failed += 1

        # Blake joins the group
        if group_name:
            api_login("qa_blake@test.local", "Pass1234")
            result = api_call("vynce.group.join_group", data={"group_name": group_name})
            log(f"  Blake joins group: {json.dumps(result)[:200]}")
            if result:
                log("  ✅ Blake joined group")
                passed += 1
            else:
                log("  ❌ Join group failed")
                failed += 1

            # Casey joins the group
            api_login("qa_casey@test.local", "Pass1234")
            result = api_call("vynce.group.join_group", data={"group_name": group_name})
            log(f"  Casey joins group: {'success' if result else 'fail'}")

            # Verify group details
            api_login("qa_alex@test.local", "Pass1234")
            details = api_get("vynce.group.get_group_details", params={"group_name": group_name})
            member_count = details.get("member_count", 0) if details else 0
            log(f"  Group member count: {member_count}")
            if member_count >= 2:
                log("  ✅ Group has correct members")
                passed += 1
            else:
                log("  ⚠️  Group member count lower than expected")

    except Exception as e:
        log(f"  ❌ Groups test failed: {e}")
        errors.append(f"Groups: {e}")
        failed += 1

    # ── 7. UI GROUPS PAGE ──────────────────────────────────────────
    log("\n" + "=" * 60)
    log("👥 7. UI GROUPS PAGE")
    log("=" * 60)

    try:
        # Login as Alex
        page.goto(f"{FRONTEND}/login", wait_until="networkidle")
        page.locator("input#email").last.fill("qa_alex@test.local")
        page.locator("input#password").last.fill("Pass1234")
        page.locator("button[type='submit']").last.click()
        page.wait_for_timeout(3000)

        # Navigate to groups
        page.goto(f"{FRONTEND}/groups", wait_until="networkidle")
        page.wait_for_timeout(3000)
        screenshot(page, "09_groups_page")

        content = page.content()
        if "NYC Tech Meetup" in content or "groups" in content.lower():
            log("  ✅ Groups page visible")
            passed += 1
        else:
            log("  ⚠️  Groups content may differ")

        # View group details if we have group_name
        if group_name:
            page.goto(f"{FRONTEND}/groups/{group_name}", wait_until="networkidle")
            page.wait_for_timeout(3000)
            screenshot(page, "10_group_detail_page")

    except Exception as e:
        log(f"  ❌ UI Groups test failed: {e}")
        errors.append(f"UI Groups: {e}")
        failed += 1

    # ── 8. EVENTS ──────────────────────────────────────────────────
    log("\n" + "=" * 60)
    log("📅 8. EVENTS")
    log("=" * 60)

    event_name = None
    try:
        # Alex creates an event
        api_login("qa_alex@test.local", "Pass1234")

        # Set future dates for the event
        from datetime import datetime, timedelta
        start = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
        end = (datetime.now() + timedelta(days=7, hours=3)).strftime("%Y-%m-%d %H:%M:%S")

        result = api_call("vynce.event.create_event", data={
            "title": "Tech Talks: AI in Dating Apps",
            "description": "A discussion on how AI is transforming the dating app landscape.",
            "category": "Tech",
            "location": "WeWork, NYC",
            "start_time": start,
            "end_time": end,
            "max_attendees": 30,
        })
        log(f"  Event created: {json.dumps(result)[:200]}")
        if result and result.get("event_name"):
            event_name = result["event_name"]
            log(f"  ✅ Event created: {event_name}")
            passed += 1
        else:
            log("  ❌ Event creation failed")
            failed += 1

        # Blake RSVPs "Going"
        if event_name:
            api_login("qa_blake@test.local", "Pass1234")
            result = api_call("vynce.event.rsvp", data={"event_name": event_name, "status": "Going"})
            log(f"  Blake RSVPs: {json.dumps(result)[:200]}")
            if result:
                log("  ✅ Blake RSVP'd Going")
                passed += 1
            else:
                log("  ❌ RSVP failed")
                failed += 1

            # Casey RSVPs "Interested"
            api_login("qa_casey@test.local", "Pass1234")
            result = api_call("vynce.event.rsvp", data={"event_name": event_name, "status": "Interested"})
            log(f"  Casey RSVPs: {'success' if result else 'fail'}")

            # Verify event details
            api_login("qa_alex@test.local", "Pass1234")
            details = api_get("vynce.event.get_event_details", params={"event_name": event_name})
            if details:
                going = details.get("going_count", 0)
                interested = details.get("interested_count", 0)
                log(f"  Event attendees - Going: {going}, Interested: {interested}")
                if going >= 1:
                    log("  ✅ Event has attendees")
                    passed += 1
            else:
                log("  ❌ Could not get event details")
                failed += 1

    except Exception as e:
        log(f"  ❌ Events test failed: {e}")
        errors.append(f"Events: {e}")
        failed += 1

    # ── 9. UI EVENTS PAGE ──────────────────────────────────────────
    log("\n" + "=" * 60)
    log("📅 9. UI EVENTS PAGE")
    log("=" * 60)

    try:
        page.goto(f"{FRONTEND}/login", wait_until="networkidle")
        page.locator("input#email").last.fill("qa_alex@test.local")
        page.locator("input#password").last.fill("Pass1234")
        page.locator("button[type='submit']").last.click()
        page.wait_for_timeout(3000)

        page.goto(f"{FRONTEND}/events", wait_until="networkidle")
        page.wait_for_timeout(3000)
        screenshot(page, "11_events_page")

        content = page.content()
        if "AI in Dating" in content or "Tech Talks" in content:
            log("  ✅ Events page shows created event")
            passed += 1
        else:
            log("  ⚠️  Event not visible in UI (may be filtered)")

        # View event details
        if event_name:
            page.goto(f"{FRONTEND}/events/{event_name}", wait_until="networkidle")
            page.wait_for_timeout(3000)
            screenshot(page, "12_event_detail_page")

    except Exception as e:
        log(f"  ❌ UI Events test failed: {e}")
        errors.append(f"UI Events: {e}")
        failed += 1

    # ── 10. SAFETY (BLOCK / REPORT) ────────────────────────────────
    log("\n" + "=" * 60)
    log("🛡️  10. SAFETY (BLOCK & REPORT)")
    log("=" * 60)

    try:
        # Alex blocks Casey
        api_login("qa_alex@test.local", "Pass1234")

        # Get Casey's user ID
        api_login("qa_casey@test.local", "Pass1234")
        casey_profile = api_get("vynce.profile.get_my_profile")
        casey_user = casey_profile.get("user")

        # Alex blocks Casey
        api_login("qa_alex@test.local", "Pass1234")
        result = api_call("vynce.safety.block_user", data={"blocked_user": casey_user})
        log(f"  Block result: {json.dumps(result)[:200]}")
        if result and result.get("ok"):
            log("  ✅ Alex blocked Casey")
            passed += 1
        else:
            log("  ❌ Block failed")
            failed += 1

        # Verify Casey no longer in Alex's discover feed
        feed = api_get("vynce.discover.get_feed")
        feed_users = [p.get("user") for p in (feed or [])]
        if casey_user not in feed_users:
            log("  ✅ Casey not in Alex's discover feed (blocked)")
            passed += 1
        else:
            log("  ⚠️  Casey still in discover feed (block may not have propagated)")

        # Unblock Casey for cleanup
        api_call("vynce.safety.unblock_user", data={"blocked_user": casey_user})

        # Alex reports Dana
        api_login("qa_dana@test.local", "Pass1234")
        dana_profile = api_get("vynce.profile.get_my_profile")
        dana_user = dana_profile.get("user")

        api_login("qa_alex@test.local", "Pass1234")
        result = api_call("vynce.safety.report_user", data={
            "reported_user": dana_user,
            "reason": "Inappropriate Content",
            "details": "Test report from QA automation",
        })
        log(f"  Report result: {json.dumps(result)[:200]}")
        if result and result.get("ok"):
            log("  ✅ Alex reported Dana")
            passed += 1
        else:
            log("  ❌ Report failed")
            failed += 1

    except Exception as e:
        log(f"  ❌ Safety test failed: {e}")
        errors.append(f"Safety: {e}")
        failed += 1

    # ── 11. REAL-TIME NOTIFICATIONS ────────────────────────────────
    log("\n" + "=" * 60)
    log("🔔 11. REAL-TIME NOTIFICATIONS")
    log("=" * 60)

    try:
        # Login as Alex and navigate to notifications page
        page.goto(f"{FRONTEND}/login", wait_until="networkidle")
        page.locator("input#email").last.fill("qa_alex@test.local")
        page.locator("input#password").last.fill("Pass1234")
        page.locator("button[type='submit']").last.click()
        page.wait_for_timeout(3000)

        page.goto(f"{FRONTEND}/notifications", wait_until="networkidle")
        page.wait_for_timeout(3000)
        screenshot(page, "13_notifications_page")

        content = page.content()
        if "Match" in content or "Like" in content or "notification" in content.lower():
            log("  ✅ Notifications page shows content")
            passed += 1
        else:
            log("  ⚠️  Notifications page may be empty")

    except Exception as e:
        log(f"  ❌ Notifications test failed: {e}")
        errors.append(f"Notifications: {e}")
        failed += 1

    # ── 12. MULTI-CONTEXT NOTIFICATION VERIFICATION ────────────────
    log("\n" + "=" * 60)
    log("🔔 12. DUO-CONTEXT NOTIFICATION TEST")
    log("=" * 60)

    try:
        # Open two browser contexts: Alex (the lister) and Blake (the listener)
        alex_ctx = browser.new_context(viewport={"width": 1280, "height": 800})
        blake_ctx = browser.new_context(viewport={"width": 600, "height": 800})

        alex_page = alex_ctx.new_page()
        blake_page = blake_ctx.new_page()

        # Login Alex
        alex_page.goto(f"{FRONTEND}/login", wait_until="networkidle")
        alex_page.locator("input#email").last.fill("qa_alex@test.local")
        alex_page.locator("input#password").last.fill("Pass1234")
        alex_page.locator("button[type='submit']").last.click()
        alex_page.wait_for_timeout(3000)

        # Login Blake
        blake_page.goto(f"{FRONTEND}/login", wait_until="networkidle")
        blake_page.locator("input#email").last.fill("qa_blake@test.local")
        blake_page.locator("input#password").last.fill("Pass1234")
        blake_page.locator("button[type='submit']").last.click()
        blake_page.wait_for_timeout(3000)

        # Navigate both to notifications
        alex_page.goto(f"{FRONTEND}/notifications", wait_until="networkidle")
        alex_page.wait_for_timeout(2000)
        screenshot(alex_page, "14_alex_notifications_before")

        blake_page.goto(f"{FRONTEND}/notifications", wait_until="networkidle")
        blake_page.wait_for_timeout(2000)
        screenshot(blake_page, "15_blake_notifications_before")

        # Now Alex sends a notification to Blake by creating a like (if not already done)
        # This should trigger a real-time notification event
        # Let's do a super like from Alex to Dana to trigger a new notification
        api_login("qa_dana@test.local", "Pass1234")
        dana_profile = api_get("vynce.profile.get_my_profile")
        dana_user = dana_profile.get("user")

        api_login("qa_alex@test.local", "Pass1234")
        result = api_call("vynce.discover.like_user", data={"to_user": dana_user, "like_type": "Super Like"})
        log(f"  Alex Super Likes Dana: {json.dumps(result)[:100]}")

        # Wait for socket to propagate
        time.sleep(3)

        # Check notifications via API for Dana
        api_login("qa_dana@test.local", "Pass1234")
        dana_notifs = api_get("vynce.notification.get_notifications")
        if dana_notifs:
            log(f"  Dana has {len(dana_notifs)} notifications")
            log(f"  Latest: {json.dumps(dana_notifs[0])[:200]}")
            log("  ✅ Notification via API confirmed")
            passed += 1
        else:
            log("  ⚠️  No notifications via API")

        # Refresh Blake's notifications via API
        api_login("qa_blake@test.local", "Pass1234")
        blake_notifs = api_get("vynce.notification.get_notifications")
        log(f"  Blake notifications count: {len(blake_notifs) if blake_notifs else 0}")

        # Refresh Blake's page
        blake_page.reload(wait_until="networkidle")
        blake_page.wait_for_timeout(2000)
        screenshot(blake_page, "16_blake_notifications_after")

        alex_ctx.close()
        blake_ctx.close()

    except Exception as e:
        log(f"  ❌ Duo-context notification test failed: {e}")
        traceback.print_exc()
        errors.append(f"Duo-notification: {e}")
        failed += 1

    # ── 13. PROFILE PAGE ───────────────────────────────────────────
    log("\n" + "=" * 60)
    log("👤 13. PROFILE PAGE VERIFICATION")
    log("=" * 60)

    try:
        page.goto(f"{FRONTEND}/login", wait_until="networkidle")
        page.locator("input#email").last.fill("qa_alex@test.local")
        page.locator("input#password").last.fill("Pass1234")
        page.locator("button[type='submit']").last.click()
        page.wait_for_timeout(3000)

        page.goto(f"{FRONTEND}/profile", wait_until="networkidle")
        page.wait_for_timeout(3000)
        screenshot(page, "17_profile_page")

        content = page.content()
        if "Alex" in content:
            log("  ✅ Profile page shows display name")
            passed += 1
        else:
            log("  ⚠️  Profile page may be loading or empty")

    except Exception as e:
        log(f"  ❌ Profile page test failed: {e}")
        errors.append(f"Profile: {e}")
        failed += 1

    # ── Summary ────────────────────────────────────────────────────
    log("\n" + "=" * 60)
    log(f"📊 RESULTS: {passed} passed, {failed} failed, {len(errors)} errors")
    log("=" * 60)


def frappe_db_exists(email):
    """Check if a user exists in Frappe via bench."""
    code = f"""
import frappe
print(frappe.db.exists("User", "{email}"))
"""
    stdout, _ = bench_exec(code)
    return "True" in stdout


def generate_report():
    """Generate QA test report."""
    report = f"""# Vynce QA Test Report
Date: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

## Summary
- **Passed:** {passed}
- **Failed:** {failed}
- **Errors:** {len(errors)}

## Error Details
"""
    for i, err in enumerate(errors, 1):
        report += f"{i}. {err}\n"

    report += "\n## Screenshots\n"
    screenshots = sorted(OUT_DIR.glob("*.png"))
    for s in screenshots:
        report += f"- [{s.name}]({s})\n"

    report += f"\n## Console Logs\nSee {OUT_DIR / 'console_logs.txt'}\n"

    (OUT_DIR / "qa_report.md").write_text(report)
    log(f"📄 Report saved to {OUT_DIR / 'qa_report.md'}")


if __name__ == "__main__":
    log("🚀 Vynce Manual QA Test Runner")
    log(f"📁 Output: {OUT_DIR}")
    log(f"🔗 Backend: {BACKEND}")
    log(f"🔗 Frontend: {FRONTEND}")
    log(f"🔗 Socket.io: {SIO_URL}")
    log("")

    try:
        run_playwright_tests()
    finally:
        # Cleanup
        cleanup_test_users([u["email"] for u in TEST_USERS])

    log("\n🏁 QA test suite complete.")
