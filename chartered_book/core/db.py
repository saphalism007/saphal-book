"""
Database layer.

Saphal Book keeps one SQLite file per company plus one small system file.

  data/system.db              users, the list of companies, login history
  data/books/<slug>.db        the complete books of one company

Keeping each company in its own file means a backup is a plain file copy, one
business can be restored without touching another, and there is no chance of a
query accidentally mixing two sets of books.

Schema changes are applied through numbered migrations so that an existing
database is upgraded in place when the software is improved, never rebuilt.

No third party packages. Standard library only.
"""

import datetime
import os
import re
import shutil
import sqlite3
import sys
import threading

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


APP_NAME = "Saphal Book"
FORMER_APP_NAME = "Chartered Book"


def _default_data_dir():
    """
    Where the books live.

    Set CHARTERED_BOOK_DATA and that wins, which is what the tests use.

    Otherwise the books go in the folder each system keeps application data in.
    On a Mac that matters: an application opened from the Finder is refused
    permission to read or write anything inside Documents or Desktop unless the
    person grants it, and the refusal is silent. Keeping the books in the
    standard place means the icon simply works.
    """
    override = (os.environ.get("SAPHAL_BOOK_DATA")
                or os.environ.get("CHARTERED_BOOK_DATA"))
    if override:
        return os.path.abspath(os.path.expanduser(override))
    home = os.path.expanduser("~")
    if sys.platform == "darwin":
        return os.path.join(home, "Library", "Application Support", APP_NAME)
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or os.path.join(home, "AppData", "Local")
        return os.path.join(base, APP_NAME)
    return os.path.join(os.environ.get("XDG_DATA_HOME") or os.path.join(home, ".local", "share"),
                        "saphal-book")


def _former_data_dir():
    """Where the books were kept when the software was called Saphal Book."""
    home = os.path.expanduser("~")
    if sys.platform == "darwin":
        return os.path.join(home, "Library", "Application Support", FORMER_APP_NAME)
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or os.path.join(home, "AppData", "Local")
        return os.path.join(base, FORMER_APP_NAME)
    return os.path.join(os.environ.get("XDG_DATA_HOME") or os.path.join(home, ".local", "share"),
                        "chartered-book")


def _carry_over_former_name():
    """
    The software used to be called Saphal Book, and the books were kept in a
    folder of that name. Renaming the software must not lose them.

    The folder is moved rather than copied, so there is one set of books and not
    two that slowly drift apart. It is a move within the same parent folder, so
    the operating system does it instantly and either completely or not at all.
    Where the move cannot be made, the old folder goes on being used rather than
    the owner being shown an empty install.
    """
    wanted = _default_data_dir()
    former = _former_data_dir()
    if os.path.exists(wanted) or not os.path.isdir(former) or wanted == former:
        return wanted
    if not os.path.exists(os.path.join(former, "system.db")):
        return wanted
    try:
        os.makedirs(os.path.dirname(wanted), exist_ok=True)
        os.rename(former, wanted)
    except OSError:
        try:
            shutil.copytree(former, wanted)
        except OSError:
            return former
    return wanted


DATA_DIR = _carry_over_former_name()
BOOKS_DIR = os.path.join(DATA_DIR, "books")
BACKUP_DIR = os.path.join(DATA_DIR, "backups")
SYSTEM_DB = os.path.join(DATA_DIR, "system.db")

# Books kept in the project folder by an earlier version.
LEGACY_DATA_DIR = os.path.join(BASE_DIR, "data")

_local = threading.local()


def ensure_dirs():
    _carry_forward_old_books()
    for path in (DATA_DIR, BOOKS_DIR, BACKUP_DIR):
        os.makedirs(path, exist_ok=True)


def _carry_forward_old_books():
    """
    Move books written by an earlier version into the new place, once.

    Nothing is deleted. The old folder is left behind with a note saying where
    its contents went, so there is never a moment where the books exist only in
    a folder that is being written to.
    """
    if DATA_DIR == LEGACY_DATA_DIR:
        return
    if not os.path.isdir(LEGACY_DATA_DIR):
        return
    if os.path.exists(SYSTEM_DB):
        return
    # Once the move has been done the old folder is left behind with a note in
    # it. Without this check that leftover would be copied into every new set of
    # books made afterwards, which is how somebody ends up looking at a sign in
    # screen on what should have been an empty install.
    if os.path.exists(os.path.join(LEGACY_DATA_DIR, "MOVED.txt")):
        return
    old_system = os.path.join(LEGACY_DATA_DIR, "system.db")
    if not os.path.exists(old_system):
        return
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        for name in os.listdir(LEGACY_DATA_DIR):
            source = os.path.join(LEGACY_DATA_DIR, name)
            target = os.path.join(DATA_DIR, name)
            if os.path.exists(target):
                continue
            if os.path.isdir(source):
                shutil.copytree(source, target)
            else:
                shutil.copy2(source, target)
        with open(os.path.join(LEGACY_DATA_DIR, "MOVED.txt"), "w", encoding="utf-8") as note:
            note.write(
                "The books were copied to:\n\n    %s\n\n"
                "That is where Saphal Book reads and writes them now, because an\n"
                "application opened from the Finder on a Mac is not allowed into the\n"
                "Documents folder without being asked first.\n\n"
                "What is left here is the copy as it stood when it moved. It is safe to\n"
                "delete once you are happy everything is in the new place.\n" % DATA_DIR)
    except OSError:
        # If the copy cannot be made, carry on with the old folder rather than
        # starting with empty books.
        globals()["DATA_DIR"] = LEGACY_DATA_DIR
        globals()["BOOKS_DIR"] = os.path.join(LEGACY_DATA_DIR, "books")
        globals()["BACKUP_DIR"] = os.path.join(LEGACY_DATA_DIR, "backups")
        globals()["SYSTEM_DB"] = os.path.join(LEGACY_DATA_DIR, "system.db")


def slugify(name):
    slug = re.sub(r"[^a-z0-9]+", "_", str(name).lower()).strip("_")
    return slug or "company"


def company_db_path(slug):
    return os.path.join(BOOKS_DIR, "%s.db" % slugify(slug))


# True when the engine is running inside a browser through Pyodide rather than
# on a computer of its own.
IN_BROWSER = sys.platform == "emscripten" or "pyodide" in sys.modules


def connect(path):
    """Open a connection with the settings this application relies on."""
    ensure_dirs()
    conn = sqlite3.connect(path, timeout=30, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    if IN_BROWSER:
        # A browser filesystem has no shared memory and no real file locking, so
        # the write ahead log cannot work there. A plain rollback journal can,
        # and since only one tab ever holds the books there is nothing to
        # contend with anyway.
        conn.execute("PRAGMA journal_mode = TRUNCATE")
        conn.execute("PRAGMA synchronous = FULL")
    else:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = FULL")
    conn.execute("PRAGMA busy_timeout = 30000")
    return conn


class Transaction:
    """
    Context manager giving an all or nothing write.

    A voucher touches several tables. If anything raises part way through, the
    whole voucher must vanish rather than leave the books half posted.
    """

    def __init__(self, conn):
        self.conn = conn

    def __enter__(self):
        self.conn.execute("BEGIN IMMEDIATE")
        return self.conn

    def __exit__(self, exc_type, exc, tb):
        if exc_type is None:
            self.conn.execute("COMMIT")
        else:
            self.conn.execute("ROLLBACK")
        return False


def now_stamp():
    return datetime.datetime.now().replace(microsecond=0).isoformat(sep=" ")


# Migration machinery


def _schema_version(conn):
    conn.execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL)")
    row = conn.execute("SELECT MAX(version) AS v FROM schema_version").fetchone()
    return row["v"] or 0


def apply_migrations(conn, migrations, label):
    """Run every migration newer than the recorded version."""
    current = _schema_version(conn)
    for version, name, script in migrations:
        if version <= current:
            continue
        # executescript ends any open transaction of its own, so the migration
        # carries its own BEGIN and COMMIT. SQLite makes DDL transactional, so a
        # failure half way leaves the database exactly as it was.
        bundle = "BEGIN;\n%s\nINSERT INTO schema_version (version) VALUES (%d);\nCOMMIT;" % (
            script, version)
        try:
            conn.executescript(bundle)
        except Exception as exc:
            try:
                conn.execute("ROLLBACK")
            except sqlite3.OperationalError:
                pass
            raise RuntimeError("Migration %s.%s (%s) failed: %s" % (label, version, name, exc))
    return _schema_version(conn)


SYSTEM_MIGRATIONS = [
    (1, "users and companies", """
    CREATE TABLE users (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        username        TEXT NOT NULL UNIQUE COLLATE NOCASE,
        full_name       TEXT NOT NULL DEFAULT '',
        password_hash   TEXT NOT NULL,
        password_salt   TEXT NOT NULL,
        iterations      INTEGER NOT NULL,
        role            TEXT NOT NULL DEFAULT 'operator',
        active          INTEGER NOT NULL DEFAULT 1,
        must_change      INTEGER NOT NULL DEFAULT 0,
        created_at      TEXT NOT NULL,
        last_login_at   TEXT,
        failed_attempts INTEGER NOT NULL DEFAULT 0,
        locked_until    TEXT
    );

    CREATE TABLE companies (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        slug            TEXT NOT NULL UNIQUE,
        name            TEXT NOT NULL,
        name_np         TEXT NOT NULL DEFAULT '',
        business_type   TEXT NOT NULL DEFAULT 'trading',
        active          INTEGER NOT NULL DEFAULT 1,
        sort_order      INTEGER NOT NULL DEFAULT 0,
        created_at      TEXT NOT NULL
    );

    CREATE TABLE user_company_access (
        user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        company_id  INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
        role        TEXT NOT NULL DEFAULT 'operator',
        PRIMARY KEY (user_id, company_id)
    );

    CREATE TABLE sessions (
        token       TEXT PRIMARY KEY,
        user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        company_id  INTEGER,
        created_at  TEXT NOT NULL,
        expires_at  TEXT NOT NULL,
        last_seen   TEXT NOT NULL
    );

    CREATE TABLE login_history (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        username    TEXT NOT NULL,
        at          TEXT NOT NULL,
        outcome     TEXT NOT NULL,
        note        TEXT NOT NULL DEFAULT ''
    );

    CREATE TABLE app_settings (
        key     TEXT PRIMARY KEY,
        value   TEXT NOT NULL
    );

    CREATE INDEX idx_sessions_user ON sessions(user_id);
    CREATE INDEX idx_login_history_at ON login_history(at);
    """),
]


SYSTEM_MIGRATIONS.append((2, "carrying books between devices", """

    -- What this device knows about each set of books on the server.
    --
    -- version is the number this device last agreed with the server. Sending
    -- anything up while that number is behind is refused, which is what stops a
    -- tablet that has been out of range all day from flattening a day of
    -- counter sales entered on the shop machine.
    --
    -- The fingerprint the server files the books under is not kept here. It is
    -- worked out from the owner's key each time, and that key only exists while
    -- somebody is signed in.
    CREATE TABLE cloud_books (
        slug            TEXT PRIMARY KEY,
        version         INTEGER NOT NULL DEFAULT 0,
        last_sent_at    TEXT NOT NULL DEFAULT '',
        last_brought_at TEXT NOT NULL DEFAULT '',
        last_device     TEXT NOT NULL DEFAULT ''
    );

    -- The account this install is tied to, so the sign in screen can offer the
    -- name back. No password and no key are ever written here.
    CREATE TABLE cloud_account (
        id              INTEGER PRIMARY KEY CHECK (id = 1),
        username        TEXT NOT NULL DEFAULT '',
        user_id         TEXT NOT NULL DEFAULT '',
        last_signed_in  TEXT NOT NULL DEFAULT ''
    );
"""))


SYSTEM_MIGRATIONS.append((3, "knowing when a set of books has changed", """

    -- A fingerprint of the books as they were the last time this device and the
    -- server agreed. Comparing it against the books now is how the software
    -- knows whether anything has been entered since, without keeping a list of
    -- what was entered.
    --
    -- This is what makes syncing automatic rather than something to remember.
    -- Changed here and not there means send. Changed there and not here means
    -- fetch. Changed in both places means stop and say so, because no rule can
    -- merge two days of separate entries and picking one silently would lose
    -- somebody's work.
    ALTER TABLE cloud_books ADD COLUMN last_hash TEXT NOT NULL DEFAULT '';
"""))


def open_system():
    """Open, and if needed create, the system database."""
    ensure_dirs()
    conn = connect(SYSTEM_DB)
    apply_migrations(conn, SYSTEM_MIGRATIONS, "system")
    return conn
