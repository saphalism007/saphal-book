"""
One username and one password, and the same books on every device.

This is the promise the whole account exists to keep, and it was not being
kept. A password changed on one device stayed on that device. The books had to
be fetched by pressing a button, on a screen with a second sign in form that
then refused the password. A laptop opened and a phone did not.

So this walks several devices through it against a pretend server, using the
real connection code, and checks what a person would see:

  a login made before there was an account gets one by signing in
  a second device signs in and the companies are simply there
  a forgotten password reset on one device opens every other device too
  a password changed properly moves the account, and the old one stops
  a device left on an old password does not drag the account back to it

Each device is its own folder of books. Nothing here goes near real ones.

Run with:  python3 -m tests.test_one_login
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile

FAILURES = []
NAME = "saphaltest"
FIRST, SECOND, THIRD = "the first pass word", "the second pass word", "the third pass word"


def check(label, got, expected):
    if got != expected:
        FAILURES.append("%s: got %r, expected %r" % (label, got, expected))


class Device(object):
    def __init__(self, root, name):
        self.folder = os.path.join(root, name)
        os.makedirs(self.folder)
        self.server = os.path.join(root, "server.json")

    def does(self, *steps):
        env = dict(os.environ, SAPHAL_BOOK_DATA=self.folder)
        done = subprocess.run(
            [sys.executable, "-m", "tests.pretend_server", self.server,
             json.dumps(steps)], env=env, capture_output=True, text=True)
        if done.returncode != 0:
            raise RuntimeError(done.stderr[-1500:])
        return json.loads(done.stdout.strip().splitlines()[-1])

    def signs_in(self, password, then=()):
        return self.does(["post", "/api/login", {"username": NAME, "password": password}],
                         ["post", "/api/cloud/fetch-waiting"],
                         ["post", "/api/cloud/auto"], *then)


def main():
    root = tempfile.mkdtemp(prefix="saphal_one_login_")
    try:
        laptop, phone, tablet = (Device(root, "laptop"), Device(root, "phone"),
                                 Device(root, "tablet"))

        # --- A login from before there was an account ---
        laptop.does(["local-user", NAME, FIRST],
                    ["books", "shop_one", "Shop One", "2026-09-01 10:00:00", "first entries"],
                    ["books", "shop_two", "Shop Two", "2026-09-01 11:00:00", "second shop"])
        got = laptop.signs_in(FIRST, [["here"]])
        check("signing in on the laptop works", got[0]["status"], 200)
        check("and gives the login an account without being asked",
              got[0]["payload"].get("account"), True)
        check("and the books go up by themselves",
              sorted(got[2]["payload"].get("sent", [])), ["Shop One", "Shop Two"])

        # --- A second device: sign in, and they are there ---
        got = phone.signs_in(FIRST, [["here"]])
        check("the phone signs in with the same name and password",
              got[0]["status"], 200)
        check("and both companies are there, with nothing pressed",
              got[-1], {"shop_one": "first entries", "shop_two": "second shop"})

        # --- The wrong password is still the wrong password ---
        got = phone.does(["post", "/api/login", {"username": NAME, "password": "not this one"}])
        check("a wrong password is refused", got[0]["status"], 401)

        # --- Forgotten, and reset on the laptop, which has lost touch ---
        laptop.does(["lose-touch"],
                    ["post", "/api/reset/here", {"username": NAME, "new_password": SECOND}])
        got = laptop.signs_in(SECOND, [["here"]])
        check("the laptop opens with the new password", got[0]["status"], 200)
        check("and is joined to the account again by doing so",
              got[0]["payload"].get("account"), True)
        check("its books are still its books",
              got[-1], {"shop_one": "first entries", "shop_two": "second shop"})

        # This is the one that was failing: opened on the laptop, not the phone.
        got = phone.signs_in(SECOND, [["here"]])
        check("the phone opens with the new password too", got[0]["status"], 200)
        check("and is on the account", got[0]["payload"].get("account"), True)
        check("with the same books",
              got[-1], {"shop_one": "first entries", "shop_two": "second shop"})

        # And a device that has never been used at all.
        got = tablet.signs_in(SECOND, [["here"]])
        check("a brand new tablet opens with it", got[0]["status"], 200)
        check("and the companies arrive on it by themselves",
              got[-1], {"shop_one": "first entries", "shop_two": "second shop"})

        # --- Work done on one device reaches the others ---
        tablet.does(["books", "shop_one", "Shop One", "2026-10-01 09:00:00",
                     "entered on the tablet"])
        tablet.signs_in(SECOND)
        got = phone.signs_in(SECOND, [["here"]])
        check("what was entered on the tablet is on the phone",
              got[-1].get("shop_one"), "entered on the tablet")

        # --- Changed properly, while signed in ---
        got = phone.does(["post", "/api/login", {"username": NAME, "password": SECOND}],
                         ["post", "/api/change-password",
                          {"current_password": SECOND, "new_password": THIRD}])
        check("changing the password says the account moved with it",
              got[1]["payload"].get("account", {}).get("state"), "moved")
        got = tablet.signs_in(THIRD, [["here"]])
        check("the tablet opens with the changed password", got[0]["status"], 200)
        check("and still has everything",
              got[-1], {"shop_one": "entered on the tablet", "shop_two": "second shop"})

        # --- A device left behind does not drag the account back ---
        got = laptop.does(["post", "/api/login", {"username": NAME, "password": SECOND}])
        check("the laptop still opens on the password it knows",
              got[0]["status"], 200)
        check("is told the password changed elsewhere",
              got[0]["payload"].get("account_older"), True)
        got = tablet.signs_in(THIRD)
        check("and the account still answers to the new one", got[0]["status"], 200)
        check("on the account", got[0]["payload"].get("account"), True)
        got = laptop.signs_in(THIRD, [["here"]])
        check("the laptop comes level as soon as the new one is typed",
              got[-1], {"shop_one": "entered on the tablet", "shop_two": "second shop"})
    finally:
        shutil.rmtree(root, ignore_errors=True)

    if FAILURES:
        print("One login: %d problem%s" % (len(FAILURES), "" if len(FAILURES) == 1 else "s"))
        for line in FAILURES:
            print("  " + line)
        return 1
    print("One login: the same username and password open the same books on every device.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
