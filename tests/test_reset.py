"""
Getting back in when the password has gone.

The sign in screen now offers this, so it has to be real. A reset that can be
walked past is worse than none, because it looks like a lock while being a
door, so what is checked here is mostly the refusals.

The code is six digits and it is guessable in a million tries, which is nothing
to a machine. Everything that makes it safe is here: it dies after five wrong
guesses, it dies after ten minutes, it can be spent once, asking for a new one
kills the old one, and only its hash is ever written down. The last of those is
checked by reading the row back and looking for the code in it, because a code
sitting in the file in plain sight would let anybody holding the device reset
the password without ever seeing the email.

No mail is sent. The sending is handed in, so what is tested is the machinery
rather than somebody's internet connection.

Run with:  python3 -m tests.test_reset
"""

import datetime
import sys

from chartered_book.core import auth, db, resets

FAILURES = []
PREFIX = "reset_test_"


def check(label, got, expected):
    if got != expected:
        FAILURES.append("%s: got %r, expected %r" % (label, got, expected))


def refuses(label, run, expect_words=""):
    try:
        run()
        FAILURES.append(label + ": it was allowed")
    except resets.ResetError as exc:
        if expect_words and expect_words.lower() not in str(exc).lower():
            FAILURES.append("%s: refused, but said %r" % (label, str(exc)))


def clean_up(system):
    rows = system.execute("SELECT id FROM users WHERE username LIKE ?",
                          (PREFIX + "%",)).fetchall()
    for row in rows:
        system.execute("DELETE FROM password_resets WHERE user_id = ?", (row["id"],))
    system.execute("DELETE FROM users WHERE username LIKE ?", (PREFIX + "%",))
    system.commit()


def main():
    system = db.open_system()
    clean_up(system)

    who = PREFIX + "shop"
    user_id = auth.create_user(system, who, "the first password", "Shop Owner",
                               "owner", email="counter@example.com",
                               mobile="9800000000")
    system.commit()

    # The code never leaves this test, which is what a real send would do.
    posted = {}

    def pretend_to_send(address, code, row):
        posted["address"] = address
        posted["code"] = code
        posted["who"] = row["username"]

    # --- Where there is nowhere to send it, it says so and sends nothing ---
    nowhere = PREFIX + "nomail"
    auth.create_user(system, nowhere, "another password", "No Address", "operator")
    system.commit()
    refuses("an account with no address",
            lambda: resets.begin(system, nowhere, pretend_to_send),
            "no email address")
    check("and nothing was sent", posted.get("code"), None)

    refuses("a username nobody has",
            lambda: resets.begin(system, PREFIX + "ghost", pretend_to_send),
            "no account here")

    # --- Asking properly ---
    asked = resets.begin(system, who, pretend_to_send)
    check("the code went to the address on the account",
          posted["address"], "counter@example.com")
    check("and to the right person", posted["who"], who)
    check("it is six digits", len(posted["code"]), 6)
    check("all of them digits", posted["code"].isdigit(), True)
    check("the screen is told where it went, and not the whole address",
          asked["sent_to"], "c*****r@example.com")

    # The code itself must not be sitting in the file.
    row = system.execute("SELECT * FROM password_resets WHERE user_id = ?",
                         (user_id,)).fetchone()
    written = " ".join(str(row[k]) for k in row.keys())
    check("the code itself is nowhere in the stored row",
          posted["code"] in written, False)

    # --- The refusals that make it worth anything ---
    refuses("asking again straight away",
            lambda: resets.begin(system, who, pretend_to_send), "wait")

    for n in range(4):
        refuses("wrong guess %d" % (n + 1),
                lambda: resets.check(system, who, "000000")
                if posted["code"] != "000000" else resets.check(system, who, "111111"),
                "wrong")
    # The fifth wrong guess kills it.
    refuses("the fifth wrong guess",
            lambda: resets.check(system, who, "999999"), "")
    refuses("and the real code no longer works after that",
            lambda: resets.check(system, who, posted["code"]),
            "guessed at too many times")

    # --- A fresh one, taken all the way through ---
    system.execute("DELETE FROM password_resets WHERE user_id = ?", (user_id,))
    system.commit()
    resets.begin(system, who, pretend_to_send)
    code = posted["code"]

    refuses("a password the rules refuse",
            lambda: resets.finish(system, who, "not a real ticket", "short"),
            "no longer valid")

    proved = resets.check(system, who, code)
    check("proving the code hands over a ticket", bool(proved["ticket"]), True)

    refuses("a made up ticket",
            lambda: resets.finish(system, who, "made up", "a good new password"),
            "no longer valid")
    refuses("a new password that is too short",
            lambda: resets.finish(system, who, proved["ticket"], "short"),
            "8 characters")

    done = resets.finish(system, who, proved["ticket"], "the second password")
    check("the password is reset", done["username"], who)

    try:
        auth.authenticate(system, who, "the first password")
        FAILURES.append("the old password still worked")
    except auth.AuthError:
        pass
    check("and the new one does",
          auth.authenticate(system, who, "the second password") is not None, True)

    # --- Spent once ---
    refuses("the same ticket a second time",
            lambda: resets.finish(system, who, proved["ticket"], "a third password"),
            "no longer valid")
    refuses("and the same code a second time",
            lambda: resets.check(system, who, code), "ask for a code")

    # --- Running out of time ---
    system.execute("DELETE FROM password_resets WHERE user_id = ?", (user_id,))
    system.commit()
    resets.begin(system, who, pretend_to_send)
    stale = (datetime.datetime.now() - datetime.timedelta(minutes=1)
             ).strftime("%Y-%m-%d %H:%M:%S")
    system.execute("UPDATE password_resets SET expires_at = ? WHERE user_id = ?",
                   (stale, user_id))
    system.commit()
    refuses("a code that has run out",
            lambda: resets.check(system, who, posted["code"]), "run out")

    # --- Everything signed in as that person is signed out by a reset ---
    system.execute("DELETE FROM password_resets WHERE user_id = ?", (user_id,))
    system.commit()
    token = auth.start_session(system, user_id)
    system.commit()
    check("there is a session before the reset",
          auth.load_session(system, token) is not None, True)
    resets.begin(system, who, pretend_to_send)
    proved = resets.check(system, who, posted["code"])
    resets.finish(system, who, proved["ticket"], "the fourth password")
    check("and none afterwards", auth.load_session(system, token), None)

    clean_up(system)

    if FAILURES:
        print("Reset: %d problem%s" % (len(FAILURES), "" if len(FAILURES) == 1 else "s"))
        for line in FAILURES:
            print("  " + line)
        return 1
    print("Reset: a forgotten password can be reset, and only by the person who "
          "gets the code.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
