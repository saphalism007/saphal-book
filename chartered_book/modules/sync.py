"""
Carrying a set of books from one device to another.

The books on this machine are the real ones. This module makes a copy, locks it,
and leaves it with the server so another device can pick it up. Nothing here is
needed for the shop to trade, and everything goes on working with the network
unplugged.

Two things are done carefully because getting either wrong loses work.

A copy is taken with SQLite's own backup, not by reading the file. A database
being written to has part of its contents sitting in a write ahead log beside
it, so reading the file raw can hand over a half finished picture. The backup
call gives a whole one.

Bringing books down never writes over the live file until the downloaded copy
has been opened, checked and found to be a real set of books. A truncated
download that overwrote the shop's ledger would be the worst thing this software
could do.
"""

import datetime
import os
import shutil
import sqlite3
import tempfile

from ..core import cloud, db


class SyncError(Exception):
    """Raised when books cannot be sent or brought back."""


def device_name():
    """Something a person will recognise when told which device wrote last."""
    import platform
    name = ""
    try:
        node = platform.node().strip()
        # A machine whose name is an address, which happens on a network that
        # hands them out, tells nobody anything. Better to say nothing than to
        # report that the books were last written by "192".
        head = node.split(".")[0]
        if node and not node.replace(".", "").isdigit():
            name = head
    except Exception:
        name = ""
    system = platform.system()
    if system == "Darwin":
        system = "Mac"
    elif system == "Windows":
        system = "Windows"
    return ("%s, %s" % (name, system)).strip(", ").strip() or "this device"


def _snapshot(slug):
    """A whole, consistent copy of a set of books, as bytes."""
    path = db.company_db_path(slug)
    if not os.path.exists(path):
        raise SyncError("There are no books called %s on this device." % slug)
    handle, temp = tempfile.mkstemp(suffix=".db")
    os.close(handle)
    try:
        source = sqlite3.connect(path)
        target = sqlite3.connect(temp)
        with target:
            source.backup(target)
        target.close()
        source.close()
        with open(temp, "rb") as reader:
            return reader.read()
    finally:
        for leftover in (temp, temp + "-wal", temp + "-shm"):
            if os.path.exists(leftover):
                os.remove(leftover)


def _looks_like_books(data):
    """
    Open a downloaded copy and satisfy ourselves it is what it claims to be.

    Checked before anything on this machine is touched.
    """
    handle, temp = tempfile.mkstemp(suffix=".db")
    os.close(handle)
    try:
        with open(temp, "wb") as writer:
            writer.write(data)
        conn = None
        try:
            conn = sqlite3.connect(temp)
            if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                return None, "The copy that came down is damaged."
            names = {row[0] for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'")}
            for needed in ("company", "accounts", "vouchers", "voucher_entries"):
                if needed not in names:
                    return None, "The copy that came down is not a set of books."
            row = conn.execute("SELECT name FROM company WHERE id = 1").fetchone()
            return (row[0] if row else ""), ""
        except sqlite3.Error:
            # Not a database at all. Rubbish rather than books, and the reason
            # this check happens before anything on the disk is touched.
            return None, "The copy that came down is not a set of books."
        finally:
            if conn is not None:
                conn.close()
    finally:
        for leftover in (temp, temp + "-wal", temp + "-shm"):
            if os.path.exists(leftover):
                os.remove(leftover)


def _state(system, slug):
    row = system.execute("SELECT * FROM cloud_books WHERE slug = ?", (slug,)).fetchone()
    if row is None:
        return {"slug": slug, "version": 0, "last_sent_at": "", "last_brought_at": "",
                "last_device": ""}
    return dict(row)


def _remember(system, slug, **fields):
    _state(system, slug)
    system.execute("INSERT OR IGNORE INTO cloud_books (slug) VALUES (?)", (slug,))
    for key, value in fields.items():
        system.execute("UPDATE cloud_books SET %s = ? WHERE slug = ?" % key, (value, slug))
    system.commit()


def status(system, session):
    """
    Where every set of books on this device stands against the server.

    One call, so the screen can show the whole picture rather than asking about
    each set of books in turn.
    """
    held = {}
    if session and session.signed_in():
        for row in session.list_books():
            held[row["book_id"]] = row

    out = []
    for company in system.execute(
            "SELECT slug, name FROM companies ORDER BY sort_order, name"):
        slug, name = company["slug"], company["name"]
        state = _state(system, slug)
        entry = {"slug": slug, "name": name, "version": state["version"],
                 "last_sent_at": state["last_sent_at"],
                 "last_brought_at": state["last_brought_at"],
                 "last_device": state["last_device"],
                 "server_version": 0, "server_device": "", "server_updated_at": "",
                 "standing": "not sent yet"}
        if session and session.signed_in():
            fingerprint = cloud.book_fingerprint(session.master_key, slug)
            there = held.pop(fingerprint, None)
            if there:
                entry["server_version"] = there["version"]
                entry["server_device"] = there.get("device", "")
                entry["server_updated_at"] = there.get("updated_at", "")
                if there["version"] == state["version"]:
                    entry["standing"] = "up to date"
                elif there["version"] > state["version"]:
                    entry["standing"] = "newer on the server"
                else:
                    entry["standing"] = "newer here"
            elif state["version"]:
                entry["standing"] = "removed from the server"
        out.append(entry)

    # Books the server carries that this device has never seen. Their names are
    # inside the locked file, so all that can be said is that they are there.
    strangers = len(held)
    return {"books": out, "waiting_elsewhere": strangers,
            "device": device_name(),
            "username": session.username if session and session.signed_in() else ""}


def send_up(system, session, slug):
    """Put this device's copy on the server."""
    if not session or not session.signed_in():
        raise SyncError("Sign in to your account first.")
    state = _state(system, slug)
    expected = state["version"]

    # Where this device believes it has sent these books before but the server
    # is holding nothing, they have been taken off it, by this person on another
    # device or by clearing the account. Refusing to send would leave the books
    # stranded here with no way back up, so the count starts again from nothing.
    if expected and session.remote_version(slug)["version"] == 0:
        expected = 0
        _remember(system, slug, version=0)

    data = _snapshot(slug)
    row = system.execute("SELECT name FROM companies WHERE slug = ?", (slug,)).fetchone()
    version = session.push(slug, data, expected, device=device_name(),
                           name=row["name"] if row else slug)
    _remember(system, slug, version=version,
              last_sent_at=db.now_stamp(), last_device=device_name())
    return {"slug": slug, "version": version, "size": len(data)}


def _install(system, slug, data, version, device):
    """
    Put a downloaded copy in place, once it has been found to be real books.

    The copy being replaced is moved aside rather than deleted, so what was here
    a moment ago still exists on the disk.
    """
    name, complaint = _looks_like_books(data)
    if complaint:
        raise SyncError(complaint + " Nothing on this device has been touched.")

    path = db.company_db_path(slug)
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    kept = ""
    if os.path.exists(path):
        kept = "%s.replaced-%s" % (path, stamp)
        shutil.copy2(path, kept)
    for leftover in (path + "-wal", path + "-shm"):
        if os.path.exists(leftover):
            os.remove(leftover)
    with open(path, "wb") as writer:
        writer.write(data)

    system.execute("INSERT OR IGNORE INTO companies (slug, name, created_at) VALUES (?, ?, ?)",
                   (slug, name or slug, db.now_stamp()))
    if name:
        system.execute("UPDATE companies SET name = ? WHERE slug = ?", (name, slug))
    system.commit()
    _remember(system, slug, version=version, last_brought_at=db.now_stamp(),
              last_device=device or "")
    return {"slug": slug, "name": name, "version": version, "size": len(data),
            "previous_copy_kept_at": kept}


def bring_new(system, session):
    """
    Fetch every set of books on the server that this device has never seen.

    This is what a fresh tablet needs and what it did not have. Signing in told
    it there was something waiting and then offered nothing to press, because the
    list from the server carries fingerprints and a fingerprint cannot be turned
    back into a name. The name is inside the locked file, so each one is fetched,
    opened, and only then does the device learn what it has.
    """
    if not session or not session.signed_in():
        raise SyncError("Sign in to your account first.")
    from ..core import cloud

    mine = {cloud.book_fingerprint(session.master_key, row["slug"])
            for row in system.execute("SELECT slug FROM companies")}
    brought = []
    for row in session.list_books():
        if row["book_id"] in mine:
            continue
        got = session.fetch_by_id(row["book_id"])
        if got is None:
            continue
        brought.append(_install(system, got["slug"], got["data"], got["version"],
                                got.get("device", "")))
    return {"brought": brought, "count": len(brought)}


def bring_down(system, session, slug, expect_name=""):
    """
    Replace this device's copy with the one on the server.

    The live books are moved aside rather than deleted, so a copy taken a moment
    before still exists on the disk if anything goes wrong.
    """
    if not session or not session.signed_in():
        raise SyncError("Sign in to your account first.")
    got = session.fetch(slug)
    if got is None:
        raise SyncError("The server has no books called that under your account.")
    return _install(system, slug, got["data"], got["version"], got.get("device", ""))
