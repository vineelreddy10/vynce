import json
import traceback
import frappe
from werkzeug.exceptions import HTTPException
from werkzeug.wrappers import Response
from .api import MatrixAPI

_api_instance = None


class MatrixResponse(HTTPException):
    """Werkzeug HTTPException that carries a JSON response.
    
    Raised from before_request to short-circuit Frappe's routing and
    return a JSON response to the client.
    """
    code = 200
    description = ""

    def get_response(self, environ=None, scope=None):
        return Response(
            self.description,
            status=self.code,
            content_type="application/json",
        )


def get_matrix_api():
    global _api_instance
    if _api_instance is None:
        _api_instance = MatrixAPI()
    return _api_instance


def before_request():
    """Frappe before_request hook: handles /_matrix/ requests."""
    path = frappe.local.request.path
    if not path.startswith("/_matrix/"):
        return

    try:
        from .storage import init_db
        init_db()

        api = get_matrix_api()
        request = frappe.local.request
        resp: Response = api.dispatch(request)
        data = resp.get_data(as_text=True)
        raise MatrixResponse(description=data)
    except MatrixResponse:
        raise
    except Exception as e:
        frappe.log_error(title="Matrix before_request error",
            message=f"{traceback.format_exc()}\nPath: {path}")
        raise MatrixResponse(
            description=json.dumps({"errcode": "M_UNKNOWN", "error": "Internal server error"})
        )