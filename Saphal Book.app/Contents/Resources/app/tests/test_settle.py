"""
The same books changed on two devices, settled without asking anybody.

It used to stop and ask which copy to keep. Now the copy worked on last is
kept, and the other is set aside whole rather than destroyed. Since nobody is
asked, getting this wrong would lose somebody's entries without a word, so
three things are held here.

The copy that wins is the one worked on last, read from inside the books and
not from the date on the file, because opening the software can touch a file
without anybody entering anything.

The copy that loses on this device is still on the disk afterwards, complete.

And a device that signs in to a different account, which is what a username
started again under a new password is, does not act on counts that belonged to
the old one. Its older books must not go up over newer ones.

Run with:  python3 -m tests.test_settle
"""

import glob
import os
import sqlite3
import sys

from chartered_book.core import cloud, db
from chartered_book.modules import sync

FAILURES = []
PREFIX = "settle_test_"
# Only ever these. The books this runs beside are somebody's real ones, and a
# test that keeps things level must not be let near them.
OURS = (PREFIX + "theirs", PREFIX + "ours", PREFIX + "stale")


def check(label, got, expected):
    if got != expected:
        FAILURES.append("%s: got %r, expected %r" % (label, got, expected))


def clean_up():
    system = db.open_system()
    system.execute("DELETE FROM companies WHERE slug LIKE ?", (PREFIX + "%",))
    system.execute("DELETE FROM cloud_books WHERE slug LIKE ?", (PREFIX + "%",))
    system.commit()
    for path in glob.glob(os.path.join(db.BOOKS_DIR, PREFIX + "*")):
        try:
            os.remove(path)
        except OSError:
            pass


def books(name, worked_on, marker):
    """Real enough books, last worked on at a given moment."""
    path = os.path.join(db.BOOKS_DIR, "_settle_probe.db")
    if os.path.exists(path):
        os.remove(path)
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE company (id INTEGER PRIMARY KEY, name TEXT)")
    conn.execute("INSERT INTO company VALUES (1, ?)", (name,))
    conn.execute("CREATE TABLE accounts (id INTEGER PRIMARY KEY)")
    conn.execute("CREATE TABLE voucher_entries (id INTEGER PRIMARY KEY)")
    conn.execute("CREATE TABLE vouchers (id INTEGER PRIMARY KEY, narration TEXT, "
                 "created_at TEXT, updated_at TEXT)")
    conn.execute("CREATE TABLE audit_log (id INTEGER PRIMARY KEY, at TEXT)")
    conn.execute("INSERT INTO vouchers (narration, created_at) VALUES (?, ?)",
                 (marker, worked_on))
    conn.execute("INSERT INTO audit_log (at) VALUES (?)", (worked_on,))
    conn.commit()
    conn.close()
    with open(path, "rb") as handle:
        data = handle.read()
    os.remove(path)
    return data


def marker_in(path_or_bytes):
    if isinstance(path_or_bytes, bytes):
        temp = os.path.join(db.BOOKS_DIR, "_settle_read.db")
        with open(temp, "wb") as handle:
            handle.write(path_or_bytes)
        try:
            return marker_in(temp)
        finally:
            os.remove(temp)
    conn = sqlite3.connect(path_or_bytes)
    try:
        return conn.execute("SELECT narration FROM vouchers").fetchone()[0]
    finally:
        conn.close()


class Account(object):
    def __init__(self):
        self.master_key = b"k" * 32
        self.username = "settletest"
        self.rows = {}

    def signed_in(self):
        return True

    def hold(self, slug, name, data, version, device):
        self.rows[slug] = {"slug": slug, "name": name, "data": data,
                           "version": version, "device": device}

    def list_books(self):
        return [{"book_id": cloud.book_fingerprint(self.master_key, slug),
                 "version": row["version"], "device": row["device"]}
                for slug, row in self.rows.items()]

    def fetch(self, slug):
        return self.rows.get(slug)

    def fetch_by_id(self, book_id):
        for slug, row in self.rows.items():
            if cloud.book_fingerprint(self.master_key, slug) == book_id:
                return row
        return None

    def remote_version(self, slug):
        row = self.rows.get(slug)
        return {"version": row["version"] if row else 0,
                "device": row["device"] if row else "", "updated_at": ""}

    def push(self, slug, data, expected_version, device="", name=""):
        held = self.remote_version(slug)["version"]
        if held != expected_version:
            raise cloud.Conflict("moved", held, "", "")
        self.hold(slug, name, data, expected_version + 1, device)
        return expected_version + 1


def put_here(system, slug, name, data, version, last_hash):
    with open(db.company_db_path(slug), "wb") as handle:
        handle.write(data)
    system.execute("INSERT OR IGNORE INTO companies (slug, name, created_at) "
                   "VALUES (?, ?, ?)", (slug, name, db.now_stamp()))
    system.commit()
    sync._remember(system, slug, version=version, last_hash=last_hash)


def main():
    clean_up()
    system = db.open_system()

    # --- Both changed, and the other device worked on them last ---
    slug = PREFIX + "theirs"
    account = Account()
    put_here(system, slug, "Settle Theirs",
             books("Settle Theirs", "2026-09-10 09:00:00", "entered here, earlier"),
             3, "what the two agreed on")
    account.hold(slug, "Settle Theirs",
                 books("Settle Theirs", "2026-09-10 17:30:00", "entered there, later"),
                 4, "the tablet")

    result = sync.auto(system, account, only=OURS)
    check("nobody is asked anything", [c for c in result["conflicts"]
                                       if c.get("slug") == slug], [])
    how = [s for s in result["settled"] if s["name"] == "Settle Theirs"]
    check("it was settled", len(how), 1)
    check("in favour of the copy worked on last", how and how[0]["kept"], "there")
    check("which is now the books on this device",
          marker_in(db.company_db_path(slug)), "entered there, later")
    aside = how[0].get("aside") if how else ""
    check("the copy that lost is still on the disk", bool(aside and os.path.exists(aside)), True)
    if aside and os.path.exists(aside):
        check("complete, with what was entered here",
              marker_in(aside), "entered here, earlier")

    again = sync.auto(system, account, only=OURS)
    check("and once settled it stays settled",
          [s for s in again["settled"] if s["name"] == "Settle Theirs"], [])

    # --- Both changed, and this device worked on them last ---
    slug = PREFIX + "ours"
    put_here(system, slug, "Settle Ours",
             books("Settle Ours", "2026-09-12 18:00:00", "entered here, later"),
             3, "what the two agreed on")
    account.hold(slug, "Settle Ours",
                 books("Settle Ours", "2026-09-12 08:00:00", "entered there, earlier"),
                 4, "the tablet")
    result = sync.auto(system, account, only=OURS)
    how = [s for s in result["settled"] if s["name"] == "Settle Ours"]
    check("this device's later work is kept", how and how[0]["kept"], "here")
    check("and is what the server now holds",
          marker_in(account.rows[slug]["data"]), "entered here, later")
    check("the books here were not touched",
          marker_in(db.company_db_path(slug)), "entered here, later")

    # --- A stale device meeting a different account ---
    #
    # Its counts say version 6 and the account says version 1. Read as numbers
    # that looks like this device being five saves ahead. It is not: the counts
    # belonged to another account, and are wiped when the account changes. What
    # is left is two copies and the question of which was worked on last.
    slug = PREFIX + "stale"
    put_here(system, slug, "Settle Stale",
             books("Settle Stale", "2026-09-05 10:35:00", "a month old"),
             0, "")
    account.hold(slug, "Settle Stale",
                 books("Settle Stale", "2026-10-04 21:00:00", "this week's work"),
                 1, "the other browser")
    result = sync.auto(system, account, only=OURS)
    check("old books do not go up over new ones",
          marker_in(account.rows[slug]["data"]), "this week's work")
    check("the new ones come down instead",
          marker_in(db.company_db_path(slug)), "this week's work")

    # --- The date on the file is not what decides ---
    check("the time comes from inside the books",
          sync.last_worked_on(db.company_db_path(slug)), "2026-10-04 21:00:00")

    clean_up()

    if FAILURES:
        print("Settle: %d problem%s" % (len(FAILURES), "" if len(FAILURES) == 1 else "s"))
        for line in FAILURES:
            print("  " + line)
        return 1
    print("Settle: the copy worked on last is kept, and the other is set aside whole.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
