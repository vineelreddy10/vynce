import json
from werkzeug.routing import Map, Rule
from werkzeug.exceptions import NotFound
from werkzeug.wrappers import Response
from .homeserver import Homeserver


class MatrixAPI:
    """Handles HTTP routing for Matrix C2S API endpoints."""

    def __init__(self):
        self.homeserver = Homeserver()
        self.url_map = Map([
            Rule("/_matrix/client/v3/register", endpoint="register", methods=["POST"]),
            Rule("/_matrix/client/v3/login", endpoint="login", methods=["POST"]),
            Rule("/_matrix/client/v3/createRoom", endpoint="create_room", methods=["POST"]),
            Rule("/_matrix/client/v3/join/<room_id>", endpoint="join_room", methods=["POST"]),
            Rule("/_matrix/client/v3/rooms/<room_id>/send/<event_type>/<txn_id>", endpoint="send_event", methods=["PUT"]),
            Rule("/_matrix/client/v3/rooms/<room_id>/messages", endpoint="get_messages", methods=["GET"]),
            Rule("/_matrix/client/v3/sync", endpoint="sync", methods=["GET"]),
            Rule("/_matrix/client/v3/account/whoami", endpoint="whoami", methods=["GET"]),
        ])

    def _get_token(self, request):
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            return auth_header[7:]
        # Fallback: query param
        return request.args.get("access_token", "")

    def dispatch(self, request):
        try:
            urls = self.url_map.bind_to_environ(request.environ)
            endpoint, args = urls.match()
            handler = getattr(self, f"handle_{endpoint}")
            result = handler(request, **args)
            if result is None:
                return Response(
                    json.dumps({"errcode": "M_FORBIDDEN", "error": "Access denied"}),
                    status=403, content_type="application/json",
                )
            return Response(
                json.dumps(result), status=200, content_type="application/json"
            )
        except NotFound:
            return Response(
                json.dumps({"errcode": "M_NOT_FOUND", "error": "Resource not found"}),
                status=404, content_type="application/json",
            )
        except Exception as e:
            return Response(
                json.dumps({"errcode": "M_UNKNOWN", "error": str(e)}),
                status=500, content_type="application/json",
            )

    def _json_body(self, request):
        return request.get_json(silent=True) or {}

    # ─── Endpoint Handlers ───

    def handle_register(self, request, **kw):
        body = self._json_body(request)
        username = body.get("username", "")
        password = body.get("password", "")
        if not username or not password:
            return {"errcode": "M_INVALID_PARAM", "error": "username and password required"}
        result = self.homeserver.register(username, password)
        if "errcode" in result:
            return result
        # Matrix register response format
        return {
            "user_id": result["user_id"],
            "access_token": result["access_token"],
            "device_id": result.get("device_id", "POC"),
        }

    def handle_login(self, request, **kw):
        body = self._json_body(request)
        login_type = body.get("type", "m.login.password")
        if login_type != "m.login.password":
            # Return supported flows
            return {"flows": [{"type": "m.login.password"}]}

        identifier = body.get("identifier", {})
        password = body.get("password", "")
        user = identifier.get("user", "") if isinstance(identifier, dict) else ""
        result = self.homeserver.login(identifier, password)
        if "errcode" in result:
            return result
        return result

    def handle_whoami(self, request, **kw):
        token = self._get_token(request)
        result = self.homeserver.whoami(token)
        return result

    def handle_create_room(self, request, **kw):
        token = self._get_token(request)
        body = self._json_body(request)
        result = self.homeserver.create_room(
            token,
            name=body.get("name", ""),
            topic=body.get("topic", ""),
            invite=body.get("invite", []),
        )
        return result

    def handle_join_room(self, request, **kw):
        token = self._get_token(request)
        result = self.homeserver.join_room(token, kw.get("room_id", ""))
        return result

    def handle_send_event(self, request, **kw):
        token = self._get_token(request)
        body = self._json_body(request)
        result = self.homeserver.send_message(
            token,
            kw.get("room_id", ""),
            kw.get("event_type", "m.room.message"),
            body,
            kw.get("txn_id"),
        )
        return result

    def handle_get_messages(self, request, **kw):
        token = self._get_token(request)
        result = self.homeserver.get_messages(
            token,
            kw.get("room_id", ""),
            from_token=request.args.get("from"),
            limit=int(request.args.get("limit", 50)),
            direction=request.args.get("dir", "b"),
        )
        return result

    def handle_sync(self, request, **kw):
        token = self._get_token(request)
        result = self.homeserver.sync(
            token,
            since=request.args.get("since"),
            timeout=int(request.args.get("timeout", 0)),
        )
        return result
