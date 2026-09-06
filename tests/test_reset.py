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


def check_the_relay_asks_no_permission():
    """
    The relay has to send the kind of request a browser will send unasked.

    A browser will post three content types without checking first. Anything
    else and it sends an OPTIONS ahead of the real request to ask permission.
    Google Apps Script does not answer OPTIONS, so the browser blocks the
    request before it leaves and hands back a bare network error that reads
    like the internet is down. That is exactly what happened: a correctly
    deployed script, and a message saying it could not be reached.

    The body is JSON and the script parses it as JSON either way. Only the
    label on it matters, and only to the browser.
    """
    from chartered_book.core import mailer, webcall

    SAFE = ("text/plain", "application/x-www-form-urlencoded", "multipart/form-data")
    seen = {}

    def pretend_call(url, method="GET", data=None, headers=None, timeout=None):
        seen["headers"] = headers or {}
        seen["data"] = data
        return 200, {"ok": True}

    was = webcall.call_json
    webcall.call_json = pretend_call
    try:
        held = {"relay_url": "https://script.google.com/macros/s/x/exec",
                "relay_secret": mailer.vault.lock(b"a secret",
                                                  mailer._device_key())}
        import base64
        held["relay_secret"] = base64.b64encode(held["relay_secret"]).decode("ascii")
        mailer._send_by_relay(held, "someone@example.com", "subject", "body")
    finally:
        webcall.call_json = was

    sent_as = seen.get("headers", {}).get("Content-Type", "")
    check("the relay sends a type a browser will not stop to ask about",
          any(sent_as.startswith(kind) for kind in SAFE), True)

    # And the script still has to be able to read it.
    import json as _json
    body = _json.loads(seen["data"].decode("utf-8"))
    check("the script still receives the secret", body["secret"], "a secret")
    check("and who it is for", body["to"], "someone@example.com")


def check_it_works_without_ssl():
    """
    The reset screen has to open on a device that cannot send mail at all.

    This is here because of a real failure. The version that runs in a browser
    has no ssl module, the mailer imported it at the top of the file, and so
    the file could not be loaded there at all. Pressing "Forgot your password?"
    asked what that device was able to offer, the question could not be
    answered, and nothing happened. The screen that was supposed to say "this
    build cannot send mail, here is what to do instead" was the very screen the
    missing module took down.

    So ssl and smtplib are taken away here, exactly as the browser has them
    taken away, and what is checked is that the mailer still loads, still
    answers whether it can send, and refuses to send with something a person
    can act on.
    """
    import importlib
    import sys

    class Absent(object):
        """Refuses two modules the way a browser does, and nothing else."""

        gone = ("ssl", "smtplib")

        def find_module(self, name, path=None):
            return self if name in self.gone else None

        def find_spec(self, name, path=None, target=None):
            if name in self.gone:
                raise ImportError("No module named %r" % name)
            return None

        def load_module(self, name):
            raise ImportError("No module named %r" % name)

    keep = {name: sys.modules.pop(name, None) for name in ("ssl", "smtplib")}
    keep["chartered_book.core.mailer"] = sys.modules.pop(
        "chartered_book.core.mailer", None)
    blocker = Absent()
    sys.meta_path.insert(0, blocker)
    try:
        stripped = importlib.import_module("chartered_book.core.mailer")
        check("the mailer loads on a device with no ssl", stripped is not None, True)

        system = db.open_system()
        was = system.execute("SELECT value FROM app_settings WHERE key = ?",
                             (stripped.SETTING_KEY,)).fetchone()
        try:
            # Set up the way a Mac would be, then ask a device with no ssl to
            # use it. That is exactly the browser's situation.
            stripped.save(system, "shop@gmail.com", "an app password")
            check("it knows this device cannot send that way",
                  stripped.settings(system)["can_send"], False)
            try:
                stripped.send(system, "someone@example.com", "x", "y")
                FAILURES.append("it claimed to send mail with no ssl module")
            except stripped.MailError as exc:
                check("and says so in a way somebody can act on",
                      "browser" in str(exc).lower(), True)
                check("and points at the way that does work here",
                      "script" in str(exc).lower(), True)

            # And with the script set up, it stops being a dead end.
            stripped.save(system, relay_url="https://script.google.com/x",
                          relay_secret="a shared secret")
            check("the script makes it able to send from here",
                  stripped.settings(system)["can_send"], True)
            check("and that is the way it would go",
                  stripped.settings(system)["how"], "relay")
        finally:
            system.execute("DELETE FROM app_settings WHERE key = ?",
                           (stripped.SETTING_KEY,))
            if was is not None:
                system.execute("INSERT INTO app_settings (key, value) VALUES (?, ?)",
                               (stripped.SETTING_KEY, was["value"]))
            system.commit()
    except ImportError as exc:
        FAILURES.append("the mailer will not load without ssl: %s" % exc)
    finally:
        sys.meta_path.remove(blocker)
        for name, was in keep.items():
            sys.modules.pop(name, None)
            if was is not None:
                sys.modules[name] = was


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

    check_it_works_without_ssl()
    check_the_relay_asks_no_permission()

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
