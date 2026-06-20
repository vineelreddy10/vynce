import json
from . import storage as store
from . import auth
from .utils import generate_room_id, generate_event_id, generate_user_id


class Homeserver:
    """Core Matrix homeserver logic."""

    def register(self, username, password):
        """POST /_matrix/client/v3/register"""
        user_id = generate_user_id(username)
        return auth.register(user_id, password)

    def login(self, identifier, password):
        """POST /_matrix/client/v3/login"""
        # identifier can be: {"type": "m.id.user", "user": "username"}
        if isinstance(identifier, dict):
            username = identifier.get("user", "")
        else:
            username = str(identifier)
        return auth.login(username, password)

    def whoami(self, token):
        """GET /_matrix/client/v3/account/whoami"""
        user_id = auth.validate_token(token)
        if not user_id:
            return None
        return {"user_id": user_id, "device_id": "POC"}

    def create_room(self, token, name="", topic="", invite=None, is_direct=False):
        """POST /_matrix/client/v3/createRoom"""
        user_id = auth.validate_token(token)
        if not user_id:
            return None

        room_id = generate_room_id()
        store.create_room(room_id, user_id, name or "", topic or "")
        store.add_member(room_id, user_id, "join")

        # Create room create event
        store.insert_event(
            generate_event_id(), room_id, user_id,
            "m.room.create", {"creator": user_id, "room_version": "1"},
            state_key="",
        )
        # Create member event for creator
        store.insert_event(
            generate_event_id(), room_id, user_id,
            "m.room.member", {"membership": "join", "displayname": user_id},
            state_key=user_id,
        )
        # Name event
        if name:
            store.insert_event(
                generate_event_id(), room_id, user_id,
                "m.room.name", {"name": name},
                state_key="",
            )

        # Invite others
        invited = invite or []
        for invitee in invited:
            invitee_id = invitee if invitee.startswith("@") else generate_user_id(invitee)
            # Create invite event
            store.insert_event(
                generate_event_id(), room_id, user_id,
                "m.room.member", {"membership": "invite"},
                state_key=invitee_id,
            )
            store.add_member(room_id, invitee_id, "invite")

        return {
            "room_id": room_id,
            "room_alias": f"#{name.lower().replace(' ', '-')}:localhost" if name else None,
        }

    def join_room(self, token, room_id):
        """POST /_matrix/client/v3/join/{roomId}"""
        user_id = auth.validate_token(token)
        if not user_id:
            return None

        room = store.get_room(room_id)
        if not room:
            return None

        store.add_member(room_id, user_id, "join")
        store.insert_event(
            generate_event_id(), room_id, user_id,
            "m.room.member", {"membership": "join"},
            state_key=user_id,
        )

        return {"room_id": room_id}

    def send_message(self, token, room_id, event_type, content, txn_id=None):
        """PUT /_matrix/client/v3/rooms/{roomId}/send/{eventType}/{txnId}"""
        user_id = auth.validate_token(token)
        if not user_id:
            return None

        if not store.is_member(room_id, user_id):
            return None

        event_id = generate_event_id()
        store.insert_event(event_id, room_id, user_id, event_type, content)

        return {"event_id": event_id}

    def get_messages(self, token, room_id, from_token=None, limit=50, direction="b"):
        """GET /_matrix/client/v3/rooms/{roomId}/messages"""
        user_id = auth.validate_token(token)
        if not user_id or not store.is_member(room_id, user_id):
            return None

        events = store.get_room_events(room_id, from_token=from_token, limit=limit, direction=direction)

        formatted = []
        end_token = from_token or str(store.get_latest_stream_position())
        start_token = end_token

        for ev in events:
            formatted.append({
                "event_id": ev["event_id"],
                "type": ev["type"],
                "room_id": ev["room_id"],
                "sender": ev["sender"],
                "content": json.loads(ev["content_json"]),
                "origin_server_ts": ev["origin_server_ts"],
                "state_key": ev["state_key"],
            })
            if direction == "b":
                start_token = str(ev["stream_ordering"])

        if formatted:
            start_token = str(formatted[-1]["origin_server_ts"]) if direction == "f" else str(formatted[0].get("origin_server_ts", ""))

        return {
            "start": start_token or from_token or "",
            "end": end_token,
            "chunk": formatted,
        }

    def sync(self, token, since=None, timeout=0):
        """GET /_matrix/client/v3/sync"""
        user_id = auth.validate_token(token)
        if not user_id:
            return None

        from_position = int(since) if since else 0
        user_rooms = store.get_user_rooms(user_id)

        join = {}
        for room in user_rooms:
            events = store.get_events_since(room["room_id"], from_position)
            if not events:
                join[room["room_id"]] = {
                    "timeline": {"events": [], "prev_batch": since or "0", "limited": False},
                    "state": {"events": []},
                    "account_data": {"events": []},
                    "ephemeral": {"events": []},
                    "unread_notifications": {},
                }
                continue

            formatted = []
            for ev in events:
                formatted.append({
                    "event_id": ev["event_id"],
                    "type": ev["type"],
                    "room_id": ev["room_id"],
                    "sender": ev["sender"],
                    "content": json.loads(ev["content_json"]),
                    "origin_server_ts": ev["origin_server_ts"],
                    "state_key": ev["state_key"],
                })

            join[room["room_id"]] = {
                "timeline": {"events": formatted, "prev_batch": since or "0", "limited": False},
                "state": {"events": []},
                "account_data": {"events": []},
                "ephemeral": {"events": []},
                "unread_notifications": {},
            }

        next_batch = str(store.get_latest_stream_position())

        return {
            "next_batch": next_batch,
            "rooms": {"join": join, "invite": {}, "leave": {}},
            "account_data": {"events": []},
            "presence": {"events": []},
            "device_lists": {"changed": []},
        }
