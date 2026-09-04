"""
Running the same books inside a browser.

Saphal Book normally answers over HTTP: the screens ask the local server for
a figure and it replies. On a phone or a tablet there is no local server to
ask, so instead the whole Python engine is loaded into the browser itself
through Pyodide, and this module stands in for the web server.

It takes the same request the screens would have sent, hands it to the same
handler in api.py, and gives back the same JSON. Not one line of accounting is
duplicated or reimplemented, which is the entire point: a figure worked out on
a phone comes off exactly the same code as a figure worked out on the Mac.

The only real differences are that the session token is handed over explicitly
rather than in a cookie, and that the books are kept in the browser's own
storage instead of a folder.
"""

import json
import traceback

from . import api  # registers every route
from .server import ApiError, Request, _match, system_conn

assert api  # imported for the side effect of registering the routes


def _decode(raw, default):
    if raw is None or raw == "":
        return default
    if isinstance(raw, (dict, list)):
        return raw
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return default


def dispatch(method, path, query="", body="", token=""):
    """
    Answer one request from the screens.

    Returns a JSON string holding the status, the payload, and whether the
    session token changed, because signing in and signing out are the two
    moments the browser has to be told to remember something new.
    """
    method = (method or "GET").upper()
    path = path or "/"
    query_map = _decode(query, {}) or {}
    # The screens send a flat query, the handlers expect a list per key, the
    # same shape the HTTP server produces from a query string.
    query_map = {k: (v if isinstance(v, list) else [v]) for k, v in query_map.items()}
    body_map = _decode(body, {}) or {}

    handler, params = _match(method, path)
    if handler is None:
        return json.dumps({"status": 404, "payload": {"error": "No such address."}})

    request = Request(method, path, query_map, body_map, {}, {})
    try:
        request.system = system_conn()
    except Exception as exc:
        return json.dumps({"status": 500,
                           "payload": {"error": "The books could not be opened: %s" % exc}})

    if token:
        from ..core import auth
        try:
            request.session = auth.load_session(request.system, token)
        except Exception:
            request.session = None

    try:
        result = handler(request, **params)
        payload = result if result is not None else {"ok": True}
        status = 200
    except ApiError as exc:
        payload, status = {"error": exc.message}, exc.status
    except Exception as exc:
        payload = {"error": _readable(exc)}
        status = 400
        try:
            traceback.print_exc()
        except Exception:
            pass

    answer = {"status": status, "payload": payload}
    if getattr(request, "set_cookie", None):
        answer["token"] = request.set_cookie
    if getattr(request, "clear_cookie", False):
        answer["clear_token"] = True
    return json.dumps(answer, ensure_ascii=False, default=str)


def _readable(exc):
    text = str(exc) or exc.__class__.__name__
    if "UNIQUE constraint failed" in text:
        return "That record already exists."
    if "FOREIGN KEY constraint failed" in text:
        return "Something this record depends on is missing or still in use."
    if "no such table" in text:
        return "These books are not set up yet. Close and open the app again."
    return text


def where_are_the_books():
    """The folder the books sit in, which in a browser is inside its storage."""
    from ..core import db
    return db.DATA_DIR


def bootstrap_message():
    """A short line for the loading screen, so the wait is explained."""
    from ..core import nepali_date as nd
    import datetime
    today = nd.describe(datetime.date.today())
    return "Saphal Book is ready. Today is %s." % today["bs_long"]
