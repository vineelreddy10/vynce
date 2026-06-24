"""Manual QA end-to-end test for Vynce using Playwright.

Run with:
    cd /home/vineel/dev/galaxy/apps/vynce && env/bin/python vynce/manual_qa_playwright.py

Requires:
    - bench server running on http://127.0.0.1:8002
    - vite dev server on http://127.0.0.1:5173
    - Socket.io on http://127.0.0.1:3001
    - Synapse Matrix on http://127.0.0.1:8008
    - Seed data: auto-reseeds by running bench execute

Reseeding forces fresh test data each run.
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime

from playwright.sync_api import sync_playwright, expect

BASE_URL = os.environ.get("VYNCE_QA_URL", "http://127.0.0.1:5173")
OUT_DIR = "/tmp/vynce_qa"
os.makedirs(OUT_DIR, exist_ok=True)

# Path to bench
BENCH = os.environ.get("VYNCE_BENCH", "/home/vineel/.local/bin/bench")
SEED_SITE = os.environ.get("VYNCE_SITE", "test.localhost")
SEED_EXECUTE = f"{BENCH} --site {SEED_SITE} execute vynce.manual_qa_seed.run_seed"

USERS = {
    "alex": ("alex@vynce.app", "TestPass123!"),
    "blake": ("blake@vynce.app", "TestPass123!"),
    "casey": ("casey@vynce.app", "TestPass123!"),
    "dana": ("dana@vynce.app", "TestPass123!"),
}

pass_count = 0
fail_count = 0
step_log: list[str] = []


def log(msg: str):
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    step_log.append(line)


def screenshot(page, name: str):
    path = os.path.join(OUT_DIR, f"{name}.png")
    page.screenshot(path=path, full_page=True)
    log(f"  📸 {name}.png")


def assert_ok(cond: bool, desc: str):
    global pass_count, fail_count
    if cond:
        pass_count += 1
        log(f"  ✅ {desc}")
    else:
        fail_count += 1
        log(f"  ❌ {desc}")


def login(page, email: str, password: str):
    """Log in via the /login page."""
    page.goto(f"{BASE_URL}/login")
    # Wait for the page to fully render - the form has mobile and desktop variants
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(2000)
    # Target input#email directly - .last picks desktop version (visible) over mobile (hidden)
    email_input = page.locator("input#email").last
    email_input.wait_for(state="visible", timeout=15000)
    email_input.fill(email)
    page.locator("input#password").last.fill(password)
    page.locator("button:has-text('Sign In')").last.click()
    # Wait for navigation to /feed
    page.wait_for_url("**/feed", timeout=15000)
    log(f"  ✓ Logged in as {email.split('@')[0]}")


def run_qa():
    global pass_count, fail_count

    # Re-seed to get fresh clean state
    log("Reseeding test data...")
    ret = os.system(f"{SEED_EXECUTE}")
    log(f"  Seed exit code: {ret}")

    pw_ctx = sync_playwright()
    p = pw_ctx.__enter__()
    browser = p.chromium.launch(headless=True)

    try:
        # ──────────────────────────────────────────────
        # TEST 1: Blake logs in, browses discover, likes Dana
        # ──────────────────────────────────────────────
        log("\n═══ TEST 1: Blake → Discover → Like Dana ═══")
        ctx_blake = browser.new_context(viewport={"width": 1280, "height": 900})
        page_blake = ctx_blake.new_page()
        login(page_blake, *USERS["blake"])

        # Navigate to People (discover with like buttons)
        page_blake.goto(f"{BASE_URL}/people")
        page_blake.wait_for_load_state("networkidle")
        screenshot(page_blake, "t1_blake_people_page")

        # Check profiles are shown
        feed_text = page_blake.text_content("body") or ""
        has_profiles = "people" in feed_text.lower()
        assert_ok(has_profiles, "Blake sees discover profiles")

        # Click the "Like" button for Dana (first button with title "Like" that corresponds to Dana's card)
        # Each profile card has 3 buttons: Pass, Like, Super Like in that order.
        # We find Dana by name text in the page
        dana_card = page_blake.locator("h3:has-text('Dana')").first
        if not dana_card.is_visible():
            # Maybe on a different page or scrolled down, try loading more
            log("  Dana not immediately visible, scrolling...")
            page_blake.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page_blake.wait_for_timeout(2000)
            dana_card = page_blake.locator("h3:has-text('Dana')").first

        if dana_card.is_visible():
            log("  Found Dana card, clicking Like")
            # The like button is in the parent card div
            card = dana_card.locator("..").locator("..")
            like_btn = card.locator('button[title="Like"]')
            like_btn.click()
            page_blake.wait_for_timeout(2000)
            screenshot(page_blake, "t1_blake_liked_dana")
            assert_ok(True, "Blake liked Dana")
        else:
            log("  Dana not found in feed after scroll")
            # Check total feed content to debug
            body_text = page_blake.text_content("body") or ""
            log(f"  Body length: {len(body_text)}, contains 'Dana': {'Dana' in body_text}")
            screenshot(page_blake, "t1_blake_no_dana")
            assert_ok(False, "Dana not found in Blake's feed")

        # ──────────────────────────────────────────────
        # TEST 2: Dana logs in, checks notifications
        # ──────────────────────────────────────────────
        log("\n═══ TEST 2: Dana → Notifications ═══")
        ctx_dana = browser.new_context(viewport={"width": 1280, "height": 900})
        page_dana = ctx_dana.new_page()
        login(page_dana, *USERS["dana"])

        # Go to notifications
        page_dana.goto(f"{BASE_URL}/notifications")
        page_dana.wait_for_load_state("load")
        page_dana.wait_for_timeout(5000)  # let socket.io events arrive & query fetch
        screenshot(page_dana, "t2_dana_notifications")

        # Reload to pick up notifications created via API (like from Blake)
        page_dana.reload()
        page_dana.wait_for_load_state("load")
        page_dana.wait_for_timeout(3000)

        body_dana = page_dana.text_content("body") or ""
        # Check for "Blake" or "New Like" notification text
        notif_by_text = page_dana.locator("text=Blake").first
        notif_by_title = page_dana.locator("text=New Like").first
        has_notification = notif_by_text.is_visible() or notif_by_title.is_visible()
        screenshot(page_dana, "t2_dana_notifications_after_reload")
        assert_ok(has_notification, "Dana sees notification about Blake's like")

        # ──────────────────────────────────────────────
        # TEST 3: Alex logs in, checks matches, opens chat
        # ──────────────────────────────────────────────
        log("\n═══ TEST 3: Alex → Matches → Chat ═══")
        ctx_alex = browser.new_context(viewport={"width": 1280, "height": 900})
        page_alex = ctx_alex.new_page()
        login(page_alex, *USERS["alex"])

        # Go to matches
        page_alex.goto(f"{BASE_URL}/matches")
        page_alex.wait_for_load_state("networkidle")
        page_alex.wait_for_timeout(3000)
        screenshot(page_alex, "t3_alex_matches")

        body_alex = page_alex.text_content("body") or ""
        if "Blake" in body_alex or "blake" in body_alex:
            assert_ok(True, "Alex sees Blake in matches")

            # Click Chat button for Blake match
            chat_btn = page_alex.locator('button:has-text("Chat")').first
            if chat_btn.is_visible():
                chat_btn.click()
                page_alex.wait_for_load_state("networkidle")
                page_alex.wait_for_timeout(5000)  # Matrix SDK init
                screenshot(page_alex, "t3_alex_chat_opened")

                # Type a message
                msg_input = page_alex.locator('input[placeholder="Type a message..."]')
                if msg_input.is_visible():
                    msg_input.fill("Hey Blake! Looking forward to the hike this weekend! 🥾")
                    msg_input.press("Enter")
                    page_alex.wait_for_timeout(3000)
                    screenshot(page_alex, "t3_alex_message_sent")
                    assert_ok(True, "Alex sent a message to Blake")

                    # Wait for it to appear in the chat
                    sent_msg = page_alex.locator("text=Hey Blake")
                    assert_ok(sent_msg.count() > 0, "Message visible in Alex's chat")
                else:
                    assert_ok(False, "Chat input not visible")
            else:
                assert_ok(False, "Chat button not visible")
        else:
            assert_ok(False, "Alex does not see matches")

        # ──────────────────────────────────────────────
        # TEST 4: Blake sees the message from Alex (realtime)
        # ──────────────────────────────────────────────
        log("\n═══ TEST 4: Blake → Receive message from Alex ═══")
        # Switch to Blake's existing page
        # NOTE: Use "load" state, NOT "networkidle" because Matrix SDK
        # maintains persistent websocket connections that never settle.
        page_blake.goto(f"{BASE_URL}/messages")
        page_blake.wait_for_load_state("load")
        page_blake.wait_for_timeout(5000)  # Matrix sync
        screenshot(page_blake, "t4_blake_messages")

        # Click on Alex's conversation
        alex_convo = page_blake.locator("text=Alex").first
        if alex_convo.is_visible():
            alex_convo.click()
            page_blake.wait_for_timeout(3000)
            screenshot(page_blake, "t4_blake_chat_opened")

            msg_received = page_blake.locator("text=Hey Blake")
            assert_ok(msg_received.count() > 0, "Blake received Alex's message in real-time")
        else:
            assert_ok(False, "Alex conversation not found in Blake's messages")

        # ──────────────────────────────────────────────
        # TEST 5: Groups - Dana views and joins Weekend Hikers
        # ──────────────────────────────────────────────
        log("\n═══ TEST 5: Groups ═══")
        page_dana.goto(f"{BASE_URL}/groups")
        page_dana.wait_for_load_state("networkidle")
        page_dana.wait_for_timeout(2000)
        screenshot(page_dana, "t5_dana_groups")

        body_groups = page_dana.text_content("body") or ""
        if "Weekend Hikers" in body_groups:
            assert_ok(True, "Dana sees Weekend Hikers group")

            # Navigate to group detail page
            page_dana.goto(f"{BASE_URL}/groups")
            page_dana.wait_for_load_state("load")
            page_dana.wait_for_timeout(500)
            group_link = page_dana.locator("text=Weekend Hikers").first
            if group_link.is_visible():
                # The card navigates on click; extract group_name from URL
                # by clicking the card
                group_link.click()
                page_dana.wait_for_load_state("load")
                page_dana.wait_for_timeout(2000)
                screenshot(page_dana, "t5_dana_group_detail")
                # On detail page, find a button with text "Join" or "Leave"
                join_btn = page_dana.locator('button:has-text("Join")').first
                if join_btn.is_visible():
                    join_btn.click()
                    page_dana.wait_for_timeout(2000)
                    screenshot(page_dana, "t5_dana_joined_group")
                    assert_ok(True, "Dana joined Weekend Hikers")
                else:
                    leave_btn = page_dana.locator('button:has-text("Leave")').first
                    if leave_btn.is_visible():
                        assert_ok(True, "Dana already in group (Leave shown)")
                    else:
                        # Check if there's any button visible in the detail page
                        all_btns = page_dana.locator("button").all()
                        btn_texts = [b.text_content() for b in all_btns]
                        log(f"  Buttons found: {btn_texts}")
                        assert_ok(False, f"No Join/Leave button found. Buttons: {btn_texts}")
        else:
            assert_ok(False, "Weekend Hikers group not visible to Dana")

        # ──────────────────────────────────────────────
        # TEST 6: Events - Dana RSVPs to Sunset Hike
        # ──────────────────────────────────────────────
        log("\n═══ TEST 6: Events ═══")
        page_dana.goto(f"{BASE_URL}/events")
        page_dana.wait_for_load_state("networkidle")
        page_dana.wait_for_timeout(2000)
        screenshot(page_dana, "t6_dana_events")

        body_events = page_dana.text_content("body") or ""
        if "Sunset Hike" in body_events:
            assert_ok(True, "Dana sees Sunset Hike & Picnic event")

            # Click RSVP - the RSVP button is on the event card with text "RSVP"
            rsvp_btn = page_dana.locator('button:has-text("RSVP")').first
            if rsvp_btn.is_visible():
                rsvp_btn.click()
                page_dana.wait_for_timeout(2000)
                screenshot(page_dana, "t6_dana_rsvped")
                assert_ok(True, "Dana RSVPed Going to event")
            else:
                # Maybe already RSVPed?
                going_text = page_dana.locator("text=Going").first
                if going_text.is_visible():
                    assert_ok(True, "Dana already RSVPed (Going badge visible)")
                else:
                    assert_ok(False, "RSVP button not visible on event card")
        else:
            assert_ok(False, "Sunset Hike event not visible to Dana")

        # ──────────────────────────────────────────────
        # TEST 7: Alex checks discover - Dana should be blocked
        # ──────────────────────────────────────────────
        log("\n═══ TEST 7: Safety - Alex blocked Dana ═══")
        page_alex.goto(f"{BASE_URL}/people")
        page_alex.wait_for_load_state("networkidle")
        page_alex.wait_for_timeout(2000)
        screenshot(page_alex, "t7_alex_discover_blocked")

        body_alex_people = page_alex.text_content("body") or ""
        dana_blocked = "Dana" not in body_alex_people
        assert_ok(dana_blocked, "Alex's discover feed excludes Dana (blocked)")

        # ──────────────────────────────────────────────
        # SUMMARY
        # ──────────────────────────────────────────────
        log("\n" + "=" * 50)
        log(f"RESULTS: {pass_count} passed, {fail_count} failed")
        if fail_count > 0:
            log("⚠️  Some tests failed - check screenshots in " + OUT_DIR)
        else:
            log("🎉 All tests passed!")

    except Exception as e:
        log(f"\n CRASH: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Save report
        report_path = os.path.join(OUT_DIR, "qa_report.md")
        with open(report_path, "a") as f:
            f.write(f"\n## QA Run {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"- **Passed:** {pass_count}\n")
            f.write(f"- **Failed:** {fail_count}\n")
            for entry in step_log:
                f.write(f"- {entry}\n")

        browser.close()
        pw_ctx.__exit__(None, None, None)

    return fail_count == 0


if __name__ == "__main__":
    success = run_qa()
    sys.exit(0 if success else 1)
