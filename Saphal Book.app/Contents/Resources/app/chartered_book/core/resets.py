"""
Getting back in when the password has gone.

A code is sent to the address the account was signed up with, and typing it
back proves the person asking is the person who owns that address. That is the
whole idea, and it is only worth anything if the code is treated properly, so:

  the code is six digits from the system random source, not from a shuffle
  only its hash is stored, salted, the same as a password
  it lasts ten minutes and no longer
  five wrong guesses and it is dead, which is what stops somebody working
    through all million of them
  it can be spent once, and asking for a new one kills the old one
  proving it hands over a ticket, and the ticket is what sets the password,
    so the code is not still lying around usable afterwards

What this does not do is pretend. Where there is no address on the account, or
no way of sending mail from this device, it says so and points at the two ways
back in that do not need a code at all: another owner sets the password, or the
books are restored from a backup. A reset flow that quietly shows the code on
the screen would be worse than having none, because it would look like security
while being none.

A reset changes nothing about the books. They sit on this device unencrypted by
any password, and every entry, company and report is exactly where it was. What
it does change is the key the account uses to lock copies going up to the
server, so copies put there under the old password stop being readable. Those
are stepped over by name when books are brought down, and the sync tests hold
that.
"""

import base64
import datetime
import hashlib
import hmac
import os
import secrets

from . import auth, db

CODE_DIGITS = 6
GOOD_FOR_MINUTES = 10
MAX_TRIES = 5
WAIT_BETWEEN_SECONDS = 60
TICKET_MINUTES = 10


class ResetError(Exception):
    pass


def _now():
    return datetime.datetime.now()


def _stamp(moment):
    return moment.strftime("%Y-%m-%d %H:%M:%S")


def _hash(code, salt):
    """Same treatment a password gets, so the stored row gives nothing away."""
    return base64.b64encode(
        auth._pbkdf2(code.encode("utf-8"), base64.b64decode(salt),
                     auth.ITERATIONS, 32)).decode("ascii")


def mask(address):
    """
    Enough of the address to recognise, not enough to learn.

    Somebody who has forgotten their password should see where the code went so
    they know which inbox to open. Somebody who has stolen the username should
    not be handed the address to go and attack.
    """
    address = (address or "").strip()
    if not address:
        return ""
    if "@" not in address:
        # A phone number. Keep the last two, which is how people recognise it.
        digits = "".join(ch for ch in address if ch.isdigit())
        if len(digits) <= 4:
            return "*" * len(digits)
        return digits[:2] + "*" * (len(digits) - 4) + digits[-2:]
    name, host = address.split("@", 1)
    if len(name) <= 2:
        hidden = name[:1] + "*"
    else:
        hidden = name[0] + "*" * (len(name) - 2) + name[-1]
    return hidden + "@" + host


def _user(system, username):
    row = system.execute(
        "SELECT id, username, full_name, email, mobile, active FROM users "
        "WHERE lower(username) = lower(?)", ((username or "").strip(),)).fetchone()
    return row


def begin(system, username, send):
    """
    Ask for a code.

    `send` is handed (address, code, user) and either sends the mail or raises.
    Nothing about the outcome says whether the username exists, because that
    would turn this screen into a way of finding out who banks here.
    """
    row = _user(system, username)
    if row is None or not row["active"]:
        raise ResetError(
            "There is no account here with that username, or it has been "
            "switched off. Check the spelling, or ask whoever set it up.")

    address = (row["email"] or "").strip()
    if not address:
        raise ResetError(
            "There is no email address on this account, so there is nowhere to "
            "send a code. Somebody with an owner login can set you a new "
            "password under Setup, Users. Add an address afterwards, under Your "
            "account, and this will work next time.")

    recent = system.execute(
        "SELECT asked_at FROM password_resets WHERE user_id = ? "
        "ORDER BY id DESC LIMIT 1", (row["id"],)).fetchone()
    if recent is not None:
        try:
            asked = datetime.datetime.strptime(recent["asked_at"], "%Y-%m-%d %H:%M:%S")
        except ValueError:
            asked = None
        if asked is not None:
            waited = (_now() - asked).total_seconds()
            if 0 <= waited < WAIT_BETWEEN_SECONDS:
                raise ResetError(
                    "A code was sent a moment ago. Wait %d seconds before asking "
                    "for another one, and check the spam folder in the meantime."
                    % int(WAIT_BETWEEN_SECONDS - waited))

    code = "".join(str(secrets.randbelow(10)) for _ in range(CODE_DIGITS))
    salt = base64.b64encode(os.urandom(auth.SALT_BYTES)).decode("ascii")

    # Sent before it is written down. If the mail will not go, nothing is
    # recorded, so the old code stays valid and the waiting period does not
    # start on a code nobody ever received.
    send(address, code, row)

    # Asking for a new one puts the old one beyond use.
    system.execute("DELETE FROM password_resets WHERE user_id = ?", (row["id"],))
    system.execute(
        "INSERT INTO password_resets (user_id, code_hash, salt, sent_to, "
        "asked_at, expires_at) VALUES (?, ?, ?, ?, ?, ?)",
        (row["id"], _hash(code, salt), salt, address, _stamp(_now()),
         _stamp(_now() + datetime.timedelta(minutes=GOOD_FOR_MINUTES))))
    system.commit()
    auth._record_login(system, row["username"], "reset requested", mask(address))
    system.commit()

    return {"sent_to": mask(address), "good_for_minutes": GOOD_FOR_MINUTES}


def check(system, username, code):
    """Prove the code, and get the ticket that the new password is set with."""
    row = _user(system, username)
    if row is None:
        raise ResetError("That code is wrong or has run out.")

    live = system.execute(
        "SELECT * FROM password_resets WHERE user_id = ? AND used_at = '' "
        "ORDER BY id DESC LIMIT 1", (row["id"],)).fetchone()
    if live is None:
        raise ResetError("Ask for a code first.")

    if _stamp(_now()) > live["expires_at"]:
        system.execute("DELETE FROM password_resets WHERE id = ?", (live["id"],))
        system.commit()
        raise ResetError("That code has run out. Ask for a new one.")

    if live["tries"] >= MAX_TRIES:
        system.execute("DELETE FROM password_resets WHERE id = ?", (live["id"],))
        system.commit()
        raise ResetError(
            "That code has been guessed at too many times and is now dead. "
            "Ask for a new one.")

    given = "".join(ch for ch in (code or "") if ch.isdigit())
    # Constant time, so how long this takes says nothing about how close the
    # guess was.
    if not hmac.compare_digest(_hash(given, live["salt"]), live["code_hash"]):
        system.execute("UPDATE password_resets SET tries = tries + 1 WHERE id = ?",
                       (live["id"],))
        system.commit()
        left = MAX_TRIES - (live["tries"] + 1)
        if left <= 0:
            raise ResetError("That code is wrong, and there are no more tries. "
                             "Ask for a new one.")
        raise ResetError("That code is wrong. %d %s left."
                         % (left, "try" if left == 1 else "tries"))

    ticket = secrets.token_urlsafe(24)
    system.execute(
        "UPDATE password_resets SET ticket = ?, expires_at = ?, tries = 0 "
        "WHERE id = ?",
        (ticket, _stamp(_now() + datetime.timedelta(minutes=TICKET_MINUTES)),
         live["id"]))
    system.commit()
    return {"ticket": ticket}


def finish(system, username, ticket, new_password):
    """Set the new password. The ticket is spent whether this works or not."""
    row = _user(system, username)
    if row is None:
        raise ResetError("That reset is no longer valid. Start again.")

    live = system.execute(
        "SELECT * FROM password_resets WHERE user_id = ? AND used_at = '' "
        "AND ticket <> '' ORDER BY id DESC LIMIT 1", (row["id"],)).fetchone()
    if live is None or not hmac.compare_digest(str(live["ticket"]), str(ticket or "")):
        raise ResetError("That reset is no longer valid. Start again.")
    if _stamp(_now()) > live["expires_at"]:
        system.execute("DELETE FROM password_resets WHERE id = ?", (live["id"],))
        system.commit()
        raise ResetError("That took too long. Ask for a new code.")

    problems = auth.password_problems(new_password)
    if problems:
        # The ticket survives a password the rules refuse, because the person
        # has already proved who they are and should get to try a better one.
        raise ResetError(" ".join(problems))

    auth.set_password(system, row["id"], new_password)
    system.execute("UPDATE password_resets SET used_at = ?, ticket = '' WHERE id = ?",
                   (_stamp(_now()), live["id"]))
    # Everything that was signed in as this person stops being signed in, which
    # is the point: if somebody else was in there, they are out now.
    system.execute("DELETE FROM sessions WHERE user_id = ?", (row["id"],))
    system.commit()
    auth._record_login(system, row["username"], "password reset", "by emailed code")
    system.commit()
    return {"username": row["username"]}


def tidy(system):
    """Drop codes nobody came back for."""
    system.execute("DELETE FROM password_resets WHERE expires_at < ? AND ticket = ''",
                   (_stamp(_now() - datetime.timedelta(hours=1)),))
    system.commit()
