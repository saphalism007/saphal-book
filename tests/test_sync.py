"""
Bringing books down from the account onto a device that has never seen them.

This exists because of a real failure. A tablet was told four sets of books were
waiting, pressed the button, and was told the copy that came down was not a set
of books. Nothing arrived. The account held three companies and one other thing:
the Google connection, which travels the same way and is filed in the same
place. Opening it as books failed, and the failure stopped the whole fetch, so
the three good companies never landed either.

Two rules come out of that, and both are tested here.

Anything under the account that is not a set of books is left alone, and is not
even fetched, because its name can be worked out on the device.

And one bad row does not cost the rest. What will not open is reported and the
rest still arrive.

Run with:  python3 -m tests.test_sync
"""

import glob
import os
import sqlite3
import sys

from chartered_book.core import cloud, db, vault
from chartered_book.modules import sync

FAILURES = []
PREFIX = "sync_test_"


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


def a_set_of_books(name):
    """The smallest thing the check will accept as real books."""
    path = os.path.join(db.BOOKS_DIR, "_sync_probe.db")
    if os.path.exists(path):
        os.remove(path)
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE company (id INTEGER PRIMARY KEY, name TEXT)")
    conn.execute("INSERT INTO company VALUES (1, ?)", (name,))
    for table in ("accounts", "vouchers", "voucher_entries"):
        conn.execute("CREATE TABLE %s (id INTEGER PRIMARY KEY)" % table)
    conn.commit()
    conn.close()
    with open(path, "rb") as handle:
        data = handle.read()
    os.remove(path)
    return data


class FakeAccount(object):
    """
    An account with things in it, without a server.

    It answers the two questions the fetch asks: what is on the account, and
    what is in one row. Everything is keyed by the same fingerprint the real
    thing uses, so the device cannot tell the difference.
    """

    def __init__(self):
        self.master_key = b"a key that is only used by this test, thirty two"[:32]
        self.username = "synctest"
        self.rows = {}
        self.fetched = []

    def signed_in(self):
        return True

    def hold(self, slug, name, data):
        self.rows[cloud.book_fingerprint(self.master_key, slug)] = {
            "slug": slug, "name": name, "data": data, "version": 1,
            "device": "the shop machine"}

    def list_books(self):
        return [{"book_id": key, "version": row["version"], "device": row["device"],
                 "updated_at": "2026-09-05T13:00:00"}
                for key, row in sorted(self.rows.items())]

    def fetch_by_id(self, book_id):
        self.fetched.append(book_id)
        row = self.rows.get(book_id)
        if row is not None and row.get("stale_password"):
            # What a copy left behind by an older password looks like: the key
            # made from today's password will not open it.
            raise vault.VaultError(
                "The password is wrong, or this file has been altered since it "
                "was locked.")
        return row


def main():
    clean_up()
    system = db.open_system()
    account = FakeAccount()

    # Three companies and the Google connection, exactly as the tablet found it.
    account.hold(PREFIX + "one", "Sync Test One", a_set_of_books("Sync Test One"))
    account.hold(PREFIX + "two", "Sync Test Two", a_set_of_books("Sync Test Two"))
    account.hold(PREFIX + "three", "Sync Test Three", a_set_of_books("Sync Test Three"))
    account.hold(cloud.LINKED_ACCOUNT, "", b'{"gdrive_account": "saphalai007@gmail.com"}')

    # What the screen offers to bring down has to be three, not four.
    standing = sync.status(system, account)
    check("the connection is not counted as books waiting",
          standing["waiting_elsewhere"], 3)

    result = sync.bring_new(system, account)
    check("all three companies arrive", result["count"], 3)
    check("and nothing had to be skipped", result["skipped_count"], 0)
    check("the connection was never even fetched",
          cloud.book_fingerprint(account.master_key, cloud.LINKED_ACCOUNT)
          in account.fetched, False)

    landed = {row["slug"]: row["name"] for row in result["brought"]}
    check("the first is named from inside the file",
          landed.get(PREFIX + "one"), "Sync Test One")
    check("so is the third", landed.get(PREFIX + "three"), "Sync Test Three")

    on_device = {row["slug"] for row in system.execute(
        "SELECT slug FROM companies WHERE slug LIKE ?", (PREFIX + "%",))}
    check("and all three are on the device",
          on_device, {PREFIX + "one", PREFIX + "two", PREFIX + "three"})

    # Asking again brings nothing, because they are no longer strangers.
    again = sync.bring_new(system, account)
    check("asking twice does not fetch them twice", again["count"], 0)

    # One unreadable row must not cost the others.
    clean_up()
    account.fetched = []
    account.hold(PREFIX + "four", "Sync Test Four", b"this is not a database at all")
    spoiled = sync.bring_new(system, account)
    check("the good ones still arrive", spoiled["count"], 3)
    check("and the bad one is reported", spoiled["skipped_count"], 1)
    check("by name", spoiled["skipped"][0]["slug"], PREFIX + "four")
    check("with a reason a person can read",
          "not a set of books" in spoiled["skipped"][0]["why"], True)

    on_device = {row["slug"] for row in system.execute(
        "SELECT slug FROM companies WHERE slug LIKE ?", (PREFIX + "%",))}
    check("the unreadable one is not on the device",
          PREFIX + "four" in on_device, False)

    # A copy locked under an older password. Somebody who has changed theirs
    # leaves one of these behind on the account, and it must be stepped over
    # rather than allowed to stop the fetch.
    clean_up()
    account.fetched = []
    # Take the unreadable one from the block above off the account, so what is
    # counted here is the stale password and nothing else.
    del account.rows[cloud.book_fingerprint(account.master_key, PREFIX + "four")]
    account.hold(PREFIX + "five", "Sync Test Five", a_set_of_books("Sync Test Five"))
    account.rows[cloud.book_fingerprint(account.master_key,
                                        PREFIX + "five")]["stale_password"] = True

    after_reset = sync.bring_new(system, account)
    check("the three good ones still arrive", after_reset["count"], 3)
    check("and the one locked under an old password is stepped over",
          after_reset["skipped_count"], 1)
    check("with a reason that does not alarm anybody",
          "older password" in after_reset["skipped"][0]["why"], True)

    on_device = {row["slug"] for row in system.execute(
        "SELECT slug FROM companies WHERE slug LIKE ?", (PREFIX + "%",))}
    check("the unopenable one is not on the device",
          PREFIX + "five" in on_device, False)

    clean_up()

    if FAILURES:
        print("Sync: %d problem%s" % (len(FAILURES), "" if len(FAILURES) == 1 else "s"))
        for line in FAILURES:
            print("  " + line)
        return 1
    print("Sync: books come down, and what is not books is left where it is.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
