"""
Users, passwords and sessions.

Passwords are never stored. What is stored is a PBKDF2 HMAC SHA256 hash with a
per user random salt and a high iteration count, which is the same family of
scheme a bank login uses. Comparison is done in constant time so that the
duration of a failed login gives nothing away.

This runs entirely on the machine in front of you. Nothing is sent anywhere and
nothing is paid for.
"""

import base64
import hashlib
import hmac
import os
import struct
import secrets
import datetime

from . import db

ITERATIONS = 240000
SALT_BYTES = 16
SESSION_HOURS = 12
MAX_FAILED = 8
LOCK_MINUTES = 15

# Higher number means more power. Used for every permission check.
ROLES = {
    "owner": 40,       # everything, including closing a year and managing users
    "accountant": 30,  # post, edit and cancel vouchers, run every report
    "operator": 20,    # enter day to day vouchers, no cancelling, no masters delete
    "viewer": 10,      # read only
}

ROLE_LABELS = {
    "owner": "Owner",
    "accountant": "Accountant",
    "operator": "Operator",
    "viewer": "View only",
}

# What each action needs.
PERMISSIONS = {
    "voucher.create": 20,
    "voucher.edit": 20,
    "voucher.cancel": 30,
    "voucher.delete": 40,
    "voucher.backdate": 30,
    "master.create": 20,
    "master.edit": 20,
    "master.delete": 30,
    "report.view": 10,
    "report.export": 10,
    "opening.edit": 30,
    "year.close": 40,
    "company.edit": 40,
    "company.create": 40,
    "user.manage": 40,
    "backup.run": 20,
    "backup.restore": 40,
    "audit.view": 30,
}


class AuthError(Exception):
    """Raised when a login or a permission check fails."""


# Python compiled for the browser does not always carry the fast key
# stretching routine, so there is a plain one to fall back on. It is the same
# algorithm, PBKDF2 with HMAC SHA256, just written out rather than called into
# C. Because it is slower, fewer rounds are used there. The number of rounds is
# stored with every password, so one made on a phone still checks out on a
# computer and the other way round.
HAS_FAST_KDF = hasattr(hashlib, "pbkdf2_hmac")
SLOW_ITERATIONS = 20000


def default_iterations():
    return ITERATIONS if HAS_FAST_KDF else SLOW_ITERATIONS


def _pbkdf2(password_bytes, salt, iterations, length=32):
    """PBKDF2 with HMAC SHA256, written out for where the built in one is absent."""
    output = b""
    block = 1
    while len(output) < length:
        current = hmac.new(password_bytes, salt + struct.pack(">I", block),
                           hashlib.sha256).digest()
        accumulated = bytearray(current)
        for _ in range(iterations - 1):
            current = hmac.new(password_bytes, current, hashlib.sha256).digest()
            for index in range(len(accumulated)):
                accumulated[index] ^= current[index]
        output += bytes(accumulated)
        block += 1
    return output[:length]


def _derive(password_bytes, salt, iterations):
    if HAS_FAST_KDF:
        return hashlib.pbkdf2_hmac("sha256", password_bytes, salt, iterations)
    return _pbkdf2(password_bytes, salt, iterations)


def hash_password(password, salt=None, iterations=None):
    if iterations is None:
        iterations = default_iterations()
    if salt is None:
        salt = os.urandom(SALT_BYTES)
    if isinstance(salt, str):
        salt = base64.b64decode(salt)
    digest = _derive(password.encode("utf-8"), salt, iterations)
    return (base64.b64encode(digest).decode("ascii"),
            base64.b64encode(salt).decode("ascii"),
            iterations)


def verify_password(password, stored_hash, stored_salt, iterations):
    candidate, _, _ = hash_password(password, stored_salt, iterations)
    return hmac.compare_digest(candidate, stored_hash)


def password_problems(password):
    """
    Return a list of reasons a password is not acceptable, empty if it is fine.
    The rules are deliberately modest, because a rule nobody can follow leads to
    a password written on the wall behind the counter.
    """
    problems = []
    if len(password) < 8:
        problems.append("Use at least 8 characters.")
    if password.isdigit():
        problems.append("Do not use digits alone.")
    if password.lower() in ("password", "12345678", "nepal123", "admin123", "qwertyui"):
        problems.append("That password is too common.")
    return problems


def create_user(conn, username, password, full_name="", role="operator", must_change=0,
                email="", mobile=""):
    username = str(username).strip()
    if not username:
        raise AuthError("Username cannot be blank.")
    if role not in ROLES:
        raise AuthError("Unknown role %r" % role)
    problems = password_problems(password)
    if problems:
        raise AuthError(" ".join(problems))
    existing = conn.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
    if existing:
        raise AuthError("A user named %s already exists." % username)
    digest, salt, iters = hash_password(password)
    cur = conn.execute(
        """INSERT INTO users (username, full_name, password_hash, password_salt,
                              iterations, role, active, must_change, created_at,
                              email, mobile)
           VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?)""",
        (username, full_name or username, digest, salt, iters, role, must_change,
         db.now_stamp(), (email or "").strip()[:200], (mobile or "").strip()[:40]))
    return cur.lastrowid


def set_password(conn, user_id, password):
    problems = password_problems(password)
    if problems:
        raise AuthError(" ".join(problems))
    digest, salt, iters = hash_password(password)
    conn.execute("""UPDATE users SET password_hash = ?, password_salt = ?, iterations = ?,
                                     must_change = 0, failed_attempts = 0, locked_until = NULL
                    WHERE id = ?""", (digest, salt, iters, user_id))


def set_details(conn, user_id, email=None, mobile=None, full_name=None):
    """Change how to reach somebody. Nothing here touches their password."""
    sets, args = [], []
    if email is not None:
        sets.append("email = ?")
        args.append(str(email).strip()[:200])
    if mobile is not None:
        sets.append("mobile = ?")
        args.append(str(mobile).strip()[:40])
    if full_name is not None:
        sets.append("full_name = ?")
        args.append(str(full_name).strip()[:120])
    if not sets:
        return False
    args.append(user_id)
    conn.execute("UPDATE users SET %s WHERE id = ?" % ", ".join(sets), args)
    return True


def _record_login(conn, username, outcome, note=""):
    conn.execute("INSERT INTO login_history (username, at, outcome, note) VALUES (?, ?, ?, ?)",
                 (username, db.now_stamp(), outcome, note))


def authenticate(conn, username, password):
    """Check a username and password, returning the user row."""
    username = str(username).strip()
    row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    if row is None:
        # Spend roughly the same time as a real check so a missing username and a
        # wrong password cannot be told apart by timing.
        hash_password(password)
        _record_login(conn, username, "failed", "no such user")
        raise AuthError("Username or password is not correct.")
    if not row["active"]:
        _record_login(conn, username, "blocked", "account disabled")
        raise AuthError("This account has been disabled.")
    locked = row["locked_until"]
    if locked and locked > db.now_stamp():
        _record_login(conn, username, "blocked", "locked until %s" % locked)
        raise AuthError("Too many failed attempts. Try again after %s." % locked)
    if not verify_password(password, row["password_hash"], row["password_salt"], row["iterations"]):
        attempts = row["failed_attempts"] + 1
        lock_to = None
        if attempts >= MAX_FAILED:
            lock_to = (datetime.datetime.now() + datetime.timedelta(minutes=LOCK_MINUTES)
                       ).replace(microsecond=0).isoformat(sep=" ")
            attempts = 0
        conn.execute("UPDATE users SET failed_attempts = ?, locked_until = ? WHERE id = ?",
                     (attempts, lock_to, row["id"]))
        _record_login(conn, username, "failed", "wrong password")
        raise AuthError("Username or password is not correct.")
    conn.execute("""UPDATE users SET failed_attempts = 0, locked_until = NULL, last_login_at = ?
                    WHERE id = ?""", (db.now_stamp(), row["id"]))
    _record_login(conn, username, "success")
    return row


def start_session(conn, user_id, company_id=None, hours=SESSION_HOURS):
    token = secrets.token_urlsafe(32)
    now = datetime.datetime.now().replace(microsecond=0)
    expires = now + datetime.timedelta(hours=hours)
    conn.execute("""INSERT INTO sessions (token, user_id, company_id, created_at, expires_at, last_seen)
                    VALUES (?, ?, ?, ?, ?, ?)""",
                 (token, user_id, company_id, now.isoformat(sep=" "),
                  expires.isoformat(sep=" "), now.isoformat(sep=" ")))
    return token


def load_session(conn, token):
    """Return a dictionary describing the signed in user, or None."""
    if not token:
        return None
    row = conn.execute("""SELECT s.token, s.user_id, s.company_id, s.expires_at,
                                 u.username, u.full_name, u.role, u.active, u.must_change
                          FROM sessions s JOIN users u ON u.id = s.user_id
                          WHERE s.token = ?""", (token,)).fetchone()
    if row is None:
        return None
    if row["expires_at"] <= db.now_stamp() or not row["active"]:
        conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
        return None
    conn.execute("UPDATE sessions SET last_seen = ? WHERE token = ?", (db.now_stamp(), token))
    return {
        "token": row["token"],
        "user_id": row["user_id"],
        "company_id": row["company_id"],
        "username": row["username"],
        "full_name": row["full_name"],
        "role": row["role"],
        "must_change": row["must_change"],
    }


def set_session_company(conn, token, company_id):
    conn.execute("UPDATE sessions SET company_id = ? WHERE token = ?", (company_id, token))


def end_session(conn, token):
    conn.execute("DELETE FROM sessions WHERE token = ?", (token,))


def purge_expired_sessions(conn):
    conn.execute("DELETE FROM sessions WHERE expires_at <= ?", (db.now_stamp(),))


def can(user, action):
    """True if the signed in user is allowed to perform an action."""
    if not user:
        return False
    needed = PERMISSIONS.get(action)
    if needed is None:
        return False
    return ROLES.get(user.get("role"), 0) >= needed


def require(user, action):
    if not can(user, action):
        raise AuthError("Your role does not allow this action.")


def find_user(conn, username):
    """The login of that name on this machine, or None. Case is ignored."""
    return conn.execute("SELECT * FROM users WHERE username = ? COLLATE NOCASE",
                        ((username or "").strip(),)).fetchone()


def has_any_user(conn):
    return conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"] > 0
