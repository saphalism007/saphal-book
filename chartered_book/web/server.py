"""
The local web server.

Chartered Book shows its screens in a browser, but nothing leaves the machine.
The server binds to 127.0.0.1 by default, which the operating system does not
route anywhere. There is no internet call anywhere in this application.

The design is deliberately small: a request comes in, a handler runs, JSON goes
back. All the accounting lives in the modules package, not here.
"""

import http.cookies
import http.server
import json
import mimetypes
import os
import socketserver
import threading
import traceback
import urllib.parse

from ..core import auth, db

HERE = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(HERE, "static")
TEMPLATE_DIR = os.path.join(HERE, "templates")
COOKIE_NAME = "chartered_book_session"

_routes = []
_local = threading.local()

# What the server was told to listen on. The phone screen needs to know whether
# other machines can reach it, and the address the browser happens to have used
# does not answer that.
BIND = {"host": "127.0.0.1", "port": 8790}


class ApiError(Exception):
    """An error meant to be shown to the person using the screen."""

    def __init__(self, message, status=400):
        super().__init__(message)
        self.message = message
        self.status = status


class Request:
    """Everything a handler needs, gathered in one place."""

    def __init__(self, method, path, query, body, cookies, headers):
        self.method = method
        self.path = path
        self.query = query
        self.body = body if isinstance(body, dict) else {}
        self.cookies = cookies
        self.headers = headers
        self.session = None
        self.system = None
        self._company_conn = None
        self.set_cookie = None
        self.clear_cookie = False

    def arg(self, name, default=None):
        if name in self.body:
            return self.body[name]
        values = self.query.get(name)
        return values[0] if values else default

    def int_arg(self, name, default=None):
        value = self.arg(name, default)
        if value in (None, ""):
            return default
        try:
            return int(value)
        except (TypeError, ValueError):
            raise ApiError("%s must be a number." % name)

    @property
    def user(self):
        return self.session

    def require_user(self):
        if not self.session:
            raise ApiError("Please sign in.", 401)
        return self.session

    def require(self, action):
        self.require_user()
        if not auth.can(self.session, action):
            raise ApiError("Your role does not allow this.", 403)

    def username(self):
        return self.session["username"] if self.session else ""

    def company(self):
        """Open the book of the company the session is working in."""
        if self._company_conn is not None:
            return self._company_conn
        self.require_user()
        company_id = self.session.get("company_id")
        if not company_id:
            raise ApiError("Choose a company first.", 409)
        row = self.system.execute("SELECT * FROM companies WHERE id = ?",
                                  (company_id,)).fetchone()
        if row is None:
            # The books this session was working in have gone, most likely
            # restored from a backup taken before they existed. Forget the
            # choice so the person is simply asked to pick again.
            auth.set_session_company(self.system, self.session["token"], None)
            self.session["company_id"] = None
            raise ApiError("That company is no longer on the list. Choose one again.", 409)
        from ..modules import company as company_module
        self._company_conn = company_module.open_company(row["slug"])
        self.company_row = row
        return self._company_conn


def route(method, path):
    """Register a handler. Paths may carry one wildcard, written as <id>."""
    def wrap(fn):
        _routes.append((method.upper(), path, fn))
        return fn
    return wrap


def _match(method, path):
    for verb, pattern, fn in _routes:
        if verb != method:
            continue
        if pattern == path:
            return fn, {}
        if "<" in pattern:
            parts = pattern.strip("/").split("/")
            given = path.strip("/").split("/")
            if len(parts) != len(given):
                continue
            params = {}
            ok = True
            for expected, actual in zip(parts, given):
                if expected.startswith("<") and expected.endswith(">"):
                    params[expected[1:-1]] = actual
                elif expected != actual:
                    ok = False
                    break
            if ok:
                return fn, params
    return None, {}


class Handler(http.server.BaseHTTPRequestHandler):
    server_version = "CharteredBook"
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        if os.environ.get("CHARTERED_BOOK_VERBOSE"):
            super().log_message(fmt, *args)

    def do_GET(self):
        self._handle("GET")

    def do_POST(self):
        self._handle("POST")

    def do_DELETE(self):
        self._handle("DELETE")

    def _read_body(self):
        length = int(self.headers.get("Content-Length") or 0)
        if not length:
            return {}
        raw = self.rfile.read(length)
        content_type = (self.headers.get("Content-Type") or "").split(";")[0].strip()
        if content_type == "application/json":
            try:
                return json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                raise ApiError("The request could not be read.")
        parsed = urllib.parse.parse_qs(raw.decode("utf-8", "replace"))
        return {k: v[0] for k, v in parsed.items()}

    def _handle(self, method):
        parsed = urllib.parse.urlparse(self.path)
        path = urllib.parse.unquote(parsed.path)
        query = urllib.parse.parse_qs(parsed.query)

        if method == "GET" and not path.startswith("/api/"):
            return self._serve_page(path)

        try:
            body = self._read_body()
        except ApiError as exc:
            return self._json({"error": exc.message}, exc.status)

        # A browser will not attach this header on a cross site form post, so
        # requiring it stops another page in the browser from acting as you.
        if method != "GET" and self.headers.get("X-Chartered-Book") != "1":
            return self._json({"error": "This request did not come from the application."}, 403)

        handler, params = _match(method, path)
        if handler is None:
            return self._json({"error": "No such address."}, 404)

        cookies = http.cookies.SimpleCookie(self.headers.get("Cookie") or "")
        request = Request(method, path, query, body, cookies, self.headers)
        request.system = system_conn()
        token = cookies[COOKIE_NAME].value if COOKIE_NAME in cookies else None
        request.session = auth.load_session(request.system, token)

        try:
            result = handler(request, **params)
            payload = result if result is not None else {"ok": True}
            status = 200
        except ApiError as exc:
            payload, status = {"error": exc.message}, exc.status
        except Exception as exc:
            payload = {"error": _friendly(exc)}
            status = 400
            if os.environ.get("CHARTERED_BOOK_VERBOSE"):
                traceback.print_exc()
        self._json(payload, status, request)

    def _serve_page(self, path):
        if path in ("/", "/index.html"):
            return self._send_file(os.path.join(TEMPLATE_DIR, "index.html"), "text/html")
        # The service worker has to be served from the root or the browser will
        # not let it control the whole application.
        if path == "/sw.js":
            # A service worker script is fetched by the browser itself rather
            # than by the page, and it will refuse one it is told never to
            # store. max-age=0 still means it is checked every time.
            return self._send_file(os.path.join(STATIC_DIR, "sw.js"),
                                   "application/javascript", cache="max-age=0")
        if path == "/manifest.json":
            return self._send_file(os.path.join(STATIC_DIR, "manifest.json"), "application/json")
        if path == "/favicon.ico":
            return self._send_file(os.path.join(STATIC_DIR, "icons", "icon-32.png"), "image/png")
        if path.startswith("/static/"):
            relative = path[len("/static/"):]
            target = os.path.normpath(os.path.join(STATIC_DIR, relative))
            if not target.startswith(STATIC_DIR) or not os.path.isfile(target):
                return self._json({"error": "Not found."}, 404)
            guessed = mimetypes.guess_type(target)[0] or "application/octet-stream"
            return self._send_file(target, guessed)
        # Any other address belongs to the single page application.
        return self._send_file(os.path.join(TEMPLATE_DIR, "index.html"), "text/html")

    def _send_file(self, filename, content_type, cache="no-store"):
        try:
            with open(filename, "rb") as handle:
                data = handle.read()
        except OSError:
            return self._json({"error": "Not found."}, 404)
        textual = (content_type.startswith("text/") or "json" in content_type
                   or "javascript" in content_type)
        self.send_response(200)
        self.send_header("Content-Type",
                         "%s; charset=utf-8" % content_type if textual else content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", cache)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(data)

    def _json(self, payload, status=200, request=None):
        data = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        if request is not None and request.set_cookie:
            cookie = http.cookies.SimpleCookie()
            cookie[COOKIE_NAME] = request.set_cookie
            cookie[COOKIE_NAME]["path"] = "/"
            cookie[COOKIE_NAME]["httponly"] = True
            cookie[COOKIE_NAME]["samesite"] = "Strict"
            self.send_header("Set-Cookie", cookie.output(header="").strip())
        if request is not None and request.clear_cookie:
            self.send_header("Set-Cookie",
                             "%s=; Path=/; Max-Age=0; HttpOnly; SameSite=Strict" % COOKIE_NAME)
        self.end_headers()
        self.wfile.write(data)


def _friendly(exc):
    """Turn an internal error into something a shopkeeper can act on."""
    text = str(exc) or exc.__class__.__name__
    if "UNIQUE constraint failed" in text:
        return "That record already exists."
    if "FOREIGN KEY constraint failed" in text:
        return "Something this record depends on is missing or still in use."
    if "database is locked" in text:
        return "The books are busy. Try again in a moment."
    return text


def system_conn():
    """One system connection for each thread, because SQLite objects are not shared."""
    conn = getattr(_local, "system", None)
    if conn is None:
        conn = db.open_system()
        _local.system = conn
    return conn


class ThreadedServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def build_server(host="127.0.0.1", port=8790):
    from . import api  # registers every route
    assert api
    last_error = None
    for candidate in range(port, port + 20):
        try:
            httpd = ThreadedServer((host, candidate), Handler)
            BIND["host"] = host
            BIND["port"] = candidate
            return httpd
        except OSError as exc:
            last_error = exc
    raise RuntimeError("No free port between %d and %d: %s" % (port, port + 19, last_error))
