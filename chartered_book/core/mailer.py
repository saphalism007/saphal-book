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

There are two ways of getting the message out, and which one is used depends on
what the device can do.

SMTP needs a socket. The Mac and Windows apps have one, so there it talks to
the provider directly and that is the end of it.

A browser tab has no socket and cannot be given one, which made the reset
useless on saphalbook.com, which is where most people actually use this. So
there is a second way: a small script the account holder puts in their own
Google account, which answers on an ordinary web address. A browser can reach
that, and it sends the mail from their own Gmail. It is free, it belongs to
them, and nothing is signed up for. RELAY_SCRIPT below is the whole of it, and
the app shows it on screen ready to copy.

The relay is used wherever it is set up, browser or not, because a thing that
works the same everywhere is worth more than a thing that works two different
ways.
"""

# What the account holder pastes into script.google.com. It is short on purpose:
# it is going to be read by somebody deciding whether to trust it with their
# Gmail, and a page of code nobody reads is how people get talked into pasting
# something else. It sends one message and answers nothing back but ok.
RELAY_SCRIPT = """\
function doPost(e) {
  var SECRET = "PUT-YOUR-SECRET-HERE";
  var body = JSON.parse(e.postData.contents);
  if (body.secret !== SECRET) {
    return ContentService.createTextOutput(JSON.stringify({error: "no"}))
      .setMimeType(ContentService.MimeType.JSON);
  }
  MailApp.sendEmail(body.to, body.subject, body.body);
  return ContentService.createTextOutput(JSON.stringify({ok: true}))
    .setMimeType(ContentService.MimeType.JSON);
}
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
                "from_name": "Saphal Book", "relay_url": "", "relay_set": False,
                "how": "nothing", "can_send": False, "smtp_here": _smtp() is not None}
    held = json.loads(row["value"])
    relay = bool(held.get("relay_url") and held.get("relay_secret"))
    smtp = bool(held.get("address") and held.get("locked"))
    return {"configured": relay or smtp,
            "address": held.get("address", ""),
            "host": held.get("host", ""), "port": held.get("port", 587),
            "from_name": held.get("from_name", "Saphal Book"),
            "relay_url": held.get("relay_url", ""), "relay_set": relay,
            # What this device would actually use, said plainly, because "set
            # up" and "able to send from here" are not the same thing and the
            # difference is the whole of the browser problem.
            "how": "relay" if relay else ("smtp" if smtp else "nothing"),
            "can_send": relay or (smtp and _smtp() is not None),
            "smtp_here": _smtp() is not None}


def save(system, address="", password="", host="", port=587,
         from_name="Saphal Book", relay_url="", relay_secret=""):
    """
    Keep the details. An empty password or secret leaves the stored one alone.

    Either way of sending is enough on its own, so this refuses only when
    neither has been filled in.
    """
    existing = system.execute("SELECT value FROM app_settings WHERE key = ?",
                              (SETTING_KEY,)).fetchone()
    held = json.loads(existing["value"]) if existing else {}

    address = (address or "").strip()
    relay_url = (relay_url or "").strip()

    if relay_url and not relay_url.startswith("https://"):
        raise MailError("The web address for the script has to start with "
                        "https://, so the code cannot be read on the way.")

    locked = held.get("locked", "")
    if password:
        blob = vault.lock(password.encode("utf-8"), _device_key())
        locked = base64.b64encode(blob).decode("ascii") if isinstance(blob, bytes) else blob

    secret = held.get("relay_secret", "")
    if relay_secret:
        blob = vault.lock(relay_secret.encode("utf-8"), _device_key())
        secret = base64.b64encode(blob).decode("ascii") if isinstance(blob, bytes) else blob

    if address:
        if "@" not in address:
            raise MailError("Put in the full email address it will send from.")
        host = (host or "").strip() or suggest(address).get("host", "")
        if not host:
            raise MailError("Put in the outgoing mail server for that address.")
        try:
            port = int(port or 587)
        except (TypeError, ValueError):
            raise MailError("The port has to be a number, usually 587.")
        if not locked:
            raise MailError("Put in the app password for that address.")
    else:
        host, port = held.get("host", ""), held.get("port", 587)

    if relay_url and not secret:
        raise MailError("Put in the secret you wrote into the script, so nobody "
                        "else can use it to send mail.")

    if not (relay_url and secret) and not (address and locked):
        raise MailError("Fill in one of the two ways of sending: the script "
                        "address, or an email address and its app password.")

    system.execute(
        "INSERT INTO app_settings (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (SETTING_KEY, json.dumps({"address": address, "host": host, "port": port,
                                  "from_name": (from_name or "Saphal Book").strip(),
                                  "locked": locked, "relay_url": relay_url,
                                  "relay_secret": secret})))
    system.commit()
    return settings(system)


def forget(system):
    system.execute("DELETE FROM app_settings WHERE key = ?", (SETTING_KEY,))
    system.commit()


def _unlock(value, what):
    try:
        blob = base64.b64decode(value) if isinstance(value, str) else value
        return vault.unlock(blob, _device_key()).decode("utf-8")
    except Exception:
        raise MailError(
            "The stored %s could not be read on this device. Put it in again "
            "under Setup, Email for codes." % what)


def _held(system):
    row = system.execute("SELECT value FROM app_settings WHERE key = ?",
                         (SETTING_KEY,)).fetchone()
    if row is None:
        raise MailError(
            "No email has been set up to send from, so there is nowhere for a "
            "code to come from. Set one up under Setup, Email for codes.")
    return json.loads(row["value"])


def _send_by_relay(held, to_address, subject, body):
    """
    Hand the message to the account holder's own script, over https.

    This is the way that works in a browser, because it is an ordinary web
    request and needs no socket of its own. The secret is what stops a stranger
    who finds the address using it to send mail as them.
    """
    from . import webcall

    url = held.get("relay_url", "")
    secret = _unlock(held.get("relay_secret", ""), "secret for the script")
    payload = json.dumps({"secret": secret, "to": to_address,
                          "subject": subject, "body": body}).encode("utf-8")
    try:
        status, detail = webcall.call_json(
            url, "POST", payload, {"Content-Type": "application/json"})
    except Exception as exc:
        raise MailError("Could not reach the script at that address (%s). Check "
                        "it is deployed and set to allow anyone." % exc)

    if status >= 400:
        raise MailError("The script refused the message (%s). Check it is "
                        "deployed as a web app that anyone can reach." % status)
    if isinstance(detail, dict) and detail.get("error"):
        raise MailError("The script refused the message. The secret here and "
                        "the one written into the script are not the same.")
    # A script that has not been authorised answers with Google's sign in page
    # rather than an error, so an answer that is not ours is treated as one.
    if isinstance(detail, dict) and detail.get("message") \
            and "ok" not in str(detail.get("message")).lower():
        raise MailError("That address answered with a Google page rather than "
                        "the script. Open the script once in your browser and "
                        "allow it, then deploy it again.")
    return True


def send(system, to_address, subject, body):
    """Send one message, or say plainly why it did not go."""
    held = _held(system)

    # The relay first, because it is the one that works everywhere.
    if held.get("relay_url") and held.get("relay_secret"):
        return _send_by_relay(held, to_address, subject, body)

    modules = _smtp()
    if modules is None or os.environ.get("SAPHAL_NO_SMTP"):
        raise MailError(
            "This is Saphal Book running inside a browser, which has no way of "
            "opening a mail connection of its own. An owner can set up the "
            "small Google script under Setup, Email for codes, and then this "
            "works here too. Until then, do the reset from the app on a Mac or "
            "Windows computer, or ask an owner to set the password under "
            "Setup, Users.")
    smtplib, ssl = modules
    note = EmailMessage()
    held["password"] = _unlock(held.get("locked", ""), "mail password")
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
