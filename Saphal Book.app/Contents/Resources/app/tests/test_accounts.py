"""
An account, and getting back into it.

The sign in screen used to say a forgotten password could not be reset. That
was frightening, and it was not even true. It now says the opposite, so this
is here to keep the promise honest.

Three things are checked. An account carries an email and a mobile number,
because backups need somewhere to go and one user could not add theirs. An
owner can set somebody a new password, and the old one stops working the
moment they do. And a password change costs nothing: the same person signs in
with the new one and everything about the account is still there.

Run with:  python3 -m tests.test_accounts
"""

import sys

from chartered_book.core import auth, db

FAILURES = []
PREFIX = "acct_test_"


def check(label, got, expected):
    if got != expected:
        FAILURES.append("%s: got %r, expected %r" % (label, got, expected))


def clean_up(system):
    system.execute("DELETE FROM users WHERE username LIKE ?", (PREFIX + "%",))
    system.commit()


def main():
    system = db.open_system()
    clean_up(system)

    owner = PREFIX + "owner"
    staff = PREFIX + "staff"

    # An owner sets up a member of staff, with the address their backups need.
    auth.create_user(system, owner, "first pass word", "Shop Owner", "owner")
    staff_id = auth.create_user(system, staff, "second pass word", "Counter Staff",
                                "operator", email="counter@example.com",
                                mobile="9800000000")
    system.commit()

    row = system.execute("SELECT email, mobile FROM users WHERE id = ?",
                         (staff_id,)).fetchone()
    check("the email is kept", row["email"], "counter@example.com")
    check("and the mobile", row["mobile"], "9800000000")

    # They can sign in with what they were given.
    check("the new user can sign in",
          auth.authenticate(system, staff, "second pass word") is not None, True)

    # The address can be corrected later without touching anything else.
    auth.set_details(system, staff_id, email="shop.counter@example.com")
    system.commit()
    row = system.execute("SELECT email, mobile, full_name FROM users WHERE id = ?",
                         (staff_id,)).fetchone()
    check("the email can be changed", row["email"], "shop.counter@example.com")
    check("without disturbing the mobile", row["mobile"], "9800000000")
    check("or the name", row["full_name"], "Counter Staff")

    # Now the part the sign in screen promises. They forget their password and
    # the owner sets a new one.
    auth.set_password(system, staff_id, "third pass word")
    system.commit()

    try:
        auth.authenticate(system, staff, "second pass word")
        FAILURES.append("the old password still worked after the reset")
    except auth.AuthError:
        pass
    signed_in = auth.authenticate(system, staff, "third pass word")
    check("the new one gets them in", signed_in is not None, True)

    # And nothing about the account was lost along the way.
    row = system.execute("SELECT email, mobile, full_name, role FROM users "
                         "WHERE id = ?", (staff_id,)).fetchone()
    check("the email survived the reset", row["email"], "shop.counter@example.com")
    check("so did the mobile", row["mobile"], "9800000000")
    check("and the name", row["full_name"], "Counter Staff")
    check("and what they are allowed to do", row["role"], "operator")

    # An owner is allowed to do the resetting. An operator is not.
    check("an owner may manage users",
          auth.can({"role": auth.find_user(system, owner)["role"]}, "user.manage"),
          True)
    check("an operator may not",
          auth.can({"role": auth.find_user(system, staff)["role"]}, "user.manage"),
          False)

    # --- The same username cannot be taken twice, however it is typed ---
    #
    # Two people signing in as the same name is not a small problem in a set of
    # books: every entry is stamped with who made it, and two of them would be
    # indistinguishable afterwards. So this is checked the way somebody would
    # actually stumble into it, not just the obvious way.
    for attempt, why in [
        (staff, "exactly the same"),
        (staff.upper(), "in capitals"),
        (staff.title(), "with a capital first letter"),
        ("  " + staff + "  ", "with spaces around it"),
    ]:
        try:
            auth.create_user(system, attempt, "a different password again")
            FAILURES.append("the username was taken twice, " + why)
        except auth.AuthError:
            pass

    # And the file itself refuses it too, so a path that somehow got past the
    # check above would still not end up with two.
    try:
        system.execute(
            "INSERT INTO users (username, full_name, password_hash, password_salt, "
            "iterations, role, active, must_change, created_at) "
            "VALUES (?, '', 'x', 'y', 1, 'operator', 1, 0, '2026-01-01')",
            (staff.upper(),))
        system.commit()
        FAILURES.append("the books themselves allowed a duplicate username")
    except Exception:
        system.rollback()

    check("so there is still exactly one of them",
          system.execute("SELECT COUNT(*) n FROM users WHERE lower(username) = ?",
                         (staff,)).fetchone()["n"], 1)

    clean_up(system)

    if FAILURES:
        print("Accounts: %d problem%s"
              % (len(FAILURES), "" if len(FAILURES) == 1 else "s"))
        for line in FAILURES:
            print("  " + line)
        return 1
    print("Accounts: a forgotten password can be reset, and nothing is lost.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
