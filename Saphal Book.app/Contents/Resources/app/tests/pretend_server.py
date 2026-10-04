"""
One device, talking to a server that is not there.

Used by test_one_login. Each run of this file is one device: it has its own
folder of books, named by SAPHAL_BOOK_DATA, and it shares a pretend server kept
in a file, so several devices can be run one after another against the same
account the way a phone, a tablet and a computer would be.

The real connection code is used throughout. Only the last step, the request
leaving the machine, is answered here instead, in the way the real server
answers: accounts that refuse a taken name, sign in that wants the right
secret, tickets that are withdrawn when a password changes, and rows that
belong to whoever is signed in.

Run by the test, not by hand.
"""

import json
import os
import sqlite3
import sys
import urllib.parse
import uuid

from chartered_book.core import auth, cloud, cloud_config, db
from chartered_book.web import embedded

SERVER_FILE = None


def _load():
    if os.path.exists(SERVER_FILE):
        with open(SERVER_FILE) as handle:
            return json.load(handle)
    return {"accounts": {}, "tickets": {}, "refresh": {}, "rows": {}}


def _save(state):
    with open(SERVER_FILE, "w") as handle:
        json.dump(state, handle)


class PretendCloud(cloud.Cloud):
    def _call(self, path, method="GET", body=None, headers=None, token=None):
        state = _load()
        if state.get("down"):
            # Asleep, the way a free project goes after a week unused.
            raise cloud.CloudError("The account server did not answer.")
        try:
            return self._answer(state, path, method, body or {}, token or self.token)
        finally:
            _save(state)

    @staticmethod
    def _issue(state, user_id):
        ticket, refresh = "t-" + uuid.uuid4().hex, "r-" + uuid.uuid4().hex
        state["tickets"][ticket] = user_id
        state["refresh"][refresh] = {"user": user_id, "ticket": ticket}
        return {"access_token": ticket, "refresh_token": refresh, "user": {"id": user_id}}

    def _answer(self, state, path, method, body, bearer):
        route, _, query = path.partition("?")
        asked = urllib.parse.parse_qs(query)
        accounts = state["accounts"]

        if route == "/auth/v1/signup":
            if body["email"] in accounts:
                return 422, {"msg": "User already registered"}
            user_id = uuid.uuid4().hex
            accounts[body["email"]] = {"secret": body["password"], "id": user_id}
            return 200, self._issue(state, user_id)

        if route == "/auth/v1/token" and asked.get("grant_type") == ["password"]:
            held = accounts.get(body["email"])
            if held is None or held["secret"] != body["password"]:
                return 400, {"error_description": "Invalid login credentials"}
            return 200, self._issue(state, held["id"])

        if route == "/auth/v1/token" and asked.get("grant_type") == ["refresh_token"]:
            held = state["refresh"].pop(body.get("refresh_token"), None)
            if held is None:
                return 400, {"error_description": "Invalid Refresh Token"}
            return 200, self._issue(state, held["user"])

        user_id = state["tickets"].get(bearer)
        if user_id is None:
            return 401, {"message": "JWT expired"}

        if route == "/auth/v1/user" and method == "PUT":
            for held in accounts.values():
                if held["id"] == user_id:
                    held["secret"] = body["password"]
            # Every other way in to this account is withdrawn, as the real one does.
            for refresh, held in list(state["refresh"].items()):
                if held["user"] == user_id and held["ticket"] != bearer:
                    del state["refresh"][refresh]
            for ticket, owner in list(state["tickets"].items()):
                if owner == user_id and ticket != bearer:
                    del state["tickets"][ticket]
            return 200, {"id": user_id}

        if route == "/rest/v1/books":
            mine = state["rows"].setdefault(user_id, {})
            wanted = asked.get("book_id", [None])[0]
            wanted = wanted[3:] if wanted and wanted.startswith("eq.") else None
            if method == "GET":
                rows = [dict(row, book_id=key, updated_at="2026-01-01T00:00:00")
                        for key, row in sorted(mine.items())
                        if wanted is None or key == wanted]
                return 200, rows
            if method == "POST":
                mine[body["book_id"]] = {"payload": body["payload"],
                                         "version": body["version"],
                                         "device": body.get("device", "")}
                return 201, None
            if method == "DELETE":
                mine.pop(wanted, None)
                return 204, None
        return 404, {"message": "no such address: " + path}


def make_books(slug, name, worked_on, marker):
    system = db.open_system()
    path = db.company_db_path(slug)
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS company (id INTEGER PRIMARY KEY, name TEXT);
        CREATE TABLE IF NOT EXISTS accounts (id INTEGER PRIMARY KEY);
        CREATE TABLE IF NOT EXISTS voucher_entries (id INTEGER PRIMARY KEY);
        CREATE TABLE IF NOT EXISTS vouchers (id INTEGER PRIMARY KEY, narration TEXT,
                                             created_at TEXT, updated_at TEXT);
        CREATE TABLE IF NOT EXISTS audit_log (id INTEGER PRIMARY KEY, at TEXT);
        DELETE FROM company; DELETE FROM vouchers; DELETE FROM audit_log;
    """)
    conn.execute("INSERT INTO company VALUES (1, ?)", (name,))
    conn.execute("INSERT INTO vouchers (narration, created_at) VALUES (?, ?)",
                 (marker, worked_on))
    conn.execute("INSERT INTO audit_log (at) VALUES (?)", (worked_on,))
    conn.commit()
    conn.close()
    system.execute("INSERT OR IGNORE INTO companies (slug, name, created_at) "
                   "VALUES (?, ?, ?)", (slug, name, db.now_stamp()))
    system.commit()


def what_is_here():
    system = db.open_system()
    found = {}
    for row in system.execute("SELECT slug FROM companies ORDER BY slug"):
        try:
            conn = sqlite3.connect(db.company_db_path(row["slug"]))
            found[row["slug"]] = conn.execute(
                "SELECT narration FROM vouchers").fetchone()[0]
            conn.close()
        except Exception as exc:                                    # noqa: BLE001
            found[row["slug"]] = "unreadable: %s" % exc
    return found


def run(steps):
    token = ""
    out = []
    for step in steps:
        what = step[0]
        if what == "local-user":
            system = db.open_system()
            auth.create_user(system, step[1], step[2], role="owner")
            system.commit()
            out.append("made")
        elif what == "books":
            make_books(*step[1:])
            out.append("made")
        elif what == "lose-touch":
            system = db.open_system()
            system.execute("UPDATE cloud_account SET master_key = '', refresh_token = ''")
            system.commit()
            from chartered_book.web import api
            api._CLOUD_SESSIONS.clear()
            out.append("lost")
        elif what == "server":
            state = _load()
            state["down"] = (step[1] == "off")
            _save(state)
            out.append(step[1])
        elif what == "here":
            out.append(what_is_here())
        elif what == "sign-out":
            token = ""
            out.append("out")
        else:
            path, body = step[1], step[2] if len(step) > 2 else {}
            answer = json.loads(embedded.dispatch("POST", path, "", json.dumps(body), token))
            if answer.get("token"):
                token = answer["token"]
            out.append({"status": answer["status"], "payload": answer["payload"]})
    return out


if __name__ == "__main__":
    SERVER_FILE = sys.argv[1]
    cloud.Cloud = PretendCloud
    cloud_config.configured = lambda system: True
    cloud_config.settings = lambda system: {"url": "http://pretend", "anon_key": "k"}
    print(json.dumps(run(json.loads(sys.argv[2]))))
