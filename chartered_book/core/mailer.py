"""
Sending one email from this device.

There is exactly one thing this is for: putting a six digit code in front of
somebody who has forgotten their password. It is not a mailing list and it
never will be.

It goes out through the account holder's own mail provider, over SMTP, using
nothing but the standard library. No service is signed up for and nothing is
paid, which is the rule the whole of Saphal Book is built to. The cost is that
the provider has to be told about it once, in Setup, and that is one screen and
an app password.

Two honest limits, both said out loud rather than discovered:

The app password is kept locked rather than in plain text, but it is locked
with a key this device can work out on its own, because there is nobody to type
a password at the moment a reset code needs sending. Somebody holding the
device and willing to read the code could get at it. That is worth knowing
before putting a real mail password in. Use an app password, which is what
Gmail hands out for exactly this and which can be withdrawn on its own without
touching the account.

And SMTP needs a socket. The Mac and Windows apps have one. The version that
runs inside a browser does not, and cannot be given one, so a reset code cannot
be sent from a browser tab. That is said on the screen at the point it matters,
rather than left to fail.
"""

import base64
import datetime
import email.utils
import json
import os
from email.message import EmailMessage

from . import vault

# smtplib and ssl are fetched at the moment of sending, not here.
#
# The browser build has no ssl module at all, and importing this file used to
# fail there before a single line of it ran. That took the reset screen down
# with it: pressing "Forgot your password?" asked what this device could offer,
# the question could not even be loaded, and nothing appeared. Nothing in this
# file except the sending itself needs either one, so nothing except the
# sending asks for them.

SETTING_KEY = "outgoing_mail"
CONNECT_SECONDS = 20

# The three that cover almost everybody here. Anything else is typed in.
KNOWN_PROVIDERS = {
    "gmail.com": {"host": "smtp.gmail.com", "port": 587,
                  "note": "Gmail needs an app password, not your ordinary one. "
                          "Make one at myaccount.google.com under Security, "
                          "then two step verification, then App passwords."},
    "outlook.com": {"host": "smtp-mail.outlook.com", "port": 587, "note": ""},
    "hotmail.com": {"host": "smtp-mail.outlook.com", "port": 587, "note": ""},
    "yahoo.com": {"host": "smtp.mail.yahoo.com", "port": 587,
                  "note": "Yahoo needs an app password."},
}


class MailError(Exception):
    pass


def _smtp():
    """The two modules sending needs, or None where this build has no such thing."""
    try:
        import smtplib
        import ssl
        return smtplib, ssl
    except ImportError:
        return None


def can_send():
    """
    Whether this build can send mail at all.

    Asked rather than assumed. The browser build has no ssl module, so the
    answer there is no, and the screen can say so before somebody types their
    mail password in for nothing.
    """
    if os.environ.get("SAPHAL_NO_SMTP"):
        return False
    return _smtp() is not None


def suggest(address):
    """What to fill the server boxes in with, from the address alone."""
    host = (address or "").split("@")[-1].strip().lower()
    return dict(KNOWN_PROVIDERS.get(host, {"host": "", "port": 587, "note": ""}))


def _device_key():
    """
    The key the stored mail password is locked with.

    Worked out from something that stays with this installation, because the
    code has to go out when nobody is signed in and so nobody is there to type
    anything. This is obfuscation with a real cipher behind it, not a secret
    kept from somebody holding the device, and the module docstring says so.
    """
    from . import db
    marker = os.path.join(db.DATA_DIR, ".mail-key")
    if os.path.exists(marker):
        with open(marker, "rb") as handle:
            seed = handle.read().strip()
        if len(seed) >= 32:
            return base64.b64encode(seed).decode("ascii")
    seed = os.urandom(48)
    with open(marker, "wb") as handle:
        handle.write(seed)
    try:
        os.chmod(marker, 0o600)
    except OSError:
        pass
    return base64.b64encode(seed).decode("ascii")


def settings(system):
    """What is set up, with the password left out."""
    row = system.execute("SELECT value FROM app_settings WHERE key = ?",
                         (SETTING_KEY,)).fetchone()
    if row is None:
        return {"configured": False, "address": "", "host": "", "port": 587,
                "from_name": "Saphal Book", "can_send": can_send()}
    held = json.loads(row["value"])
    return {"configured": bool(held.get("address")), "address": held.get("address", ""),
            "host": held.get("host", ""), "port": held.get("port", 587),
            "from_name": held.get("from_name", "Saphal Book"),
            "can_send": can_send()}


def save(system, address, password, host="", port=587, from_name="Saphal Book"):
    """Keep the details. An empty password leaves the stored one alone."""
    address = (address or "").strip()
    if not address or "@" not in address:
        raise MailError("Put in the full email address it will send from.")
    guess = suggest(address)
    host = (host or "").strip() or guess.get("host", "")
    if not host:
        raise MailError("Put in the outgoing mail server for that address.")
    try:
        port = int(port or 587)
    except (TypeError, ValueError):
        raise MailError("The port has to be a number, usually 587.")

    existing = system.execute("SELECT value FROM app_settings WHERE key = ?",
                              (SETTING_KEY,)).fetchone()
    locked = json.loads(existing["value"]).get("locked", "") if existing else ""
    if password:
        locked = vault.lock(password.encode("utf-8"), _device_key())
        if isinstance(locked, bytes):
            locked = base64.b64encode(locked).decode("ascii")
    if not locked:
        raise MailError("Put in the app password for that address.")

    system.execute(
        "INSERT INTO app_settings (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (SETTING_KEY, json.dumps({"address": address, "host": host, "port": port,
                                  "from_name": (from_name or "Saphal Book").strip(),
                                  "locked": locked})))
    system.commit()
    return settings(system)


def forget(system):
    system.execute("DELETE FROM app_settings WHERE key = ?", (SETTING_KEY,))
    system.commit()


def _held(system):
    row = system.execute("SELECT value FROM app_settings WHERE key = ?",
                         (SETTING_KEY,)).fetchone()
    if row is None:
        raise MailError(
            "No email has been set up to send from, so there is nowhere for a "
            "code to come from. Set one up under Setup, Email for codes.")
    held = json.loads(row["value"])
    locked = held.get("locked", "")
    try:
        blob = base64.b64decode(locked) if isinstance(locked, str) else locked
        held["password"] = vault.unlock(blob, _device_key()).decode("utf-8")
    except Exception:
        raise MailError(
            "The stored mail password could not be read on this device. Put it "
            "in again under Setup, Email for codes.")
    return held


def send(system, to_address, subject, body):
    """Send one message, or say plainly why it did not go."""
    modules = _smtp()
    if modules is None or os.environ.get("SAPHAL_NO_SMTP"):
        raise MailError(
            "This is the version that runs inside a browser, and a browser tab "
            "cannot open a mail connection. Do the reset from the Saphal Book "
            "app on a Mac or a Windows computer, or ask somebody with an owner "
            "login to set the password under Setup, Users.")
    smtplib, ssl = modules

    held = _held(system)
    note = EmailMessage()
    note["From"] = email.utils.formataddr(
        (held.get("from_name") or "Saphal Book", held["address"]))
    note["To"] = to_address
    note["Subject"] = subject
    note["Date"] = email.utils.formatdate(localtime=True)
    note["Message-ID"] = email.utils.make_msgid(domain="saphalbook.com")
    note.set_content(body)

    port = int(held.get("port") or 587)
    context = ssl.create_default_context()
    try:
        # 465 is TLS from the first byte. 587 starts in the clear and is lifted
        # into TLS by STARTTLS. Getting these the wrong way round sends the mail
        # password across the wire in the open, so the two are kept apart here
        # rather than hoped about.
        if port == 465:
            opened = smtplib.SMTP_SSL(held["host"], port, timeout=CONNECT_SECONDS,
                                      context=context)
        else:
            opened = smtplib.SMTP(held["host"], port, timeout=CONNECT_SECONDS)
        with opened as server:
            server.ehlo()
            if port != 465:
                server.starttls(context=context)
                server.ehlo()
            server.login(held["address"], held["password"])
            server.send_message(note)
    # Narrowest first, and OSError last, because a TLS failure is an OSError
    # and would otherwise be reported as a server nobody could reach, which
    # would have somebody checking their internet instead of their port.
    except smtplib.SMTPAuthenticationError:
        raise MailError(
            "The mail provider refused that address and password. If it is "
            "Gmail, it has to be an app password, not the password you sign in "
            "to Gmail with.")
    except smtplib.SMTPNotSupportedError:
        raise MailError(
            "That server will not take an encrypted connection on port %d. The "
            "mail password is not being sent in the open, so nothing was sent. "
            "Try port 587, or 465." % port)
    except ssl.SSLError as exc:
        raise MailError("The encrypted connection to the mail server failed "
                        "(%s). Check the server name and the port." % exc)
    except smtplib.SMTPException as exc:
        raise MailError("The mail did not go: %s" % exc)
    except OSError as exc:
        raise MailError("Could not reach the mail server (%s). Check the "
                        "internet connection and the server name." % exc)
    return True


def send_test(system, to_address):
    return send(system, to_address, "Saphal Book test",
                "This is the test message from Saphal Book.\n\n"
                "Getting it means reset codes will reach this address.\n")


def send_code(system, address, code, user, minutes=10):
    """The message somebody actually reads at the moment they are locked out."""
    who = (user["full_name"] or user["username"]) if user else ""
    body = (
        ("Hello %s,\n\n" % who) if who else "Hello,\n\n"
    ) + (
        "Your Saphal Book reset code is:\n\n"
        "    %s\n\n"
        "Type it into the screen that asked for it. It works for %d minutes and "
        "once only.\n\n"
        "If you did not ask to reset your password, you can ignore this. Nobody "
        "can get into your books with this code alone, and your password has not "
        "been changed.\n\n"
        "Sent %s\n"
        % (code, minutes,
           datetime.datetime.now().strftime("%d %B %Y at %I:%M %p"))
    )
    return send(system, address, "Saphal Book reset code: %s" % code, body)
