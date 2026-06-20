import frappe
import json
from frappe import _

# These are Frappe whitelisted endpoints that the Desk UI calls
# The actual Matrix C2S API is handled by the middleware at /_matrix/client/v3/*


@frappe.whitelist(allow_guest=True)
def get_status():
    """Get Matrix homeserver status and stats."""
    try:
        from .storage import get_connection, init_db
        init_db()
        conn = get_connection()

        user_count = conn.execute("SELECT COUNT(*) as c FROM users").fetchone()["c"]
        room_count = conn.execute("SELECT COUNT(*) as c FROM rooms").fetchone()["c"]
        event_count = conn.execute("SELECT COUNT(*) as c FROM events").fetchone()["c"]

        return {
            "status": "Running",
            "users": user_count,
            "rooms": room_count,
            "messages": event_count,
            "version": "1.7 (POC)",
        }
    except Exception as e:
        return {"status": "Error", "error": str(e)}


@frappe.whitelist(allow_guest=True)
def create_test_user():
    """Create a test Matrix user for POC verification."""
    from . import auth
    import frappe
    import string, random

    username = f"testuser_{''.join(random.choices(string.ascii_lowercase, k=6))}"
    password = "test123"

    result = auth.register(f"@{username}:localhost", password)
    if "errcode" in result:
        frappe.throw(result["error"])

    return {
        "username": username,
        "user_id": result["user_id"],
        "access_token": result["access_token"],
        "password": password,
    }


@frappe.whitelist(allow_guest=True)
def create_test_room(name: str = "Test Room"):
    """Create a test room with existing test users."""
    from . import auth, storage as store
    import string, random

    # Create two test users if they don't exist
    users = []
    for i in range(2):
        uname = f"testroom_user_{i}_{''.join(random.choices(string.ascii_lowercase, k=4))}"
        token = None
        result = auth.register(f"@{uname}:localhost", "test123")
        if "errcode" not in result:
            token = result["access_token"]
            users.append({"username": uname, "token": token, "user_id": f"@{uname}:localhost"})
        else:
            # User exists - get a token by logging in
            login_result = auth.login(f"@{uname}:localhost", "test123")
            if "errcode" not in login_result:
                token = login_result["access_token"]
                users.append({"username": uname, "token": token, "user_id": f"@{uname}:localhost"})

    if len(users) < 2:
        frappe.throw("Could not create test users")

    # User 1 creates a room inviting User 2
    from .homeserver import Homeserver
    hs = Homeserver()
    result = hs.create_room(
        users[0]["token"],
        name=name,
        invite=[users[1]["user_id"]],
    )
    room_id = result["room_id"]

    # User 2 joins the room
    hs.join_room(users[1]["token"], room_id)

    # Send a welcome message
    hs.send_message(users[0]["token"], room_id, "m.room.message", {
        "msgtype": "m.text",
        "body": f"Welcome to {name}! 👋"
    })

    return {
        "room_id": room_id,
        "name": name,
        "users": [u["username"] for u in users],
        "tokens": [u["token"] for u in users],
    }


@frappe.whitelist(allow_guest=True)
def list_rooms():
    """List all Matrix rooms."""
    from .storage import get_connection, init_db
    init_db()
    conn = get_connection()

    rooms = conn.execute("""
        SELECT r.*, 
               (SELECT COUNT(*) FROM room_members WHERE room_id = r.room_id AND membership = 'join') as member_count,
               (SELECT MAX(stream_ordering) FROM events WHERE room_id = r.room_id) as last_activity
        FROM rooms r
        ORDER BY created_ts DESC
    """).fetchall()

    result = []
    for r in rooms:
        d = dict(r)
        # Get last message
        last_msg = conn.execute(
            "SELECT content_json, sender, origin_server_ts FROM events WHERE room_id = ? AND type = 'm.room.message' ORDER BY stream_ordering DESC LIMIT 1",
            (r["room_id"],),
        ).fetchone()
        if last_msg:
            import json
            content = json.loads(last_msg["content_json"])
            d["last_message"] = content.get("body", "")
            d["last_sender"] = last_msg["sender"]
        result.append(d)

    return result


@frappe.whitelist(allow_guest=True)
def get_room_detail(room_id: str):
    """Get room details: members, recent messages."""
    from .storage import get_connection, init_db
    init_db()
    conn = get_connection()

    room = conn.execute("SELECT * FROM rooms WHERE room_id = ?", (room_id,)).fetchone()
    if not room:
        frappe.throw("Room not found")

    members = conn.execute(
        "SELECT user_id FROM room_members WHERE room_id = ? AND membership = 'join'",
        (room_id,),
    ).fetchall()

    events = conn.execute(
        "SELECT * FROM events WHERE room_id = ? ORDER BY stream_ordering DESC LIMIT 50",
        (room_id,),
    ).fetchall()

    import json as j
    return {
        "room": dict(room),
        "members": [m["user_id"] for m in members],
        "events": [
            {
                "event_id": e["event_id"],
                "sender": e["sender"],
                "type": e["type"],
                "content": j.loads(e["content_json"]),
                "origin_server_ts": e["origin_server_ts"],
            }
            for e in reversed(events)
        ],
    }
