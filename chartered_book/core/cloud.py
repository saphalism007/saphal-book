"""
Talking to the server that carries books between devices.

The server is Supabase. It holds an account for each person and, against that
account, one row per set of books. What is in the row is a locked file it cannot
read. See vault.py for the lock; this module only carries the result.

Three ideas hold the whole thing together.

The books on this machine are the real ones. The server is a way of getting a
copy to another device, not the place the books live. Everything goes on working
with the network unplugged, which is the point of a shop.

A username is not an email address, but Supabase counts accounts by email, and
counting them is exactly what makes a duplicate impossible. So a username is
turned into an address in a domain that exists only for this purpose. The server
enforces that two people cannot take the same one, which is the thing that could
never be done while every device kept its own list.

The password does two separate jobs and must not do them with the same secret.
One half signs in. The other half unlocks the books and is never sent anywhere.
Both come from the password, by different routes, so the server learns nothing
that would let it open what it is storing.
"""

import hashlib
import hmac
import json
import struct
import sys
import urllib.error
import urllib.parse
import urllib.request

from . import vault

# Usernames live here. Nobody sends mail to it and no such domain is registered
# for mail; it exists so the server has something unique to count.
USERNAME_DOMAIN = "users.saphalbook.np"

SIGN_IN_LABEL = b"saphal book, the half of the password that signs in, version 1"
BOOK_NAME_LABEL = b"saphal book, the fingerprint of a set of books, version 1"

TIMEOUT = 30


class CloudError(Exception):
    """Raised when the server cannot do what was asked."""


class NotConfigured(CloudError):
    """Raised when no server has been set up for these books."""


class Conflict(CloudError):
    """
    Raised when the copy on the server is newer than the one being sent.

    Carries what is known about the other copy so a person can be told where it
    came from rather than simply being blocked.
    """

    def __init__(self, message, remote_version=0, device="", updated_at=""):
        CloudError.__init__(self, message)
        self.remote_version = remote_version
        self.device = device
        self.updated_at = updated_at


# Turning one password into two secrets that cannot be worked back from each other


def _split_password(username, password):
    """
    Give back the pair the password leads to.

    The first is sent to the server as the account password. The second never
    leaves the machine and is what locks the books. Each is a separate child of
    a key stretched from the password, so holding one tells you nothing about
    the other, and the server holding the first cannot arrive at the second.

    The username is folded into the salt so that two people who choose the same
    password do not end up with the same keys.
    """
    if not username or not password:
        raise CloudError("A username and a password are both needed.")
    salt = hashlib.sha256(("saphal book|" + username.strip().lower()).encode("utf-8")).digest()[:16]
    master = vault._pbkdf2(password.encode("utf-8"), salt, vault.ITERATIONS, 32)
    sign_in = hmac.new(master, SIGN_IN_LABEL, hashlib.sha256).hexdigest()
    return sign_in, master


def address_for(username):
    """The address a username is filed under on the server."""
    cleaned = (username or "").strip().lower()
    if not cleaned:
        raise CloudError("Choose a username.")
    allowed = set("abcdefghijklmnopqrstuvwxyz0123456789._-")
    if set(cleaned) - allowed:
        raise CloudError(
            "A username can hold letters, numbers, a dot, a dash and an underscore, "
            "and nothing else.")
    if len(cleaned) < 3:
        raise CloudError("A username needs at least three characters.")
    return "%s@%s" % (cleaned, USERNAME_DOMAIN)


def book_fingerprint(master_key, slug):
    """
    What a set of books is called on the server.

    A fingerprint made with the owner's own key, so the server is told which row
    to fetch without being told what the company is called.
    """
    return hmac.new(master_key, BOOK_NAME_LABEL + b"|" + slug.encode("utf-8"),
                    hashlib.sha256).hexdigest()


# Getting a request out of the machine, whichever kind of machine it is


IN_BROWSER = sys.platform == "emscripten" or "pyodide" in sys.modules


def _machine_call(url, method, data, headers):
    """The ordinary way, on a computer with a network of its own."""
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        answer = urllib.request.urlopen(request, timeout=TIMEOUT)
        raw = answer.read().decode("utf-8")
        return answer.status, (json.loads(raw) if raw.strip() else None)
    except urllib.error.HTTPError as error:
        raw = error.read().decode("utf-8", "replace")
        try:
            detail = json.loads(raw)
        except ValueError:
            detail = {"message": raw[:300]}
        return error.code, detail
    except urllib.error.URLError as error:
        raise CloudError(
            "Could not reach the server. Check the internet connection. (%s)" % error.reason)


def _browser_call(url, method, data, headers):
    """
    The same request, from inside a browser.

    Where this software runs in a browser it is Python compiled to
    WebAssembly, and WebAssembly has no sockets. Everything urllib knows how to
    do is therefore unavailable, and the request has to be handed to the browser
    itself. Without this the whole of syncing was dead on a tablet, which is the
    one device it was most wanted on.

    The request is made the blocking way on purpose. Every caller here is
    ordinary top to bottom Python that expects an answer before the next line,
    and rewriting all of it to wait would gain nothing: sending a set of books is
    a deliberate act with a message on the screen, not something happening in the
    background while somebody types.
    """
    try:
        from js import XMLHttpRequest
    except ImportError:
        raise CloudError("This browser will not let the books reach the server.")

    xhr = XMLHttpRequest.new()
    try:
        xhr.open(method, url, False)
        for name, value in headers.items():
            xhr.setRequestHeader(name, value)
        xhr.send(data.decode("utf-8") if data is not None else None)
    except Exception as error:                                      # noqa: BLE001
        raise CloudError(
            "Could not reach the server. Check the internet connection. (%s)" % error)

    status = int(xhr.status or 0)
    raw = xhr.responseText or ""
    if status == 0:
        raise CloudError("Could not reach the server. Check the internet connection.")
    try:
        return status, (json.loads(raw) if raw.strip() else None)
    except ValueError:
        return status, {"message": raw[:300]}


# What actually goes inside the locked file
#
# Not the books on their own. A device that has never seen a set of books knows
# only the fingerprint the server files it under, and a fingerprint cannot be
# turned back into a name. Without something to say what these books are, a new
# tablet can be told there is something waiting and have no way to ask for it,
# which is exactly the corner the first version painted itself into.
#
# So a short note travels inside the lock, ahead of the books: what they are
# called and what the file should be named. The server sees neither, because
# both are inside the part it cannot read.

ENVELOPE = b"SBBOOK\x01"


def _wrap(slug, name, data):
    note = json.dumps({"slug": slug, "name": name}, ensure_ascii=False).encode("utf-8")
    return ENVELOPE + struct.pack(">I", len(note)) + note + data


def _unwrap(blob):
    """Give back what the books are called and the books themselves."""
    if not blob.startswith(ENVELOPE):
        # Sent by a version that did not carry the note. Still perfectly good
        # books; they simply cannot say what they are called.
        return {"slug": "", "name": "", "data": blob}
    start = len(ENVELOPE)
    size = struct.unpack(">I", blob[start:start + 4])[0]
    note = json.loads(blob[start + 4:start + 4 + size].decode("utf-8"))
    return {"slug": note.get("slug", ""), "name": note.get("name", ""),
            "data": blob[start + 4 + size:]}


class Cloud(object):
    """One connection to the server, for one signed in person."""

    def __init__(self, url, anon_key):
        if not url or not anon_key:
            raise NotConfigured("No server has been set up for these books.")
        self.url = url.rstrip("/")
        self.anon_key = anon_key
        self.token = None
        self.refresh_token = None
        self.user_id = None
        self.username = None
        self.master_key = None

    # Speaking to it

    def _call(self, path, method="GET", body=None, headers=None, token=None):
        data = json.dumps(body).encode("utf-8") if body is not None else None
        head = {"apikey": self.anon_key,
                "Authorization": "Bearer " + (token or self.token or self.anon_key)}
        if data is not None:
            head["Content-Type"] = "application/json"
        head.update(headers or {})
        if IN_BROWSER:
            return _browser_call(self.url + path, method, data, head)
        return _machine_call(self.url + path, method, data, head)

    @staticmethod
    def _complain(detail, fallback):
        for key in ("msg", "message", "error_description", "error", "hint"):
            if isinstance(detail, dict) and detail.get(key):
                return str(detail[key])
        return fallback

    # Accounts

    def sign_up(self, username, password):
        """
        Open an account. The server refuses a username somebody already has,
        which is the whole reason for putting accounts on a server at all.
        """
        sign_in_secret, master = _split_password(username, password)
        status, detail = self._call("/auth/v1/signup", "POST", {
            "email": address_for(username), "password": sign_in_secret})
        if status in (200, 201):
            self._remember(detail, username, master)
            if not self.token:
                raise CloudError(
                    "The account was made but the server did not sign you in. Email "
                    "confirmation is probably still switched on for this project.")
            return {"username": username, "user_id": self.user_id}
        if status in (400, 422) and "already" in json.dumps(detail).lower():
            raise CloudError(
                "The username %s is taken. Somebody has already opened an account with "
                "it, so choose another one." % username)
        raise CloudError(self._complain(detail, "The account could not be opened."))

    def sign_in(self, username, password):
        """Sign in, and work out the key that unlocks the books, without sending it."""
        sign_in_secret, master = _split_password(username, password)
        status, detail = self._call("/auth/v1/token?grant_type=password", "POST", {
            "email": address_for(username), "password": sign_in_secret})
        if status == 200:
            self._remember(detail, username, master)
            return {"username": username, "user_id": self.user_id}
        if status in (400, 401):
            raise CloudError("That username and password do not match an account.")
        raise CloudError(self._complain(detail, "Could not sign in."))

    def resume(self, username, master_key, refresh_token):
        """
        Pick a connection back up without asking for the password again.

        The key that unlocks the books was worked out at sign in and kept on
        this device, so all that is needed here is a fresh ticket from the
        server. Where the ticket has expired or been withdrawn this fails and
        the password is asked for, which is the old behaviour and the right one.
        """
        if not (username and master_key and refresh_token):
            raise CloudError("Nothing to sign back in with.")
        status, detail = self._call("/auth/v1/token?grant_type=refresh_token", "POST",
                                    {"refresh_token": refresh_token})
        if status != 200:
            raise CloudError(self._complain(detail, "Could not pick the account back up."))
        self._remember(detail, username, master_key)
        return {"username": username, "user_id": self.user_id}

    def _remember(self, detail, username, master):
        detail = detail or {}
        self.token = detail.get("access_token")
        self.refresh_token = detail.get("refresh_token")
        self.user_id = (detail.get("user") or {}).get("id")
        self.username = username
        self.master_key = master

    def signed_in(self):
        return bool(self.token and self.master_key)

    def sign_out(self):
        self.token = self.refresh_token = self.user_id = None
        self.username = self.master_key = None

    # Books

    def _require(self):
        if not self.signed_in():
            raise CloudError("Sign in to the server first.")

    def list_books(self):
        """Every set of books this account carries, without opening any of them."""
        self._require()
        status, rows = self._call(
            "/rest/v1/books?select=book_id,version,device,updated_at&order=updated_at.desc")
        if status != 200:
            raise CloudError(self._complain(rows, "Could not read the list of books."))
        return rows or []

    def fetch(self, slug):
        """
        Bring a set of books down and unlock it.

        Returns None where the server has never seen these books.
        """
        self._require()
        fingerprint = book_fingerprint(self.master_key, slug)
        status, rows = self._call(
            "/rest/v1/books?book_id=eq.%s&select=payload,version,device,updated_at"
            % urllib.parse.quote(fingerprint))
        if status != 200:
            raise CloudError(self._complain(rows, "Could not fetch those books."))
        if not rows:
            # Either the server has never seen these books, or the key in hand
            # is not the one they were filed under. The two look the same from
            # here, and deliberately so: the server cannot tell us which.
            return None
        row = rows[0]
        import base64
        try:
            blob = base64.b64decode(row["payload"])
        except Exception:
            raise CloudError("The copy on the server is damaged and will not decode.")
        inside = _unwrap(vault.unlock(blob, self._vault_password()))
        return {"data": inside["data"], "slug": inside["slug"] or slug,
                "name": inside["name"],
                "version": row["version"], "device": row.get("device", ""),
                "updated_at": row.get("updated_at", "")}

    def fetch_by_id(self, book_id):
        """
        Bring down a set of books this device has never seen.

        All it has is the fingerprint from the list. What the books are called
        comes out of the locked file once it is open, which is the only place it
        was ever written.
        """
        self._require()
        import base64
        status, rows = self._call(
            "/rest/v1/books?book_id=eq.%s&select=payload,version,device,updated_at"
            % urllib.parse.quote(book_id))
        if status != 200:
            raise CloudError(self._complain(rows, "Could not fetch those books."))
        if not rows:
            return None
        row = rows[0]
        try:
            blob = base64.b64decode(row["payload"])
        except Exception:
            raise CloudError("The copy on the server is damaged and will not decode.")
        inside = _unwrap(vault.unlock(blob, self._vault_password()))
        if not inside["slug"]:
            raise CloudError(
                "Those books were sent by an older version that did not record what "
                "they are called. Send them up again from the device that has them.")
        return {"data": inside["data"], "slug": inside["slug"], "name": inside["name"],
                "version": row["version"], "device": row.get("device", ""),
                "updated_at": row.get("updated_at", "")}


    def remote_version(self, slug):
        """What version the server holds, or zero where it holds nothing."""
        self._require()
        fingerprint = book_fingerprint(self.master_key, slug)
        status, rows = self._call(
            "/rest/v1/books?book_id=eq.%s&select=version,device,updated_at"
            % urllib.parse.quote(fingerprint))
        if status != 200:
            raise CloudError(self._complain(rows, "Could not ask the server."))
        if not rows:
            return {"version": 0, "device": "", "updated_at": ""}
        return rows[0]

    def push(self, slug, data, expected_version, device="", name=""):
        """
        Send a set of books up, but only if nothing newer is already there.

        expected_version is what this device last saw. Where the server has moved
        on since, the send is refused rather than allowed to flatten somebody
        else's day of work.
        """
        self._require()
        import base64
        held = self.remote_version(slug)
        if held["version"] != expected_version:
            raise Conflict(
                "The copy on the server has changed since this device last looked. "
                "It is at version %d and this device expected %d."
                % (held["version"], expected_version),
                held["version"], held.get("device", ""), held.get("updated_at", ""))

        fingerprint = book_fingerprint(self.master_key, slug)
        blob = vault.lock(_wrap(slug, name or slug, data), self._vault_password())
        row = {"owner": self.user_id, "book_id": fingerprint,
               "version": expected_version + 1, "device": device[:80],
               "payload": base64.b64encode(blob).decode("ascii")}
        status, detail = self._call(
            "/rest/v1/books?on_conflict=owner,book_id", "POST", row,
            headers={"Prefer": "resolution=merge-duplicates,return=minimal"})
        if status not in (200, 201, 204):
            raise CloudError(self._complain(detail, "The server would not take the books."))
        return expected_version + 1

    def forget(self, slug):
        """Remove a set of books from the server. The copy here is untouched."""
        self._require()
        fingerprint = book_fingerprint(self.master_key, slug)
        status, detail = self._call(
            "/rest/v1/books?book_id=eq.%s" % urllib.parse.quote(fingerprint), "DELETE")
        if status not in (200, 204):
            raise CloudError(self._complain(detail, "Could not remove those books."))
        return True

    def _vault_password(self):
        """
        The key the books are locked with, as bytes.

        Not the password the person typed and not the secret the server holds.
        The master key itself, which only ever exists in memory on this machine.
        """
        return self.master_key.hex()


# Settings that belong to the person rather than to the machine


# A reserved name, kept apart from any company slug so it can never collide with
# one. The server sees only the fingerprint of it, as with everything else.
LINKED_ACCOUNT = "\x00saphal-book/linked-google-account"


# Everything kept under the account that is not a set of books. A tablet
# fetching what is waiting for it has to know to leave these alone: one of them
# opened as books says it is not a set of books, and that used to stop the whole
# fetch, which is how a device with four companies waiting ended up with none.
RESERVED_SLUGS = (LINKED_ACCOUNT,)

RESERVED_PREFIX = "\x00saphal-book/"


def is_reserved(slug):
    """Whether a name belongs to the software rather than to a company."""
    return bool(slug) and slug.startswith(RESERVED_PREFIX)


def _secret_slug(name):
    return RESERVED_PREFIX + name


def save_linked_account(session, details):
    """
    Put somebody's Google connection where their other devices can reach it.

    The connection belongs to the person, not to the machine they happened to
    set it up on. Signing in as the same person on a tablet should reach the
    same Drive without going through Google's consent screens again.

    It travels the way the books do, locked with the key made from the password,
    so the server stores something it cannot read. What Google handed over is a
    key to somebody's Drive, and it gets at least the care the books get.
    """
    blob = json.dumps(details, ensure_ascii=False).encode("utf-8")
    held = session.remote_version(LINKED_ACCOUNT)
    return session.push(LINKED_ACCOUNT, blob, held["version"], device="linked account")


def linked_account(session):
    """The Google connection this person set up, wherever they set it up."""
    got = session.fetch(LINKED_ACCOUNT)
    if got is None:
        return None
    try:
        return json.loads(got["data"].decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return None


def forget_linked_account(session):
    try:
        session.forget(LINKED_ACCOUNT)
    except CloudError:
        pass
    return True
