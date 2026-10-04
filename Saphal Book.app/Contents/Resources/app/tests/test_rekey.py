"""
A changed password has to be changed everywhere, or it is not changed.

The password signs in to the account and is also the key the copies on the
server are locked with. Changing it on one device and nowhere else leaves the
account answering to the old one and the copies locked with a key nobody will
type again. That is how somebody gets locked out of their own books by doing
the sensible thing, and it happened.

What is checked here is the move itself, against a stand in for the server
that keeps rows the way the real one does. After a move, a second device that
has never seen any of this and only knows the new password must be able to
open every set of books, at the version it was at. The old password must open
nothing. And a move that fails at any step must leave the server byte for byte
as it found it, because half a move is the one outcome that loses books.

Run with:  python3 -m tests.test_rekey
"""

import sys

from chartered_book.core import cloud, vault
from chartered_book.modules import rekey

FAILURES = []
NAME = "rekeytest"
OLD = "the old pass word"
NEW = "the new pass word"


def check(label, got, expected):
    if got != expected:
        FAILURES.append("%s: got %r, expected %r" % (label, got, expected))


class Server(object):
    """What the real one keeps: locked rows, and the secret that signs in."""

    def __init__(self):
        self.rows = {}
        self.secret = None
        self.refuse_password = False
        self.fail_on_put = 0
        self.puts = 0


class Account(object):
    """One device's connection to it."""

    def __init__(self, server):
        self.server = server
        self.master_key = None
        self.username = None
        self.user_id = "someone"
        self.token = None

    def sign_in(self, username, password):
        secret, master = cloud._split_password(username, password)
        if self.server.secret is None:
            self.server.secret = secret
        if secret != self.server.secret:
            raise cloud.CloudError("That username and password do not match an account.")
        self.master_key, self.username, self.token = master, username, "ticket"

    def signed_in(self):
        return bool(self.token and self.master_key)

    def list_books(self):
        return [{"book_id": key, "version": row["version"]}
                for key, row in sorted(self.server.rows.items())]

    def fetch_raw(self, book_id):
        row = self.server.rows.get(book_id)
        return dict(row) if row else None

    def put_raw(self, book_id, blob, version, device=""):
        self.server.puts += 1
        if self.server.fail_on_put and self.server.puts >= self.server.fail_on_put:
            raise cloud.CloudError("The line dropped.")
        self.server.rows[book_id] = {"blob": blob, "version": version, "device": device}

    def forget_by_id(self, book_id):
        self.server.rows.pop(book_id, None)

    def change_sign_in(self, secret):
        if self.server.refuse_password:
            raise cloud.CloudError("The account would not take the new password.")
        self.server.secret = secret

    # What an ordinary send does, so the rows start out the way real ones do.
    def send(self, slug, data, version, device):
        blob = vault.lock(cloud._wrap(slug, slug.title(), data), self.master_key.hex())
        self.server.rows[cloud.book_fingerprint(self.master_key, slug)] = {
            "blob": blob, "version": version, "device": device}

    def open(self, slug):
        row = self.server.rows.get(cloud.book_fingerprint(self.master_key, slug))
        if row is None:
            return None
        inside = cloud._unwrap(vault.unlock(row["blob"], self.master_key.hex()))
        return {"data": inside["data"], "version": row["version"],
                "device": row["device"]}


def a_server_with_books():
    server = Server()
    first = Account(server)
    first.sign_in(NAME, OLD)
    first.send("shop_one", b"the books of shop one", 7, "the shop machine")
    first.send("shop_two", b"the books of shop two", 3, "the tablet")
    first.send(cloud.LINKED_ACCOUNT, b'{"gdrive_account": "x@example.com"}', 2,
               "linked account")
    # And one left behind by a password before the old one.
    server.rows["left-behind"] = {
        "blob": vault.lock(cloud._wrap("ghost", "Ghost", b"old"), "some other key"),
        "version": 1, "device": "long ago"}
    return server, first


def main():
    # --- The move, done properly ---
    server, first = a_server_with_books()
    result = rekey.move(first, NAME, NEW, lambda: Account(server))
    check("three copies were moved", result["moved"], 3)
    check("and the one nobody can open was left alone", result["left"], 1)
    check("it is still there, untouched", "left-behind" in server.rows, True)
    check("nothing was duplicated", len(server.rows), 4)

    # A second device that knows only the new password.
    second = Account(server)
    second.sign_in(NAME, NEW)
    one = second.open("shop_one")
    check("the second device opens shop one", one and one["data"],
          b"the books of shop one")
    check("at the version it was at", one and one["version"], 7)
    check("sent from where it was sent from", one and one["device"],
          "the shop machine")
    two = second.open("shop_two")
    check("and shop two", two and two["data"], b"the books of shop two")
    check("at its own version", two and two["version"], 3)
    linked = second.open(cloud.LINKED_ACCOUNT)
    check("and the Google connection came across too",
          linked and linked["data"], b'{"gdrive_account": "x@example.com"}')

    # The old password is finished.
    stale = Account(server)
    try:
        stale.sign_in(NAME, OLD)
        FAILURES.append("the old password still signs in to the account")
    except cloud.CloudError:
        pass
    old_master = cloud._split_password(NAME, OLD)[1]
    check("and nothing is filed under the old key any more",
          cloud.book_fingerprint(old_master, "shop_one") in server.rows, False)

    check("the device that made the change holds the new key",
          result["session"].master_key, cloud._split_password(NAME, NEW)[1])

    # --- The account refuses the new password ---
    server, first = a_server_with_books()
    before = {key: dict(row) for key, row in server.rows.items()}
    secret_before = server.secret
    server.refuse_password = True
    try:
        rekey.move(first, NAME, NEW, lambda: Account(server))
        FAILURES.append("a refused password change was reported as done")
    except rekey.RekeyError:
        pass
    check("a refusal leaves every row exactly as it was", server.rows, before)
    check("and the account on its old password", server.secret, secret_before)
    check("and this device on its old key", first.master_key,
          cloud._split_password(NAME, OLD)[1])

    # --- The line drops half way through filing the new copies ---
    server, first = a_server_with_books()
    before = {key: dict(row) for key, row in server.rows.items()}
    server.fail_on_put = 2
    try:
        rekey.move(first, NAME, NEW, lambda: Account(server))
        FAILURES.append("half a move was reported as done")
    except rekey.RekeyError:
        pass
    check("half a move is put back", server.rows, before)
    check("with the account still on the old password", server.secret,
          cloud._split_password(NAME, OLD)[0])

    # --- The same password again is nothing to do ---
    server, first = a_server_with_books()
    before = {key: dict(row) for key, row in server.rows.items()}
    result = rekey.move(first, NAME, OLD, lambda: Account(server))
    check("the same password moves nothing", result["same"], True)
    check("and touches nothing", server.rows, before)

    if FAILURES:
        print("Rekey: %d problem%s" % (len(FAILURES), "" if len(FAILURES) == 1 else "s"))
        for line in FAILURES:
            print("  " + line)
        return 1
    print("Rekey: a changed password moves the account and every copy on it, "
          "or moves nothing.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
